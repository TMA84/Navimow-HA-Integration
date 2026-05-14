"""Select platform for the Navimow integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api_client import NavimowApiError
from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity
from .models import WorkMode

_LOGGER = logging.getLogger(__name__)

WORK_MODE_OPTIONS = [
    WorkMode.STANDARD.value,
    WorkMode.FAST.value,
    WorkMode.SILENT.value,
]

SELECT_DESCRIPTION = SelectEntityDescription(
    key="work_mode",
    translation_key="work_mode",
    icon="mdi:speedometer",
    options=WORK_MODE_OPTIONS,
)

MOWING_ZONE_DESCRIPTION = SelectEntityDescription(
    key="mowing_zone",
    translation_key="mowing_zone",
    icon="mdi:map-marker",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow select entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[SelectEntity] = []
    for coordinator in coordinators.values():
        entities.append(NavimowWorkModeSelectEntity(coordinator))
        # Only add mowing zone select if device has multiple zones
        if (
            coordinator.data
            and coordinator.data.map_data
            and len(coordinator.data.map_data.zones) > 1
        ):
            entities.append(NavimowMowingZoneSelectEntity(coordinator))

    async_add_entities(entities)


class NavimowWorkModeSelectEntity(NavimowEntity, SelectEntity):
    """Representation of a Navimow select entity for work mode."""

    entity_description: SelectEntityDescription

    def __init__(self, coordinator: NavimowCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, SELECT_DESCRIPTION)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.settings.work_mode.value

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return WORK_MODE_OPTIONS

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        try:
            success = await self.coordinator.api_client.set_setting(
                self.coordinator.device_sn, "work_mode", option
            )
            if not success:
                _LOGGER.warning(
                    "Failed to set work_mode to %s for device %s",
                    option,
                    self.coordinator.device_sn,
                )
                return
        except NavimowApiError as err:
            _LOGGER.warning(
                "Error setting work_mode to %s for device %s: %s",
                option,
                self.coordinator.device_sn,
                err,
            )
            return

        # Trigger coordinator refresh to confirm new value
        await self.coordinator.async_request_refresh()


class NavimowMowingZoneSelectEntity(NavimowEntity, SelectEntity):
    """Representation of a Navimow select entity for mowing zone selection."""

    entity_description: SelectEntityDescription

    def __init__(self, coordinator: NavimowCoordinator) -> None:
        """Initialize the mowing zone select entity."""
        super().__init__(coordinator, MOWING_ZONE_DESCRIPTION)

    @property
    def current_option(self) -> str | None:
        """Return the currently active zone name."""
        if self.coordinator.data is None or self.coordinator.data.map_data is None:
            return None
        for zone in self.coordinator.data.map_data.zones:
            if zone.active:
                return zone.name
        return None

    @property
    def options(self) -> list[str]:
        """Return the list of available zone names."""
        if self.coordinator.data is None or self.coordinator.data.map_data is None:
            return []
        return [zone.name for zone in self.coordinator.data.map_data.zones]

    async def async_select_option(self, option: str) -> None:
        """Change the selected mowing zone."""
        if self.coordinator.data is None or self.coordinator.data.map_data is None:
            return

        # Find the zone_id for the selected zone name
        zone_id = None
        for zone in self.coordinator.data.map_data.zones:
            if zone.name == option:
                zone_id = zone.zone_id
                break

        if zone_id is None:
            _LOGGER.warning(
                "Zone '%s' not found for device %s",
                option,
                self.coordinator.device_sn,
            )
            return

        try:
            success = await self.coordinator.api_client.set_setting(
                self.coordinator.device_sn, "mowing_zone", zone_id
            )
            if not success:
                _LOGGER.warning(
                    "Failed to set mowing_zone to %s for device %s",
                    option,
                    self.coordinator.device_sn,
                )
                return
        except NavimowApiError as err:
            _LOGGER.warning(
                "Error setting mowing_zone to %s for device %s: %s",
                option,
                self.coordinator.device_sn,
                err,
            )
            return

        # Trigger coordinator refresh to confirm new value
        await self.coordinator.async_request_refresh()
