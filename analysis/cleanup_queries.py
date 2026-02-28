"""
Cleanup query functions extracted from the Streamlit Cleanup page.

Pure SQL queries over the SQLite cache — no UI dependencies.
"""
import time

from cache.database import _connect

_DEFAULT_SWEEP_CATEGORIES = ["CATEGORY_PROMOTIONS", "CATEGORY_UPDATES"]


def cleanup_query_messages(
    account_email: str,
    sender_email: str | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
    labels: list[str] | None = None,
    unread_only: bool = False,
    min_size: int = 0,
) -> list[dict]:
    """
    Return message_id + size_estimate for emails matching the given filters.
    Always excludes starred and important emails.
    """
    clauses = [
        "is_starred = 0",
        "is_important = 0",
    ]
    params: list = []

    if sender_email is not None:
        clauses.append("sender_email = ?")
        params.append(sender_email)

    if start_ts:
        clauses.append("date_ts >= ?")
        params.append(start_ts)
    if end_ts:
        clauses.append("date_ts <= ?")
        params.append(end_ts)
    if unread_only:
        clauses.append("is_read = 0")
    if min_size:
        clauses.append("size_estimate >= ?")
        params.append(min_size)
    if labels:
        label_clauses = " OR ".join("JSON_EACH.value = ?" for _ in labels)
        clauses.append(
            f"message_id IN ("
            f"  SELECT emails.message_id FROM emails, JSON_EACH(emails.label_ids)"
            f"  WHERE {label_clauses}"
            f")"
        )
        params.extend(labels)

    sql = (
        "SELECT message_id, size_estimate FROM emails"
        f" WHERE {' AND '.join(clauses)}"
    )
    conn = _connect(account_email)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def smart_sweep_query(
    account_email: str,
    days: int = 90,
    min_count: int = 5,
    categories: list[str] | None = None,
    max_read_rate: float = 0.3,
) -> list[dict]:
    """
    Return high-volume promotional senders the user mostly ignores.

    Filters:
      - Only emails within the last `days` days
      - Only emails in the given `categories` (default: PROMOTIONS + UPDATES)
      - Excludes starred and important emails
      - Senders must have >= `min_count` qualifying emails
      - Sender's read rate must be <= `max_read_rate`

    Returns list of {sender_email, count, total_size, read_rate} ordered by count DESC.
    """
    if categories is None:
        categories = _DEFAULT_SWEEP_CATEGORIES

    cutoff_ts = int(time.time()) - days * 86400

    # Build the category IN clause using JSON_EACH for correct JSON array parsing
    cat_placeholders = ",".join("?" * len(categories))
    category_subquery = (
        f"message_id IN ("
        f"  SELECT e2.message_id FROM emails e2, JSON_EACH(e2.label_ids)"
        f"  WHERE JSON_EACH.value IN ({cat_placeholders})"
        f")"
    )

    sql = f"""
        SELECT
            sender_email,
            COUNT(*)                    AS count,
            COALESCE(SUM(size_estimate), 0) AS total_size,
            AVG(CAST(is_read AS REAL))  AS read_rate
        FROM emails
        WHERE date_ts >= ?
          AND is_starred = 0
          AND is_important = 0
          AND {category_subquery}
        GROUP BY sender_email
        HAVING COUNT(*) >= ? AND AVG(CAST(is_read AS REAL)) <= ?
        ORDER BY count DESC
    """

    params = [cutoff_ts] + list(categories) + [min_count, max_read_rate]

    conn = _connect(account_email)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cleanup_query_messages_by_senders(
    account_email: str,
    sender_emails: list[str],
) -> list[dict]:
    """
    Return message_id + size_estimate for all non-starred, non-important emails
    from any of the given senders. Used by the smart sweep preview.
    """
    if not sender_emails:
        return []

    placeholders = ",".join("?" * len(sender_emails))
    sql = (
        f"SELECT message_id, size_estimate FROM emails"
        f" WHERE sender_email IN ({placeholders})"
        f" AND is_starred = 0 AND is_important = 0"
    )
    conn = _connect(account_email)
    rows = conn.execute(sql, sender_emails).fetchall()
    conn.close()
    return [dict(r) for r in rows]
