"""
Tests for auth/oauth.py

Run with: pytest tests/test_oauth.py -v
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from auth.oauth import (
    get_client_secret_path,
    get_token_path,
    load_credentials,
    save_credentials,
    get_authenticated_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def tmp_credentials_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_CLEANER_CREDENTIALS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def valid_token_data():
    return {
        "token": "access_token_abc",
        "refresh_token": "refresh_token_xyz",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id_123",
        "client_secret": "client_secret_456",
        "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
    }


def _write_token(tmp_path, email, data):
    token_dir = tmp_path / email
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "token.json").write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

class TestGetClientSecretPath:
    def test_returns_string(self, tmp_credentials_dir):
        path = get_client_secret_path()
        assert isinstance(path, str)

    def test_filename_is_client_secret_json(self, tmp_credentials_dir):
        path = get_client_secret_path()
        assert path.endswith("client_secret.json")

    def test_path_is_under_credentials_dir(self, tmp_credentials_dir):
        path = get_client_secret_path()
        assert str(tmp_credentials_dir) in path

    def test_same_path_for_all_accounts(self, tmp_credentials_dir):
        """client_secret.json is shared — must not vary by account."""
        assert get_client_secret_path() == get_client_secret_path()


class TestGetTokenPath:
    def test_returns_string(self, tmp_data_dir):
        path = get_token_path("user@gmail.com")
        assert isinstance(path, str)

    def test_filename_is_token_json(self, tmp_data_dir):
        path = get_token_path("user@gmail.com")
        assert path.endswith("token.json")

    def test_path_is_under_data_dir(self, tmp_data_dir):
        path = get_token_path("user@gmail.com")
        assert str(tmp_data_dir) in path

    def test_different_accounts_have_different_paths(self, tmp_data_dir):
        path1 = get_token_path("alice@gmail.com")
        path2 = get_token_path("bob@gmail.com")
        assert path1 != path2

    def test_account_email_in_path(self, tmp_data_dir):
        path = get_token_path("alice@gmail.com")
        assert "alice@gmail.com" in path

    def test_paths_are_in_separate_directories(self, tmp_data_dir):
        path1 = get_token_path("alice@gmail.com")
        path2 = get_token_path("bob@gmail.com")
        assert os.path.dirname(path1) != os.path.dirname(path2)


# ---------------------------------------------------------------------------
# load_credentials
# ---------------------------------------------------------------------------

class TestLoadCredentials:
    def test_returns_none_when_token_file_missing(self, tmp_data_dir):
        result = load_credentials("notoken@gmail.com")
        assert result is None

    def test_returns_credentials_when_token_exists(
        self, tmp_data_dir, valid_token_data
    ):
        _write_token(tmp_data_dir, "user@gmail.com", valid_token_data)
        with patch("auth.oauth.Credentials") as MockCreds:
            MockCreds.from_authorized_user_info.return_value = MagicMock()
            result = load_credentials("user@gmail.com")
        assert result is not None

    def test_reads_correct_account_token(self, tmp_data_dir, valid_token_data):
        """Alice's token must not be loaded when asking for Bob's credentials."""
        _write_token(tmp_data_dir, "alice@gmail.com", valid_token_data)
        result = load_credentials("bob@gmail.com")
        assert result is None

    def test_passes_token_data_to_credentials(self, tmp_data_dir, valid_token_data):
        _write_token(tmp_data_dir, "user@gmail.com", valid_token_data)
        with patch("auth.oauth.Credentials") as MockCreds:
            mock_creds = MagicMock()
            MockCreds.from_authorized_user_info.return_value = mock_creds
            result = load_credentials("user@gmail.com")
            MockCreds.from_authorized_user_info.assert_called_once_with(
                valid_token_data
            )


# ---------------------------------------------------------------------------
# save_credentials
# ---------------------------------------------------------------------------

class TestSaveCredentials:
    def test_creates_token_file(self, tmp_data_dir):
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = json.dumps({"token": "abc"})
        save_credentials("user@gmail.com", mock_creds)
        token_path = Path(get_token_path("user@gmail.com"))
        assert token_path.exists()

    def test_creates_parent_directories(self, tmp_data_dir):
        """data/<email>/ must be created if absent."""
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = json.dumps({"token": "abc"})
        email = "newuser@gmail.com"
        assert not Path(get_token_path(email)).parent.exists()
        save_credentials(email, mock_creds)
        assert Path(get_token_path(email)).parent.exists()

    def test_writes_credentials_json(self, tmp_data_dir):
        token_data = {"token": "my_access_token", "refresh_token": "my_refresh"}
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = json.dumps(token_data)
        save_credentials("user@gmail.com", mock_creds)
        written = json.loads(Path(get_token_path("user@gmail.com")).read_text())
        assert written == token_data

    def test_overwrites_existing_token(self, tmp_data_dir, valid_token_data):
        _write_token(tmp_data_dir, "user@gmail.com", valid_token_data)
        new_token = {"token": "new_token"}
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = json.dumps(new_token)
        save_credentials("user@gmail.com", mock_creds)
        written = json.loads(Path(get_token_path("user@gmail.com")).read_text())
        assert written["token"] == "new_token"


# ---------------------------------------------------------------------------
# get_authenticated_service
# ---------------------------------------------------------------------------

class TestGetAuthenticatedService:
    def test_returns_service_with_valid_credentials(
        self, tmp_data_dir, valid_token_data
    ):
        _write_token(tmp_data_dir, "user@gmail.com", valid_token_data)
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expired = False
        with (
            patch("auth.oauth.Credentials") as MockCreds,
            patch("auth.oauth.build") as mock_build,
        ):
            MockCreds.from_authorized_user_info.return_value = mock_creds
            mock_build.return_value = MagicMock()
            service = get_authenticated_service("user@gmail.com")
        mock_build.assert_called_once()
        assert service is not None

    def test_refreshes_expired_credentials(self, tmp_data_dir, valid_token_data):
        _write_token(tmp_data_dir, "user@gmail.com", valid_token_data)
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token_xyz"
        with (
            patch("auth.oauth.Credentials") as MockCreds,
            patch("auth.oauth.Request") as MockRequest,
            patch("auth.oauth.build"),
            patch("auth.oauth.save_credentials") as mock_save,
        ):
            MockCreds.from_authorized_user_info.return_value = mock_creds
            get_authenticated_service("user@gmail.com")
        mock_creds.refresh.assert_called_once()
        mock_save.assert_called_once_with("user@gmail.com", mock_creds)

    def test_runs_oauth_flow_when_no_credentials(
        self, tmp_data_dir, tmp_credentials_dir
    ):
        """No token.json → must trigger the OAuth flow."""
        (tmp_credentials_dir / "client_secret.json").write_text(
            json.dumps({"installed": {}})
        )
        mock_creds = MagicMock()
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        with (
            patch("auth.oauth.InstalledAppFlow") as MockFlow,
            patch("auth.oauth.build"),
            patch("auth.oauth.save_credentials") as mock_save,
        ):
            MockFlow.from_client_secrets_file.return_value = mock_flow
            get_authenticated_service("user@gmail.com")
        MockFlow.from_client_secrets_file.assert_called_once()
        mock_flow.run_local_server.assert_called_once_with(port=0)
        mock_save.assert_called_once_with("user@gmail.com", mock_creds)

    def test_saves_credentials_after_oauth_flow(
        self, tmp_data_dir, tmp_credentials_dir
    ):
        (tmp_credentials_dir / "client_secret.json").write_text(
            json.dumps({"installed": {}})
        )
        mock_creds = MagicMock()
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        with (
            patch("auth.oauth.InstalledAppFlow") as MockFlow,
            patch("auth.oauth.build"),
            patch("auth.oauth.save_credentials") as mock_save,
        ):
            MockFlow.from_client_secrets_file.return_value = mock_flow
            get_authenticated_service("user@gmail.com")
        mock_save.assert_called_once_with("user@gmail.com", mock_creds)

    def test_builds_gmail_service(self, tmp_data_dir, valid_token_data):
        _write_token(tmp_data_dir, "user@gmail.com", valid_token_data)
        mock_creds = MagicMock()
        mock_creds.valid = True
        with (
            patch("auth.oauth.Credentials") as MockCreds,
            patch("auth.oauth.build") as mock_build,
        ):
            MockCreds.from_authorized_user_info.return_value = mock_creds
            mock_build.return_value = MagicMock()
            get_authenticated_service("user@gmail.com")
        mock_build.assert_called_once_with(
            "gmail", "v1", credentials=mock_creds
        )
