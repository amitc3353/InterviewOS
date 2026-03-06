"""Tests for input validation and sanitization — 25 tests, zero network calls."""

import pytest
from pathlib import Path

from backend.interview.input_validation import (
    sanitize_scenario_name,
    sanitize_candidate_name,
    validate_scenario_id,
    validate_path_within_directory,
    _contains_path_traversal,
    MAX_SCENARIO_NAME_LENGTH,
    MAX_CANDIDATE_NAME_LENGTH,
)


# ---------------------------------------------------------------------------
# Tests: sanitize_scenario_name
# ---------------------------------------------------------------------------

def test_scenario_name_valid_simple():
    """Valid simple scenario name passes through."""
    assert sanitize_scenario_name("Design a URL shortener") == "Design a URL shortener"


def test_scenario_name_valid_with_hyphens():
    """Scenario name with hyphens is valid."""
    assert sanitize_scenario_name("E-commerce inventory system") == "E-commerce inventory system"


def test_scenario_name_valid_with_special_chars():
    """Scenario name with apostrophes, commas, periods is valid."""
    assert sanitize_scenario_name("Design an API gateway (v2)") == "Design an API gateway (v2)"


def test_scenario_name_strips_whitespace():
    """Leading and trailing whitespace is stripped."""
    assert sanitize_scenario_name("  Design a cache  ") == "Design a cache"


def test_scenario_name_collapses_spaces():
    """Multiple internal spaces are collapsed to single space."""
    assert sanitize_scenario_name("Design   a   cache") == "Design a cache"


def test_scenario_name_empty_rejected():
    """Empty scenario name raises ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        sanitize_scenario_name("")


def test_scenario_name_whitespace_only_rejected():
    """Whitespace-only scenario name raises ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        sanitize_scenario_name("   ")


def test_scenario_name_too_long_rejected():
    """Scenario name exceeding max length raises ValueError."""
    long_name = "a" * (MAX_SCENARIO_NAME_LENGTH + 1)
    with pytest.raises(ValueError, match="too long"):
        sanitize_scenario_name(long_name)


def test_scenario_name_path_traversal_rejected():
    """Scenario name with path traversal sequence '../../etc/passwd' is rejected."""
    with pytest.raises(ValueError, match="invalid characters|path traversal"):
        sanitize_scenario_name("../../etc/passwd")


def test_scenario_name_url_encoded_traversal_rejected():
    """URL-encoded path traversal is rejected."""
    with pytest.raises(ValueError, match="invalid characters|path traversal"):
        sanitize_scenario_name("..%2f..%2fetc%2fpasswd")


def test_scenario_name_backslash_rejected():
    """Backslash in scenario name is rejected."""
    with pytest.raises(ValueError, match="invalid characters|path traversal"):
        sanitize_scenario_name("Design\\a\\system")


def test_scenario_name_script_injection_rejected():
    """Script tags in scenario name are rejected."""
    with pytest.raises(ValueError, match="invalid characters"):
        sanitize_scenario_name("<script>alert('xss')</script>")


def test_scenario_name_sql_injection_rejected():
    """SQL injection patterns in scenario name are rejected."""
    with pytest.raises(ValueError, match="invalid characters"):
        sanitize_scenario_name("'; DROP TABLE sessions;--")


# ---------------------------------------------------------------------------
# Tests: sanitize_candidate_name
# ---------------------------------------------------------------------------

def test_candidate_name_valid():
    """Valid candidate name passes through."""
    assert sanitize_candidate_name("Alice Smith") == "Alice Smith"


def test_candidate_name_with_apostrophe():
    """Candidate name with apostrophe (e.g., O'Brien) is valid."""
    assert sanitize_candidate_name("Dr. O'Brien") == "Dr. O'Brien"


def test_candidate_name_none_returns_none():
    """None candidate name returns None."""
    assert sanitize_candidate_name(None) is None


def test_candidate_name_empty_returns_none():
    """Empty string candidate name returns None."""
    assert sanitize_candidate_name("") is None


def test_candidate_name_too_long_rejected():
    """Candidate name exceeding max length raises ValueError."""
    long_name = "a" * (MAX_CANDIDATE_NAME_LENGTH + 1)
    with pytest.raises(ValueError, match="too long"):
        sanitize_candidate_name(long_name)


def test_candidate_name_special_chars_rejected():
    """Candidate name with disallowed chars is rejected."""
    with pytest.raises(ValueError, match="invalid characters"):
        sanitize_candidate_name("<script>alert(1)</script>")


def test_candidate_name_path_traversal_rejected():
    """Candidate name with '..' is rejected."""
    with pytest.raises(ValueError, match="path traversal|invalid characters"):
        sanitize_candidate_name("Dr..")


# ---------------------------------------------------------------------------
# Tests: validate_scenario_id
# ---------------------------------------------------------------------------

def test_scenario_id_valid():
    """Valid scenario ID passes through."""
    assert validate_scenario_id("url-shortener") == "url-shortener"


def test_scenario_id_path_traversal_rejected():
    """Path traversal in scenario ID is rejected."""
    with pytest.raises(ValueError, match="Invalid scenario ID|path traversal"):
        validate_scenario_id("../../etc/passwd")


def test_scenario_id_uppercase_rejected():
    """Uppercase letters in scenario ID are rejected."""
    with pytest.raises(ValueError, match="Invalid scenario ID"):
        validate_scenario_id("URL-Shortener")


def test_scenario_id_empty_rejected():
    """Empty scenario ID is rejected."""
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_scenario_id("")


# ---------------------------------------------------------------------------
# Tests: validate_path_within_directory
# ---------------------------------------------------------------------------

def test_path_within_directory_valid(tmp_path: Path):
    """File within directory passes validation."""
    child = tmp_path / "scenario.yaml"
    child.touch()
    result = validate_path_within_directory(child, tmp_path)
    assert str(result).startswith(str(tmp_path.resolve()))


def test_path_outside_directory_rejected(tmp_path: Path):
    """Path escaping the allowed directory is rejected."""
    escape_path = tmp_path / ".." / ".." / "etc" / "passwd"
    with pytest.raises(ValueError, match="resolves outside"):
        validate_path_within_directory(escape_path, tmp_path)


# ---------------------------------------------------------------------------
# Tests: _contains_path_traversal
# ---------------------------------------------------------------------------

def test_contains_path_traversal_dot_dot():
    """Detects '..' traversal pattern."""
    assert _contains_path_traversal("../../etc/passwd") is True


def test_contains_path_traversal_clean():
    """Clean string returns False."""
    assert _contains_path_traversal("url-shortener") is False
