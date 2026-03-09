"""Tests for AgentConfig — new fields and from_env() loading."""

import os
from unittest.mock import patch

import pytest

from backend.config import AgentConfig


# ---------------------------------------------------------------------------
# Tests: new config fields (cartesia_speed, vad_sensitivity)
# ---------------------------------------------------------------------------

def test_config_defaults():
    """AgentConfig has correct defaults for new fields."""
    config = AgentConfig(
        livekit_url="ws://localhost",
        livekit_api_key="key",
        livekit_api_secret="secret",
        deepgram_api_key="dgk",
        anthropic_api_key="ak",
        openai_api_key="ok",
        cartesia_api_key="ck",
    )
    assert config.cartesia_speed == 0.85
    assert config.vad_sensitivity == 0.5


def test_config_from_env_cartesia_speed():
    """from_env() reads CARTESIA_SPEED from environment."""
    env = {
        "LIVEKIT_URL": "ws://test",
        "LIVEKIT_API_KEY": "k",
        "LIVEKIT_API_SECRET": "s",
        "DEEPGRAM_API_KEY": "d",
        "ANTHROPIC_API_KEY": "a",
        "OPENAI_API_KEY": "o",
        "CARTESIA_API_KEY": "c",
        "CARTESIA_SPEED": "1.2",
    }
    with patch.dict(os.environ, env, clear=True):
        config = AgentConfig.from_env()
    assert config.cartesia_speed == 1.2


def test_config_from_env_vad_sensitivity():
    """from_env() reads VAD_SENSITIVITY from environment."""
    env = {
        "LIVEKIT_URL": "ws://test",
        "LIVEKIT_API_KEY": "k",
        "LIVEKIT_API_SECRET": "s",
        "DEEPGRAM_API_KEY": "d",
        "ANTHROPIC_API_KEY": "a",
        "OPENAI_API_KEY": "o",
        "CARTESIA_API_KEY": "c",
        "VAD_SENSITIVITY": "0.8",
    }
    with patch.dict(os.environ, env, clear=True):
        config = AgentConfig.from_env()
    assert config.vad_sensitivity == 0.8


def test_config_from_env_defaults_when_not_set():
    """from_env() uses defaults when CARTESIA_SPEED and VAD_SENSITIVITY not set."""
    env = {
        "LIVEKIT_URL": "ws://test",
        "LIVEKIT_API_KEY": "k",
        "LIVEKIT_API_SECRET": "s",
        "DEEPGRAM_API_KEY": "d",
        "ANTHROPIC_API_KEY": "a",
        "OPENAI_API_KEY": "o",
        "CARTESIA_API_KEY": "c",
    }
    with patch.dict(os.environ, env, clear=True):
        config = AgentConfig.from_env()
    assert config.cartesia_speed == 0.85
    assert config.vad_sensitivity == 0.5


def test_config_validate_success():
    """validate() returns True when all required keys are set."""
    config = AgentConfig(
        livekit_url="ws://localhost:7880",
        livekit_api_key="APIkey123",
        livekit_api_secret="APIsecret456",
        deepgram_api_key="dg_real_key",
        anthropic_api_key="sk-ant-real",
        openai_api_key="sk-real",
        cartesia_api_key="cart_real",
    )
    assert config.validate() is True


def test_config_validate_fails_missing_key():
    """validate() returns False when a required key is empty."""
    config = AgentConfig(
        livekit_url="",
        livekit_api_key="key",
        livekit_api_secret="secret",
        deepgram_api_key="dgk",
        anthropic_api_key="ak",
        openai_api_key="ok",
        cartesia_api_key="ck",
    )
    assert config.validate() is False


def test_config_validate_fails_placeholder():
    """validate() returns False when a key has a placeholder value."""
    config = AgentConfig(
        livekit_url="ws://localhost",
        livekit_api_key="your_api_key_here",
        livekit_api_secret="secret",
        deepgram_api_key="dgk",
        anthropic_api_key="ak",
        openai_api_key="ok",
        cartesia_api_key="ck",
    )
    assert config.validate() is False
