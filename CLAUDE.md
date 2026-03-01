# Gmail Cleaner — Project Instructions

## Project Overview
A personal web-based tool to clean up a 20-year-old Gmail account (and up to 2-3 family accounts) that is nearing storage capacity. The goal is to visualize storage usage, bulk-delete unwanted emails, and unsubscribe from mailing lists — with the user always in control. Nothing is deleted without explicit approval.

## Tech Stack
- **Frontend/UI**: Next.js 16 (TypeScript, Tailwind CSS, Recharts)
- **Backend**: FastAPI + uvicorn
- **Language**: Python (backend), TypeScript (frontend)
- **Gmail access**: `google-api-python-client` with OAuth2 (`gmail.modify` scope only)
- **Local cache**: SQLite (one DB per account)
- **Data analysis**: pandas

## Architecture
```
Next.js (port 3000) --> FastAPI (port 8000) --> Python Service Layer --> Gmail API
                                                         |
                                                   SQLite Cache (per account)
```

## Project Structure
```
gmail_cleaner/
├── requirements.txt
├── .gitignore
├── CLAUDE.md
│
├── config/
│   └── settings.py             # Constants, API config, rate limits, paths
│
├── auth/
│   ├── oauth.py                # OAuth2 flow, token management, multi-account
│   └── credentials/            # .gitignored
│       └── client_secret.json  # Shared GCP OAuth client (one for all accounts)
│
├── gmail/
│   ├── client.py               # Rate limiter, retry (execute_with_retry), batch helper
│   ├── fetcher.py              # Message listing, metadata batch fetch (pagination)
│   └── actions.py              # Trash, unsubscribe operations
│
├── cache/
│   ├── database.py             # SQLite schema, CRUD, per-account DB path
│   ├── sync.py                 # Full sync + incremental sync (via history.list)
│   └── sync_manager.py         # Background sync thread, stop_events, progress via sync_state
│
├── analysis/
│   ├── aggregator.py           # Top senders, category breakdown, timeline
│   ├── insights.py             # Read behavior, frequency, dead subscriptions, oldest_unread_senders
│   └── cleanup_queries.py      # cleanup_query_messages(), smart_sweep_query()
│
├── components/
│   ├── safety.py               # live_label_check(), is_large_batch() — no UI deps
│   └── filters.py              # apply_filters() — pure pandas, no UI deps
│
├── backend/                    # FastAPI app
│   ├── main.py                 # App factory, CORS, lifespan (auto-loads tokens on startup)
│   ├── state.py                # In-memory: gmail_services, sync_threads, cleanup_threads, pending_flows
│   ├── dependencies.py         # get_account(), get_service() dependency injection
│   ├── models/schemas.py       # Pydantic request/response models
│   └── routers/
│       ├── auth.py             # GET /accounts, POST /connect, GET /callback, DELETE /accounts/{email}, POST /logout
│       ├── sync.py             # GET /status, POST /start, GET /progress (SSE)
│       ├── dashboard.py        # GET /stats, /top-senders, /categories, /timeline
│       ├── cleanup.py          # POST /preview, POST /execute (background), GET /progress (SSE), POST /stop
│       ├── unsubscribe.py      # GET /dead, POST /post
│       └── insights.py         # GET /read-rate, /unread-by-label, /oldest-unread
│
├── frontend/                   # Next.js app
│   ├── src/app/                # App Router pages (layout, home/dashboard, cleanup, unsubscribe, insights)
│   ├── src/components/         # UI components (Sidebar, SyncBanner, CleanupProgressBar, charts, etc.)
│   ├── src/hooks/              # useSyncStatus (SSE), useCleanup (SSE state machine)
│   └── src/lib/                # api.ts, types.ts, format.ts, AccountContext.tsx
│
├── tests/                      # 311 tests — all service layer + all FastAPI routers
│
└── data/                       # .gitignored — per-account isolated storage
    └── <email>/
        ├── token.json
        └── cache.db
```

