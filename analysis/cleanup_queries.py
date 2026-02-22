"""
Cleanup query functions extracted from the Streamlit Cleanup page.

Pure SQL queries over the SQLite cache — no UI dependencies.
"""
from cache.database import _connect


def cleanup_query_messages(
    account_email: str,
    sender_email: str,
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
        "sender_email = ?",
        "is_starred = 0",
        "is_important = 0",
    ]
    params: list = [sender_email]

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
