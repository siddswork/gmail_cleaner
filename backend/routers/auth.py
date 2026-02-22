"""
Auth router — OAuth2 flow management.
"""
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from auth.oauth import (
    create_auth_flow,
    exchange_code,
    get_authenticated_service,
    load_credentials,
)
from backend import state
from backend.models.schemas import AccountInfo, AccountsResponse, ConnectResponse
from cache.database import init_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _data_root():
    from auth.oauth import _data_root
    return _data_root()


@router.get("/accounts", response_model=AccountsResponse)
def list_accounts():
    """List all accounts that have a saved token."""
    root = _data_root()
    accounts = []
    if root.exists():
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / "token.json").exists():
                email = d.name
                accounts.append(AccountInfo(email=email, has_token=True))
                # Auto-load service if not already in memory
                if email not in state.gmail_services:
                    try:
                        svc = get_authenticated_service(email)
                        state.gmail_services[email] = svc
                    except Exception:
                        pass
    return AccountsResponse(accounts=accounts)


@router.post("/connect", response_model=ConnectResponse)
def connect_account():
    """Start OAuth flow. Returns the auth URL for the user to visit."""
    redirect_uri = "http://localhost:8000/api/auth/callback"
    flow, auth_url = create_auth_flow(redirect_uri)

    # Extract the state parameter from the auth URL
    parsed = urlparse(auth_url)
    qs = parse_qs(parsed.query)
    flow_state = qs.get("state", [""])[0]

    if not flow_state:
        raise HTTPException(status_code=500, detail="Failed to generate OAuth state")

    state.pending_flows[flow_state] = flow
    return ConnectResponse(auth_url=auth_url, state=flow_state)


@router.get("/callback")
def oauth_callback(code: str, state: str):
    """Handle OAuth redirect from Google."""
    from backend import state as app_state

    flow = app_state.pending_flows.pop(state, None)
    if flow is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    try:
        email, creds = exchange_code(flow, code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {e}")

    # Initialize DB and service
    init_db(email)
    svc = get_authenticated_service(email)
    app_state.gmail_services[email] = svc

    # Redirect to frontend
    return RedirectResponse(url=f"http://localhost:3000/?auth=success&email={email}")


@router.delete("/accounts/{email}")
def remove_account(email: str):
    """Remove account from in-memory state (does not delete files)."""
    state.gmail_services.pop(email, None)
    state.sync_threads.pop(email, None)
    return {"message": f"Account '{email}' removed from session"}
