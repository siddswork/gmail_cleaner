"""
Tests for cache/sync.py

Run with: pytest tests/test_sync.py -v
"""
import ssl
import pytest
from unittest.mock import MagicMock, patch, call

from cache.database import init_db, get_sync_state, set_sync_state
from cache.sync import full_sync, incremental_sync


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def account(tmp_data_dir):
    email = "test@example.com"
    init_db(email)
    return email


def make_service(history_id="99999"):
    service = MagicMock()
    service.users().getProfile().execute.return_value = {
        "historyId": history_id,
        "emailAddress": "test@example.com",
    }
    return service


def make_email_data(message_id="msg_1"):
    return {
        "message_id": message_id,
        "thread_id": "thread_1",
        "sender_email": "sender@example.com",
        "sender_name": "Sender",
        "subject": "Hello",
        "date_ts": 1700000000,
        "size_estimate": 5000,
        "label_ids": '["INBOX"]',
        "is_read": True,
        "is_starred": False,
        "is_important": False,
        "has_attachments": False,
        "unsubscribe_url": None,
        "unsubscribe_post": None,
        "snippet": "snippet text",
        "fetched_at": 1700000100,
    }


# ---------------------------------------------------------------------------
# full_sync
# ---------------------------------------------------------------------------

class TestFullSync:
    def test_fetches_all_pages(self, account):
        service = make_service()
        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
        ):
            mock_list.side_effect = [
                {"ids": ["a", "b"], "next_page_token": "page2"},
                {"ids": ["c", "d"], "next_page_token": None},
            ]
            full_sync(account, service)
        assert mock_list.call_count == 2

    def test_upserts_fetched_emails_to_db(self, account):
        service = make_service()
        email = make_email_data("msg_1")
        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=[email]),
            patch("cache.sync.batch_upsert_emails") as mock_upsert,
        ):
            mock_list.return_value = {"ids": ["msg_1"], "next_page_token": None}
            full_sync(account, service)
        mock_upsert.assert_called_once_with(account, [email])

    def test_stores_history_id_after_sync(self, account):
        service = make_service(history_id="42000")
        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
        ):
            mock_list.return_value = {"ids": [], "next_page_token": None}
            full_sync(account, service)
        assert get_sync_state(account, "last_history_id") == "42000"

    def test_stores_full_sync_timestamp(self, account):
        service = make_service()
        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
            patch("cache.sync.time") as mock_time,
        ):
            mock_list.return_value = {"ids": [], "next_page_token": None}
            mock_time.time.return_value = 1700000000
            full_sync(account, service)
        assert get_sync_state(account, "last_full_sync_ts") == "1700000000"

    def test_saves_page_checkpoint_before_fetching_next_page(self, account):
        """Checkpoint must be saved so an interrupted sync can resume."""
        service = make_service()
        saved_checkpoints = []

        original_set = set_sync_state

        def capturing_set(email, key, value):
            if key == "full_sync_page_token":
                saved_checkpoints.append(value)
            original_set(email, key, value)

        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
            patch("cache.sync.set_sync_state", side_effect=capturing_set),
            patch("cache.sync.get_sync_state", return_value=None),
        ):
            mock_list.side_effect = [
                {"ids": [], "next_page_token": "page2_token"},
                {"ids": [], "next_page_token": None},
            ]
            full_sync(account, service)

        assert "page2_token" in saved_checkpoints

    def test_clears_checkpoint_on_completion(self, account):
        service = make_service()
        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
        ):
            mock_list.return_value = {"ids": [], "next_page_token": None}
            full_sync(account, service)
        assert get_sync_state(account, "full_sync_page_token") is None

    def test_resumes_from_stored_checkpoint(self, account):
        """If a checkpoint exists, the first list call must use it as page_token."""
        set_sync_state(account, "full_sync_page_token", "resume_token")
        service = make_service()
        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
        ):
            mock_list.return_value = {"ids": [], "next_page_token": None}
            full_sync(account, service)
        first_call = mock_list.call_args_list[0]
        assert first_call.kwargs.get("page_token") == "resume_token"

    def test_returns_total_count_synced(self, account):
        service = make_service()
        emails = [make_email_data(f"msg_{i}") for i in range(3)]
        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=emails),
            patch("cache.sync.batch_upsert_emails"),
        ):
            mock_list.return_value = {
                "ids": ["msg_0", "msg_1", "msg_2"],
                "next_page_token": None,
            }
            count = full_sync(account, service)
        assert count == 3


