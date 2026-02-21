"""Locked constraints - facts established in conversation that shouldn't be re-asked."""

from typing import Dict, Any, Optional


class LockedConstraints:
    """
    Track facts established during interview.

    Once a fact is locked, the interviewer should never re-ask it.
    """

    def __init__(self):
        """Initialize empty constraints."""
        self.constraints: Dict[str, Any] = {}

    def lock(self, key: str, value: Any) -> None:
        """
        Lock a constraint.

        Args:
            key: Constraint name (tps_peak, payment_method, etc.)
            value: The established value
        """
        if key not in self.constraints:
            self.constraints[key] = value

    def get(self, key: str) -> Optional[Any]:
        """Get a locked constraint value."""
        return self.constraints.get(key)

    def has(self, key: str) -> bool:
        """Check if a constraint is locked."""
        return key in self.constraints

    def to_dict(self) -> Dict[str, Any]:
        """Export as dict."""
        return self.constraints.copy()

    def to_prompt_text(self) -> str:
        """
        Format for LLM prompt.

        Returns text listing all locked facts so LLM doesn't re-ask.
        """
        if not self.constraints:
            return "No locked constraints yet."

        lines = ["LOCKED CONSTRAINTS (DO NOT RE-ASK):"]
        for key, value in self.constraints.items():
            lines.append(f"- {key}: {value}")

        return "\n".join(lines)
