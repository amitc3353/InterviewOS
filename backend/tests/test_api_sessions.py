"""Tests for session management API endpoints."""

import json
import os
import tempfile
from unittest.mock import patch

import jwt as pyjwt
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
    with patch("backend.api.routers.sessions._get_storage", return_value=storage), \
         patch("backend.api.tokens._get_storage", return_value=storage):
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


# ---------------------------------------------------------------------------
# Fixtures for token and feedback tests
# ---------------------------------------------------------------------------

_TEST_API_KEY = "test-api-key"
_TEST_API_SECRET = "test-secret-that-is-long-enough-for-hs256-signing-key-padding"


@pytest.fixture
def client_with_livekit(storage: SessionStorage):
    """Create a test client with isolated storage and LiveKit env vars."""
    app = create_app()
    env_vars = {
        "LIVEKIT_API_KEY": _TEST_API_KEY,
        "LIVEKIT_API_SECRET": _TEST_API_SECRET,
    }
    with patch("backend.api.routers.sessions._get_storage", return_value=storage), \
         patch("backend.api.tokens._get_storage", return_value=storage), \
         patch.dict(os.environ, env_vars):
        yield TestClient(app)


@pytest.fixture
def tmp_scorecards_dir():
    """Create a temporary directory for scorecard files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_scorecard_data() -> dict:
    """Return sample scorecard data matching FeedbackResponse schema."""
    return {
        "session_id": "test-session-abc",
        "scenario": "Design a URL shortener",
        "dimensions": {
            "system_architecture": {
                "dimension": "system_architecture",
                "score": 4,
                "label": "Strong",
                "rationale": "Demonstrated solid architecture with clear component separation.",
                "strengths": ["Clean API design", "Good use of caching"],
                "gaps": ["Could explore more storage options"],
            },
            "technical_depth": {
                "dimension": "technical_depth",
                "score": 3,
                "label": "Solid",
                "rationale": "Showed adequate depth on hashing and encoding.",
                "strengths": ["Understood base62 encoding"],
                "gaps": ["Missing collision handling details"],
            },
            "scalability_reliability": {
                "dimension": "scalability_reliability",
                "score": 4,
                "label": "Strong",
                "rationale": "Good discussion of horizontal scaling and CDN usage.",
                "strengths": ["CDN for reads", "Database sharding strategy"],
                "gaps": ["No mention of circuit breakers"],
            },
            "communication": {
                "dimension": "communication",
                "score": 5,
                "label": "Exceptional",
                "rationale": "Clear, structured communication throughout.",
                "strengths": ["Proactive clarification", "Visual diagrams"],
                "gaps": [],
            },
            "requirements_gathering": {
                "dimension": "requirements_gathering",
                "score": 3,
                "label": "Solid",
                "rationale": "Asked relevant questions about scale and constraints.",
                "strengths": ["Identified key traffic patterns"],
                "gaps": ["Missed analytics requirements"],
            },
        },
        "overall_score": 3.8,
        "hire_signal": "Lean Yes",
        "narrative": "Strong candidate with solid architecture skills. Could deepen failure mode analysis.",
        "locked_constraints": {"database": "PostgreSQL", "cache": "Redis"},
        "total_turns": 24,
        "elapsed_minutes": 42.5,
        "generated_at": "2026-01-15T14:30:00Z",
    }


# ---------------------------------------------------------------------------
# Tests: GET /api/sessions/:id/token
# ---------------------------------------------------------------------------

def test_get_token_success(
    client_with_livekit: TestClient, storage: SessionStorage, sample_session_data: dict
):
    """GET /api/sessions/:id/token returns valid JWT with correct claims."""
    _seed_session(storage, sample_session_data)

    resp = client_with_livekit.get("/api/sessions/test-session-abc/token")
    assert resp.status_code == 200
    body = resp.json()

    assert "token" in body
    assert body["room_name"] == "interview-test1234"

    # Decode JWT and verify claims
    decoded = pyjwt.decode(body["token"], options={"verify_signature": False})
    assert decoded["iss"] == _TEST_API_KEY
    assert decoded["sub"] == "participant-test-ses"
    assert decoded["video"]["room"] == "interview-test1234"
    assert decoded["video"]["roomJoin"] is True
    assert decoded["video"]["canPublish"] is True
    assert decoded["video"]["canSubscribe"] is True


def test_get_token_session_not_found(client_with_livekit: TestClient):
    """GET /api/sessions/:id/token returns 404 for missing session."""
    resp = client_with_livekit.get("/api/sessions/nonexistent-id/token")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_token_missing_credentials(
    storage: SessionStorage, sample_session_data: dict
):
    """GET /api/sessions/:id/token returns 500 when LiveKit credentials missing."""
    _seed_session(storage, sample_session_data)
    app = create_app()
    env_vars = {"LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}
    with patch("backend.api.routers.sessions._get_storage", return_value=storage), \
         patch("backend.api.tokens._get_storage", return_value=storage), \
         patch.dict(os.environ, env_vars, clear=False):
        client = TestClient(app)
        resp = client.get("/api/sessions/test-session-abc/token")
        assert resp.status_code == 500
        assert "credentials" in resp.json()["detail"].lower()


def test_get_token_no_room_name(
    client_with_livekit: TestClient, storage: SessionStorage
):
    """GET /api/sessions/:id/token returns 400 when session has no room."""
    no_room_data = {
        "session_id": "no-room-session",
        "scenario": "Test",
        "phase": "intro",
        "locked_constraints": {},
        "conversation_history": [],
        "transcript": [],
        "metadata": {},
        "scorecard": None,
        "session_start_time": "2026-01-01T00:00:00",
        "created_at": "2026-01-01T00:00:00",
        "elapsed_seconds": 0.0,
        "total_turns": 0,
        "livekit_room_name": None,
    }
    _seed_session(storage, no_room_data)

    resp = client_with_livekit.get("/api/sessions/no-room-session/token")
    assert resp.status_code == 400
    assert "no livekit room" in resp.json()["detail"].lower()


def test_get_token_jwt_has_expiry(
    client_with_livekit: TestClient, storage: SessionStorage, sample_session_data: dict
):
    """GET /api/sessions/:id/token returns JWT with expiry claim."""
    _seed_session(storage, sample_session_data)

    resp = client_with_livekit.get("/api/sessions/test-session-abc/token")
    body = resp.json()
    decoded = pyjwt.decode(body["token"], options={"verify_signature": False})
    assert "exp" in decoded
    assert decoded["exp"] > decoded["nbf"]


# ---------------------------------------------------------------------------
# Tests: GET /api/sessions/:id/feedback
# ---------------------------------------------------------------------------

def test_get_feedback_success(
    client: TestClient,
    tmp_scorecards_dir: str,
    sample_scorecard_data: dict,
):
    """GET /api/sessions/:id/feedback returns parsed scorecard."""
    session_id = sample_scorecard_data["session_id"]
    scorecard_path = os.path.join(tmp_scorecards_dir, f"{session_id}.json")
    with open(scorecard_path, "w") as f:
        json.dump(sample_scorecard_data, f)

    with patch("backend.api.routers.sessions._get_scorecards_dir", return_value=tmp_scorecards_dir):
        resp = client.get(f"/api/sessions/{session_id}/feedback")

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["overall_score"] == 3.8
    assert body["hire_signal"] == "Lean Yes"
    assert len(body["dimensions"]) == 5
    assert body["dimensions"]["system_architecture"]["score"] == 4
    assert body["dimensions"]["communication"]["label"] == "Exceptional"
    assert body["total_turns"] == 24
    assert body["elapsed_minutes"] == 42.5


def test_get_feedback_not_found(client: TestClient, tmp_scorecards_dir: str):
    """GET /api/sessions/:id/feedback returns 404 for missing scorecard."""
    with patch("backend.api.routers.sessions._get_scorecards_dir", return_value=tmp_scorecards_dir):
        resp = client.get("/api/sessions/nonexistent-session/feedback")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_feedback_invalid_json(client: TestClient, tmp_scorecards_dir: str):
    """GET /api/sessions/:id/feedback returns 422 for corrupt scorecard JSON."""
    session_id = "corrupt-scorecard"
    scorecard_path = os.path.join(tmp_scorecards_dir, f"{session_id}.json")
    with open(scorecard_path, "w") as f:
        f.write("{not valid json!!!")

    with patch("backend.api.routers.sessions._get_scorecards_dir", return_value=tmp_scorecards_dir):
        resp = client.get(f"/api/sessions/{session_id}/feedback")

    assert resp.status_code == 422
    assert "invalid" in resp.json()["detail"].lower()


def test_get_feedback_dimensions_structure(
    client: TestClient,
    tmp_scorecards_dir: str,
    sample_scorecard_data: dict,
):
    """GET /api/sessions/:id/feedback returns all dimension fields."""
    session_id = sample_scorecard_data["session_id"]
    scorecard_path = os.path.join(tmp_scorecards_dir, f"{session_id}.json")
    with open(scorecard_path, "w") as f:
        json.dump(sample_scorecard_data, f)

    with patch("backend.api.routers.sessions._get_scorecards_dir", return_value=tmp_scorecards_dir):
        resp = client.get(f"/api/sessions/{session_id}/feedback")

    body = resp.json()
    for dim_name, dim_data in body["dimensions"].items():
        assert "dimension" in dim_data
        assert "score" in dim_data
        assert isinstance(dim_data["score"], int)
        assert 1 <= dim_data["score"] <= 5
        assert "label" in dim_data
        assert "rationale" in dim_data
        assert "strengths" in dim_data
        assert isinstance(dim_data["strengths"], list)
        assert "gaps" in dim_data
        assert isinstance(dim_data["gaps"], list)


def test_get_feedback_rejects_path_traversal(
    client: TestClient, tmp_scorecards_dir: str
):
    """GET /api/sessions/:id/feedback rejects path traversal attempts."""
    with patch("backend.api.routers.sessions._get_scorecards_dir", return_value=tmp_scorecards_dir):
        resp = client.get("/api/sessions/../../etc/passwd/feedback")
    assert resp.status_code in [400, 404, 422]
