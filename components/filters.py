"""
Filter logic for the cleanup workflow.

apply_filters() is a pure pandas function — no UI dependencies.
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
