"""
Tests for gmail/actions.py

Run with: pytest tests/test_actions.py -v
"""
import json
import pytest
from unittest.mock import MagicMock, patch, call

from cache.database import init_db, upsert_email, get_email, batch_upsert_emails, _connect


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def account(tmp_data_dir):
    email = "test@example.com"
    init_db(email)
    return email


def _make_email(message_id, size_estimate=1000, is_starred=False, is_important=False):
    return {
        "message_id": message_id,
        "thread_id": f"thread_{message_id}",
        "sender_email": "sender@example.com",
        "sender_name": "Sender",
        "subject": f"Subject {message_id}",
        "date_ts": 1700000000,
        "size_estimate": size_estimate,
        "label_ids": json.dumps(["INBOX"]),
        "is_read": True,
        "is_starred": is_starred,
        "is_important": is_important,
        "has_attachments": False,
        "unsubscribe_url": None,
        "unsubscribe_post": None,
        "snippet": "snippet",
        "fetched_at": 1700000000,
    }


def _mock_service():
    """Return a minimal Gmail service mock that supports batchModify."""
    service = MagicMock()
    batch_modify_exec = MagicMock(return_value=None)
    service.users().messages().batchModify().execute = batch_modify_exec
    return service


def _action_log_rows(account):
    """Return all rows from action_log for the given account."""
    conn = _connect(account)
    rows = conn.execute("SELECT * FROM action_log").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# trash_messages
# ---------------------------------------------------------------------------

class TestTrashMessages:
    def test_moves_messages_to_trash_via_batch_modify(self, account):
        """batchModify is called with addLabelIds=['TRASH'] for the given IDs."""
        from gmail.actions import trash_messages

        upsert_email(account, _make_email("msg1", size_estimate=500))
        upsert_email(account, _make_email("msg2", size_estimate=1500))

        service = MagicMock()
        service.users().messages().batchModify().execute.return_value = None

        trash_messages(account, service, ["msg1", "msg2"])

        service.users().messages().batchModify.assert_called_with(
            userId="me",
            body={"ids": ["msg1", "msg2"], "addLabelIds": ["TRASH"]},
        )

    def test_deletes_rows_from_cache_after_trash(self, account):
        """Rows are removed from SQLite immediately after a successful API call."""
        from gmail.actions import trash_messages

        upsert_email(account, _make_email("msg1"))
        upsert_email(account, _make_email("msg2"))

        service = MagicMock()
        service.users().messages().batchModify().execute.return_value = None

        trash_messages(account, service, ["msg1", "msg2"])

        assert get_email(account, "msg1") is None
        assert get_email(account, "msg2") is None

    def test_empty_list_is_noop(self, account):
        """Calling with an empty list does nothing — no API call, no DB change."""
        from gmail.actions import trash_messages

        service = MagicMock()
        trash_messages(account, service, [])

        service.users().messages().batchModify.assert_not_called()
        assert _action_log_rows(account) == []

    def test_logs_action_with_correct_fields(self, account):
        """Action log entry has the right action type, count, size_reclaimed."""
        from gmail.actions import trash_messages

        upsert_email(account, _make_email("msg1", size_estimate=400))
        upsert_email(account, _make_email("msg2", size_estimate=600))

        service = MagicMock()
        service.users().messages().batchModify().execute.return_value = None

        trash_messages(account, service, ["msg1", "msg2"])

        rows = _action_log_rows(account)
        assert len(rows) == 1
        row = rows[0]
        assert row["action"] == "trash"
        assert row["count"] == 2
        assert row["size_reclaimed"] == 1000  # 400 + 600
        logged_ids = json.loads(row["message_ids"])
        assert set(logged_ids) == {"msg1", "msg2"}

    def test_chunks_into_1000_per_api_call(self, account):
        """When > 1000 IDs are given, batchModify is called multiple times."""
        from gmail.actions import trash_messages

        ids = [f"msg{i}" for i in range(1500)]
        batch_upsert_emails(account, [_make_email(mid, size_estimate=100) for mid in ids])

        service = MagicMock()
        # Reset after the setup accessor so we count only calls made by trash_messages
        service.users().messages().batchModify().execute.return_value = None
        service.users().messages().batchModify.reset_mock()

        trash_messages(account, service, ids)

        # Should be called twice: first 1000, then 500
        assert service.users().messages().batchModify.call_count == 2

    def test_does_not_delete_from_cache_on_api_error(self, account):
        """If the API call raises, rows stay in SQLite — no partial deletes."""
        from gmail.actions import trash_messages
        from googleapiclient.errors import HttpError

        upsert_email(account, _make_email("msg1"))

        service = MagicMock()
        fake_resp = MagicMock()
        fake_resp.status = 500
        service.users().messages().batchModify().execute.side_effect = HttpError(
            resp=fake_resp, content=b"Server error"
        )

        with pytest.raises(HttpError):
            trash_messages(account, service, ["msg1"])

        # Row must still exist
        assert get_email(account, "msg1") is not None
        assert _action_log_rows(account) == []

    def test_returns_summary_dict(self, account):
        """Return value is a dict with 'trashed' count and 'size_reclaimed'."""
        from gmail.actions import trash_messages

        upsert_email(account, _make_email("msg1", size_estimate=300))
        upsert_email(account, _make_email("msg2", size_estimate=700))

        service = MagicMock()
        service.users().messages().batchModify().execute.return_value = None

        result = trash_messages(account, service, ["msg1", "msg2"])

        assert result["trashed"] == 2
        assert result["size_reclaimed"] == 1000


