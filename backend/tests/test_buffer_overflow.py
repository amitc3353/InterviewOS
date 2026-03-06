"""Tests for buffer overflow prevention logic — MAX_CHAT_CTX_ITEMS hard cap.

These tests validate the trimming algorithm without importing InterviewAgent
(which requires LiveKit runtime). The logic is tested as pure functions.
"""

import pytest
from unittest.mock import Mock


# ---------------------------------------------------------------------------
# Constants (mirrored from interview_agent.py)
# ---------------------------------------------------------------------------

MAX_HISTORY_MESSAGES = 18   # 9 turns (user + assistant pairs)
MAX_CHAT_CTX_ITEMS = 50     # Hard cap on total items


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(role: str, content: str = "test") -> Mock:
    """Create a mock chat context item with a role attribute."""
    item = Mock()
    item.role = role
    item.content = content
    return item


def _build_items(system_count: int, non_system_count: int) -> list:
    """Build a list of system and non-system mock items."""
    items = []
    for i in range(system_count):
        items.append(_make_item("system", f"system-{i}"))
    for i in range(non_system_count):
        role = "user" if i % 2 == 0 else "assistant"
        items.append(_make_item(role, f"{role}-{i}"))
    return items


def _apply_trimming(items: list) -> tuple:
    """
    Apply the same trimming logic as InterviewAgent.llm_node.

    Returns:
        (result_items, trimmed_count, trigger) where trigger is
        'hard_cap', 'normal', or 'none'.
    """
    system_items = [
        item for item in items
        if hasattr(item, 'role') and item.role == "system"
    ]
    non_system_items = [
        item for item in items
        if not (hasattr(item, 'role') and item.role == "system")
    ]

    trigger = "none"
    trimmed_count = 0

    if len(items) > MAX_CHAT_CTX_ITEMS:
        # Hard cap: aggressive trim
        keep_count = min(MAX_HISTORY_MESSAGES, MAX_CHAT_CTX_ITEMS - len(system_items))
        trimmed_count = len(non_system_items) - keep_count
        non_system_items = non_system_items[-keep_count:]
        trigger = "hard_cap"
    elif len(non_system_items) > MAX_HISTORY_MESSAGES:
        # Normal trim
        trimmed_count = len(non_system_items) - MAX_HISTORY_MESSAGES
        non_system_items = non_system_items[-MAX_HISTORY_MESSAGES:]
        trigger = "normal"

    result_items = system_items + non_system_items
    return result_items, trimmed_count, trigger


# ---------------------------------------------------------------------------
# Tests — No trimming needed
# ---------------------------------------------------------------------------

def test_no_trimming_under_both_limits():
    """No trimming when under both MAX_HISTORY_MESSAGES and MAX_CHAT_CTX_ITEMS."""
    items = _build_items(system_count=2, non_system_count=10)
    result, trimmed, trigger = _apply_trimming(items)

    assert len(result) == 12  # Unchanged
    assert trimmed == 0
    assert trigger == "none"


def test_no_trimming_at_exact_max_history():
    """No trimming when non-system items exactly equal MAX_HISTORY_MESSAGES."""
    items = _build_items(system_count=2, non_system_count=MAX_HISTORY_MESSAGES)
    result, trimmed, trigger = _apply_trimming(items)

    assert len(result) == 2 + MAX_HISTORY_MESSAGES
    assert trimmed == 0
    assert trigger == "none"


# ---------------------------------------------------------------------------
# Tests — Normal trimming (under hard cap)
# ---------------------------------------------------------------------------

def test_normal_trimming_over_max_history():
    """Normal trimming when over MAX_HISTORY_MESSAGES but under hard cap."""
    items = _build_items(system_count=2, non_system_count=25)
    result, trimmed, trigger = _apply_trimming(items)

    assert len(result) == 2 + MAX_HISTORY_MESSAGES  # 2 system + 18 kept
    assert trimmed == 25 - MAX_HISTORY_MESSAGES  # 7 trimmed
    assert trigger == "normal"


def test_normal_trimming_keeps_recent_messages():
    """Normal trimming keeps the most recent non-system messages."""
    items = _build_items(system_count=1, non_system_count=25)

    # Tag each non-system item with an index for tracking
    non_system = [i for i in items if i.role != "system"]
    for idx, item in enumerate(non_system):
        item.index = idx

    result, _, trigger = _apply_trimming(items)
    assert trigger == "normal"

    # Get non-system items from result
    result_non_system = [i for i in result if i.role != "system"]

    # Should have kept the last MAX_HISTORY_MESSAGES items
    assert result_non_system[0].index == 25 - MAX_HISTORY_MESSAGES
    assert result_non_system[-1].index == 24


