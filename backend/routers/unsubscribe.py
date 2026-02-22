"""
Unsubscribe router — dead subscription list and POST unsubscribe.
"""
from fastapi import APIRouter, Depends, Query

from analysis.insights import dead_subscriptions
from backend.dependencies import get_account
from backend.models.schemas import (
    DeadSubscription,
    UnsubscribePostRequest,
    UnsubscribePostResponse,
)
from gmail.actions import unsubscribe_via_post

router = APIRouter(prefix="/api/unsubscribe", tags=["unsubscribe"])


@router.get("/dead", response_model=list[DeadSubscription])
def dead(
    account: str = Depends(get_account),
    days: int = Query(30, ge=1, le=365),
):
    """Return senders with dead subscriptions (all unread, older than days)."""
    return dead_subscriptions(account, days=days)


@router.post("/post", response_model=UnsubscribePostResponse)
def post_unsubscribe(req: UnsubscribePostRequest):
    """Execute an RFC 8058 POST unsubscribe request."""
    success = unsubscribe_via_post(req.unsubscribe_url, req.unsubscribe_post or "")
    return UnsubscribePostResponse(success=success)
