"""
Project-wide constants and configuration.
All tunable values live here — nothing is hardcoded elsewhere.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CREDENTIALS_DIR = PROJECT_ROOT / "auth" / "credentials"
CLIENT_SECRET_PATH = CREDENTIALS_DIR / "client_secret.json"

# ---------------------------------------------------------------------------
# Gmail API
# ---------------------------------------------------------------------------

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Maximum messages per batch request (Gmail hard limit is 100; we stay well under)
BATCH_SIZE = 50

# Maximum results per messages.list page (Gmail max is 500)
PAGE_SIZE = 500

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

# Target quota units per second (hard limit is 250; we leave headroom)
RATE_LIMIT_QPS = 150

# Retry settings for 429 / 500 / 503 responses
RETRY_MAX_ATTEMPTS = 5
RETRY_BASE_DELAY_SEC = 1.0   # first backoff delay in seconds
RETRY_BACKOFF_FACTOR = 2.0   # multiplier per retry

# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

# Require typing this word to confirm batches larger than the threshold
LARGE_BATCH_CONFIRM_WORD = "DELETE"
LARGE_BATCH_THRESHOLD = 500
