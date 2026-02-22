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
