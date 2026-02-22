"""
Gmail mailbox sync — full and incremental.

Full sync:
  - Pages through the entire mailbox via messages.list
  - Saves a page checkpoint to sync_state before each page advance (resumable)
  - Stores the historyId returned by the API for future incremental syncs

Incremental sync:
  - Calls history.list with the stored historyId
  - Upserts newly added messages, deletes removed messages
  - Updates the stored historyId
"""
import time

from cache.database import (
    batch_upsert_emails,
    delete_emails,
    get_sync_state,
    set_sync_state,
)
from gmail.fetcher import fetch_metadata_batch, list_message_ids


def full_sync(account_email: str, service, progress_callback=None) -> int:
    """
    Fetch all message metadata and write to the SQLite cache.

    Resumable: a page checkpoint is persisted to sync_state before advancing
    to the next page. An interrupted sync resumes from the checkpoint on the
    next call rather than restarting from zero.

    Args:
        account_email:     Account to sync.
        service:           Authenticated Gmail API service.
        progress_callback: Optional callable(total_so_far) called after each page.

    Returns:
        Total number of messages synced.
    """
    # Capture historyId before we start paging — it represents the mailbox
    # state at the beginning of the sync, which is what we want to store.
    profile = service.users().getProfile(userId="me").execute()
    history_id = profile["historyId"]

    # Resume from a previous interrupted sync if a checkpoint exists
    page_token = get_sync_state(account_email, "full_sync_page_token")

    total = 0

    while True:
        result = list_message_ids(service, page_token=page_token)
        ids = result["ids"]
        next_page_token = result["next_page_token"]

        if ids:
            emails = fetch_metadata_batch(service, ids)
            batch_upsert_emails(account_email, emails)
            total += len(emails)

        if progress_callback:
            progress_callback(total)

        if not next_page_token:
            break

        # Save checkpoint before advancing — if we crash here, we resume
        # from next_page_token rather than from page 1.
        set_sync_state(account_email, "full_sync_page_token", next_page_token)
        page_token = next_page_token

    # Sync complete — persist final state
    set_sync_state(account_email, "last_history_id", str(history_id))
    set_sync_state(account_email, "last_full_sync_ts", str(int(time.time())))
    set_sync_state(account_email, "full_sync_page_token", None)  # clear checkpoint

    return total


def incremental_sync(account_email: str, service) -> int:
    """
    Sync only changes since the last known historyId via history.list.

    Requires a prior full_sync to have stored a historyId. Raises RuntimeError
    if no historyId is found (caller should fall back to full_sync).

    Returns:
        Count of changes processed (messages added + messages deleted).
    """
    history_id = get_sync_state(account_email, "last_history_id")
    if not history_id:
        raise RuntimeError(
            "No history ID stored. Run a full sync before incremental sync."
        )

    response = service.users().history().list(
        userId="me",
        startHistoryId=history_id,
        historyTypes=["messageAdded", "messageDeleted"],
    ).execute()

    history_records = response.get("history", [])

    added_ids: list[str] = []
    deleted_ids: list[str] = []

    for record in history_records:
        for added in record.get("messagesAdded", []):
            added_ids.append(added["message"]["id"])
        for deleted in record.get("messagesDeleted", []):
            deleted_ids.append(deleted["message"]["id"])

    if added_ids:
        new_emails = fetch_metadata_batch(service, added_ids)
        batch_upsert_emails(account_email, new_emails)

    if deleted_ids:
        delete_emails(account_email, deleted_ids)

    set_sync_state(
        account_email,
        "last_history_id",
        str(response.get("historyId", history_id)),
    )

    return len(added_ids) + len(deleted_ids)
