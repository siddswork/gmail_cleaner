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

def _mock_service_with_labels(label_map: dict[str, list[str]], error_ids: set | None = None):
    """
    Build a Gmail service mock that simulates batch execution.

    When batch.execute() is called the callback is invoked for each added
    request_id — using label_map to build the response, or an HttpError for
    any ID listed in error_ids.
    """
    from googleapiclient.errors import HttpError as _HttpError

    error_ids = error_ids or set()
    service = MagicMock()

    def new_batch_http_request(callback):
        batch = MagicMock()
        added = []
        batch.add.side_effect = lambda req, request_id=None: added.append(request_id)

        def batch_execute():
            for mid in added:
                if mid in error_ids:
                    fake_resp = MagicMock()
                    fake_resp.status = 404
                    callback(mid, None, _HttpError(resp=fake_resp, content=b"Not found"))
                else:
                    callback(mid, {"id": mid, "labelIds": label_map.get(mid, [])}, None)

        batch.execute.side_effect = batch_execute
        return batch

    service.new_batch_http_request.side_effect = new_batch_http_request
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

        service = _mock_service_with_labels(
            label_map={"good_msg": ["INBOX"]},
            error_ids={"bad_msg"},
        )

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

    def test_uses_batch_api_for_multiple_messages(self):
        """live_label_check must use the batch API — not individual .execute() calls.

        This test sets up ONLY the batch path (new_batch_http_request). If the
        implementation is sequential it will misclassify STARRED messages as safe
        (because individual .execute() returns a MagicMock, not real label data).
        """
        from components.safety import live_label_check

        ids = [f"msg{i}" for i in range(60)]
        # First two messages are blocked — batch path must surface this correctly
        label_map = {ids[0]: ["STARRED"], ids[1]: ["IMPORTANT"]}

        service = MagicMock()

        def new_batch_http_request(callback):
            batch = MagicMock()
            added = []
            batch.add.side_effect = lambda req, request_id=None: added.append(request_id)
            batch.execute.side_effect = lambda: [
                callback(mid, {"id": mid, "labelIds": label_map.get(mid, [])}, None)
                for mid in added
            ]
            return batch

        service.new_batch_http_request.side_effect = new_batch_http_request

        result = live_label_check(service, ids)

        assert len(result["blocked"]) == 2
        assert len(result["safe"]) == 58
        assert result["errors"] == []
        # ceil(60 / 50) = 2 batches
        assert service.new_batch_http_request.call_count == 2


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
