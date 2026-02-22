"""
Insights router — read behavior and engagement analysis.
"""
from fastapi import APIRouter, Depends, Query

from analysis.insights import (
    oldest_unread_senders,
    read_rate_by_sender,
    unread_by_label,
)
from backend.dependencies import get_account
from backend.models.schemas import (
    OldestUnreadSender,
    ReadRateSender,
    UnreadByLabelInfo,
)

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/read-rate", response_model=list[ReadRateSender])
def read_rate(
    account: str = Depends(get_account),
    limit: int = Query(50, ge=10, le=200),
):
    return read_rate_by_sender(account, limit=limit)


@router.get("/unread-by-label", response_model=list[UnreadByLabelInfo])
def unread_by_label_endpoint(account: str = Depends(get_account)):
    return unread_by_label(account)


@router.get("/oldest-unread", response_model=list[OldestUnreadSender])
def oldest_unread(
    account: str = Depends(get_account),
    limit: int = Query(20, ge=5, le=100),
):
    return oldest_unread_senders(account, limit=limit)