# ---------------------------------------------------------------------------
# incremental_sync
# ---------------------------------------------------------------------------

class TestIncrementalSync:
    def test_raises_when_no_history_id_stored(self, account):
        service = MagicMock()
        with pytest.raises(RuntimeError, match="full sync"):
            incremental_sync(account, service)

    def test_calls_history_list_with_stored_id(self, account):
        set_sync_state(account, "last_history_id", "12345")
        service = MagicMock()
        service.users().history().list().execute.return_value = {
            "history": [],
            "historyId": "12346",
        }
        with patch("cache.sync.fetch_metadata_batch", return_value=[]):
            incremental_sync(account, service)
        service.users().history().list.assert_called_with(
            userId="me",
            startHistoryId="12345",
            historyTypes=["messageAdded", "messageDeleted"],
        )

    def test_upserts_added_messages(self, account):
        set_sync_state(account, "last_history_id", "12345")
        service = MagicMock()
        service.users().history().list().execute.return_value = {
            "history": [
                {"messagesAdded": [{"message": {"id": "new_msg_1"}}]},
            ],
            "historyId": "12346",
        }
        email = make_email_data("new_msg_1")
        with (
            patch("cache.sync.fetch_metadata_batch", return_value=[email]) as mock_fetch,
            patch("cache.sync.batch_upsert_emails") as mock_upsert,
        ):
            incremental_sync(account, service)
        mock_fetch.assert_called_once_with(service, ["new_msg_1"])
        mock_upsert.assert_called_once_with(account, [email])

    def test_deletes_removed_messages(self, account):
        set_sync_state(account, "last_history_id", "12345")
        service = MagicMock()
        service.users().history().list().execute.return_value = {
            "history": [
                {"messagesDeleted": [{"message": {"id": "del_msg_1"}}]},
            ],
            "historyId": "12346",
        }
        with (
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
            patch("cache.sync.delete_emails") as mock_delete,
        ):
            incremental_sync(account, service)
        mock_delete.assert_called_once_with(account, ["del_msg_1"])

    def test_updates_history_id_after_sync(self, account):
        set_sync_state(account, "last_history_id", "12345")
        service = MagicMock()
        service.users().history().list().execute.return_value = {
            "history": [],
            "historyId": "99999",
        }
        with patch("cache.sync.fetch_metadata_batch", return_value=[]):
            incremental_sync(account, service)
        assert get_sync_state(account, "last_history_id") == "99999"

    def test_returns_total_count_of_changes(self, account):
        set_sync_state(account, "last_history_id", "12345")
        service = MagicMock()
        service.users().history().list().execute.return_value = {
            "history": [
                {"messagesAdded": [
                    {"message": {"id": "a"}},
                    {"message": {"id": "b"}},
                ]},
                {"messagesDeleted": [
                    {"message": {"id": "c"}},
                ]},
            ],
            "historyId": "12346",
        }
        added_emails = [make_email_data("a"), make_email_data("b")]
        with (
            patch("cache.sync.fetch_metadata_batch", return_value=added_emails),
            patch("cache.sync.batch_upsert_emails"),
            patch("cache.sync.delete_emails"),
        ):
            count = incremental_sync(account, service)
        assert count == 3  # 2 added + 1 deleted

    def test_retries_on_ssl_eof_error(self, account):
        """incremental_sync must retry history.list on SSLEOFError."""
        set_sync_state(account, "last_history_id", "12345")
        service = MagicMock()
        service.users().history().list().execute.side_effect = [
            ssl.SSLEOFError(),
            {"history": [], "historyId": "12346"},
        ]
        with (
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
            patch("time.sleep"),
        ):
            count = incremental_sync(account, service)
        assert count == 0
        # execute called twice — once failed, once succeeded
        assert service.users().history().list().execute.call_count == 2


class TestFullSyncRetry:
    def test_retries_get_profile_on_ssl_eof_error(self, account):
        """full_sync must retry getProfile on SSLEOFError."""
        service = MagicMock()
        service.users().getProfile().execute.side_effect = [
            ssl.SSLEOFError(),
            {"historyId": "99999", "emailAddress": "test@example.com"},
        ]
        with (
            patch("cache.sync.list_message_ids") as mock_list,
            patch("cache.sync.fetch_metadata_batch", return_value=[]),
            patch("time.sleep"),
        ):
            mock_list.return_value = {"ids": [], "next_page_token": None}
            full_sync(account, service)
        assert get_sync_state(account, "last_history_id") == "99999"
        assert service.users().getProfile().execute.call_count == 2
