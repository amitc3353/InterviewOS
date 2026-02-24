"""Parses LLM responses and extracts spoken text + state updates."""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Tags that are spoken aloud (sent to TTS)
_SPOKEN_TAGS = {"ACK", "Q", "SUMMARY"}

# Tags that update state internally (never spoken)
_INTERNAL_TAGS = {"PHASE", "LOCK", "LISTEN", "FOLLOWUP"}

_TAG_PATTERN = re.compile(r'\[([A-Z]+):([^\]]*)\]')


class StreamingResponseParser:
    """
    Parses inline tag responses from Claude in real-time.

    Usage:
        parser = StreamingResponseParser()
        async for chunk in llm_stream:
            spoken = parser.feed(chunk)
            if spoken:
                yield spoken_to_tts(spoken)
        final = parser.flush()
        if final:
            yield spoken_to_tts(final)
        phase, constraints = parser.get_state_updates()
        full_text = parser.get_spoken_text()

    Automatically falls back to JSON parsing if Claude returns JSON instead of tags.
    """

    def __init__(self):
        self.buffer = ""
        self._phase: Optional[str] = None
        self._locks: List[str] = []          # raw "key=value" strings
        self._spoken_parts: List[str] = []   # ordered spoken fragments (for history)
        self._has_summary = False            # True once [SUMMARY:...] is processed
        self._processed_up_to = 0           # buffer index of last fully processed tag end
        self._is_json_mode = False          # True if Claude returned JSON accidentally
        self._json_buffer = ""             # accumulates full response for JSON fallback
        self._json_parser = _JsonResponseParser()
        self._json_fallback_result: Optional[Tuple[str, Optional[str], Optional[Dict]]] = None

    def feed(self, chunk: str) -> Optional[str]:
        """
        Feed a streamed chunk. Returns spoken text if a spoken tag ([ACK], [Q],
        [SUMMARY]) just completed, or None if no new spoken text yet.

        Handles tags spanning multiple chunks transparently.
        """
        self.buffer += chunk
        self._json_buffer += chunk

        # Auto-detect JSON mode on first meaningful content
        if not self._is_json_mode and not self._spoken_parts and self._phase is None:
            stripped = self._json_buffer.lstrip()
            if stripped and stripped[0] == '{':
                self._is_json_mode = True
                logger.info("Detected JSON response — activating JSON fallback parser")
                return None

        if self._is_json_mode:
            return None  # Buffer everything; parse in flush()

        return self._extract_completed_tags()

    def _extract_completed_tags(self) -> Optional[str]:
        """Scan buffer for complete [TAG:value] patterns. Return new spoken text."""
        spoken_output: List[str] = []
        last_match_end = self._processed_up_to

        for match in _TAG_PATTERN.finditer(self.buffer, self._processed_up_to):
            tag = match.group(1)
            value = match.group(2).strip()
            last_match_end = match.end()

            if tag == "PHASE":
                self._phase = value

            elif tag == "LOCK":
                if value and "=" in value:
                    self._locks.append(value)

            elif tag == "SUMMARY":
                self._has_summary = True
                self._spoken_parts.append(value)
                spoken_output.append(value)

            elif tag == "ACK":
                # Suppress ACK if SUMMARY already spoken this turn
                if not self._has_summary:
                    self._spoken_parts.append(value)
                    spoken_output.append(value)

            elif tag == "Q":
                self._spoken_parts.append(value)
                spoken_output.append(value)

            # LISTEN and FOLLOWUP: silently discard

        # Advance processed pointer; trim fully-consumed buffer
        self._processed_up_to = last_match_end
        self.buffer = self.buffer[self._processed_up_to:]
        self._processed_up_to = 0

        return " ".join(spoken_output) if spoken_output else None

    def flush(self) -> Optional[str]:
        """
        Called after the stream ends. Handles two cases:
        1. JSON mode: runs full JSON parse on buffered content.
        2. Tag mode: processes any remaining buffer (handles truncated tags).

        Returns any final spoken text not yet yielded, or None.
        """
        if self._is_json_mode:
            spoken, phase, constraints = self._json_parser.parse(self._json_buffer)
            self._phase = phase
            if constraints:
                for key, value in constraints.items():
                    self._locks.append(f"{key}={value}")
            if spoken and spoken not in self._spoken_parts:
                self._spoken_parts.append(spoken)
            return spoken or None

        # Tag mode: anything left in buffer after all tags were processed
        # is likely stray text or a truncated tag — discard safely
        remaining = self.buffer.strip()
        if remaining and not remaining.startswith("["):
            logger.warning(f"Discarding stray text outside tags: {remaining[:60]!r}")
        self.buffer = ""
        return None

    def get_state_updates(self) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
        """
        After stream completes, return (phase, constraints).

        Call this AFTER flush() to ensure JSON fallback results are included.
        """
        phase = self._phase
        constraints: Dict[str, str] = {}
        for lock_str in self._locks:
            if "=" in lock_str:
                key, _, value = lock_str.partition("=")
                constraints[key.strip()] = value.strip()
        return phase, constraints if constraints else None

    def get_spoken_text(self) -> str:
        """Full spoken text for recording in conversation history."""
        return " ".join(self._spoken_parts).strip()


class _JsonResponseParser:
    """
    Legacy JSON parser — fallback for when Claude accidentally returns JSON.
    Preserves all original ResponseParser logic exactly.
    """

    def parse(self, raw_response: str) -> Tuple[str, Optional[str], Optional[Dict[str, str]]]:
        try:
            parsed = json.loads(raw_response.strip())
            phase = parsed.get("phase")
            spoken_text = self._build_spoken_text(parsed)
            updated_constraints = parsed.get("update_locked_constraints")
            return spoken_text, phase, updated_constraints
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}. Trying fallback.")
            return self._fallback_parse(raw_response)

    def _build_spoken_text(self, parsed: Dict) -> str:
        constraint_summary = parsed.get("constraint_summary", "")
        interviewer_says = parsed.get("interviewer_says", "")
        question = parsed.get("question", "")
        parts = []
        if constraint_summary:
            parts.append(constraint_summary)
        elif interviewer_says:
            parts.append(interviewer_says)
        if question:
            parts.append(question)
        return " ".join(parts).strip()

    def _fallback_parse(self, raw_response: str) -> Tuple[str, None, None]:
        # Try markdown code block
        if "```json" in raw_response:
            try:
                start = raw_response.index("```json") + 7
                end = raw_response.index("```", start)
                parsed = json.loads(raw_response[start:end].strip())
                return (
                    self._build_spoken_text(parsed),
                    parsed.get("phase"),
                    parsed.get("update_locked_constraints"),
                )
            except (ValueError, json.JSONDecodeError):
                pass
        # Regex extraction
        q_match = re.search(r'"question"\s*:\s*"([^"]*)"', raw_response)
        says_match = re.search(r'"interviewer_says"\s*:\s*"([^"]*)"', raw_response)
        phase_match = re.search(r'"phase"\s*:\s*"([^"]+)"', raw_response)
        parts = []
        if says_match and says_match.group(1):
            parts.append(says_match.group(1))
        if q_match and q_match.group(1):
            parts.append(q_match.group(1))
        spoken = " ".join(parts) if parts else raw_response.strip()[:200]
        return spoken, phase_match.group(1) if phase_match else None, None
