"""Tests for session management API endpoints."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.server import create_app
from backend.api.storage import SessionStorage


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
    with patch("backend.api.routers.sessions._get_storage", return_value=storage):
        yield TestClient(app)


@pytest.fixture
def sample_session_data() -> dict:
    """Return sample session data for storage seeding."""
    return {
        "session_id": "test-session-abc",
        "scenario": "Design a URL shortener",
        "phase": "scope",
        "locked_constraints": {"database": "PostgreSQL"},
        "conversation_history": [
            {"role": "assistant", "content": "Hello", "timestamp": "2026-01-01T00:00:00"},
            {"role": "user", "content": "Hi", "timestamp": "2026-01-01T00:00:05"},
        ],
        "transcript": [],
        "metadata": {"candidate_name": "Alice"},
        "scorecard": None,
        "session_start_time": "2026-01-01T00:00:00",
        "created_at": "2026-01-01T00:00:00",
        "elapsed_seconds": 120.5,
        "total_turns": 3,
        "phase_turn_count": 1,
        "livekit_room_name": "interview-test1234",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_session(storage: SessionStorage, data: dict) -> None:
    """Write session data directly to storage."""
    storage.save(data)


# ---------------------------------------------------------------------------
# Tests: Health check
# ---------------------------------------------------------------------------

def test_health_check(client: TestClient):
    """GET /health returns status ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Tests: POST /api/sessions
# ---------------------------------------------------------------------------

def test_create_session_success(client: TestClient):
    """POST /api/sessions creates a new session and returns 201."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "Design a URL shortener"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["scenario"] == "Design a URL shortener"
    assert body["phase"] == "intro"
    assert body["locked_constraints"] == {}
    assert body["total_turns"] == 0
    assert "session_id" in body
    assert body["session_id"]  # not empty
    assert "created_at" in body


def test_create_session_with_candidate_name(client: TestClient):
    """POST /api/sessions accepts optional candidate_name."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "Design a chat system", "candidate_name": "Bob"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["scenario"] == "Design a chat system"


def test_create_session_empty_scenario_rejected(client: TestClient):
    """POST /api/sessions rejects empty scenario."""
    resp = client.post("/api/sessions", json={"scenario": ""})
    assert resp.status_code == 422  # Validation error


def test_create_session_missing_scenario_rejected(client: TestClient):
    """POST /api/sessions rejects missing scenario field."""
    resp = client.post("/api/sessions", json={})
    assert resp.status_code == 422


