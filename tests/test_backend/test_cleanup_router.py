"""
Tests for backend/routers/cleanup.py
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from cache.database import upsert_email


def _make_email(message_id, sender_email="spam@x.com", size_estimate=1000,
                is_starred=False, is_important=False):
    return {
        "message_id": message_id,
        "thread_id": f"t_{message_id}",
        "sender_email": sender_email,
        "sender_name": "Spam",
        "subject": "Hi",
        "date_ts": 1700000000,
        "size_estimate": size_estimate,
        "label_ids": json.dumps(["INBOX"]),
        "is_read": False,
        "is_starred": is_starred,
        "is_important": is_important,
        "has_attachments": False,
        "unsubscribe_url": None,
        "unsubscribe_post": None,
        "snippet": "",
        "fetched_at": 1700000100,
    }


class TestCleanupPreview:
    def test_preview_returns_count_and_size(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1", size_estimate=500))
        upsert_email(account, _make_email("m2", size_estimate=700))

        resp = client.post(
            f"/api/cleanup/preview?account={email}",
            json={"sender_email": "spam@x.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["total_size"] == 1200
        assert len(data["message_ids"]) == 2

    def test_preview_excludes_starred(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1"))
        upsert_email(account, _make_email("m2", is_starred=True))

        resp = client.post(
            f"/api/cleanup/preview?account={email}",
            json={"sender_email": "spam@x.com"},
        )
        assert resp.json()["count"] == 1

    def test_preview_requires_connected_account(self, client):
        resp = client.post(
            "/api/cleanup/preview?account=nobody@x.com",
            json={"sender_email": "a@x.com"},
        )
        assert resp.status_code == 400


class TestCleanupExecute:
    def test_execute_returns_400_for_empty_ids(self, client, connected_account):
        email, _ = connected_account
        resp = client.post(
            f"/api/cleanup/execute?account={email}",
            json={"message_ids": []},
        )
        assert resp.status_code == 400

    def test_execute_large_batch_requires_confirm_word(self, client, connected_account, account):
        email, _ = connected_account
        # Create 501 message IDs (over threshold of 500)
        ids = [f"m{i}" for i in range(501)]
        resp = client.post(
            f"/api/cleanup/execute?account={email}",
            json={"message_ids": ids},
        )
        assert resp.status_code == 400
        assert "DELETE" in resp.json()["detail"]

    def test_execute_large_batch_with_confirm_word_proceeds(
        self, client, connected_account, account
    ):
        email, svc = connected_account
        # Insert 501 emails in DB
        for i in range(501):
            upsert_email(account, _make_email(f"m{i}"))

        ids = [f"m{i}" for i in range(501)]
        svc.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "id": "m0", "labelIds": []
        }
        svc.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        with patch("backend.routers.cleanup.incremental_sync"):
            with patch("backend.routers.cleanup.live_label_check") as mock_check:
                mock_check.return_value = {"safe": ids, "blocked": [], "errors": []}
                with patch("backend.routers.cleanup.trash_messages") as mock_trash:
                    mock_trash.return_value = {"trashed": 501, "size_reclaimed": 501000}
                    resp = client.post(
                        f"/api/cleanup/execute?account={email}",
                        json={"message_ids": ids, "confirm_word": "DELETE"},
                    )

        assert resp.status_code == 200
        assert resp.json()["trashed"] == 501

    def test_execute_normal_batch(self, client, connected_account, account):
        email, svc = connected_account
        upsert_email(account, _make_email("m1"))

        with patch("backend.routers.cleanup.incremental_sync"):
            with patch("backend.routers.cleanup.live_label_check") as mock_check:
                mock_check.return_value = {"safe": ["m1"], "blocked": [], "errors": []}
                with patch("backend.routers.cleanup.trash_messages") as mock_trash:
                    mock_trash.return_value = {"trashed": 1, "size_reclaimed": 1000}
                    resp = client.post(
                        f"/api/cleanup/execute?account={email}",
                        json={"message_ids": ["m1"]},
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data["trashed"] == 1
        assert data["blocked"] == 0
        assert data["errors"] == 0
