"""Tests for structured logging in response_parser.py — JSON parse attempts, fallback paths, success/failure."""

from unittest.mock import MagicMock, patch

import pytest

from backend.interview.response_parser import StreamingResponseParser, _JsonResponseParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parser(session_id: str = "test-session-123", turn_number: int = 5) -> StreamingResponseParser:
    """Create a StreamingResponseParser with session_id and turn_number."""
    return StreamingResponseParser(session_id=session_id, turn_number=turn_number)


# ---------------------------------------------------------------------------
# Tests — JSON Mode Detection Logging
# ---------------------------------------------------------------------------

def test_json_mode_detection_logs_info():
    """JSON mode detection logs parse_json_detected event."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.info = MagicMock()

        parser = _make_parser(session_id="session-json-1", turn_number=7)

        # Feed JSON response (starts with '{')
        parser.feed('{"phase": "architecture", "question": "What about scaling?"}')

        # Verify logging
        assert mock_logger.info.called
        call_args = mock_logger.info.call_args

        assert call_args.kwargs['event_type'] == 'parse_json_detected'
        assert call_args.kwargs['session_id'] == "session-json-1"
        assert call_args.kwargs['turn_number'] == 7


def test_tag_mode_does_not_trigger_json_detection():
    """Tag mode response does not trigger JSON detection."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.info = MagicMock()

        parser = _make_parser()

        # Feed tag response
        parser.feed('[ACK:Okay.] [Q:What database would you use?]')

        # No JSON detection logging
        assert not mock_logger.info.called


# ---------------------------------------------------------------------------
# Tests — JSON Parse Attempt Logging
# ---------------------------------------------------------------------------

def test_json_flush_logs_parse_attempt():
    """flush() in JSON mode logs parse_json_attempt event."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.info = MagicMock()
        mock_logger.debug = MagicMock()

        parser = _make_parser(session_id="session-json-2", turn_number=10)

        # Feed JSON response
        parser.feed('{"question": "How would you handle failures?"}')
        parser.flush()

        # Verify parse attempt logging
        debug_calls = [call for call in mock_logger.debug.call_args_list
                       if call.kwargs.get('event_type') == 'parse_json_attempt']
        assert len(debug_calls) >= 1

        call_args = debug_calls[0]
        assert call_args.kwargs['session_id'] == "session-json-2"
        assert call_args.kwargs['turn_number'] == 10
        assert 'buffer_length' in call_args.kwargs


def test_json_parse_success_logs_debug():
    """Successful JSON parse logs parse_json_success event."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.info = MagicMock()
        mock_logger.debug = MagicMock()

        parser = _make_parser(session_id="session-json-3", turn_number=15)

        # Feed valid JSON
        parser.feed('{"question": "What about caching?", "phase": "architecture"}')
        parser.flush()

        # Verify success logging
        success_calls = [call for call in mock_logger.debug.call_args_list
                         if call.kwargs.get('event_type') == 'parse_json_success']
        assert len(success_calls) >= 1

        call_args = success_calls[0]
        assert call_args.kwargs['session_id'] == "session-json-3"
        assert call_args.kwargs['turn_number'] == 15
        assert 'has_spoken' in call_args.kwargs
        assert 'has_phase' in call_args.kwargs
        assert 'constraints_count' in call_args.kwargs


# ---------------------------------------------------------------------------
# Tests — No-Tag Fallback Logging
# ---------------------------------------------------------------------------

def test_no_tags_fallback_logs_warning():
    """Response with no tags logs parse_no_tags_fallback event."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.warning = MagicMock()

        parser = _make_parser(session_id="session-fallback-1", turn_number=3)

        # Feed plain text (no tags)
        parser.feed('What database would you choose?')
        result = parser.flush()

        assert result == 'What database would you choose?'

        # Verify fallback logging
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args

        assert call_args.kwargs['event_type'] == 'parse_no_tags_fallback'
        assert call_args.kwargs['session_id'] == "session-fallback-1"
        assert call_args.kwargs['turn_number'] == 3
        assert 'text_preview' in call_args.kwargs


def test_stray_text_logs_warning():
    """Stray text after tags logs parse_stray_text event."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.warning = MagicMock()

        parser = _make_parser(session_id="session-stray-1", turn_number=8)

        # Feed tags + stray text
        parser.feed('[Q:What about scaling?] Some extra text here')
        parser.flush()

        # Verify stray text warning
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args

        assert call_args.kwargs['event_type'] == 'parse_stray_text'
        assert call_args.kwargs['session_id'] == "session-stray-1"
        assert call_args.kwargs['turn_number'] == 8
        assert 'text_preview' in call_args.kwargs


# ---------------------------------------------------------------------------
# Tests — _JsonResponseParser Logging
# ---------------------------------------------------------------------------

def test_json_parser_success_logs_debug():
    """_JsonResponseParser successful parse logs parse_json_success."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        parser = _JsonResponseParser(session_id="session-jparser-1", turn_number=12)

        json_response = '{"question": "How do you handle retries?", "phase": "failure"}'
        spoken, phase, constraints = parser.parse(json_response)

        assert spoken == "How do you handle retries?"
        assert phase == "failure"

        # Verify logging
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args

        assert call_args.kwargs['event_type'] == 'parse_json_success'
        assert call_args.kwargs['session_id'] == "session-jparser-1"
        assert call_args.kwargs['turn_number'] == 12
        assert call_args.kwargs['has_phase'] is True
        assert call_args.kwargs['has_spoken'] is True


def test_json_parser_failure_logs_warning():
    """_JsonResponseParser parse failure logs parse_json_failed."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.warning = MagicMock()
        mock_logger.debug = MagicMock()
        mock_logger.info = MagicMock()

        parser = _JsonResponseParser(session_id="session-jparser-2", turn_number=20)

        # Feed malformed JSON
        malformed = '{"question": "What about', "phase": "scope"}'
        spoken, phase, constraints = parser.parse(malformed)

        # Should fall back and still return something
        assert spoken

        # Verify failure logging
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args

        assert call_args.kwargs['event_type'] == 'parse_json_failed'
        assert call_args.kwargs['session_id'] == "session-jparser-2"
        assert call_args.kwargs['turn_number'] == 20
        assert 'error' in call_args.kwargs
        assert 'response_preview' in call_args.kwargs


