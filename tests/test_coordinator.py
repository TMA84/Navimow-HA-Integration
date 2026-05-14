"""Tests for the NavimowCoordinator."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# Mock homeassistant modules so the coordinator can be imported
_ha_mock = ModuleType("homeassistant")
_ha_mock.config_entries = ModuleType("homeassistant.config_entries")
_ha_mock.config_entries.ConfigEntry = MagicMock
_ha_mock.core = ModuleType("homeassistant.core")
_ha_mock.core.HomeAssistant = MagicMock

_ha_helpers = ModuleType("homeassistant.helpers")
_ha_update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")


class _MockDataUpdateCoordinator:
    """Mock DataUpdateCoordinator base class."""

    def __class_getitem__(cls, item):
        """Support generic subscripting like DataUpdateCoordinator[T]."""
        return cls

    def __init__(self, hass, logger, *, name, update_interval, config_entry=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.config_entry = config_entry


class _MockUpdateFailed(Exception):
    """Mock UpdateFailed exception."""

    pass


_ha_update_coordinator.DataUpdateCoordinator = _MockDataUpdateCoordinator
_ha_update_coordinator.UpdateFailed = _MockUpdateFailed

_ha_helpers_aiohttp = ModuleType("homeassistant.helpers.aiohttp_client")
_ha_helpers_aiohttp.async_get_clientsession = MagicMock()

_ha_helpers_device_registry = ModuleType("homeassistant.helpers.device_registry")
_ha_helpers_device_registry.DeviceInfo = dict

_ha_helpers_entity = ModuleType("homeassistant.helpers.entity")
_ha_helpers_entity.EntityDescription = MagicMock

sys.modules.setdefault("homeassistant", _ha_mock)
sys.modules.setdefault("homeassistant.config_entries", _ha_mock.config_entries)
sys.modules.setdefault("homeassistant.core", _ha_mock.core)
sys.modules.setdefault("homeassistant.helpers", _ha_helpers)
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", _ha_helpers_aiohttp)
sys.modules.setdefault("homeassistant.helpers.device_registry", _ha_helpers_device_registry)
sys.modules.setdefault("homeassistant.helpers.entity", _ha_helpers_entity)
sys.modules.setdefault(
    "homeassistant.helpers.update_coordinator", _ha_update_coordinator
)

from custom_components.navimow.api_client import NavimowApiError
from custom_components.navimow.coordinator import (
    ACTIVE_STATES,
    IDLE_STATES,
    NavimowCoordinator,
)
from custom_components.navimow.models import (
    MowerState,
    NavimowDeviceData,
    TaskState,
)

# Get the actual UpdateFailed class that the coordinator uses
_MockUpdateFailed = sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_hass():
    """Return a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Return a mock ConfigEntry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    return entry


@pytest.fixture
def coordinator(mock_hass, mock_config_entry, mock_api_client):
    """Return a NavimowCoordinator instance with mocked dependencies."""
    coord = NavimowCoordinator(
        hass=mock_hass,
        config_entry=mock_config_entry,
        api_client=mock_api_client,
        device_sn="NVM1234567890",
    )
    return coord


# ---------------------------------------------------------------------------
# Polling Interval Tests
# ---------------------------------------------------------------------------


class TestAdjustPollingInterval:
    """Tests for _adjust_polling_interval method."""

    def test_active_states_set_10s_interval(self, coordinator):
        """Active states should set polling to 10 seconds."""
        for state in ACTIVE_STATES:
            coordinator.update_interval = NavimowCoordinator.POLL_INTERVAL_DEFAULT
            coordinator._adjust_polling_interval(state)
            assert coordinator.update_interval == NavimowCoordinator.POLL_INTERVAL_ACTIVE

    def test_idle_states_set_60s_interval(self, coordinator):
        """Idle states should set polling to 60 seconds."""
        for state in IDLE_STATES:
            coordinator.update_interval = NavimowCoordinator.POLL_INTERVAL_DEFAULT
            coordinator._adjust_polling_interval(state)
            assert coordinator.update_interval == NavimowCoordinator.POLL_INTERVAL_IDLE

    def test_other_states_set_30s_interval(self, coordinator):
        """Other states (paused, error) should set polling to 30 seconds."""
        other_states = {MowerState.PAUSED, MowerState.ERROR}
        for state in other_states:
            coordinator.update_interval = NavimowCoordinator.POLL_INTERVAL_IDLE
            coordinator._adjust_polling_interval(state)
            assert coordinator.update_interval == NavimowCoordinator.POLL_INTERVAL_DEFAULT

    def test_no_change_when_interval_already_correct(self, coordinator):
        """Should not log or change if interval is already correct."""
        coordinator.update_interval = NavimowCoordinator.POLL_INTERVAL_ACTIVE
        coordinator._adjust_polling_interval(MowerState.MOWING)
        # Interval should remain the same
        assert coordinator.update_interval == NavimowCoordinator.POLL_INTERVAL_ACTIVE


