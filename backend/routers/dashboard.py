"""
Dashboard router — mailbox stats, top senders, categories, timeline.
"""
from fastapi import APIRouter, Depends, Query

from analysis.aggregator import (
    category_breakdown,
    overall_stats,
    storage_timeline,
    top_senders_by_count,
    top_senders_by_size,
)
from backend.dependencies import get_account
from backend.models.schemas import (
    CategoryInfo,
    OverallStatsResponse,
    SenderInfo,
    TimelineBucket,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=OverallStatsResponse)
def stats(account: str = Depends(get_account)):
    return overall_stats(account)


@router.get("/top-senders", response_model=list[SenderInfo])
def top_senders(
    account: str = Depends(get_account),
    sort: str = Query("count", pattern="^(count|size)$"),
    limit: int = Query(20, ge=1, le=200),
):
    if sort == "size":
        return top_senders_by_size(account, limit=limit)
    return top_senders_by_count(account, limit=limit)


@router.get("/categories", response_model=list[CategoryInfo])
def categories(account: str = Depends(get_account)):
    return category_breakdown(account)


@router.get("/timeline", response_model=list[TimelineBucket])
def timeline(
    account: str = Depends(get_account),
    granularity: str = Query("month", pattern="^(month|year)$"),
):
    return storage_timeline(account, granularity=granularity)
