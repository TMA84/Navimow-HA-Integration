"""Property-based tests for blade life calculation.

# Feature: navimow-home-assistant, Property 12: Blade Remaining Life Calculation
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Mock homeassistant modules so the coordinator can be imported
# ---------------------------------------------------------------------------

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

from custom_components.navimow.coordinator import NavimowCoordinator
from custom_components.navimow.models import (
    DeviceTelemetry,
    MowerState,
    TaskState,
    WorkMode,
)


# ---------------------------------------------------------------------------
# Helper to build a DeviceTelemetry with specific blade values
# ---------------------------------------------------------------------------


def _make_telemetry(usage: float, lifetime: float) -> DeviceTelemetry:
    """Create a DeviceTelemetry instance with given blade usage and lifetime."""
    return DeviceTelemetry(
        battery_level=80,
        battery_voltage=25.0,
        battery_temperature_fault=False,
        state=MowerState.STANDBY,
        work_mode=WorkMode.STANDARD,
        task_state=TaskState.NO_TASK,
        mowing_progress=0,
        current_mowing_area=0.0,
        total_mowing_area=0.0,
        blade_usage_time=usage,
        blade_lifetime_hours=lifetime,
        total_mowing_time=0.0,
        network_type="4G",
        cellular_signal=20,
        mqtt_connected=True,
        wifi_ssid=None,
    )


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


# Feature: navimow-home-assistant, Property 12: Blade Remaining Life Calculation
class TestBladeRemainingLifeCalculation:
    """Property-based tests for blade remaining life calculation.

    **Validates: Requirements 20.2, 20.3**
    """

    @given(
        usage=st.floats(min_value=0, max_value=1000),
        lifetime=st.floats(min_value=1, max_value=500),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_remaining_life_matches_formula(self, usage: float, lifetime: float):
        """For any U >= 0 and L > 0, remaining_life = max(0, (1 - U/L) * 100)."""
        telemetry = _make_telemetry(usage, lifetime)
        result = NavimowCoordinator._build_maintenance_data(telemetry)

        expected = max(0.0, (1 - usage / lifetime) * 100)
        assert result.blade_remaining_life_pct == pytest.approx(expected), (
            f"Expected {expected}, got {result.blade_remaining_life_pct} "
            f"for usage={usage}, lifetime={lifetime}"
        )

    @given(
        usage=st.floats(min_value=0, max_value=1000),
        lifetime=st.floats(min_value=1, max_value=500),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_result_always_in_0_to_100(self, usage: float, lifetime: float):
        """The result is always in [0, 100]."""
        telemetry = _make_telemetry(usage, lifetime)
        result = NavimowCoordinator._build_maintenance_data(telemetry)

        assert 0.0 <= result.blade_remaining_life_pct <= 100.0, (
            f"blade_remaining_life_pct={result.blade_remaining_life_pct} "
            f"is outside [0, 100] for usage={usage}, lifetime={lifetime}"
        )

    @given(
        usage=st.floats(min_value=0, max_value=1000),
        lifetime=st.floats(min_value=1, max_value=500),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_blade_replacement_needed_iff_below_10_percent(
        self, usage: float, lifetime: float
    ):
        """blade_replacement_needed is True iff remaining life < 10%."""
        telemetry = _make_telemetry(usage, lifetime)
        result = NavimowCoordinator._build_maintenance_data(telemetry)

        remaining = result.blade_remaining_life_pct
        if remaining < 10.0:
            assert result.blade_replacement_needed is True, (
                f"Expected blade_replacement_needed=True when remaining={remaining}%"
            )
        else:
            assert result.blade_replacement_needed is False, (
                f"Expected blade_replacement_needed=False when remaining={remaining}%"
            )
