"""
Tests for cache/cleanup_manager.py

Run with: pytest tests/test_backend/test_cleanup_manager.py -v
"""
import threading
import time
import pytest
from unittest.mock import MagicMock, patch

from cache.database import init_db


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


@pytest.fixture(autouse=True)
def reset_cleanup_state():
    """Clear module-level state before each test to prevent leakage."""
    import cache.cleanup_manager as cm
    cm.stop_events.clear()
    cm.cleanup_progress.clear()
    yield
    # Clean up after test too
    for event in cm.stop_events.values():
        event.set()
    cm.stop_events.clear()
    cm.cleanup_progress.clear()


@pytest.fixture(autouse=True)
def mock_sync_and_check():
    """Mock incremental_sync and live_label_check so worker doesn't hit Gmail API.
    live_label_check passes all IDs through as safe by default."""
    with patch("cache.cleanup_manager.incremental_sync"):
        with patch("cache.cleanup_manager.live_label_check") as mock_check:
            def passthrough(service, ids):
                return {"safe": ids, "blocked": [], "errors": []}
            mock_check.side_effect = passthrough
            yield mock_check


# ---------------------------------------------------------------------------
# get_cleanup_progress
# ---------------------------------------------------------------------------

class TestGetCleanupProgress:
    def test_returns_idle_when_no_job(self, account):
        """With no job started, status is 'idle' with all zeros."""
        from cache.cleanup_manager import get_cleanup_progress

        result = get_cleanup_progress(account)
        assert result["status"] == "idle"
        assert result["total"] == 0
        assert result["processed"] == 0
        assert result["trashed"] == 0
        assert result["size_reclaimed"] == 0
        assert result["errors"] == 0

    def test_returns_running_state_after_start(self, account):
        """After start_background_cleanup, status is 'running'."""
        from cache.cleanup_manager import start_background_cleanup, get_cleanup_progress

        ids = ["m1", "m2", "m3"]
        barrier = threading.Barrier(2)

        def fake_trash(acct, svc, message_ids, progress_callback=None, stop_event=None):
            barrier.wait()  # signal we're running
            barrier.wait()  # wait for test to inspect state
            return {"trashed": 0, "size_reclaimed": 0, "stopped_early": False}

        with patch("cache.cleanup_manager.trash_messages", side_effect=fake_trash):
            t = start_background_cleanup(account, MagicMock(), ids)
            barrier.wait()  # wait until worker is inside trash_messages
            result = get_cleanup_progress(account)
            barrier.wait()  # let worker finish
            t.join(timeout=2)

        assert result["status"] == "running"
        assert result["total"] == 3


# ---------------------------------------------------------------------------
# start_background_cleanup
# ---------------------------------------------------------------------------

