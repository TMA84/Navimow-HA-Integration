"""Property-based tests for GPS validity to device tracker state.

# Feature: navimow-home-assistant, Property 8: GPS Validity to Device Tracker State
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Load the models module directly to avoid homeassistant dependency
_spec = importlib.util.spec_from_file_location(
    "models", "custom_components/navimow/models.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["models"] = _mod
_spec.loader.exec_module(_mod)

LocationData = _mod.LocationData


# Strategy for generating LocationData instances
location_data_strategy = st.builds(
    LocationData,
    latitude=st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False),
    longitude=st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False),
    altitude=st.floats(min_value=-500.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    speed=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    hdop=st.floats(min_value=0.1, max_value=99.9, allow_nan=False, allow_infinity=False),
    satellites_in_use=st.integers(min_value=0, max_value=30),
    satellites_in_view=st.integers(min_value=0, max_value=50),
    data_valid=st.booleans(),
)


def _make_tracker_entity(location: LocationData):
    """Create a NavimowDeviceTrackerEntity with mocked coordinator providing the given location."""
    # We need to import the device_tracker module with mocked HA dependencies
    # The conftest already sets up the HA mocks in sys.modules, so we can import
    # But we need to also mock the device_tracker-specific HA modules
    from types import ModuleType

    # Mock device_tracker HA modules if not already present
    if "homeassistant.components.device_tracker" not in sys.modules:
        _dt_mod = ModuleType("homeassistant.components.device_tracker")

        class _SourceType:
            GPS = "gps"
            ROUTER = "router"
            BLUETOOTH = "bluetooth"
            BLUETOOTH_LE = "bluetooth_le"

        _dt_mod.SourceType = _SourceType
        sys.modules["homeassistant.components.device_tracker"] = _dt_mod

    if "homeassistant.components.device_tracker.config_entry" not in sys.modules:
        _dt_ce_mod = ModuleType("homeassistant.components.device_tracker.config_entry")

        class _TrackerEntity:
            """Mock TrackerEntity base class."""
            pass

        _dt_ce_mod.TrackerEntity = _TrackerEntity
        sys.modules["homeassistant.components.device_tracker.config_entry"] = _dt_ce_mod

    # Ensure the navimow modules are importable
    if "custom_components" not in sys.modules:
        sys.modules["custom_components"] = ModuleType("custom_components")
    if "custom_components.navimow" not in sys.modules:
        _navimow_mod = ModuleType("custom_components.navimow")
        sys.modules["custom_components.navimow"] = _navimow_mod
    if "custom_components.navimow.const" not in sys.modules:
        _const_mod = ModuleType("custom_components.navimow.const")
        _const_mod.DOMAIN = "navimow"
        sys.modules["custom_components.navimow.const"] = _const_mod
    if "custom_components.navimow.coordinator" not in sys.modules:
        _coord_mod = ModuleType("custom_components.navimow.coordinator")
        _coord_mod.NavimowCoordinator = MagicMock
        sys.modules["custom_components.navimow.coordinator"] = _coord_mod
    if "custom_components.navimow.entity" not in sys.modules:
        _entity_mod = ModuleType("custom_components.navimow.entity")

        class _NavimowEntity:
            """Mock NavimowEntity base class."""
            _attr_has_entity_name = True

            def __init__(self, coordinator, description):
                self.coordinator = coordinator
                self.entity_description = description
                self._attr_unique_id = f"{coordinator.device_sn}_{description.key}"

        _entity_mod.NavimowEntity = _NavimowEntity
        sys.modules["custom_components.navimow.entity"] = _entity_mod
    if "custom_components.navimow.models" not in sys.modules:
        sys.modules["custom_components.navimow.models"] = _mod

    # Now load the device_tracker module
    dt_spec = importlib.util.spec_from_file_location(
        "custom_components.navimow.device_tracker",
        "custom_components/navimow/device_tracker.py",
    )
    dt_module = importlib.util.module_from_spec(dt_spec)
    dt_spec.loader.exec_module(dt_module)

    NavimowDeviceTrackerEntity = dt_module.NavimowDeviceTrackerEntity

    # Create a mock coordinator with the given location data
    coordinator = MagicMock()
    coordinator.device_sn = "NVM_TEST_001"
    coordinator.data = MagicMock()
    coordinator.data.location = location

    entity = NavimowDeviceTrackerEntity(coordinator)
    return entity


# Feature: navimow-home-assistant, Property 8: GPS Validity to Device Tracker State
class TestGPSValidityToDeviceTrackerState:
    """Property-based tests for GPS validity to device tracker state.

    **Validates: Requirements 6.7**
    """

    @given(
        location=st.builds(
            LocationData,
            latitude=st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False),
            longitude=st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False),
            altitude=st.floats(min_value=-500.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
            speed=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
            hdop=st.floats(min_value=0.1, max_value=99.9, allow_nan=False, allow_infinity=False),
            satellites_in_use=st.integers(min_value=0, max_value=30),
            satellites_in_view=st.integers(min_value=0, max_value=50),
            data_valid=st.just(False),
        )
    )
    @settings(max_examples=100)
    def test_data_valid_false_results_in_unknown_state(self, location: LocationData) -> None:
        """When data_valid is False, the device tracker state is 'unknown'.

        The latitude and longitude should be None, and location_name should be 'unknown'.

        **Validates: Requirements 6.7**
        """
        entity = _make_tracker_entity(location)

        # When GPS data is invalid, latitude and longitude should be None
        assert entity.latitude is None
        assert entity.longitude is None
        # location_name should be "unknown" to set the state to unknown
        assert entity.location_name == "unknown"

    @given(
        location=st.builds(
            LocationData,
            latitude=st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False),
            longitude=st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False),
            altitude=st.floats(min_value=-500.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
            speed=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
            hdop=st.floats(min_value=0.1, max_value=99.9, allow_nan=False, allow_infinity=False),
            satellites_in_use=st.integers(min_value=0, max_value=30),
            satellites_in_view=st.integers(min_value=0, max_value=50),
            data_valid=st.just(True),
        )
    )
    @settings(max_examples=100)
    def test_data_valid_true_results_in_valid_coordinates(self, location: LocationData) -> None:
        """When data_valid is True, the device tracker provides valid coordinates.

        The latitude and longitude should be floats (the actual coordinate values),
        and location_name should be None (allowing HA to determine home/not_home).

        **Validates: Requirements 6.7**
        """
        entity = _make_tracker_entity(location)

        # When GPS data is valid, latitude and longitude should be the actual float values
        assert entity.latitude is not None
        assert entity.longitude is not None
        assert isinstance(entity.latitude, float)
        assert isinstance(entity.longitude, float)
        # Verify coordinates match the input data
        assert entity.latitude == location.latitude
        assert entity.longitude == location.longitude
        # location_name should be None so HA determines home/not_home based on zone
        assert entity.location_name is None

    @given(location=location_data_strategy)
    @settings(max_examples=100)
    def test_gps_validity_determines_tracker_state_consistently(
        self, location: LocationData
    ) -> None:
        """For any LocationData, the tracker state is determined solely by data_valid.

        If data_valid is False → unknown state (no coordinates, location_name='unknown').
        If data_valid is True → valid state (coordinates present, location_name=None).

        **Validates: Requirements 6.7**
        """
        entity = _make_tracker_entity(location)

        if not location.data_valid:
            # Invalid GPS → unknown state
            assert entity.latitude is None
            assert entity.longitude is None
            assert entity.location_name == "unknown"
        else:
            # Valid GPS → coordinates available, HA determines home/not_home
            assert entity.latitude == location.latitude
            assert entity.longitude == location.longitude
            assert isinstance(entity.latitude, float)
            assert isinstance(entity.longitude, float)
            assert entity.location_name is None