# ---------------------------------------------------------------------------
# Exponential Backoff Tests
# ---------------------------------------------------------------------------


class TestCalculateBackoff:
    """Tests for _calculate_backoff static method."""

    def test_first_failure_gives_30s(self):
        """First failure should give 30 seconds delay."""
        assert NavimowCoordinator._calculate_backoff(1) == 30

    def test_second_failure_gives_60s(self):
        """Second failure should give 60 seconds delay."""
        assert NavimowCoordinator._calculate_backoff(2) == 60

    def test_third_failure_gives_120s(self):
        """Third failure should give 120 seconds delay."""
        assert NavimowCoordinator._calculate_backoff(3) == 120

    def test_fourth_failure_gives_240s(self):
        """Fourth failure should give 240 seconds delay."""
        assert NavimowCoordinator._calculate_backoff(4) == 240

    def test_fifth_failure_capped_at_300s(self):
        """Fifth failure should be capped at 300 seconds."""
        assert NavimowCoordinator._calculate_backoff(5) == 300

    def test_large_failure_count_capped_at_300s(self):
        """Large failure counts should be capped at 300 seconds."""
        assert NavimowCoordinator._calculate_backoff(10) == 300
        assert NavimowCoordinator._calculate_backoff(20) == 300

    def test_backoff_never_below_30(self):
        """Backoff should never be below 30 seconds."""
        assert NavimowCoordinator._calculate_backoff(1) >= 30

    def test_backoff_never_above_300(self):
        """Backoff should never exceed 300 seconds."""
        for n in range(1, 50):
            assert NavimowCoordinator._calculate_backoff(n) <= 300


# ---------------------------------------------------------------------------
# Data Parsing Tests
# ---------------------------------------------------------------------------


class TestParseDeviceInfo:
    """Tests for _parse_device_info static method."""

    def test_parses_complete_device_info(self, mock_device_info_response):
        """Should parse a complete device info response."""
        raw = mock_device_info_response["data"]
        result = NavimowCoordinator._parse_device_info(raw)

        assert result.device_sn == "NVM1234567890"
        assert result.model == "Navimow i105"
        assert result.name == "Front Yard Mower"
        assert result.firmware_versions.ecu == "1.2.3"
        assert result.firmware_versions.bms == "2.0.1"
        assert result.firmware_versions.vision_fence is None

    def test_handles_missing_fields(self):
        """Should handle missing fields with defaults."""
        raw = {}
        result = NavimowCoordinator._parse_device_info(raw)

        assert result.device_sn == ""
        assert result.model == ""
        assert result.firmware_versions.ecu == "unknown"


class TestParseTelemetry:
    """Tests for _parse_telemetry static method."""

    def test_parses_complete_telemetry(self, mock_telemetry_response):
        """Should parse a complete telemetry response."""
        raw = mock_telemetry_response["data"]
        result = NavimowCoordinator._parse_telemetry(raw)

        assert result.battery_level == 78
        assert result.battery_voltage == 25.6
        assert result.state == MowerState.MOWING
        assert result.work_mode == "standard"
        assert result.task_state == TaskState.SCHEDULED_MOWING
        assert result.mowing_progress == 45

    def test_handles_unknown_state(self):
        """Should default to standby for unknown states."""
        raw = {"state": "unknown_state"}
        result = NavimowCoordinator._parse_telemetry(raw)
        assert result.state == MowerState.STANDBY

    def test_handles_missing_fields(self):
        """Should handle missing fields with defaults."""
        raw = {}
        result = NavimowCoordinator._parse_telemetry(raw)
        assert result.battery_level == 0
        assert result.state == MowerState.STANDBY


