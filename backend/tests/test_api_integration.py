"""End-to-end integration tests for the InterviewOS API.

Tests the complete interview lifecycle:
1) Create a session
2) Get a LiveKit token
3) Verify session state (phase=intro)
4) Simulate interview completion
5) Get feedback scorecard
"""

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
# Test configuration
# ---------------------------------------------------------------------------

_TEST_API_KEY = "integration-test-api-key"
_TEST_API_SECRET = "integration-test-secret-long-enough-for-hs256-signing-key-pad"


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
def client(storage: SessionStorage):
    """Create a test client with isolated storage and LiveKit credentials."""
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
def sample_scorecard() -> dict:
    """Return a complete scorecard matching the FeedbackResponse schema."""
    return {
        "session_id": "",  # Filled in by test
        "scenario": "Design a URL shortener",
        "dimensions": {
            "system_architecture": {
                "dimension": "system_architecture",
                "score": 4,
                "label": "Strong",
                "rationale": "Solid component breakdown with clear separation of concerns.",
                "strengths": ["Clean API design", "Good caching strategy"],
                "gaps": ["Could explore more storage options"],
            },
            "technical_depth": {
                "dimension": "technical_depth",
                "score": 3,
                "label": "Solid",
                "rationale": "Adequate depth on hashing and encoding schemes.",
                "strengths": ["Understood base62 encoding"],
                "gaps": ["Missing collision handling details"],
            },
            "scalability_reliability": {
                "dimension": "scalability_reliability",
                "score": 4,
                "label": "Strong",
                "rationale": "Good horizontal scaling discussion and CDN usage.",
                "strengths": ["CDN for reads", "Database sharding strategy"],
                "gaps": ["No circuit breaker discussion"],
            },
            "communication": {
                "dimension": "communication",
                "score": 5,
                "label": "Exceptional",
                "rationale": "Clear, structured communication throughout the interview.",
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
        "narrative": "Strong candidate with solid architecture skills.",
        "locked_constraints": {"database": "PostgreSQL", "cache": "Redis"},
        "total_turns": 24,
        "elapsed_minutes": 42.5,
        "generated_at": "2026-01-15T14:30:00Z",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simulate_interview_completion(
    storage: SessionStorage,
    session_id: str,
    scorecards_dir: str,
    scorecard_data: dict,
) -> None:
    """
    Simulate a completed interview by updating session state and writing a scorecard.

    Mutates session storage to reflect a completed interview with conversation
    history, phase=wrap, and writes the scorecard JSON to the scorecards directory.
    """
    session_data = storage.load(session_id)
    assert session_data is not None, f"Session {session_id} not found in storage"

    # Update session to reflect completed interview
    session_data["phase"] = "wrap"
    session_data["total_turns"] = 24
    session_data["phase_turn_count"] = 2
    session_data["elapsed_seconds"] = 2550.0
    session_data["locked_constraints"] = {
        "database": "PostgreSQL",
        "cache": "Redis",
    }
    session_data["conversation_history"] = [
        {
            "role": "assistant",
            "content": "Welcome! Let's design a URL shortener.",
            "timestamp": "2026-01-15T14:00:00",
        },
        {
            "role": "user",
            "content": "Sure, let me start with the requirements.",
            "timestamp": "2026-01-15T14:00:10",
        },
        {
            "role": "assistant",
            "content": "Great, what scale are we designing for?",
            "timestamp": "2026-01-15T14:00:15",
        },
        {
            "role": "user",
            "content": "Let's target 100M URLs per day.",
            "timestamp": "2026-01-15T14:00:30",
        },
        {
            "role": "assistant",
            "content": "Thank you for the discussion. Let's wrap up.",
            "timestamp": "2026-01-15T14:42:30",
        },
    ]
    storage.save(session_data)

    # Write scorecard file
    scorecard_data["session_id"] = session_id
    scorecard_path = os.path.join(scorecards_dir, f"{session_id}.json")
    with open(scorecard_path, "w") as f:
        json.dump(scorecard_data, f)


# ---------------------------------------------------------------------------
# Tests: Full interview lifecycle (end-to-end)
# ---------------------------------------------------------------------------

class TestInterviewLifecycle:
    """End-to-end tests for the complete interview lifecycle."""

    def test_full_lifecycle(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_scorecard: dict,
    ):
        """
        Complete interview lifecycle: create → token → state → complete → feedback.

        Steps:
        1. POST /api/sessions to create a session
        2. GET /api/sessions/:id/token to get a LiveKit token
        3. GET /api/sessions/:id/state to verify initial phase=intro
        4. Simulate interview completion (update storage + write scorecard)
        5. GET /api/sessions/:id/feedback to verify scorecard
        """
        # Step 1: Create session
        create_resp = client.post(
            "/api/sessions",
            json={"scenario": "Design a URL shortener", "candidate_name": "Alice"},
        )
        assert create_resp.status_code == 201
        session = create_resp.json()
        session_id = session["session_id"]
        assert session["scenario"] == "Design a URL shortener"
        assert session["phase"] == "intro"
        assert session["total_turns"] == 0
        assert session["livekit_room_name"] is not None

        # Step 2: Get LiveKit token
        token_resp = client.get(f"/api/sessions/{session_id}/token")
        assert token_resp.status_code == 200
        token_body = token_resp.json()
        assert "token" in token_body
        assert token_body["room_name"] == session["livekit_room_name"]

        # Verify JWT claims
        decoded = pyjwt.decode(token_body["token"], options={"verify_signature": False})
        assert decoded["iss"] == _TEST_API_KEY
        assert decoded["video"]["roomJoin"] is True
        assert decoded["video"]["canPublish"] is True

        # Step 3: Verify initial state (phase=intro)
        state_resp = client.get(f"/api/sessions/{session_id}/state")
        assert state_resp.status_code == 200
        state = state_resp.json()
        assert state["session_id"] == session_id
        assert state["phase"] == "intro"
        assert state["locked_constraints"] == {}
        assert state["turn_count"] == 0
        assert state["conversation_history"] == []

        # Step 4: Simulate interview completion
        _simulate_interview_completion(
            storage, session_id, tmp_scorecards_dir, sample_scorecard
        )

        # Verify state updated to wrap phase
        state_resp2 = client.get(f"/api/sessions/{session_id}/state")
        assert state_resp2.status_code == 200
        state2 = state_resp2.json()
        assert state2["phase"] == "wrap"
        assert state2["turn_count"] == 24
        assert state2["locked_constraints"] == {"database": "PostgreSQL", "cache": "Redis"}
        assert len(state2["conversation_history"]) == 5

        # Step 5: Get feedback scorecard
        with patch(
            "backend.api.routers.sessions._get_scorecards_dir",
            return_value=tmp_scorecards_dir,
        ):
            feedback_resp = client.get(f"/api/sessions/{session_id}/feedback")
        assert feedback_resp.status_code == 200
        feedback = feedback_resp.json()
        assert feedback["session_id"] == session_id
        assert feedback["overall_score"] == 3.8
        assert feedback["hire_signal"] == "Lean Yes"
        assert len(feedback["dimensions"]) == 5
        assert feedback["total_turns"] == 24
        assert feedback["elapsed_minutes"] == 42.5

    def test_lifecycle_session_appears_in_list(self, client: TestClient):
        """Created session appears in GET /api/sessions list."""
        # Create two sessions
        resp1 = client.post(
            "/api/sessions", json={"scenario": "Design a URL shortener"}
        )
        resp2 = client.post(
            "/api/sessions", json={"scenario": "Design a chat system"}
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201

        # List sessions
        list_resp = client.get("/api/sessions")
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert body["total"] == 2

        scenarios = {s["scenario"] for s in body["sessions"]}
        assert "Design a URL shortener" in scenarios
        assert "Design a chat system" in scenarios


# ---------------------------------------------------------------------------
# Tests: State transitions across endpoints
# ---------------------------------------------------------------------------

class TestStateTransitions:
    """Tests for verifying state consistency across API endpoints."""

    def test_state_reflects_storage_updates(
        self, client: TestClient, storage: SessionStorage
    ):
        """Session state endpoint reflects changes made directly to storage."""
        # Create session via API
        create_resp = client.post(
            "/api/sessions", json={"scenario": "Design a payment gateway"}
        )
        session_id = create_resp.json()["session_id"]

        # Directly update storage (simulating agent activity)
        data = storage.load(session_id)
        data["phase"] = "architecture"
        data["total_turns"] = 8
        data["locked_constraints"] = {"message_broker": "Kafka"}
        data["conversation_history"] = [
            {"role": "assistant", "content": "Let's discuss architecture.", "timestamp": "2026-01-15T14:05:00"},
            {"role": "user", "content": "I'll use Kafka for async processing.", "timestamp": "2026-01-15T14:05:15"},
        ]
        storage.save(data)

        # Verify state endpoint returns updated data
        state_resp = client.get(f"/api/sessions/{session_id}/state")
        assert state_resp.status_code == 200
        state = state_resp.json()
        assert state["phase"] == "architecture"
        assert state["turn_count"] == 8
        assert state["locked_constraints"] == {"message_broker": "Kafka"}
        assert len(state["conversation_history"]) == 2

    def test_multiple_sessions_independent(
        self, client: TestClient, storage: SessionStorage
    ):
        """Multiple sessions maintain independent state."""
        # Create two sessions
        resp1 = client.post(
            "/api/sessions", json={"scenario": "Design a URL shortener"}
        )
        resp2 = client.post(
            "/api/sessions", json={"scenario": "Design a chat system"}
        )
        sid1 = resp1.json()["session_id"]
        sid2 = resp2.json()["session_id"]

        # Update only the first session
        data1 = storage.load(sid1)
        data1["phase"] = "deep_dive"
        data1["total_turns"] = 15
        storage.save(data1)

        # Verify states are independent
        state1 = client.get(f"/api/sessions/{sid1}/state").json()
        state2 = client.get(f"/api/sessions/{sid2}/state").json()

        assert state1["phase"] == "deep_dive"
        assert state1["turn_count"] == 15
        assert state2["phase"] == "intro"
        assert state2["turn_count"] == 0


# ---------------------------------------------------------------------------
# Tests: Error scenarios in the lifecycle
# ---------------------------------------------------------------------------

class TestLifecycleErrors:
    """Tests for error handling during the interview lifecycle."""

    def test_token_before_session_exists(self, client: TestClient):
        """GET /api/sessions/:id/token returns 404 for nonexistent session."""
        resp = client.get("/api/sessions/nonexistent-id/token")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_state_before_session_exists(self, client: TestClient):
        """GET /api/sessions/:id/state returns 404 for nonexistent session."""
        resp = client.get("/api/sessions/nonexistent-session/state")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_feedback_before_interview_completes(
        self, client: TestClient, tmp_scorecards_dir: str
    ):
        """GET /api/sessions/:id/feedback returns 404 when no scorecard exists."""
        # Create session but don't complete the interview
        create_resp = client.post(
            "/api/sessions", json={"scenario": "Design a URL shortener"}
        )
        session_id = create_resp.json()["session_id"]

        with patch(
            "backend.api.routers.sessions._get_scorecards_dir",
            return_value=tmp_scorecards_dir,
        ):
            feedback_resp = client.get(f"/api/sessions/{session_id}/feedback")
        assert feedback_resp.status_code == 404
        assert "not found" in feedback_resp.json()["detail"].lower()

    def test_feedback_with_corrupt_scorecard(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
    ):
        """GET /api/sessions/:id/feedback returns 422 for corrupt scorecard JSON."""
        create_resp = client.post(
            "/api/sessions", json={"scenario": "Design a URL shortener"}
        )
        session_id = create_resp.json()["session_id"]

        # Write corrupt scorecard
        scorecard_path = os.path.join(tmp_scorecards_dir, f"{session_id}.json")
        with open(scorecard_path, "w") as f:
            f.write("{invalid json!!!")

        with patch(
            "backend.api.routers.sessions._get_scorecards_dir",
            return_value=tmp_scorecards_dir,
        ):
            feedback_resp = client.get(f"/api/sessions/{session_id}/feedback")
        assert feedback_resp.status_code == 422
        assert "invalid" in feedback_resp.json()["detail"].lower()

    def test_create_session_invalid_payload(self, client: TestClient):
        """POST /api/sessions rejects invalid payloads."""
        # Missing scenario
        resp = client.post("/api/sessions", json={})
        assert resp.status_code == 422

        # Empty scenario
        resp = client.post("/api/sessions", json={"scenario": ""})
        assert resp.status_code == 422

    def test_token_missing_livekit_credentials(
        self, storage: SessionStorage
    ):
        """GET /api/sessions/:id/token returns 500 when credentials are missing."""
        app = create_app()
        env_vars = {"LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}
        with patch("backend.api.routers.sessions._get_storage", return_value=storage), \
             patch("backend.api.tokens._get_storage", return_value=storage), \
             patch.dict(os.environ, env_vars, clear=False):
            test_client = TestClient(app)

            # Create session first
            create_resp = test_client.post(
                "/api/sessions", json={"scenario": "Design a URL shortener"}
            )
            session_id = create_resp.json()["session_id"]

            # Try to get token
            token_resp = test_client.get(f"/api/sessions/{session_id}/token")
            assert token_resp.status_code == 500
            assert "credentials" in token_resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: Feedback scorecard validation
# ---------------------------------------------------------------------------

class TestFeedbackValidation:
    """Tests for validating feedback scorecard structure and content."""

    def test_feedback_dimensions_complete(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_scorecard: dict,
    ):
        """Feedback response includes all dimension fields with correct types."""
        create_resp = client.post(
            "/api/sessions", json={"scenario": "Design a URL shortener"}
        )
        session_id = create_resp.json()["session_id"]

        _simulate_interview_completion(
            storage, session_id, tmp_scorecards_dir, sample_scorecard
        )

        with patch(
            "backend.api.routers.sessions._get_scorecards_dir",
            return_value=tmp_scorecards_dir,
        ):
            feedback_resp = client.get(f"/api/sessions/{session_id}/feedback")

        assert feedback_resp.status_code == 200
        feedback = feedback_resp.json()

        # Verify each dimension has the expected structure
        expected_dimensions = [
            "system_architecture",
            "technical_depth",
            "scalability_reliability",
            "communication",
            "requirements_gathering",
        ]
        for dim_name in expected_dimensions:
            assert dim_name in feedback["dimensions"], f"Missing dimension: {dim_name}"
            dim = feedback["dimensions"][dim_name]
            assert isinstance(dim["score"], int)
            assert 1 <= dim["score"] <= 5
            assert isinstance(dim["label"], str)
            assert isinstance(dim["rationale"], str)
            assert isinstance(dim["strengths"], list)
            assert isinstance(dim["gaps"], list)

    def test_feedback_scores_in_valid_range(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_scorecard: dict,
    ):
        """All dimension scores are between 1 and 5, overall_score is a float."""
        create_resp = client.post(
            "/api/sessions", json={"scenario": "Design a URL shortener"}
        )
        session_id = create_resp.json()["session_id"]

        _simulate_interview_completion(
            storage, session_id, tmp_scorecards_dir, sample_scorecard
        )

        with patch(
            "backend.api.routers.sessions._get_scorecards_dir",
            return_value=tmp_scorecards_dir,
        ):
            feedback_resp = client.get(f"/api/sessions/{session_id}/feedback")

        feedback = feedback_resp.json()
        assert isinstance(feedback["overall_score"], float)
        assert 1.0 <= feedback["overall_score"] <= 5.0

        for dim in feedback["dimensions"].values():
            assert 1 <= dim["score"] <= 5

    def test_feedback_locked_constraints_match_session(
        self,
        client: TestClient,
        storage: SessionStorage,
        tmp_scorecards_dir: str,
        sample_scorecard: dict,
    ):
        """Feedback locked_constraints match what was set during the interview."""
        create_resp = client.post(
            "/api/sessions", json={"scenario": "Design a URL shortener"}
        )
        session_id = create_resp.json()["session_id"]

        _simulate_interview_completion(
            storage, session_id, tmp_scorecards_dir, sample_scorecard
        )

        # Get session state constraints
        state_resp = client.get(f"/api/sessions/{session_id}/state")
        state_constraints = state_resp.json()["locked_constraints"]

        # Get feedback constraints
        with patch(
            "backend.api.routers.sessions._get_scorecards_dir",
            return_value=tmp_scorecards_dir,
        ):
            feedback_resp = client.get(f"/api/sessions/{session_id}/feedback")
        feedback_constraints = feedback_resp.json()["locked_constraints"]

        # Both should have the constraints set during simulation
        assert state_constraints == {"database": "PostgreSQL", "cache": "Redis"}
        assert feedback_constraints == {"database": "PostgreSQL", "cache": "Redis"}
