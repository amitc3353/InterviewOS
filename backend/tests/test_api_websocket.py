"""Tests for WebSocket transcript streaming endpoint."""

import asyncio
import tempfile
import time
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


def _make_empty_session(session_id: str, phase: str = "intro") -> dict:
    """Build minimal session data with no conversation history."""
    return {
        "session_id": session_id,
        "scenario": "Test",
        "phase": phase,
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


def _make_reconnection_session_data(session_id: str, history: list) -> dict:
    """Build minimal session data for reconnection tests."""
    return {
        "session_id": session_id,
        "scenario": "Design a message queue",
        "phase": "architecture",
        "locked_constraints": {},
        "conversation_history": history,
        "transcript": [],
        "metadata": {},
        "scorecard": None,
        "session_start_time": "2026-01-01T00:00:00",
        "created_at": "2026-01-01T00:00:00",
        "elapsed_seconds": 60.0,
        "total_turns": len(history),
        "livekit_room_name": None,
    }


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


@pytest.mark.asyncio
async def test_manager_publish_sync_test_only():
    """_publish_sync_test_only() delivers events without async context."""
    manager = TranscriptEventManager()
    queue = await manager.subscribe("session-sync")

    event = TranscriptEvent(
        speaker="interviewer", text="Sync publish test", phase="intro", turn_number=0
    )
    manager._publish_sync_test_only("session-sync", event)

    assert not queue.empty()
    received = queue.get_nowait()
    assert received.text == "Sync publish test"


@pytest.mark.asyncio
async def test_manager_publish_sync_test_only_no_subscribers():
    """_publish_sync_test_only() to session with no subscribers does not raise."""
    manager = TranscriptEventManager()
    event = TranscriptEvent(
        speaker="interviewer", text="Nobody here", phase="intro", turn_number=0
    )
    # Should not raise
    manager._publish_sync_test_only("nonexistent", event)


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
    _seed_session(storage, _make_empty_session("empty-session"))

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
    _seed_session(storage, _make_empty_session("realtime-session", phase="architecture"))

    manager = get_transcript_manager()

    with client.websocket_connect("/api/sessions/realtime-session/transcript") as ws:
        # Allow subscription to be established in the ASGI background thread
        time.sleep(0.05)

        event = TranscriptEvent(
            speaker="interviewer",
            text="What about caching?",
            phase="architecture",
            turn_number=1,
            timestamp="2026-01-15T10:30:00",
        )
        manager._publish_sync_test_only("realtime-session", event)

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
    _seed_session(storage, _make_empty_session("disconnect-session"))

    manager = get_transcript_manager()

    with client.websocket_connect("/api/sessions/disconnect-session/transcript") as ws:
        assert manager.subscriber_count("disconnect-session") == 1

    # After context manager exits (disconnect), subscriber should be cleaned up
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


# ---------------------------------------------------------------------------
# Tests: WebSocket endpoint — reconnection handling
# ---------------------------------------------------------------------------

def test_websocket_reconnect_receives_full_history(
    client: TestClient, storage: SessionStorage
):
    """After disconnect+reconnect, client receives full conversation history again."""
    history = [
        {"role": "assistant", "content": "Let's discuss the design.", "timestamp": "2026-01-01T00:00:00"},
        {"role": "user", "content": "I'd start with requirements.", "timestamp": "2026-01-01T00:00:05"},
        {"role": "assistant", "content": "Good. What scale?", "timestamp": "2026-01-01T00:00:10"},
    ]
    data = _make_reconnection_session_data("reconnect-session", history)
    _seed_session(storage, data)

    manager = get_transcript_manager()

    # First connection — receive history and disconnect
    with client.websocket_connect("/api/sessions/reconnect-session/transcript") as ws:
        for _ in range(3):
            ws.receive_json()
        assert manager.subscriber_count("reconnect-session") == 1

    # After disconnect, subscriber is cleaned up
    assert manager.subscriber_count("reconnect-session") == 0

    # Reconnect — should receive the same full history again
    with client.websocket_connect("/api/sessions/reconnect-session/transcript") as ws:
        msg1 = ws.receive_json()
        assert msg1["speaker"] == "interviewer"
        assert msg1["text"] == "Let's discuss the design."
        assert msg1["turn_number"] == 0

        msg2 = ws.receive_json()
        assert msg2["speaker"] == "candidate"
        assert msg2["text"] == "I'd start with requirements."
        assert msg2["turn_number"] == 1

        msg3 = ws.receive_json()
        assert msg3["speaker"] == "interviewer"
        assert msg3["text"] == "Good. What scale?"
        assert msg3["turn_number"] == 2

        assert manager.subscriber_count("reconnect-session") == 1


def test_websocket_reconnect_gets_new_subscriber(
    client: TestClient, storage: SessionStorage
):
    """Each reconnection creates a fresh subscriber queue."""
    _seed_session(storage, _make_reconnection_session_data("resub-session", []))

    manager = get_transcript_manager()

    # Connect, verify subscriber count, disconnect
    with client.websocket_connect("/api/sessions/resub-session/transcript"):
        assert manager.subscriber_count("resub-session") == 1

    assert manager.subscriber_count("resub-session") == 0

    # Reconnect — new subscriber
    with client.websocket_connect("/api/sessions/resub-session/transcript"):
        assert manager.subscriber_count("resub-session") == 1

    assert manager.subscriber_count("resub-session") == 0


def test_websocket_reconnect_receives_events_after_rejoin(
    client: TestClient, storage: SessionStorage
):
    """After reconnection, client receives new events published post-reconnect."""
    _seed_session(storage, _make_reconnection_session_data("rejoin-session", []))

    manager = get_transcript_manager()

    # First connection and disconnect
    with client.websocket_connect("/api/sessions/rejoin-session/transcript"):
        pass

    # Reconnect and verify new events arrive
    with client.websocket_connect("/api/sessions/rejoin-session/transcript") as ws:
        # Allow subscription to be established
        time.sleep(0.05)

        event = TranscriptEvent(
            speaker="interviewer",
            text="Welcome back! Let's continue.",
            phase="architecture",
            turn_number=0,
            timestamp="2026-01-15T11:00:00",
        )
        manager._publish_sync_test_only("rejoin-session", event)

        msg = ws.receive_json()
        assert msg["speaker"] == "interviewer"
        assert msg["text"] == "Welcome back! Let's continue."
        assert msg["turn_number"] == 0


def test_websocket_concurrent_connections_same_session(
    client: TestClient, storage: SessionStorage
):
    """Multiple simultaneous WebSocket connections to same session each receive events."""
    _seed_session(storage, _make_reconnection_session_data("concurrent-session", []))

    manager = get_transcript_manager()

    with client.websocket_connect("/api/sessions/concurrent-session/transcript") as ws1:
        assert manager.subscriber_count("concurrent-session") == 1

        with client.websocket_connect("/api/sessions/concurrent-session/transcript") as ws2:
            assert manager.subscriber_count("concurrent-session") == 2

            # Allow subscriptions to be established
            time.sleep(0.05)

            event = TranscriptEvent(
                speaker="candidate",
                text="Both should see this.",
                phase="architecture",
                turn_number=0,
                timestamp="2026-01-15T12:00:00",
            )
            manager._publish_sync_test_only("concurrent-session", event)

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()
            assert msg1["text"] == "Both should see this."
            assert msg2["text"] == "Both should see this."

        # ws2 disconnected
        assert manager.subscriber_count("concurrent-session") == 1

    # ws1 disconnected
    assert manager.subscriber_count("concurrent-session") == 0


# ---------------------------------------------------------------------------
# Tests: WebSocket endpoint — mock agent transcript stream
# ---------------------------------------------------------------------------

def test_websocket_receives_sequential_agent_events(
    client: TestClient, storage: SessionStorage
):
    """WebSocket receives multiple events in order from simulated agent stream."""
    _seed_session(storage, _make_reconnection_session_data("stream-session", []))

    manager = get_transcript_manager()

    with client.websocket_connect("/api/sessions/stream-session/transcript") as ws:
        # Allow subscription to be established
        time.sleep(0.05)

        events = [
            TranscriptEvent(
                speaker="candidate",
                text="I would use Kafka.",
                phase="architecture",
                turn_number=0,
                timestamp="2026-01-15T10:00:00",
            ),
            TranscriptEvent(
                speaker="interviewer",
                text="Why Kafka over RabbitMQ?",
                phase="architecture",
                turn_number=1,
                timestamp="2026-01-15T10:00:05",
            ),
            TranscriptEvent(
                speaker="candidate",
                text="Higher throughput for our scale.",
                phase="architecture",
                turn_number=2,
                timestamp="2026-01-15T10:00:10",
            ),
        ]
        for event in events:
            manager._publish_sync_test_only("stream-session", event)

        received = [ws.receive_json() for _ in range(3)]
        assert received[0]["speaker"] == "candidate"
        assert received[0]["text"] == "I would use Kafka."
        assert received[1]["speaker"] == "interviewer"
        assert received[1]["text"] == "Why Kafka over RabbitMQ?"
        assert received[2]["speaker"] == "candidate"
        assert received[2]["text"] == "Higher throughput for our scale."
        # Verify ordering by turn_number
        assert [m["turn_number"] for m in received] == [0, 1, 2]
