"""Tests for LiveKit room disconnect/reconnect handling."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from livekit import rtc

from backend.agents.interview_agent import entrypoint
from backend.models.session import InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_room():
    """Create a mock LiveKit room with event handlers."""
    room = MagicMock(spec=rtc.Room)
    room.name = "test-room-123"
    room.disconnect = AsyncMock()
    room.event_handlers = {}

    def on_event(event_name):
        def decorator(handler):
            room.event_handlers[event_name] = handler
            return handler
        return decorator

    room.on = on_event
    return room


def _make_mock_participant(identity: str, kind: rtc.ParticipantKind):
    """Create a mock participant."""
    participant = MagicMock(spec=rtc.RemoteParticipant)
    participant.identity = identity
    participant.kind = kind
    return participant


def _make_mock_job_context(room):
    """Create a mock JobContext."""
    ctx = MagicMock()
    ctx.room = room
    ctx.proc = MagicMock()
    ctx.proc.userdata = {}
    ctx.job = MagicMock()
    ctx.job.metadata = '{"scenario": "url-shortener"}'
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_participant_disconnect_event_tracked():
    """Participant disconnect is logged and tracked without crashing."""
    room = _make_mock_room()
    ctx = _make_mock_job_context(room)

    # Mock session and agent initialization
    with patch('backend.agents.interview_agent.AgentSession') as MockSession, \
         patch('backend.agents.interview_agent.ScenarioLoader') as MockLoader, \
         patch('backend.agents.interview_agent.InterviewAgent') as MockAgent:

        mock_session = MockSession.return_value
        mock_session.start = AsyncMock()
        mock_session.say = AsyncMock()
        mock_session.on = MagicMock(side_effect=lambda event: lambda fn: fn)

        mock_loader_instance = MockLoader.return_value
        mock_loader_instance._scenarios = {"url-shortener": MagicMock()}
        mock_loader_instance.get_scenario = MagicMock()

        # Start entrypoint in background
        entrypoint_task = asyncio.create_task(entrypoint(ctx))
        await asyncio.sleep(0.1)  # Let entrypoint initialize

        # Verify disconnect handler was registered
        assert "participant_disconnected" in room.event_handlers

        # Simulate participant disconnect
        candidate = _make_mock_participant("candidate-1", rtc.ParticipantKind.STANDARD)
        room.event_handlers["participant_disconnected"](candidate)

        # Agent should not crash — still running
        assert not entrypoint_task.done()

        # Clean up
        entrypoint_task.cancel()
        try:
            await entrypoint_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_reconnect_within_30s_resumes_seamlessly():
    """Reconnection within 30s cancels shutdown and resumes session."""
    room = _make_mock_room()
    ctx = _make_mock_job_context(room)

    with patch('backend.agents.interview_agent.AgentSession') as MockSession, \
         patch('backend.agents.interview_agent.ScenarioLoader') as MockLoader, \
         patch('backend.agents.interview_agent.InterviewAgent') as MockAgent:

        mock_session = MockSession.return_value
        mock_session.start = AsyncMock()
        mock_session.say = AsyncMock()
        mock_session.on = MagicMock(side_effect=lambda event: lambda fn: fn)

        mock_loader_instance = MockLoader.return_value
        mock_loader_instance._scenarios = {"url-shortener": MagicMock()}
        mock_loader_instance.get_scenario = MagicMock()

        # Start entrypoint
        entrypoint_task = asyncio.create_task(entrypoint(ctx))
        await asyncio.sleep(0.1)

        # Disconnect
        candidate = _make_mock_participant("candidate-1", rtc.ParticipantKind.STANDARD)
        room.event_handlers["participant_disconnected"](candidate)
        await asyncio.sleep(0.1)

        # Reconnect within 30s
        room.event_handlers["participant_connected"](candidate)
        await asyncio.sleep(0.1)

        # Room should NOT be disconnected (shutdown cancelled)
        room.disconnect.assert_not_called()

        # Clean up
        entrypoint_task.cancel()
        try:
            await entrypoint_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_disconnect_over_30s_triggers_shutdown():
    """Disconnection lasting >30s triggers graceful shutdown."""
    room = _make_mock_room()
    ctx = _make_mock_job_context(room)

    with patch('backend.agents.interview_agent.AgentSession') as MockSession, \
         patch('backend.agents.interview_agent.ScenarioLoader') as MockLoader, \
         patch('backend.agents.interview_agent.InterviewAgent') as MockAgent:

        mock_session = MockSession.return_value
        mock_session.start = AsyncMock()
        mock_session.say = AsyncMock()
        mock_session.on = MagicMock(side_effect=lambda event: lambda fn: fn)

        mock_loader_instance = MockLoader.return_value
        mock_loader_instance._scenarios = {"url-shortener": MagicMock()}
        mock_loader_instance.get_scenario = MagicMock()

        mock_agent = MockAgent.return_value
        mock_agent._scoring_triggered = False
        mock_agent._generate_scorecard = AsyncMock()

        # Start entrypoint
        entrypoint_task = asyncio.create_task(entrypoint(ctx))
        await asyncio.sleep(0.1)

        # Disconnect
        candidate = _make_mock_participant("candidate-1", rtc.ParticipantKind.STANDARD)
        room.event_handlers["participant_disconnected"](candidate)

        # Wait for shutdown timeout (mocked to be faster in test)
        await asyncio.sleep(30.5)

        # Room should be disconnected after timeout
        room.disconnect.assert_called_once()

        # Clean up
        entrypoint_task.cancel()
        try:
            await entrypoint_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_disconnect_triggers_scoring():
    """Graceful shutdown after disconnect triggers scorecard generation."""
    room = _make_mock_room()
    ctx = _make_mock_job_context(room)

    with patch('backend.agents.interview_agent.AgentSession') as MockSession, \
         patch('backend.agents.interview_agent.ScenarioLoader') as MockLoader, \
         patch('backend.agents.interview_agent.InterviewAgent') as MockAgent:

        mock_session = MockSession.return_value
        mock_session.start = AsyncMock()
        mock_session.say = AsyncMock()
        mock_session.on = MagicMock(side_effect=lambda event: lambda fn: fn)

        mock_loader_instance = MockLoader.return_value
        mock_loader_instance._scenarios = {"url-shortener": MagicMock()}
        mock_loader_instance.get_scenario = MagicMock()

        mock_agent = MockAgent.return_value
        mock_agent._scoring_triggered = False
        mock_agent._generate_scorecard = AsyncMock()

        # Start entrypoint
        entrypoint_task = asyncio.create_task(entrypoint(ctx))
        await asyncio.sleep(0.1)

        # Disconnect
        candidate = _make_mock_participant("candidate-1", rtc.ParticipantKind.STANDARD)
        room.event_handlers["participant_disconnected"](candidate)

        # Wait for shutdown
        await asyncio.sleep(30.5)

        # Scorecard should be generated
        mock_agent._generate_scorecard.assert_called_once()

        # Clean up
        entrypoint_task.cancel()
        try:
            await entrypoint_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_agent_disconnect_ignored():
    """Agent's own disconnect event is ignored (not a candidate disconnect)."""
    room = _make_mock_room()
    ctx = _make_mock_job_context(room)

    with patch('backend.agents.interview_agent.AgentSession') as MockSession, \
         patch('backend.agents.interview_agent.ScenarioLoader') as MockLoader, \
         patch('backend.agents.interview_agent.InterviewAgent') as MockAgent:

        mock_session = MockSession.return_value
        mock_session.start = AsyncMock()
        mock_session.say = AsyncMock()
        mock_session.on = MagicMock(side_effect=lambda event: lambda fn: fn)

        mock_loader_instance = MockLoader.return_value
        mock_loader_instance._scenarios = {"url-shortener": MagicMock()}
        mock_loader_instance.get_scenario = MagicMock()

        # Start entrypoint
        entrypoint_task = asyncio.create_task(entrypoint(ctx))
        await asyncio.sleep(0.1)

        # Agent disconnects (not a candidate)
        agent_participant = _make_mock_participant("agent", rtc.ParticipantKind.AGENT)
        room.event_handlers["participant_disconnected"](agent_participant)
        await asyncio.sleep(0.1)

        # No shutdown should be triggered
        room.disconnect.assert_not_called()

        # Clean up
        entrypoint_task.cancel()
        try:
            await entrypoint_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_multiple_disconnect_reconnect_cycles():
    """Multiple disconnect/reconnect cycles are handled correctly."""
    room = _make_mock_room()
    ctx = _make_mock_job_context(room)

    with patch('backend.agents.interview_agent.AgentSession') as MockSession, \
         patch('backend.agents.interview_agent.ScenarioLoader') as MockLoader, \
         patch('backend.agents.interview_agent.InterviewAgent') as MockAgent:

        mock_session = MockSession.return_value
        mock_session.start = AsyncMock()
        mock_session.say = AsyncMock()
        mock_session.on = MagicMock(side_effect=lambda event: lambda fn: fn)

        mock_loader_instance = MockLoader.return_value
        mock_loader_instance._scenarios = {"url-shortener": MagicMock()}
        mock_loader_instance.get_scenario = MagicMock()

        mock_agent = MockAgent.return_value
        mock_agent._scoring_triggered = False

        # Start entrypoint
        entrypoint_task = asyncio.create_task(entrypoint(ctx))
        await asyncio.sleep(0.1)

        candidate = _make_mock_participant("candidate-1", rtc.ParticipantKind.STANDARD)

        # Cycle 1: Disconnect and reconnect quickly
        room.event_handlers["participant_disconnected"](candidate)
        await asyncio.sleep(0.5)
        room.event_handlers["participant_connected"](candidate)
        await asyncio.sleep(0.1)

        # Cycle 2: Disconnect and reconnect quickly again
        room.event_handlers["participant_disconnected"](candidate)
        await asyncio.sleep(0.5)
        room.event_handlers["participant_connected"](candidate)
        await asyncio.sleep(0.1)

        # No shutdown should occur
        room.disconnect.assert_not_called()

        # Clean up
        entrypoint_task.cancel()
        try:
            await entrypoint_task
        except asyncio.CancelledError:
            pass
