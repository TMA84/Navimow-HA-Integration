"""Security utilities for the Navimow integration."""

from __future__ import annotations

import logging
import re


# Patterns that match common token/password formats in log output
_TOKEN_PATTERNS = [
    # Bearer tokens (long alphanumeric strings)
    re.compile(r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"),
    # Generic long hex/base64 tokens (32+ chars)
    re.compile(r"(?:access_token|refresh_token|token|password|secret)[\"':\s=]+([^\s\"',}{]+)"),
    # OAuth tokens in URL params
    re.compile(r"(?:access_token|refresh_token|token|password)=([^&\s]+)"),
]

# Minimum token length to redact (avoid false positives on short strings)
_MIN_TOKEN_LENGTH = 16


class NavimowLogFilter(logging.Filter):
    """Log filter that redacts tokens and passwords from log output.

    This filter scans log messages for patterns that look like tokens,
    passwords, or other sensitive credentials and replaces them with
    [REDACTED].
    """

    def __init__(self, sensitive_values: list[str] | None = None) -> None:
        """Initialize the log filter.

        Args:
            sensitive_values: Optional list of known sensitive values to redact.
                These are exact string values (e.g., the current access token)
                that should always be redacted from log output.
        """
        super().__init__()
        self._sensitive_values: list[str] = sensitive_values or []

    def add_sensitive_value(self, value: str) -> None:
        """Add a sensitive value to the redaction list.

        Args:
            value: The sensitive string value to redact from logs.
        """
        if value and len(value) >= _MIN_TOKEN_LENGTH and value not in self._sensitive_values:
            self._sensitive_values.append(value)

    def remove_sensitive_value(self, value: str) -> None:
        """Remove a sensitive value from the redaction list.

        Args:
            value: The sensitive string value to stop redacting.
        """
        if value in self._sensitive_values:
            self._sensitive_values.remove(value)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter a log record by redacting sensitive values.

        Args:
            record: The log record to filter.

        Returns:
            True (always allows the record through, but with redacted content).
        """
        if record.msg:
            record.msg = self._redact(str(record.msg))

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        return True

    def _redact(self, text: str) -> str:
        """Redact sensitive values from a text string.

        Args:
            text: The text to redact.

        Returns:
            Text with sensitive values replaced by [REDACTED].
        """
        # First, redact known sensitive values (exact match)
        for value in self._sensitive_values:
            if value in text:
                text = text.replace(value, "[REDACTED]")

        # Then apply pattern-based redaction
        for pattern in _TOKEN_PATTERNS:
            text = pattern.sub(
                lambda m: m.group(0).replace(m.group(1), "[REDACTED]")
                if m.lastindex and len(m.group(1)) >= _MIN_TOKEN_LENGTH
                else m.group(0),
                text,
            )

        return text
