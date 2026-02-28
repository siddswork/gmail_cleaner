"""
Background cleanup management.

Provides helpers to start a bulk-trash job in a background daemon thread.
Progress is stored in memory (ephemeral — not persisted to SQLite) so the
frontend can poll or receive SSE updates without touching thread internals.

One job per account at a time. A RuntimeError is raised if a job is already
running when start_background_cleanup is called.
"""
import logging
import threading

from cache.sync import incremental_sync

logger = logging.getLogger(__name__)
from components.safety import live_label_check
from gmail.actions import trash_messages

# Per-account stop events — set to signal a running cleanup to stop gracefully.
stop_events: dict[str, threading.Event] = {}

# Per-account live progress — updated by the worker via progress_callback.
cleanup_progress: dict[str, dict] = {}

# Per-account active threads — used to detect if a job is still running.
_active_threads: dict[str, threading.Thread] = {}

_IDLE: dict = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "trashed": 0,
    "size_reclaimed": 0,
    "errors": 0,
}


def get_cleanup_progress(account_email: str) -> dict:
    """
    Return the current cleanup progress for the account.

    Returns:
        {
            status:        "idle" | "running" | "done" | "stopped" | "error"
            total:         int  — total messages in this job
            processed:     int  — messages processed so far
            trashed:       int  — messages successfully trashed
            size_reclaimed:int  — bytes reclaimed
            errors:        int  — count of errors
        }
    """
    return dict(cleanup_progress.get(account_email, _IDLE))


def stop_cleanup(account_email: str) -> None:
    """
    Signal a running cleanup to stop gracefully.

    Sets the stop_event for the account so trash_messages() exits at the next
    chunk boundary. Does nothing if no event is registered.
    """
    event = stop_events.get(account_email)
    if event is not None:
        event.set()


def start_background_cleanup(
    account_email: str,
    service,
    message_ids: list[str],
) -> threading.Thread:
    """
    Start trash_messages in a background daemon thread.

    Raises RuntimeError if a cleanup job is already running for this account.
    Returns the started Thread.
    """
    # Check if already running
    existing = _active_threads.get(account_email)
    if existing is not None and existing.is_alive():
        raise RuntimeError(f"Cleanup already running for {account_email}")

    stop_event = threading.Event()
    stop_events[account_email] = stop_event

    # Initialise progress before starting the thread so callers can read it
    # immediately after start_background_cleanup returns.
    cleanup_progress[account_email] = {
        "status": "running",
        "total": len(message_ids),
        "processed": 0,
        "trashed": 0,
        "size_reclaimed": 0,
        "errors": 0,
    }

    t = threading.Thread(
        target=_cleanup_worker,
        args=(account_email, service, message_ids, stop_event),
        daemon=True,
    )
    _active_threads[account_email] = t
    t.start()
    return t


def _cleanup_worker(
    account_email: str,
    service,
    message_ids: list[str],
    stop_event: threading.Event,
) -> None:
    """Thread target: sync, live-check, then trash safe messages."""

    def _progress_callback(processed: int, trashed: int, size_reclaimed: int = 0) -> None:
        cleanup_progress[account_email].update({
            "processed": processed,
            "trashed": trashed,
            "size_reclaimed": size_reclaimed,
        })

    logger.info("Cleanup started for %s — %d messages", account_email, len(message_ids))

    try:
        # Step 1: incremental sync (quick — seconds for an up-to-date cache)
        try:
            incremental_sync(account_email, service)
        except RuntimeError:
            pass  # No history ID yet — proceed with cache as-is

        # Step 2: live label check — filter out starred/important
        check = live_label_check(service, message_ids)
        safe_ids = check["safe"]

        if not safe_ids:
            cleanup_progress[account_email].update({
                "status": "done",
                "total": 0,
                "processed": 0,
                "trashed": 0,
                "size_reclaimed": 0,
            })
            logger.info("Cleanup for %s — 0 safe messages after live check, nothing to do", account_email)
            return

        # Update total to reflect safe IDs only
        cleanup_progress[account_email]["total"] = len(safe_ids)

        # Step 3: trash safe messages
        result = trash_messages(
            account_email,
            service,
            safe_ids,
            progress_callback=_progress_callback,
            stop_event=stop_event,
        )
        stopped = result.get("stopped_early")
        status = "stopped" if stopped else "done"
        cleanup_progress[account_email].update({
            "status": status,
            "processed": result["trashed"],
            "trashed": result["trashed"],
            "size_reclaimed": result["size_reclaimed"],
        })
        if stopped:
            logger.info(
                "Cleanup stopped early for %s — trashed %d",
                account_email, result["trashed"],
            )
        else:
            logger.info(
                "Cleanup complete for %s — trashed %d, reclaimed %d bytes",
                account_email, result["trashed"], result["size_reclaimed"],
            )
    except Exception:
        logger.exception("Cleanup worker crashed for %s", account_email)
        cleanup_progress[account_email]["status"] = "error"
    finally:
        stop_events.pop(account_email, None)
