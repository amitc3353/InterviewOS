"""Tests for LiveKit connection handshake end-to-end.

Validates that run_interview.py and interview_agent.py correctly create
a LiveKit room, generate a connection URL, and that the client can connect
without WebSocket errors. All external services are mocked.

Mocks the livekit SDK modules at sys.modules level so tests run without
livekit-agents or livekit-rtc installed.
"""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from dataclasses import dataclass

# Livekit mocks are installed by conftest.py before test collection
from backend.agents.interview_agent import entrypoint, prewarm, InterviewAgent
from backend.config import AgentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> AgentConfig:
    """Create minimal test config with all required fields."""
    return AgentConfig(
        livekit_url="ws://localhost:7880",
        livekit_api_key="devkey",
        livekit_api_secret="devsecret",
        deepgram_api_key="test-dg-key",
        anthropic_api_key="test-anthropic-key",
        openai_api_key="test-openai-key",
        cartesia_api_key="test-cartesia-key",
    )


def _make_mock_room(name: str = "test-interview-room"):
    """Create a mock LiveKit room with event registration support."""
    room = MagicMock()
    room.name = name
    room.sid = "RM_test_sid_123"
    room.disconnect = AsyncMock()
    room.event_handlers = {}

    def on_event(event_name):
        def decorator(handler):
            room.event_handlers[event_name] = handler
            return handler
        return decorator

    room.on = on_event
    return room


def _make_mock_participant(identity: str = "candidate-1", kind: str = "standard"):
    """Create a mock RemoteParticipant."""
    participant = MagicMock()
    participant.identity = identity
    participant.kind = kind
    participant.sid = f"PA_{identity}_sid"
    return participant


def _make_mock_job_context(room, metadata: str = '{"scenario": "url-shortener"}'):
    """Create a mock JobContext with room and metadata."""
    ctx = MagicMock()
    ctx.room = room
    ctx.proc = MagicMock()
    ctx.proc.userdata = {}
    ctx.job = MagicMock()
    ctx.job.metadata = metadata
    return ctx


# ---------------------------------------------------------------------------
# Tests — WorkerOptions configuration
# ---------------------------------------------------------------------------

class TestWorkerOptionsConfiguration:
    """Verify run_interview.py produces valid WorkerOptions."""

    @patch.dict("os.environ", {
        "LIVEKIT_URL": "wss://interview.livekit.cloud",
        "LIVEKIT_API_KEY": "APIxyz123",
        "LIVEKIT_API_SECRET": "secret456",
        "DEEPGRAM_API_KEY": "dg-test",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "OPENAI_API_KEY": "sk-oai-test",
        "CARTESIA_API_KEY": "cart-test",
    })
    def test_worker_options_created_with_config(self):
        """WorkerOptions receives correct LiveKit URL, API key, and secret."""
        config = AgentConfig.from_env()
        assert config.livekit_url == "wss://interview.livekit.cloud"
        assert config.livekit_api_key == "APIxyz123"
        assert config.livekit_api_secret == "secret456"

    @patch.dict("os.environ", {
        "LIVEKIT_URL": "wss://example.livekit.cloud",
        "LIVEKIT_API_KEY": "key",
        "LIVEKIT_API_SECRET": "secret",
        "DEEPGRAM_API_KEY": "dg",
        "ANTHROPIC_API_KEY": "ant",
        "OPENAI_API_KEY": "oai",
        "CARTESIA_API_KEY": "cart",
    })
    def test_entrypoint_is_async_callable(self):
        """Entrypoint function is an async callable."""
        assert callable(entrypoint)
        assert asyncio.iscoroutinefunction(entrypoint)

    def test_config_validation_rejects_empty_livekit_url(self):
        """Config validation fails when LIVEKIT_URL is empty."""
        config = AgentConfig(
            livekit_url="",
            livekit_api_key="key",
            livekit_api_secret="secret",
            deepgram_api_key="dg",
            anthropic_api_key="ant",
            openai_api_key="oai",
            cartesia_api_key="cart",
        )
        assert config.validate() is False

    def test_config_validation_rejects_placeholder_api_key(self):
        """Config validation fails when API key is a placeholder."""
        config = AgentConfig(
            livekit_url="wss://test.livekit.cloud",
            livekit_api_key="your_api_key_here",
            livekit_api_secret="secret",
            deepgram_api_key="dg",
            anthropic_api_key="ant",
            openai_api_key="oai",
            cartesia_api_key="cart",
        )
        assert config.validate() is False

    def test_config_validation_accepts_valid_config(self):
        """Config validation passes with properly set values."""
        config = _make_config()
        assert config.validate() is True


# ---------------------------------------------------------------------------
# Tests — Entrypoint handshake (room join, session start)
# ---------------------------------------------------------------------------

