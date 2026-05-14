"""Binary sensor platform for the Navimow integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity
from .models import MowerState, NavimowDeviceData


@dataclass(frozen=True, kw_only=True)
class NavimowBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Navimow binary sensor entity."""

    value_fn: Callable[[NavimowDeviceData], bool | None]


BINARY_SENSORS: tuple[NavimowBinarySensorEntityDescription, ...] = (
    NavimowBinarySensorEntityDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data.telemetry.state == MowerState.CHARGING,
    ),
    NavimowBinarySensorEntityDescription(
        key="battery_temperature_fault",
        translation_key="battery_temperature_fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:thermometer-alert",
        value_fn=lambda data: data.telemetry.battery_temperature_fault,
    ),
    NavimowBinarySensorEntityDescription(
        key="mqtt_connected",
        translation_key="mqtt_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.telemetry.mqtt_connected,
    ),
    NavimowBinarySensorEntityDescription(
        key="has_error",
        translation_key="has_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
        value_fn=lambda data: len(data.errors) > 0,
    ),
    NavimowBinarySensorEntityDescription(
        key="blade_replacement_needed",
        translation_key="blade_replacement_needed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:knife",
        value_fn=lambda data: data.maintenance.blade_replacement_needed,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow binary sensor entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[NavimowBinarySensorEntity] = []
    for coordinator in coordinators.values():
        for description in BINARY_SENSORS:
            entities.append(NavimowBinarySensorEntity(coordinator, description))

    async_add_entities(entities)


class NavimowBinarySensorEntity(NavimowEntity, BinarySensorEntity):
    """Representation of a Navimow binary sensor entity."""

    entity_description: NavimowBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: NavimowCoordinator,
        description: NavimowBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor entity."""
        super().__init__(coordinator, description)

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
