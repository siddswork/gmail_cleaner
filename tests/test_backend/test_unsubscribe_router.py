"""
Tests for backend/routers/unsubscribe.py
"""
import json
import time
from unittest.mock import patch

import pytest

from cache.database import upsert_email


def _make_email(message_id, sender_email="news@x.com", is_read=False,
                date_ts=None, unsubscribe_url=None, is_starred=False, is_important=False):
    if date_ts is None:
        date_ts = int(time.time()) - 100 * 86400  # 100 days ago
    return {
        "message_id": message_id,
        "thread_id": f"t_{message_id}",
        "sender_email": sender_email,
        "sender_name": "News",
        "subject": "Newsletter",
        "date_ts": date_ts,
        "size_estimate": 5000,
        "label_ids": json.dumps(["INBOX", "CATEGORY_PROMOTIONS"]),
        "is_read": is_read,
        "is_starred": is_starred,
        "is_important": is_important,
        "has_attachments": False,
        "unsubscribe_url": unsubscribe_url,
        "unsubscribe_post": None,
        "snippet": "",
        "fetched_at": 1700000100,
    }


class TestUnsubscribeRoutes:
    def test_dead_returns_list(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email(
            "m1", unsubscribe_url="https://unsub.example.com",
        ))
        resp = client.get(f"/api/unsubscribe/dead?account={email}")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert resp.json()[0]["sender_email"] == "news@x.com"

    def test_dead_requires_connected_account(self, client):
        resp = client.get("/api/unsubscribe/dead?account=nobody@x.com")
        assert resp.status_code == 400

    def test_dead_respects_days_param(self, client, connected_account, account):
        email, _ = connected_account
        recent_ts = int(time.time()) - 5 * 86400  # 5 days ago — not dead at 30 days
        upsert_email(account, _make_email(
            "m1", date_ts=recent_ts, unsubscribe_url="https://unsub.example.com",
        ))
        resp = client.get(f"/api/unsubscribe/dead?account={email}&days=30")
        assert resp.json() == []

    def test_post_unsubscribe_success(self, client, connected_account):
        email, _ = connected_account
        with patch("backend.routers.unsubscribe.unsubscribe_via_post", return_value=True):
            resp = client.post(
                "/api/unsubscribe/post",
                json={"unsubscribe_url": "https://unsub.example.com", "unsubscribe_post": ""},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_post_unsubscribe_failure(self, client, connected_account):
        email, _ = connected_account
        with patch("backend.routers.unsubscribe.unsubscribe_via_post", return_value=False):
            resp = client.post(
                "/api/unsubscribe/post",
                json={"unsubscribe_url": "https://unsub.example.com"},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is False
