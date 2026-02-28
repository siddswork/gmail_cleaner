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

    def test_preview_without_sender(self, client, connected_account, account):
        """Preview with no sender_email but with label filter returns matching emails."""
        email, _ = connected_account
        upsert_email(account, _make_email("m1", sender_email="a@x.com"))
        upsert_email(account, _make_email("m2", sender_email="b@x.com"))

        resp = client.post(
            f"/api/cleanup/preview?account={email}",
            json={"labels": ["INBOX"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

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
        ids = [f"m{i}" for i in range(501)]
        resp = client.post(
            f"/api/cleanup/execute?account={email}",
            json={"message_ids": ids},
        )
        assert resp.status_code == 400
        assert "DELETE" in resp.json()["detail"]

    def test_execute_large_batch_with_confirm_word_starts_background_job(
        self, client, connected_account, account
    ):
        """Large batch with confirm_word starts background job and returns 202."""
        email, _ = connected_account
        ids = [f"m{i}" for i in range(501)]

        with patch("backend.routers.cleanup.start_background_cleanup") as mock_start:
            mock_start.return_value = None
            resp = client.post(
                f"/api/cleanup/execute?account={email}",
                json={"message_ids": ids, "confirm_word": "DELETE"},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "running"
        assert data["total"] == 501

    def test_execute_normal_batch_starts_background_job(self, client, connected_account, account):
        """Normal batch starts background job and returns 202 with running status."""
        email, _ = connected_account

        with patch("backend.routers.cleanup.start_background_cleanup") as mock_start:
            mock_start.return_value = None
            resp = client.post(
                f"/api/cleanup/execute?account={email}",
                json={"message_ids": ["m1"]},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "running"
        assert data["total"] == 1

    def test_execute_returns_409_if_job_already_running(self, client, connected_account, account):
        """If a cleanup job is already running, execute returns 409."""
        email, _ = connected_account

        with patch("backend.routers.cleanup.start_background_cleanup") as mock_start:
            mock_start.side_effect = RuntimeError("Cleanup already running")
            resp = client.post(
                f"/api/cleanup/execute?account={email}",
                json={"message_ids": ["m1"]},
            )

        assert resp.status_code == 409


class TestCleanupJobStatus:
    def test_job_status_idle_when_no_job(self, client, connected_account):
        """GET /job-status returns idle status when no job has been started."""
        email, _ = connected_account

        with patch("backend.routers.cleanup.get_cleanup_progress") as mock_progress:
            mock_progress.return_value = {
                "status": "idle", "total": 0, "processed": 0,
                "trashed": 0, "size_reclaimed": 0, "errors": 0,
            }
            resp = client.get(f"/api/cleanup/job-status?account={email}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"

    def test_job_status_returns_running_state(self, client, connected_account):
        """GET /job-status returns running progress when a job is active."""
        email, _ = connected_account

        with patch("backend.routers.cleanup.get_cleanup_progress") as mock_progress:
            mock_progress.return_value = {
                "status": "running", "total": 100, "processed": 42,
                "trashed": 42, "size_reclaimed": 4200, "errors": 0,
            }
            resp = client.get(f"/api/cleanup/job-status?account={email}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["total"] == 100
        assert data["processed"] == 42

    def test_job_status_requires_connected_account(self, client):
        resp = client.get("/api/cleanup/job-status?account=nobody@x.com")
        assert resp.status_code == 400


class TestCleanupStop:
    def test_stop_calls_stop_cleanup(self, client, connected_account):
        """POST /stop signals the running job to stop."""
        email, _ = connected_account

        with patch("backend.routers.cleanup.stop_cleanup") as mock_stop:
            resp = client.post(f"/api/cleanup/stop?account={email}")

        assert resp.status_code == 200
        mock_stop.assert_called_once_with(email)

    def test_stop_requires_connected_account(self, client):
        resp = client.post("/api/cleanup/stop?account=nobody@x.com")
        assert resp.status_code == 400


class TestSmartSweepEndpoints:
    def test_smart_sweep_returns_sender_list(self, client, connected_account):
        """GET /smart-sweep returns a list of qualifying senders."""
        email, _ = connected_account

        with patch("backend.routers.cleanup.smart_sweep_query") as mock_query:
            mock_query.return_value = [
                {"sender_email": "promo@x.com", "count": 50, "total_size": 50000, "read_rate": 0.1},
            ]
            resp = client.get(f"/api/cleanup/smart-sweep?account={email}")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["sender_email"] == "promo@x.com"
        assert data[0]["count"] == 50

    def test_smart_sweep_requires_connected_account(self, client):
        resp = client.get("/api/cleanup/smart-sweep?account=nobody@x.com")
        assert resp.status_code == 400

    def test_smart_sweep_preview_returns_count_and_ids(self, client, connected_account, account):
        """POST /smart-sweep/preview returns message IDs and aggregate size."""
        email, _ = connected_account
        upsert_email(account, _make_email("m1", sender_email="promo@x.com", size_estimate=500))
        upsert_email(account, _make_email("m2", sender_email="promo@x.com", size_estimate=700))

        resp = client.post(
            f"/api/cleanup/smart-sweep/preview?account={email}",
            json={"sender_emails": ["promo@x.com"]},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["total_size"] == 1200
        assert set(data["message_ids"]) == {"m1", "m2"}

    def test_smart_sweep_preview_excludes_starred(self, client, connected_account, account):
        """Starred emails are excluded from smart sweep preview."""
        email, _ = connected_account
        upsert_email(account, _make_email("m1", sender_email="promo@x.com"))
        upsert_email(account, _make_email("m2", sender_email="promo@x.com", is_starred=True))

        resp = client.post(
            f"/api/cleanup/smart-sweep/preview?account={email}",
            json={"sender_emails": ["promo@x.com"]},
        )

        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_smart_sweep_preview_empty_senders(self, client, connected_account):
        """Empty sender list returns zero results."""
        email, _ = connected_account

        resp = client.post(
            f"/api/cleanup/smart-sweep/preview?account={email}",
            json={"sender_emails": []},
        )

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
