"""
Gmail API HTTP layer.

Provides:
  - RateLimiter  : token-bucket limiter to stay under Gmail's quota ceiling
  - execute_with_retry : single request with exponential backoff on transient errors
  - batch_execute      : splits a request list into chunks of 50, executes each batch
"""
import json
import time

from googleapiclient.errors import HttpError

RETRYABLE_STATUS_CODES = {429, 500, 503}
RATE_LIMIT_403_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}


def _is_rate_limit_403(exc: HttpError) -> bool:
    """Return True if a 403 HttpError is a rate-limit error (retriable)."""
    try:
        data = json.loads(exc.content)
        reasons = {e.get("reason", "") for e in data.get("error", {}).get("errors", [])}
        return bool(reasons & RATE_LIMIT_403_REASONS)
    except Exception:
        return False


class RateLimiter:
    """
    Tracks quota units consumed per second.
    Sleeps for the remainder of the current 1-second window when the
    target is exceeded, then resets the counter.
    """

    def __init__(self, target_qps: int = 150):
        self._target_qps = target_qps
        self._window_start: float | None = None
        self._units_in_window: int = 0

    def consume(self, units: int) -> None:
        now = time.time()

        # Start or reset the 1-second window
        if self._window_start is None or now - self._window_start >= 1.0:
            self._window_start = now
            self._units_in_window = 0

        # If this batch would exceed the budget, sleep until the window resets
        if self._units_in_window + units > self._target_qps:
            sleep_duration = 1.0 - (now - self._window_start)
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            self._window_start = time.time()
            self._units_in_window = 0

        self._units_in_window += units


def execute_with_retry(request, max_attempts: int = 5, base_delay: float = 1.0):
    """
    Execute a Gmail API request, retrying on 429 / 500 / 503 with
    exponential backoff. Raises immediately on any other HttpError.
    """
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return request.execute()
        except HttpError as exc:
            status = exc.resp.status
            if status not in RETRYABLE_STATUS_CODES:
                if status == 403 and _is_rate_limit_403(exc):
                    pass  # fall through to retry
                else:
                    raise
            last_exc = exc
            time.sleep(base_delay * (2 ** attempt))
    raise last_exc


def batch_execute(service, requests_list: list, callback, batch_size: int = 50) -> None:
    """
    Execute a list of API request objects in batches of `batch_size` (max 50).
    `callback(request_id, response, exception)` is called for each response.
    """
    if not requests_list:
        return

    for i in range(0, len(requests_list), batch_size):
        chunk = requests_list[i : i + batch_size]
        batch = service.new_batch_http_request(callback=callback)
        for req in chunk:
            batch.add(req)
        batch.execute()