# ---------------------------------------------------------------------------
# unsubscribe_via_post
# ---------------------------------------------------------------------------

class TestUnsubscribeViaPost:
    def test_returns_true_on_2xx_response(self):
        """A 200 OK from the unsubscribe endpoint returns True."""
        from gmail.actions import unsubscribe_via_post

        with patch("gmail.actions.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            result = unsubscribe_via_post(
                "https://example.com/unsub",
                "List-Unsubscribe=One-Click",
            )

        assert result is True

    def test_posts_correct_headers_and_body(self):
        """POST is sent with Content-Type and the post body as the request body."""
        from gmail.actions import unsubscribe_via_post

        with patch("gmail.actions.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            unsubscribe_via_post(
                "https://example.com/unsub",
                "List-Unsubscribe=One-Click",
            )

        mock_post.assert_called_once_with(
            "https://example.com/unsub",
            data="List-Unsubscribe=One-Click",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

    def test_returns_false_on_non_2xx_response(self):
        """A 4xx/5xx response returns False."""
        from gmail.actions import unsubscribe_via_post

        with patch("gmail.actions.requests.post") as mock_post:
            mock_post.return_value.status_code = 400
            result = unsubscribe_via_post(
                "https://example.com/unsub",
                "List-Unsubscribe=One-Click",
            )

        assert result is False

    def test_returns_false_on_connection_error(self):
        """Network errors (ConnectionError) return False instead of raising."""
        from gmail.actions import unsubscribe_via_post
        import requests

        with patch("gmail.actions.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("refused")
            result = unsubscribe_via_post(
                "https://example.com/unsub",
                "List-Unsubscribe=One-Click",
            )

        assert result is False

    def test_returns_false_on_timeout(self):
        """Request timeouts return False instead of raising."""
        from gmail.actions import unsubscribe_via_post
        import requests

        with patch("gmail.actions.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("timed out")
            result = unsubscribe_via_post(
                "https://example.com/unsub",
                "List-Unsubscribe=One-Click",
            )

        assert result is False


# ---------------------------------------------------------------------------
# unsubscribe_via_url
# ---------------------------------------------------------------------------

class TestUnsubscribeViaUrl:
    def test_returns_url_unchanged(self):
        """Returns the URL as-is for the UI to open in the browser."""
        from gmail.actions import unsubscribe_via_url

        url = "https://example.com/unsubscribe?token=abc123"
        assert unsubscribe_via_url(url) == url

    def test_returns_none_for_none(self):
        from gmail.actions import unsubscribe_via_url

        assert unsubscribe_via_url(None) is None

    def test_returns_none_for_empty_string(self):
        from gmail.actions import unsubscribe_via_url

        assert unsubscribe_via_url("") is None
