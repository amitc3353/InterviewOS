"""Tests for WebSocket transcript streaming endpoint."""

import asyncio
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.server import create_app
from backend.api.storage import SessionStorage
from backend.api.transcript_manager import (
    TranscriptEvent,
    TranscriptEventManager,
    get_transcript_manager,
)


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
         patch("backend.api.routers.websocket._get_storage", return_value=storage):
        yield TestClient(app)


@pytest.fixture
def sample_session_data() -> dict:
    """Return sample session data for storage seeding."""
    return {
        "session_id": "test-ws-session",
        "scenario": "Design a URL shortener",
        "phase": "scope",
        "locked_constraints": {"database": "PostgreSQL"},
        "conversation_history": [
            {"role": "assistant", "content": "Hello, let's begin.", "timestamp": "2026-01-01T00:00:00"},
            {"role": "user", "content": "Sure, let's go.", "timestamp": "2026-01-01T00:00:05"},
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


@pytest.fixture
def manager() -> TranscriptEventManager:
    """Create a fresh TranscriptEventManager for testing."""
    return TranscriptEventManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_session(storage: SessionStorage, data: dict) -> None:
    """Write session data directly to storage."""
    storage.save(data)


# ---------------------------------------------------------------------------
# Tests: TranscriptEvent
# ---------------------------------------------------------------------------

def test_transcript_event_to_dict():
    """TranscriptEvent.to_dict() returns correct message format."""
    event = TranscriptEvent(
        speaker="candidate",
        text="I would use a hash function.",
        phase="architecture",
        turn_number=5,
        timestamp="2026-01-15T10:30:00",
    )
    result = event.to_dict()

    assert result["speaker"] == "candidate"
    assert result["text"] == "I would use a hash function."
    assert result["phase"] == "architecture"
    assert result["turn_number"] == 5
    assert result["timestamp"] == "2026-01-15T10:30:00"


def test_transcript_event_default_timestamp():
    """TranscriptEvent generates ISO8601 timestamp when not provided."""
    event = TranscriptEvent(
        speaker="interviewer",
        text="Tell me about caching.",
        phase="deep_dive",
        turn_number=3,
    )
    result = event.to_dict()
    # Should be a non-empty ISO8601 string
    assert result["timestamp"]
    assert "T" in result["timestamp"]


def test_transcript_event_speaker_values():
    """TranscriptEvent accepts both 'interviewer' and 'candidate' speakers."""
    for speaker in ["interviewer", "candidate"]:
        event = TranscriptEvent(
            speaker=speaker, text="test", phase="intro", turn_number=0
        )
        assert event.to_dict()["speaker"] == speaker


# ---------------------------------------------------------------------------
# Tests: TranscriptEventManager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_subscribe_and_publish():
    """Published events are received by subscribers."""
    manager = TranscriptEventManager()
    queue = await manager.subscribe("session-1")

    event = TranscriptEvent(
        speaker="interviewer", text="Hello!", phase="intro", turn_number=1
    )
    await manager.publish("session-1", event)

    received = queue.get_nowait()
    assert received.speaker == "interviewer"
    assert received.text == "Hello!"


@pytest.mark.asyncio
async def test_manager_multiple_subscribers():
    """Multiple subscribers each receive published events."""
    manager = TranscriptEventManager()
    queue1 = await manager.subscribe("session-1")
    queue2 = await manager.subscribe("session-1")

    event = TranscriptEvent(
        speaker="candidate", text="My approach...", phase="scope", turn_number=2
    )
    await manager.publish("session-1", event)

    assert not queue1.empty()
    assert not queue2.empty()
    assert queue1.get_nowait().text == "My approach..."
    assert queue2.get_nowait().text == "My approach..."


@pytest.mark.asyncio
async def test_manager_unsubscribe():
    """Unsubscribed clients no longer receive events."""
    manager = TranscriptEventManager()
    queue = await manager.subscribe("session-1")
    await manager.unsubscribe("session-1", queue)

    event = TranscriptEvent(
        speaker="interviewer", text="Follow-up", phase="deep_dive", turn_number=3
    )
    await manager.publish("session-1", event)

    assert queue.empty()


@pytest.mark.asyncio
async def test_manager_subscriber_count():
    """subscriber_count() returns correct count."""
    manager = TranscriptEventManager()
    assert manager.subscriber_count("session-1") == 0

    queue1 = await manager.subscribe("session-1")
    assert manager.subscriber_count("session-1") == 1

    queue2 = await manager.subscribe("session-1")
    assert manager.subscriber_count("session-1") == 2

    await manager.unsubscribe("session-1", queue1)
    assert manager.subscriber_count("session-1") == 1

    await manager.unsubscribe("session-1", queue2)
    assert manager.subscriber_count("session-1") == 0


@pytest.mark.asyncio
async def test_manager_publish_to_nonexistent_session():
    """Publishing to a session with no subscribers does not raise."""
    manager = TranscriptEventManager()
    event = TranscriptEvent(
        speaker="interviewer", text="Anyone?", phase="intro", turn_number=0
    )
    # Should not raise
    await manager.publish("nonexistent-session", event)


@pytest.mark.asyncio
async def test_manager_unsubscribe_nonexistent_queue():
    """Unsubscribing with an unknown queue does not raise."""
    manager = TranscriptEventManager()
    orphan_queue: asyncio.Queue = asyncio.Queue()
    # Should not raise
    await manager.unsubscribe("nonexistent-session", orphan_queue)


@pytest.mark.asyncio
async def test_manager_session_isolation():
    """Events for one session are not received by subscribers of another."""
    manager = TranscriptEventManager()
    queue_a = await manager.subscribe("session-a")
    queue_b = await manager.subscribe("session-b")

    event = TranscriptEvent(
        speaker="candidate", text="Only for A", phase="scope", turn_number=1
    )
    await manager.publish("session-a", event)

    assert not queue_a.empty()
    assert queue_b.empty()


def test_get_transcript_manager_returns_singleton():
    """get_transcript_manager() returns the same instance each call."""
    m1 = get_transcript_manager()
    m2 = get_transcript_manager()
    assert m1 is m2


# ---------------------------------------------------------------------------
# Tests: WebSocket endpoint — connection and history
# ---------------------------------------------------------------------------

def test_websocket_connect_and_receive_history(
    client: TestClient, storage: SessionStorage, sample_session_data: dict
):
    """WebSocket connects and sends existing conversation history."""
    _seed_session(storage, sample_session_data)

    with client.websocket_connect("/api/sessions/test-ws-session/transcript") as ws:
        # Should receive 2 history messages
        msg1 = ws.receive_json()
        assert msg1["speaker"] == "interviewer"
        assert msg1["text"] == "Hello, let's begin."
        assert msg1["phase"] == "scope"
        assert msg1["turn_number"] == 0

        msg2 = ws.receive_json()
        assert msg2["speaker"] == "candidate"
        assert msg2["text"] == "Sure, let's go."
        assert msg2["turn_number"] == 1


def test_websocket_message_format(
    client: TestClient, storage: SessionStorage, sample_session_data: dict
):
    """WebSocket messages contain all required fields."""
    _seed_session(storage, sample_session_data)

    with client.websocket_connect("/api/sessions/test-ws-session/transcript") as ws:
        msg = ws.receive_json()
        required_fields = {"speaker", "text", "timestamp", "phase", "turn_number"}
        assert required_fields.issubset(set(msg.keys()))


def test_websocket_empty_history(
    client: TestClient, storage: SessionStorage
):
    """WebSocket connects successfully for session with empty conversation history."""
    data = {
        "session_id": "empty-session",
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
    _seed_session(storage, data)

    with client.websocket_connect("/api/sessions/empty-session/transcript") as ws:
        # No history messages — next message would be a ping after timeout
        # Just verify connection succeeded by closing cleanly
        pass


# ---------------------------------------------------------------------------
# Tests: WebSocket endpoint — error cases
# ---------------------------------------------------------------------------

def test_websocket_invalid_session_id(client: TestClient):
    """WebSocket closes with 4004 for non-existent session."""
    with pytest.raises(Exception):
        with client.websocket_connect("/api/sessions/nonexistent-id/transcript") as ws:
            ws.receive_json()


def test_websocket_path_traversal_rejected(client: TestClient):
    """WebSocket closes with 4000 for path traversal session IDs."""
    with pytest.raises(Exception):
        with client.websocket_connect("/api/sessions/../../etc/passwd/transcript") as ws:
            ws.receive_json()


# ---------------------------------------------------------------------------
# Tests: WebSocket endpoint — real-time event streaming
# ---------------------------------------------------------------------------

def test_websocket_receives_published_events(
    client: TestClient, storage: SessionStorage
):
    """WebSocket receives events published via TranscriptEventManager."""
    data = {
        "session_id": "realtime-session",
        "scenario": "Design a cache",
        "phase": "architecture",
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
    _seed_session(storage, data)

    manager = get_transcript_manager()

    with client.websocket_connect("/api/sessions/realtime-session/transcript") as ws:
        # Publish an event from "outside" (simulating agent)
        import asyncio

        loop = asyncio.new_event_loop()
        event = TranscriptEvent(
            speaker="interviewer",
            text="What about caching?",
            phase="architecture",
            turn_number=1,
            timestamp="2026-01-15T10:30:00",
        )
        loop.run_until_complete(manager.publish("realtime-session", event))
        loop.close()

        msg = ws.receive_json()
        assert msg["speaker"] == "interviewer"
        assert msg["text"] == "What about caching?"
        assert msg["phase"] == "architecture"
        assert msg["turn_number"] == 1
        assert msg["timestamp"] == "2026-01-15T10:30:00"


# ---------------------------------------------------------------------------
# Tests: WebSocket endpoint — disconnect handling
# ---------------------------------------------------------------------------

def test_websocket_disconnect_cleanup(
    client: TestClient, storage: SessionStorage
):
    """WebSocket disconnect properly unsubscribes from event manager."""
    data = {
        "session_id": "disconnect-session",
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
    _seed_session(storage, data)

    manager = get_transcript_manager()

    with client.websocket_connect("/api/sessions/disconnect-session/transcript") as ws:
        assert manager.subscriber_count("disconnect-session") == 1

    # After context manager exits (disconnect), subscriber should be cleaned up
    # Give a moment for cleanup
    assert manager.subscriber_count("disconnect-session") == 0


# ---------------------------------------------------------------------------
# Tests: _history_entry_to_message helper
# ---------------------------------------------------------------------------

def test_history_entry_to_message_assistant():
    """_history_entry_to_message maps 'assistant' role to 'interviewer'."""
    from backend.api.routers.websocket import _history_entry_to_message

    entry = {"role": "assistant", "content": "Hello!", "timestamp": "2026-01-01T00:00:00"}
    result = _history_entry_to_message(entry, 0, "intro")
    assert result["speaker"] == "interviewer"
    assert result["text"] == "Hello!"
    assert result["timestamp"] == "2026-01-01T00:00:00"
    assert result["phase"] == "intro"
    assert result["turn_number"] == 0


def test_history_entry_to_message_user():
    """_history_entry_to_message maps 'user' role to 'candidate'."""
    from backend.api.routers.websocket import _history_entry_to_message

    entry = {"role": "user", "content": "I'd use Redis.", "timestamp": "2026-01-01T00:01:00"}
    result = _history_entry_to_message(entry, 3, "deep_dive")
    assert result["speaker"] == "candidate"
    assert result["text"] == "I'd use Redis."
    assert result["phase"] == "deep_dive"
    assert result["turn_number"] == 3


def test_history_entry_to_message_missing_fields():
    """_history_entry_to_message handles missing fields gracefully."""
    from backend.api.routers.websocket import _history_entry_to_message

    entry = {}
    result = _history_entry_to_message(entry, 0, "intro")
    assert result["speaker"] == "candidate"  # default: non-assistant maps to candidate
    assert result["text"] == ""
    assert result["timestamp"] == ""
    assert result["phase"] == "intro"
    assert result["turn_number"] == 0
