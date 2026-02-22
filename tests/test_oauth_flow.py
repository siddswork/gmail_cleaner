"""
Tests for the FastAPI OAuth flow functions in auth/oauth.py:
  - create_auth_flow(redirect_uri)
  - exchange_code(flow, code)

Run with: pytest tests/test_oauth_flow.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from auth.oauth import create_auth_flow, exchange_code


@pytest.fixture
def tmp_credentials(monkeypatch, tmp_path):
    """Create a fake client_secret.json and point auth at it."""
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    secret = {
        "web": {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8000/api/auth/callback"],
        }
    }
    (creds_dir / "client_secret.json").write_text(json.dumps(secret))
    monkeypatch.setenv("GMAIL_CLEANER_CREDENTIALS_DIR", str(creds_dir))
    return creds_dir


class TestCreateAuthFlow:
    def test_returns_flow_and_auth_url(self, tmp_credentials):
        """create_auth_flow should return a (flow, auth_url) tuple."""
        flow, auth_url = create_auth_flow("http://localhost:8000/api/auth/callback")
        assert flow is not None
        assert "accounts.google.com" in auth_url
        assert "client_id=test-client-id" in auth_url

    def test_auth_url_contains_redirect_uri(self, tmp_credentials):
        redirect = "http://localhost:8000/api/auth/callback"
        _, auth_url = create_auth_flow(redirect)
        assert "redirect_uri" in auth_url

    def test_auth_url_contains_state(self, tmp_credentials):
        """The auth URL should contain a state parameter for CSRF protection."""
        _, auth_url = create_auth_flow("http://localhost:8000/api/auth/callback")
        assert "state=" in auth_url

    def test_flow_has_redirect_uri_set(self, tmp_credentials):
        flow, _ = create_auth_flow("http://localhost:8000/api/auth/callback")
        assert flow.redirect_uri == "http://localhost:8000/api/auth/callback"


class TestExchangeCode:
    @patch("auth.oauth.build")
    def test_exchange_code_returns_email_and_creds(self, mock_build, tmp_credentials, monkeypatch, tmp_path):
        """exchange_code should return (email, credentials) on success."""
        monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(tmp_path / "data"))

        # Create a mock flow that returns mock credentials
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.to_json.return_value = json.dumps({
            "token": "fake-token",
            "refresh_token": "fake-refresh",
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
        })
        mock_flow.fetch_token.return_value = None
        mock_flow.credentials = mock_creds

        # Mock Gmail service to return profile
        mock_service = MagicMock()
        mock_service.users().getProfile().execute.return_value = {
            "emailAddress": "user@gmail.com"
        }
        mock_build.return_value = mock_service

        email, creds = exchange_code(mock_flow, "fake-auth-code")
        assert email == "user@gmail.com"
        assert creds is mock_creds
        mock_flow.fetch_token.assert_called_once_with(code="fake-auth-code")

    @patch("auth.oauth.build")
    def test_exchange_code_saves_credentials(self, mock_build, tmp_credentials, monkeypatch, tmp_path):
        """exchange_code should persist the token to data/<email>/token.json."""
        data_dir = tmp_path / "data"
        monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(data_dir))

        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.to_json.return_value = json.dumps({"token": "saved"})
        mock_flow.credentials = mock_creds

        mock_service = MagicMock()
        mock_service.users().getProfile().execute.return_value = {
            "emailAddress": "user@gmail.com"
        }
        mock_build.return_value = mock_service

        exchange_code(mock_flow, "code")

        token_path = data_dir / "user@gmail.com" / "token.json"
        assert token_path.exists()
        assert json.loads(token_path.read_text()) == {"token": "saved"}
