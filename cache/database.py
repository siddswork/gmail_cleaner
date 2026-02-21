"""
SQLite cache layer — one database per Gmail account.

All public functions accept `account_email` as their first argument.
The data root is controlled by the GMAIL_CLEANER_DATA_DIR env var
(defaults to `<project_root>/data`).
"""
import os
import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _data_root() -> Path:
    env = os.environ.get("GMAIL_CLEANER_DATA_DIR")
    if env:
        return Path(env)
    # Default: two levels up from this file → project root / data
    return Path(__file__).parent.parent / "data"


def _connect(account_email: str) -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(account_email))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def get_db_path(account_email: str) -> str:
    """Return the absolute path to the SQLite DB for this account."""
    return str(_data_root() / account_email / "cache.db")


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def init_db(account_email: str) -> None:
    """Create the per-account directory and initialize all tables (idempotent)."""
    db_path = Path(get_db_path(account_email))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = _connect(account_email)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS emails (
                message_id        TEXT PRIMARY KEY,
                thread_id         TEXT,
                sender_email      TEXT,
                sender_name       TEXT,
                subject           TEXT,
                date_ts           INTEGER,
                size_estimate     INTEGER,
                label_ids         TEXT,
                is_read           BOOLEAN,
                is_starred        BOOLEAN,
                is_important      BOOLEAN,
                has_attachments   BOOLEAN,
                unsubscribe_url   TEXT,
                unsubscribe_post  TEXT,
                snippet           TEXT,
                fetched_at        INTEGER
            );

            CREATE TABLE IF NOT EXISTS action_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                action         TEXT,
                message_ids    TEXT,
                count          INTEGER,
                size_reclaimed INTEGER,
                timestamp      INTEGER,
                details        TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
    conn.close()


# ---------------------------------------------------------------------------
# Email CRUD
# ---------------------------------------------------------------------------

def upsert_email(account_email: str, email_data: dict) -> None:
    """Insert or replace an email record."""
    conn = _connect(account_email)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO emails (
                message_id, thread_id, sender_email, sender_name,
                subject, date_ts, size_estimate, label_ids,
                is_read, is_starred, is_important, has_attachments,
                unsubscribe_url, unsubscribe_post, snippet, fetched_at
            ) VALUES (
                :message_id, :thread_id, :sender_email, :sender_name,
                :subject, :date_ts, :size_estimate, :label_ids,
                :is_read, :is_starred, :is_important, :has_attachments,
                :unsubscribe_url, :unsubscribe_post, :snippet, :fetched_at
            )
            """,
            email_data,
        )
    conn.close()


def get_email(account_email: str, message_id: str) -> sqlite3.Row | None:
    """Return the email row for `message_id`, or None if not found."""
    conn = _connect(account_email)
    row = conn.execute(
        "SELECT * FROM emails WHERE message_id = ?", (message_id,)
    ).fetchone()
    conn.close()
    return row


def delete_emails(account_email: str, message_ids: list[str]) -> None:
    """Delete email rows by message ID (called after trashing in Gmail)."""
    if not message_ids:
        return
    placeholders = ",".join("?" * len(message_ids))
    conn = _connect(account_email)
    with conn:
        conn.execute(
            f"DELETE FROM emails WHERE message_id IN ({placeholders})",
            message_ids,
        )
    conn.close()


# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------

def log_action(account_email: str, action_data: dict) -> None:
    """Append a record to the action_log table."""
    conn = _connect(account_email)
    with conn:
        conn.execute(
            """
            INSERT INTO action_log (action, message_ids, count, size_reclaimed, timestamp, details)
            VALUES (:action, :message_ids, :count, :size_reclaimed, :timestamp, :details)
            """,
            action_data,
        )
    conn.close()


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

def get_sync_state(account_email: str, key: str) -> str | None:
    """Return the value for `key` from sync_state, or None if absent."""
    conn = _connect(account_email)
    row = conn.execute(
        "SELECT value FROM sync_state WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def set_sync_state(account_email: str, key: str, value: str) -> None:
    """Insert or update a key in sync_state."""
    conn = _connect(account_email)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.close()
