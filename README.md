# Gmail Cleaner

A personal web tool to reclaim storage on a Gmail account that has accumulated 20+ years of email.
Supports up to 3 accounts. Nothing is deleted without explicit approval — all destructive actions
go through Gmail's Trash (30-day recovery window).

## Architecture

```
Next.js (port 3000) ──► FastAPI (port 8000) ──► Gmail API
                                 │
                           SQLite cache (per account)
```

## Prerequisites

- Python 3.12+
- Node.js 18+
- A Google Cloud project with the Gmail API enabled (see [GCP Setup](#gcp-setup) below)

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/siddswork/gmail_cleaner
cd gmail_cleaner

# 2. Create a Python virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt

# 3. Install frontend dependencies
cd frontend
npm install
cd ..
```

## Running the App

### Option A — single command (recommended)

```bash
source .venv/bin/activate
./start.sh
```

This starts both the backend and frontend in the background and prints their URLs.
Use `./stop.sh` to shut everything down.

### Option B — two terminals

**Terminal 1 (backend):**
```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 (frontend):**
```bash
cd frontend
npm run dev
```

Then open **http://localhost:3000** in your browser.

> **WSL2 note:** open the URL in your Windows browser, not the WSL terminal browser.

## First Run — Connecting a Gmail Account

1. Open http://localhost:3000
2. Click **Connect account**
3. Copy the auth URL that appears and open it in your browser
4. Complete the Google sign-in
5. Google redirects back to the app automatically
6. On the Home page, click **Start sync** — the first full sync takes 90–120 minutes for a large mailbox; progress is shown live

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## GCP Setup

Before the OAuth flow can work you need a GCP project with credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Gmail API** for that project.
3. Go to **APIs & Services → Credentials** → **Create credentials** → **OAuth 2.0 Client ID**.
4. Application type: **Web application**.
5. Under **Authorized redirect URIs** add: `http://localhost:8000/api/auth/callback`
6. Download the JSON file and save it to:
   ```
   auth/credentials/client_secret.json
   ```
   This file is gitignored and must never be committed.
7. Go to **OAuth consent screen → Test users** and add your Gmail address.

## Sensitive Data — What Is Never Committed

| Path | What it contains |
|---|---|
| `auth/credentials/client_secret.json` | GCP OAuth client secret |
| `data/<email>/token.json` | Per-account OAuth access + refresh tokens |
| `data/<email>/cache.db` | Per-account SQLite cache of email metadata |

All of these paths are covered by `.gitignore`.

## Project Structure

```
gmail_cleaner/
├── backend/                # FastAPI app (port 8000)
│   ├── main.py             # App factory, CORS, startup
│   ├── state.py            # In-memory services and sync threads
│   ├── dependencies.py     # Dependency injection
│   ├── models/schemas.py   # Pydantic request/response models
│   └── routers/            # auth, sync, dashboard, cleanup, unsubscribe, insights
├── frontend/               # Next.js app (port 3000)
│   └── src/
│       ├── app/            # Pages: home, dashboard, cleanup, unsubscribe, insights
│       ├── components/     # UI components and Recharts wrappers
│       ├── hooks/          # useAccounts, useSyncStatus (SSE), useCleanup
│       └── lib/            # api.ts, types.ts, format.ts
├── config/settings.py      # Constants and API config
├── auth/oauth.py           # OAuth2 flow and token management
├── cache/database.py       # SQLite schema and CRUD (one DB per account)
├── cache/sync.py           # Full and incremental Gmail sync
├── gmail/client.py         # Rate limiter, retry, batch helper
├── gmail/fetcher.py        # Message listing and metadata fetch
├── gmail/actions.py        # Trash and unsubscribe operations
├── analysis/aggregator.py  # Top senders, category breakdown, timeline
├── analysis/insights.py    # Read behavior, dead subscriptions, oldest unread
├── analysis/cleanup_queries.py  # Cleanup message query
├── components/             # Pure Python safety checks and filter logic
├── tests/                  # pytest test suite (283 tests)
├── start.sh                # Start both backend and frontend
└── stop.sh                 # Stop both
```

## Safety Rules

- Emails are **never permanently deleted** — only moved to Trash via the Gmail API.
- Starred and Important emails are **always excluded** from analysis and bulk actions.
- Every destructive action requires an explicit confirmation step in the UI.
- Batches larger than 500 emails require typing `DELETE` to confirm.
