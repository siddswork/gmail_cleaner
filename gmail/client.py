"""
Gmail API HTTP layer.

Provides:
  - RateLimiter  : token-bucket limiter to stay under Gmail's quota ceiling
  - execute_with_retry : single request with exponential backoff on transient errors
  - batch_execute      : splits a request list into chunks of 50, executes each batch
"""
import json
import logging
import ssl
import time

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 503}
RATE_LIMIT_403_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}

# Network-level errors that are always transient and safe to retry.
# SSLEOFError, ConnectionResetError, BrokenPipeError are all OSError subclasses,
# but we list them explicitly for clarity.
TRANSIENT_NETWORK_ERRORS = (
    ssl.SSLEOFError,
    ConnectionResetError,
    BrokenPipeError,
    TimeoutError,
    OSError,
)

# Retry config for batch.execute() network failures
_BATCH_RETRY_ATTEMPTS = 3
_BATCH_RETRY_DELAY = 5.0


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


# Module-level rate limiter — shared across all throttled API calls.
_rate_limiter = RateLimiter(target_qps=150)


def execute_with_retry(request, max_attempts: int = 8, base_delay: float = 2.0):
    """
    Execute a Gmail API request, retrying on transient errors with
    exponential backoff.

    - 429 / 500 / 503: standard backoff (base_delay * 2^attempt)
    - 403 rateLimitExceeded: minimum 60s wait (per-minute quota window)
    - SSLEOFError / ConnectionResetError / BrokenPipeError / TimeoutError / OSError:
      standard backoff (transient network drops)
    - any other HttpError: raised immediately
    """
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return request.execute()
        except HttpError as exc:
            status = exc.resp.status
            if status in RETRYABLE_STATUS_CODES:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Transient HTTP error (%s) — retrying in %ds (attempt %d/%d)",
                    status, int(delay), attempt + 1, max_attempts,
                )
            elif status == 403 and _is_rate_limit_403(exc):
                # Gmail per-minute quota — must wait for the window to reset
                delay = max(60.0, base_delay * (2 ** attempt))
                logger.warning(
                    "Rate limit hit — waiting %ds (attempt %d/%d)",
                    int(delay), attempt + 1, max_attempts,
                )
            else:
                raise
            last_exc = exc
            time.sleep(delay)
        except TRANSIENT_NETWORK_ERRORS as exc:
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Transient network error (%s: %s) — retrying in %ds (attempt %d/%d)",
                type(exc).__name__, exc, int(delay), attempt + 1, max_attempts,
            )
            last_exc = exc
            time.sleep(delay)
    raise last_exc


def _batch_execute_with_retry(batch) -> None:
    """Execute a batch request, retrying on transient network errors."""
    last_exc = None
    for attempt in range(_BATCH_RETRY_ATTEMPTS):
        try:
            batch.execute()
            return
        except TRANSIENT_NETWORK_ERRORS as exc:
            delay = _BATCH_RETRY_DELAY * (2 ** attempt)
            logger.warning(
                "Batch network error (%s) — retrying in %ds (attempt %d/%d)",
                type(exc).__name__, int(delay), attempt + 1, _BATCH_RETRY_ATTEMPTS,
            )
            last_exc = exc
            time.sleep(delay)
    raise last_exc


def batch_execute(
    service,
    requests_list: list,
    callback,
    batch_size: int = 50,
    rate_limiter: RateLimiter | None = None,
    units_per_request: int = 5,
) -> None:
    """
    Execute a list of API request objects in batches of `batch_size` (max 50).
    `callback(request_id, response, exception)` is called for each response.

    If `rate_limiter` is provided, `units_per_request * len(chunk)` units are
    consumed before each batch chunk to spread quota usage over time and avoid
    per-minute quota exhaustion. Pass `_rate_limiter` for normal production use;
    omit (or pass None) in tests to skip throttling.
    """
    if not requests_list:
        return

    for i in range(0, len(requests_list), batch_size):
        chunk = requests_list[i : i + batch_size]
        if rate_limiter is not None:
            rate_limiter.consume(len(chunk) * units_per_request)
        batch = service.new_batch_http_request(callback=callback)
        for req in chunk:
            batch.add(req)
        _batch_execute_with_retry(batch)
