"""Data models and enums for the Navimow integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class MowerState(StrEnum):
    """Mower operational states."""

    MOWING = "mowing"
    RETURNING = "returning"
    CHARGING = "charging"
    STANDBY = "standby"
    PAUSED = "paused"
    ERROR = "error"
    MAPPING = "mapping"
    CALIBRATING = "calibrating"
    IDLE_PARKING = "idle_parking"


class WorkMode(StrEnum):
    """Mowing work modes."""

    STANDARD = "standard"
    FAST = "fast"
    SILENT = "silent"


class TaskState(StrEnum):
    """Current task states."""

    SCHEDULED_MOWING = "scheduled_mowing"
    MANUAL_MOWING = "manual_mowing"
    NO_TASK = "no_task"
    WAITING = "waiting"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class LawnMowerActivity(StrEnum):
    """Lawn mower activity states matching Home Assistant's LawnMowerActivity."""

    MOWING = "mowing"
    DOCKED = "docked"
    PAUSED = "paused"
    RETURNING = "returning"
    ERROR = "error"


# Mapping from API state code strings to MowerState
API_STATE_CODES: dict[str, MowerState] = {
    "WORK_MOWING": MowerState.MOWING,
    "WORK_RETURNING": MowerState.RETURNING,
    "IDLE_CHARGING": MowerState.CHARGING,
    "IDLE_STANDBY": MowerState.STANDBY,
    "IDLE_PARKING": MowerState.IDLE_PARKING,
    "WORK_PAUSED": MowerState.PAUSED,
    "WORK_MAPPING": MowerState.MAPPING,
    "WORK_CALIBRATING": MowerState.CALIBRATING,
    # Error states: any ERROR_* prefix maps to error
    "ERROR_LIFT": MowerState.ERROR,
    "ERROR_STUCK": MowerState.ERROR,
    "ERROR_BATTERY": MowerState.ERROR,
    "ERROR_BLADE": MowerState.ERROR,
    "ERROR_MOTOR": MowerState.ERROR,
    "ERROR_SENSOR": MowerState.ERROR,
    "ERROR_COMMUNICATION": MowerState.ERROR,
    "ERROR_GPS": MowerState.ERROR,
    "ERROR_BOUNDARY": MowerState.ERROR,
    "ERROR_UNKNOWN": MowerState.ERROR,
}

# Mapping from MowerState to LawnMowerActivity
MOWER_STATE_TO_ACTIVITY: dict[MowerState, LawnMowerActivity] = {
    MowerState.MOWING: LawnMowerActivity.MOWING,
    MowerState.MAPPING: LawnMowerActivity.MOWING,
    MowerState.CALIBRATING: LawnMowerActivity.MOWING,
    MowerState.CHARGING: LawnMowerActivity.DOCKED,
    MowerState.STANDBY: LawnMowerActivity.DOCKED,
    MowerState.IDLE_PARKING: LawnMowerActivity.DOCKED,
    MowerState.PAUSED: LawnMowerActivity.PAUSED,
    MowerState.RETURNING: LawnMowerActivity.RETURNING,
    MowerState.ERROR: LawnMowerActivity.ERROR,
}


def map_api_state_to_mower_state(api_state_code: str) -> MowerState:
    """Map an API state code string to a MowerState enum value.

    Any state code starting with 'ERROR_' maps to MowerState.ERROR.
    Known state codes are mapped directly from API_STATE_CODES.

    Args:
        api_state_code: The state code string from the API (e.g., 'WORK_MOWING').

    Returns:
        The corresponding MowerState enum value.

    Raises:
        ValueError: If the state code is not recognized.
    """
    # Check for ERROR_ prefix first
    if api_state_code.startswith("ERROR_"):
        return MowerState.ERROR

    if api_state_code in API_STATE_CODES:
        return API_STATE_CODES[api_state_code]

    raise ValueError(f"Unknown API state code: {api_state_code}")


def map_mower_state_to_activity(state: MowerState) -> LawnMowerActivity:
    """Map a MowerState to a LawnMowerActivity.

    Args:
        state: The current MowerState.

    Returns:
        The corresponding LawnMowerActivity.

    Raises:
        ValueError: If the state has no mapping (should not happen for valid MowerState values).
    """
    if state in MOWER_STATE_TO_ACTIVITY:
        return MOWER_STATE_TO_ACTIVITY[state]

    raise ValueError(f"No activity mapping for state: {state}")


@dataclass
class NavimowDevice:
    """Discovered device from account."""

    device_sn: str
    name: str
    model: str
    online: bool


