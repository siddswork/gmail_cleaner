"""
Pydantic request/response models for the FastAPI backend.
"""
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class ConnectResponse(BaseModel):
    auth_url: str
    state: str


class AccountInfo(BaseModel):
    email: str
    has_token: bool


class AccountsResponse(BaseModel):
    accounts: list[AccountInfo]


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

class SyncStatusResponse(BaseModel):
    total_synced: int
    is_complete: bool
    page_token: str | None
    last_full_sync_ts: int | None
    needs_full_sync: bool
    is_syncing: bool
    messages_total: int | None
    sync_started_ts: int | None


class SyncStartResponse(BaseModel):
    message: str
    already_running: bool


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class OverallStatsResponse(BaseModel):
    total_count: int
    total_size: int
    read_count: int
    unread_count: int
    starred_count: int
    important_count: int
    oldest_ts: int | None
    newest_ts: int | None
    db_size_bytes: int


class SenderInfo(BaseModel):
    sender_email: str
    sender_name: str | None
    count: int
    total_size: int


class CategoryInfo(BaseModel):
    category: str
    count: int
    total_size: int


class TimelineBucket(BaseModel):
    period: str
    count: int
    total_size: int


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

class CleanupPreviewRequest(BaseModel):
    sender_email: str
    start_ts: int | None = None
    end_ts: int | None = None
    labels: list[str] | None = None
    unread_only: bool = False
    min_size: int = 0


class CleanupPreviewResponse(BaseModel):
    count: int
    total_size: int
    message_ids: list[str]


class CleanupExecuteRequest(BaseModel):
    message_ids: list[str]
    confirm_word: str | None = None


class CleanupExecuteResponse(BaseModel):
    trashed: int
    size_reclaimed: int
    blocked: int
    errors: int


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------

class DeadSubscription(BaseModel):
    sender_email: str
    sender_name: str | None
    count: int
    total_size: int
    latest_ts: int
    unsubscribe_url: str


class UnsubscribePostRequest(BaseModel):
    unsubscribe_url: str
    unsubscribe_post: str | None = None


class UnsubscribePostResponse(BaseModel):
    success: bool


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

class ReadRateSender(BaseModel):
    sender_email: str
    sender_name: str | None
    total_count: int
    read_count: int
    read_rate: float


class UnreadByLabelInfo(BaseModel):
    category: str
    unread_count: int
    total_size: int


class OldestUnreadSender(BaseModel):
    sender_email: str
    sender_name: str | None
    unread_count: int
    total_size: int
    latest_unread_ts: int
