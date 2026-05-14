"""Lawn mower platform for the Navimow integration."""

from __future__ import annotations

import logging

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api_client import NavimowApiError
from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity
from .models import map_mower_state_to_activity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow lawn mower entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[NavimowLawnMowerEntity] = []
    for coordinator in coordinators.values():
        entities.append(NavimowLawnMowerEntity(coordinator))

    async_add_entities(entities)


class NavimowLawnMowerEntity(NavimowEntity, LawnMowerEntity):
    """Representation of a Navimow lawn mower entity."""

    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )
    _attr_name = None  # Use device name directly

    def __init__(self, coordinator: NavimowCoordinator) -> None:
        """Initialize the lawn mower entity."""
        from homeassistant.helpers.entity import EntityDescription

        description = EntityDescription(key="lawn_mower", name=None)
        super().__init__(coordinator, description)
        # Override unique_id to just be the device serial (main entity)
        self._attr_unique_id = coordinator.device_sn

    @property
    def activity(self) -> LawnMowerActivity | None:
        """Return the current activity of the lawn mower."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.telemetry.state
        try:
            return LawnMowerActivity(map_mower_state_to_activity(state).value)
        except ValueError:
            return None

    async def async_start_mowing(self) -> None:
        """Start mowing."""
        await self._send_command("MOWER_HANDLE_MOW")

    async def async_pause(self) -> None:
        """Pause mowing."""
        await self._send_command("MOWER_HANDLE_STOP")

    async def async_dock(self) -> None:
        """Return to dock."""
        await self._send_command("MOWER_HANDLE_PARK")

    async def _send_command(self, command: str) -> None:
        """Send a command to the mower and refresh coordinator.

        Args:
            command: The command identifier to send.

        Raises:
            HomeAssistantError: If the command fails.
        """
        try:
            success = await self.coordinator.api_client.send_command(
                self.coordinator.device_sn, command
            )
            if not success:
                raise HomeAssistantError(
                    f"Command {command} was rejected by the device"
                )
        except NavimowApiError as err:
            raise HomeAssistantError(
                f"Communication error sending command {command}: {err}"
            ) from err

        # Trigger coordinator refresh after successful command
        await self.coordinator.async_request_refresh()
