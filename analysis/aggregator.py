"""
Aggregation queries over the local SQLite cache.

All functions accept `account_email` and query the cache directly.
Cleanup-oriented views (top_senders_*, category_breakdown, storage_timeline)
exclude starred and important emails.
overall_stats reports the full picture including starred/important.
"""
import json
import sqlite3
from datetime import datetime, timezone

from cache.database import _connect


# ---------------------------------------------------------------------------
# Top senders
# ---------------------------------------------------------------------------

def top_senders_by_count(account_email: str, limit: int = 20) -> list[dict]:
    """Return top senders ordered by email count descending, excluding starred/important."""
    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT sender_email, sender_name, COUNT(*) AS count, SUM(size_estimate) AS total_size
        FROM emails
        WHERE is_starred = 0 AND is_important = 0
        GROUP BY sender_email
        ORDER BY count DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def top_senders_by_size(account_email: str, limit: int = 20) -> list[dict]:
    """Return top senders ordered by total size descending, excluding starred/important."""
    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT sender_email, sender_name, COUNT(*) AS count, SUM(size_estimate) AS total_size
        FROM emails
        WHERE is_starred = 0 AND is_important = 0
        GROUP BY sender_email
        ORDER BY total_size DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Category breakdown
# ---------------------------------------------------------------------------

def category_breakdown(account_email: str) -> list[dict]:
    """
    Return count and total size per CATEGORY_* label, excluding starred/important.
    Each email may contribute to multiple categories (one row per CATEGORY_* label it carries).
    """
    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT label_ids, size_estimate
        FROM emails
        WHERE is_starred = 0 AND is_important = 0
        """,
    ).fetchall()
    conn.close()

    counts: dict[str, int] = {}
    sizes: dict[str, int] = {}
    for row in rows:
        labels = json.loads(row["label_ids"]) if row["label_ids"] else []
        for label in labels:
            if label.startswith("CATEGORY_"):
                counts[label] = counts.get(label, 0) + 1
                sizes[label] = sizes.get(label, 0) + (row["size_estimate"] or 0)

    if not counts:
        return []

    return [
        {"category": cat, "count": counts[cat], "total_size": sizes[cat]}
        for cat in sorted(counts)
    ]


# ---------------------------------------------------------------------------
# Storage timeline
# ---------------------------------------------------------------------------

def storage_timeline(account_email: str, granularity: str = "month") -> list[dict]:
    """
    Return count and total size bucketed by time period, ordered chronologically.
    granularity: "month" -> period like "2024-01", "year" -> "2024"
    Excludes starred and important emails.
    """
    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT date_ts, size_estimate
        FROM emails
        WHERE is_starred = 0 AND is_important = 0
        ORDER BY date_ts ASC
        """,
    ).fetchall()
    conn.close()

    buckets: dict[str, dict] = {}
    for row in rows:
        if row["date_ts"] is None:
            continue
        dt = datetime.fromtimestamp(row["date_ts"], tz=timezone.utc)
        if granularity == "year":
            period = dt.strftime("%Y")
        else:
            period = dt.strftime("%Y-%m")

        if period not in buckets:
            buckets[period] = {"period": period, "count": 0, "total_size": 0}
        buckets[period]["count"] += 1
        buckets[period]["total_size"] += row["size_estimate"] or 0

    return [buckets[p] for p in sorted(buckets)]


# ---------------------------------------------------------------------------
# Overall stats
# ---------------------------------------------------------------------------

def overall_stats(account_email: str) -> dict:
    """
    Return aggregate statistics over ALL emails (including starred/important).
    Intended as an informational summary, not a cleanup view.
    """
    conn = _connect(account_email)
    row = conn.execute(
        """
        SELECT
            COUNT(*)                                                      AS total_count,
            COALESCE(SUM(size_estimate), 0)                               AS total_size,
            COALESCE(SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END), 0)    AS read_count,
            COALESCE(SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END), 0)    AS unread_count,
            COALESCE(SUM(CASE WHEN is_starred = 1 THEN 1 ELSE 0 END), 0) AS starred_count,
            COALESCE(SUM(CASE WHEN is_important = 1 THEN 1 ELSE 0 END), 0) AS important_count,
            MIN(date_ts) AS oldest_ts,
            MAX(date_ts) AS newest_ts
        FROM emails
        """,
    ).fetchone()
    conn.close()
    return dict(row)