## Multi-Account Support
- One GCP project / OAuth client (`client_secret.json`) shared across all accounts
- Each account gets its own isolated `data/<email>/` directory
- Single active account model — logout clears the session without auto-selecting next account
- `backend/state.py` `gmail_services` dict tracks active services
- All service modules accept an `account_email` parameter

## Project Evolution — Key Pivots

This section captures the major decisions and "aha moments" that shaped the project. Future Claude instances should understand *why* things are the way they are.

### 1. Streamlit → FastAPI + Next.js
**Started with**: Streamlit for both UI and backend (5 pages: `app.py`, `pages/1_Dashboard.py`, etc.)
**Problem**: Streamlit is great for prototyping but has no real async support, SSE is impossible, and long-running operations (sync, bulk trash) block the entire UI thread.
**Pivot**: Migrated to FastAPI (Python backend, port 8000) + Next.js (TypeScript frontend, port 3000). The split gave us real background threads, SSE streams, and a proper separation of concerns. All Streamlit files deleted; service layer kept intact (aggregator, insights, actions, etc.).

### 2. Sync: Naive → Background Thread + SSE + Resumable
**Started with**: A synchronous sync call that blocked the UI for 90–120 minutes.
**Aha**: Full sync of 190k emails takes ~106 minutes at 150 units/sec. This cannot be synchronous.
**Pivot**: `cache/sync_manager.py` launches a daemon thread, writes progress to `sync_state` KV table, and exposes an SSE endpoint (`GET /api/sync/progress`). Frontend connects via SSE and shows a live progress bar with ETA. Added `threading.Event` for graceful stop. Sync is resumable via `full_sync_page_token` checkpoint — an interrupted sync continues from where it left off.

### 3. Retry: Bare .execute() → execute_with_retry with Smart Backoff
**Problem**: 403 `rateLimitExceeded` (per-minute quota) crashed the sync thread with no recovery.
**Aha**: Google's per-minute quota resets every 60 seconds, so a standard exponential backoff (2s, 4s, 8s...) is wrong — you need to wait at least 60s before the first retry.
**Pivot**: `gmail/client.py` `execute_with_retry()` now detects 403 `rateLimitExceeded` vs. 403 `forbidden`, waits a minimum of 60s for quota errors, and uses `max_attempts=8`. Applied to both `list_message_ids` (fetcher) and trash operations (actions).

### 4. Cleanup: Synchronous HTTP → Background Thread + SSE (in progress)
**Problem**: Current `POST /api/cleanup/execute` blocks the HTTP connection for the entire duration. For 1000s of emails this will time out. No retry, no progress visibility, no stop button.
**Aha**: The same pattern that fixed sync applies here — background daemon thread + SSE progress stream + stop event. One job per account at a time.
**Pivot**: Rewriting cleanup to use `cache/cleanup_manager.py` (mirrors `sync_manager.py`), making `/execute` return immediately (202), adding SSE progress, and adding a Stop button.

### 5. UX: MultiAccount Switcher → Single-Account Login Model
**Problem**: AccountSwitcher on every page was confusing and added complexity. Users don't switch accounts mid-session.
**Pivot**: Single active account stored in `AccountContext`. Home page shows login form when logged out, dashboard when logged in. Logout button inline in sidebar nav. The `__new__` OAuth artifact filtered from accounts list.

### 6. Workflow: Ad-Hoc → TDD + /handoff + /cont... slash commands
**Aha**: Long coding sessions lose context between conversations. Claude starts fresh and repeats work.
**Pivot**: Created `/handoff` slash command (writes structured `## Last Session` to `CLAUDE.md`) and `/cont...` (reads it to resume). Established strict TDD: failing tests first, implementation second, never simultaneously. Model switching: Opus for planning/architecture, Sonnet for coding — encoded in `CLAUDE.md` instructions.

