"""
Insight queries over the local SQLite cache.

All functions accept `account_email` and query the cache directly.
Excludes starred and important emails from all analysis.
"""
import time

from cache.database import _connect


def dead_subscriptions(account_email: str, days: int = 30) -> list[dict]:
    """
    Return senders with unsubscribe URLs where ALL emails are unread
    and the most recent email is older than `days` ago.
    Ordered by email count descending.
    """
    cutoff_ts = int(time.time()) - days * 86400
    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT
            e.sender_email,
            e.sender_name,
            COUNT(*)            AS count,
            SUM(e.size_estimate)  AS total_size,
            MAX(e.date_ts)        AS latest_ts,
            (
                SELECT unsubscribe_url
                FROM emails
                WHERE sender_email = e.sender_email
                  AND is_starred = 0
                  AND is_important = 0
                  AND unsubscribe_url IS NOT NULL
                ORDER BY date_ts DESC
                LIMIT 1
            ) AS unsubscribe_url
        FROM emails e
        WHERE e.is_starred = 0
          AND e.is_important = 0
          AND e.unsubscribe_url IS NOT NULL
        GROUP BY e.sender_email
        HAVING
            SUM(CASE WHEN e.is_read = 1 THEN 1 ELSE 0 END) = 0
            AND MAX(e.date_ts) < ?
        ORDER BY count DESC
        """,
        (cutoff_ts,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def read_rate_by_sender(account_email: str, limit: int = 50) -> list[dict]:
    """
    Return per-sender read rate (read_count / total_count),
    ordered by total email count descending.
    Excludes starred and important emails.
    """
    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT
            sender_email,
            sender_name,
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) AS read_count,
            CAST(SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) AS REAL)
                / COUNT(*) AS read_rate
        FROM emails
        WHERE is_starred = 0 AND is_important = 0
        GROUP BY sender_email
        ORDER BY total_count DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def unread_by_label(account_email: str) -> list[dict]:
    """
    Return unread count and total size per CATEGORY_* label,
    sorted by category name. Excludes starred and important emails.
    Only counts unread emails.
    """
    import json as _json

    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT label_ids, size_estimate
        FROM emails
        WHERE is_starred = 0
          AND is_important = 0
          AND is_read = 0
        """,
    ).fetchall()
    conn.close()

    counts: dict[str, int] = {}
    sizes: dict[str, int] = {}
    for row in rows:
        labels = _json.loads(row["label_ids"]) if row["label_ids"] else []
        for label in labels:
            if label.startswith("CATEGORY_"):
                counts[label] = counts.get(label, 0) + 1
                sizes[label] = sizes.get(label, 0) + (row["size_estimate"] or 0)

    if not counts:
        return []

    return [
        {"category": cat, "unread_count": counts[cat], "total_size": sizes[cat]}
        for cat in sorted(counts)
    ]


def oldest_unread_senders(account_email: str, limit: int = 20) -> list[dict]:
    """
    Return senders with the oldest most-recent unread email,
    excluding starred and important. Ordered by latest_unread_ts ASC
    (oldest first).
    """
    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT
            sender_email,
            sender_name,
            COUNT(*)           AS unread_count,
            SUM(size_estimate) AS total_size,
            MAX(date_ts)       AS latest_unread_ts
        FROM emails
        WHERE is_read = 0
          AND is_starred = 0
          AND is_important = 0
        GROUP BY sender_email
        ORDER BY latest_unread_ts ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
