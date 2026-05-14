"""Tests for the Navimow security module - credential redaction in logs."""

# Feature: navimow-home-assistant, Property 11: Credential Redaction in Logs

import importlib.util
import logging

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Load the security module directly to avoid homeassistant dependency
_spec = importlib.util.spec_from_file_location(
    "security", "custom_components/navimow/security.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
NavimowLogFilter = _mod.NavimowLogFilter


def _make_log_record(msg: str, level: int = logging.INFO) -> logging.LogRecord:
    """Create a logging.LogRecord with the given message."""
    return logging.LogRecord(
        name="custom_components.navimow",
        level=level,
        pathname="security.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )


# Feature: navimow-home-assistant, Property 11: Credential Redaction in Logs
class TestCredentialRedactionProperty:
    """Property-based tests for credential redaction in logs.

    **Validates: Requirements 21.3**
    """

    @given(
        token=st.text(
            min_size=16,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_characters="\x00",
            ),
        ),
    )
    @settings(max_examples=100)
    def test_registered_token_never_appears_in_filtered_log(
        self, token: str
    ) -> None:
        """For any generated token (min 16 chars), after registering it with the
        filter and passing a log record containing that token, the output record
        does NOT contain the literal token value.

        **Validates: Requirements 21.3**
        """
        log_filter = NavimowLogFilter()
        log_filter.add_sensitive_value(token)

        # Create a log record that contains the token
        msg = f"API response received with token {token} in payload"
        record = _make_log_record(msg)

        result = log_filter.filter(record)

        # The token must not appear in the filtered message
        assert token not in record.msg

    @given(
        token=st.text(
            min_size=16,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_characters="\x00",
            ),
        ),
    )
    @settings(max_examples=100)
    def test_filter_always_returns_true(self, token: str) -> None:
        """The filter always returns True (allows the record through) regardless
        of content.

        **Validates: Requirements 21.3**
        """
        log_filter = NavimowLogFilter()
        log_filter.add_sensitive_value(token)

        msg = f"Debug: token={token}"
        record = _make_log_record(msg)

        result = log_filter.filter(record)

        assert result is True

    @given(
        token=st.text(
            min_size=16,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_characters="\x00",
            ),
        ),
    )
    @settings(max_examples=100)
    def test_redacted_text_contains_redacted_marker(self, token: str) -> None:
        """The redacted text contains '[REDACTED]' where the token was.

        **Validates: Requirements 21.3**
        """
        log_filter = NavimowLogFilter()
        log_filter.add_sensitive_value(token)

        msg = f"Using credential: {token}"
        record = _make_log_record(msg)

        log_filter.filter(record)

        # The redacted marker must be present
        assert "[REDACTED]" in record.msg

    @given(
        token=st.text(
            min_size=16,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_characters="\x00",
            ),
        ),
        level=st.sampled_from(
            [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]
        ),
    )
    @settings(max_examples=100)
    def test_redaction_works_at_all_log_levels(
        self, token: str, level: int
    ) -> None:
        """No log message at any level contains literal token values after filtering.

        **Validates: Requirements 21.3**
        """
        log_filter = NavimowLogFilter()
        log_filter.add_sensitive_value(token)

        msg = f"Level {level} message with secret {token} embedded"
        record = _make_log_record(msg, level=level)

        result = log_filter.filter(record)

        assert result is True
        assert token not in record.msg
        assert "[REDACTED]" in record.msg
