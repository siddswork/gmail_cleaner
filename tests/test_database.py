"""
Tests for cache/database.py

Run with: pytest tests/test_database.py -v
"""
import json
import os
import pytest
import tempfile

from cache.database import (
    get_db_path,
    init_db,
    upsert_email,
    get_email,
    delete_emails,
    log_action,
    get_sync_state,
    set_sync_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    """Redirect DATA_DIR to a temp directory so tests don't touch real data."""
    monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def account(tmp_data_dir):
    """An initialized DB for a test account."""
    email = "test@example.com"
    init_db(email)
    return email


@pytest.fixture
def sample_email():
    return {
        "message_id": "msg_001",
        "thread_id": "thread_001",
        "sender_email": "sender@example.com",
        "sender_name": "Sender Name",
        "subject": "Hello World",
        "date_ts": 1700000000,
        "size_estimate": 12345,
        "label_ids": json.dumps(["INBOX", "CATEGORY_PROMOTIONS"]),
        "is_read": False,
        "is_starred": False,
        "is_important": False,
        "has_attachments": False,
        "unsubscribe_url": "https://example.com/unsub",
        "unsubscribe_post": "List-Unsubscribe=One-Click",
        "snippet": "Hello, this is a snippet.",
        "fetched_at": 1700000100,
    }


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

class TestGetDbPath:
    def test_returns_path_under_data_dir(self, tmp_data_dir):
        path = get_db_path("user@gmail.com")
        assert str(tmp_data_dir) in path

    def test_path_is_scoped_to_account_email(self, tmp_data_dir):
        path1 = get_db_path("alice@gmail.com")
        path2 = get_db_path("bob@gmail.com")
        assert path1 != path2
        assert "alice@gmail.com" in path1
        assert "bob@gmail.com" in path2

    def test_path_ends_with_cache_db(self, tmp_data_dir):
        path = get_db_path("user@gmail.com")
        assert path.endswith("cache.db")

    def test_different_accounts_are_fully_isolated(self, tmp_data_dir):
        """DB files must be in separate directories, not just separate filenames."""
        path1 = get_db_path("alice@gmail.com")
        path2 = get_db_path("bob@gmail.com")
        assert os.path.dirname(path1) != os.path.dirname(path2)


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

class TestInitDb:
    def test_creates_emails_table(self, tmp_data_dir):
        init_db("user@gmail.com")
        import sqlite3
        conn = sqlite3.connect(get_db_path("user@gmail.com"))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='emails'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_creates_action_log_table(self, tmp_data_dir):
        init_db("user@gmail.com")
        import sqlite3
        conn = sqlite3.connect(get_db_path("user@gmail.com"))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='action_log'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_creates_sync_state_table(self, tmp_data_dir):
        init_db("user@gmail.com")
        import sqlite3
        conn = sqlite3.connect(get_db_path("user@gmail.com"))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_state'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_creates_parent_directories(self, tmp_data_dir):
        """init_db must create data/<email>/ if it doesn't exist."""
        email = "newuser@example.com"
        db_path = get_db_path(email)
        assert not os.path.exists(db_path)
        init_db(email)
        assert os.path.exists(db_path)

    def test_idempotent_on_second_call(self, tmp_data_dir):
        """Calling init_db twice must not raise or corrupt existing data."""
        init_db("user@gmail.com")
        init_db("user@gmail.com")  # should not raise


# ---------------------------------------------------------------------------
# Email CRUD
# ---------------------------------------------------------------------------

class TestUpsertEmail:
    def test_inserts_new_email(self, account, sample_email):
        upsert_email(account, sample_email)
        row = get_email(account, sample_email["message_id"])
        assert row is not None
        assert row["message_id"] == "msg_001"

    def test_updates_existing_email(self, account, sample_email):
        upsert_email(account, sample_email)
        updated = {**sample_email, "subject": "Updated Subject"}
        upsert_email(account, updated)
        row = get_email(account, "msg_001")
        assert row["subject"] == "Updated Subject"

    def test_all_fields_stored_correctly(self, account, sample_email):
        upsert_email(account, sample_email)
        row = get_email(account, "msg_001")
        assert row["thread_id"] == "thread_001"
        assert row["sender_email"] == "sender@example.com"
        assert row["sender_name"] == "Sender Name"
        assert row["date_ts"] == 1700000000
        assert row["size_estimate"] == 12345
        assert row["is_read"] == False
        assert row["is_starred"] == False
        assert row["is_important"] == False
        assert row["has_attachments"] == False
        assert row["unsubscribe_url"] == "https://example.com/unsub"
        assert row["snippet"] == "Hello, this is a snippet."

    def test_does_not_mix_accounts(self, tmp_data_dir, sample_email):
        """An email inserted for account A must not appear for account B."""
        init_db("alice@gmail.com")
        init_db("bob@gmail.com")
        upsert_email("alice@gmail.com", sample_email)
        row = get_email("bob@gmail.com", sample_email["message_id"])
        assert row is None


class TestGetEmail:
    def test_returns_none_for_missing_id(self, account):
        assert get_email(account, "nonexistent_id") is None

    def test_returns_dict_like_row(self, account, sample_email):
        upsert_email(account, sample_email)
        row = get_email(account, "msg_001")
        # Must support key-based access
        assert row["message_id"] == "msg_001"


class TestDeleteEmails:
    def test_deletes_single_email(self, account, sample_email):
        upsert_email(account, sample_email)
        delete_emails(account, ["msg_001"])
        assert get_email(account, "msg_001") is None

    def test_deletes_multiple_emails(self, account, sample_email):
        emails = [
            {**sample_email, "message_id": "msg_A"},
            {**sample_email, "message_id": "msg_B"},
            {**sample_email, "message_id": "msg_C"},
        ]
        for e in emails:
            upsert_email(account, e)
        delete_emails(account, ["msg_A", "msg_B"])
        assert get_email(account, "msg_A") is None
        assert get_email(account, "msg_B") is None
        assert get_email(account, "msg_C") is not None

    def test_delete_nonexistent_is_noop(self, account):
        """Deleting IDs that don't exist must not raise."""
        delete_emails(account, ["does_not_exist"])


# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------

class TestLogAction:
    def test_logs_trash_action(self, account):
        log_action(account, {
            "action": "trash",
            "message_ids": json.dumps(["msg_001", "msg_002"]),
            "count": 2,
            "size_reclaimed": 24690,
            "timestamp": 1700001000,
            "details": json.dumps({"sender": "sender@example.com"}),
        })
        import sqlite3
        conn = sqlite3.connect(get_db_path(account))
        rows = conn.execute("SELECT * FROM action_log").fetchall()
        assert len(rows) == 1
        conn.close()

    def test_log_id_autoincrement(self, account):
        for i in range(3):
            log_action(account, {
                "action": "trash",
                "message_ids": json.dumps([f"msg_{i}"]),
                "count": 1,
                "size_reclaimed": 1000,
                "timestamp": 1700001000 + i,
                "details": "{}",
            })
        import sqlite3
        conn = sqlite3.connect(get_db_path(account))
        ids = [r[0] for r in conn.execute("SELECT id FROM action_log").fetchall()]
        assert ids == [1, 2, 3]
        conn.close()


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

class TestSyncState:
    def test_get_returns_none_for_missing_key(self, account):
        assert get_sync_state(account, "last_history_id") is None

    def test_set_then_get(self, account):
        set_sync_state(account, "last_history_id", "12345")
        assert get_sync_state(account, "last_history_id") == "12345"

    def test_update_existing_key(self, account):
        set_sync_state(account, "last_history_id", "100")
        set_sync_state(account, "last_history_id", "200")
        assert get_sync_state(account, "last_history_id") == "200"

    def test_multiple_keys_independent(self, account):
        set_sync_state(account, "last_history_id", "999")
        set_sync_state(account, "last_full_sync_ts", "1700000000")
        set_sync_state(account, "total_messages_synced", "42000")
        assert get_sync_state(account, "last_history_id") == "999"
        assert get_sync_state(account, "last_full_sync_ts") == "1700000000"
        assert get_sync_state(account, "total_messages_synced") == "42000"

    def test_sync_state_isolated_per_account(self, tmp_data_dir):
        init_db("alice@gmail.com")
        init_db("bob@gmail.com")
        set_sync_state("alice@gmail.com", "last_history_id", "alice_val")
        assert get_sync_state("bob@gmail.com", "last_history_id") is None
