"""
Tests for analysis/insights.py

Run with: pytest tests/test_insights.py -v
"""
import json
import time

import pytest

from cache.database import init_db, upsert_email
from analysis.insights import (
    dead_subscriptions,
    oldest_unread_senders,
    read_rate_by_sender,
    unread_by_label,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    """Redirect DATA_DIR to a temp directory so tests don't touch real data."""
    monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def account(tmp_data_dir):
    """An initialized DB for a test account."""
    email = "test@example.com"
    init_db(email)
    return email


def _make_email(
    message_id,
    sender_email="sender@example.com",
    sender_name="Sender",
    date_ts=1700000000,
    size_estimate=1000,
    label_ids=None,
    is_read=True,
    is_starred=False,
    is_important=False,
    unsubscribe_url=None,
    unsubscribe_post=None,
):
    """Helper to build an email dict with sensible defaults."""
    if label_ids is None:
        label_ids = ["INBOX"]
    return {
        "message_id": message_id,
        "thread_id": f"thread_{message_id}",
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": f"Subject {message_id}",
        "date_ts": date_ts,
        "size_estimate": size_estimate,
        "label_ids": json.dumps(label_ids),
        "is_read": is_read,
        "is_starred": is_starred,
        "is_important": is_important,
        "has_attachments": False,
        "unsubscribe_url": unsubscribe_url,
        "unsubscribe_post": unsubscribe_post,
        "snippet": "snippet",
        "fetched_at": 1700000100,
    }


# ---------------------------------------------------------------------------
# dead_subscriptions
# ---------------------------------------------------------------------------

class TestDeadSubscriptions:
    def test_returns_sender_with_all_unread_and_old_unsub_url(self, account):
        """A sender whose emails are all unread, all older than `days`, and have unsub URL."""
        old_ts = int(time.time()) - 100 * 86400  # 100 days ago
        upsert_email(account, _make_email(
            "m1", sender_email="spam@news.com", is_read=False,
            date_ts=old_ts, unsubscribe_url="https://unsub.com/1",
        ))
        upsert_email(account, _make_email(
            "m2", sender_email="spam@news.com", is_read=False,
            date_ts=old_ts - 86400, unsubscribe_url="https://unsub.com/1",
        ))

        result = dead_subscriptions(account, days=30)
        assert len(result) == 1
        assert result[0]["sender_email"] == "spam@news.com"

    def test_excludes_sender_with_any_read_email(self, account):
        """If even one email from a sender is read, they are not dead."""
        old_ts = int(time.time()) - 100 * 86400
        upsert_email(account, _make_email(
            "m1", sender_email="news@co.com", is_read=False,
            date_ts=old_ts, unsubscribe_url="https://unsub.com",
        ))
        upsert_email(account, _make_email(
            "m2", sender_email="news@co.com", is_read=True,
            date_ts=old_ts, unsubscribe_url="https://unsub.com",
        ))

        result = dead_subscriptions(account, days=30)
        assert len(result) == 0

    def test_excludes_sender_with_recent_email(self, account):
        """If the most recent email is newer than `days`, not dead."""
        recent_ts = int(time.time()) - 5 * 86400  # 5 days ago
        upsert_email(account, _make_email(
            "m1", sender_email="fresh@co.com", is_read=False,
            date_ts=recent_ts, unsubscribe_url="https://unsub.com",
        ))

        result = dead_subscriptions(account, days=30)
        assert len(result) == 0

    def test_excludes_sender_without_unsubscribe_url(self, account):
        """No unsub URL means it's not a subscription — skip it."""
        old_ts = int(time.time()) - 100 * 86400
        upsert_email(account, _make_email(
            "m1", sender_email="person@co.com", is_read=False,
            date_ts=old_ts, unsubscribe_url=None,
        ))

        result = dead_subscriptions(account, days=30)
        assert len(result) == 0

    def test_excludes_starred_emails(self, account):
        """Starred emails are excluded from analysis entirely."""
        old_ts = int(time.time()) - 100 * 86400
        upsert_email(account, _make_email(
            "m1", sender_email="star@co.com", is_read=False,
            date_ts=old_ts, unsubscribe_url="https://unsub.com",
            is_starred=True,
        ))

        result = dead_subscriptions(account, days=30)
        assert len(result) == 0

    def test_excludes_important_emails(self, account):
        """Important emails are excluded from analysis entirely."""
        old_ts = int(time.time()) - 100 * 86400
        upsert_email(account, _make_email(
            "m1", sender_email="imp@co.com", is_read=False,
            date_ts=old_ts, unsubscribe_url="https://unsub.com",
            is_important=True,
        ))

        result = dead_subscriptions(account, days=30)
        assert len(result) == 0

    def test_returns_count_and_size(self, account):
        """Result includes total email count and total size for that sender."""
        old_ts = int(time.time()) - 100 * 86400
        upsert_email(account, _make_email(
            "m1", sender_email="bulk@co.com", is_read=False,
            date_ts=old_ts, size_estimate=500, unsubscribe_url="https://unsub.com",
        ))
        upsert_email(account, _make_email(
            "m2", sender_email="bulk@co.com", is_read=False,
            date_ts=old_ts - 86400, size_estimate=700, unsubscribe_url="https://unsub.com",
        ))

        result = dead_subscriptions(account, days=30)
        assert result[0]["count"] == 2
        assert result[0]["total_size"] == 1200

    def test_returns_latest_unsubscribe_url(self, account):
        """Result includes the unsubscribe_url from the most recent email."""
        old_ts = int(time.time()) - 100 * 86400
        upsert_email(account, _make_email(
            "m1", sender_email="bulk@co.com", is_read=False,
            date_ts=old_ts, unsubscribe_url="https://unsub.com/latest",
        ))
        upsert_email(account, _make_email(
            "m2", sender_email="bulk@co.com", is_read=False,
            date_ts=old_ts - 86400, unsubscribe_url="https://unsub.com/older",
        ))

        result = dead_subscriptions(account, days=30)
        assert result[0]["unsubscribe_url"] == "https://unsub.com/latest"

    def test_ordered_by_count_descending(self, account):
        """Results sorted by email count descending."""
        old_ts = int(time.time()) - 100 * 86400
        # fewer: 1 email
        upsert_email(account, _make_email(
            "f1", sender_email="few@co.com", is_read=False,
            date_ts=old_ts, unsubscribe_url="https://unsub.com",
        ))
        # many: 3 emails
        for i in range(3):
            upsert_email(account, _make_email(
                f"m{i}", sender_email="many@co.com", is_read=False,
                date_ts=old_ts, unsubscribe_url="https://unsub.com",
            ))

        result = dead_subscriptions(account, days=30)
        assert result[0]["sender_email"] == "many@co.com"
        assert result[1]["sender_email"] == "few@co.com"

    def test_empty_database_returns_empty_list(self, account):
        result = dead_subscriptions(account, days=30)
        assert result == []


# ---------------------------------------------------------------------------
# read_rate_by_sender
# ---------------------------------------------------------------------------

class TestReadRateBySender:
    def test_returns_read_rate_per_sender(self, account):
        """read_rate = read_count / total_count for each sender."""
        # alice: 2 read, 1 unread -> 2/3
        upsert_email(account, _make_email("a1", sender_email="alice@x.com", is_read=True))
        upsert_email(account, _make_email("a2", sender_email="alice@x.com", is_read=True))
        upsert_email(account, _make_email("a3", sender_email="alice@x.com", is_read=False))

        result = read_rate_by_sender(account)
        assert len(result) == 1
        assert result[0]["sender_email"] == "alice@x.com"
        assert result[0]["total_count"] == 3
        assert result[0]["read_count"] == 2
        assert abs(result[0]["read_rate"] - 2 / 3) < 0.01

    def test_ordered_by_total_count_descending(self, account):
        """Senders with the most emails appear first."""
        for i in range(5):
            upsert_email(account, _make_email(f"a{i}", sender_email="prolific@x.com"))
        for i in range(2):
            upsert_email(account, _make_email(f"b{i}", sender_email="sparse@x.com"))

        result = read_rate_by_sender(account)
        assert result[0]["sender_email"] == "prolific@x.com"
        assert result[1]["sender_email"] == "sparse@x.com"

    def test_respects_limit(self, account):
        for i in range(10):
            upsert_email(account, _make_email(f"m{i}", sender_email=f"user{i}@x.com"))

        result = read_rate_by_sender(account, limit=3)
        assert len(result) == 3

    def test_excludes_starred_emails(self, account):
        upsert_email(account, _make_email("s1", sender_email="star@x.com", is_starred=True))
        upsert_email(account, _make_email("n1", sender_email="normal@x.com"))

        result = read_rate_by_sender(account)
        senders = [r["sender_email"] for r in result]
        assert "star@x.com" not in senders
        assert "normal@x.com" in senders

    def test_excludes_important_emails(self, account):
        upsert_email(account, _make_email("i1", sender_email="imp@x.com", is_important=True))
        upsert_email(account, _make_email("n1", sender_email="normal@x.com"))

        result = read_rate_by_sender(account)
        senders = [r["sender_email"] for r in result]
        assert "imp@x.com" not in senders

    def test_all_unread_sender_has_zero_rate(self, account):
        upsert_email(account, _make_email("m1", sender_email="ghost@x.com", is_read=False))
        upsert_email(account, _make_email("m2", sender_email="ghost@x.com", is_read=False))

        result = read_rate_by_sender(account)
        assert result[0]["read_rate"] == 0.0

    def test_all_read_sender_has_one_rate(self, account):
        upsert_email(account, _make_email("m1", sender_email="diligent@x.com", is_read=True))
        upsert_email(account, _make_email("m2", sender_email="diligent@x.com", is_read=True))

        result = read_rate_by_sender(account)
        assert result[0]["read_rate"] == 1.0

    def test_includes_sender_name(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", sender_name="Alice"))

        result = read_rate_by_sender(account)
        assert result[0]["sender_name"] == "Alice"

    def test_empty_database_returns_empty_list(self, account):
        result = read_rate_by_sender(account)
        assert result == []


# ---------------------------------------------------------------------------
# unread_by_label
# ---------------------------------------------------------------------------

class TestUnreadByLabel:
    def test_returns_unread_count_and_size_per_category(self, account):
        upsert_email(account, _make_email(
            "m1", label_ids=["INBOX", "CATEGORY_PROMOTIONS"],
            is_read=False, size_estimate=100,
        ))
        upsert_email(account, _make_email(
            "m2", label_ids=["INBOX", "CATEGORY_PROMOTIONS"],
            is_read=False, size_estimate=200,
        ))
        upsert_email(account, _make_email(
            "m3", label_ids=["INBOX", "CATEGORY_UPDATES"],
            is_read=False, size_estimate=500,
        ))

        result = unread_by_label(account)
        by_cat = {r["category"]: r for r in result}

        assert by_cat["CATEGORY_PROMOTIONS"]["unread_count"] == 2
        assert by_cat["CATEGORY_PROMOTIONS"]["total_size"] == 300
        assert by_cat["CATEGORY_UPDATES"]["unread_count"] == 1
        assert by_cat["CATEGORY_UPDATES"]["total_size"] == 500

    def test_excludes_read_emails(self, account):
        """Only unread emails are counted."""
        upsert_email(account, _make_email(
            "m1", label_ids=["CATEGORY_SOCIAL"], is_read=True, size_estimate=999,
        ))
        upsert_email(account, _make_email(
            "m2", label_ids=["CATEGORY_SOCIAL"], is_read=False, size_estimate=100,
        ))

        result = unread_by_label(account)
        by_cat = {r["category"]: r for r in result}
        assert by_cat["CATEGORY_SOCIAL"]["unread_count"] == 1
        assert by_cat["CATEGORY_SOCIAL"]["total_size"] == 100

    def test_excludes_starred_and_important(self, account):
        upsert_email(account, _make_email(
            "s1", label_ids=["CATEGORY_SOCIAL"], is_read=False,
            size_estimate=999, is_starred=True,
        ))
        upsert_email(account, _make_email(
            "i1", label_ids=["CATEGORY_SOCIAL"], is_read=False,
            size_estimate=999, is_important=True,
        ))
        upsert_email(account, _make_email(
            "n1", label_ids=["CATEGORY_SOCIAL"], is_read=False,
            size_estimate=100,
        ))

        result = unread_by_label(account)
        by_cat = {r["category"]: r for r in result}
        assert by_cat["CATEGORY_SOCIAL"]["unread_count"] == 1
        assert by_cat["CATEGORY_SOCIAL"]["total_size"] == 100

    def test_only_includes_category_labels(self, account):
        """INBOX, SENT, UNREAD etc. should not appear — only CATEGORY_*."""
        upsert_email(account, _make_email(
            "m1", label_ids=["INBOX", "UNREAD", "CATEGORY_FORUMS"],
            is_read=False, size_estimate=100,
        ))

        result = unread_by_label(account)
        categories = [r["category"] for r in result]
        assert "INBOX" not in categories
        assert "UNREAD" not in categories
        assert "CATEGORY_FORUMS" in categories

    def test_empty_database_returns_empty_list(self, account):
        result = unread_by_label(account)
        assert result == []

    def test_all_read_returns_empty_list(self, account):
        """If every email is read, there are no unread-by-label results."""
        upsert_email(account, _make_email(
            "m1", label_ids=["CATEGORY_PROMOTIONS"], is_read=True,
        ))

        result = unread_by_label(account)
        assert result == []

    def test_sorted_by_category_name(self, account):
        upsert_email(account, _make_email(
            "m1", label_ids=["CATEGORY_UPDATES"], is_read=False,
        ))
        upsert_email(account, _make_email(
            "m2", label_ids=["CATEGORY_FORUMS"], is_read=False,
        ))

        result = unread_by_label(account)
        cats = [r["category"] for r in result]
        assert cats == sorted(cats)


# ---------------------------------------------------------------------------
# oldest_unread_senders
# ---------------------------------------------------------------------------

class TestOldestUnreadSenders:
    def test_returns_senders_ordered_by_oldest_latest_unread(self, account):
        """Senders whose most recent unread is oldest should appear first."""
        upsert_email(account, _make_email(
            "m1", sender_email="old@x.com", is_read=False,
            date_ts=1000000000, size_estimate=500,
        ))
        upsert_email(account, _make_email(
            "m2", sender_email="recent@x.com", is_read=False,
            date_ts=1700000000, size_estimate=300,
        ))

        result = oldest_unread_senders(account, limit=10)
        assert len(result) == 2
        assert result[0]["sender_email"] == "old@x.com"
        assert result[1]["sender_email"] == "recent@x.com"

    def test_returns_unread_count_and_size(self, account):
        upsert_email(account, _make_email(
            "m1", sender_email="bulk@x.com", is_read=False,
            date_ts=1000000000, size_estimate=100,
        ))
        upsert_email(account, _make_email(
            "m2", sender_email="bulk@x.com", is_read=False,
            date_ts=1000086400, size_estimate=200,
        ))

        result = oldest_unread_senders(account, limit=10)
        assert result[0]["unread_count"] == 2
        assert result[0]["total_size"] == 300

    def test_excludes_read_emails(self, account):
        upsert_email(account, _make_email(
            "m1", sender_email="mixed@x.com", is_read=True, date_ts=1000000000,
        ))

        result = oldest_unread_senders(account, limit=10)
        assert len(result) == 0

    def test_excludes_starred(self, account):
        upsert_email(account, _make_email(
            "m1", sender_email="star@x.com", is_read=False,
            date_ts=1000000000, is_starred=True,
        ))

        result = oldest_unread_senders(account, limit=10)
        assert len(result) == 0

    def test_excludes_important(self, account):
        upsert_email(account, _make_email(
            "m1", sender_email="imp@x.com", is_read=False,
            date_ts=1000000000, is_important=True,
        ))

        result = oldest_unread_senders(account, limit=10)
        assert len(result) == 0

    def test_respects_limit(self, account):
        for i in range(5):
            upsert_email(account, _make_email(
                f"m{i}", sender_email=f"user{i}@x.com", is_read=False,
                date_ts=1000000000 + i * 86400,
            ))

        result = oldest_unread_senders(account, limit=3)
        assert len(result) == 3

    def test_empty_database_returns_empty_list(self, account):
        result = oldest_unread_senders(account, limit=10)
        assert result == []

    def test_includes_sender_name(self, account):
        upsert_email(account, _make_email(
            "m1", sender_email="a@x.com", sender_name="Alice",
            is_read=False, date_ts=1000000000,
        ))

        result = oldest_unread_senders(account, limit=10)
        assert result[0]["sender_name"] == "Alice"

    def test_returns_latest_unread_ts(self, account):
        """latest_unread_ts should be the MAX date_ts for unread emails from that sender."""
        upsert_email(account, _make_email(
            "m1", sender_email="a@x.com", is_read=False, date_ts=1000000000,
        ))
        upsert_email(account, _make_email(
            "m2", sender_email="a@x.com", is_read=False, date_ts=1000086400,
        ))

        result = oldest_unread_senders(account, limit=10)
        assert result[0]["latest_unread_ts"] == 1000086400
