"""
Cleanup router — preview and execute bulk trash operations.
"""
from fastapi import APIRouter, Depends, HTTPException

from analysis.cleanup_queries import cleanup_query_messages
from backend.dependencies import get_account, get_service
from backend.models.schemas import (
    CleanupExecuteRequest,
    CleanupExecuteResponse,
    CleanupPreviewRequest,
    CleanupPreviewResponse,
)
from cache.sync import incremental_sync
from components.safety import is_large_batch, live_label_check
from config.settings import LARGE_BATCH_CONFIRM_WORD
from gmail.actions import trash_messages

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])


@router.post("/preview", response_model=CleanupPreviewResponse)
def preview(
    req: CleanupPreviewRequest,
    account: str = Depends(get_account),
):
    """Return matching message IDs and stats for the given filters."""
    messages = cleanup_query_messages(
        account_email=account,
        sender_email=req.sender_email,
        start_ts=req.start_ts,
        end_ts=req.end_ts,
        labels=req.labels,
        unread_only=req.unread_only,
        min_size=req.min_size,
    )
    total_size = sum(m["size_estimate"] or 0 for m in messages)
    return CleanupPreviewResponse(
        count=len(messages),
        total_size=total_size,
        message_ids=[m["message_id"] for m in messages],
    )


@router.post("/execute", response_model=CleanupExecuteResponse)
def execute(
    req: CleanupExecuteRequest,
    account: str = Depends(get_account),
    service=Depends(get_service),
):
    """Sync → live label check → trash the given message IDs."""
    if not req.message_ids:
        raise HTTPException(status_code=400, detail="No message IDs provided")

    # Large batch guard
    if is_large_batch(len(req.message_ids)):
        if req.confirm_word != LARGE_BATCH_CONFIRM_WORD:
            raise HTTPException(
                status_code=400,
                detail=f"Large batch requires confirm_word='{LARGE_BATCH_CONFIRM_WORD}'",
            )

    # Step 1: incremental sync
    try:
        incremental_sync(account, service)
    except RuntimeError:
        pass  # No history ID yet — proceed with cache as-is

    # Step 2: live label check
    check = live_label_check(service, req.message_ids)
    safe_ids = check["safe"]
    blocked_count = len(check["blocked"])
    error_count = len(check["errors"])

    # Step 3: trash safe messages
    if safe_ids:
        result = trash_messages(account, service, safe_ids)
    else:
        result = {"trashed": 0, "size_reclaimed": 0}

    return CleanupExecuteResponse(
        trashed=result["trashed"],
        size_reclaimed=result["size_reclaimed"],
        blocked=blocked_count,
        errors=error_count,
    )
