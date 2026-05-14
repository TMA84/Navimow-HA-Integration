"""Base entity for the Navimow integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NavimowCoordinator


class NavimowEntity(CoordinatorEntity[NavimowCoordinator]):
    """Base entity for Navimow integration.

    All Navimow entities extend this class to share common device info
    and unique ID generation logic.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NavimowCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the Navimow entity.

        Args:
            coordinator: The data update coordinator for this device.
            description: The entity description defining key, name, etc.
        """
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_sn}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the device registry.

        Groups all entities under a single device entry with manufacturer,
        model, serial number, firmware version, and configuration URL.
        """
        data = self.coordinator.data
        device_info_data = data.device_info if data else None

        # Extract firmware version (ECU) for sw_version
        sw_version: str | None = None
        if device_info_data and device_info_data.firmware_versions:
            sw_version = device_info_data.firmware_versions.ecu

        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_sn)},
            manufacturer="Segway",
            model=device_info_data.model if device_info_data else None,
            name=device_info_data.name if device_info_data else None,
            serial_number=self.coordinator.device_sn,
            sw_version=sw_version,
            configuration_url="https://navimow.segway.com/",
        )
