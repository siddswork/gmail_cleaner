"""
Shared fixtures for backend tests.
"""
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import state
from backend.main import app
from cache.database import init_db


@pytest.fixture(autouse=True)
def clear_state():
    """Clear in-memory state before each test."""
    state.gmail_services.clear()
    state.sync_threads.clear()
    state.pending_flows.clear()
    yield
    state.gmail_services.clear()
    state.sync_threads.clear()
    state.pending_flows.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_CLEANER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def account(tmp_data_dir):
    email = "test@example.com"
    init_db(email)
    return email


@pytest.fixture
def connected_account(account):
    """An account with a mock Gmail service registered in state."""
    mock_service = MagicMock()
    state.gmail_services[account] = mock_service
    return account, mock_service