---

## Capacity Analysis (Primary Account)

Mailbox counts as of 2026-02-21 (categories overlap — emails can carry multiple labels):

| Label | Count |
|---|---|
| Inbox | 58,066 |
| Promotions | 55,341 |
| Updates | 67,096 |
| Social | 6,828 |
| Purchases | 3,359 |
| Forums | 189 |
| Spam | 104 |

**Estimated unique messages (all folders including Sent/Archived): ~150,000–200,000**
The category counts above overlap significantly — an email often carries both `INBOX` and `CATEGORY_PROMOTIONS`.
Upper bound of 190,000 used for all estimates below.

### Local Storage
- Metadata only (no bodies or attachments) — ~520 bytes per row
- 190,000 × 520 bytes + SQLite overhead ≈ **~140 MB** on disk per account

### API Cost — Full Sync (first run only)
| Step | Calls | Quota units |
|---|---|---|
| `messages.list` (500/page) | 380 calls | 1,900 units |
| `messages.get` in batches of 50 | 3,800 batches | 950,000 units |
| **Total** | | **~952,000 units** |

At 150 units/sec target: **~106 minutes** for a full sync of 190,000 emails.

- Daily quota limit: 1 billion units/day — full sync uses < 0.1%, not a concern.
- After first sync, incremental sync via `history.list` takes **seconds**.

### Key Sync Implications
- **Full sync must be resumable** — store a page checkpoint in `sync_state` so an interrupted sync picks up where it left off rather than restarting from zero.
- Show a progress bar during full sync; allow the user to browse partial data while it runs.
- Sync time: ~90–120 minutes for this account size.

## Gmail API Rules
- **Scopes**: `gmail.modify` only — this makes permanent deletion impossible at the API level
- **Batch size**: 50 messages per batch request (never exceed 100)
- **Rate limiting**: target 150 quota units/sec (hard limit is 250)
- **Retry**: use `execute_with_retry` from `gmail/client.py` — 60s minimum wait on 403 rateLimitExceeded, exponential backoff on 429/500/503
- **Pagination**: always use `nextPageToken` for `messages.list`; max 500 results per page
- **Sync strategy**: full sync on first run (stores `historyId`), incremental via `history.list` on subsequent runs

## Safety Rules — NEVER VIOLATE
1. **Never permanently delete** — always use `messages.trash`, never `messages.delete`
2. **Never touch starred emails** — filter by `is_starred = 0` in all queries
3. **Never touch important emails** — filter by `is_important = 0` in all queries
4. **Pre-action live check** — before trashing, re-fetch current labels from Gmail API (cache may be stale)
5. **Sync before action** — run incremental sync before any cleanup operation
6. **Confirmation required** — always show preview (count + size) before executing
7. **Large batch protection** — require typing "DELETE" for batches > 500 emails

## SQLite Schema (per account DB)
```sql
CREATE TABLE emails (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT,
    sender_email TEXT,
    sender_name TEXT,
    subject TEXT,
    date_ts INTEGER,              -- Unix timestamp
    size_estimate INTEGER,        -- bytes
    label_ids TEXT,               -- JSON array e.g. '["INBOX","CATEGORY_PROMOTIONS"]'
    is_read BOOLEAN,
    is_starred BOOLEAN,           -- denormalized from label_ids for fast safety filtering
    is_important BOOLEAN,         -- denormalized from label_ids for fast safety filtering
    has_attachments BOOLEAN,
    unsubscribe_url TEXT,         -- List-Unsubscribe header
    unsubscribe_post TEXT,        -- List-Unsubscribe-Post header
    snippet TEXT,
    fetched_at INTEGER
);

CREATE TABLE action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,                  -- 'trash', 'unsubscribe'
    message_ids TEXT,             -- JSON array
    count INTEGER,
    size_reclaimed INTEGER,
    timestamp INTEGER,
    details TEXT                  -- JSON with sender, query, etc.
);

CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT);
-- Keys: last_history_id, last_full_sync_ts, total_messages_synced,
--       full_sync_page_token, messages_total, sync_started_ts
```

