"""
Cleanup router — preview and execute bulk trash operations.

Execute is now asynchronous: POST /execute starts a background job and
returns 202 immediately. Poll GET /job-status or listen to GET /progress
(SSE) for live updates.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from analysis.cleanup_queries import (
    cleanup_query_messages,
    cleanup_query_messages_by_senders,
    smart_sweep_query,
)
from backend import state
from backend.dependencies import get_account, get_service
from backend.models.schemas import (
    CleanupExecuteRequest,
    CleanupJobStatus,
    CleanupPreviewRequest,
    CleanupPreviewResponse,
    SmartSweepPreviewRequest,
    SmartSweepPreviewResponse,
    SmartSweepSender,
)
from cache.cleanup_manager import get_cleanup_progress, start_background_cleanup, stop_cleanup
from components.safety import is_large_batch
from config.settings import LARGE_BATCH_CONFIRM_WORD

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


@router.post("/execute", status_code=202, response_model=CleanupJobStatus)
def execute(
    req: CleanupExecuteRequest,
    account: str = Depends(get_account),
    service=Depends(get_service),
):
    """
    Start background cleanup job (sync + live label check + trash).

    Returns 202 immediately. The background worker handles sync,
    live label check, and trashing. Poll GET /job-status or listen
    to GET /progress (SSE) for updates.
    """
    if not req.message_ids:
        raise HTTPException(status_code=400, detail="No message IDs provided")

    # Block cleanup while a sync is running — concurrent DB writes cause crashes
    sync_thread = state.sync_threads.get(account)
    if sync_thread is not None and sync_thread.is_alive():
        raise HTTPException(
            status_code=409,
            detail="Sync is in progress. Wait for sync to complete before running cleanup.",
        )

    # Large batch guard
    if is_large_batch(len(req.message_ids)):
        if req.confirm_word != LARGE_BATCH_CONFIRM_WORD:
            raise HTTPException(
                status_code=400,
                detail=f"Large batch requires confirm_word='{LARGE_BATCH_CONFIRM_WORD}'",
            )

    # Start background cleanup — worker does sync + live_label_check + trash
    try:
        start_background_cleanup(account, service, req.message_ids)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return CleanupJobStatus(
        status="running",
        total=len(req.message_ids),
        processed=0,
        trashed=0,
        size_reclaimed=0,
        errors=0,
    )


@router.get("/job-status", response_model=CleanupJobStatus)
def job_status(account: str = Depends(get_account)):
    """Poll the current cleanup job status for the account."""
    progress = get_cleanup_progress(account)
    return CleanupJobStatus(**progress)


@router.post("/stop")
def stop(account: str = Depends(get_account)):
    """Signal the running cleanup job to stop after the current chunk."""
    stop_cleanup(account)
    return {"message": "Stop signal sent"}


@router.get("/progress")
async def cleanup_progress_sse(account: str = Depends(get_account)):
    """SSE stream of cleanup progress. Sends updates every 2 seconds."""
    async def event_stream():
        while True:
            progress = get_cleanup_progress(account)
            yield f"data: {json.dumps(progress)}\n\n"

            if progress["status"] in ("done", "stopped", "error"):
                yield f"event: {progress['status']}\ndata: {{}}\n\n"
                break

            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/smart-sweep", response_model=list[SmartSweepSender])
def smart_sweep(account: str = Depends(get_account)):
    """Return high-volume, low-read-rate promotional senders for the account."""
    return smart_sweep_query(account)


@router.post("/smart-sweep/preview", response_model=SmartSweepPreviewResponse)
def smart_sweep_preview(
    req: SmartSweepPreviewRequest,
    account: str = Depends(get_account),
):
    """Return message IDs and aggregate size for the selected smart sweep senders."""
    messages = cleanup_query_messages_by_senders(account, req.sender_emails)
    total_size = sum(m["size_estimate"] or 0 for m in messages)
    return SmartSweepPreviewResponse(
        count=len(messages),
        total_size=total_size,
        message_ids=[m["message_id"] for m in messages],
    )
