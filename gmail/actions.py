"""
Gmail write operations.

Provides:
  - trash_messages       : move messages to Trash via batchModify, update cache + log
  - unsubscribe_via_post : RFC 8058 one-click POST unsubscribe
  - unsubscribe_via_url  : return the unsubscribe URL for the UI to open
"""
import json
import time

import requests
from googleapiclient.errors import HttpError

from cache.database import delete_emails, log_action, _connect

# Gmail batchModify accepts up to 1000 IDs per call
_BATCH_MODIFY_LIMIT = 1000


def trash_messages(account_email: str, service, message_ids: list[str]) -> dict:
    """
    Move messages to Trash via Gmail batchModify.

    Steps:
      1. Query sizes from cache (for the action log).
      2. Call batchModify in chunks of 1000 — raises on any API error.
      3. On full success: delete rows from SQLite, write action_log entry.

    Returns:
        {"trashed": int, "size_reclaimed": int}
    """
    if not message_ids:
        return {"trashed": 0, "size_reclaimed": 0}

    # Query sizes before any API call so the log is accurate
    total_size = _sum_sizes(account_email, message_ids)

    # Call API — raises HttpError on failure; cache is untouched until success
    for i in range(0, len(message_ids), _BATCH_MODIFY_LIMIT):
        chunk = message_ids[i : i + _BATCH_MODIFY_LIMIT]
        service.users().messages().batchModify(
            userId="me",
            body={"ids": chunk, "addLabelIds": ["TRASH"]},
        ).execute()

    # All API calls succeeded — update cache and log
    delete_emails(account_email, message_ids)
    log_action(
        account_email,
        {
            "action": "trash",
            "message_ids": json.dumps(message_ids),
            "count": len(message_ids),
            "size_reclaimed": total_size,
            "timestamp": int(time.time()),
            "details": json.dumps({}),
        },
    )

    return {"trashed": len(message_ids), "size_reclaimed": total_size}


def unsubscribe_via_post(unsubscribe_url: str, unsubscribe_post: str) -> bool:
    """
    Send an RFC 8058 one-click unsubscribe POST request.

    Returns True on a 2xx response, False on any non-2xx or network error.
    """
    try:
        response = requests.post(
            unsubscribe_url,
            data=unsubscribe_post,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        return 200 <= response.status_code < 300
    except (requests.ConnectionError, requests.Timeout):
        return False


def unsubscribe_via_url(unsubscribe_url: str | None) -> str | None:
    """
    Return the unsubscribe URL for the UI to open in the browser.
    Returns None when the URL is absent or empty.
    """
    return unsubscribe_url if unsubscribe_url else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sum_sizes(account_email: str, message_ids: list[str]) -> int:
    """Return the total size_estimate for the given message IDs from the cache."""
    placeholders = ",".join("?" * len(message_ids))
    conn = _connect(account_email)
    row = conn.execute(
        f"SELECT COALESCE(SUM(size_estimate), 0) AS total FROM emails"
        f" WHERE message_id IN ({placeholders})",
        message_ids,
    ).fetchone()
    conn.close()
    return row["total"] if row else 0
