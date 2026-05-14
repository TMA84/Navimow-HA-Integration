"""Tests for the Navimow API client."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import pytest_asyncio

# Mock homeassistant modules so the package __init__.py can be imported
_ha_mock = ModuleType("homeassistant")
_ha_mock.config_entries = ModuleType("homeassistant.config_entries")
_ha_mock.config_entries.ConfigEntry = MagicMock
_ha_mock.core = ModuleType("homeassistant.core")
_ha_mock.core.HomeAssistant = MagicMock
sys.modules.setdefault("homeassistant", _ha_mock)
sys.modules.setdefault("homeassistant.config_entries", _ha_mock.config_entries)
sys.modules.setdefault("homeassistant.core", _ha_mock.core)

from custom_components.navimow.api_client import NavimowApiClient, NavimowApiError
from custom_components.navimow.const import API_BASE_URL, REGIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(mock_session, mock_auth) -> NavimowApiClient:
    """Return a NavimowApiClient instance with mocked dependencies."""
    return NavimowApiClient(
        session=mock_session,
        auth=mock_auth,
        region="fra",
    )


def make_response(status: int = 200, json_data: dict | None = None, headers: dict | None = None):
    """Create a mock aiohttp response context manager."""
    response = AsyncMock()
    response.status = status
    response.headers = headers or {"Content-Type": "application/json"}
    response.json = AsyncMock(return_value=json_data or {"code": 0, "data": {}})
    response.raise_for_status = MagicMock()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    return response


# ---------------------------------------------------------------------------
# Regional URL Construction Tests
# ---------------------------------------------------------------------------


class TestBaseUrl:
    """Tests for regional base URL construction."""

    @pytest.mark.parametrize("region", REGIONS)
    def test_base_url_for_all_regions(self, mock_session, mock_auth, region):
        """Test that base_url is correctly constructed for all valid regions."""
        client = NavimowApiClient(session=mock_session, auth=mock_auth, region=region)
        expected = f"https://navimow-{region}.ninebot.com/"
        assert client.base_url == expected

    def test_base_url_format(self, api_client):
        """Test that base_url ends with a slash and uses https."""
        assert api_client.base_url.startswith("https://")
        assert api_client.base_url.endswith("/")
        assert "fra" in api_client.base_url


# ---------------------------------------------------------------------------
# GET Endpoint Tests
# ---------------------------------------------------------------------------


class TestGetEndpoints:
    """Tests for GET API endpoints."""

    @pytest.mark.asyncio
    async def test_get_devices(self, api_client, mock_session):
        """Test get_devices returns list of devices."""
        devices_data = [
            {"device_sn": "NVM123", "name": "Mower 1", "model": "i105", "online": True}
        ]
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": devices_data})
        )
        result = await api_client.get_devices()
        assert result == devices_data

    @pytest.mark.asyncio
    async def test_get_device_info(self, api_client, mock_session):
        """Test get_device_info returns device info dict."""
        info_data = {"device_sn": "NVM123", "model": "i105", "name": "Mower"}
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": info_data})
        )
        result = await api_client.get_device_info("NVM123")
        assert result == info_data

    @pytest.mark.asyncio
    async def test_get_device_data(self, api_client, mock_session):
        """Test get_device_data returns telemetry dict."""
        telemetry = {"battery_level": 80, "state": "mowing"}
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": telemetry})
        )
        result = await api_client.get_device_data("NVM123")
        assert result == telemetry

    @pytest.mark.asyncio
    async def test_get_today_plan(self, api_client, mock_session):
        """Test get_today_plan returns schedule dict."""
        schedule = {"schedule_enabled": True, "next_start": "2024-01-01T08:00:00Z"}
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": schedule})
        )
        result = await api_client.get_today_plan("NVM123")
        assert result == schedule

    @pytest.mark.asyncio
    async def test_get_settings_status(self, api_client, mock_session):
        """Test get_settings_status returns settings dict."""
        settings = {"cutting_height": 40, "rain_sensor": True}
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": settings})
        )
        result = await api_client.get_settings_status("NVM123")
        assert result == settings

    @pytest.mark.asyncio
    async def test_get_location(self, api_client, mock_session):
        """Test get_location returns location dict."""
        location = {"latitude": 51.5, "longitude": -0.1, "data_valid": True}
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": location})
        )
        result = await api_client.get_location("NVM123")
        assert result == location

    @pytest.mark.asyncio
    async def test_get_trail_list(self, api_client, mock_session):
        """Test get_trail_list returns list of trails."""
        trails = [{"trail_id": "t1", "area": 100.0}]
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": trails})
        )
        result = await api_client.get_trail_list("NVM123")
        assert result == trails

    @pytest.mark.asyncio
    async def test_get_trail_detail(self, api_client, mock_session):
        """Test get_trail_detail returns trail detail dict."""
        trail = {"trail_id": "t1", "points": []}
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": trail})
        )
        result = await api_client.get_trail_detail("t1")
        assert result == trail

    @pytest.mark.asyncio
    async def test_get_errors(self, api_client, mock_session):
        """Test get_errors returns list of errors."""
        errors = [{"code": 15, "title": "Lifted"}]
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": errors})
        )
        result = await api_client.get_errors("NVM123")
        assert result == errors

    @pytest.mark.asyncio
    async def test_get_firmware_info(self, api_client, mock_session):
        """Test get_firmware_info returns firmware dict."""
        firmware = {"update_available": True, "new_version": "1.3.0"}
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": firmware})
        )
        result = await api_client.get_firmware_info("NVM123")
        assert result == firmware

    @pytest.mark.asyncio
    async def test_get_bms_detail(self, api_client, mock_session):
        """Test get_bms_detail returns BMS dict."""
        bms = {"voltage": 25.6, "cycles": 142}
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": bms})
        )
        result = await api_client.get_bms_detail("NVM123")
        assert result == bms


# ---------------------------------------------------------------------------
# Command Endpoint Tests
# ---------------------------------------------------------------------------


class TestCommandEndpoints:
    """Tests for command API endpoints."""

    @pytest.mark.asyncio
    async def test_send_command_success(self, api_client, mock_session):
        """Test send_command returns True on success."""
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0})
        )
        result = await api_client.send_command("NVM123", "MOWER_HANDLE_MOW")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_command_with_params(self, api_client, mock_session):
        """Test send_command passes params correctly."""
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0})
        )
        result = await api_client.send_command(
            "NVM123", "MOWER_HANDLE_MOW", params={"zone": "zone_1"}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_command_failure(self, api_client, mock_session):
        """Test send_command returns False on API error code."""
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": -1, "message": "Invalid state"})
        )
        result = await api_client.send_command("NVM123", "MOWER_HANDLE_MOW")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_setting_success(self, api_client, mock_session):
        """Test set_setting returns True on success."""
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0})
        )
        result = await api_client.set_setting("NVM123", "cutting_height", 40)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_power_success(self, api_client, mock_session):
        """Test set_power returns True on success."""
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0})
        )
        result = await api_client.set_power("NVM123", "on")
        assert result is True


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for HTTP error handling."""

    @pytest.mark.asyncio
    async def test_401_triggers_token_refresh_and_retry(self, api_client, mock_session, mock_auth):
        """Test that 401 response triggers token refresh and retries."""
        # First call returns 401, second (after refresh) returns 200
        response_401 = make_response(status=401)
        response_200 = make_response(json_data={"code": 0, "data": {"ok": True}})

        # The first request context returns 401, the retry returns 200
        mock_session.request = MagicMock(side_effect=[response_401, response_200])

        result = await api_client.get_device_info("NVM123")
        assert result == {"ok": True}
        mock_auth.async_refresh_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_401_after_refresh_raises_error(self, api_client, mock_session, mock_auth):
        """Test that 401 after token refresh raises NavimowApiError."""
        response_401 = make_response(status=401)

        # Both the initial and retry requests return 401
        mock_session.request = MagicMock(side_effect=[response_401, response_401])

        with pytest.raises(NavimowApiError, match="Authentication failed"):
            await api_client.get_device_info("NVM123")

    @pytest.mark.asyncio
    async def test_429_raises_with_retry_after(self, api_client, mock_session):
        """Test that 429 response raises NavimowApiError with retry_after."""
        response_429 = make_response(
            status=429, headers={"Retry-After": "120"}
        )
        mock_session.request = MagicMock(return_value=response_429)

        with pytest.raises(NavimowApiError) as exc_info:
            await api_client.get_devices()
        assert exc_info.value.retry_after == 120

    @pytest.mark.asyncio
    async def test_429_default_retry_after_when_header_missing(self, api_client, mock_session):
        """Test that 429 without Retry-After header defaults to 60s."""
        response_429 = make_response(status=429, headers={})
        mock_session.request = MagicMock(return_value=response_429)

        with pytest.raises(NavimowApiError) as exc_info:
            await api_client.get_devices()
        assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_429_invalid_retry_after_defaults_to_60(self, api_client, mock_session):
        """Test that 429 with invalid Retry-After defaults to 60s."""
        response_429 = make_response(status=429, headers={"Retry-After": "not-a-number"})
        mock_session.request = MagicMock(return_value=response_429)

        with pytest.raises(NavimowApiError) as exc_info:
            await api_client.get_devices()
        assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_5xx_retries_with_backoff(self, api_client, mock_session):
        """Test that 5xx errors retry up to MAX_RETRIES times."""
        response_500 = make_response(status=500)
        mock_session.request = MagicMock(return_value=response_500)

        with patch("custom_components.navimow.api_client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(NavimowApiError, match="Server error 500"):
                await api_client.get_devices()

    @pytest.mark.asyncio
    async def test_5xx_succeeds_on_retry(self, api_client, mock_session):
        """Test that 5xx error followed by success returns data."""
        response_500 = make_response(status=500)
        response_200 = make_response(json_data={"code": 0, "data": [{"sn": "NVM1"}]})

        mock_session.request = MagicMock(side_effect=[response_500, response_200])

        with patch("custom_components.navimow.api_client.asyncio.sleep", new_callable=AsyncMock):
            result = await api_client.get_devices()
        assert result == [{"sn": "NVM1"}]

    @pytest.mark.asyncio
    async def test_network_error_retries(self, api_client, mock_session):
        """Test that network errors retry with backoff."""
        mock_session.request = MagicMock(
            side_effect=aiohttp.ClientError("Connection refused")
        )

        with patch("custom_components.navimow.api_client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(NavimowApiError, match="Network error"):
                await api_client.get_devices()

    @pytest.mark.asyncio
    async def test_network_error_succeeds_on_retry(self, api_client, mock_session):
        """Test that network error followed by success returns data."""
        response_200 = make_response(json_data={"code": 0, "data": {"ok": True}})

        mock_session.request = MagicMock(
            side_effect=[aiohttp.ClientError("timeout"), response_200]
        )

        with patch("custom_components.navimow.api_client.asyncio.sleep", new_callable=AsyncMock):
            result = await api_client.get_device_info("NVM123")
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_4xx_raises_immediately(self, api_client, mock_session):
        """Test that 4xx errors (other than 401/429) raise immediately without retry."""
        response_403 = make_response(status=403)
        mock_session.request = MagicMock(return_value=response_403)

        with pytest.raises(NavimowApiError, match="status 403"):
            await api_client.get_devices()


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_data_field(self, api_client, mock_session):
        """Test handling of response with missing data field."""
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0})
        )
        result = await api_client.get_devices()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_trail_list_empty(self, api_client, mock_session):
        """Test get_trail_list with no trails."""
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": []})
        )
        result = await api_client.get_trail_list("NVM123")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_errors_empty(self, api_client, mock_session):
        """Test get_errors with no active errors."""
        mock_session.request = MagicMock(
            return_value=make_response(json_data={"code": 0, "data": []})
        )
        result = await api_client.get_errors("NVM123")
        assert result == []


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# ---------------------------------------------------------------------------

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from custom_components.navimow.auth import NavimowAuth
from custom_components.navimow.const import PASSPORT_BASE_URL, REGIONS