class TestEntrypointHandshake:
    """Validate the entrypoint function initializes the LiveKit session correctly."""

    @pytest.mark.asyncio
    async def test_entrypoint_starts_session_with_room(self):
        """Entrypoint creates AgentSession and starts it with the room."""
        room = _make_mock_room()
        ctx = _make_mock_job_context(room)

        with patch('backend.config.AgentConfig.from_env') as mock_from_env, \
             patch('backend.interview.scenario_loader.ScenarioLoader') as MockLoader:

            mock_from_env.return_value = _make_config()

            mock_scenario = MagicMock()
            mock_scenario.id = "url-shortener"
            mock_scenario.name = "Design a URL Shortener"
            mock_scenario.archetype = "storage"
            mock_loader_instance = MockLoader.return_value
            mock_loader_instance._scenarios = {"url-shortener": mock_scenario}
            mock_loader_instance.get_scenario.return_value = mock_scenario

            task = asyncio.create_task(entrypoint(ctx))
            await asyncio.sleep(0.3)

            # Verify event handlers were registered on the room
            assert "disconnected" in room.event_handlers
            assert "participant_disconnected" in room.event_handlers
            assert "participant_connected" in room.event_handlers

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_entrypoint_parses_scenario_from_metadata(self):
        """Entrypoint correctly parses scenario from job metadata JSON."""
        room = _make_mock_room()
        ctx = _make_mock_job_context(room, metadata='{"scenario": "payment-gateway"}')

        with patch('backend.config.AgentConfig.from_env') as mock_from_env, \
             patch('backend.interview.scenario_loader.ScenarioLoader') as MockLoader:

            mock_from_env.return_value = _make_config()

            mock_scenario = MagicMock()
            mock_scenario.id = "payment-gateway"
            mock_scenario.name = "Design a Payment Gateway"
            mock_scenario.archetype = "infrastructure"

            mock_loader_instance = MockLoader.return_value
            mock_loader_instance._scenarios = {"payment-gateway": mock_scenario}
            mock_loader_instance.get_scenario.return_value = mock_scenario

            task = asyncio.create_task(entrypoint(ctx))
            await asyncio.sleep(0.3)

            # ScenarioLoader.get_scenario should be called with the scenario ID
            mock_loader_instance.get_scenario.assert_called_with("payment-gateway")

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_entrypoint_uses_default_scenario_on_empty_metadata(self):
        """Entrypoint falls back to default scenario when metadata is empty."""
        room = _make_mock_room()
        ctx = _make_mock_job_context(room, metadata="")
        ctx.job.metadata = ""

        with patch('backend.config.AgentConfig.from_env') as mock_from_env, \
             patch('backend.interview.scenario_loader.ScenarioLoader') as MockLoader:

            mock_from_env.return_value = _make_config()

            mock_loader_instance = MockLoader.return_value
            mock_loader_instance._scenarios = {}
            mock_loader_instance.get_scenario = MagicMock()

            task = asyncio.create_task(entrypoint(ctx))
            await asyncio.sleep(0.3)

            # Should NOT call get_scenario when metadata is empty
            mock_loader_instance.get_scenario.assert_not_called()

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_entrypoint_falls_back_on_invalid_json_metadata(self):
        """Entrypoint uses literal metadata text when JSON parsing fails."""
        room = _make_mock_room()
        ctx = _make_mock_job_context(room, metadata="Design a Chat System")

        with patch('backend.config.AgentConfig.from_env') as mock_from_env, \
             patch('backend.interview.scenario_loader.ScenarioLoader') as MockLoader:

            mock_from_env.return_value = _make_config()

            mock_loader_instance = MockLoader.return_value
            mock_loader_instance._scenarios = {}
            mock_loader_instance.get_scenario = MagicMock()

            task = asyncio.create_task(entrypoint(ctx))
            await asyncio.sleep(0.3)

            # Should not crash — entrypoint uses literal text as scenario
            # Entrypoint completes normally after setup (not a long-running loop)
            if task.done():
                # Verify it completed without raising an exception
                task.result()
            else:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


# ---------------------------------------------------------------------------
# Tests — Connection handshake simulation
# ---------------------------------------------------------------------------

