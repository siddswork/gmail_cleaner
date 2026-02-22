"""
Tests for cache/sync_manager.py

Run with: pytest tests/test_sync_manager.py -v
"""
import threading
import pytest
from unittest.mock import MagicMock, patch

from cache.database import init_db, get_sync_state, set_sync_state
from cache.sync_manager import (
    needs_full_sync,
    has_interrupted_sync,
    get_sync_progress,
    start_background_sync,
    stop_sync,
)


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


# ---------------------------------------------------------------------------
# needs_full_sync
# ---------------------------------------------------------------------------

class TestNeedsFullSync:
    def test_returns_true_when_no_sync_has_run(self, account):
        # Fresh DB — no sync state at all
        assert needs_full_sync(account) is True

    def test_returns_false_when_full_sync_is_complete(self, account):
        set_sync_state(account, "last_full_sync_ts", "1700000000")
        assert needs_full_sync(account) is False

    def test_returns_true_when_sync_was_interrupted(self, account):
        # Interrupted: has a page token checkpoint but no completion timestamp
        set_sync_state(account, "full_sync_page_token", "some_token")
        assert needs_full_sync(account) is True


# ---------------------------------------------------------------------------
# has_interrupted_sync
# ---------------------------------------------------------------------------

class TestHasInterruptedSync:
    def test_returns_false_when_no_sync_started(self, account):
        assert has_interrupted_sync(account) is False

    def test_returns_true_when_page_token_exists(self, account):
        set_sync_state(account, "full_sync_page_token", "page_token_abc")
        assert has_interrupted_sync(account) is True

    def test_returns_false_when_sync_completed_cleanly(self, account):
        # full_sync clears the token on completion
        set_sync_state(account, "last_full_sync_ts", "1700000000")
        # page token is None (cleared by full_sync on completion)
        assert has_interrupted_sync(account) is False

    def test_returns_false_when_page_token_is_none_string(self, account):
        # sync_state stores None as the literal string "None" via set_sync_state
        set_sync_state(account, "full_sync_page_token", "None")
        assert has_interrupted_sync(account) is False


# ---------------------------------------------------------------------------
# get_sync_progress
# ---------------------------------------------------------------------------

class TestGetSyncProgress:
    def test_returns_zeros_on_empty_state(self, account):
        result = get_sync_progress(account)
        assert result["total_synced"] == 0
        assert result["is_complete"] is False
        assert result["page_token"] is None
        assert result["last_full_sync_ts"] is None

    def test_returns_total_synced(self, account):
        set_sync_state(account, "total_messages_synced", "4200")
        result = get_sync_progress(account)
        assert result["total_synced"] == 4200

    def test_is_complete_true_when_last_full_sync_ts_set(self, account):
        set_sync_state(account, "last_full_sync_ts", "1700000000")
        result = get_sync_progress(account)
        assert result["is_complete"] is True
        assert result["last_full_sync_ts"] == 1700000000

    def test_page_token_returned_when_present(self, account):
        set_sync_state(account, "full_sync_page_token", "token_xyz")
        result = get_sync_progress(account)
        assert result["page_token"] == "token_xyz"

    def test_page_token_none_when_absent(self, account):
        result = get_sync_progress(account)
        assert result["page_token"] is None


# ---------------------------------------------------------------------------
# start_background_sync
# ---------------------------------------------------------------------------

