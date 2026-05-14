"""Button platform for the Navimow integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api_client import NavimowApiError
from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity

_LOGGER = logging.getLogger(__name__)

CANCEL_SCHEDULE_DESCRIPTION = ButtonEntityDescription(
    key="cancel_today_schedule",
    translation_key="cancel_today_schedule",
    icon="mdi:calendar-remove",
)

RESET_BLADE_COUNTER_DESCRIPTION = ButtonEntityDescription(
    key="reset_blade_counter",
    translation_key="reset_blade_counter",
    icon="mdi:knife",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow button entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[ButtonEntity] = []
    for coordinator in coordinators.values():
        entities.append(NavimowCancelScheduleButtonEntity(coordinator))
        entities.append(NavimowResetBladeCounterButtonEntity(coordinator))

    async_add_entities(entities)


class NavimowCancelScheduleButtonEntity(NavimowEntity, ButtonEntity):
    """Representation of a Navimow button entity for cancelling today's schedule."""

    entity_description: ButtonEntityDescription

    def __init__(self, coordinator: NavimowCoordinator) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator, CANCEL_SCHEDULE_DESCRIPTION)

    async def async_press(self) -> None:
        """Handle the button press to cancel today's schedule."""
        try:
            success = await self.coordinator.api_client.send_command(
                self.coordinator.device_sn, "TASK_CANCEL_TODAY"
            )
            if not success:
                raise HomeAssistantError(
                    "Failed to cancel today's schedule"
                )
        except NavimowApiError as err:
            raise HomeAssistantError(
                f"Communication error cancelling schedule: {err}"
            ) from err

        # Trigger coordinator refresh after successful command
        await self.coordinator.async_request_refresh()


class NavimowResetBladeCounterButtonEntity(NavimowEntity, ButtonEntity):
    """Representation of a Navimow button entity for resetting the blade counter."""

    entity_description: ButtonEntityDescription

    def __init__(self, coordinator: NavimowCoordinator) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator, RESET_BLADE_COUNTER_DESCRIPTION)

    async def async_press(self) -> None:
        """Handle the button press to reset the blade usage counter."""
        try:
            success = await self.coordinator.api_client.send_command(
                self.coordinator.device_sn, "RESET_BLADE_COUNTER"
            )
            if not success:
                raise HomeAssistantError(
                    "Failed to reset blade counter"
                )
        except NavimowApiError as err:
            raise HomeAssistantError(
                f"Communication error resetting blade counter: {err}"
            ) from err

        # Trigger coordinator refresh after successful command
        await self.coordinator.async_request_refresh()
