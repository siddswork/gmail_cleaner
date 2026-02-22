"""
Tests for components/filters.py

Only apply_filters() is unit-tested — it is pure pandas logic with no
Streamlit dependency. Widget functions (date_range_filter, label_filter,
sender_filter, size_filter) require a running Streamlit context and are
tested manually.

Run with: pytest tests/test_filters.py -v
"""
import json
import pytest
import pandas as pd

from components.filters import apply_filters


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_row(
    message_id="m1",
    sender_email="sender@example.com",
    sender_name="Sender Name",
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
        "sender_email": sender_email,
        "sender_name": sender_name,
        "date_ts": date_ts,
        "size_estimate": size_estimate,
        "label_ids": json.dumps(label_ids),
        "is_read": is_read,
        "is_starred": is_starred,
        "is_important": is_important,
    }


@pytest.fixture
def sample_df():
    """A small DataFrame with a variety of emails for filter testing."""
    rows = [
        _make_row("m1", sender_email="alice@x.com", sender_name="Alice",
                  date_ts=1700000000, size_estimate=500,
                  label_ids=["INBOX", "CATEGORY_PROMOTIONS"], is_read=True),
        _make_row("m2", sender_email="bob@x.com", sender_name="Bob Smith",
                  date_ts=1710000000, size_estimate=5000,
                  label_ids=["INBOX", "CATEGORY_UPDATES"], is_read=False),
        _make_row("m3", sender_email="carol@x.com", sender_name="Carol",
                  date_ts=1720000000, size_estimate=20000,
                  label_ids=["CATEGORY_SOCIAL"], is_read=False),
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Empty filters — pass-through
# ---------------------------------------------------------------------------

class TestEmptyFilters:
    def test_empty_filters_returns_all_rows(self, sample_df):
        result = apply_filters(sample_df, {})
        assert len(result) == 3

    def test_none_values_ignored(self, sample_df):
        result = apply_filters(sample_df, {"start_ts": None, "end_ts": None, "sender": None, "labels": None})
        assert len(result) == 3

    def test_returns_dataframe(self, sample_df):
        result = apply_filters(sample_df, {})
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Date range filter
# ---------------------------------------------------------------------------

class TestDateRangeFilter:
    def test_start_ts_excludes_older_emails(self, sample_df):
        # m1 date_ts=1700000000, m2=1710000000, m3=1720000000
        result = apply_filters(sample_df, {"start_ts": 1705000000})
        assert set(result["message_id"]) == {"m2", "m3"}

    def test_end_ts_excludes_newer_emails(self, sample_df):
        result = apply_filters(sample_df, {"end_ts": 1715000000})
        assert set(result["message_id"]) == {"m1", "m2"}

    def test_start_and_end_ts_together(self, sample_df):
        result = apply_filters(sample_df, {"start_ts": 1705000000, "end_ts": 1715000000})
        assert set(result["message_id"]) == {"m2"}

    def test_start_ts_is_inclusive(self, sample_df):
        result = apply_filters(sample_df, {"start_ts": 1700000000})
        assert "m1" in result["message_id"].values

    def test_end_ts_is_inclusive(self, sample_df):
        result = apply_filters(sample_df, {"end_ts": 1720000000})
        assert "m3" in result["message_id"].values

    def test_no_match_returns_empty_dataframe(self, sample_df):
        result = apply_filters(sample_df, {"start_ts": 9999999999})
        assert len(result) == 0
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Sender filter
# ---------------------------------------------------------------------------

class TestSenderFilter:
    def test_filters_by_sender_email_substring(self, sample_df):
        result = apply_filters(sample_df, {"sender": "alice"})
        assert len(result) == 1
        assert result.iloc[0]["message_id"] == "m1"

    def test_filters_by_sender_name_substring(self, sample_df):
        result = apply_filters(sample_df, {"sender": "bob smith"})
        assert len(result) == 1
        assert result.iloc[0]["message_id"] == "m2"

    def test_sender_filter_is_case_insensitive(self, sample_df):
        result_lower = apply_filters(sample_df, {"sender": "alice"})
        result_upper = apply_filters(sample_df, {"sender": "ALICE"})
        assert len(result_lower) == len(result_upper) == 1

    def test_sender_matches_on_email_domain(self, sample_df):
        result = apply_filters(sample_df, {"sender": "x.com"})
        assert len(result) == 3

    def test_empty_sender_string_returns_all(self, sample_df):
        result = apply_filters(sample_df, {"sender": ""})
        assert len(result) == 3

    def test_no_match_returns_empty(self, sample_df):
        result = apply_filters(sample_df, {"sender": "zzznomatch"})
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Label filter
# ---------------------------------------------------------------------------

class TestLabelFilter:
    def test_filters_to_emails_with_any_selected_label(self, sample_df):
        # m1 has CATEGORY_PROMOTIONS, m2 has CATEGORY_UPDATES, m3 has CATEGORY_SOCIAL
        result = apply_filters(sample_df, {"labels": ["CATEGORY_PROMOTIONS"]})
        assert set(result["message_id"]) == {"m1"}

    def test_multiple_labels_are_unioned(self, sample_df):
        result = apply_filters(sample_df, {"labels": ["CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"]})
        assert set(result["message_id"]) == {"m1", "m3"}

    def test_empty_labels_list_returns_all(self, sample_df):
        result = apply_filters(sample_df, {"labels": []})
        assert len(result) == 3

    def test_label_that_matches_multiple_emails(self, sample_df):
        # Both m1 and m2 have INBOX
        result = apply_filters(sample_df, {"labels": ["INBOX"]})
        assert set(result["message_id"]) == {"m1", "m2"}

    def test_no_matching_label_returns_empty(self, sample_df):
        result = apply_filters(sample_df, {"labels": ["LABEL_DOES_NOT_EXIST"]})
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Size filter
# ---------------------------------------------------------------------------

class TestSizeFilter:
    def test_min_size_excludes_smaller_emails(self, sample_df):
        # m1=500, m2=5000, m3=20000
        result = apply_filters(sample_df, {"min_size": 1000})
        assert set(result["message_id"]) == {"m2", "m3"}

    def test_max_size_excludes_larger_emails(self, sample_df):
        result = apply_filters(sample_df, {"max_size": 5000})
        assert set(result["message_id"]) == {"m1", "m2"}

    def test_min_and_max_size_together(self, sample_df):
        result = apply_filters(sample_df, {"min_size": 1000, "max_size": 10000})
        assert set(result["message_id"]) == {"m2"}

    def test_min_size_is_inclusive(self, sample_df):
        result = apply_filters(sample_df, {"min_size": 500})
        assert "m1" in result["message_id"].values

    def test_max_size_is_inclusive(self, sample_df):
        result = apply_filters(sample_df, {"max_size": 20000})
        assert "m3" in result["message_id"].values


# ---------------------------------------------------------------------------
# Unread filter
# ---------------------------------------------------------------------------

class TestUnreadFilter:
    def test_unread_only_true_excludes_read_emails(self, sample_df):
        # m1 is read, m2 and m3 are unread
        result = apply_filters(sample_df, {"unread_only": True})
        assert set(result["message_id"]) == {"m2", "m3"}

    def test_unread_only_false_returns_all(self, sample_df):
        result = apply_filters(sample_df, {"unread_only": False})
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------

class TestCombinedFilters:
    def test_multiple_filters_are_anded(self, sample_df):
        # Unread AND size >= 1000 → m2 (5000, unread) and m3 (20000, unread)
        # Then add label CATEGORY_UPDATES → only m2
        result = apply_filters(sample_df, {
            "unread_only": True,
            "min_size": 1000,
            "labels": ["CATEGORY_UPDATES"],
        })
        assert set(result["message_id"]) == {"m2"}

    def test_all_filters_together(self, sample_df):
        result = apply_filters(sample_df, {
            "start_ts": 1705000000,
            "end_ts": 1715000000,
            "sender": "bob",
            "labels": ["CATEGORY_UPDATES"],
            "min_size": 1000,
            "max_size": 10000,
            "unread_only": True,
        })
        assert set(result["message_id"]) == {"m2"}

    def test_empty_df_with_any_filter_returns_empty(self):
        empty_df = pd.DataFrame(columns=["message_id", "sender_email", "sender_name",
                                          "date_ts", "size_estimate", "label_ids",
                                          "is_read", "is_starred", "is_important"])
        result = apply_filters(empty_df, {"sender": "alice", "unread_only": True})
        assert len(result) == 0