# Feature: navimow-home-assistant, Property 1: Regional URL Construction
class TestPropertyRegionalUrlConstruction:
    """Property-based tests for regional URL construction.

    **Validates: Requirements 1.5**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(region=st.sampled_from(["fra", "ore", "sg", "bj", "mos"]))
    def test_api_base_url_matches_region(self, mock_session, mock_auth, region):
        """For any valid region, the API base URL equals https://navimow-{region}.ninebot.com/."""
        client = NavimowApiClient(session=mock_session, auth=mock_auth, region=region)
        expected = f"https://navimow-{region}.ninebot.com/"
        assert client.base_url == expected

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(region=st.sampled_from(["fra", "ore", "sg", "bj", "mos"]))
    def test_passport_url_matches_region(self, mock_session, mock_auth, region):
        """For any valid region, the passport URL equals https://api-passport-{region}.ninebot.com/."""
        expected = f"https://api-passport-{region}.ninebot.com/"
        # Verify via the PASSPORT_BASE_URL constant (same mechanism used by NavimowAuth)
        assert PASSPORT_BASE_URL.format(region=region) == expected

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(region=st.sampled_from(["fra", "ore", "sg", "bj", "mos"]))
    def test_api_base_url_uses_https(self, mock_session, mock_auth, region):
        """For any valid region, the API base URL uses HTTPS."""
        client = NavimowApiClient(session=mock_session, auth=mock_auth, region=region)
        assert client.base_url.startswith("https://")

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(region=st.sampled_from(["fra", "ore", "sg", "bj", "mos"]))
    def test_api_base_url_ends_with_slash(self, mock_session, mock_auth, region):
        """For any valid region, the API base URL ends with a trailing slash."""
        client = NavimowApiClient(session=mock_session, auth=mock_auth, region=region)
        assert client.base_url.endswith("/")


