"""
Gmail write operations.

Provides:
  - trash_messages       : move messages to Trash via batchModify, update cache + log
  - unsubscribe_via_post : RFC 8058 one-click POST unsubscribe
  - unsubscribe_via_url  : return the unsubscribe URL for the UI to open
"""
import json
import logging
import threading
import time

import requests
from googleapiclient.errors import HttpError

from cache.database import delete_emails, log_action, _connect
from gmail.client import execute_with_retry

logger = logging.getLogger(__name__)

# Gmail batchModify accepts up to 1000 IDs per call
_BATCH_MODIFY_LIMIT = 1000


def trash_messages(
    account_email: str,
    service,
    message_ids: list[str],
    progress_callback=None,  # callable(processed: int, trashed: int, size_reclaimed: int)
    stop_event: threading.Event | None = None,
) -> dict:
    """
    Move messages to Trash via Gmail batchModify.

    Steps (per chunk):
      1. Check stop_event — exit early if set.
      2. Call batchModify via execute_with_retry (retries on transient errors).
      3. On chunk success: delete rows from SQLite, update counters, call progress_callback.
    At the end (or on early stop): write one action_log entry with actual counts.

    Returns:
        {"trashed": int, "size_reclaimed": int, "stopped_early": bool}
    """
    if not message_ids:
        return {"trashed": 0, "size_reclaimed": 0, "stopped_early": False}

    trashed_ids: list[str] = []
    total_size = 0
    stopped_early = False

    logger.info("Trashing %d messages for %s", len(message_ids), account_email)

    try:
        for i in range(0, len(message_ids), _BATCH_MODIFY_LIMIT):
            # Check stop signal before starting each chunk
            if stop_event is not None and stop_event.is_set():
                stopped_early = True
                break

            chunk = message_ids[i : i + _BATCH_MODIFY_LIMIT]

            # Query sizes before deleting so the log is accurate
            chunk_size = _sum_sizes(account_email, chunk)

            # API call with retry — raises on non-transient errors
            request = service.users().messages().batchModify(
                userId="me",
                body={"ids": chunk, "addLabelIds": ["TRASH"]},
            )
            execute_with_retry(request)

            # Chunk succeeded — update cache and counters immediately
            delete_emails(account_email, chunk)
            trashed_ids.extend(chunk)
            total_size += chunk_size
            logger.info(
                "Trashed chunk of %d messages for %s (total so far: %d)",
                len(chunk), account_email, len(trashed_ids),
            )

            if progress_callback is not None:
                progress_callback(len(trashed_ids), len(trashed_ids), total_size)
    except Exception:
        # Write partial action_log before re-raising so we don't lose
        # the record of what was already trashed.
        if trashed_ids:
            log_action(
                account_email,
                {
                    "action": "trash",
                    "message_ids": json.dumps(trashed_ids),
                    "count": len(trashed_ids),
                    "size_reclaimed": total_size,
                    "timestamp": int(time.time()),
                    "details": json.dumps({}),
                },
            )
        raise

    # Write action log once (even on early stop, if anything was trashed)
    if trashed_ids:
        log_action(
            account_email,
            {
                "action": "trash",
                "message_ids": json.dumps(trashed_ids),
                "count": len(trashed_ids),
                "size_reclaimed": total_size,
                "timestamp": int(time.time()),
                "details": json.dumps({}),
            },
        )

    return {
        "trashed": len(trashed_ids),
        "size_reclaimed": total_size,
        "stopped_early": stopped_early,
    }


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
