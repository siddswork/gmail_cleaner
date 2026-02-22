"""
Tests for analysis/cleanup_queries.py — cleanup_query_messages()

Run with: pytest tests/test_cleanup_queries.py -v
"""
import json

import pytest

from cache.database import init_db, upsert_email
from analysis.cleanup_queries import cleanup_query_messages


@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def account(tmp_data_dir):
    email = "test@example.com"
    init_db(email)
    return email


def _make_email(
    message_id,
    sender_email="sender@example.com",
    date_ts=1700000000,
    size_estimate=1000,
    label_ids=None,
    is_read=True,
    is_starred=False,
    is_important=False,
):
    if label_ids is None:
        label_ids = ["INBOX"]
    return {
        "message_id": message_id,
        "thread_id": f"thread_{message_id}",
        "sender_email": sender_email,
        "sender_name": "Sender",
        "subject": f"Subject {message_id}",
        "date_ts": date_ts,
        "size_estimate": size_estimate,
        "label_ids": json.dumps(label_ids),
        "is_read": is_read,
        "is_starred": is_starred,
        "is_important": is_important,
        "has_attachments": False,
        "unsubscribe_url": None,
        "unsubscribe_post": None,
        "snippet": "snippet",
        "fetched_at": 1700000100,
    }


class TestCleanupQueryMessages:
    def test_returns_messages_for_sender(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com"))
        upsert_email(account, _make_email("m2", sender_email="b@x.com"))

        result = cleanup_query_messages(account, sender_email="a@x.com")
        assert len(result) == 1
        assert result[0]["message_id"] == "m1"

    def test_excludes_starred(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", is_starred=True))

        result = cleanup_query_messages(account, sender_email="a@x.com")
        assert len(result) == 0

    def test_excludes_important(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", is_important=True))

        result = cleanup_query_messages(account, sender_email="a@x.com")
        assert len(result) == 0

    def test_filter_start_ts(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", date_ts=1000))
        upsert_email(account, _make_email("m2", sender_email="a@x.com", date_ts=2000))

        result = cleanup_query_messages(account, sender_email="a@x.com", start_ts=1500)
        assert len(result) == 1
        assert result[0]["message_id"] == "m2"

    def test_filter_end_ts(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", date_ts=1000))
        upsert_email(account, _make_email("m2", sender_email="a@x.com", date_ts=2000))

        result = cleanup_query_messages(account, sender_email="a@x.com", end_ts=1500)
        assert len(result) == 1
        assert result[0]["message_id"] == "m1"

    def test_filter_unread_only(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", is_read=True))
        upsert_email(account, _make_email("m2", sender_email="a@x.com", is_read=False))

        result = cleanup_query_messages(account, sender_email="a@x.com", unread_only=True)
        assert len(result) == 1
        assert result[0]["message_id"] == "m2"

    def test_filter_min_size(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", size_estimate=100))
        upsert_email(account, _make_email("m2", sender_email="a@x.com", size_estimate=5000))

        result = cleanup_query_messages(account, sender_email="a@x.com", min_size=1000)
        assert len(result) == 1
        assert result[0]["message_id"] == "m2"

    def test_filter_labels(self, account):
        upsert_email(account, _make_email(
            "m1", sender_email="a@x.com", label_ids=["INBOX", "CATEGORY_PROMOTIONS"],
        ))
        upsert_email(account, _make_email(
            "m2", sender_email="a@x.com", label_ids=["INBOX", "CATEGORY_UPDATES"],
        ))

        result = cleanup_query_messages(
            account, sender_email="a@x.com", labels=["CATEGORY_PROMOTIONS"],
        )
        assert len(result) == 1
        assert result[0]["message_id"] == "m1"

    def test_returns_message_id_and_size(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", size_estimate=999))

        result = cleanup_query_messages(account, sender_email="a@x.com")
        assert result[0]["message_id"] == "m1"
        assert result[0]["size_estimate"] == 999

    def test_empty_result(self, account):
        result = cleanup_query_messages(account, sender_email="nobody@x.com")
        assert result == []