# Feature: navimow-home-assistant, Property 10: Rate Limit Backoff Duration
class TestPropertyRateLimitBackoffDuration:
    """Property-based tests for rate limit backoff duration.

    **Validates: Requirements 17.4**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(retry_after_value=st.integers(min_value=1, max_value=3600))
    @pytest.mark.asyncio
    async def test_retry_after_header_respected(self, mock_session, mock_auth, retry_after_value):
        """For any 429 response with a positive Retry-After header, backoff equals that value."""
        client = NavimowApiClient(session=mock_session, auth=mock_auth, region="fra")

        response_429 = make_response(
            status=429, headers={"Retry-After": str(retry_after_value)}
        )
        mock_session.request = MagicMock(return_value=response_429)

        with pytest.raises(NavimowApiError) as exc_info:
            await client.get_devices()
        assert exc_info.value.retry_after == retry_after_value

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(invalid_header=st.sampled_from(["", "abc", "not-a-number", "-1.5", "3.14", "NaN"]))
    @pytest.mark.asyncio
    async def test_unparseable_retry_after_defaults_to_60(self, mock_session, mock_auth, invalid_header):
        """If Retry-After header is unparseable, backoff defaults to 60 seconds."""
        client = NavimowApiClient(session=mock_session, auth=mock_auth, region="fra")

        response_429 = make_response(
            status=429, headers={"Retry-After": invalid_header} if invalid_header else {}
        )
        mock_session.request = MagicMock(return_value=response_429)

        with pytest.raises(NavimowApiError) as exc_info:
            await client.get_devices()
        assert exc_info.value.retry_after == 60

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(retry_after_value=st.integers(min_value=1, max_value=3600))
    @pytest.mark.asyncio
    async def test_backoff_duration_never_negative(self, mock_session, mock_auth, retry_after_value):
        """The backoff duration is never negative for any valid Retry-After value."""
        client = NavimowApiClient(session=mock_session, auth=mock_auth, region="fra")

        response_429 = make_response(
            status=429, headers={"Retry-After": str(retry_after_value)}
        )
        mock_session.request = MagicMock(return_value=response_429)

        with pytest.raises(NavimowApiError) as exc_info:
            await client.get_devices()
        assert exc_info.value.retry_after >= 0

    @pytest.mark.asyncio
    async def test_absent_retry_after_header_defaults_to_60(self, mock_session, mock_auth):
        """If Retry-After header is absent, backoff defaults to 60 seconds."""
        client = NavimowApiClient(session=mock_session, auth=mock_auth, region="fra")

        response_429 = make_response(status=429, headers={})
        mock_session.request = MagicMock(return_value=response_429)

        with pytest.raises(NavimowApiError) as exc_info:
            await client.get_devices()
        assert exc_info.value.retry_after == 60
