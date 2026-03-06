"""Tests for security audit — config validation, API key masking, API input sanitization.

15 tests, zero network calls.
"""

import json
import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.server import create_app
from backend.api.storage import SessionStorage
from backend.config import AgentConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_storage_dir():
    """Create a temporary directory for session storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def storage(tmp_storage_dir: str) -> SessionStorage:
    """Create a SessionStorage backed by a temp directory."""
    return SessionStorage(storage_dir=tmp_storage_dir)


@pytest.fixture
def client(storage: SessionStorage):
    """Create a test client with isolated storage."""
    app = create_app()
    with patch("backend.api.routers.sessions._get_storage", return_value=storage), \
         patch("backend.api.tokens._get_storage", return_value=storage):
        yield TestClient(app)


# ---------------------------------------------------------------------------
# Tests: AgentConfig — placeholder detection
# ---------------------------------------------------------------------------

def test_config_rejects_placeholder_api_keys():
    """Config validation rejects placeholder API key values."""
    config = AgentConfig(
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key="your_livekit_api_key_here",
        livekit_api_secret="your_secret_here",
        deepgram_api_key="your_deepgram_api_key_here",
        anthropic_api_key="your_anthropic_api_key_here",
        openai_api_key="your_openai_api_key_here",
        cartesia_api_key="your_cartesia_api_key_here",
    )
    assert config.validate() is False


def test_config_rejects_empty_api_keys():
    """Config validation rejects empty API key values."""
    config = AgentConfig(
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key="real-key",
        livekit_api_secret="real-secret",
        deepgram_api_key="",
        anthropic_api_key="real-key",
        openai_api_key="real-key",
        cartesia_api_key="real-key",
    )
    assert config.validate() is False


def test_config_accepts_real_api_keys():
    """Config validation accepts non-placeholder API key values."""
    config = AgentConfig(
        livekit_url="wss://myproject.livekit.cloud",
        livekit_api_key="APImykey123",
        livekit_api_secret="secretvalue456",
        deepgram_api_key="dg_key_abc123",
        anthropic_api_key="sk-ant-abc123",
        openai_api_key="sk-proj-abc123",
        cartesia_api_key="ct_abc123",
    )
    assert config.validate() is True


def test_is_placeholder_detection():
    """Placeholder patterns are correctly detected."""
    assert AgentConfig._is_placeholder("your_api_key_here") is True
    assert AgentConfig._is_placeholder("sk-xxx") is True
    assert AgentConfig._is_placeholder("CHANGEME") is True
    assert AgentConfig._is_placeholder("replace_me") is True
    assert AgentConfig._is_placeholder("TODO") is True
    assert AgentConfig._is_placeholder("placeholder_value") is True
    # Real values should not be detected as placeholders
    assert AgentConfig._is_placeholder("sk-ant-api03-abc123def456") is False
    assert AgentConfig._is_placeholder("dg_1234567890abcdef") is False


# ---------------------------------------------------------------------------
# Tests: AgentConfig — secret masking
# ---------------------------------------------------------------------------

def test_mask_secret_shows_last_four():
    """mask_secret shows only last 4 characters."""
    assert AgentConfig.mask_secret("sk-ant-api03-abc123") == "****c123"


def test_mask_secret_short_value():
    """mask_secret masks very short values completely."""
    assert AgentConfig.mask_secret("abc") == "****"


def test_mask_secret_empty():
    """mask_secret handles empty string."""
    assert AgentConfig.mask_secret("") == "****"


# ---------------------------------------------------------------------------
# Tests: Config loads from env vars only (no hardcoded secrets)
# ---------------------------------------------------------------------------

def test_config_from_env_no_hardcoded_secrets():
    """AgentConfig.from_env() loads all secrets from environment only."""
    env_vars = {
        "LIVEKIT_URL": "wss://test.livekit.cloud",
        "LIVEKIT_API_KEY": "test-api-key",
        "LIVEKIT_API_SECRET": "test-api-secret",
        "DEEPGRAM_API_KEY": "test-deepgram-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "OPENAI_API_KEY": "test-openai-key",
        "CARTESIA_API_KEY": "test-cartesia-key",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        config = AgentConfig.from_env()

    assert config.livekit_url == "wss://test.livekit.cloud"
    assert config.livekit_api_key == "test-api-key"
    assert config.deepgram_api_key == "test-deepgram-key"
    assert config.anthropic_api_key == "test-anthropic-key"
    assert config.cartesia_api_key == "test-cartesia-key"


def test_config_from_env_missing_vars_default_empty():
    """AgentConfig.from_env() defaults to empty string for missing keys."""
    with patch.dict(os.environ, {}, clear=True):
        config = AgentConfig.from_env()

    assert config.livekit_url == ""
    assert config.livekit_api_key == ""
    assert config.deepgram_api_key == ""


# ---------------------------------------------------------------------------
# Tests: API input sanitization
# ---------------------------------------------------------------------------

def test_api_rejects_path_traversal_scenario(client: TestClient):
    """POST /api/sessions rejects scenario with path traversal."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "../../etc/passwd"},
    )
    assert resp.status_code == 422


def test_api_rejects_script_injection_scenario(client: TestClient):
    """POST /api/sessions rejects scenario with script tags."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "<script>alert('xss')</script>"},
    )
    assert resp.status_code == 422


def test_api_accepts_valid_scenario(client: TestClient):
    """POST /api/sessions accepts valid scenario names."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "Design a URL shortener"},
    )
    assert resp.status_code == 201
    assert resp.json()["scenario"] == "Design a URL shortener"


def test_api_accepts_scenario_with_hyphens(client: TestClient):
    """POST /api/sessions accepts scenario with hyphens and parentheses."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "E-commerce inventory (v2)"},
    )
    assert resp.status_code == 201


def test_api_rejects_candidate_name_injection(client: TestClient):
    """POST /api/sessions rejects candidate name with script tags."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "Design a cache", "candidate_name": "<img onerror=alert(1)>"},
    )
    assert resp.status_code == 422


def test_api_accepts_valid_candidate_name(client: TestClient):
    """POST /api/sessions accepts valid candidate name."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "Design a cache", "candidate_name": "Dr. O'Brien-Smith"},
    )
    assert resp.status_code == 201
