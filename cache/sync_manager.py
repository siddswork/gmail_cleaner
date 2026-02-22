"""
Background sync management.

Provides helpers to detect sync state and launch a full sync in a
background daemon thread. Progress is written to sync_state so the
Streamlit UI can poll it without touching thread internals.
"""
import threading

from cache.database import get_sync_state, set_sync_state
from cache.sync import full_sync


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
            total_synced:      int   — messages synced so far (0 if none)
            is_complete:       bool  — True if last_full_sync_ts is set
            page_token:        str | None — current page checkpoint
            last_full_sync_ts: int | None — Unix timestamp of last completion
        }
    """
    raw_total = get_sync_state(account_email, "total_messages_synced")
    raw_ts = get_sync_state(account_email, "last_full_sync_ts")
    raw_token = get_sync_state(account_email, "full_sync_page_token")

    return {
        "total_synced": int(raw_total) if raw_total else 0,
        "is_complete": raw_ts is not None,
        "page_token": raw_token if raw_token and raw_token != "None" else None,
        "last_full_sync_ts": int(raw_ts) if raw_ts else None,
    }


def _sync_worker(account_email: str, service) -> None:
    """Thread target: run full_sync and report progress to sync_state."""
    def _progress_callback(total: int) -> None:
        set_sync_state(account_email, "total_messages_synced", str(total))

    full_sync(account_email, service, progress_callback=_progress_callback)


def start_background_sync(account_email: str, service) -> threading.Thread:
    """
    Start full_sync in a background daemon thread.

    The thread writes incremental progress to sync_state via a callback so
    the Streamlit UI can poll it with st.rerun(). Because it is a daemon
    thread it will not block process exit if the user closes the browser.

    Returns the started Thread (store in st.session_state to check liveness).
    """
    t = threading.Thread(
        target=_sync_worker,
        args=(account_email, service),
        daemon=True,
    )
    t.start()
    return t