class TestParseLocation:
    """Tests for _parse_location static method."""

    def test_parses_complete_location(self, mock_location_response):
        """Should parse a complete location response."""
        raw = mock_location_response["data"]
        result = NavimowCoordinator._parse_location(raw)

        assert result.latitude == 51.5074
        assert result.longitude == -0.1278
        assert result.data_valid is True
        assert result.satellites_in_use == 12


class TestParseSchedule:
    """Tests for _parse_schedule static method."""

    def test_parses_complete_schedule(self, mock_schedule_response):
        """Should parse a complete schedule response."""
        raw = mock_schedule_response["data"]
        result = NavimowCoordinator._parse_schedule(raw)

        assert result.schedule_enabled is True
        assert result.next_start is not None
        assert result.next_end is not None
        assert len(result.schedules) == 1

    def test_handles_empty_schedule(self):
        """Should handle empty schedule data."""
        raw = {"schedule_enabled": False}
        result = NavimowCoordinator._parse_schedule(raw)

        assert result.schedule_enabled is False
        assert result.next_start is None
        assert result.next_end is None
        assert result.schedules == []


class TestParseSettings:
    """Tests for _parse_settings static method."""

    def test_parses_complete_settings(self, mock_settings_response):
        """Should parse a complete settings response."""
        raw = mock_settings_response["data"]
        result = NavimowCoordinator._parse_settings(raw)

        assert result.cutting_height == 40
        assert result.rain_sensor is True
        assert result.anti_interference is None
        assert result.plan_switch is True


class TestParseErrors:
    """Tests for _parse_errors static method."""

    def test_parses_error_list(self, mock_errors_response):
        """Should parse a list of errors."""
        raw = mock_errors_response["data"]
        result = NavimowCoordinator._parse_errors(raw)

        assert len(result) == 1
        assert result[0].code == 15
        assert result[0].title == "Mower lifted"
        assert result[0].severity == 2

    def test_handles_empty_error_list(self):
        """Should handle empty error list."""
        result = NavimowCoordinator._parse_errors([])
        assert result == []


class TestParseTrailList:
    """Tests for _parse_trail_list static method."""

    def test_parses_trail_list(self, mock_trail_list_response):
        """Should parse a trail list response."""
        raw = mock_trail_list_response["data"]
        result = NavimowCoordinator._parse_trail_list(raw)

        assert len(result) == 2
        assert result[0].trail_id == "trail_001"
        assert result[0].duration == 95.0
        assert result[0].area == 350.0


class TestBuildMaintenanceData:
    """Tests for _build_maintenance_data static method."""

    def test_calculates_blade_life_correctly(self):
        """Should calculate blade remaining life percentage."""
        telemetry = MagicMock()
        telemetry.blade_usage_time = 100.0
        telemetry.blade_lifetime_hours = 200.0

        result = NavimowCoordinator._build_maintenance_data(telemetry)

        assert result.blade_remaining_life_pct == 50.0
        assert result.blade_replacement_needed is False
        assert result.maintenance_status == "ok"

    def test_blade_replacement_needed_below_10_percent(self):
        """Should flag replacement needed when below 10%."""
        telemetry = MagicMock()
        telemetry.blade_usage_time = 185.0
        telemetry.blade_lifetime_hours = 200.0

        result = NavimowCoordinator._build_maintenance_data(telemetry)

        assert result.blade_remaining_life_pct == pytest.approx(7.5)
        assert result.blade_replacement_needed is True
        assert result.maintenance_status == "blade_replacement_due"

    def test_blade_life_never_negative(self):
        """Should clamp blade life at 0%."""
        telemetry = MagicMock()
        telemetry.blade_usage_time = 300.0
        telemetry.blade_lifetime_hours = 200.0

        result = NavimowCoordinator._build_maintenance_data(telemetry)

        assert result.blade_remaining_life_pct == 0.0
        assert result.blade_replacement_needed is True


# ---------------------------------------------------------------------------
# Fetch All Data Integration Test
# ---------------------------------------------------------------------------


