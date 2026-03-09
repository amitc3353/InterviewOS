"""Shared pytest configuration and fixtures for backend tests.

Installs mock livekit SDK modules into sys.modules at import time so that
test files can freely ``from livekit import rtc`` or
``from backend.agents.interview_agent import ...`` without the real
livekit-agents / livekit-rtc packages being installed.

This conftest is loaded by pytest **before** test modules are collected,
ensuring the mocks are available at import time for all test files.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock


def _install_livekit_mocks() -> None:
    """Install comprehensive mock livekit modules into sys.modules."""
    # Skip if already mocked (e.g., by a test file that sets up its own mocks)
    if "livekit" in sys.modules and hasattr(sys.modules["livekit"], "_conftest_mocked"):
        return

    mock_modules = {}

    # -----------------------------------------------------------------------
    # livekit root
    # -----------------------------------------------------------------------
    livekit_mod = types.ModuleType("livekit")
    livekit_mod._conftest_mocked = True
    mock_modules["livekit"] = livekit_mod

    # -----------------------------------------------------------------------
    # livekit.rtc — includes AudioFrame, Room, RemoteParticipant, etc.
    # -----------------------------------------------------------------------
    rtc_mod = types.ModuleType("livekit.rtc")
    rtc_mod.AudioFrame = MagicMock
    rtc_mod.Room = MagicMock
    rtc_mod.RemoteParticipant = MagicMock

    class _ParticipantKind:
        STANDARD = "standard"
        AGENT = "agent"
        SIP = "sip"
        INGRESS = "ingress"

    rtc_mod.ParticipantKind = _ParticipantKind
    livekit_mod.rtc = rtc_mod
    mock_modules["livekit.rtc"] = rtc_mod

    # -----------------------------------------------------------------------
    # livekit.agents
    # -----------------------------------------------------------------------
    agents_mod = types.ModuleType("livekit.agents")

    class _MockAgentDefault:
        """Mock for Agent.default — provides default node implementations."""
        @staticmethod
        async def llm_node(agent_self, chat_ctx, tools, model_settings):
            return
            yield  # noqa: makes this an async generator

        @staticmethod
        async def tts_node(agent_self, text_gen, model_settings):
            return
            yield  # noqa: makes this an async generator

    class _MockAgent:
        default = _MockAgentDefault()

        def __init__(self, *args, **kwargs):
            pass

    class _MockAgentSession:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        async def start(self, **kwargs):
            pass

        async def say(self, text, **kwargs):
            pass

        def on(self, event):
            def decorator(fn):
                return fn
            return decorator

    class _MockWorkerOptions:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    agents_mod.Agent = _MockAgent
    agents_mod.AgentSession = _MockAgentSession
    agents_mod.AgentServer = MagicMock
    agents_mod.JobContext = MagicMock
    agents_mod.JobProcess = MagicMock
    agents_mod.WorkerOptions = _MockWorkerOptions
    agents_mod.ModelSettings = MagicMock
    livekit_mod.agents = agents_mod
    mock_modules["livekit.agents"] = agents_mod

    # -----------------------------------------------------------------------
    # livekit.agents.llm
    # -----------------------------------------------------------------------
    llm_mod = types.ModuleType("livekit.agents.llm")
    llm_mod.ChatContext = MagicMock
    llm_mod.ChatChunk = MagicMock
    llm_mod.ChatText = MagicMock
    llm_mod.Tool = MagicMock
    llm_mod.ChoiceDelta = MagicMock
    agents_mod.llm = llm_mod
    mock_modules["livekit.agents.llm"] = llm_mod

    # -----------------------------------------------------------------------
    # livekit.agents.stt
    # -----------------------------------------------------------------------
    stt_mod = types.ModuleType("livekit.agents.stt")

    class _MockSTT:
        def __init__(self, *args, **kwargs):
            pass

    class _MockSpeechStream:
        def __init__(self, *args, **kwargs):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self):
            pass

        def push_frame(self, frame):
            pass

        async def flush(self):
            pass

    class _SpeechEventType:
        FINAL_TRANSCRIPT = "final_transcript"
        INTERIM_TRANSCRIPT = "interim_transcript"
        END_OF_SPEECH = "end_of_speech"

    class _SpeechData:
        def __init__(self, text="", language=""):
            self.text = text
            self.language = language

    class _SpeechEvent:
        def __init__(self, type=None, alternatives=None):
            self.type = type
            self.alternatives = alternatives or []

    stt_mod.STT = _MockSTT
    stt_mod.SpeechStream = _MockSpeechStream
    stt_mod.SpeechEventType = _SpeechEventType
    stt_mod.SpeechData = _SpeechData
    stt_mod.SpeechEvent = _SpeechEvent
    agents_mod.stt = stt_mod
    mock_modules["livekit.agents.stt"] = stt_mod

    # -----------------------------------------------------------------------
    # livekit.agents.cli
    # -----------------------------------------------------------------------
    cli_mod = types.ModuleType("livekit.agents.cli")
    cli_mod.run_app = MagicMock()
    agents_mod.cli = cli_mod
    mock_modules["livekit.agents.cli"] = cli_mod

    # -----------------------------------------------------------------------
    # livekit.plugins.*
    # -----------------------------------------------------------------------
    plugins_mod = types.ModuleType("livekit.plugins")
    mock_modules["livekit.plugins"] = plugins_mod

    for plugin_name in [
        "deepgram", "openai", "silero", "anthropic", "cartesia", "turn_detector",
    ]:
        full_name = f"livekit.plugins.{plugin_name}"
        plugin_mod = types.ModuleType(full_name)
        # Use MagicMock() instances (not the class) so chained attribute access
        # like silero.VAD.load() works via auto-created attrs
        plugin_mod.STT = MagicMock()
        plugin_mod.LLM = MagicMock()
        plugin_mod.TTS = MagicMock()
        plugin_mod.VAD = MagicMock()
        mock_modules[full_name] = plugin_mod
        setattr(plugins_mod, plugin_name, plugin_mod)

    # turn_detector.english submodule
    td_english_mod = types.ModuleType("livekit.plugins.turn_detector.english")
    td_english_mod.EnglishModel = MagicMock
    mock_modules["livekit.plugins.turn_detector.english"] = td_english_mod
    mock_modules["livekit.plugins.turn_detector"].english = td_english_mod

    # -----------------------------------------------------------------------
    # livekit.api (for token generation)
    # -----------------------------------------------------------------------
    api_mod = types.ModuleType("livekit.api")

    class _MockVideoGrants:
        """Mock VideoGrants that stores grant fields for JWT encoding."""
        def __init__(self, **kwargs):
            self.room_join = kwargs.get("room_join", False)
            self.room = kwargs.get("room", "")
            self.can_publish = kwargs.get("can_publish", False)
            self.can_subscribe = kwargs.get("can_subscribe", False)

        def to_dict(self) -> dict:
            result = {}
            if self.room_join:
                result["roomJoin"] = True
            if self.room:
                result["room"] = self.room
            if self.can_publish:
                result["canPublish"] = True
            if self.can_subscribe:
                result["canSubscribe"] = True
            return result

    class _MockAccessToken:
        """Mock AccessToken that produces real JWT strings via pyjwt."""
        def __init__(self, api_key: str = "", api_secret: str = ""):
            self._api_key = api_key
            self._api_secret = api_secret
            self._identity = ""
            self._grants = _MockVideoGrants()

        def with_identity(self, identity: str) -> "_MockAccessToken":
            self._identity = identity
            return self

        def with_grants(self, grants: "_MockVideoGrants") -> "_MockAccessToken":
            self._grants = grants
            return self

        def to_jwt(self) -> str:
            import jwt as _pyjwt
            import time as _time
            now = int(_time.time())
            payload = {
                "iss": self._api_key,
                "sub": self._identity,
                "video": self._grants.to_dict() if hasattr(self._grants, "to_dict") else {},
                "nbf": now,
                "exp": now + 3600,
                "iat": now,
            }
            secret = self._api_secret if self._api_secret else "mock-secret"
            return _pyjwt.encode(payload, secret, algorithm="HS256")

    api_mod.AccessToken = _MockAccessToken
    api_mod.VideoGrants = _MockVideoGrants
    api_mod.LiveKitAPI = MagicMock
    mock_modules["livekit.api"] = api_mod

    # Install all mocks into sys.modules
    for name, mod in mock_modules.items():
        sys.modules[name] = mod


# Install mocks at conftest import time (before test modules are collected)
_install_livekit_mocks()
