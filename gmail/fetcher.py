"""
Gmail message fetcher.

Provides:
  - parse_sender         : split a 'From' header into (name, email)
  - list_message_ids     : one page of message IDs from messages.list
  - fetch_metadata_batch : batch-fetch headers + size for a list of IDs
"""
import json
import re
import time
from email.utils import parseaddr, parsedate_to_datetime

from gmail.client import batch_execute, execute_with_retry

# Headers we request from the API (everything else is ignored)
METADATA_HEADERS = [
    "From",
    "Subject",
    "Date",
    "List-Unsubscribe",
    "List-Unsubscribe-Post",
]


def parse_sender(from_header: str) -> tuple[str, str]:
    """
    Parse a 'From' header value into (sender_name, sender_email).

    Handles:
      - "Name <email>"
      - '"Quoted Name" <email>'
      - "email" (no name)
      - "" (empty)
    """
    if not from_header:
        return "", ""
    name, email_addr = parseaddr(from_header)
    name = name.strip().strip('"').strip()
    return name, email_addr.lower()


def list_message_ids(service, query: str = "", page_token: str = None) -> dict:
    """
    Fetch one page of message IDs via messages.list.

    Returns:
        {
            "ids": [str, ...],
            "next_page_token": str | None,
        }
    """
    response = execute_with_retry(
        service.users().messages().list(
            userId="me",
            maxResults=500,
            pageToken=page_token,
            q=query,
        )
    )

    messages = response.get("messages", [])
    return {
        "ids": [m["id"] for m in messages],
        "next_page_token": response.get("nextPageToken"),
    }


def fetch_metadata_batch(service, message_ids: list[str]) -> list[dict]:
    """
    Batch-fetch metadata for a list of message IDs.

    Returns a list of email dicts ready for upsert into the SQLite cache.
    Messages that returned an API error are silently skipped.
    """
    results = []

    def callback(request_id, response, exception):
        if exception is not None:
            return
        results.append(_parse_message(response))

    requests = [
        service.users().messages().get(
            userId="me",
            id=mid,
            format="metadata",
            metadataHeaders=METADATA_HEADERS,
        )
        for mid in message_ids
    ]

    batch_execute(service, requests, callback)
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_message(msg: dict) -> dict:
    """Transform a raw messages.get response into a DB-ready dict."""
    payload = msg.get("payload", {})
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
    label_ids = msg.get("labelIds", [])
    parts = payload.get("parts", [])

    sender_name, sender_email = parse_sender(headers.get("From", ""))

    return {
        "message_id": msg["id"],
        "thread_id": msg.get("threadId"),
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": headers.get("Subject", ""),
        "date_ts": _parse_date(headers.get("Date", "")),
        "size_estimate": msg.get("sizeEstimate", 0),
        "label_ids": json.dumps(label_ids),
        "is_read": "UNREAD" not in label_ids,
        "is_starred": "STARRED" in label_ids,
        "is_important": "IMPORTANT" in label_ids,
        "has_attachments": any(p.get("filename") for p in parts),
        "unsubscribe_url": _extract_unsubscribe_url(headers.get("List-Unsubscribe")),
        "unsubscribe_post": headers.get("List-Unsubscribe-Post"),
        "snippet": msg.get("snippet", ""),
        "fetched_at": int(time.time()),
    }


def _extract_unsubscribe_url(header_value: str | None) -> str | None:
    """
    Extract the https/http URL from a List-Unsubscribe header.

    Header may contain: "<url>, <mailto:...>" — we want only the URL part.
    Returns None when no URL is present.
    """
    if not header_value:
        return None
    match = re.search(r"<(https?://[^>]+)>", header_value)
    return match.group(1) if match else None


def _parse_date(date_str: str) -> int:
    """Parse an RFC 2822 date string to a Unix timestamp. Returns 0 on failure."""
    try:
        return int(parsedate_to_datetime(date_str).timestamp())
    except Exception:
        return 0
