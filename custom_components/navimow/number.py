"""Number platform for the Navimow integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api_client import NavimowApiError
from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity

_LOGGER = logging.getLogger(__name__)

NUMBER_DESCRIPTION = NumberEntityDescription(
    key="cutting_height",
    translation_key="cutting_height",
    icon="mdi:grass",
    native_min_value=20,
    native_max_value=60,
    native_step=5,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    device_class=NumberDeviceClass.DISTANCE,
    mode=NumberMode.SLIDER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow number entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[NavimowNumberEntity] = []
    for coordinator in coordinators.values():
        entities.append(NavimowNumberEntity(coordinator))

    async_add_entities(entities)


class NavimowNumberEntity(NavimowEntity, NumberEntity):
    """Representation of a Navimow number entity for cutting height."""

    entity_description: NumberEntityDescription

    def __init__(self, coordinator: NavimowCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, NUMBER_DESCRIPTION)

    @property
    def native_value(self) -> float | None:
        """Return the current cutting height value."""
        if self.coordinator.data is None:
            return None
        return float(self.coordinator.data.settings.cutting_height)

    async def async_set_native_value(self, value: float) -> None:
        """Set the cutting height value."""
        int_value = int(value)
        try:
            success = await self.coordinator.api_client.set_setting(
                self.coordinator.device_sn, "cutting_height", int_value
            )
            if not success:
                _LOGGER.warning(
                    "Failed to set cutting_height to %d for device %s",
                    int_value,
                    self.coordinator.device_sn,
                )
                return
        except NavimowApiError as err:
            _LOGGER.warning(
                "Error setting cutting_height to %d for device %s: %s",
                int_value,
                self.coordinator.device_sn,
                err,
            )
            return

        # Trigger coordinator refresh to confirm new value
        await self.coordinator.async_request_refresh()
