# Gmail Cleaner

A personal web tool to reclaim storage on a Gmail account that has accumulated 20+ years of email.
Supports up to 3 accounts. Nothing is deleted without explicit approval — all destructive actions
go through Gmail's Trash (30-day recovery window).

## Prerequisites

- Python 3.12+
- A Google Cloud project with the Gmail API enabled (see [GCP Setup](#gcp-setup) below)

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/siddswork/gmail_cleaner
cd gmail_cleaner

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

## Running the App

```bash
source .venv/bin/activate
streamlit run app.py
```

The app opens at `http://localhost:8501`. On first run it will walk you through
connecting your Gmail account via OAuth.

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

To run a specific test file:

```bash
pytest tests/test_database.py -v
```

## GCP Setup

Before the OAuth flow can work you need to create a GCP project and download
your OAuth client credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Gmail API** for that project.
3. Go to **APIs & Services → Credentials** and create an **OAuth 2.0 Client ID**
   (application type: *Desktop app*).
4. Download the JSON file and save it to:
   ```
   auth/credentials/client_secret.json
   ```
   This file is gitignored and must never be committed.

## Sensitive Data — What Is Never Committed

| Path | What it contains |
|---|---|
| `auth/credentials/client_secret.json` | GCP OAuth client secret |
| `data/<email>/token.json` | Per-account OAuth access + refresh tokens |
| `data/<email>/cache.db` | Per-account SQLite cache of email metadata |

All of these paths are covered by `.gitignore`. Double-check with
`git status` before committing if you are unsure.

## Project Structure

```
gmail_cleaner/
├── app.py                  # Entry point, auth flow, account switcher
├── config/settings.py      # Constants and API config
├── auth/oauth.py           # OAuth2 flow and token management
├── cache/database.py       # SQLite schema and CRUD (one DB per account)
├── cache/sync.py           # Full and incremental Gmail sync
├── gmail/client.py         # Rate limiter, retry, batch helper
├── gmail/fetcher.py        # Message listing and metadata fetch
├── gmail/actions.py        # Trash and unsubscribe operations
├── analysis/aggregator.py  # Top senders, category breakdown
├── analysis/insights.py    # Read behavior, dead subscriptions
├── pages/                  # Streamlit multi-page UI
├── components/             # Reusable UI widgets and safety checks
└── tests/                  # pytest test suite
```

## Safety Rules

- Emails are **never permanently deleted** — only moved to Trash via the Gmail API.
- Starred and Important emails are **always excluded** from analysis and bulk actions.
- Every destructive action requires an explicit confirmation step in the UI.
- Batches larger than 500 emails require typing `DELETE` to confirm.