class TestFetchAllData:
    """Tests for _fetch_all_data method."""

    @pytest.mark.asyncio
    async def test_batches_api_calls(
        self,
        coordinator,
        mock_api_client,
        mock_device_info_response,
        mock_telemetry_response,
        mock_schedule_response,
        mock_settings_response,
        mock_location_response,
        mock_errors_response,
        mock_firmware_response,
        mock_trail_list_response,
    ):
        """Should batch all API calls in a single update cycle."""
        mock_api_client.get_device_info = AsyncMock(
            return_value=mock_device_info_response["data"]
        )
        mock_api_client.get_device_data = AsyncMock(
            return_value=mock_telemetry_response["data"]
        )
        mock_api_client.get_today_plan = AsyncMock(
            return_value=mock_schedule_response["data"]
        )
        mock_api_client.get_settings_status = AsyncMock(
            return_value=mock_settings_response["data"]
        )
        mock_api_client.get_location = AsyncMock(
            return_value=mock_location_response["data"]
        )
        mock_api_client.get_errors = AsyncMock(
            return_value=mock_errors_response["data"]
        )
        mock_api_client.get_firmware_info = AsyncMock(
            return_value=mock_firmware_response["data"]
        )
        mock_api_client.get_trail_list = AsyncMock(
            return_value=mock_trail_list_response["data"]
        )

        result = await coordinator._fetch_all_data()

        assert isinstance(result, NavimowDeviceData)
        assert result.device_info.device_sn == "NVM1234567890"
        assert result.telemetry.battery_level == 78
        assert result.telemetry.state == MowerState.MOWING
        assert result.location.latitude == 51.5074
        assert result.schedule.schedule_enabled is True
        assert result.settings.cutting_height == 40
        assert len(result.errors) == 1
        assert result.firmware.update_available is True
        assert len(result.trail_history) == 2

        # Verify all core API calls were made
        mock_api_client.get_device_info.assert_called_once_with("NVM1234567890")
        mock_api_client.get_device_data.assert_called_once_with("NVM1234567890")
        mock_api_client.get_today_plan.assert_called_once_with("NVM1234567890")
        mock_api_client.get_settings_status.assert_called_once_with("NVM1234567890")
        mock_api_client.get_location.assert_called_once_with("NVM1234567890")
        mock_api_client.get_errors.assert_called_once_with("NVM1234567890")


# ---------------------------------------------------------------------------
# Firmware Check Frequency Tests
# ---------------------------------------------------------------------------


class TestFirmwareCheckFrequency:
    """Tests for firmware check at reduced frequency."""

    @pytest.mark.asyncio
    async def test_checks_firmware_on_first_call(
        self, coordinator, mock_api_client, mock_firmware_response
    ):
        """Should check firmware on the first call."""
        mock_api_client.get_firmware_info = AsyncMock(
            return_value=mock_firmware_response["data"]
        )

        result = await coordinator._fetch_firmware_if_due()

        assert result.update_available is True
        mock_api_client.get_firmware_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_firmware_check_within_interval(
        self, coordinator, mock_api_client, mock_firmware_response
    ):
        """Should skip firmware check if within the hour interval."""
        mock_api_client.get_firmware_info = AsyncMock(
            return_value=mock_firmware_response["data"]
        )

        # First call - should fetch
        await coordinator._fetch_firmware_if_due()
        mock_api_client.get_firmware_info.reset_mock()

        # Second call immediately after - should use cache
        result = await coordinator._fetch_firmware_if_due()

        assert result.update_available is True
        mock_api_client.get_firmware_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_checks_firmware_after_interval_elapsed(
        self, coordinator, mock_api_client, mock_firmware_response
    ):
        """Should check firmware again after the interval has elapsed."""
        mock_api_client.get_firmware_info = AsyncMock(
            return_value=mock_firmware_response["data"]
        )

        # First call
        await coordinator._fetch_firmware_if_due()
        mock_api_client.get_firmware_info.reset_mock()

        # Simulate time passing beyond the interval
        coordinator._last_firmware_check = datetime.now(
            tz=timezone.utc
        ) - timedelta(hours=2)

        # Should fetch again
        await coordinator._fetch_firmware_if_due()
        mock_api_client.get_firmware_info.assert_called_once()


# ---------------------------------------------------------------------------
# Trail History Fetch Frequency Tests
# ---------------------------------------------------------------------------