class TestStartBackgroundCleanup:
    def test_returns_a_thread(self, account):
        """start_background_cleanup returns a threading.Thread."""
        from cache.cleanup_manager import start_background_cleanup

        with patch("cache.cleanup_manager.trash_messages",
                   return_value={"trashed": 0, "size_reclaimed": 0, "stopped_early": False}):
            t = start_background_cleanup(account, MagicMock(), ["m1"])
            t.join(timeout=2)

        assert isinstance(t, threading.Thread)

    def test_thread_is_daemon(self, account):
        """The launched thread is a daemon thread."""
        from cache.cleanup_manager import start_background_cleanup

        with patch("cache.cleanup_manager.trash_messages",
                   return_value={"trashed": 0, "size_reclaimed": 0, "stopped_early": False}):
            t = start_background_cleanup(account, MagicMock(), ["m1"])
            assert t.daemon is True
            t.join(timeout=2)

    def test_initializes_progress_to_running(self, account):
        """Immediately after calling start, cleanup_progress has status='running'."""
        from cache.cleanup_manager import start_background_cleanup, get_cleanup_progress

        ids = ["m1", "m2"]
        started = threading.Event()

        def fake_trash(acct, svc, message_ids, progress_callback=None, stop_event=None):
            started.set()
            time.sleep(0.1)
            return {"trashed": 2, "size_reclaimed": 0, "stopped_early": False}

        with patch("cache.cleanup_manager.trash_messages", side_effect=fake_trash):
            t = start_background_cleanup(account, MagicMock(), ids)
            started.wait(timeout=1)
            result = get_cleanup_progress(account)
            t.join(timeout=2)

        assert result["status"] == "running"
        assert result["total"] == 2

    def test_raises_runtime_error_if_already_running(self, account):
        """A second call while a job is active raises RuntimeError."""
        from cache.cleanup_manager import start_background_cleanup
        import cache.cleanup_manager as cm

        barrier = threading.Barrier(2)

        def fake_trash(acct, svc, message_ids, progress_callback=None, stop_event=None):
            barrier.wait()
            barrier.wait()
            return {"trashed": 0, "size_reclaimed": 0, "stopped_early": False}

        with patch("cache.cleanup_manager.trash_messages", side_effect=fake_trash):
            t = start_background_cleanup(account, MagicMock(), ["m1"])
            barrier.wait()  # wait until first worker is inside trash_messages

            with pytest.raises(RuntimeError, match="already running"):
                start_background_cleanup(account, MagicMock(), ["m2"])

            barrier.wait()  # let first worker finish
            t.join(timeout=2)

    def test_second_start_allowed_after_first_completes(self, account):
        """After a job finishes, a new job can be started without error."""
        from cache.cleanup_manager import start_background_cleanup

        with patch("cache.cleanup_manager.trash_messages",
                   return_value={"trashed": 1, "size_reclaimed": 0, "stopped_early": False}):
            t1 = start_background_cleanup(account, MagicMock(), ["m1"])
            t1.join(timeout=2)

            # First job done — should be able to start a second
            t2 = start_background_cleanup(account, MagicMock(), ["m2"])
            t2.join(timeout=2)

        assert not t2.is_alive()

    def test_stores_stop_event_for_account(self, account):
        """start_background_cleanup registers a stop_event while the job runs."""
        from cache.cleanup_manager import start_background_cleanup
        import cache.cleanup_manager as cm

        barrier = threading.Barrier(2)

        def fake_trash(acct, svc, message_ids, progress_callback=None, stop_event=None):
            barrier.wait()  # signal running
            barrier.wait()  # wait for test to check
            return {"trashed": 0, "size_reclaimed": 0, "stopped_early": False}

        with patch("cache.cleanup_manager.trash_messages", side_effect=fake_trash):
            t = start_background_cleanup(account, MagicMock(), ["m1"])
            barrier.wait()  # wait until worker is inside trash_messages
            assert account in cm.stop_events
            assert isinstance(cm.stop_events[account], threading.Event)
            barrier.wait()  # let worker finish
            t.join(timeout=2)

    def test_stop_event_cleaned_up_after_completion(self, account):
        """stop_events entry is removed after the worker finishes."""
        from cache.cleanup_manager import start_background_cleanup
        import cache.cleanup_manager as cm

        with patch("cache.cleanup_manager.trash_messages",
                   return_value={"trashed": 1, "size_reclaimed": 100, "stopped_early": False}):
            t = start_background_cleanup(account, MagicMock(), ["m1"])
            t.join(timeout=2)

        assert account not in cm.stop_events

    def test_stop_event_cleaned_up_after_error(self, account):
        """stop_events entry is removed even when the worker raises."""
        from cache.cleanup_manager import start_background_cleanup
        import cache.cleanup_manager as cm

        with patch("cache.cleanup_manager.trash_messages",
                   side_effect=RuntimeError("boom")):
            t = start_background_cleanup(account, MagicMock(), ["m1"])
            t.join(timeout=2)

        assert account not in cm.stop_events


# ---------------------------------------------------------------------------
# stop_cleanup
# ---------------------------------------------------------------------------

class TestStopCleanup:
    def test_sets_stop_event_for_account(self, account):
        """stop_cleanup sets the stop_event registered for the account."""
        from cache.cleanup_manager import stop_cleanup
        import cache.cleanup_manager as cm

        event = threading.Event()
        cm.stop_events[account] = event

        stop_cleanup(account)
        assert event.is_set()

    def test_noop_when_no_event_registered(self, account):
        """stop_cleanup does not raise when no event is registered."""
        from cache.cleanup_manager import stop_cleanup

        stop_cleanup(account)  # should not raise


# ---------------------------------------------------------------------------
# progress_callback updates cleanup_progress
# ---------------------------------------------------------------------------

class TestProgressCallback:
    def test_progress_updated_via_callback(self, account):
        """The worker's progress_callback updates cleanup_progress counters."""
        from cache.cleanup_manager import start_background_cleanup, get_cleanup_progress

        ids = [f"m{i}" for i in range(5)]
        progress_snapshots = []

        def fake_trash(acct, svc, message_ids, progress_callback=None, stop_event=None):
            # Simulate two callback calls
            if progress_callback:
                progress_callback(3, 3, 300)
                progress_snapshots.append(get_cleanup_progress(acct))
                progress_callback(5, 5, 500)
                progress_snapshots.append(get_cleanup_progress(acct))
            return {"trashed": 5, "size_reclaimed": 500, "stopped_early": False}

        with patch("cache.cleanup_manager.trash_messages", side_effect=fake_trash):
            t = start_background_cleanup(account, MagicMock(), ids)
            t.join(timeout=2)

        assert len(progress_snapshots) == 2
        assert progress_snapshots[0]["processed"] == 3
        assert progress_snapshots[0]["trashed"] == 3
        assert progress_snapshots[0]["size_reclaimed"] == 300
        assert progress_snapshots[1]["processed"] == 5
        assert progress_snapshots[1]["trashed"] == 5
        assert progress_snapshots[1]["size_reclaimed"] == 500


