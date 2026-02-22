"""
Safety checks for the cleanup workflow.

Provides:
  - live_label_check   : re-fetch labels from Gmail to partition IDs into safe/blocked/errors
  - is_large_batch     : predicate — True when count exceeds the large-batch threshold
  - confirm_trash_dialog : Streamlit UI — show preview and confirm button (not unit tested)
  - large_batch_guard    : Streamlit UI — require typing "DELETE" for large batches (not unit tested)
"""
import streamlit as st

from config.settings import LARGE_BATCH_CONFIRM_WORD, LARGE_BATCH_THRESHOLD

try:
    from googleapiclient.errors import HttpError
except ImportError:
    HttpError = Exception  # fallback for environments without the library


# ---------------------------------------------------------------------------
# Pure logic (unit tested)
# ---------------------------------------------------------------------------

def live_label_check(service, message_ids: list[str]) -> dict:
    """
    Re-fetch current labels from Gmail for each message ID.

    Returns a dict with three buckets:
        {
            "safe":    [ids where neither STARRED nor IMPORTANT is present],
            "blocked": [ids where STARRED or IMPORTANT is present],
            "errors":  [ids where the API call failed],
        }

    Only requests id and labelIds fields to minimise quota usage.
    """
    if not message_ids:
        return {"safe": [], "blocked": [], "errors": []}

    safe: list[str] = []
    blocked: list[str] = []
    errors: list[str] = []

    for mid in message_ids:
        try:
            response = service.users().messages().get(
                userId="me",
                id=mid,
                format="minimal",
                fields="id,labelIds",
            ).execute()
            label_ids = response.get("labelIds", [])
            if "STARRED" in label_ids or "IMPORTANT" in label_ids:
                blocked.append(mid)
            else:
                safe.append(mid)
        except HttpError:
            errors.append(mid)

    return {"safe": safe, "blocked": blocked, "errors": errors}


def is_large_batch(count: int) -> bool:
    """Return True when count exceeds the large-batch confirmation threshold."""
    return count > LARGE_BATCH_THRESHOLD


# ---------------------------------------------------------------------------
# Streamlit UI (not unit tested)
# ---------------------------------------------------------------------------

def confirm_trash_dialog(count: int, total_size: int) -> bool:
    """
    Display a preview of the pending trash operation and a confirm button.

    Returns True when the user clicks Confirm, False otherwise.
    """
    size_mb = total_size / (1024 * 1024)
    st.warning(
        f"You are about to trash **{count:,}** emails "
        f"({size_mb:.1f} MB). This action can be undone from Gmail Trash "
        f"within 30 days."
    )
    return st.button("Confirm — Move to Trash", type="primary")


def large_batch_guard(count: int) -> bool:
    """
    For batches larger than LARGE_BATCH_THRESHOLD, require the user to type
    the confirmation word before the Confirm button is enabled.

    Returns True when the guard is satisfied (or not triggered).
    """
    if not is_large_batch(count):
        return True

    typed = st.text_input(
        f'Type "{LARGE_BATCH_CONFIRM_WORD}" to confirm deletion of {count:,} emails'
    )
    return typed == LARGE_BATCH_CONFIRM_WORD