def test_json_parser_markdown_fallback_logs_debug():
    """_JsonResponseParser markdown fallback logs parse_fallback_markdown."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.debug = MagicMock()
        mock_logger.warning = MagicMock()
        mock_logger.info = MagicMock()

        parser = _JsonResponseParser(session_id="session-markdown", turn_number=5)

        # JSON in markdown code block
        markdown_response = '''```json
{"question": "What about monitoring?", "phase": "deep_dive"}
```'''
        spoken, phase, constraints = parser.parse(markdown_response)

        # Verify markdown fallback logging
        debug_calls = [call for call in mock_logger.debug.call_args_list
                       if call.kwargs.get('event_type') == 'parse_fallback_markdown']
        assert len(debug_calls) >= 1

        call_args = debug_calls[0]
        assert call_args.kwargs['session_id'] == "session-markdown"
        assert call_args.kwargs['turn_number'] == 5


def test_json_parser_markdown_success_logs_info():
    """_JsonResponseParser markdown fallback success logs parse_fallback_success."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.debug = MagicMock()
        mock_logger.warning = MagicMock()
        mock_logger.info = MagicMock()

        parser = _JsonResponseParser(session_id="session-md-success", turn_number=9)

        markdown_response = '''```json
{"question": "How would you scale this?"}
```'''
        spoken, phase, constraints = parser.parse(markdown_response)

        # Verify success logging
        info_calls = [call for call in mock_logger.info.call_args_list
                      if call.kwargs.get('event_type') == 'parse_fallback_success']
        assert len(info_calls) >= 1

        call_args = info_calls[0]
        assert call_args.kwargs['session_id'] == "session-md-success"
        assert call_args.kwargs['turn_number'] == 9
        assert call_args.kwargs['fallback_method'] == 'markdown'


def test_json_parser_regex_fallback_logs_debug():
    """_JsonResponseParser regex fallback logs parse_fallback_regex."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.debug = MagicMock()
        mock_logger.warning = MagicMock()
        mock_logger.info = MagicMock()

        parser = _JsonResponseParser(session_id="session-regex", turn_number=14)

        # Malformed JSON that will trigger regex fallback
        malformed = '{"question": "What database?" "phase": "scope"'
        spoken, phase, constraints = parser.parse(malformed)

        # Verify regex fallback logging
        debug_calls = [call for call in mock_logger.debug.call_args_list
                       if call.kwargs.get('event_type') == 'parse_fallback_regex']
        assert len(debug_calls) >= 1

        call_args = debug_calls[0]
        assert call_args.kwargs['session_id'] == "session-regex"
        assert call_args.kwargs['turn_number'] == 14


def test_json_parser_regex_success_logs_info():
    """_JsonResponseParser regex fallback success logs parse_fallback_success."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.debug = MagicMock()
        mock_logger.warning = MagicMock()
        mock_logger.info = MagicMock()

        parser = _JsonResponseParser(session_id="session-regex-success", turn_number=18)

        # Partial JSON that regex can extract
        partial = '{"question": "Tell me about caching" "phase": "architecture"'
        spoken, phase, constraints = parser.parse(partial)

        # Verify success logging
        info_calls = [call for call in mock_logger.info.call_args_list
                      if call.kwargs.get('event_type') == 'parse_fallback_success']
        assert len(info_calls) >= 1

        call_args = info_calls[0]
        assert call_args.kwargs['session_id'] == "session-regex-success"
        assert call_args.kwargs['turn_number'] == 18
        assert call_args.kwargs['fallback_method'] == 'regex'
        assert 'has_question' in call_args.kwargs
        assert 'has_phase' in call_args.kwargs


# ---------------------------------------------------------------------------
# Tests — Session Context Propagation
# ---------------------------------------------------------------------------

def test_parser_session_id_propagates_to_logs():
    """Parser session_id propagates to all log events."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.info = MagicMock()
        mock_logger.debug = MagicMock()

        custom_session_id = "custom-session-xyz-789"
        parser = _make_parser(session_id=custom_session_id, turn_number=25)

        # Trigger JSON mode
        parser.feed('{"question": "How do you monitor this?"}')
        parser.flush()

        # All log calls should include session_id
        all_calls = mock_logger.info.call_args_list + mock_logger.debug.call_args_list
        for call in all_calls:
            if 'event_type' in call.kwargs:
                assert call.kwargs['session_id'] == custom_session_id


def test_parser_turn_number_propagates_to_logs():
    """Parser turn_number propagates to all log events."""
    with patch('backend.interview.response_parser.logger') as mock_logger:
        mock_logger.info = MagicMock()
        mock_logger.debug = MagicMock()

        custom_turn = 42
        parser = _make_parser(session_id="test", turn_number=custom_turn)

        # Trigger JSON mode
        parser.feed('{"question": "Explain your approach"}')
        parser.flush()

        # All log calls should include turn_number
        all_calls = mock_logger.info.call_args_list + mock_logger.debug.call_args_list
        for call in all_calls:
            if 'event_type' in call.kwargs:
                assert call.kwargs['turn_number'] == custom_turn
