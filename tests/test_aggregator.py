"""
Tests for analysis/aggregator.py

Run with: pytest tests/test_aggregator.py -v
"""
import json
import os
import pytest

from cache.database import init_db, upsert_email
from analysis.aggregator import (
    top_senders_by_count,
    top_senders_by_size,
    category_breakdown,
    storage_timeline,
    overall_stats,
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
        "unsubscribe_url": None,
        "unsubscribe_post": None,
        "snippet": "snippet",
        "fetched_at": 1700000100,
    }


# ---------------------------------------------------------------------------
# top_senders_by_count
# ---------------------------------------------------------------------------

class TestTopSendersByCount:
    def test_returns_senders_ordered_by_count_descending(self, account):
        # alice: 3 emails, bob: 1 email
        for i in range(3):
            upsert_email(account, _make_email(f"a{i}", sender_email="alice@x.com", sender_name="Alice"))
        upsert_email(account, _make_email("b0", sender_email="bob@x.com", sender_name="Bob"))

        result = top_senders_by_count(account)
        assert len(result) == 2
        assert result[0]["sender_email"] == "alice@x.com"
        assert result[0]["count"] == 3
        assert result[1]["sender_email"] == "bob@x.com"
        assert result[1]["count"] == 1

    def test_excludes_starred_emails(self, account):
        upsert_email(account, _make_email("s1", sender_email="star@x.com", is_starred=True))
        upsert_email(account, _make_email("n1", sender_email="normal@x.com"))

        result = top_senders_by_count(account)
        senders = [r["sender_email"] for r in result]
        assert "star@x.com" not in senders
        assert "normal@x.com" in senders

    def test_excludes_important_emails(self, account):
        upsert_email(account, _make_email("i1", sender_email="imp@x.com", is_important=True))
        upsert_email(account, _make_email("n1", sender_email="normal@x.com"))

        result = top_senders_by_count(account)
        senders = [r["sender_email"] for r in result]
        assert "imp@x.com" not in senders

    def test_respects_limit(self, account):
        for i in range(10):
            upsert_email(account, _make_email(f"m{i}", sender_email=f"user{i}@x.com"))

        result = top_senders_by_count(account, limit=5)
        assert len(result) == 5

    def test_empty_database_returns_empty_list(self, account):
        result = top_senders_by_count(account)
        assert result == []

    def test_includes_sender_name(self, account):
        upsert_email(account, _make_email("m1", sender_email="alice@x.com", sender_name="Alice A"))

        result = top_senders_by_count(account)
        assert result[0]["sender_name"] == "Alice A"

    def test_includes_total_size(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", size_estimate=500))
        upsert_email(account, _make_email("m2", sender_email="a@x.com", size_estimate=700))

        result = top_senders_by_count(account)
        assert result[0]["total_size"] == 1200


# ---------------------------------------------------------------------------
# top_senders_by_size
# ---------------------------------------------------------------------------

class TestTopSendersBySize:
    def test_returns_senders_ordered_by_total_size_descending(self, account):
        # alice: 2 small emails (total 200), bob: 1 big email (5000)
        upsert_email(account, _make_email("a1", sender_email="alice@x.com", size_estimate=100))
        upsert_email(account, _make_email("a2", sender_email="alice@x.com", size_estimate=100))
        upsert_email(account, _make_email("b1", sender_email="bob@x.com", size_estimate=5000))

        result = top_senders_by_size(account)
        assert result[0]["sender_email"] == "bob@x.com"
        assert result[0]["total_size"] == 5000
        assert result[1]["sender_email"] == "alice@x.com"
        assert result[1]["total_size"] == 200

    def test_excludes_starred_and_important(self, account):
        upsert_email(account, _make_email("s1", sender_email="star@x.com", size_estimate=9999, is_starred=True))
        upsert_email(account, _make_email("i1", sender_email="imp@x.com", size_estimate=9999, is_important=True))
        upsert_email(account, _make_email("n1", sender_email="normal@x.com", size_estimate=100))

        result = top_senders_by_size(account)
        senders = [r["sender_email"] for r in result]
        assert "star@x.com" not in senders
        assert "imp@x.com" not in senders
        assert "normal@x.com" in senders

    def test_respects_limit(self, account):
        for i in range(10):
            upsert_email(account, _make_email(f"m{i}", sender_email=f"user{i}@x.com", size_estimate=1000 * i))

        result = top_senders_by_size(account, limit=3)
        assert len(result) == 3

    def test_includes_count(self, account):
        upsert_email(account, _make_email("m1", sender_email="a@x.com", size_estimate=500))
        upsert_email(account, _make_email("m2", sender_email="a@x.com", size_estimate=700))

        result = top_senders_by_size(account)
        assert result[0]["count"] == 2


# ---------------------------------------------------------------------------
# category_breakdown
# ---------------------------------------------------------------------------

class TestCategoryBreakdown:
    def test_returns_count_and_size_per_category(self, account):
        upsert_email(account, _make_email("m1", label_ids=["INBOX", "CATEGORY_PROMOTIONS"], size_estimate=100))
        upsert_email(account, _make_email("m2", label_ids=["INBOX", "CATEGORY_PROMOTIONS"], size_estimate=200))
        upsert_email(account, _make_email("m3", label_ids=["INBOX", "CATEGORY_UPDATES"], size_estimate=300))

        result = category_breakdown(account)
        by_cat = {r["category"]: r for r in result}

        assert "CATEGORY_PROMOTIONS" in by_cat
        assert by_cat["CATEGORY_PROMOTIONS"]["count"] == 2
        assert by_cat["CATEGORY_PROMOTIONS"]["total_size"] == 300

        assert "CATEGORY_UPDATES" in by_cat
        assert by_cat["CATEGORY_UPDATES"]["count"] == 1
        assert by_cat["CATEGORY_UPDATES"]["total_size"] == 300

    def test_excludes_starred_and_important(self, account):
        upsert_email(account, _make_email("s1", label_ids=["CATEGORY_SOCIAL"], is_starred=True, size_estimate=100))
        upsert_email(account, _make_email("n1", label_ids=["CATEGORY_SOCIAL"], size_estimate=200))

        result = category_breakdown(account)
        by_cat = {r["category"]: r for r in result}
        assert by_cat["CATEGORY_SOCIAL"]["count"] == 1
        assert by_cat["CATEGORY_SOCIAL"]["total_size"] == 200

    def test_only_includes_category_labels(self, account):
        # INBOX, SENT, UNREAD etc. should NOT appear — only CATEGORY_* labels
        upsert_email(account, _make_email("m1", label_ids=["INBOX", "UNREAD", "CATEGORY_FORUMS"]))

        result = category_breakdown(account)
        categories = [r["category"] for r in result]
        assert "INBOX" not in categories
        assert "UNREAD" not in categories
        assert "CATEGORY_FORUMS" in categories

    def test_empty_database_returns_empty_list(self, account):
        result = category_breakdown(account)
        assert result == []

    def test_emails_with_no_category_excluded(self, account):
        # An email with only INBOX label — no CATEGORY_* — should not appear
        upsert_email(account, _make_email("m1", label_ids=["INBOX"]))

        result = category_breakdown(account)
        assert result == []


# ---------------------------------------------------------------------------
# storage_timeline
# ---------------------------------------------------------------------------

class TestStorageTimeline:
    def test_returns_monthly_buckets_ordered_chronologically(self, account):
        # Jan 2024, Feb 2024, Jan 2024 again
        jan_1 = 1704067200   # 2024-01-01 00:00 UTC
        jan_15 = 1705276800  # 2024-01-15 00:00 UTC
        feb_1 = 1706745600   # 2024-02-01 00:00 UTC

        upsert_email(account, _make_email("m1", date_ts=jan_1, size_estimate=100))
        upsert_email(account, _make_email("m2", date_ts=jan_15, size_estimate=200))
        upsert_email(account, _make_email("m3", date_ts=feb_1, size_estimate=500))

        result = storage_timeline(account, granularity="month")

        assert len(result) == 2
        assert result[0]["period"] == "2024-01"
        assert result[0]["count"] == 2
        assert result[0]["total_size"] == 300
        assert result[1]["period"] == "2024-02"
        assert result[1]["count"] == 1
        assert result[1]["total_size"] == 500

    def test_returns_yearly_buckets(self, account):
        ts_2023 = 1672531200  # 2023-01-01
        ts_2024 = 1704067200  # 2024-01-01

        upsert_email(account, _make_email("m1", date_ts=ts_2023, size_estimate=100))
        upsert_email(account, _make_email("m2", date_ts=ts_2024, size_estimate=200))

        result = storage_timeline(account, granularity="year")

        assert len(result) == 2
        assert result[0]["period"] == "2023"
        assert result[1]["period"] == "2024"

    def test_excludes_starred_and_important(self, account):
        ts = 1704067200
        upsert_email(account, _make_email("s1", date_ts=ts, size_estimate=999, is_starred=True))
        upsert_email(account, _make_email("n1", date_ts=ts, size_estimate=100))

        result = storage_timeline(account)
        assert len(result) == 1
        assert result[0]["total_size"] == 100

    def test_empty_database_returns_empty_list(self, account):
        result = storage_timeline(account)
        assert result == []


# ---------------------------------------------------------------------------
# overall_stats
# ---------------------------------------------------------------------------

class TestOverallStats:
    def test_returns_total_count_and_size(self, account):
        upsert_email(account, _make_email("m1", size_estimate=100))
        upsert_email(account, _make_email("m2", size_estimate=200))

        result = overall_stats(account)
        assert result["total_count"] == 2
        assert result["total_size"] == 300

    def test_returns_read_and_unread_counts(self, account):
        upsert_email(account, _make_email("m1", is_read=True))
        upsert_email(account, _make_email("m2", is_read=False))
        upsert_email(account, _make_email("m3", is_read=False))

        result = overall_stats(account)
        assert result["read_count"] == 1
        assert result["unread_count"] == 2

    def test_returns_starred_and_important_counts(self, account):
        upsert_email(account, _make_email("m1", is_starred=True))
        upsert_email(account, _make_email("m2", is_important=True))
        upsert_email(account, _make_email("m3"))

        result = overall_stats(account)
        assert result["starred_count"] == 1
        assert result["important_count"] == 1

    def test_returns_oldest_and_newest_timestamps(self, account):
        upsert_email(account, _make_email("m1", date_ts=1000000))
        upsert_email(account, _make_email("m2", date_ts=2000000))

        result = overall_stats(account)
        assert result["oldest_ts"] == 1000000
        assert result["newest_ts"] == 2000000

    def test_empty_database(self, account):
        result = overall_stats(account)
        assert result["total_count"] == 0
        assert result["total_size"] == 0
        assert result["read_count"] == 0
        assert result["unread_count"] == 0
        assert result["starred_count"] == 0
        assert result["important_count"] == 0
        assert result["oldest_ts"] is None
        assert result["newest_ts"] is None

    def test_includes_all_emails_not_just_cleanable(self, account):
        """overall_stats reports the full picture — starred/important included."""
        upsert_email(account, _make_email("m1", is_starred=True, size_estimate=100))
        upsert_email(account, _make_email("m2", is_important=True, size_estimate=200))
        upsert_email(account, _make_email("m3", size_estimate=300))

        result = overall_stats(account)
        # All 3 emails counted in totals
        assert result["total_count"] == 3
        assert result["total_size"] == 600
