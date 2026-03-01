"""
Tests for gmail/actions.py — trash_messages

Uses an in-process SQLite DB (tmp_path) and mocks out:
  - execute_with_retry (avoid real HTTP)
  - _rate_limiter.consume (avoid sleeps)
  - Gmail service (MagicMock)
"""
import json
import sqlite3
import threading
from unittest.mock import MagicMock, call, patch

import pytest

from cache.database import (
    get_db_path,
    get_email,
    get_sync_state,
    init_db,
    upsert_email,
)
from gmail.actions import trash_messages


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


@pytest.fixture
def mock_service():
    svc = MagicMock()
    # service.users().messages().batchModify(...).execute() is called via execute_with_retry
    return svc


def _make_email(message_id, size=1000):
    return {
        "message_id": message_id,
        "thread_id": "t1",
        "sender_email": "a@b.com",
        "sender_name": "A",
        "subject": f"Email {message_id}",
        "date_ts": 1700000000,
        "size_estimate": size,
        "label_ids": json.dumps(["INBOX"]),
        "is_read": False,
        "is_starred": False,
        "is_important": False,
        "has_attachments": False,
        "unsubscribe_url": None,
        "unsubscribe_post": None,
        "snippet": "snip",
        "fetched_at": 1700000000,
    }


def _seed(account, ids, size=1000):
    """Insert rows for the given IDs and return the list."""
    for mid in ids:
        upsert_email(account, _make_email(mid, size))
    return ids


