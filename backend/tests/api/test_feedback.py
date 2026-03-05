"""Tests for feedback, state, and history listing endpoints.

Covers:
- GET /api/sessions/{id}/state — state retrieval happy path and edge cases
- GET /api/sessions/{id}/feedback — feedback retrieval with missing scorecard handling
- GET /api/sessions — history listing with multiple sessions and scorecard enrichment
"""

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
def tmp_scorecards_dir():
    """Create a temporary directory for scorecard files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def storage(tmp_storage_dir: str) -> SessionStorage:
    """Create a SessionStorage backed by a temp directory."""
    return SessionStorage(storage_dir=tmp_storage_dir)


@pytest.fixture
def client(storage: SessionStorage, tmp_scorecards_dir: str):
    """Create a test client with isolated storage and scorecards directory."""
    app = create_app()
    with patch("backend.api.routers.sessions._get_storage", return_value=storage), \
         patch("backend.api.tokens._get_storage", return_value=storage), \
         patch("backend.api.routers.sessions._get_scorecards_dir", return_value=tmp_scorecards_dir):
        yield TestClient(app)


@pytest.fixture
def sample_session_data() -> dict:
    """Return sample session data for storage seeding."""
    return {
        "session_id": "fb-test-session-001",
        "scenario": "Design a URL shortener",
        "phase": "deep_dive",
        "locked_constraints": {"database": "PostgreSQL", "cache": "Redis"},
        "conversation_history": [
            {"role": "assistant", "content": "Welcome!", "timestamp": "2026-01-15T14:00:00"},
            {"role": "user", "content": "Thanks.", "timestamp": "2026-01-15T14:00:10"},
            {"role": "assistant", "content": "Let's scope.", "timestamp": "2026-01-15T14:01:00"},
            {"role": "user", "content": "100M URLs/day.", "timestamp": "2026-01-15T14:01:15"},
        ],
        "transcript": [],
        "metadata": {"candidate_name": "Alice"},
        "scorecard": None,
        "session_start_time": "2026-01-15T14:00:00",
        "created_at": "2026-01-15T14:00:00",
        "elapsed_seconds": 300.0,
        "total_turns": 8,
        "phase_turn_count": 3,
        "livekit_room_name": "interview-fb001234",
    }


@pytest.fixture
def sample_scorecard_data() -> dict:
    """Return sample scorecard data matching FeedbackResponse schema."""
    return {
        "session_id": "fb-test-session-001",
        "scenario": "Design a URL shortener",
        "dimensions": {
            "system_architecture": {
                "dimension": "system_architecture",
                "score": 4,
                "label": "Strong",
                "rationale": "Solid component breakdown.",
                "strengths": ["Clean API design"],
                "gaps": ["Could explore more storage options"],
            },
            "technical_depth": {
                "dimension": "technical_depth",
                "score": 3,
                "label": "Solid",
                "rationale": "Adequate depth on hashing.",
                "strengths": ["Understood base62"],
                "gaps": ["Missing collision handling"],
            },
            "scalability_reliability": {
                "dimension": "scalability_reliability",
                "score": 4,
                "label": "Strong",
                "rationale": "Good horizontal scaling discussion.",
                "strengths": ["CDN for reads"],
                "gaps": ["No circuit breaker discussion"],
            },
            "communication": {
                "dimension": "communication",
                "score": 5,
                "label": "Exceptional",
                "rationale": "Clear structured communication.",
                "strengths": ["Proactive clarification"],
                "gaps": [],
            },
            "requirements_gathering": {
                "dimension": "requirements_gathering",
                "score": 3,
                "label": "Solid",
                "rationale": "Asked relevant scale questions.",
                "strengths": ["Identified traffic patterns"],
                "gaps": ["Missed analytics requirements"],
            },
        },
        "overall_score": 3.8,
        "hire_signal": "Lean Yes",
        "narrative": "Strong candidate with solid architecture skills.",
        "locked_constraints": {"database": "PostgreSQL", "cache": "Redis"},
        "total_turns": 24,
        "elapsed_minutes": 42.5,
        "generated_at": "2026-01-15T14:45:00Z",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_session(storage: SessionStorage, data: dict) -> None:
    """Write session data directly to storage."""
    storage.save(data)


def _write_scorecard(scorecards_dir: str, scorecard_data: dict) -> None:
    """Write a scorecard JSON file to the scorecards directory."""
    session_id = scorecard_data["session_id"]
    path = os.path.join(scorecards_dir, f"{session_id}.json")
    with open(path, "w") as f:
        json.dump(scorecard_data, f)


# ---------------------------------------------------------------------------
# Tests: GET /api/sessions/:id/state — state retrieval
# ---------------------------------------------------------------------------

class TestStateRetrieval:
    """Tests for the session state retrieval endpoint."""

    def test_state_returns_phase_and_constraints(
        self,
        client: TestClient,
        storage: SessionStorage,
        sample_session_data: dict,
    ):
        """State endpoint returns phase, turn_count, elapsed_seconds, locked_constraints."""
        _seed_session(storage, sample_session_data)

        resp = client.get("/api/sessions/fb-test-session-001/state")
        assert resp.status_code == 200
        body = resp.json()

        assert body["phase"] == "deep_dive"
        assert body["turn_count"] == 8
        assert body["elapsed_seconds"] == 300.0
        assert body["locked_constraints"] == {"database": "PostgreSQL", "cache": "Redis"}

    def test_state_returns_conversation_history(
        self,
        client: TestClient,
        storage: SessionStorage,
        sample_session_data: dict,
    ):
        """State endpoint includes conversation_history."""
        _seed_session(storage, sample_session_data)

        resp = client.get("/api/sessions/fb-test-session-001/state")
        body = resp.json()

        assert len(body["conversation_history"]) == 4
        assert body["conversation_history"][0]["role"] == "assistant"
        assert body["conversation_history"][1]["role"] == "user"

    def test_state_not_found_returns_404(self, client: TestClient):
        """State endpoint returns 404 for nonexistent session."""
        resp = client.get("/api/sessions/nonexistent-id/state")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_state_for_freshly_created_session(self, client: TestClient):
        """State endpoint returns default values for a newly created session."""
        create_resp = client.post(
            "/api/sessions",
            json={"scenario": "Design a payment gateway"},
        )
        session_id = create_resp.json()["session_id"]

        resp = client.get(f"/api/sessions/{session_id}/state")
        assert resp.status_code == 200
        body = resp.json()

        assert body["phase"] == "intro"
        assert body["turn_count"] == 0
        assert body["elapsed_seconds"] == 0.0
        assert body["locked_constraints"] == {}
        assert body["conversation_history"] == []

    def test_state_rejects_path_traversal(self, client: TestClient):
        """State endpoint rejects path traversal attempts."""
        resp = client.get("/api/sessions/../../etc/passwd/state")
        assert resp.status_code in [400, 404, 422]

    def test_state_returns_phase_turn_count(
        self,
        client: TestClient,
        storage: SessionStorage,
        sample_session_data: dict,
    ):
        """State endpoint includes phase_turn_count field."""
        _seed_session(storage, sample_session_data)

        resp = client.get("/api/sessions/fb-test-session-001/state")
        body = resp.json()
        assert body["phase_turn_count"] == 3


# ---------------------------------------------------------------------------
# Tests: GET /api/sessions/:id/feedback — feedback retrieval
# ---------------------------------------------------------------------------

class TestFeedbackRetrieval:
    """Tests for the session feedback retrieval endpoint."""

    def test_feedback_returns_five_dimensions(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_session_data: dict,
        sample_scorecard_data: dict,
    ):
        """Feedback endpoint returns all 5 dimension scores with labels."""
        _seed_session(storage, sample_session_data)
        _write_scorecard(tmp_scorecards_dir, sample_scorecard_data)

        resp = client.get("/api/sessions/fb-test-session-001/feedback")
        assert resp.status_code == 200
        body = resp.json()

        assert len(body["dimensions"]) == 5
        expected_dims = {
            "system_architecture",
            "technical_depth",
            "scalability_reliability",
            "communication",
            "requirements_gathering",
        }
        assert set(body["dimensions"].keys()) == expected_dims

    def test_feedback_dimension_structure(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_session_data: dict,
        sample_scorecard_data: dict,
    ):
        """Each dimension has score, label, rationale, strengths, gaps."""
        _seed_session(storage, sample_session_data)
        _write_scorecard(tmp_scorecards_dir, sample_scorecard_data)

        resp = client.get("/api/sessions/fb-test-session-001/feedback")
        body = resp.json()

        for dim_name, dim_data in body["dimensions"].items():
            assert "score" in dim_data, f"Missing score in {dim_name}"
            assert isinstance(dim_data["score"], int)
            assert 1 <= dim_data["score"] <= 5, f"Score out of range in {dim_name}"
            assert "label" in dim_data, f"Missing label in {dim_name}"
            assert "rationale" in dim_data, f"Missing rationale in {dim_name}"
            assert isinstance(dim_data["strengths"], list)
            assert isinstance(dim_data["gaps"], list)

    def test_feedback_overall_score_and_hire_signal(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_session_data: dict,
        sample_scorecard_data: dict,
    ):
        """Feedback returns overall_score and hire_signal."""
        _seed_session(storage, sample_session_data)
        _write_scorecard(tmp_scorecards_dir, sample_scorecard_data)

        resp = client.get("/api/sessions/fb-test-session-001/feedback")
        body = resp.json()

        assert body["overall_score"] == 3.8
        assert body["hire_signal"] == "Lean Yes"
        assert body["total_turns"] == 24
        assert body["elapsed_minutes"] == 42.5

    def test_feedback_missing_scorecard_returns_404(
        self, client: TestClient,
    ):
        """Feedback returns 404 when no scorecard exists for the session."""
        # Create session but no scorecard
        create_resp = client.post(
            "/api/sessions",
            json={"scenario": "Design a chat system"},
        )
        session_id = create_resp.json()["session_id"]

        resp = client.get(f"/api/sessions/{session_id}/feedback")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_feedback_corrupt_scorecard_returns_422(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_session_data: dict,
    ):
        """Feedback returns 422 when scorecard JSON is corrupt."""
        _seed_session(storage, sample_session_data)
        # Write corrupt JSON
        scorecard_path = os.path.join(
            tmp_scorecards_dir, f"{sample_session_data['session_id']}.json"
        )
        with open(scorecard_path, "w") as f:
            f.write("{invalid json!!!")

        resp = client.get(f"/api/sessions/{sample_session_data['session_id']}/feedback")
        assert resp.status_code == 422
        assert "invalid" in resp.json()["detail"].lower()

    def test_feedback_nonexistent_session_returns_404(self, client: TestClient):
        """Feedback returns 404 for a completely nonexistent session ID."""
        resp = client.get("/api/sessions/totally-unknown-session/feedback")
        assert resp.status_code == 404

    def test_feedback_rejects_path_traversal(self, client: TestClient):
        """Feedback endpoint rejects path traversal attempts."""
        resp = client.get("/api/sessions/../../etc/passwd/feedback")
        assert resp.status_code in [400, 404, 422]

    def test_feedback_includes_narrative(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_session_data: dict,
        sample_scorecard_data: dict,
    ):
        """Feedback includes narrative summary."""
        _seed_session(storage, sample_session_data)
        _write_scorecard(tmp_scorecards_dir, sample_scorecard_data)

        resp = client.get("/api/sessions/fb-test-session-001/feedback")
        body = resp.json()
        assert body["narrative"] == "Strong candidate with solid architecture skills."


# ---------------------------------------------------------------------------
# Tests: GET /api/sessions — history listing with scorecard enrichment
# ---------------------------------------------------------------------------

class TestHistoryListing:
    """Tests for the session history listing endpoint with scorecard data."""

    def test_list_empty_returns_zero(self, client: TestClient):
        """Empty storage returns empty session list."""
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sessions"] == []
        assert body["total"] == 0

    def test_list_multiple_sessions(
        self, client: TestClient, storage: SessionStorage
    ):
        """Lists multiple sessions with correct metadata."""
        # Seed three sessions with different dates
        for i, (scenario, date) in enumerate([
            ("Design a URL shortener", "2026-01-01T10:00:00"),
            ("Design a chat system", "2026-01-02T10:00:00"),
            ("Design a rate limiter", "2026-01-03T10:00:00"),
        ]):
            storage.save({
                "session_id": f"hist-session-{i}",
                "scenario": scenario,
                "phase": "intro",
                "locked_constraints": {},
                "conversation_history": [],
                "transcript": [],
                "metadata": {},
                "scorecard": None,
                "session_start_time": date,
                "created_at": date,
                "elapsed_seconds": 0.0,
                "total_turns": 0,
                "livekit_room_name": f"interview-hist{i}",
            })

        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["sessions"]) == 3

        # Verify sessions are sorted newest first
        assert body["sessions"][0]["session_id"] == "hist-session-2"
        assert body["sessions"][1]["session_id"] == "hist-session-1"
        assert body["sessions"][2]["session_id"] == "hist-session-0"

    def test_list_includes_scorecard_data(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
    ):
        """Sessions with scorecards include overall_score and hire_signal."""
        # Create a session
        session_data = {
            "session_id": "scored-session-1",
            "scenario": "Design a URL shortener",
            "phase": "wrap",
            "locked_constraints": {"database": "PostgreSQL"},
            "conversation_history": [],
            "transcript": [],
            "metadata": {},
            "scorecard": None,
            "session_start_time": "2026-01-15T14:00:00",
            "created_at": "2026-01-15T14:00:00",
            "elapsed_seconds": 2550.0,
            "total_turns": 24,
            "livekit_room_name": "interview-scored1",
        }
        storage.save(session_data)

        # Write a scorecard for it
        scorecard = {
            "session_id": "scored-session-1",
            "overall_score": 4.2,
            "hire_signal": "Strong Yes",
        }
        scorecard_path = os.path.join(tmp_scorecards_dir, "scored-session-1.json")
        with open(scorecard_path, "w") as f:
            json.dump(scorecard, f)

        resp = client.get("/api/sessions")
        body = resp.json()
        assert body["total"] == 1

        session = body["sessions"][0]
        assert session["overall_score"] == 4.2
        assert session["hire_signal"] == "Strong Yes"

    def test_list_without_scorecard_has_null_scores(
        self, client: TestClient, storage: SessionStorage,
    ):
        """Sessions without scorecards have null overall_score and hire_signal."""
        storage.save({
            "session_id": "no-score-session",
            "scenario": "Design a chat system",
            "phase": "intro",
            "locked_constraints": {},
            "conversation_history": [],
            "transcript": [],
            "metadata": {},
            "scorecard": None,
            "session_start_time": "2026-01-10T10:00:00",
            "created_at": "2026-01-10T10:00:00",
            "elapsed_seconds": 0.0,
            "total_turns": 0,
            "livekit_room_name": "interview-noscore",
        })

        resp = client.get("/api/sessions")
        body = resp.json()
        session = body["sessions"][0]
        assert session["overall_score"] is None
        assert session["hire_signal"] is None

    def test_list_mixed_scored_and_unscored(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
    ):
        """List correctly shows scores for completed sessions and null for in-progress."""
        # Session with scorecard
        storage.save({
            "session_id": "completed-sess",
            "scenario": "Design a URL shortener",
            "phase": "wrap",
            "locked_constraints": {},
            "conversation_history": [],
            "transcript": [],
            "metadata": {},
            "scorecard": None,
            "session_start_time": "2026-01-15T14:00:00",
            "created_at": "2026-01-15T14:00:00",
            "elapsed_seconds": 2550.0,
            "total_turns": 24,
            "livekit_room_name": "interview-comp",
        })
        scorecard_path = os.path.join(tmp_scorecards_dir, "completed-sess.json")
        with open(scorecard_path, "w") as f:
            json.dump({"overall_score": 3.5, "hire_signal": "Lean Yes"}, f)

        # Session without scorecard
        storage.save({
            "session_id": "active-sess",
            "scenario": "Design a chat system",
            "phase": "scope",
            "locked_constraints": {},
            "conversation_history": [],
            "transcript": [],
            "metadata": {},
            "scorecard": None,
            "session_start_time": "2026-01-16T10:00:00",
            "created_at": "2026-01-16T10:00:00",
            "elapsed_seconds": 120.0,
            "total_turns": 4,
            "livekit_room_name": "interview-active",
        })

        resp = client.get("/api/sessions")
        body = resp.json()
        assert body["total"] == 2

        sessions_by_id = {s["session_id"]: s for s in body["sessions"]}
        assert sessions_by_id["completed-sess"]["overall_score"] == 3.5
        assert sessions_by_id["completed-sess"]["hire_signal"] == "Lean Yes"
        assert sessions_by_id["active-sess"]["overall_score"] is None
        assert sessions_by_id["active-sess"]["hire_signal"] is None

    def test_list_ignores_corrupt_scorecard(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
    ):
        """Corrupt scorecard file does not break the listing — scores show as null."""
        storage.save({
            "session_id": "corrupt-score-sess",
            "scenario": "Design a rate limiter",
            "phase": "wrap",
            "locked_constraints": {},
            "conversation_history": [],
            "transcript": [],
            "metadata": {},
            "scorecard": None,
            "session_start_time": "2026-01-20T10:00:00",
            "created_at": "2026-01-20T10:00:00",
            "elapsed_seconds": 2700.0,
            "total_turns": 26,
            "livekit_room_name": "interview-corrupt",
        })

        # Write corrupt scorecard
        scorecard_path = os.path.join(tmp_scorecards_dir, "corrupt-score-sess.json")
        with open(scorecard_path, "w") as f:
            f.write("not valid json{{{")

        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        session = body["sessions"][0]
        assert session["session_id"] == "corrupt-score-sess"
        # Corrupt scorecard should be silently skipped
        assert session["overall_score"] is None
        assert session["hire_signal"] is None

    def test_list_sessions_contain_scenario_and_dates(
        self, client: TestClient, storage: SessionStorage
    ):
        """Each listed session includes scenario, created_at, and elapsed_seconds."""
        storage.save({
            "session_id": "meta-session",
            "scenario": "Design a notification system",
            "phase": "architecture",
            "locked_constraints": {"queue": "SQS"},
            "conversation_history": [],
            "transcript": [],
            "metadata": {"candidate_name": "Bob"},
            "scorecard": None,
            "session_start_time": "2026-02-01T09:00:00",
            "created_at": "2026-02-01T09:00:00",
            "elapsed_seconds": 600.0,
            "total_turns": 10,
            "livekit_room_name": "interview-meta",
        })

        resp = client.get("/api/sessions")
        body = resp.json()
        session = body["sessions"][0]

        assert session["scenario"] == "Design a notification system"
        assert session["created_at"] == "2026-02-01T09:00:00"
        assert session["elapsed_seconds"] == 600.0
        assert session["total_turns"] == 10
        assert session["phase"] == "architecture"
        assert session["locked_constraints"] == {"queue": "SQS"}
