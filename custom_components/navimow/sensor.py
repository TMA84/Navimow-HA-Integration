"""Sensor platform for the Navimow integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NavimowCoordinator
from .entity import NavimowEntity
from .errors import get_error_message
from .models import NavimowDeviceData


@dataclass(frozen=True, kw_only=True)
class NavimowSensorEntityDescription(SensorEntityDescription):
    """Describes a Navimow sensor entity."""

    value_fn: Callable[[NavimowDeviceData], str | int | float | datetime | None]
    extra_attrs_fn: Callable[[NavimowDeviceData], dict[str, Any]] | None = None


# ─── Battery and Power Sensors (Task 9.1) ──────────────────────────────────

BATTERY_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="battery_level",
        translation_key="battery_level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.telemetry.battery_level,
    ),
    NavimowSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.telemetry.battery_voltage,
    ),
)

# ─── Status and Activity Sensors (Task 9.2) ────────────────────────────────

STATUS_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "mowing",
            "returning",
            "charging",
            "standby",
            "paused",
            "error",
            "mapping",
            "calibrating",
            "idle_parking",
        ],
        value_fn=lambda data: data.telemetry.state.value,
    ),
    NavimowSensorEntityDescription(
        key="mowing_progress",
        translation_key="mowing_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:progress-check",
        value_fn=lambda data: data.telemetry.mowing_progress,
    ),
    NavimowSensorEntityDescription(
        key="current_task",
        translation_key="current_task",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "scheduled_mowing",
            "manual_mowing",
            "no_task",
            "waiting",
            "cancelled",
            "completed",
        ],
        value_fn=lambda data: data.telemetry.task_state.value,
    ),
    NavimowSensorEntityDescription(
        key="schedule_end_time",
        translation_key="schedule_end_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.schedule.next_end,
    ),
    NavimowSensorEntityDescription(
        key="work_mode",
        translation_key="work_mode",
        device_class=SensorDeviceClass.ENUM,
        options=["standard", "fast", "silent"],
        value_fn=lambda data: data.telemetry.work_mode.value,
    ),
)

# ─── GPS and Positioning Sensors (Task 9.3) ────────────────────────────────

GPS_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="gps_satellites_in_use",
        translation_key="gps_satellites_in_use",
        icon="mdi:satellite-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.location.satellites_in_use,
    ),
    NavimowSensorEntityDescription(
        key="gps_satellites_in_view",
        translation_key="gps_satellites_in_view",
        icon="mdi:satellite-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.location.satellites_in_view,
    ),
    NavimowSensorEntityDescription(
        key="gps_hdop",
        translation_key="gps_hdop",
        icon="mdi:crosshairs-gps",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.location.hdop,
    ),
    NavimowSensorEntityDescription(
        key="gps_speed",
        translation_key="gps_speed",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.location.speed,
    ),
    NavimowSensorEntityDescription(
        key="gps_altitude",
        translation_key="gps_altitude",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.location.altitude,
    ),
)

# ─── Connectivity Sensors (Task 9.4) ───────────────────────────────────────

CONNECTIVITY_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="network_type",
        translation_key="network_type",
        icon="mdi:network",
        value_fn=lambda data: data.telemetry.network_type,
    ),
    NavimowSensorEntityDescription(
        key="cellular_signal",
        translation_key="cellular_signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.telemetry.cellular_signal,
    ),
    NavimowSensorEntityDescription(
        key="wifi_ssid",
        translation_key="wifi_ssid",
        icon="mdi:wifi",
        value_fn=lambda data: data.telemetry.wifi_ssid,
    ),
)

# ─── Area and Statistics Sensors (Task 9.5) ─────────────────────────────────

AREA_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="total_mowing_area",
        translation_key="total_mowing_area",
        native_unit_of_measurement="m²",
        icon="mdi:texture-box",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.telemetry.total_mowing_area,
    ),
    NavimowSensorEntityDescription(
        key="current_mowing_area",
        translation_key="current_mowing_area",
        native_unit_of_measurement="m²",
        icon="mdi:texture-box",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.telemetry.current_mowing_area,
    ),
    NavimowSensorEntityDescription(
        key="total_mowing_time",
        translation_key="total_mowing_time",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.telemetry.total_mowing_time,
    ),
    NavimowSensorEntityDescription(
        key="map_area",
        translation_key="map_area",
        native_unit_of_measurement="m²",
        icon="mdi:map",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.map_data.total_area if data.map_data else None,
    ),
)

# ─── Schedule Sensors (Task 9.6) ───────────────────────────────────────────

SCHEDULE_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="next_schedule_start",
        translation_key="next_schedule_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.schedule.next_start,
    ),
    NavimowSensorEntityDescription(
        key="next_schedule_end",
        translation_key="next_schedule_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.schedule.next_end,
    ),
)

# ─── Diagnostic Sensors (Task 9.7) ─────────────────────────────────────────

DIAGNOSTIC_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="device_model",
        translation_key="device_model",
        icon="mdi:robot-mower",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.device_info.model,
    ),
    NavimowSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.device_info.firmware_versions.ecu,
    ),
)

# ─── Error Sensors (Task 14.1) ─────────────────────────────────────────────

ERROR_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="error_code",
        translation_key="error_code",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.errors[0].code if data.errors else 0,
    ),
    NavimowSensorEntityDescription(
        key="error_message",
        translation_key="error_message",
        icon="mdi:alert-circle-outline",
        value_fn=lambda data: get_error_message(data.errors[0].code) if data.errors else "",
    ),
)

# ─── Maintenance Sensors (Task 15.1) ──────────────────────────────────────

MAINTENANCE_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="blade_usage_time",
        translation_key="blade_usage_time",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:knife",
        value_fn=lambda data: data.maintenance.blade_usage_hours,
    ),
    NavimowSensorEntityDescription(
        key="blade_remaining_life",
        translation_key="blade_remaining_life",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:knife",
        value_fn=lambda data: round(data.maintenance.blade_remaining_life_pct, 1),
    ),
    NavimowSensorEntityDescription(
        key="maintenance_status",
        translation_key="maintenance_status",
        icon="mdi:wrench",
        value_fn=lambda data: data.maintenance.maintenance_status,
        extra_attrs_fn=lambda data: {
            "hints": [
                {
                    "type": hint.hint_type,
                    "title": hint.title,
                    "description": hint.description,
                    "timestamp": hint.timestamp.isoformat(),
                }
                for hint in data.maintenance.maintenance_hints
            ]
        },
    ),
)

# ─── Map and Zone Sensors (Task 16.1) ─────────────────────────────────────

MAP_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="active_zones",
        translation_key="active_zones",
        icon="mdi:map-marker-multiple",
        value_fn=lambda data: (
            ", ".join(z.name for z in data.map_data.zones if z.active)
            if data.map_data and data.map_data.zones
            else ""
        ),
    ),
    NavimowSensorEntityDescription(
        key="map_status",
        translation_key="map_status",
        icon="mdi:map-check",
        value_fn=lambda data: data.map_data.map_status if data.map_data else "no_map",
    ),
)

# ─── Trail History Sensors (Task 17.1) ────────────────────────────────────


def _get_trail_extra_attrs(data: NavimowDeviceData) -> dict[str, Any]:
    """Get last 7 days of trail data as extra state attributes."""
    now = datetime.now(tz=timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    recent_trails = [
        {
            "trail_id": t.trail_id,
            "date": t.date.isoformat(),
            "duration_minutes": t.duration,
            "area_m2": t.area,
        }
        for t in data.trail_history
        if t.date >= seven_days_ago
    ]
    return {"trail_history_7d": recent_trails}


TRAIL_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    NavimowSensorEntityDescription(
        key="last_mowing_date",
        translation_key="last_mowing_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        value_fn=lambda data: data.trail_history[0].date if data.trail_history else None,
        extra_attrs_fn=_get_trail_extra_attrs,
    ),
    NavimowSensorEntityDescription(
        key="last_mowing_duration",
        translation_key="last_mowing_duration",
        native_unit_of_measurement="min",
        icon="mdi:timer-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.trail_history[0].duration if data.trail_history else None,
        extra_attrs_fn=_get_trail_extra_attrs,
    ),
    NavimowSensorEntityDescription(
        key="last_mowing_area",
        translation_key="last_mowing_area",
        native_unit_of_measurement="m²",
        icon="mdi:texture-box",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.trail_history[0].area if data.trail_history else None,
        extra_attrs_fn=_get_trail_extra_attrs,
    ),
)

# ─── All Sensors Combined ──────────────────────────────────────────────────

ALL_SENSORS: tuple[NavimowSensorEntityDescription, ...] = (
    *BATTERY_SENSORS,
    *STATUS_SENSORS,
    *GPS_SENSORS,
    *CONNECTIVITY_SENSORS,
    *AREA_SENSORS,
    *SCHEDULE_SENSORS,
    *DIAGNOSTIC_SENSORS,
    *ERROR_SENSORS,
    *MAINTENANCE_SENSORS,
    *MAP_SENSORS,
    *TRAIL_SENSORS,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Navimow sensor entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, NavimowCoordinator] = data["coordinators"]

    entities: list[NavimowSensorEntity] = []
    for coordinator in coordinators.values():
        for description in ALL_SENSORS:
            entities.append(NavimowSensorEntity(coordinator, description))

    async_add_entities(entities)


class NavimowSensorEntity(NavimowEntity, SensorEntity):
    """Representation of a Navimow sensor entity."""

    entity_description: NavimowSensorEntityDescription

    def __init__(
        self,
        coordinator: NavimowCoordinator,
        description: NavimowSensorEntityDescription,
    ) -> None:
        """Initialize the sensor entity.

        Args:
            coordinator: The data update coordinator for this device.
            description: The sensor entity description.
        """
        super().__init__(coordinator, description)

    @property
    def native_value(self) -> str | int | float | datetime | None:
        """Return the current sensor value from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes if defined."""
        if self.coordinator.data is None:
            return None
        if self.entity_description.extra_attrs_fn is not None:
            return self.entity_description.extra_attrs_fn(self.coordinator.data)
        return None

    @property
    def icon(self) -> str | None:
        """Return the icon, with variants for battery and blade sensors."""
        if self.entity_description.key == "battery_level":
            if self.coordinator.data is not None:
                level = self.coordinator.data.telemetry.battery_level
                if level < 20:
                    return "mdi:battery-low"
                return "mdi:battery"
        if self.entity_description.key == "blade_remaining_life":
            if self.coordinator.data is not None:
                pct = self.coordinator.data.maintenance.blade_remaining_life_pct
                if pct < 20:
                    return "mdi:knife-military"
        return super().icon
