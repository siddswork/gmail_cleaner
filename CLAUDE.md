# Gmail Cleaner — Project Instructions

## Project Overview
A personal web-based tool to clean up a 20-year-old Gmail account (and up to 2-3 family accounts) that is nearing storage capacity. The goal is to visualize storage usage, bulk-delete unwanted emails, and unsubscribe from mailing lists — with the user always in control. Nothing is deleted without explicit approval.

## Tech Stack
- **Frontend/UI**: Streamlit
- **Language**: Python
- **Gmail access**: `google-api-python-client` with OAuth2 (`gmail.modify` scope only)
- **Local cache**: SQLite (one DB per account)
- **Data analysis**: pandas
- **Charts**: Plotly
- **No FastAPI** — Streamlit calls Gmail API directly through Python service modules

## Architecture
```
Streamlit App --> Python Service Layer --> Gmail API
                        |
                   SQLite Cache (per account)
```

## Project Structure
```
gmail_cleaner/
├── app.py                      # Entry point, auth flow, account switcher, sync
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
│   └── insights.py             # Read behavior, frequency, dead subscriptions
│
├── pages/
│   ├── 1_Dashboard.py          # Space analysis charts and tables
│   ├── 2_Cleanup.py            # Bulk delete with preview + confirmation
│   ├── 3_Unsubscribe.py        # Subscription manager
│   └── 4_Insights.py           # Read behavior insights
│
├── components/
│   ├── safety.py               # Protection checks, confirmation dialogs
│   ├── filters.py              # Reusable filter widgets
│   └── charts.py               # Plotly chart wrappers
│
└── data/                       # .gitignored — per-account isolated storage
    └── <email>/                # e.g., data/sidd@gmail.com/
        ├── token.json          # OAuth token for this account
        └── cache.db            # SQLite cache for this account
```

## Multi-Account Support
- One GCP project / OAuth client (`client_secret.json`) shared across all accounts
- Each account gets its own isolated `data/<email>/` directory
- Sidebar account switcher: add, switch, remove accounts
- `st.session_state['active_account']` tracks the currently active account
- All service modules accept an `account_email` parameter to resolve the correct data path

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
```bash
streamlit run app.py
```

## Key Gotchas
- Streamlit reruns the entire script on every interaction — all state must be in `st.session_state` or SQLite, never Python globals
- `sender_email` must be parsed from the `From` header at insert time (e.g., extract `email@example.com` from `"Name <email@example.com>"`)
- `is_starred` and `is_important` are denormalized from `label_ids` at insert time for fast safety queries
- Initial full sync takes ~90–120 minutes for ~190k emails (primary account) — show progress bar and allow browsing partial data during sync; sync must be resumable via a page checkpoint in `sync_state`
- After trashing messages, delete those rows from SQLite immediately (don't wait for next sync)
- The `data/` and `auth/credentials/` directories are gitignored — never commit tokens or credentials

---

## Last Session
**Date**: 2026-02-21

### What We Were Trying to Accomplish
Kickstart a brand new Gmail cleanup tool from scratch — a personal web app to help reclaim storage on a 20-year-old Gmail account nearing capacity, with support for 2-3 family accounts.

### What Was Completed
- **Git initialized** with `main` branch; remote set to `https://github.com/siddswork/gmail_cleaner`
- **Architecture decisions finalized** (all made with Opus):
  - Streamlit over React or FastAPI — fastest path to a working personal tool
  - No FastAPI — Streamlit calls Gmail API directly
  - SQLite per-account cache
  - `gmail.modify` scope only — permanent delete impossible at API level
  - Multi-account support (up to 3 family accounts, shared GCP OAuth client)
  - No LLMs in v1 — basic aggregation/pandas is sufficient
  - TDD workflow mandated (user added this to CLAUDE.md)
- **Plan written and approved** — 5 implementation phases fully designed (see Implementation Phases above)
- **`CLAUDE.md` created** with full project instructions, schema, safety rules, and model usage preferences (user modified to add TDD rules and planning mode prompts)
- **`MEMORY.md` seeded** at `~/.claude/projects/.../memory/MEMORY.md`

### What Is In Progress
Nothing is in progress — the project directory is **empty except for `CLAUDE.md`**. No code has been written yet.

### Known Issues / Blockers
- **GCP project not yet created** — the user needs to create a Google Cloud project, enable the Gmail API, and download `client_secret.json` before the OAuth flow can work. This is a prerequisite for Phase 1 testing.
- No `requirements.txt`, no virtual environment set up yet.

### Exact Next Step to Resume
**Start Phase 1: Foundation** — following TDD workflow.

Order of work:
1. Write failing tests for `cache/database.py` (schema creation, CRUD) → show to user → get confirmation → implement
2. Write failing tests for `auth/oauth.py` (token load/save, multi-account path resolution) → show → confirm → implement
3. Write `config/settings.py` (no tests needed — just constants)
4. Write `requirements.txt`
5. Write `.gitignore`
6. Write `app.py` skeleton (auth flow, account switcher, sync status)

**Reminder before starting**: Per CLAUDE.md, ask the user if they want to switch to Opus for planning, or confirm Sonnet is fine for coding and proceed with TDD.
