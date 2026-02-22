"""
OAuth2 flow and token management for multi-account Gmail access.

Each account has its own token at data/<email>/token.json.
All accounts share a single OAuth client at auth/credentials/client_secret.json.

Environment variables:
  GMAIL_CLEANER_DATA_DIR         — root for per-account token + cache files
  GMAIL_CLEANER_CREDENTIALS_DIR  — directory containing client_secret.json
"""
import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _data_root() -> Path:
    env = os.environ.get("GMAIL_CLEANER_DATA_DIR")
    return Path(env) if env else Path(__file__).parent.parent / "data"


def _credentials_dir() -> Path:
    env = os.environ.get("GMAIL_CLEANER_CREDENTIALS_DIR")
    return Path(env) if env else Path(__file__).parent / "credentials"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def get_client_secret_path() -> str:
    """Return the path to the shared GCP OAuth client secret file."""
    return str(_credentials_dir() / "client_secret.json")


def get_token_path(account_email: str) -> str:
    """Return the path to the per-account OAuth token file."""
    return str(_data_root() / account_email / "token.json")


# ---------------------------------------------------------------------------
# Credential persistence
# ---------------------------------------------------------------------------

def load_credentials(account_email: str) -> Credentials | None:
    """Load stored credentials for this account. Returns None if absent."""
    token_path = Path(get_token_path(account_email))
    if not token_path.exists():
        return None
    data = json.loads(token_path.read_text())
    return Credentials.from_authorized_user_info(data)


def save_credentials(account_email: str, creds: Credentials) -> None:
    """Persist credentials to token.json, creating parent dirs as needed."""
    token_path = Path(get_token_path(account_email))
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------

def get_authenticated_service(account_email: str):
    """
    Return an authenticated Gmail API service for the given account.

    Credential resolution order:
      1. Valid stored credentials  → use as-is
      2. Expired + refresh token   → refresh silently, save, use
      3. No credentials            → run OAuth flow, save, use
    """
    creds = load_credentials(account_email)

    if creds and creds.valid:
        pass
    elif creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(account_email, creds)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            get_client_secret_path(), SCOPES
        )
        creds = flow.run_local_server(port=0, open_browser=False)
        save_credentials(account_email, creds)

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Web-based OAuth flow (for FastAPI backend)
# ---------------------------------------------------------------------------

def create_auth_flow(redirect_uri: str) -> tuple:
    """
    Create an OAuth2 flow for web-based authorization.

    Returns (flow, auth_url) where:
      - flow: the Flow object (store it keyed by state for the callback)
      - auth_url: the URL the user should visit to authorize
    """
    flow = Flow.from_client_secrets_file(
        get_client_secret_path(),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return flow, auth_url


def exchange_code(flow, code: str) -> tuple:
    """
    Exchange an authorization code for credentials.

    Steps:
      1. Fetch token using the code
      2. Get the user's email via getProfile
      3. Save credentials to data/<email>/token.json

    Returns (email, credentials).
    """
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Get the user's email address
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]

    # Persist credentials
    save_credentials(email, creds)

    return email, creds
