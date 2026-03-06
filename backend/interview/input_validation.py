"""Input validation and sanitization for user-supplied data.

Prevents path traversal, injection attacks, and enforces safe character sets
for scenario names, session IDs, and general user input.
"""

import os
import re
from pathlib import Path
from typing import Optional

from ..structured_logging import get_logger

logger = get_logger(__name__)

# Scenario names: letters, digits, spaces, hyphens, apostrophes, commas, periods
# Matches patterns like "Design a URL shortener" or "E-commerce inventory system"
_SCENARIO_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 \-',.\(\)]+$")

# Maximum lengths
MAX_SCENARIO_NAME_LENGTH = 200
MAX_CANDIDATE_NAME_LENGTH = 100


def sanitize_scenario_name(name: str) -> str:
    """
    Validate and sanitize a scenario name.

    Allows alphanumeric characters, spaces, hyphens, apostrophes, commas,
    periods, and parentheses. Strips leading/trailing whitespace and
    collapses multiple spaces.

    Args:
        name: Raw scenario name from user input

    Returns:
        Sanitized scenario name

    Raises:
        ValueError: If name is empty, too long, or contains invalid characters
    """
    if not name or not name.strip():
        raise ValueError("Scenario name cannot be empty")

    name = name.strip()

    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)

    if len(name) > MAX_SCENARIO_NAME_LENGTH:
        raise ValueError(
            f"Scenario name too long ({len(name)} chars, max {MAX_SCENARIO_NAME_LENGTH})"
        )

    if not _SCENARIO_NAME_PATTERN.match(name):
        raise ValueError(
            f"Scenario name contains invalid characters. "
            f"Only letters, numbers, spaces, hyphens, apostrophes, "
            f"commas, periods, and parentheses are allowed."
        )

    # Reject path traversal patterns even if they match the regex
    if _contains_path_traversal(name):
        raise ValueError("Scenario name contains path traversal characters")

    return name


def sanitize_candidate_name(name: Optional[str]) -> Optional[str]:
    """
    Validate and sanitize a candidate name.

    Args:
        name: Raw candidate name, or None

    Returns:
        Sanitized name or None

    Raises:
        ValueError: If name is too long or contains invalid characters
    """
    if name is None:
        return None

    name = name.strip()
    if not name:
        return None

    if len(name) > MAX_CANDIDATE_NAME_LENGTH:
        raise ValueError(
            f"Candidate name too long ({len(name)} chars, max {MAX_CANDIDATE_NAME_LENGTH})"
        )

    # Allow letters, spaces, hyphens, apostrophes, periods (e.g., "Dr. O'Brien")
    if not re.match(r"^[a-zA-Z0-9 \-'.]+$", name):
        raise ValueError(
            "Candidate name contains invalid characters. "
            "Only letters, numbers, spaces, hyphens, apostrophes, and periods are allowed."
        )

    # Reject path traversal patterns even if they match the regex
    if _contains_path_traversal(name):
        raise ValueError("Candidate name contains path traversal characters")

    return name


def validate_scenario_id(scenario_id: str) -> str:
    """
    Validate a scenario ID for safe use in file lookups.

    Scenario IDs should be lowercase alphanumeric with hyphens only
    (e.g., "url-shortener", "payment-gateway").

    Args:
        scenario_id: Raw scenario ID

    Returns:
        Validated scenario ID

    Raises:
        ValueError: If ID is invalid or contains path traversal
    """
    if not scenario_id or not scenario_id.strip():
        raise ValueError("Scenario ID cannot be empty")

    scenario_id = scenario_id.strip()

    if not re.match(r"^[a-z0-9\-]+$", scenario_id):
        raise ValueError(
            f"Invalid scenario ID '{scenario_id}'. "
            f"Only lowercase letters, numbers, and hyphens are allowed."
        )

    if _contains_path_traversal(scenario_id):
        raise ValueError("Scenario ID contains path traversal characters")

    return scenario_id


def validate_path_within_directory(file_path: Path, allowed_dir: Path) -> Path:
    """
    Ensure a file path resolves within the allowed directory.

    Prevents path traversal attacks by resolving symlinks and checking
    that the resolved path starts with the allowed directory.

    Args:
        file_path: Path to validate
        allowed_dir: Directory the file must be within

    Returns:
        Resolved absolute path

    Raises:
        ValueError: If path escapes allowed directory
    """
    resolved = file_path.resolve()
    allowed = allowed_dir.resolve()

    if not str(resolved).startswith(str(allowed) + os.sep) and resolved != allowed:
        raise ValueError(
            f"Path '{file_path}' resolves outside allowed directory '{allowed_dir}'"
        )

    return resolved


def _contains_path_traversal(value: str) -> bool:
    """Check if a string contains path traversal patterns."""
    # Check for directory traversal sequences
    traversal_patterns = [
        "..",
        "/",
        "\\",
        "%2e",  # URL-encoded dot
        "%2f",  # URL-encoded forward slash
        "%5c",  # URL-encoded backslash
    ]
    value_lower = value.lower()
    return any(pattern in value_lower for pattern in traversal_patterns)
