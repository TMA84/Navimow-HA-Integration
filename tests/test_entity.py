"""Tests for the NavimowEntity base class."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# Mock homeassistant modules before importing the entity module
_ha_mock = ModuleType("homeassistant")
_ha_mock.config_entries = ModuleType("homeassistant.config_entries")
_ha_mock.config_entries.ConfigEntry = MagicMock
_ha_mock.core = ModuleType("homeassistant.core")
_ha_mock.core.HomeAssistant = MagicMock

_ha_helpers = ModuleType("homeassistant.helpers")
_ha_helpers_aiohttp = ModuleType("homeassistant.helpers.aiohttp_client")
_ha_helpers_aiohttp.async_get_clientsession = MagicMock()

_ha_helpers_device_registry = ModuleType("homeassistant.helpers.device_registry")
_ha_helpers_device_registry.DeviceInfo = dict  # DeviceInfo is a TypedDict

_ha_helpers_entity = ModuleType("homeassistant.helpers.entity")
_ha_helpers_entity.EntityDescription = MagicMock

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


class _MockCoordinatorEntity:
    """Mock CoordinatorEntity base class."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def unique_id(self):
        """Return unique_id from _attr_unique_id."""
        return getattr(self, "_attr_unique_id", None)


_ha_update_coordinator.DataUpdateCoordinator = _MockDataUpdateCoordinator
_ha_update_coordinator.UpdateFailed = Exception
_ha_update_coordinator.CoordinatorEntity = _MockCoordinatorEntity

sys.modules.setdefault("homeassistant", _ha_mock)
sys.modules.setdefault("homeassistant.config_entries", _ha_mock.config_entries)
sys.modules.setdefault("homeassistant.core", _ha_mock.core)
sys.modules.setdefault("homeassistant.helpers", _ha_helpers)
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", _ha_helpers_aiohttp)
sys.modules.setdefault("homeassistant.helpers.device_registry", _ha_helpers_device_registry)
sys.modules.setdefault("homeassistant.helpers.entity", _ha_helpers_entity)
sys.modules.setdefault("homeassistant.helpers.update_coordinator", _ha_update_coordinator)

from custom_components.navimow.const import DOMAIN
from custom_components.navimow.entity import NavimowEntity
from custom_components.navimow.models import DeviceInfo, FirmwareVersions


class TestNavimowEntity:
    """Tests for NavimowEntity base class."""

    def _make_coordinator(
        self,
        device_sn: str = "NVM1234567890",
        model: str = "Navimow i105",
        name: str = "Front Yard Mower",
        ecu_version: str = "1.2.3",
    ) -> MagicMock:
        """Create a mock coordinator with device data."""
        coordinator = MagicMock()
        coordinator.device_sn = device_sn
        coordinator.data = MagicMock()
        coordinator.data.device_info = DeviceInfo(
            device_sn=device_sn,
            model=model,
            name=name,
            firmware_versions=FirmwareVersions(
                ecu=ecu_version,
                bms="2.0.1",
                gps="3.1.0",
                bluetooth="1.0.5",
                wifi="2.1.0",
                blade_motor="1.1.0",
                charging_station="1.0.2",
                iot="2.2.0",
                audio="1.0.0",
                bump_sensor="1.0.1",
                vision_fence=None,
            ),
        )
        return coordinator

    def _make_description(self, key: str = "battery_level") -> MagicMock:
        """Create a mock EntityDescription."""
        description = MagicMock()
        description.key = key
        return description

    def test_unique_id_combines_device_sn_and_key(self):
        """Test that unique_id is formed from device_sn and description key."""
        coordinator = self._make_coordinator(device_sn="NVM_ABC123")
        description = self._make_description(key="battery_level")

        entity = NavimowEntity(coordinator, description)

        assert entity.unique_id == "NVM_ABC123_battery_level"

    def test_unique_id_different_keys(self):
        """Test that different description keys produce different unique IDs."""
        coordinator = self._make_coordinator(device_sn="NVM_XYZ")
        desc1 = self._make_description(key="status")
        desc2 = self._make_description(key="gps_speed")

        entity1 = NavimowEntity(coordinator, desc1)
        entity2 = NavimowEntity(coordinator, desc2)

        assert entity1.unique_id != entity2.unique_id
        assert entity1.unique_id == "NVM_XYZ_status"
        assert entity2.unique_id == "NVM_XYZ_gps_speed"

    def test_has_entity_name_is_true(self):
        """Test that _attr_has_entity_name is True."""
        coordinator = self._make_coordinator()
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)

        assert entity._attr_has_entity_name is True

    def test_device_info_manufacturer(self):
        """Test that device_info returns manufacturer as Segway."""
        coordinator = self._make_coordinator()
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)
        info = entity.device_info

        assert info["manufacturer"] == "Segway"

    def test_device_info_identifiers(self):
        """Test that device_info identifiers use DOMAIN and device_sn."""
        coordinator = self._make_coordinator(device_sn="NVM_TEST_SN")
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)
        info = entity.device_info

        assert info["identifiers"] == {(DOMAIN, "NVM_TEST_SN")}

    def test_device_info_model(self):
        """Test that device_info includes the device model."""
        coordinator = self._make_coordinator(model="Navimow i108")
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)
        info = entity.device_info

        assert info["model"] == "Navimow i108"

    def test_device_info_name(self):
        """Test that device_info includes the device name."""
        coordinator = self._make_coordinator(name="My Mower")
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)
        info = entity.device_info

        assert info["name"] == "My Mower"

    def test_device_info_serial_number(self):
        """Test that device_info includes the serial number."""
        coordinator = self._make_coordinator(device_sn="NVM_SERIAL_123")
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)
        info = entity.device_info

        assert info["serial_number"] == "NVM_SERIAL_123"

    def test_device_info_sw_version(self):
        """Test that device_info includes ECU firmware version as sw_version."""
        coordinator = self._make_coordinator(ecu_version="2.5.0")
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)
        info = entity.device_info

        assert info["sw_version"] == "2.5.0"

    def test_device_info_configuration_url(self):
        """Test that device_info includes the Navimow configuration URL."""
        coordinator = self._make_coordinator()
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)
        info = entity.device_info

        assert info["configuration_url"] == "https://navimow.segway.com/"

    def test_device_info_with_no_data(self):
        """Test device_info gracefully handles missing coordinator data."""
        coordinator = MagicMock()
        coordinator.device_sn = "NVM_NODATA"
        coordinator.data = None
        description = self._make_description()

        entity = NavimowEntity(coordinator, description)
        info = entity.device_info

        assert info["identifiers"] == {(DOMAIN, "NVM_NODATA")}
        assert info["manufacturer"] == "Segway"
        assert info["serial_number"] == "NVM_NODATA"
        assert info["model"] is None
        assert info["name"] is None
        assert info["sw_version"] is None
        assert info["configuration_url"] == "https://navimow.segway.com/"

    def test_entity_description_stored(self):
        """Test that entity_description is stored on the entity."""
        coordinator = self._make_coordinator()
        description = self._make_description(key="test_key")

        entity = NavimowEntity(coordinator, description)

        assert entity.entity_description is description
