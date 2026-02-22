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
│   ├── client.py               # Rate limiter, retry, batch helper
│   ├── fetcher.py              # Message listing, metadata batch fetch (pagination)
│   └── actions.py              # Trash, unsubscribe operations
│
├── cache/
│   ├── database.py             # SQLite schema, CRUD, per-account DB path
│   └── sync.py                 # Full sync + incremental sync (via history.list)
│
├── analysis/
│   ├── aggregator.py           # Top senders, category breakdown, timeline
│   ├── insights.py             # Read behavior, frequency, dead subscriptions, oldest_unread_senders
│   └── cleanup_queries.py      # cleanup_query_messages() — extracted from old Cleanup page
│
├── components/
│   ├── safety.py               # live_label_check(), is_large_batch() — no UI deps
│   └── filters.py              # apply_filters() — pure pandas, no UI deps
│
├── backend/                    # FastAPI app
│   ├── main.py                 # App factory, CORS, lifespan (auto-loads tokens on startup)
│   ├── state.py                # In-memory: gmail_services, sync_threads, pending_flows
│   ├── dependencies.py         # get_account(), get_service() dependency injection
│   ├── models/schemas.py       # Pydantic request/response models
│   └── routers/
│       ├── auth.py             # GET /accounts, POST /connect, GET /callback, DELETE /accounts/{email}
│       ├── sync.py             # GET /status, POST /start, GET /progress (SSE)
│       ├── dashboard.py        # GET /stats, /top-senders, /categories, /timeline
│       ├── cleanup.py          # POST /preview, POST /execute
│       ├── unsubscribe.py      # GET /dead, POST /post
│       └── insights.py         # GET /read-rate, /unread-by-label, /oldest-unread
│
├── frontend/                   # Next.js app
│   ├── src/app/                # App Router pages (layout, home, dashboard, cleanup, unsubscribe, insights)
│   ├── src/components/         # UI components (Sidebar, AccountSwitcher, SyncBanner, charts, etc.)
│   ├── src/hooks/              # useAccounts, useSyncStatus (SSE), useCleanup (state machine)
│   └── src/lib/                # api.ts, types.ts, format.ts
│
├── tests/                      # 283 tests — all service layer + all FastAPI routers
│
└── data/                       # .gitignored — per-account isolated storage
    └── <email>/
        ├── token.json
        └── cache.db
```

## Multi-Account Support
- One GCP project / OAuth client (`client_secret.json`) shared across all accounts
- Each account gets its own isolated `data/<email>/` directory
- Account switcher on Home page: add, switch, remove accounts
- `backend/state.py` `gmail_services` dict tracks active services
- All service modules accept an `account_email` parameter

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

### Key implications for Phase 2
- **Full sync must be resumable** — store a page checkpoint in `sync_state` so an interrupted sync picks up where it left off rather than restarting from zero.
- Show a progress bar during full sync; allow the user to browse partial data while it runs.
- Update the Key Gotchas sync time estimate: ~90–120 minutes for this account size.

## Gmail API Rules
- **Scopes**: `gmail.modify` only — this makes permanent deletion impossible at the API level
- **Batch size**: 50 messages per batch request (never exceed 100)
- **Rate limiting**: target 150 quota units/sec (hard limit is 250)
- **Retry**: exponential backoff on 429, 500, 503 responses
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
-- Keys: last_history_id, last_full_sync_ts, total_messages_synced
```

## Streamlit Session State Keys
- `gmail_service` — authenticated Gmail API service object
- `active_account` — currently active account email string
- `last_sync` — timestamp of last sync
- `sync_in_progress` — boolean flag
- `pending_trash` — list of message IDs awaiting confirmation
- `trash_confirmed` — boolean after user confirms

## Implementation Phases
1. **Foundation**: `requirements.txt`, `.gitignore`, `config/settings.py`, `auth/oauth.py`, `cache/database.py`, `app.py`
2. **Fetching & Caching**: `gmail/client.py`, `gmail/fetcher.py`, `cache/sync.py`
3. **Dashboard**: `analysis/aggregator.py`, `components/charts.py`, `components/filters.py`, `pages/1_Dashboard.py`
4. **Cleanup**: `gmail/actions.py`, `components/safety.py`, `pages/2_Cleanup.py`
5. **Unsubscribe & Insights**: `analysis/insights.py`, `pages/3_Unsubscribe.py`, `pages/4_Insights.py`

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