class TestTrailFetchFrequency:
    """Tests for trail history fetch at reduced frequency."""

    @pytest.mark.asyncio
    async def test_fetches_trail_on_first_call(
        self, coordinator, mock_api_client, mock_trail_list_response
    ):
        """Should fetch trail history on the first call."""
        mock_api_client.get_trail_list = AsyncMock(
            return_value=mock_trail_list_response["data"]
        )

        result = await coordinator._fetch_trail_if_due({})

        assert len(result) == 2
        mock_api_client.get_trail_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetches_trail_on_task_completion(
        self, coordinator, mock_api_client, mock_trail_list_response
    ):
        """Should fetch trail history when task completes."""
        mock_api_client.get_trail_list = AsyncMock(
            return_value=mock_trail_list_response["data"]
        )

        # Set up previous state as mowing
        coordinator._previous_task_state = TaskState.SCHEDULED_MOWING
        # Set last fetch to recent (within interval)
        coordinator._last_trail_fetch = datetime.now(tz=timezone.utc)

        # Simulate task completion
        result = await coordinator._fetch_trail_if_due(
            {"task_state": "completed"}
        )

        assert len(result) == 2
        mock_api_client.get_trail_list.assert_called_once()


# ---------------------------------------------------------------------------
# State Change Detection Tests
# ---------------------------------------------------------------------------


class TestDetectStateChanges:
    """Tests for _detect_state_changes method."""

    def test_fires_error_event_on_new_error(self, coordinator, mock_hass):
        """Should fire navimow_error event when entering error state."""
        coordinator._previous_state = MowerState.MOWING

        data = MagicMock()
        data.telemetry.state = MowerState.ERROR
        data.telemetry.task_state = TaskState.NO_TASK
        data.errors = [
            MagicMock(code=15, title="Mower lifted", content="Lifted", severity=2)
        ]

        coordinator._detect_state_changes(data)

        mock_hass.bus.async_fire.assert_called_with(
            "navimow_error",
            {
                "device_sn": "NVM1234567890",
                "code": 15,
                "title": "Mower lifted",
                "content": "Lifted",
                "severity": 2,
            },
        )

    def test_fires_completion_event_on_task_complete(self, coordinator, mock_hass):
        """Should fire navimow_mowing_complete event on task completion."""
        coordinator._previous_task_state = TaskState.SCHEDULED_MOWING

        data = MagicMock()
        data.telemetry.state = MowerState.CHARGING
        data.telemetry.task_state = TaskState.COMPLETED
        data.telemetry.current_mowing_area = 350.0
        data.telemetry.total_mowing_time = 95.0
        data.errors = []

        coordinator._detect_state_changes(data)

        mock_hass.bus.async_fire.assert_called_with(
            "navimow_mowing_complete",
            {
                "device_sn": "NVM1234567890",
                "area": 350.0,
                "total_mowing_time": 95.0,
            },
        )

    def test_no_event_when_already_in_error_state(self, coordinator, mock_hass):
        """Should not fire error event if already in error state."""
        coordinator._previous_state = MowerState.ERROR

        data = MagicMock()
        data.telemetry.state = MowerState.ERROR
        data.telemetry.task_state = TaskState.NO_TASK
        data.errors = [MagicMock(code=15)]

        coordinator._detect_state_changes(data)

        mock_hass.bus.async_fire.assert_not_called()


# ---------------------------------------------------------------------------
# Failure Tracking Tests
# ---------------------------------------------------------------------------


