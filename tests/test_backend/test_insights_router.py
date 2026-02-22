"""
Tests for backend/routers/insights.py
"""
import json

import pytest

from cache.database import upsert_email


def _make_email(message_id, sender_email="a@x.com", is_read=False,
                label_ids=None, size_estimate=1000, date_ts=1000000000):
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
        "is_read": is_read,
        "is_starred": False,
        "is_important": False,
        "has_attachments": False,
        "unsubscribe_url": None,
        "unsubscribe_post": None,
        "snippet": "",
        "fetched_at": 1700000100,
    }


class TestInsightsRoutes:
    def test_read_rate_returns_list(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1", is_read=True))
        upsert_email(account, _make_email("m2", is_read=False))
        resp = client.get(f"/api/insights/read-rate?account={email}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["read_rate"] == 0.5

    def test_unread_by_label_returns_list(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email(
            "m1", is_read=False, label_ids=["CATEGORY_PROMOTIONS"],
        ))
        resp = client.get(f"/api/insights/unread-by-label?account={email}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["category"] == "CATEGORY_PROMOTIONS"

    def test_oldest_unread_returns_list(self, client, connected_account, account):
        email, _ = connected_account
        upsert_email(account, _make_email("m1", is_read=False, date_ts=1000000000))
        resp = client.get(f"/api/insights/oldest-unread?account={email}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["latest_unread_ts"] == 1000000000

    def test_routes_require_connected_account(self, client):
        for path in ["/read-rate", "/unread-by-label", "/oldest-unread"]:
            resp = client.get(f"/api/insights{path}?account=nobody@x.com")
            assert resp.status_code == 400
