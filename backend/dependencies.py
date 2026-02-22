"""
FastAPI dependency injection helpers.
"""
from fastapi import HTTPException, Query

from backend import state


def get_account(account: str = Query(..., description="Account email address")) -> str:
    """Validate that the account has an authenticated service."""
    if account not in state.gmail_services:
        raise HTTPException(
            status_code=400,
            detail=f"Account '{account}' is not connected. Use /api/auth/connect first.",
        )
    return account


def get_service(account: str = Query(..., description="Account email address")):
    """Return the Gmail API service for the given account."""
    if account not in state.gmail_services:
        raise HTTPException(
            status_code=400,
            detail=f"Account '{account}' is not connected.",
        )
    return state.gmail_services[account]
