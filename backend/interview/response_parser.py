"""Parses LLM responses and extracts spoken text + state updates."""

import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parses Claude's JSON responses with fallback to raw text."""
    
    def parse(self, raw_response: str) -> Tuple[str, Optional[List[str]]]:
        """
        Parse LLM response and extract spoken text + constraint updates.
        
        Args:
            raw_response: Raw text from LLM
            
        Returns:
            Tuple of (spoken_text, updated_constraints)
            - spoken_text: What the interviewer should say
            - updated_constraints: New locked constraints (or None if no update)
        """
        try:
            # Try to parse as JSON
            parsed = json.loads(raw_response.strip())
            
            # Extract spoken text
            interviewer_says = parsed.get("interviewer_says", "")
            question = parsed.get("question", "")
            spoken_text = self._build_spoken_text(interviewer_says, question)
            
            # Extract constraint updates
            updated_constraints = parsed.get("update_locked_constraints")
            
            return spoken_text, updated_constraints
            
        except json.JSONDecodeError as e:
            # JSON parsing failed - use fallback
            logger.warning(f"JSON parse failed: {e}. Using raw text fallback.")
            return self._fallback_parse(raw_response)
    
    def _build_spoken_text(self, interviewer_says: str, question: str) -> str:
        """Build natural spoken text from components."""
        parts = []
        
        if interviewer_says:
            parts.append(interviewer_says)
        
        if question:
            parts.append(question)
        
        return " ".join(parts).strip()
    
    def _fallback_parse(self, raw_response: str) -> Tuple[str, None]:
        """
        Fallback when JSON parsing fails.
        
        Extract whatever text is there and use it directly.
        Skip state updates to avoid corruption.
        """
        # Try to extract JSON from markdown code blocks
        if "```json" in raw_response:
            try:
                start = raw_response.index("```json") + 7
                end = raw_response.index("```", start)
                json_text = raw_response[start:end].strip()
                parsed = json.loads(json_text)
                
                interviewer_says = parsed.get("interviewer_says", "")
                question = parsed.get("question", "")
                spoken_text = self._build_spoken_text(interviewer_says, question)
                updated_constraints = parsed.get("update_locked_constraints")
                
                return spoken_text, updated_constraints
            except (ValueError, json.JSONDecodeError):
                pass
        
        # Last resort: use raw text, strip any JSON artifacts
        clean_text = raw_response.strip()
        
        # Remove common JSON-like artifacts
        if clean_text.startswith("{"):
            # Try to extract just the text values
            lines = [
                line.strip()
                for line in clean_text.split("\n")
                if not line.strip().startswith(("{", "}", '"phase":', '"update_locked_constraints":'))
            ]
            clean_text = " ".join(lines)
        
        # Remove quotes if present
        clean_text = clean_text.strip('"')
        
        logger.info(f"Fallback text: {clean_text[:100]}...")
        
        return clean_text, None
