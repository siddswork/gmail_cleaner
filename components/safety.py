"""
Safety checks for the cleanup workflow.

Provides:
  - live_label_check : re-fetch labels from Gmail to partition IDs into safe/blocked/errors
  - is_large_batch   : predicate — True when count exceeds the large-batch threshold
"""
from config.settings import LARGE_BATCH_THRESHOLD
from gmail.client import _rate_limiter

try:
    from googleapiclient.errors import HttpError
except ImportError:
    HttpError = Exception  # fallback for environments without the library

_LABEL_CHECK_BATCH_SIZE = 50
_LABEL_CHECK_UNITS_PER_REQUEST = 5  # messages.get = 5 quota units


# ---------------------------------------------------------------------------
# Pure logic (unit tested)
# ---------------------------------------------------------------------------

def live_label_check(service, message_ids: list[str]) -> dict:
    """
    Re-fetch current labels from Gmail for each message ID using batch requests.

    Returns a dict with three buckets:
        {
            "safe":    [ids where neither STARRED nor IMPORTANT is present],
            "blocked": [ids where STARRED or IMPORTANT is present],
            "errors":  [ids where the API call failed],
        }

    Sends up to 50 requests per batch to minimise round-trips. Uses the
    shared rate limiter (5 quota units per messages.get call).
    """
    if not message_ids:
        return {"safe": [], "blocked": [], "errors": []}

    safe: list[str] = []
    blocked: list[str] = []
    errors: list[str] = []

    def callback(request_id, response, exception):
        mid = request_id  # request_id is the message ID (set via batch.add)
        if exception is not None:
            errors.append(mid)
            return
        label_ids = response.get("labelIds", [])
        if "STARRED" in label_ids or "IMPORTANT" in label_ids:
            blocked.append(mid)
        else:
            safe.append(mid)

    for i in range(0, len(message_ids), _LABEL_CHECK_BATCH_SIZE):
        chunk = message_ids[i : i + _LABEL_CHECK_BATCH_SIZE]
        _rate_limiter.consume(len(chunk) * _LABEL_CHECK_UNITS_PER_REQUEST)
        batch = service.new_batch_http_request(callback=callback)
        for mid in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=mid,
                    format="minimal",
                    fields="id,labelIds",
                ),
                request_id=mid,
            )
        batch.execute()

    return {"safe": safe, "blocked": blocked, "errors": errors}


def is_large_batch(count: int) -> bool:
    """Return True when count exceeds the large-batch confirmation threshold."""
    return count > LARGE_BATCH_THRESHOLD