class TestStartBackgroundSync:
    def test_returns_a_thread(self, account):
        service = MagicMock()
        with patch("cache.sync_manager.full_sync"):
            t = start_background_sync(account, service)
        assert isinstance(t, threading.Thread)

    def test_thread_is_daemon(self, account):
        service = MagicMock()
        with patch("cache.sync_manager.full_sync"):
            t = start_background_sync(account, service)
        assert t.daemon is True

    def test_thread_is_started(self, account):
        service = MagicMock()
        with patch("cache.sync_manager.full_sync"):
            t = start_background_sync(account, service)
        # A started thread is alive or has already finished (if very fast)
        # is_alive() may be False if the mock returned instantly — use is_alive or check via join
        t.join(timeout=2)
        # If join returns within 2s the thread ran and completed — that's correct behavior

    def test_thread_calls_full_sync_with_correct_args(self, account):
        service = MagicMock()
        with patch("cache.sync_manager.full_sync") as mock_full_sync:
            t = start_background_sync(account, service)
            t.join(timeout=2)
        mock_full_sync.assert_called_once()
        call_args = mock_full_sync.call_args
        assert call_args.args[0] == account
        assert call_args.args[1] is service

    def test_thread_passes_progress_callback(self, account):
        service = MagicMock()
        captured_callback = []

        def capture_full_sync(acct, svc, progress_callback=None, stop_event=None):
            captured_callback.append(progress_callback)

        with patch("cache.sync_manager.full_sync", side_effect=capture_full_sync):
            t = start_background_sync(account, service)
            t.join(timeout=2)

        assert len(captured_callback) == 1
        assert callable(captured_callback[0])

    def test_progress_callback_writes_to_sync_state(self, account):
        service = MagicMock()

        def run_callback_immediately(acct, svc, progress_callback=None, stop_event=None):
            if progress_callback:
                progress_callback(1337)

        with patch("cache.sync_manager.full_sync", side_effect=run_callback_immediately):
            t = start_background_sync(account, service)
            t.join(timeout=2)

        assert get_sync_state(account, "total_messages_synced") == "1337"

    def test_start_background_sync_stores_sync_started_ts(self, account):
        """start_background_sync must write sync_started_ts to sync_state."""
        service = MagicMock()
        with patch("cache.sync_manager.full_sync"):
            t = start_background_sync(account, service)
            t.join(timeout=2)

        ts = get_sync_state(account, "sync_started_ts")
        assert ts is not None
        assert int(ts) > 0

    def test_start_background_sync_passes_stop_event_to_full_sync(self, account):
        """full_sync must receive a stop_event keyword arg."""
        import threading
        service = MagicMock()
        captured = []

        def capture(acct, svc, progress_callback=None, stop_event=None):
            captured.append(stop_event)

        with patch("cache.sync_manager.full_sync", side_effect=capture):
            t = start_background_sync(account, service)
            t.join(timeout=2)

        assert len(captured) == 1
        assert isinstance(captured[0], threading.Event)


# ---------------------------------------------------------------------------
# stop_sync
# ---------------------------------------------------------------------------

class TestStopSync:
    def test_stop_sync_signals_event(self, account):
        """stop_sync must set the stop_event for the account."""
        from cache import sync_manager
        import threading

        event = threading.Event()
        sync_manager.stop_events[account] = event

        stop_sync(account)
        assert event.is_set()

    def test_stop_sync_noop_when_no_event(self, account):
        """stop_sync should not raise when no event is registered."""
        stop_sync(account)  # should not raise

    def test_stop_sync_joins_thread_if_running(self, account):
        """stop_sync waits for sync thread to finish."""
        from cache import sync_manager
        import threading

        event = threading.Event()
        sync_manager.stop_events[account] = event

        finished = []
        def slow_worker():
            event.wait()
            finished.append(True)

        t = threading.Thread(target=slow_worker, daemon=True)
        t.start()

        stop_sync(account, thread=t, timeout=2)
        assert finished  # thread completed


# ---------------------------------------------------------------------------
# get_sync_progress — messages_total and sync_started_ts
# ---------------------------------------------------------------------------

class TestGetSyncProgressExtended:
    def test_messages_total_returned_when_set(self, account):
        set_sync_state(account, "messages_total", "190000")
        result = get_sync_progress(account)
        assert result["messages_total"] == 190000

    def test_messages_total_none_when_absent(self, account):
        result = get_sync_progress(account)
        assert result["messages_total"] is None

    def test_sync_started_ts_returned_when_set(self, account):
        set_sync_state(account, "sync_started_ts", "1700000000")
        result = get_sync_progress(account)
        assert result["sync_started_ts"] == 1700000000

    def test_sync_started_ts_none_when_absent(self, account):
        result = get_sync_progress(account)
        assert result["sync_started_ts"] is None