@dataclass
class FirmwareVersions:
    """All firmware component versions."""

    ecu: str
    bms: str
    gps: str
    bluetooth: str
    wifi: str
    blade_motor: str  # NCU
    charging_station: str  # CGS
    iot: str  # Telematics BOX
    audio: str  # MSC
    bump_sensor: str
    vision_fence: str | None = None


@dataclass
class DeviceInfo:
    """Static device information."""

    device_sn: str
    model: str
    name: str
    firmware_versions: FirmwareVersions
    manufacturer: str = "Segway"


@dataclass
class DeviceTelemetry:
    """Real-time telemetry data."""

    battery_level: int  # 0-100
    battery_voltage: float
    battery_temperature_fault: bool
    state: MowerState
    work_mode: WorkMode
    task_state: TaskState
    mowing_progress: int  # 0-100
    current_mowing_area: float  # m²
    total_mowing_area: float  # m²
    blade_usage_time: float  # hours
    blade_lifetime_hours: float  # manufacturer recommended replacement interval (default 200)
    total_mowing_time: float  # hours
    network_type: str
    cellular_signal: int  # CSQ
    mqtt_connected: bool
    wifi_ssid: str | None


@dataclass
class MaintenanceHint:
    """A single maintenance hint from the device."""

    hint_type: str  # blade_wear, cleaning, service
    title: str
    description: str
    timestamp: datetime


@dataclass
class MaintenanceData:
    """Maintenance and blade management data."""

    blade_usage_hours: float  # cumulative blade operating hours
    blade_lifetime_hours: float  # recommended replacement interval (default 200h)
    blade_remaining_life_pct: float  # calculated: max(0, (1 - usage/lifetime) * 100)
    blade_replacement_needed: bool  # True if remaining life < 10% or hint received
    maintenance_status: str  # ok, blade_replacement_due, cleaning_needed, service_required
    maintenance_hints: list[MaintenanceHint]  # active maintenance hints from API


@dataclass
class LocationData:
    """GPS location data."""

    latitude: float
    longitude: float
    altitude: float
    speed: float
    hdop: float
    satellites_in_use: int
    satellites_in_view: int
    data_valid: bool


@dataclass
class ScheduleEntry:
    """Single schedule entry."""

    start_time: datetime
    end_time: datetime
    zones: list[str]
    active: bool


@dataclass
class ScheduleData:
    """Today's mowing schedule."""

    schedule_enabled: bool
    next_start: datetime | None
    next_end: datetime | None
    schedules: list[ScheduleEntry] = field(default_factory=list)


@dataclass
class SettingsData:
    """Device settings."""

    cutting_height: int  # mm
    work_mode: WorkMode
    rain_sensor: bool
    edge_mowing: bool
    mowing_cycle: bool
    anti_theft: bool
    dark_mode: bool
    anti_interference: bool | None  # None if not supported
    plan_switch: bool


@dataclass
class ZoneInfo:
    """Individual mowing zone."""

    zone_id: str
    name: str
    area: float
    active: bool


@dataclass
class MapData:
    """Map and zone information."""

    boundaries: list[list[tuple[float, float]]]
    islands: list[list[tuple[float, float]]]
    channels: list[list[tuple[float, float]]]
    zones: list[ZoneInfo]
    map_status: str  # valid, needs_update, no_map
    total_area: float  # m²


@dataclass
class ErrorInfo:
    """Active error information."""

    code: int
    title: str
    content: str
    severity: int  # 1-3
    timestamp: datetime


@dataclass
class TrailEntry:
    """Mowing trail history entry."""

    trail_id: str
    date: datetime
    duration: float  # minutes
    area: float  # m²


@dataclass
class FirmwareInfo:
    """Available firmware update info."""

    update_available: bool
    new_version: str | None
    release_notes: str | None
    current_versions: FirmwareVersions


@dataclass
class BmsDetail:
    """Battery management system details."""

    voltage: float
    current: float
    temperature: float
    cycles: int
    health: int  # percentage


@dataclass
class NavimowDeviceData:
    """Complete device data returned by coordinator."""

    device_info: DeviceInfo
    telemetry: DeviceTelemetry
    location: LocationData
    schedule: ScheduleData
    settings: SettingsData
    map_data: MapData | None
    errors: list[ErrorInfo]
    trail_history: list[TrailEntry]
    firmware: FirmwareInfo
    bms: BmsDetail
    maintenance: MaintenanceData
