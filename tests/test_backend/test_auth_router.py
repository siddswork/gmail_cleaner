"""
Tests for backend/routers/auth.py
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend import state


class TestListAccounts:
    def test_returns_empty_when_no_data_dir(self, client, tmp_data_dir):
        resp = client.get("/api/auth/accounts")
        assert resp.status_code == 200
        assert resp.json()["accounts"] == []

    def test_returns_account_with_token(self, client, account, tmp_data_dir):
        token_path = tmp_data_dir / account / "token.json"
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps({"token": "x"}))

        with patch("backend.routers.auth.get_authenticated_service") as mock_svc:
            mock_svc.return_value = MagicMock()
            resp = client.get("/api/auth/accounts")

        assert resp.status_code == 200
        emails = [a["email"] for a in resp.json()["accounts"]]
        assert account in emails

    def test_filters_out_new_directory(self, client, tmp_data_dir):
        """__new__ artifact from old OAuth flow must not appear in accounts list."""
        new_dir = tmp_data_dir / "__new__"
        new_dir.mkdir(parents=True)
        (new_dir / "token.json").write_text(json.dumps({"token": "x"}))

        resp = client.get("/api/auth/accounts")
        assert resp.status_code == 200
        emails = [a["email"] for a in resp.json()["accounts"]]
        assert "__new__" not in emails


class TestLogout:
    def test_logout_removes_service_from_state(self, client, connected_account, tmp_data_dir):
        email, _ = connected_account
        with patch("backend.routers.auth.stop_sync"):
            resp = client.post(f"/api/auth/accounts/{email}/logout")

        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out"
        assert email not in state.gmail_services

    def test_logout_removes_sync_thread_from_state(self, client, connected_account, tmp_data_dir):
        email, _ = connected_account
        mock_thread = MagicMock()
        state.sync_threads[email] = mock_thread

        with patch("backend.routers.auth.stop_sync"):
            resp = client.post(f"/api/auth/accounts/{email}/logout")

        assert resp.status_code == 200
        assert email not in state.sync_threads

    def test_logout_calls_stop_sync(self, client, connected_account, tmp_data_dir):
        email, _ = connected_account
        with patch("backend.routers.auth.stop_sync") as mock_stop:
            client.post(f"/api/auth/accounts/{email}/logout")

        mock_stop.assert_called_once_with(email, thread=None)

    def test_logout_not_connected_is_idempotent(self, client, tmp_data_dir):
        """Logout succeeds even if the account isn't connected (no-op)."""
        resp = client.post("/api/auth/accounts/nobody@x.com/logout")
        assert resp.status_code == 200
