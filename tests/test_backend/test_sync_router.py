"""
Tests for backend/routers/sync.py
"""
import threading
from unittest.mock import MagicMock, patch

import pytest


class TestSyncRoutes:
    def test_status_returns_sync_info(self, client, connected_account):
        email, _ = connected_account
        resp = client.get(f"/api/sync/status?account={email}")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_synced" in data
        assert "is_complete" in data
        assert "needs_full_sync" in data
        assert "is_syncing" in data

    def test_status_requires_connected_account(self, client):
        resp = client.get("/api/sync/status?account=nobody@x.com")
        assert resp.status_code == 400

    def test_start_launches_sync_thread(self, client, connected_account):
        email, _ = connected_account
        with patch("backend.routers.sync.start_background_sync") as mock_sync:
            mock_thread = MagicMock(spec=threading.Thread)
            mock_sync.return_value = mock_thread
            resp = client.post(f"/api/sync/start?account={email}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["already_running"] is False
        mock_sync.assert_called_once()

    def test_start_returns_already_running_if_active(self, client, connected_account):
        from backend import state
        email, _ = connected_account
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        state.sync_threads[email] = mock_thread

        resp = client.post(f"/api/sync/start?account={email}")
        assert resp.status_code == 200
        assert resp.json()["already_running"] is True

    def test_status_includes_messages_total(self, client, connected_account):
        from cache.database import set_sync_state
        email, _ = connected_account
        set_sync_state(email, "messages_total", "190000")

        resp = client.get(f"/api/sync/status?account={email}")
        assert resp.status_code == 200
        assert resp.json()["messages_total"] == 190000

    def test_status_messages_total_none_when_absent(self, client, connected_account):
        email, _ = connected_account
        resp = client.get(f"/api/sync/status?account={email}")
        assert resp.status_code == 200
        assert resp.json()["messages_total"] is None

    def test_status_includes_sync_started_ts(self, client, connected_account):
        from cache.database import set_sync_state
        email, _ = connected_account
        set_sync_state(email, "sync_started_ts", "1700000000")

        resp = client.get(f"/api/sync/status?account={email}")
        assert resp.status_code == 200
        assert resp.json()["sync_started_ts"] == 1700000000

    def test_force_start_clears_cache_before_sync(self, client, connected_account):
        from cache.database import upsert_email, get_sync_state, set_sync_state, get_email
        import json
        email, _ = connected_account
        # Seed emails + sync_state
        upsert_email(email, {
            "message_id": "stale_msg",
            "thread_id": "t1",
            "sender_email": "a@b.com",
            "sender_name": "A",
            "subject": "Stale",
            "date_ts": 1700000000,
            "size_estimate": 1000,
            "label_ids": json.dumps(["INBOX"]),
            "is_read": False,
            "is_starred": False,
            "is_important": False,
            "has_attachments": False,
            "unsubscribe_url": None,
            "unsubscribe_post": None,
            "snippet": "stale",
            "fetched_at": 1700000000,
        })
        set_sync_state(email, "last_history_id", "abc123")

        with patch("backend.routers.sync.start_background_sync") as mock_sync:
            mock_thread = MagicMock(spec=threading.Thread)
            mock_sync.return_value = mock_thread
            resp = client.post(f"/api/sync/start?account={email}&force=true")

        assert resp.status_code == 200
        assert resp.json()["already_running"] is False
        # Cache must be wiped
        assert get_email(email, "stale_msg") is None
        assert get_sync_state(email, "last_history_id") is None

    def test_normal_start_does_not_clear_cache(self, client, connected_account):
        from cache.database import upsert_email, get_email
        import json
        email, _ = connected_account
        upsert_email(email, {
            "message_id": "keep_msg",
            "thread_id": "t1",
            "sender_email": "a@b.com",
            "sender_name": "A",
            "subject": "Keep",
            "date_ts": 1700000000,
            "size_estimate": 1000,
            "label_ids": json.dumps(["INBOX"]),
            "is_read": False,
            "is_starred": False,
            "is_important": False,
            "has_attachments": False,
            "unsubscribe_url": None,
            "unsubscribe_post": None,
            "snippet": "keep",
            "fetched_at": 1700000000,
        })

        with patch("backend.routers.sync.start_background_sync") as mock_sync:
            mock_thread = MagicMock(spec=threading.Thread)
            mock_sync.return_value = mock_thread
            resp = client.post(f"/api/sync/start?account={email}")

        assert resp.status_code == 200
        # Row must still be there
        assert get_email(email, "keep_msg") is not None

    def test_force_while_sync_running_returns_error(self, client, connected_account):
        from backend import state
        email, _ = connected_account
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        state.sync_threads[email] = mock_thread

        resp = client.post(f"/api/sync/start?account={email}&force=true")
        assert resp.status_code == 200
        assert resp.json()["already_running"] is True
