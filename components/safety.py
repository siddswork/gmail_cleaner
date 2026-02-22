"""
Safety checks for the cleanup workflow.

Provides:
  - live_label_check : re-fetch labels from Gmail to partition IDs into safe/blocked/errors
  - is_large_batch   : predicate — True when count exceeds the large-batch threshold
"""
from config.settings import LARGE_BATCH_THRESHOLD

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
