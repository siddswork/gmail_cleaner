"""
Tests for components/safety.py

Run with: pytest tests/test_safety.py -v

Note: confirm_trash_dialog and large_batch_guard are Streamlit UI functions
and are not unit tested here.
"""
import pytest
from unittest.mock import MagicMock

from config.settings import LARGE_BATCH_THRESHOLD


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mock_service_with_labels(label_map: dict[str, list[str]]):
    """
    Build a Gmail service mock where messages().get().execute() returns
    the label_ids specified in label_map keyed by message ID.
    """
    service = MagicMock()

    def get_side_effect(userId, id, format, fields):  # noqa: A002
        response = MagicMock()
        response.execute.return_value = {
            "id": id,
            "labelIds": label_map.get(id, []),
        }
        return response

    service.users().messages().get.side_effect = get_side_effect
    return service


# ---------------------------------------------------------------------------
# live_label_check
# ---------------------------------------------------------------------------

class TestLiveLabelCheck:
    def test_all_safe_messages(self):
        """Messages without STARRED or IMPORTANT go to 'safe'."""
        from components.safety import live_label_check

        service = _mock_service_with_labels({
            "msg1": ["INBOX", "CATEGORY_PROMOTIONS"],
            "msg2": ["INBOX"],
        })

        result = live_label_check(service, ["msg1", "msg2"])

        assert set(result["safe"]) == {"msg1", "msg2"}
        assert result["blocked"] == []
        assert result["errors"] == []

    def test_starred_message_goes_to_blocked(self):
        """A message with STARRED label is blocked."""
        from components.safety import live_label_check

        service = _mock_service_with_labels({
            "msg1": ["INBOX", "STARRED"],
        })

        result = live_label_check(service, ["msg1"])

        assert result["safe"] == []
        assert result["blocked"] == ["msg1"]

    def test_important_message_goes_to_blocked(self):
        """A message with IMPORTANT label is blocked."""
        from components.safety import live_label_check

        service = _mock_service_with_labels({
            "msg1": ["INBOX", "IMPORTANT"],
        })

        result = live_label_check(service, ["msg1"])

        assert result["safe"] == []
        assert result["blocked"] == ["msg1"]

    def test_starred_and_important_not_duplicated(self):
        """A message that is both STARRED and IMPORTANT appears only once in blocked."""
        from components.safety import live_label_check

        service = _mock_service_with_labels({
            "msg1": ["INBOX", "STARRED", "IMPORTANT"],
        })

        result = live_label_check(service, ["msg1"])

        assert result["safe"] == []
        assert result["blocked"] == ["msg1"]
        assert result["errors"] == []

    def test_mixed_safe_and_blocked(self):
        """Correctly partitions a mix of safe and blocked messages."""
        from components.safety import live_label_check

        service = _mock_service_with_labels({
            "safe1": ["INBOX"],
            "safe2": ["CATEGORY_PROMOTIONS"],
            "blocked1": ["INBOX", "STARRED"],
            "blocked2": ["IMPORTANT"],
        })

        result = live_label_check(service, ["safe1", "safe2", "blocked1", "blocked2"])

        assert set(result["safe"]) == {"safe1", "safe2"}
        assert set(result["blocked"]) == {"blocked1", "blocked2"}
        assert result["errors"] == []

    def test_empty_input_returns_empty_buckets(self):
        """Empty message list returns all-empty result."""
        from components.safety import live_label_check

        service = MagicMock()

        result = live_label_check(service, [])

        assert result == {"safe": [], "blocked": [], "errors": []}
        service.users().messages().get.assert_not_called()

    def test_api_error_on_individual_message_goes_to_errors(self):
        """When a single message's API call fails, it goes to 'errors' — not safe or blocked."""
        from components.safety import live_label_check
        from googleapiclient.errors import HttpError

        service = MagicMock()
        fake_resp = MagicMock()
        fake_resp.status = 404

        def get_side_effect(userId, id, format, fields):  # noqa: A002
            if id == "bad_msg":
                response = MagicMock()
                response.execute.side_effect = HttpError(
                    resp=fake_resp, content=b"Not found"
                )
                return response
            response = MagicMock()
            response.execute.return_value = {"id": id, "labelIds": ["INBOX"]}
            return response

        service.users().messages().get.side_effect = get_side_effect

        result = live_label_check(service, ["good_msg", "bad_msg"])

        assert result["safe"] == ["good_msg"]
        assert result["blocked"] == []
        assert result["errors"] == ["bad_msg"]

    def test_fetches_labels_and_id_fields_only(self):
        """The API call requests only id and labelIds to minimise quota usage."""
        from components.safety import live_label_check

        service = _mock_service_with_labels({"msg1": ["INBOX"]})

        live_label_check(service, ["msg1"])

        service.users().messages().get.assert_called_once_with(
            userId="me",
            id="msg1",
            format="minimal",
            fields="id,labelIds",
        )


# ---------------------------------------------------------------------------
# is_large_batch
# ---------------------------------------------------------------------------

class TestIsLargeBatch:
    def test_returns_false_below_threshold(self):
        from components.safety import is_large_batch

        assert is_large_batch(LARGE_BATCH_THRESHOLD - 1) is False

    def test_returns_false_at_exact_threshold(self):
        from components.safety import is_large_batch

        assert is_large_batch(LARGE_BATCH_THRESHOLD) is False

    def test_returns_true_above_threshold(self):
        from components.safety import is_large_batch

        assert is_large_batch(LARGE_BATCH_THRESHOLD + 1) is True

    def test_returns_false_for_zero(self):
        from components.safety import is_large_batch

        assert is_large_batch(0) is False

    def test_returns_true_for_large_number(self):
        from components.safety import is_large_batch

        assert is_large_batch(10_000) is True
