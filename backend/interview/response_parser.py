"""Parses LLM responses and extracts spoken text + state updates."""

import json
import logging
import re
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parses Claude's JSON responses with fallback to raw text."""
    
    def parse(self, raw_response: str) -> Tuple[str, Optional[str], Optional[Dict[str, str]]]:
        """
        Parse LLM response and extract spoken text + phase + constraint updates.
        
        Args:
            raw_response: Raw text from LLM
            
        Returns:
            Tuple of (spoken_text, phase, updated_constraints)
            - spoken_text: What the interviewer should say
            - phase: New phase (or None if no change)
            - updated_constraints: New locked constraints (or None if no update)
        """
        try:
            # Try to parse as JSON
            parsed = json.loads(raw_response.strip())
            
            # Extract phase
            phase = parsed.get("phase")
            
            # Extract spoken text (handles constraint_summary)
            spoken_text = self._build_spoken_text(parsed)
            
            # Extract constraint updates
            updated_constraints = parsed.get("update_locked_constraints")
            
            return spoken_text, phase, updated_constraints
            
        except json.JSONDecodeError as e:
            # JSON parsing failed - use fallback
            logger.warning(f"JSON parse failed: {e}. Using raw text fallback.")
            return self._fallback_parse(raw_response)
    
    def _build_spoken_text(self, parsed: Dict) -> str:
        """
        Build natural spoken text from parsed JSON.
        
        Handles three cases:
        1. constraint_summary present (phase transition) → use summary + question
        2. interviewer_says present → use acknowledgment + question
        3. Just question → use question only
        """
        constraint_summary = parsed.get("constraint_summary", "")
        interviewer_says = parsed.get("interviewer_says", "")
        question = parsed.get("question", "")
        
        parts = []
        
        # Priority: constraint_summary replaces interviewer_says
        if constraint_summary:
            parts.append(constraint_summary)
        elif interviewer_says:
            parts.append(interviewer_says)
        
        if question:
            parts.append(question)
        
        return " ".join(parts).strip()
    
    def _extract_fields_regex(self, raw_response: str) -> Optional[Tuple[str, Optional[str], Optional[Dict[str, str]]]]:
        """Try to extract key fields using regex when JSON is malformed."""
        phase = None
        interviewer_says = ""
        question = ""
        constraint_summary = ""
        
        # Extract phase
        phase_match = re.search(r'"phase"\s*:\s*"([^"]+)"', raw_response)
        if phase_match:
            phase = phase_match.group(1)
        
        # Extract interviewer_says
        says_match = re.search(r'"interviewer_says"\s*:\s*"([^"]*)"', raw_response)
        if says_match:
            interviewer_says = says_match.group(1)
        
        # Extract question
        q_match = re.search(r'"question"\s*:\s*"([^"]*)"', raw_response)
        if q_match:
            question = q_match.group(1)
        
        # Extract constraint_summary
        summary_match = re.search(r'"constraint_summary"\s*:\s*"([^"]*)"', raw_response)
        if summary_match:
            constraint_summary = summary_match.group(1)
        
        # Extract constraints
        constraints = None
        constraint_match = re.search(r'"update_locked_constraints"\s*:\s*(\{[^}]+\})', raw_response)
        if constraint_match:
            try:
                constraints = json.loads(constraint_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Only return if we got at least a question or acknowledgment
        if question or interviewer_says or constraint_summary:
            parts = []
            if constraint_summary:
                parts.append(constraint_summary)
            elif interviewer_says:
                parts.append(interviewer_says)
            if question:
                parts.append(question)
            spoken_text = " ".join(parts)
            return spoken_text, phase, constraints
        
        return None
    
    def _fallback_parse(self, raw_response: str) -> Tuple[str, None, None]:
        """
        Fallback when JSON parsing fails.
        
        Try to extract JSON from markdown code blocks.
        If that fails, use raw text and skip state updates.
        """
        # Try to extract JSON from markdown code blocks
        if "```json" in raw_response:
            try:
                start = raw_response.index("```json") + 7
                end = raw_response.index("```", start)
                json_text = raw_response[start:end].strip()
                parsed = json.loads(json_text)
                
                phase = parsed.get("phase")
                spoken_text = self._build_spoken_text(parsed)
                updated_constraints = parsed.get("update_locked_constraints")
                
                logger.info("Recovered JSON from markdown code block")
                return spoken_text, phase, updated_constraints
                
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"Markdown JSON extraction failed: {e}")
        
        # Try regex extraction for malformed JSON
        regex_result = self._extract_fields_regex(raw_response)
        if regex_result:
            logger.info("Recovered fields via regex extraction")
            return regex_result
        
        # Last resort: use raw text, strip any JSON artifacts
        clean_text = self._clean_raw_text(raw_response)
        
        logger.info(f"Fallback to raw text: {clean_text[:100]}...")
        
        # Return raw text, no state updates
        return clean_text, None, None
    
    def _clean_raw_text(self, raw_text: str) -> str:
        """Clean raw text of JSON artifacts."""
        clean_text = raw_text.strip()
        
        # If it looks like malformed JSON, try to extract text content
        if clean_text.startswith("{"):
            # Try to extract values that look like speech
            lines = []
            for line in clean_text.split("\n"):
                line = line.strip()
                
                # Skip JSON structure and ALL internal-only fields
                skip_prefixes = (
                    "{", "}", "[", "]", "```",
                    '"phase"', '"update_locked_constraints"',
                    '"what_im_listening_for"', '"followup_if_vague"',
                    '"constraint_summary"',
                )
                if any(line.startswith(p) for p in skip_prefixes):
                    continue
                
                # Extract quoted values
                if '":' in line:
                    try:
                        value = line.split('":"', 1)[1].rstrip('",')
                        if value and not value.startswith(("{", "[")):
                            lines.append(value)
                    except IndexError:
                        pass
            
            if lines:
                clean_text = " ".join(lines)
        
        # Remove surrounding quotes if present
        clean_text = clean_text.strip('"')
        
        return clean_text
