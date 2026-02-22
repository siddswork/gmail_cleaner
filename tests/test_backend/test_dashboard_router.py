"""
Tests for backend/routers/dashboard.py
"""
import json

import pytest

from cache.database import upsert_email


def _make_email(message_id, sender_email="a@x.com", size_estimate=1000,
                label_ids=None, is_starred=False, is_important=False,
                date_ts=1700000000):
    if label_ids is None:
        label_ids = ["INBOX"]
    return {
        "message_id": message_id,
        "thread_id": f"t_{message_id}",
        "sender_email": sender_email,
        "sender_name": "A",
        "subject": "S",
        "date_ts": date_ts,
        "size_estimate": size_estimate,
        "label_ids": json.dumps(label_ids),
        "is_read": True,
        "is_starred": is_starred,
        "is_important": is_important,
        "has_attachments": False,
        "unsubscribe_url": None,
        "unsubscribe_post": None,
        "snippet": "",
        "fetched_at": 1700000100,
    }


class TestDashboardRoutes:
    def test_stats_returns_200(self, client, connected_account):
        email, _ = connected_account
        resp = client.get(f"/api/dashboard/stats?account={email}")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_count" in data

    def test_stats_requires_connected_account(self, client):
        resp = client.get("/api/dashboard/stats?account=nobody@x.com")
        assert resp.status_code == 400

    def test_top_senders_returns_list(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1", sender_email="a@x.com"))
        upsert_email(account, _make_email("m2", sender_email="b@x.com"))
        resp = client.get(f"/api/dashboard/top-senders?account={email}")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_top_senders_sort_by_size(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1", sender_email="big@x.com", size_estimate=9999))
        resp = client.get(f"/api/dashboard/top-senders?account={email}&sort=size")
        assert resp.status_code == 200

    def test_categories_returns_list(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1", label_ids=["CATEGORY_PROMOTIONS"]))
        resp = client.get(f"/api/dashboard/categories?account={email}")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_timeline_returns_list(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1", date_ts=1700000000))
        resp = client.get(f"/api/dashboard/timeline?account={email}")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_timeline_granularity_year(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1", date_ts=1700000000))
        resp = client.get(f"/api/dashboard/timeline?account={email}&granularity=year")
        assert resp.status_code == 200