def test_create_session_persists_to_storage(client: TestClient, storage: SessionStorage):
    """Created session is persisted and can be loaded from storage."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "Design a rate limiter"},
    )
    session_id = resp.json()["session_id"]

    loaded = storage.load(session_id)
    assert loaded is not None
    assert loaded["scenario"] == "Design a rate limiter"
    assert loaded["phase"] == "intro"


def test_create_session_returns_livekit_room_name(client: TestClient):
    """Created session includes a livekit_room_name."""
    resp = client.post(
        "/api/sessions",
        json={"scenario": "Design a URL shortener"},
    )
    body = resp.json()
    assert body["livekit_room_name"] is not None
    assert body["livekit_room_name"].startswith("interview-")


# ---------------------------------------------------------------------------
# Tests: GET /api/sessions
# ---------------------------------------------------------------------------

def test_list_sessions_empty(client: TestClient):
    """GET /api/sessions returns empty list when no sessions exist."""
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions"] == []
    assert body["total"] == 0


def test_list_sessions_returns_created_sessions(client: TestClient):
    """GET /api/sessions returns previously created sessions."""
    # Create two sessions
    client.post("/api/sessions", json={"scenario": "Design a URL shortener"})
    client.post("/api/sessions", json={"scenario": "Design a chat system"})

    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["sessions"]) == 2

    scenarios = {s["scenario"] for s in body["sessions"]}
    assert "Design a URL shortener" in scenarios
    assert "Design a chat system" in scenarios


def test_list_sessions_includes_seeded_data(
    client: TestClient, storage: SessionStorage, sample_session_data: dict
):
    """GET /api/sessions includes sessions seeded directly in storage."""
    _seed_session(storage, sample_session_data)

    resp = client.get("/api/sessions")
    body = resp.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == "test-session-abc"
    assert body["sessions"][0]["phase"] == "scope"


# ---------------------------------------------------------------------------
# Tests: GET /api/sessions/:id/state
# ---------------------------------------------------------------------------

def test_get_session_state_success(
    client: TestClient, storage: SessionStorage, sample_session_data: dict
):
    """GET /api/sessions/:id/state returns session state."""
    _seed_session(storage, sample_session_data)

    resp = client.get("/api/sessions/test-session-abc/state")
    assert resp.status_code == 200
    body = resp.json()

    assert body["session_id"] == "test-session-abc"
    assert body["phase"] == "scope"
    assert body["locked_constraints"] == {"database": "PostgreSQL"}
    assert body["turn_count"] == 3
    assert body["elapsed_seconds"] == 120.5
    assert len(body["conversation_history"]) == 2


def test_get_session_state_not_found(client: TestClient):
    """GET /api/sessions/:id/state returns 404 for missing session."""
    resp = client.get("/api/sessions/nonexistent-id/state")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_session_state_after_creation(client: TestClient):
    """GET /api/sessions/:id/state works for newly created sessions."""
    create_resp = client.post(
        "/api/sessions",
        json={"scenario": "Design a payment gateway"},
    )
    session_id = create_resp.json()["session_id"]

    state_resp = client.get(f"/api/sessions/{session_id}/state")
    assert state_resp.status_code == 200
    body = state_resp.json()

    assert body["session_id"] == session_id
    assert body["phase"] == "intro"
    assert body["locked_constraints"] == {}
    assert body["turn_count"] == 0
    assert body["conversation_history"] == []


# ---------------------------------------------------------------------------
# Tests: Storage layer
# ---------------------------------------------------------------------------

def test_storage_save_and_load(storage: SessionStorage):
    """SessionStorage round-trips data correctly."""
    data = {"session_id": "s1", "scenario": "test", "created_at": "2026-01-01"}
    storage.save(data)

    loaded = storage.load("s1")
    assert loaded is not None
    assert loaded["session_id"] == "s1"
    assert loaded["scenario"] == "test"


def test_storage_load_nonexistent(storage: SessionStorage):
    """SessionStorage.load returns None for missing session."""
    assert storage.load("does-not-exist") is None


def test_storage_list_sessions_sorted(storage: SessionStorage):
    """SessionStorage.list_sessions returns newest first."""
    storage.save({"session_id": "old", "created_at": "2026-01-01T00:00:00"})
    storage.save({"session_id": "new", "created_at": "2026-02-01T00:00:00"})

    sessions = storage.list_sessions()
    assert len(sessions) == 2
    assert sessions[0]["session_id"] == "new"
    assert sessions[1]["session_id"] == "old"


def test_storage_delete(storage: SessionStorage):
    """SessionStorage.delete removes the session file."""
    storage.save({"session_id": "del-me", "created_at": "2026-01-01"})
    assert storage.load("del-me") is not None

    deleted = storage.delete("del-me")
    assert deleted is True
    assert storage.load("del-me") is None


def test_storage_delete_nonexistent(storage: SessionStorage):
    """SessionStorage.delete returns False for missing session."""
    assert storage.delete("does-not-exist") is False


def test_storage_handles_corrupt_json(storage: SessionStorage):
    """SessionStorage gracefully handles corrupt JSON files."""
    # Write invalid JSON
    bad_path = os.path.join(storage.storage_dir, "corrupt.json")
    with open(bad_path, "w") as f:
        f.write("{invalid json")

    # load should return None
    assert storage.load("corrupt") is None

    # list_sessions should skip the corrupt file
    storage.save({"session_id": "valid", "created_at": "2026-01-01"})
    sessions = storage.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "valid"


# ---------------------------------------------------------------------------
# Tests: Security — path traversal prevention
# ---------------------------------------------------------------------------

def test_get_session_state_rejects_path_traversal(client: TestClient):
    """GET /api/sessions/:id/state rejects path traversal attempts."""
    resp = client.get("/api/sessions/../../etc/passwd/state")
    assert resp.status_code in [400, 404, 422]


def test_storage_rejects_path_traversal_in_load(storage: SessionStorage):
    """SessionStorage.load raises ValueError for path traversal IDs."""
    with pytest.raises(ValueError, match="Invalid session ID format"):
        storage.load("../../etc/passwd")


def test_storage_rejects_path_traversal_in_save(storage: SessionStorage):
    """SessionStorage.save raises ValueError for path traversal IDs."""
    with pytest.raises(ValueError, match="Invalid session ID format"):
        storage.save({"session_id": "../malicious"})


def test_storage_rejects_path_traversal_in_delete(storage: SessionStorage):
    """SessionStorage.delete raises ValueError for path traversal IDs."""
    with pytest.raises(ValueError, match="Invalid session ID format"):
        storage.delete("../../../etc/shadow")


def test_storage_rejects_empty_session_id(storage: SessionStorage):
    """SessionStorage rejects empty string session IDs."""
    with pytest.raises(ValueError, match="Invalid session ID format"):
        storage.load("")


def test_storage_accepts_valid_uuid_session_id(storage: SessionStorage):
    """SessionStorage accepts normal UUID-style session IDs."""
    # Should not raise
    result = storage.load("550e8400-e29b-41d4-a716-446655440000")
    assert result is None  # Not found, but no ValueError