# ---------------------------------------------------------------------------
# Final status after completion
# ---------------------------------------------------------------------------

class TestWorkerSyncAndCheck:
    """Tests that the worker runs incremental_sync and live_label_check."""

    def test_worker_calls_live_label_check(self, account, mock_sync_and_check):
        """The worker calls live_label_check with the provided message_ids."""
        from cache.cleanup_manager import start_background_cleanup

        with patch("cache.cleanup_manager.trash_messages",
                   return_value={"trashed": 2, "size_reclaimed": 200, "stopped_early": False}):
            t = start_background_cleanup(account, MagicMock(), ["m1", "m2"])
            t.join(timeout=2)

        mock_sync_and_check.assert_called_once()
        call_ids = mock_sync_and_check.call_args[0][1]
        assert set(call_ids) == {"m1", "m2"}

    def test_worker_filters_blocked_ids(self, account, mock_sync_and_check):
        """When live_label_check blocks some IDs, only safe ones are trashed."""
        from cache.cleanup_manager import start_background_cleanup, get_cleanup_progress

        mock_sync_and_check.side_effect = lambda svc, ids: {
            "safe": ["m1"], "blocked": ["m2"], "errors": [],
        }

        with patch("cache.cleanup_manager.trash_messages",
                   return_value={"trashed": 1, "size_reclaimed": 100, "stopped_early": False}) as mock_trash:
            t = start_background_cleanup(account, MagicMock(), ["m1", "m2"])
            t.join(timeout=2)

        # trash_messages should only receive the safe ID
        call_args = mock_trash.call_args
        assert call_args[0][2] == ["m1"]

        result = get_cleanup_progress(account)
        assert result["total"] == 1  # updated to reflect safe IDs only

    def test_worker_handles_all_blocked(self, account, mock_sync_and_check):
        """When all IDs are blocked, worker finishes with status=done and total=0."""
        from cache.cleanup_manager import start_background_cleanup, get_cleanup_progress

        mock_sync_and_check.side_effect = lambda svc, ids: {
            "safe": [], "blocked": ["m1", "m2"], "errors": [],
        }

        with patch("cache.cleanup_manager.trash_messages") as mock_trash:
            t = start_background_cleanup(account, MagicMock(), ["m1", "m2"])
            t.join(timeout=2)

        mock_trash.assert_not_called()
        result = get_cleanup_progress(account)
        assert result["status"] == "done"
        assert result["total"] == 0


class TestFinalStatus:
    def test_status_done_after_normal_completion(self, account):
        """After trash_messages returns normally, status is 'done'."""
        from cache.cleanup_manager import start_background_cleanup, get_cleanup_progress

        with patch("cache.cleanup_manager.trash_messages",
                   return_value={"trashed": 2, "size_reclaimed": 200, "stopped_early": False}):
            t = start_background_cleanup(account, MagicMock(), ["m1", "m2"])
            t.join(timeout=2)

        result = get_cleanup_progress(account)
        assert result["status"] == "done"
        assert result["trashed"] == 2
        assert result["size_reclaimed"] == 200

    def test_status_stopped_when_stopped_early(self, account):
        """When trash_messages returns stopped_early=True, status is 'stopped'."""
        from cache.cleanup_manager import start_background_cleanup, get_cleanup_progress

        with patch("cache.cleanup_manager.trash_messages",
                   return_value={"trashed": 1, "size_reclaimed": 100, "stopped_early": True}):
            t = start_background_cleanup(account, MagicMock(), ["m1", "m2"])
            t.join(timeout=2)

        result = get_cleanup_progress(account)
        assert result["status"] == "stopped"

    def test_status_error_on_exception(self, account):
        """When trash_messages raises, status is 'error'."""
        from cache.cleanup_manager import start_background_cleanup, get_cleanup_progress

        with patch("cache.cleanup_manager.trash_messages",
                   side_effect=RuntimeError("API failure")):
            t = start_background_cleanup(account, MagicMock(), ["m1"])
            t.join(timeout=2)

        result = get_cleanup_progress(account)
        assert result["status"] == "error"
