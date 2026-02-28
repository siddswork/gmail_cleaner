"""
Tests for gmail/fetcher.py

Run with: pytest tests/test_fetcher.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from gmail.fetcher import parse_sender, list_message_ids, fetch_metadata_batch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_message(message_id, headers, label_ids=None, size=5000, parts=None):
    payload = {
        "headers": [{"name": k, "value": v} for k, v in headers.items()],
        "mimeType": "text/plain",
    }
    if parts is not None:
        payload["parts"] = parts
    return {
        "id": message_id,
        "threadId": f"thread_{message_id}",
        "labelIds": label_ids or ["INBOX"],
        "sizeEstimate": size,
        "snippet": "This is a snippet.",
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# parse_sender
# ---------------------------------------------------------------------------

class TestParseSender:
    def test_full_format_name_and_email(self):
        name, email = parse_sender("John Doe <john@example.com>")
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_email_only(self):
        name, email = parse_sender("john@example.com")
        assert name == ""
        assert email == "john@example.com"

    def test_quoted_name(self):
        name, email = parse_sender('"Acme Corp" <noreply@acme.com>')
        assert name == "Acme Corp"
        assert email == "noreply@acme.com"

    def test_email_is_lowercased(self):
        name, email = parse_sender("John <JOHN@EXAMPLE.COM>")
        assert email == "john@example.com"

    def test_empty_string_returns_empty_strings(self):
        name, email = parse_sender("")
        assert name == ""
        assert email == ""

    def test_whitespace_stripped_from_name(self):
        name, email = parse_sender("  John Doe  <john@example.com>")
        assert name == "John Doe"


# ---------------------------------------------------------------------------
# list_message_ids
# ---------------------------------------------------------------------------

class TestListMessageIds:
    def _service_with_response(self, message_ids, next_page_token=None):
        service = MagicMock()
        response = {"messages": [{"id": mid} for mid in message_ids]}
        if next_page_token:
            response["nextPageToken"] = next_page_token
        service.users().messages().list().execute.return_value = response
        return service

    def test_returns_message_ids(self):
        service = self._service_with_response(["id1", "id2", "id3"])
        result = list_message_ids(service)
        assert result["ids"] == ["id1", "id2", "id3"]

    def test_returns_next_page_token_when_present(self):
        service = self._service_with_response(["id1"], next_page_token="token_abc")
        result = list_message_ids(service)
        assert result["next_page_token"] == "token_abc"

    def test_next_page_token_is_none_when_absent(self):
        service = self._service_with_response(["id1"])
        result = list_message_ids(service)
        assert result["next_page_token"] is None

    def test_passes_page_token_to_api(self):
        service = self._service_with_response(["id1"])
        list_message_ids(service, page_token="my_token")
        service.users().messages().list.assert_called_with(
            userId="me",
            maxResults=500,
            pageToken="my_token",
            q="",
        )

    def test_passes_query_to_api(self):
        service = self._service_with_response(["id1"])
        list_message_ids(service, query="from:spam@example.com")
        service.users().messages().list.assert_called_with(
            userId="me",
            maxResults=500,
            pageToken=None,
            q="from:spam@example.com",
        )

    def test_returns_empty_list_when_no_messages(self):
        service = MagicMock()
        service.users().messages().list().execute.return_value = {}
        result = list_message_ids(service)
        assert result["ids"] == []
        assert result["next_page_token"] is None


# ---------------------------------------------------------------------------
# fetch_metadata_batch
# ---------------------------------------------------------------------------

class TestFetchMetadataBatch:
    def _run_with_messages(self, service, messages):
        """Helper: simulate batch_execute calling the callback for each message."""
        def fake_batch(svc, reqs, cb, **kwargs):
            for i, msg in enumerate(messages):
                if msg is None:
                    cb(str(i), None, Exception("API error"))
                else:
                    cb(str(i), msg, None)

        with patch("gmail.fetcher.batch_execute", side_effect=fake_batch):
            return fetch_metadata_batch(service, [m["id"] if m else f"err_{i}"
                                                  for i, m in enumerate(messages)])

    def test_returns_list_of_dicts(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "Alice <alice@example.com>",
            "Subject": "Hello",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        })
        results = self._run_with_messages(service, [msg])
        assert len(results) == 1
        assert results[0]["message_id"] == "msg1"

    def test_parses_sender_name_and_email(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "Alice <alice@example.com>",
            "Subject": "Hello",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        })
        results = self._run_with_messages(service, [msg])
        assert results[0]["sender_email"] == "alice@example.com"
        assert results[0]["sender_name"] == "Alice"

    def test_is_starred_true_when_starred_label_present(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "alice@example.com",
            "Subject": "Hi",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        }, label_ids=["INBOX", "STARRED"])
        results = self._run_with_messages(service, [msg])
        assert results[0]["is_starred"] is True

    def test_is_starred_false_when_no_starred_label(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "alice@example.com",
            "Subject": "Hi",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        }, label_ids=["INBOX"])
        results = self._run_with_messages(service, [msg])
        assert results[0]["is_starred"] is False

    def test_is_important_from_important_label(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "alice@example.com",
            "Subject": "Hi",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        }, label_ids=["INBOX", "IMPORTANT"])
        results = self._run_with_messages(service, [msg])
        assert results[0]["is_important"] is True

    def test_is_read_true_when_unread_label_absent(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "alice@example.com",
            "Subject": "Hi",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        }, label_ids=["INBOX"])
        results = self._run_with_messages(service, [msg])
        assert results[0]["is_read"] is True

    def test_is_read_false_when_unread_label_present(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "alice@example.com",
            "Subject": "Hi",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        }, label_ids=["INBOX", "UNREAD"])
        results = self._run_with_messages(service, [msg])
        assert results[0]["is_read"] is False

    def test_has_attachments_true_when_parts_have_filename(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "alice@example.com",
            "Subject": "See attachment",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        }, parts=[{"filename": "report.pdf", "mimeType": "application/pdf"}])
        results = self._run_with_messages(service, [msg])
        assert results[0]["has_attachments"] is True

    def test_has_attachments_false_when_no_filename_in_parts(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "alice@example.com",
            "Subject": "Hi",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        }, parts=[{"filename": "", "mimeType": "text/plain"}])
        results = self._run_with_messages(service, [msg])
        assert results[0]["has_attachments"] is False

    def test_extracts_unsubscribe_url(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "newsletter@example.com",
            "Subject": "Weekly Update",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
            "List-Unsubscribe": "<https://example.com/unsub>",
        })
        results = self._run_with_messages(service, [msg])
        assert results[0]["unsubscribe_url"] == "https://example.com/unsub"

    def test_extracts_url_from_combined_unsubscribe_header(self):
        """Header may contain both <url> and <mailto:...> — extract the https URL."""
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "newsletter@example.com",
            "Subject": "Weekly Update",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
            "List-Unsubscribe": "<https://example.com/unsub>, <mailto:unsub@example.com>",
        })
        results = self._run_with_messages(service, [msg])
        assert results[0]["unsubscribe_url"] == "https://example.com/unsub"

    def test_unsubscribe_url_is_none_when_header_absent(self):
        service = MagicMock()
        msg = make_message("msg1", {
            "From": "alice@example.com",
            "Subject": "Hi",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        })
        results = self._run_with_messages(service, [msg])
        assert results[0]["unsubscribe_url"] is None

    def test_skips_errored_messages_in_batch(self):
        service = MagicMock()
        good_msg = make_message("msg_good", {
            "From": "alice@example.com",
            "Subject": "Hi",
            "Date": "Mon, 1 Jan 2024 00:00:00 +0000",
        })
        # None signals an error in our helper
        results = self._run_with_messages(service, [None, good_msg])
        assert len(results) == 1
        assert results[0]["message_id"] == "msg_good"

    def test_passes_rate_limiter_to_batch_execute(self):
        """fetch_metadata_batch must pass _rate_limiter so batches are throttled."""
        from gmail.client import _rate_limiter
        service = MagicMock()
        with patch("gmail.fetcher.batch_execute") as mock_batch:
            fetch_metadata_batch(service, ["id1", "id2"])
        _, kwargs = mock_batch.call_args
        assert kwargs.get("rate_limiter") is _rate_limiter