# ---------------------------------------------------------------------------
# Tests — Hard cap trimming
# ---------------------------------------------------------------------------

def test_hard_cap_triggers_at_51_items():
    """Hard cap triggers when total items exceed 50."""
    items = _build_items(system_count=2, non_system_count=49)
    assert len(items) == 51  # Over hard cap

    result, trimmed, trigger = _apply_trimming(items)

    assert trigger == "hard_cap"
    assert len(result) <= MAX_CHAT_CTX_ITEMS
    assert trimmed > 0


def test_hard_cap_does_not_trigger_at_50_items():
    """Hard cap does NOT trigger at exactly 50 items."""
    items = _build_items(system_count=2, non_system_count=48)
    assert len(items) == 50  # Exactly at cap

    _, _, trigger = _apply_trimming(items)

    # At exactly 50, the hard cap condition (> 50) does NOT trigger.
    # But normal trimming may still apply since 48 > 18.
    assert trigger != "hard_cap"


def test_hard_cap_aggressive_trim():
    """Hard cap aggressively trims to under the 50-item limit."""
    items = _build_items(system_count=3, non_system_count=55)
    assert len(items) == 58  # Well over hard cap

    result, trimmed, trigger = _apply_trimming(items)

    assert trigger == "hard_cap"
    assert len(result) <= MAX_CHAT_CTX_ITEMS
    assert trimmed == 55 - min(MAX_HISTORY_MESSAGES, MAX_CHAT_CTX_ITEMS - 3)


def test_hard_cap_preserves_all_system_messages():
    """Hard cap never trims system messages."""
    items = _build_items(system_count=10, non_system_count=45)
    assert len(items) == 55

    result, _, trigger = _apply_trimming(items)

    system_in_result = [i for i in result if i.role == "system"]
    assert len(system_in_result) == 10  # All system messages kept
    assert trigger == "hard_cap"


def test_hard_cap_with_many_system_messages_reduces_non_system():
    """Many system messages reduce available space for non-system items."""
    items = _build_items(system_count=35, non_system_count=20)
    assert len(items) == 55  # Over hard cap

    result, trimmed, trigger = _apply_trimming(items)

    assert trigger == "hard_cap"

    # keep_count = min(18, 50 - 35) = min(18, 15) = 15
    expected_keep = min(MAX_HISTORY_MESSAGES, MAX_CHAT_CTX_ITEMS - 35)
    assert expected_keep == 15

    non_system_in_result = [i for i in result if i.role != "system"]
    assert len(non_system_in_result) == expected_keep
    assert trimmed == 20 - expected_keep


def test_hard_cap_keeps_most_recent():
    """Hard cap keeps the most recent non-system messages."""
    items = _build_items(system_count=2, non_system_count=55)

    non_system = [i for i in items if i.role != "system"]
    for idx, item in enumerate(non_system):
        item.index = idx

    result, _, trigger = _apply_trimming(items)
    assert trigger == "hard_cap"

    result_non_system = [i for i in result if i.role != "system"]
    keep_count = min(MAX_HISTORY_MESSAGES, MAX_CHAT_CTX_ITEMS - 2)

    # Verify we kept the LAST keep_count items
    assert result_non_system[0].index == 55 - keep_count
    assert result_non_system[-1].index == 54


# ---------------------------------------------------------------------------
# Tests — Source verification
# ---------------------------------------------------------------------------

def test_constants_match_source():
    """Verify our test constants match the actual source code."""
    import re

    source_path = "backend/agents/interview_agent.py"
    with open(source_path) as f:
        source = f.read()

    # Check MAX_HISTORY_MESSAGES
    match = re.search(r'MAX_HISTORY_MESSAGES\s*=\s*(\d+)', source)
    assert match, "MAX_HISTORY_MESSAGES not found in source"
    assert int(match.group(1)) == MAX_HISTORY_MESSAGES

    # Check MAX_CHAT_CTX_ITEMS
    match = re.search(r'MAX_CHAT_CTX_ITEMS\s*=\s*(\d+)', source)
    assert match, "MAX_CHAT_CTX_ITEMS not found in source"
    assert int(match.group(1)) == MAX_CHAT_CTX_ITEMS


def test_source_has_memory_profiling():
    """Source code includes session memory profiling at 5-turn intervals."""
    source_path = "backend/agents/interview_agent.py"
    with open(source_path) as f:
        source = f.read()

    assert "session_memory_profile" in source
    assert "total_turn_count % 5 == 0" in source
    assert "get_memory_stats" in source
