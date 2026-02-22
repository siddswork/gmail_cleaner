"""
Filter logic for the Dashboard.

apply_filters() is a pure pandas function — no Streamlit dependency.
Streamlit widget functions (date_range_filter, label_filter, sender_filter,
size_filter) are UI helpers that return values to pass into apply_filters().
"""
import json

import pandas as pd


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    Apply a dict of optional filters to an email DataFrame.
    All active filters are ANDed together.

    Supported keys:
        start_ts    (int)  — keep emails with date_ts >= start_ts
        end_ts      (int)  — keep emails with date_ts <= end_ts
        sender      (str)  — case-insensitive substring match on sender_email or sender_name
        labels      (list) — keep emails that carry at least one of the listed labels
        min_size    (int)  — keep emails with size_estimate >= min_size (bytes)
        max_size    (int)  — keep emails with size_estimate <= max_size (bytes)
        unread_only (bool) — if True, keep only unread emails
    """
    if df.empty:
        return df

    mask = pd.Series(True, index=df.index)

    start_ts = filters.get("start_ts")
    if start_ts is not None:
        mask &= df["date_ts"] >= start_ts

    end_ts = filters.get("end_ts")
    if end_ts is not None:
        mask &= df["date_ts"] <= end_ts

    sender = filters.get("sender")
    if sender:
        term = sender.lower()
        mask &= (
            df["sender_email"].str.lower().str.contains(term, na=False)
            | df["sender_name"].str.lower().str.contains(term, na=False)
        )

    labels = filters.get("labels")
    if labels:
        def _has_any_label(label_ids_json: str) -> bool:
            try:
                email_labels = json.loads(label_ids_json) if label_ids_json else []
            except (ValueError, TypeError):
                email_labels = []
            return any(l in email_labels for l in labels)

        mask &= df["label_ids"].apply(_has_any_label)

    min_size = filters.get("min_size")
    if min_size is not None:
        mask &= df["size_estimate"] >= min_size

    max_size = filters.get("max_size")
    if max_size is not None:
        mask &= df["size_estimate"] <= max_size

    if filters.get("unread_only"):
        mask &= df["is_read"] == False  # noqa: E712

    return df[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Streamlit widget helpers (not unit tested — require Streamlit context)
# ---------------------------------------------------------------------------

def date_range_filter():
    """Render date range pickers and return (start_ts, end_ts) as Unix timestamps or (None, None)."""
    import streamlit as st
    from datetime import datetime, timezone

    col1, col2 = st.columns(2)
    start_date = col1.date_input("From", value=None, key="filter_start_date")
    end_date = col2.date_input("To", value=None, key="filter_end_date")

    start_ts = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc).timestamp()) if start_date else None
    end_ts = int(datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc).timestamp()) if end_date else None
    return start_ts, end_ts


def sender_filter() -> str:
    """Render a sender search box and return the search string."""
    import streamlit as st
    return st.text_input("Sender", placeholder="Search by name or email", key="filter_sender")


def label_filter(available_labels: list[str]) -> list[str]:
    """Render a multiselect for Gmail labels and return selected labels."""
    import streamlit as st
    return st.multiselect("Labels", options=available_labels, key="filter_labels")


def size_filter() -> tuple[int | None, int | None]:
    """Render min/max size sliders (in KB) and return (min_bytes, max_bytes)."""
    import streamlit as st

    col1, col2 = st.columns(2)
    min_kb = col1.number_input("Min size (KB)", min_value=0, value=0, step=10, key="filter_min_size")
    max_kb = col2.number_input("Max size (KB)", min_value=0, value=0, step=10, key="filter_max_size")

    min_size = min_kb * 1024 if min_kb > 0 else None
    max_size = max_kb * 1024 if max_kb > 0 else None
    return min_size, max_size