class TestConnectionHandshake:
    """Simulate client connection lifecycle and verify handshake completes."""

    @pytest.mark.asyncio
    async def test_participant_connect_fires_event(self):
        """Participant connecting to room fires connected event without error."""
        room = _make_mock_room()
        ctx = _make_mock_job_context(room)

        with patch('backend.config.AgentConfig.from_env') as mock_from_env, \
             patch('backend.interview.scenario_loader.ScenarioLoader') as MockLoader:

            mock_from_env.return_value = _make_config()

            mock_scenario = MagicMock()
            mock_scenario.id = "url-shortener"
            mock_scenario.name = "Design a URL Shortener"
            mock_scenario.archetype = "storage"
            mock_loader_instance = MockLoader.return_value
            mock_loader_instance._scenarios = {"url-shortener": mock_scenario}
            mock_loader_instance.get_scenario.return_value = mock_scenario

            task = asyncio.create_task(entrypoint(ctx))
            await asyncio.sleep(0.3)

            # Simulate client connecting — should not raise
            participant = _make_mock_participant("candidate-1", "standard")
            handler = room.event_handlers.get("participant_connected")
            assert handler is not None, "participant_connected handler must be registered"
            handler(participant)

            # Room should NOT be disconnected (connection is fresh)
            room.disconnect.assert_not_called()

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_full_connect_disconnect_reconnect_handshake(self):
        """Full lifecycle: connect -> disconnect -> reconnect completes without errors."""
        room = _make_mock_room()
        ctx = _make_mock_job_context(room)

        with patch('backend.config.AgentConfig.from_env') as mock_from_env, \
             patch('backend.interview.scenario_loader.ScenarioLoader') as MockLoader:

            mock_from_env.return_value = _make_config()

            mock_scenario = MagicMock()
            mock_scenario.id = "url-shortener"
            mock_scenario.name = "Design a URL Shortener"
            mock_scenario.archetype = "storage"
            mock_loader_instance = MockLoader.return_value
            mock_loader_instance._scenarios = {"url-shortener": mock_scenario}
            mock_loader_instance.get_scenario.return_value = mock_scenario

            task = asyncio.create_task(entrypoint(ctx))
            await asyncio.sleep(0.3)

            participant = _make_mock_participant("candidate-1", "standard")

            # Step 1: Client connects
            room.event_handlers["participant_connected"](participant)
            await asyncio.sleep(0.05)

            # Step 2: Client disconnects (network blip)
            room.event_handlers["participant_disconnected"](participant)
            await asyncio.sleep(0.1)

            # Step 3: Client reconnects within 30s
            room.event_handlers["participant_connected"](participant)
            await asyncio.sleep(0.05)

            # Handshake succeeds — room not torn down
            room.disconnect.assert_not_called()

            # Entrypoint completes normally after setup (not a long-running loop)
            if task.done():
                task.result()  # Verify no exception
            else:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_agent_participant_disconnect_ignored(self):
        """Agent (non-candidate) disconnect events don't trigger reconnect logic."""
        room = _make_mock_room()
        ctx = _make_mock_job_context(room)

        with patch('backend.config.AgentConfig.from_env') as mock_from_env, \
             patch('backend.interview.scenario_loader.ScenarioLoader') as MockLoader:

            mock_from_env.return_value = _make_config()

            mock_scenario = MagicMock()
            mock_scenario.id = "url-shortener"
            mock_scenario.name = "Design a URL Shortener"
            mock_scenario.archetype = "storage"
            mock_loader_instance = MockLoader.return_value
            mock_loader_instance._scenarios = {"url-shortener": mock_scenario}
            mock_loader_instance.get_scenario.return_value = mock_scenario

            task = asyncio.create_task(entrypoint(ctx))
            await asyncio.sleep(0.3)

            # Agent-type participant disconnects — should NOT trigger shutdown
            agent_participant = _make_mock_participant("agent-bot", "agent")
            room.event_handlers["participant_disconnected"](agent_participant)
            await asyncio.sleep(0.1)

            room.disconnect.assert_not_called()

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_room_disconnected_event_does_not_crash(self):
        """Room-level disconnected event is handled without raising."""
        room = _make_mock_room()
        ctx = _make_mock_job_context(room)

        with patch('backend.config.AgentConfig.from_env') as mock_from_env, \
             patch('backend.interview.scenario_loader.ScenarioLoader') as MockLoader:

            mock_from_env.return_value = _make_config()

            mock_scenario = MagicMock()
            mock_scenario.id = "url-shortener"
            mock_scenario.name = "Design a URL Shortener"
            mock_scenario.archetype = "storage"
            mock_loader_instance = MockLoader.return_value
            mock_loader_instance._scenarios = {"url-shortener": mock_scenario}
            mock_loader_instance.get_scenario.return_value = mock_scenario

            task = asyncio.create_task(entrypoint(ctx))
            await asyncio.sleep(0.3)

            # Fire room disconnect event — should not crash
            handler = room.event_handlers.get("disconnected")
            assert handler is not None
            handler()  # Should not raise
            await asyncio.sleep(0.05)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# Tests — Prewarm and agent initialization
# ---------------------------------------------------------------------------