**Backend** (terminal 1, from project root):
```bash
uvicorn backend.main:app --reload --port 8000
```

**Frontend** (terminal 2):
```bash
cd frontend && npm run dev
```

Open `http://localhost:3000` in browser.

## Key Gotchas
- `sender_email` must be parsed from the `From` header at insert time (e.g., extract `email@example.com` from `"Name <email@example.com>"`)
- `is_starred` and `is_important` are denormalized from `label_ids` at insert time for fast safety queries
- Initial full sync takes ~90–120 minutes for ~190k emails (primary account) — SSE progress stream via `GET /api/sync/progress`; sync must be resumable via a page checkpoint in `sync_state`
- After trashing messages, delete those rows from SQLite immediately (don't wait for next sync)
- The `data/` and `auth/credentials/` directories are gitignored — never commit tokens or credentials
- Backend auto-loads existing tokens on startup (lifespan event in `backend/main.py`)
- OAuth redirect URI must be `http://localhost:8000/api/auth/callback` in GCP console

---

## Last Session
**Date**: 2026-02-22

### What We Were Trying to Accomplish
Two things this session:
1. Complete the Streamlit → FastAPI + Next.js migration (Phases A–D) — DONE
2. Implement a UX rework based on user feedback — plan written, **NOT YET COMMITTED OR IMPLEMENTED**

### What Was Completed

**Full Streamlit → FastAPI + Next.js migration (283 tests passing):**

- Phase A: Service layer additions — `oldest_unread_senders()`, `create_auth_flow()`, `exchange_code()`, `cleanup_query_messages()`
- Phase B: FastAPI backend — `backend/` directory with 6 routers (auth, sync SSE, dashboard, cleanup, unsubscribe, insights)
- Phase C: Next.js frontend — 5 pages, 10+ components, Recharts charts, SSE-based sync, `AccountContext` for shared state, `useCleanup` state machine
- Phase D: Deleted `app.py`, `pages/`, trimmed Streamlit deps from `components/`, updated `.gitignore`, `CLAUDE.md`, `README.md`
- 283 tests all pass; `npm run build` clean

### What Is In Progress — NOT YET COMMITTED

**Git state: everything is STAGED but not committed, and deletions still need to be staged.**

To complete the commit:
```bash
git add -u  # stages deleted files (app.py, pages/*)
git add frontend/.gitignore  # untracked
git commit -m "Migrate from Streamlit to FastAPI + Next.js (283 tests passing)"
git push
```

**UX rework plan written but not implemented** — plan file at:
`/home/sidd/.claude/plans/refactored-juggling-meteor.md`

UX rework covers 4 phases:
1. **Backend**: graceful sync stop (`threading.Event`), store `messages_total`/`sync_started_ts`, filter `__new__` from accounts, add `POST /api/auth/logout`
2. **Frontend AccountContext**: single login/logout model (remove `setActiveAccount`, add `logout()`)
3. **UI rework**: merge Home+Dashboard into `page.tsx` (login page when logged out, dashboard when in), conditional sidebar nav, new `SyncBanner` with progress bar + ETA, delete `AccountSwitcher.tsx` and `dashboard/page.tsx`
4. **Dashboard auto-refresh**: `setInterval` every 30s while `is_syncing`

### Known Issues / Blockers
- **GCP project not yet set up** — `client_secret.json` missing. This blocks live runs.
- **`__new__` account showing in UI** — artifact from old OAuth flow; fixed in UX rework plan (filter it in `backend/routers/auth.py` `list_accounts()`)
- **Home page UX problems** — multi-account switcher layout is confusing; fixed in UX rework plan
- **No sync progress bar** — only "Syncing... N cached" text; fixed in UX rework plan

### Exact Next Step to Resume

**Step 1: Finish the commit** (this was interrupted during this session):
```bash
cd /home/sidd/dev/utility/gmail_cleaner
git add -u
git add frontend/.gitignore
git commit -m "Migrate from Streamlit to FastAPI + Next.js (283 tests passing)"
git push
```

**Step 2: Implement the UX rework** — read plan at `/home/sidd/.claude/plans/refactored-juggling-meteor.md`, then proceed with TDD starting from Phase 1 (backend changes). Use Opus for planning, Sonnet for coding.