## Model Usage Preference

### Before Planning Mode
When I ask you to plan, create a plan, analyze an approach, or break down a task:
- Before doing anything, say exactly:
  "🧠 PLANNING MODE: This is a good time to switch to Opus for deeper reasoning.
   Type 'yes' to continue with current model, or switch to Opus first."
- Wait for my response before proceeding with the plan.

### After Planning is Complete
When you finish producing a plan and I confirm it:
- Say exactly:
  "✅ PLAN COMPLETE: Consider switching to Sonnet now for faster,
   cost-efficient implementation. Switch models and then tell me to proceed."
- Do not start implementation until I explicitly say "proceed" or "start".

## Development Workflow — TDD is Non-Negotiable

You MUST follow strict TDD for all feature development:

1. Before writing any implementation code, write a failing test first
2. Show me the failing test and wait for my confirmation before proceeding
3. Write the minimal implementation to make the test pass
4. Refactor only after tests are green
5. Never write implementation and tests simultaneously

If I ask you to implement something directly without mentioning tests,
remind me of TDD and ask: "Should I start with the failing test first?"

Red → Green → Refactor. Always.

## Running the App

```bash
./start.sh   # starts backend (port 8000) + frontend (port 3000)
./stop.sh    # stops both
```

Or manually:
```bash
# Terminal 1 (project root)
uvicorn backend.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

Open `http://localhost:3000` in browser.

## Key Gotchas
- `sender_email` must be parsed from the `From` header at insert time (e.g., extract `email@example.com` from `"Name <email@example.com>"`)
- `is_starred` and `is_important` are denormalized from `label_ids` at insert time for fast safety queries
- Initial full sync takes ~90–120 minutes for ~190k emails (primary account) — SSE progress stream via `GET /api/sync/progress`; sync must be resumable via `full_sync_page_token` checkpoint in `sync_state`
- After trashing messages, delete those rows from SQLite immediately (don't wait for next sync)
- The `data/` and `auth/credentials/` directories are gitignored — never commit tokens or credentials
- Backend auto-loads existing tokens on startup (lifespan event in `backend/main.py`)
- OAuth redirect URI must be `http://localhost:8000/api/auth/callback` in GCP console
- 403 `rateLimitExceeded` = per-minute quota hit — wait 60s minimum before retry (NOT the same as 429 which is per-second)
- `date_ts = 0` appears for emails with unparseable dates — always filter with `date_ts > 0` in MIN/MAX/timeline queries

---

## Last Session
**Date**: 2026-03-01

### What Was Accomplished
- Cleanup rework fully complete (was done in a prior session — verified this session):
  - `gmail/actions.py` — retry + progress_callback + stop_event
  - `cache/cleanup_manager.py` — background daemon thread + in-memory progress
  - `backend/routers/cleanup.py` — async execute (202), job-status, SSE progress, stop, smart-sweep endpoints
  - `analysis/cleanup_queries.py` — smart_sweep_query
  - Frontend — useCleanup hook (SSE), CleanupProgressBar, 3-tab cleanup page (Bulk Senders / Smart Sweep / Advanced)
- Force Full Re-sync implemented (TDD):
  - `cache/database.py` — `clear_cache()` wipes emails + sync_state, preserves action_log
  - `backend/routers/sync.py` — `force=true` query param on `POST /api/sync/start`
  - Frontend — `api.sync.forceStart()`, `forceFullSync` in `useSyncStatus`, confirmation dialog in `SyncBanner`
- `tests/test_gmail_actions.py` — 18 new tests for `trash_messages` (empty, clean path, progress_callback, stop_event, exceptions)
- **413 tests passing**

### Current State
All planned work is complete. No pending tasks.