# Patch both execute_with_retry and the rate limiter for all tests in this module.
# Using autouse=False so individual tests can override where needed.
@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Suppress rate-limiter sleeps."""
    with patch("gmail.actions._rate_limiter") as mock_rl:
        mock_rl.consume = MagicMock()
        yield mock_rl


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

class TestTrashMessagesEmpty:
    def test_empty_list_returns_zero_result(self, account, mock_service):
        result = trash_messages(account, mock_service, [])
        assert result == {"trashed": 0, "size_reclaimed": 0, "stopped_early": False}

    def test_empty_list_makes_no_api_call(self, account, mock_service):
        with patch("gmail.actions.execute_with_retry") as mock_retry:
            trash_messages(account, mock_service, [])
        mock_retry.assert_not_called()


# ---------------------------------------------------------------------------
# Clean path
# ---------------------------------------------------------------------------

class TestTrashMessagesCleanPath:
    def test_returns_correct_counts(self, account, mock_service):
        ids = _seed(account, ["msg_a", "msg_b", "msg_c"], size=500)
        with patch("gmail.actions.execute_with_retry"):
            result = trash_messages(account, mock_service, ids)
        assert result["trashed"] == 3
        assert result["size_reclaimed"] == 1500
        assert result["stopped_early"] is False

    def test_deletes_rows_from_sqlite(self, account, mock_service):
        ids = _seed(account, ["msg_1", "msg_2"])
        with patch("gmail.actions.execute_with_retry"):
            trash_messages(account, mock_service, ids)
        assert get_email(account, "msg_1") is None
        assert get_email(account, "msg_2") is None

    def test_writes_action_log(self, account, mock_service):
        ids = _seed(account, ["msg_x"])
        with patch("gmail.actions.execute_with_retry"):
            trash_messages(account, mock_service, ids)
        conn = sqlite3.connect(get_db_path(account))
        rows = conn.execute("SELECT * FROM action_log WHERE action='trash'").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_batchmodify_called_with_correct_body(self, account, mock_service):
        ids = _seed(account, ["msg_a", "msg_b"])
        with patch("gmail.actions.execute_with_retry") as mock_retry:
            trash_messages(account, mock_service, ids)
        mock_service.users().messages().batchModify.assert_called_once_with(
            userId="me",
            body={"ids": ids, "addLabelIds": ["TRASH"]},
        )
        mock_retry.assert_called_once()


# ---------------------------------------------------------------------------
# progress_callback
# ---------------------------------------------------------------------------

class TestTrashMessagesProgressCallback:
    def test_callback_called_once_for_single_chunk(self, account, mock_service):
        ids = _seed(account, ["m1", "m2", "m3"])
        cb = MagicMock()
        with patch("gmail.actions.execute_with_retry"):
            trash_messages(account, mock_service, ids, progress_callback=cb)
        cb.assert_called_once()

    def test_callback_called_per_chunk(self, account, mock_service):
        # Patch chunk limit to 2 so 4 IDs → 2 chunks → 2 callback calls
        ids = _seed(account, ["m1", "m2", "m3", "m4"])
        cb = MagicMock()
        with patch("gmail.actions.execute_with_retry"), \
             patch("gmail.actions._BATCH_MODIFY_LIMIT", 2):
            trash_messages(account, mock_service, ids, progress_callback=cb)
        assert cb.call_count == 2

    def test_callback_receives_cumulative_totals(self, account, mock_service):
        ids = _seed(account, ["m1", "m2", "m3", "m4"], size=100)
        calls_received = []
        def cb(processed, trashed, size):
            calls_received.append((processed, trashed, size))

        with patch("gmail.actions.execute_with_retry"), \
             patch("gmail.actions._BATCH_MODIFY_LIMIT", 2):
            trash_messages(account, mock_service, ids, progress_callback=cb)

        # After first chunk: 2 trashed, 200 bytes
        assert calls_received[0] == (2, 2, 200)
        # After second chunk: 4 trashed, 400 bytes
        assert calls_received[1] == (4, 4, 400)

    def test_no_callback_does_not_raise(self, account, mock_service):
        ids = _seed(account, ["m1"])
        with patch("gmail.actions.execute_with_retry"):
            result = trash_messages(account, mock_service, ids, progress_callback=None)
        assert result["trashed"] == 1


# ---------------------------------------------------------------------------
# stop_event
# ---------------------------------------------------------------------------

class TestTrashMessagesStopEvent:
    def test_stop_before_first_chunk_returns_stopped_early(self, account, mock_service):
        ids = _seed(account, ["m1", "m2"])
        event = threading.Event()
        event.set()  # already set before we start
        with patch("gmail.actions.execute_with_retry") as mock_retry:
            result = trash_messages(account, mock_service, ids, stop_event=event)
        assert result["stopped_early"] is True
        assert result["trashed"] == 0
        mock_retry.assert_not_called()

    def test_stop_before_first_chunk_leaves_rows_intact(self, account, mock_service):
        ids = _seed(account, ["m1", "m2"])
        event = threading.Event()
        event.set()
        with patch("gmail.actions.execute_with_retry"):
            trash_messages(account, mock_service, ids, stop_event=event)
        assert get_email(account, "m1") is not None
        assert get_email(account, "m2") is not None

    def test_stop_between_chunks_returns_partial_result(self, account, mock_service):
        # 4 IDs, chunk size 2 → stop after first chunk
        ids = _seed(account, ["m1", "m2", "m3", "m4"])
        event = threading.Event()
        call_count = 0

        def fake_retry(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # After first chunk succeeds, set the stop event
                event.set()

        with patch("gmail.actions.execute_with_retry", side_effect=fake_retry), \
             patch("gmail.actions._BATCH_MODIFY_LIMIT", 2):
            result = trash_messages(account, mock_service, ids, stop_event=event)

        assert result["stopped_early"] is True
        assert result["trashed"] == 2  # only first chunk completed

    def test_stop_between_chunks_writes_partial_action_log(self, account, mock_service):
        ids = _seed(account, ["m1", "m2", "m3", "m4"])
        event = threading.Event()
        call_count = 0

        def fake_retry(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                event.set()

        with patch("gmail.actions.execute_with_retry", side_effect=fake_retry), \
             patch("gmail.actions._BATCH_MODIFY_LIMIT", 2):
            trash_messages(account, mock_service, ids, stop_event=event)

        conn = sqlite3.connect(get_db_path(account))
        rows = conn.execute("SELECT count FROM action_log WHERE action='trash'").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == 2  # only 2 trashed

    def test_no_stop_event_completes_normally(self, account, mock_service):
        ids = _seed(account, ["m1", "m2"])
        with patch("gmail.actions.execute_with_retry"):
            result = trash_messages(account, mock_service, ids, stop_event=None)
        assert result["stopped_early"] is False
        assert result["trashed"] == 2


# ---------------------------------------------------------------------------
# Exception / partial log
# ---------------------------------------------------------------------------

class TestTrashMessagesException:
    def test_exception_on_first_chunk_writes_no_log(self, account, mock_service):
        """If nothing was trashed before the error, no action_log entry is written."""
        ids = _seed(account, ["m1", "m2"])
        with patch("gmail.actions.execute_with_retry", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                trash_messages(account, mock_service, ids)
        conn = sqlite3.connect(get_db_path(account))
        rows = conn.execute("SELECT * FROM action_log").fetchall()
        conn.close()
        assert len(rows) == 0

    def test_exception_after_partial_success_writes_partial_log(self, account, mock_service):
        """If first chunk succeeded and second raised, log the first chunk."""
        ids = _seed(account, ["m1", "m2", "m3", "m4"])
        call_count = 0

        def fake_retry(req):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("network blip")

        with patch("gmail.actions.execute_with_retry", side_effect=fake_retry), \
             patch("gmail.actions._BATCH_MODIFY_LIMIT", 2):
            with pytest.raises(RuntimeError):
                trash_messages(account, mock_service, ids)

        conn = sqlite3.connect(get_db_path(account))
        rows = conn.execute("SELECT count FROM action_log WHERE action='trash'").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == 2  # first chunk was logged

    def test_exception_preserves_already_deleted_rows(self, account, mock_service):
        """Rows from the succeeded first chunk must be deleted even when the second chunk fails."""
        ids = _seed(account, ["m1", "m2", "m3", "m4"])
        call_count = 0

        def fake_retry(req):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("boom")

        with patch("gmail.actions.execute_with_retry", side_effect=fake_retry), \
             patch("gmail.actions._BATCH_MODIFY_LIMIT", 2):
            with pytest.raises(RuntimeError):
                trash_messages(account, mock_service, ids)

        assert get_email(account, "m1") is None
        assert get_email(account, "m2") is None
        # Second chunk rows still present (were not trashed)
        assert get_email(account, "m3") is not None
        assert get_email(account, "m4") is not None
