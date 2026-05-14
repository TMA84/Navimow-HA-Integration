"""Device tracker platform for the Navimow integration."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow device tracker entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[NavimowDeviceTrackerEntity] = []
    for coordinator in coordinators.values():
        entities.append(NavimowDeviceTrackerEntity(coordinator))

    async_add_entities(entities)


class NavimowDeviceTrackerEntity(NavimowEntity, TrackerEntity):
    """Representation of a Navimow device tracker entity."""

    _attr_name = None  # Use device name directly

    def __init__(self, coordinator: NavimowCoordinator) -> None:
        """Initialize the device tracker entity."""
        description = EntityDescription(key="device_tracker", name=None)
        super().__init__(coordinator, description)

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device tracker."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        if self.coordinator.data is None:
            return None
        if not self.coordinator.data.location.data_valid:
            return None
        return self.coordinator.data.location.latitude

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        if self.coordinator.data is None:
            return None
        if not self.coordinator.data.location.data_valid:
            return None
        return self.coordinator.data.location.longitude

    @property
    def location_name(self) -> str | None:
        """Return a location name for the device.

        Returns 'unknown' when GPS data is invalid.
        """
        if self.coordinator.data is None:
            return None
        if not self.coordinator.data.location.data_valid:
            return "unknown"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, any] | None:
        """Return additional state attributes including map boundaries."""
        if self.coordinator.data is None:
            return None

        attrs: dict[str, any] = {
            "altitude": self.coordinator.data.location.altitude,
            "speed": self.coordinator.data.location.speed,
            "hdop": self.coordinator.data.location.hdop,
            "satellites_in_use": self.coordinator.data.location.satellites_in_use,
            "data_valid": self.coordinator.data.location.data_valid,
        }

        # Expose map boundary coordinates as device attributes
        if self.coordinator.data.map_data is not None:
            attrs["map_boundaries"] = self.coordinator.data.map_data.boundaries

        return attrs