class TestFailureTracking:
    """Tests for consecutive failure tracking and backoff."""

    @pytest.mark.asyncio
    async def test_raises_update_failed_after_3_failures(
        self, coordinator, mock_api_client
    ):
        """Should raise UpdateFailed after 3 consecutive failures."""
        mock_api_client.get_device_info = AsyncMock(
            side_effect=NavimowApiError("Network error")
        )
        coordinator._consecutive_failures = 2  # Already had 2 failures

        with pytest.raises(_MockUpdateFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_applies_backoff_on_failure(self, coordinator, mock_api_client):
        """Should apply exponential backoff on failure."""
        mock_api_client.get_device_info = AsyncMock(
            side_effect=NavimowApiError("Network error")
        )

        with pytest.raises(_MockUpdateFailed):
            await coordinator._async_update_data()

        # After first failure, backoff should be 30s
        assert coordinator.update_interval == timedelta(seconds=30)
        assert coordinator._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_resets_failures_on_success(
        self,
        coordinator,
        mock_api_client,
        mock_device_info_response,
        mock_telemetry_response,
        mock_schedule_response,
        mock_settings_response,
        mock_location_response,
        mock_errors_response,
        mock_firmware_response,
        mock_trail_list_response,
    ):
        """Should reset failure counter on successful update."""
        coordinator._consecutive_failures = 2

        mock_api_client.get_device_info = AsyncMock(
            return_value=mock_device_info_response["data"]
        )
        mock_api_client.get_device_data = AsyncMock(
            return_value=mock_telemetry_response["data"]
        )
        mock_api_client.get_today_plan = AsyncMock(
            return_value=mock_schedule_response["data"]
        )
        mock_api_client.get_settings_status = AsyncMock(
            return_value=mock_settings_response["data"]
        )
        mock_api_client.get_location = AsyncMock(
            return_value=mock_location_response["data"]
        )
        mock_api_client.get_errors = AsyncMock(
            return_value=mock_errors_response["data"]
        )
        mock_api_client.get_firmware_info = AsyncMock(
            return_value=mock_firmware_response["data"]
        )
        mock_api_client.get_trail_list = AsyncMock(
            return_value=mock_trail_list_response["data"]
        )

        result = await coordinator._async_update_data()

        assert coordinator._consecutive_failures == 0
        assert isinstance(result, NavimowDeviceData)


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


# Feature: navimow-home-assistant, Property 4: State-to-Polling-Interval Mapping
class TestPollingIntervalMappingProperty:
    """Property-based tests for state-to-polling-interval mapping.

    **Validates: Requirements 3.2, 3.3**
    """

    @given(state=st.sampled_from(MowerState))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_active_states_map_to_10s(self, state, coordinator):
        """Active states (mowing, returning, mapping, calibrating) → 10s polling."""
        assume(state in ACTIVE_STATES)
        coordinator.update_interval = NavimowCoordinator.POLL_INTERVAL_DEFAULT
        coordinator._adjust_polling_interval(state)
        assert coordinator.update_interval == timedelta(seconds=10)

    @given(state=st.sampled_from(MowerState))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_idle_states_map_to_60s(self, state, coordinator):
        """Idle states (charging, standby, idle_parking) → 60s polling."""
        assume(state in IDLE_STATES)
        coordinator.update_interval = NavimowCoordinator.POLL_INTERVAL_DEFAULT
        coordinator._adjust_polling_interval(state)
        assert coordinator.update_interval == timedelta(seconds=60)

    @given(state=st.sampled_from(MowerState))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_other_states_map_to_30s(self, state, coordinator):
        """Other states (paused, error) → 30s polling."""
        assume(state not in ACTIVE_STATES and state not in IDLE_STATES)
        coordinator.update_interval = NavimowCoordinator.POLL_INTERVAL_IDLE
        coordinator._adjust_polling_interval(state)
        assert coordinator.update_interval == timedelta(seconds=30)

    @given(state=st.sampled_from(MowerState))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_mapping_is_total(self, state, coordinator):
        """Every MowerState maps to exactly one interval (10s, 30s, or 60s)."""
        coordinator.update_interval = timedelta(seconds=0)
        coordinator._adjust_polling_interval(state)
        assert coordinator.update_interval in {
            timedelta(seconds=10),
            timedelta(seconds=30),
            timedelta(seconds=60),
        }


# Feature: navimow-home-assistant, Property 5: Exponential Backoff Calculation
class TestExponentialBackoffProperty:
    """Property-based tests for exponential backoff calculation.

    **Validates: Requirements 3.5**
    """

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=100)
    def test_backoff_matches_formula(self, n):
        """For any N >= 1, delay equals min(30 * 2^(N-1), 300)."""
        expected = min(30 * (2 ** (n - 1)), 300)
        actual = NavimowCoordinator._calculate_backoff(n)
        assert actual == expected

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=100)
    def test_backoff_never_exceeds_300(self, n):
        """The delay never exceeds 300 seconds."""
        delay = NavimowCoordinator._calculate_backoff(n)
        assert delay <= 300

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=100)
    def test_backoff_never_below_30(self, n):
        """The delay never falls below 30 seconds."""
        delay = NavimowCoordinator._calculate_backoff(n)
        assert delay >= 30
