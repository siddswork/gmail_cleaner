"""
Background sync management.

Provides helpers to detect sync state and launch a full sync in a
background daemon thread. Progress is written to sync_state so the
frontend can poll it without touching thread internals.
"""
import logging
import threading
import time

from cache.database import get_sync_state, set_sync_state, get_email_count
from cache.sync import full_sync

logger = logging.getLogger(__name__)

# Per-account stop events — set to signal a running sync to stop gracefully.
stop_events: dict[str, threading.Event] = {}


def needs_full_sync(account_email: str) -> bool:
    """Return True if a full sync has never completed for this account."""
    return get_sync_state(account_email, "last_full_sync_ts") is None


def has_interrupted_sync(account_email: str) -> bool:
    """
    Return True if a previous full sync started but never completed.
    An interrupted sync has a page checkpoint but no completion timestamp.
    """
    token = get_sync_state(account_email, "full_sync_page_token")
    # Treat both Python None and the literal string "None" as absent
    return token is not None and token != "None"


def get_sync_progress(account_email: str) -> dict:
    """
    Read current sync progress from sync_state.

    Returns:
        {
            total_synced:      int        — messages synced so far (0 if none)
            is_complete:       bool       — True if last_full_sync_ts is set
            page_token:        str | None — current page checkpoint
            last_full_sync_ts: int | None — Unix timestamp of last completion
            messages_total:    int | None — total messages in mailbox (from getProfile)
            sync_started_ts:   int | None — Unix timestamp when sync started
        }
    """
    raw_ts = get_sync_state(account_email, "last_full_sync_ts")
    raw_token = get_sync_state(account_email, "full_sync_page_token")
    raw_messages_total = get_sync_state(account_email, "messages_total")
    raw_started_ts = get_sync_state(account_email, "sync_started_ts")

    # Always read actual row count from the DB — this is accurate regardless
    # of whether a previous sync run wrote to sync_state or was interrupted.
    try:
        total_synced = get_email_count(account_email)
    except Exception:
        total_synced = 0

    return {
        "total_synced": total_synced,
        "is_complete": raw_ts is not None,
        "page_token": raw_token if raw_token and raw_token != "None" else None,
        "last_full_sync_ts": int(raw_ts) if raw_ts else None,
        "messages_total": int(raw_messages_total) if raw_messages_total else None,
        "sync_started_ts": int(raw_started_ts) if raw_started_ts else None,
    }


def stop_sync(account_email: str, thread: threading.Thread | None = None, timeout: float = 5.0) -> None:
    """
    Signal a running sync to stop gracefully.

    Sets the stop_event for the account so that full_sync() exits at the
    next page boundary. Optionally joins the thread to wait for it to finish.
    """
    event = stop_events.get(account_email)
    if event is not None:
        event.set()
    if thread is not None:
        thread.join(timeout=timeout)


def _sync_worker(account_email: str, service, stop_event: threading.Event) -> None:
    """Thread target: run full_sync and report progress to sync_state."""
    set_sync_state(account_email, "sync_started_ts", str(int(time.time())))
    logger.info("Sync started for %s", account_email)

    def _progress_callback(total: int) -> None:
        set_sync_state(account_email, "total_messages_synced", str(total))

    try:
        full_sync(account_email, service, progress_callback=_progress_callback, stop_event=stop_event)
        logger.info("Sync completed for %s", account_email)
    except Exception:
        logger.exception("Sync worker crashed for %s", account_email)


def start_background_sync(account_email: str, service) -> threading.Thread:
    """
    Start full_sync in a background daemon thread.

    The thread writes incremental progress to sync_state via a callback so
    the frontend can poll it. A stop_event is stored in `stop_events` so
    `stop_sync()` can signal graceful termination.

    Returns the started Thread.
    """
    stop_event = threading.Event()
    stop_events[account_email] = stop_event

    t = threading.Thread(
        target=_sync_worker,
        args=(account_email, service, stop_event),
        daemon=True,
    )
    t.start()
    return t
