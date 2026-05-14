"""Tests for the Navimow error code mapping and custom exceptions."""

from __future__ import annotations

import importlib.util
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Load the errors module directly to avoid homeassistant dependency
_spec = importlib.util.spec_from_file_location(
    "errors", "custom_components/navimow/errors.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["errors"] = _mod
_spec.loader.exec_module(_mod)

VEHICLE_ERROR_CODES = _mod.VEHICLE_ERROR_CODES
MAP_ERROR_CODES = _mod.MAP_ERROR_CODES
get_error_message = _mod.get_error_message
NavimowApiError = _mod.NavimowApiError
NavimowAuthError = _mod.NavimowAuthError
NavimowCommandError = _mod.NavimowCommandError


class TestVehicleErrorCodes:
    """Tests for vehicle error code mapping."""

    def test_vehicle_error_codes_has_69_entries_plus_zero(self) -> None:
        """Vehicle error codes should have entries for 0-69."""
        # Code 0 plus codes 1-69
        assert len(VEHICLE_ERROR_CODES) == 70
        for code in range(70):
            assert code in VEHICLE_ERROR_CODES

    def test_vehicle_error_code_zero_is_no_error(self) -> None:
        """Error code 0 should map to 'No error'."""
        assert VEHICLE_ERROR_CODES[0] == "No error"

    def test_all_vehicle_error_messages_are_non_empty(self) -> None:
        """All vehicle error messages (1-69) should be non-empty strings."""
        for code in range(1, 70):
            msg = VEHICLE_ERROR_CODES[code]
            assert isinstance(msg, str)
            assert len(msg) > 0


class TestMapErrorCodes:
    """Tests for map error code mapping."""

    def test_map_error_codes_has_9_entries_plus_zero(self) -> None:
        """Map error codes should have entries for 0-9."""
        assert len(MAP_ERROR_CODES) == 10
        for code in range(10):
            assert code in MAP_ERROR_CODES

    def test_map_error_code_zero_is_no_error(self) -> None:
        """Error code 0 should map to 'No error'."""
        assert MAP_ERROR_CODES[0] == "No error"

    def test_all_map_error_messages_are_non_empty(self) -> None:
        """All map error messages (1-9) should be non-empty strings."""
        for code in range(1, 10):
            msg = MAP_ERROR_CODES[code]
            assert isinstance(msg, str)
            assert len(msg) > 0


class TestGetErrorMessage:
    """Tests for the get_error_message function."""

    def test_vehicle_error_code_zero_returns_empty_string(self) -> None:
        """Error code 0 should return empty string."""
        assert get_error_message(0) == ""
        assert get_error_message(0, "vehicle") == ""

    def test_map_error_code_zero_returns_empty_string(self) -> None:
        """Map error code 0 should return empty string."""
        assert get_error_message(0, "map") == ""

    def test_valid_vehicle_error_code(self) -> None:
        """Valid vehicle error codes should return their message."""
        assert get_error_message(1) == "Mower lifted"
        assert get_error_message(2) == "Mower stuck"
        assert get_error_message(3) == "Blade motor blocked"

    def test_valid_map_error_code(self) -> None:
        """Valid map error codes should return their message."""
        assert get_error_message(1, "map") == "Map data corrupted"
        assert get_error_message(2, "map") == "Boundary incomplete"
        assert get_error_message(3, "map") == "Zone overlap detected"

    def test_unknown_vehicle_error_code(self) -> None:
        """Unknown vehicle error codes should return a descriptive message."""
        result = get_error_message(100)
        assert "Unknown" in result
        assert "100" in result

    def test_unknown_map_error_code(self) -> None:
        """Unknown map error codes should return a descriptive message."""
        result = get_error_message(99, "map")
        assert "Unknown" in result
        assert "99" in result

    def test_default_error_type_is_vehicle(self) -> None:
        """Default error type should be 'vehicle'."""
        assert get_error_message(1) == get_error_message(1, "vehicle")

    def test_negative_error_code(self) -> None:
        """Negative error codes should return unknown message."""
        result = get_error_message(-1)
        assert "Unknown" in result


class TestCustomExceptions:
    """Tests for custom exception classes."""

    def test_navimow_api_error_basic(self) -> None:
        """NavimowApiError should store message."""
        err = NavimowApiError("test error")
        assert str(err) == "test error"
        assert err.retry_after is None

    def test_navimow_api_error_with_retry_after(self) -> None:
        """NavimowApiError should store retry_after."""
        err = NavimowApiError("rate limited", retry_after=120)
        assert str(err) == "rate limited"
        assert err.retry_after == 120

    def test_navimow_auth_error(self) -> None:
        """NavimowAuthError should be a basic exception."""
        err = NavimowAuthError("auth failed")
        assert str(err) == "auth failed"
        assert isinstance(err, Exception)

    def test_navimow_command_error_basic(self) -> None:
        """NavimowCommandError should store message."""
        err = NavimowCommandError("cannot dock: already docked")
        assert str(err) == "cannot dock: already docked"
        assert err.error_code is None

    def test_navimow_command_error_with_code(self) -> None:
        """NavimowCommandError should store error_code."""
        err = NavimowCommandError("command failed", error_code=42)
        assert str(err) == "command failed"
        assert err.error_code == 42

    def test_exceptions_are_catchable_as_exception(self) -> None:
        """All custom exceptions should be catchable as Exception."""
        with pytest.raises(Exception):
            raise NavimowApiError("test")

        with pytest.raises(Exception):
            raise NavimowAuthError("test")

        with pytest.raises(Exception):
            raise NavimowCommandError("test")


# Feature: navimow-home-assistant, Property 9: Error Code to Message Mapping
class TestErrorCodeMappingProperty:
    """Property-based tests for error code to message mapping.

    **Validates: Requirements 14.2**
    """

    @given(code=st.integers(min_value=1, max_value=69))
    @settings(max_examples=100)
    def test_valid_vehicle_error_codes_return_non_empty_string(self, code: int) -> None:
        """For any valid vehicle error code (1-69), get_error_message returns a non-empty string."""
        result = get_error_message(code)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(code=st.integers(min_value=1, max_value=9))
    @settings(max_examples=100)
    def test_valid_map_error_codes_return_non_empty_string(self, code: int) -> None:
        """For any valid map error code (1-9), get_error_message returns a non-empty string."""
        result = get_error_message(code, "map")
        assert isinstance(result, str)
        assert len(result) > 0

    @given(error_type=st.sampled_from(["vehicle", "map"]))
    @settings(max_examples=100)
    def test_error_code_zero_returns_empty_string(self, error_type: str) -> None:
        """For error code 0, the function returns an empty string for both vehicle and map types."""
        result = get_error_message(0, error_type)
        assert isinstance(result, str)
        assert result == ""

    @given(code=st.integers(min_value=0, max_value=69))
    @settings(max_examples=100)
    def test_vehicle_error_message_is_always_string_type(self, code: int) -> None:
        """The returned message is always a string type for any vehicle error code."""
        result = get_error_message(code)
        assert isinstance(result, str)

    @given(code=st.integers(min_value=0, max_value=9))
    @settings(max_examples=100)
    def test_map_error_message_is_always_string_type(self, code: int) -> None:
        """The returned message is always a string type for any map error code."""
        result = get_error_message(code, "map")
        assert isinstance(result, str)
