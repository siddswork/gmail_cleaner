"""
Tests for analysis/cleanup_queries.py — cleanup_query_messages() + smart_sweep_query()

Run with: pytest tests/test_cleanup_queries.py -v
"""
import json
import time

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

    def test_no_sender_returns_all_matching(self, account):
        """When sender_email is None, return emails from all senders matching other filters."""
        upsert_email(account, _make_email("m1", sender_email="a@x.com", date_ts=1000))
        upsert_email(account, _make_email("m2", sender_email="b@x.com", date_ts=2000))
        upsert_email(account, _make_email("m3", sender_email="c@x.com", date_ts=3000))

        result = cleanup_query_messages(account, sender_email=None, start_ts=1500)
        assert len(result) == 2
        ids = {r["message_id"] for r in result}
        assert ids == {"m2", "m3"}


# ---------------------------------------------------------------------------
# smart_sweep_query
# ---------------------------------------------------------------------------

class TestSmartSweepQuery:
    """Tests for smart_sweep_query — high-volume, low-read-rate promotional senders."""

    # Helpers
    _NOW = int(time.time())
    _RECENT = _NOW - 100          # 100 seconds ago — within any reasonable window
    _OLD = _NOW - (91 * 86400)    # 91 days ago — outside a 90-day window

    def _promo_email(self, message_id, sender_email, date_ts=None, is_read=False,
                     is_starred=False, is_important=False, size_estimate=1000,
                     labels=None):
        if date_ts is None:
            date_ts = self._RECENT
        if labels is None:
            labels = ["INBOX", "CATEGORY_PROMOTIONS"]
        return {
            "message_id": message_id,
            "thread_id": f"t_{message_id}",
            "sender_email": sender_email,
            "sender_name": "Promo",
            "subject": "Sale",
            "date_ts": date_ts,
            "size_estimate": size_estimate,
            "label_ids": json.dumps(labels),
            "is_read": is_read,
            "is_starred": is_starred,
            "is_important": is_important,
            "has_attachments": False,
            "unsubscribe_url": None,
            "unsubscribe_post": None,
            "snippet": "",
            "fetched_at": self._RECENT,
        }

    def test_returns_qualifying_sender(self, account):
        """A sender with >= min_count emails and read_rate <= max_read_rate is returned."""
        from analysis.cleanup_queries import smart_sweep_query

        for i in range(5):
            upsert_email(account, self._promo_email(f"m{i}", "promo@x.com", is_read=False))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert len(result) == 1
        assert result[0]["sender_email"] == "promo@x.com"
        assert result[0]["count"] == 5

    def test_excludes_sender_below_min_count(self, account):
        """Sender with fewer than min_count emails is not returned."""
        from analysis.cleanup_queries import smart_sweep_query

        for i in range(4):
            upsert_email(account, self._promo_email(f"m{i}", "promo@x.com", is_read=False))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert result == []

    def test_excludes_sender_above_max_read_rate(self, account):
        """Sender with read_rate > max_read_rate is excluded."""
        from analysis.cleanup_queries import smart_sweep_query

        # 4 read, 1 unread → read_rate = 0.8, above 0.3 threshold
        for i in range(4):
            upsert_email(account, self._promo_email(f"r{i}", "active@x.com", is_read=True))
        upsert_email(account, self._promo_email("u0", "active@x.com", is_read=False))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert result == []

    def test_excludes_starred_emails_from_count(self, account):
        """Starred emails are excluded — a sender with only starred emails is not returned."""
        from analysis.cleanup_queries import smart_sweep_query

        for i in range(5):
            upsert_email(account, self._promo_email(f"m{i}", "promo@x.com", is_starred=True))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert result == []

    def test_excludes_important_emails_from_count(self, account):
        """Important emails are excluded — a sender with only important emails is not returned."""
        from analysis.cleanup_queries import smart_sweep_query

        for i in range(5):
            upsert_email(account, self._promo_email(f"m{i}", "promo@x.com", is_important=True))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert result == []

    def test_excludes_emails_outside_date_window(self, account):
        """Emails older than `days` are excluded from the count."""
        from analysis.cleanup_queries import smart_sweep_query

        # 5 old emails — outside 90-day window
        for i in range(5):
            upsert_email(account, self._promo_email(f"m{i}", "old@x.com", date_ts=self._OLD))

        result = smart_sweep_query(account, days=90, min_count=5, max_read_rate=0.3)
        assert result == []

    def test_only_counts_emails_in_promo_or_updates_categories(self, account):
        """Emails not in CATEGORY_PROMOTIONS or CATEGORY_UPDATES are excluded."""
        from analysis.cleanup_queries import smart_sweep_query

        # 5 inbox-only emails (no promo/updates label)
        for i in range(5):
            upsert_email(account, self._promo_email(
                f"m{i}", "inbox@x.com", is_read=False, labels=["INBOX"]
            ))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert result == []

    def test_includes_updates_category(self, account):
        """CATEGORY_UPDATES emails also qualify (not just CATEGORY_PROMOTIONS)."""
        from analysis.cleanup_queries import smart_sweep_query

        for i in range(5):
            upsert_email(account, self._promo_email(
                f"m{i}", "updates@x.com", is_read=False,
                labels=["INBOX", "CATEGORY_UPDATES"]
            ))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert len(result) == 1
        assert result[0]["sender_email"] == "updates@x.com"

    def test_custom_categories_filter(self, account):
        """Custom `categories` parameter overrides the default list."""
        from analysis.cleanup_queries import smart_sweep_query

        for i in range(5):
            upsert_email(account, self._promo_email(
                f"m{i}", "social@x.com", is_read=False,
                labels=["INBOX", "CATEGORY_SOCIAL"]
            ))

        # Only CATEGORY_SOCIAL passed as custom category
        result = smart_sweep_query(
            account, days=1, min_count=5, max_read_rate=0.3,
            categories=["CATEGORY_SOCIAL"]
        )
        assert len(result) == 1
        assert result[0]["sender_email"] == "social@x.com"

    def test_returns_correct_fields(self, account):
        """Each result row has sender_email, count, total_size, read_rate."""
        from analysis.cleanup_queries import smart_sweep_query

        for i in range(5):
            upsert_email(account, self._promo_email(
                f"m{i}", "promo@x.com", is_read=False, size_estimate=200
            ))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        row = result[0]
        assert "sender_email" in row
        assert "count" in row
        assert "total_size" in row
        assert "read_rate" in row
        assert row["total_size"] == 1000  # 5 × 200
        assert row["read_rate"] == pytest.approx(0.0)

    def test_ordered_by_count_descending(self, account):
        """Results are ordered highest-count sender first."""
        from analysis.cleanup_queries import smart_sweep_query

        for i in range(10):
            upsert_email(account, self._promo_email(f"a{i}", "big@x.com", is_read=False))
        for i in range(5):
            upsert_email(account, self._promo_email(f"b{i}", "small@x.com", is_read=False))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert len(result) == 2
        assert result[0]["sender_email"] == "big@x.com"
        assert result[1]["sender_email"] == "small@x.com"

    def test_read_rate_calculated_correctly(self, account):
        """read_rate is the fraction of emails that are read (0.0–1.0)."""
        from analysis.cleanup_queries import smart_sweep_query

        # 5 emails: 1 read, 4 unread → read_rate = 0.2
        upsert_email(account, self._promo_email("r0", "promo@x.com", is_read=True))
        for i in range(4):
            upsert_email(account, self._promo_email(f"u{i}", "promo@x.com", is_read=False))

        result = smart_sweep_query(account, days=1, min_count=5, max_read_rate=0.3)
        assert len(result) == 1
        assert result[0]["read_rate"] == pytest.approx(0.2)
