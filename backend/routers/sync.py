"""
Sync router — background sync management with SSE progress.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from backend import state
from backend.dependencies import get_account, get_service
from backend.models.schemas import SyncStartResponse, SyncStatusResponse
from cache.database import clear_cache, init_db
from cache.sync_manager import (
    get_sync_progress,
    needs_full_sync,
    start_background_sync,
)

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(account: str = Depends(get_account)):
    """Return current sync state for the account."""
    progress = get_sync_progress(account)
    thread = state.sync_threads.get(account)
    is_syncing = thread is not None and thread.is_alive()

    return SyncStatusResponse(
        total_synced=progress["total_synced"],
        is_complete=progress["is_complete"],
        page_token=progress["page_token"],
        last_full_sync_ts=progress["last_full_sync_ts"],
        needs_full_sync=needs_full_sync(account),
        is_syncing=is_syncing,
        messages_total=progress["messages_total"],
        sync_started_ts=progress["sync_started_ts"],
        synced_this_run=progress["synced_this_run"],
    )


@router.post("/start", response_model=SyncStartResponse)
def start_sync(account: str = Depends(get_account), force: bool = False):
    """Start a background sync for the account. Use force=true to wipe the cache first."""
    # Check if already running
    thread = state.sync_threads.get(account)
    if thread is not None and thread.is_alive():
        return SyncStartResponse(message="Sync already running", already_running=True)

    if force:
        clear_cache(account)

    service = state.gmail_services[account]
    init_db(account)
    thread = start_background_sync(account, service)
    state.sync_threads[account] = thread

    return SyncStartResponse(message="Sync started", already_running=False)


@router.get("/progress")
async def sync_progress_sse(account: str = Query(...)):
    """SSE stream of sync progress. Sends updates every 2 seconds."""
    if account not in state.gmail_services:
        async def error_stream():
            yield f"data: {json.dumps({'error': 'Account not connected'})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def event_stream():
        while True:
            progress = get_sync_progress(account)
            thread = state.sync_threads.get(account)
            is_syncing = thread is not None and thread.is_alive()

            data = {
                "total_synced": progress["total_synced"],
                "is_complete": progress["is_complete"],
                "is_syncing": is_syncing,
                "messages_total": progress["messages_total"],
                "sync_started_ts": progress["sync_started_ts"],
                "synced_this_run": progress["synced_this_run"],
            }
            yield f"data: {json.dumps(data)}\n\n"

            if progress["is_complete"] and not is_syncing:
                yield "event: complete\ndata: {}\n\n"
                break

            if not is_syncing and not progress["is_complete"]:
                # Sync stopped without completing (error or not started)
                yield f"event: stopped\ndata: {json.dumps(data)}\n\n"
                break

            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
