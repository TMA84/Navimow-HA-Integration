"""Switch platform for the Navimow integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api_client import NavimowApiError
from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity
from .models import NavimowDeviceData

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class NavimowSwitchEntityDescription(SwitchEntityDescription):
    """Describes a Navimow switch entity."""

    value_fn: Callable[[NavimowDeviceData], bool | None]
    setting_key: str
    conditional_fn: Callable[[NavimowDeviceData], bool] | None = None


SWITCHES: tuple[NavimowSwitchEntityDescription, ...] = (
    NavimowSwitchEntityDescription(
        key="schedule_enabled",
        translation_key="schedule_enabled",
        icon="mdi:calendar-clock",
        value_fn=lambda data: data.settings.plan_switch,
        setting_key="plan_switch",
    ),
    NavimowSwitchEntityDescription(
        key="rain_sensor",
        translation_key="rain_sensor",
        icon="mdi:weather-rainy",
        value_fn=lambda data: data.settings.rain_sensor,
        setting_key="rain_sensor",
    ),
    NavimowSwitchEntityDescription(
        key="edge_mowing",
        translation_key="edge_mowing",
        icon="mdi:border-all-variant",
        value_fn=lambda data: data.settings.edge_mowing,
        setting_key="edge_mowing",
    ),
    NavimowSwitchEntityDescription(
        key="mowing_cycle",
        translation_key="mowing_cycle",
        icon="mdi:refresh",
        value_fn=lambda data: data.settings.mowing_cycle,
        setting_key="mowing_cycle",
    ),
    NavimowSwitchEntityDescription(
        key="anti_theft",
        translation_key="anti_theft",
        icon="mdi:shield-lock",
        value_fn=lambda data: data.settings.anti_theft,
        setting_key="anti_theft",
    ),
    NavimowSwitchEntityDescription(
        key="dark_mode",
        translation_key="dark_mode",
        icon="mdi:weather-night",
        value_fn=lambda data: data.settings.dark_mode,
        setting_key="dark_mode",
    ),
    NavimowSwitchEntityDescription(
        key="anti_interference",
        translation_key="anti_interference",
        icon="mdi:signal-off",
        value_fn=lambda data: data.settings.anti_interference,
        setting_key="anti_interference",
        conditional_fn=lambda data: data.settings.anti_interference is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow switch entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[NavimowSwitchEntity] = []
    for coordinator in coordinators.values():
        for description in SWITCHES:
            # Skip conditional entities if condition is not met
            if description.conditional_fn is not None:
                if coordinator.data is None:
                    continue
                if not description.conditional_fn(coordinator.data):
                    continue
            entities.append(NavimowSwitchEntity(coordinator, description))

    async_add_entities(entities)


class NavimowSwitchEntity(NavimowEntity, SwitchEntity):
    """Representation of a Navimow switch entity."""

    entity_description: NavimowSwitchEntityDescription

    def __init__(
        self,
        coordinator: NavimowCoordinator,
        description: NavimowSwitchEntityDescription,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator, description)

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._set_setting(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._set_setting(False)

    async def _set_setting(self, value: bool) -> None:
        """Set the switch setting with rollback on failure.

        Args:
            value: The new value to set.
        """
        previous_value = self.is_on
        setting_key = self.entity_description.setting_key

        try:
            success = await self.coordinator.api_client.set_setting(
                self.coordinator.device_sn, setting_key, value
            )
            if not success:
                # Rollback: revert state and log warning
                _LOGGER.warning(
                    "Failed to set %s to %s for device %s, reverting",
                    setting_key,
                    value,
                    self.coordinator.device_sn,
                )
                self.async_write_ha_state()
                return
        except NavimowApiError as err:
            # Rollback: revert state and log warning
            _LOGGER.warning(
                "Error setting %s to %s for device %s: %s, reverting",
                setting_key,
                value,
                self.coordinator.device_sn,
                err,
            )
            self.async_write_ha_state()
            return

        # Trigger coordinator refresh to confirm new value
        await self.coordinator.async_request_refresh()
