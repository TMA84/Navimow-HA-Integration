"""Update platform for the Navimow integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity

_LOGGER = logging.getLogger(__name__)

UPDATE_DESCRIPTION = UpdateEntityDescription(
    key="firmware",
    translation_key="firmware",
    device_class=UpdateDeviceClass.FIRMWARE,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow update entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[NavimowUpdateEntity] = []
    for coordinator in coordinators.values():
        entities.append(NavimowUpdateEntity(coordinator))

    async_add_entities(entities)


class NavimowUpdateEntity(NavimowEntity, UpdateEntity):
    """Representation of a Navimow firmware update entity."""

    entity_description: UpdateEntityDescription

    def __init__(self, coordinator: NavimowCoordinator) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator, UPDATE_DESCRIPTION)

    @property
    def installed_version(self) -> str | None:
        """Return the current firmware version (ECU)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.firmware.current_versions.ecu

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version."""
        if self.coordinator.data is None:
            return None
        firmware = self.coordinator.data.firmware
        if firmware.update_available and firmware.new_version:
            return firmware.new_version
        return firmware.current_versions.ecu

    @property
    def release_summary(self) -> str | None:
        """Return release notes for the latest version."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.firmware.release_notes

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return all firmware component versions as diagnostic attributes."""
        if self.coordinator.data is None:
            return None
        versions = self.coordinator.data.firmware.current_versions
        attrs: dict[str, Any] = {
            "ecu_version": versions.ecu,
            "bms_version": versions.bms,
            "gps_version": versions.gps,
            "bluetooth_version": versions.bluetooth,
            "wifi_version": versions.wifi,
            "blade_motor_version": versions.blade_motor,
            "charging_station_version": versions.charging_station,
            "iot_version": versions.iot,
            "audio_version": versions.audio,
            "bump_sensor_version": versions.bump_sensor,
        }
        if versions.vision_fence is not None:
            attrs["vision_fence_version"] = versions.vision_fence
        return attrs