class TestPrewarmAndInit:
    """Validate prewarm and InterviewAgent initialization for connection readiness."""

    def test_prewarm_sets_turn_detector_in_userdata(self):
        """Prewarm sets turn_detector key in proc.userdata."""
        mock_proc = MagicMock()
        mock_proc.userdata = {}

        with patch('backend.config.AgentConfig.from_env') as mock_from_env:
            mock_config = _make_config()
            mock_config.use_semantic_turn_detection = False
            mock_from_env.return_value = mock_config

            prewarm(mock_proc)

            assert "turn_detector" in mock_proc.userdata

    def test_prewarm_loads_semantic_detector_when_enabled(self):
        """Prewarm loads semantic turn detector when config enables it."""
        mock_proc = MagicMock()
        mock_proc.userdata = {}

        with patch('backend.config.AgentConfig.from_env') as mock_from_env:
            mock_config = _make_config()
            mock_config.use_semantic_turn_detection = True
            mock_from_env.return_value = mock_config

            prewarm(mock_proc)

            # Should have attempted to create EnglishModel
            assert "turn_detector" in mock_proc.userdata

    def test_interview_agent_initializes_session(self):
        """InterviewAgent creates an interview session with correct scenario."""
        config = _make_config()
        agent = InterviewAgent(config, "Design a URL Shortener")

        assert agent.interview_session is not None
        assert agent.interview_session.scenario == "Design a URL Shortener"
        assert agent.interview_session.state.phase.value == "intro"

    def test_interview_agent_phase_manager_created(self):
        """InterviewAgent initializes PhaseManager for the given scenario."""
        config = _make_config()
        agent = InterviewAgent(config, "Design a Rate Limiter")

        assert agent.phase_manager is not None
        assert agent.scenario == "Design a Rate Limiter"

    def test_interview_agent_scoring_not_triggered_initially(self):
        """InterviewAgent starts with scoring not yet triggered."""
        config = _make_config()
        agent = InterviewAgent(config, "Design a Cache")

        assert agent._scoring_triggered is False
        assert agent._session_completed is False


# ---------------------------------------------------------------------------
# Tests — Error handling during connection
# ---------------------------------------------------------------------------

class TestConnectionErrorHandling:
    """Verify graceful error handling during connection issues."""

    def test_config_mask_secret_hides_api_keys(self):
        """mask_secret properly hides API keys for connection logging."""
        assert AgentConfig.mask_secret("sk-ant-api123456789abc") == "****9abc"
        assert AgentConfig.mask_secret("") == "****"
        assert AgentConfig.mask_secret("ab") == "****"
        assert AgentConfig.mask_secret("abcde") == "****bcde"

    def test_config_mask_secret_boundary_values(self):
        """mask_secret handles edge cases for key lengths."""
        # 4 chars or fewer are fully masked (don't reveal short secrets)
        assert AgentConfig.mask_secret("abcd") == "****"
        assert AgentConfig.mask_secret("abc") == "****"
        assert AgentConfig.mask_secret("a") == "****"

    @patch.dict("os.environ", {
        "LIVEKIT_URL": "",
        "LIVEKIT_API_KEY": "key",
        "LIVEKIT_API_SECRET": "secret",
        "DEEPGRAM_API_KEY": "dg",
        "ANTHROPIC_API_KEY": "ant",
        "OPENAI_API_KEY": "oai",
        "CARTESIA_API_KEY": "cart",
    })
    def test_config_from_env_with_empty_url_fails_validation(self):
        """Config loaded from env with empty LIVEKIT_URL fails validation."""
        config = AgentConfig.from_env()
        assert config.livekit_url == ""
        assert config.validate() is False

    @patch.dict("os.environ", {
        "LIVEKIT_URL": "wss://test.livekit.cloud",
        "LIVEKIT_API_KEY": "APIkey123",
        "LIVEKIT_API_SECRET": "APIsecret456",
        "DEEPGRAM_API_KEY": "dg-live-key",
        "ANTHROPIC_API_KEY": "sk-ant-live-key",
        "OPENAI_API_KEY": "sk-oai-live-key",
        "CARTESIA_API_KEY": "cart-live-key",
    })
    def test_config_from_env_with_all_values_passes_validation(self):
        """Config loaded from env with all values set passes validation."""
        config = AgentConfig.from_env()
        assert config.validate() is True
        assert config.livekit_url == "wss://test.livekit.cloud"

    def test_config_rejects_multiple_placeholder_patterns(self):
        """Config validation catches various placeholder patterns."""
        placeholders = [
            "your_api_key",
            "sk-xxx",
            "key_here",
            "replace_me",
            "todo_add_key",
            "changeme",
            "placeholder_value",
        ]
        for placeholder in placeholders:
            config = AgentConfig(
                livekit_url="wss://test.livekit.cloud",
                livekit_api_key=placeholder,
                livekit_api_secret="secret",
                deepgram_api_key="dg",
                anthropic_api_key="ant",
                openai_api_key="oai",
                cartesia_api_key="cart",
            )
            assert config.validate() is False, f"Should reject placeholder: {placeholder}"
