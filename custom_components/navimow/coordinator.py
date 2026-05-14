"""DataUpdateCoordinator for the Navimow integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_client import NavimowApiClient, NavimowApiError
from .models import (
    BmsDetail,
    DeviceInfo,
    DeviceTelemetry,
    ErrorInfo,
    FirmwareInfo,
    FirmwareVersions,
    LocationData,
    MaintenanceData,
    MaintenanceHint,
    MapData,
    MowerState,
    NavimowDeviceData,
    ScheduleData,
    ScheduleEntry,
    SettingsData,
    TaskState,
    TrailEntry,
    WorkMode,
    ZoneInfo,
)

_LOGGER = logging.getLogger(__name__)

# Active states that trigger faster polling
ACTIVE_STATES = {
    MowerState.MOWING,
    MowerState.RETURNING,
    MowerState.MAPPING,
    MowerState.CALIBRATING,
}

# Idle states that trigger slower polling
IDLE_STATES = {
    MowerState.CHARGING,
    MowerState.STANDBY,
    MowerState.IDLE_PARKING,
}


class NavimowCoordinator(DataUpdateCoordinator[NavimowDeviceData]):
    """Coordinator for a single Navimow device with adaptive polling."""

    POLL_INTERVAL_ACTIVE = timedelta(seconds=10)
    POLL_INTERVAL_DEFAULT = timedelta(seconds=30)
    POLL_INTERVAL_IDLE = timedelta(seconds=60)

    FIRMWARE_CHECK_INTERVAL = timedelta(hours=1)
    TRAIL_FETCH_INTERVAL = timedelta(hours=1)

    MAX_FAILURES_BEFORE_UNAVAILABLE = 3
    BACKOFF_INITIAL_DELAY = 30  # seconds
    BACKOFF_MAX_DELAY = 300  # seconds (5 minutes)
    BACKOFF_FACTOR = 2

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_client: NavimowApiClient,
        device_sn: str,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            config_entry: The config entry for this integration.
            api_client: The API client for communicating with the Navimow cloud.
            device_sn: The serial number of the device to coordinate.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"Navimow {device_sn}",
            update_interval=self.POLL_INTERVAL_DEFAULT,
            config_entry=config_entry,
        )
        self.api_client = api_client
        self.device_sn = device_sn

        # Failure tracking for exponential backoff
        self._consecutive_failures: int = 0

        # Firmware check tracking (reduced frequency)
        self._last_firmware_check: datetime | None = None
        self._last_firmware_data: FirmwareInfo | None = None

        # Trail history tracking (reduced frequency)
        self._last_trail_fetch: datetime | None = None
        self._last_trail_data: list[TrailEntry] = []

        # Previous state for detecting transitions
        self._previous_state: MowerState | None = None
        self._previous_task_state: TaskState | None = None

    async def _async_update_data(self) -> NavimowDeviceData:
        """Fetch all device data in a batched update cycle.

        Batches calls to multiple API endpoints and parses responses
        into data model objects. Implements exponential backoff on failures
        and marks the device unavailable after 3 consecutive failures.

        Returns:
            NavimowDeviceData with all parsed device information.

        Raises:
            UpdateFailed: After 3 consecutive failures.
        """
        try:
            data = await self._fetch_all_data()
            # Reset failure counter on success
            self._consecutive_failures = 0
            # Adjust polling interval based on current state
            self._adjust_polling_interval(data.telemetry.state)
            # Detect state changes and fire events
            self._detect_state_changes(data)
            return data
        except NavimowApiError as err:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "API error for device %s (failure %d/%d): %s",
                self.device_sn,
                self._consecutive_failures,
                self.MAX_FAILURES_BEFORE_UNAVAILABLE,
                err,
            )

            if self._consecutive_failures >= self.MAX_FAILURES_BEFORE_UNAVAILABLE:
                raise UpdateFailed(
                    f"Device {self.device_sn} unavailable after "
                    f"{self._consecutive_failures} consecutive failures: {err}"
                ) from err

            # Apply exponential backoff for the next poll
            backoff_delay = self._calculate_backoff(self._consecutive_failures)
            self.update_interval = timedelta(seconds=backoff_delay)
            _LOGGER.debug(
                "Applying backoff of %ds for device %s",
                backoff_delay,
                self.device_sn,
            )

            raise UpdateFailed(
                f"API error for device {self.device_sn}: {err}"
            ) from err
        except Exception as err:
            self._consecutive_failures += 1
            _LOGGER.exception(
                "Unexpected error for device %s (failure %d/%d)",
                self.device_sn,
                self._consecutive_failures,
                self.MAX_FAILURES_BEFORE_UNAVAILABLE,
            )

            if self._consecutive_failures >= self.MAX_FAILURES_BEFORE_UNAVAILABLE:
                raise UpdateFailed(
                    f"Device {self.device_sn} unavailable after "
                    f"{self._consecutive_failures} consecutive failures: {err}"
                ) from err

            backoff_delay = self._calculate_backoff(self._consecutive_failures)
            self.update_interval = timedelta(seconds=backoff_delay)

            raise UpdateFailed(
                f"Unexpected error for device {self.device_sn}: {err}"
            ) from err

    async def _fetch_all_data(self) -> NavimowDeviceData:
        """Batch all API calls and parse responses into data models.

        Returns:
            Complete NavimowDeviceData with all parsed fields.
        """
        # Batch the core API calls
        device_info_raw = await self.api_client.get_device_info(self.device_sn)
        device_data_raw = await self.api_client.get_device_data(self.device_sn)
        today_plan_raw = await self.api_client.get_today_plan(self.device_sn)
        settings_raw = await self.api_client.get_settings_status(self.device_sn)
        location_raw = await self.api_client.get_location(self.device_sn)
        errors_raw = await self.api_client.get_errors(self.device_sn)

        # Firmware check at reduced frequency (once per hour)
        firmware_data = await self._fetch_firmware_if_due()

        # Trail history at reduced frequency (once per hour or on task completion)
        trail_data = await self._fetch_trail_if_due(device_data_raw)

        # Parse raw responses into data model objects
        device_info = self._parse_device_info(device_info_raw)
        telemetry = self._parse_telemetry(device_data_raw)
        location = self._parse_location(location_raw)
        schedule = self._parse_schedule(today_plan_raw)
        settings = self._parse_settings(settings_raw)
        errors = self._parse_errors(errors_raw)
        maintenance = self._build_maintenance_data(telemetry)

        return NavimowDeviceData(
            device_info=device_info,
            telemetry=telemetry,
            location=location,
            schedule=schedule,
            settings=settings,
            map_data=None,  # Map data fetched separately when needed
            errors=errors,
            trail_history=trail_data,
            firmware=firmware_data,
            bms=BmsDetail(
                voltage=telemetry.battery_voltage,
                current=0.0,
                temperature=0.0,
                cycles=0,
                health=100,
            ),
            maintenance=maintenance,
        )

    async def _fetch_firmware_if_due(self) -> FirmwareInfo:
        """Fetch firmware info only if the check interval has elapsed.

        Returns:
            FirmwareInfo from API or cached data.
        """
        now = datetime.now(tz=timezone.utc)
        should_check = (
            self._last_firmware_check is None
            or (now - self._last_firmware_check) >= self.FIRMWARE_CHECK_INTERVAL
        )

        if should_check:
            try:
                firmware_raw = await self.api_client.get_firmware_info(self.device_sn)
                self._last_firmware_data = self._parse_firmware(firmware_raw)
                self._last_firmware_check = now
            except NavimowApiError:
                _LOGGER.debug(
                    "Firmware check failed for %s, using cached data",
                    self.device_sn,
                )

        if self._last_firmware_data is not None:
            return self._last_firmware_data

        # Return a default if we've never fetched firmware data
        return FirmwareInfo(
            update_available=False,
            new_version=None,
            release_notes=None,
            current_versions=FirmwareVersions(
                ecu="unknown",
                bms="unknown",
                gps="unknown",
                bluetooth="unknown",
                wifi="unknown",
                blade_motor="unknown",
                charging_station="unknown",
                iot="unknown",
                audio="unknown",
                bump_sensor="unknown",
                vision_fence=None,
            ),
        )

    async def _fetch_trail_if_due(
        self, device_data_raw: dict[str, Any]
    ) -> list[TrailEntry]:
        """Fetch trail history if the interval has elapsed or task completed.

        Args:
            device_data_raw: Raw device data to check for task completion.

        Returns:
            List of TrailEntry objects.
        """
        now = datetime.now(tz=timezone.utc)
        task_state_str = device_data_raw.get("task_state", "")
        task_just_completed = (
            task_state_str == TaskState.COMPLETED
            and self._previous_task_state is not None
            and self._previous_task_state != TaskState.COMPLETED
        )

        should_fetch = (
            self._last_trail_fetch is None
            or (now - self._last_trail_fetch) >= self.TRAIL_FETCH_INTERVAL
            or task_just_completed
        )

        if should_fetch:
            try:
                trail_raw = await self.api_client.get_trail_list(self.device_sn)
                self._last_trail_data = self._parse_trail_list(trail_raw)
                self._last_trail_fetch = now
            except NavimowApiError:
                _LOGGER.debug(
                    "Trail fetch failed for %s, using cached data",
                    self.device_sn,
                )

        return self._last_trail_data

    def _adjust_polling_interval(self, state: MowerState) -> None:
        """Adjust update_interval based on mower activity state.

        Active states (mowing, returning, mapping, calibrating) → 10s
        Idle states (charging, standby, idle_parking) → 60s
        Other states (paused, error) → 30s

        Args:
            state: The current MowerState of the device.
        """
        if state in ACTIVE_STATES:
            new_interval = self.POLL_INTERVAL_ACTIVE
        elif state in IDLE_STATES:
            new_interval = self.POLL_INTERVAL_IDLE
        else:
            new_interval = self.POLL_INTERVAL_DEFAULT

        if self.update_interval != new_interval:
            _LOGGER.debug(
                "Adjusting polling interval for %s from %s to %s (state: %s)",
                self.device_sn,
                self.update_interval,
                new_interval,
                state,
            )
            self.update_interval = new_interval

    @staticmethod
    def _calculate_backoff(consecutive_failures: int) -> float:
        """Calculate exponential backoff delay.

        Formula: min(30 * 2^(N-1), 300) where N is consecutive failure count.

        Args:
            consecutive_failures: Number of consecutive failures (N >= 1).

        Returns:
            Backoff delay in seconds, between 30 and 300.
        """
        delay = 30 * (2 ** (consecutive_failures - 1))
        return min(delay, 300)

    def _detect_state_changes(self, data: NavimowDeviceData) -> None:
        """Detect state transitions and fire events.

        Fires events for:
        - New errors appearing
        - Alert on lift/stuck detection (error codes 1, 2)
        - Task completion
        - Schedule started
        - Maintenance hints

        Args:
            data: The newly fetched device data.
        """
        current_state = data.telemetry.state
        current_task_state = data.telemetry.task_state

        # Fire error event if new errors appeared
        if data.errors and self._previous_state != MowerState.ERROR and current_state == MowerState.ERROR:
            for error in data.errors:
                self.hass.bus.async_fire(
                    "navimow_error",
                    {
                        "device_sn": self.device_sn,
                        "code": error.code,
                        "title": error.title,
                        "content": error.content,
                        "severity": error.severity,
                    },
                )

                # Fire alert event for lift/stuck detection (codes 1=lifted, 2=stuck)
                if error.code in (1, 2):
                    alert_type = "lifted" if error.code == 1 else "stuck"
                    self.hass.bus.async_fire(
                        "navimow_alert",
                        {
                            "device_sn": self.device_sn,
                            "alert_type": alert_type,
                            "code": error.code,
                            "title": error.title,
                            "content": error.content,
                        },
                    )

                # Create persistent notification for severity level 3 errors
                if error.severity >= 3:
                    self.hass.components.persistent_notification.async_create(
                        message=(
                            f"Navimow {self.device_sn}: {error.title}\n\n"
                            f"{error.content}"
                        ),
                        title=f"Navimow Critical Error ({error.code})",
                        notification_id=f"navimow_error_{self.device_sn}_{error.code}",
                    )

        # Fire task completion event
        if (
            current_task_state == TaskState.COMPLETED
            and self._previous_task_state is not None
            and self._previous_task_state != TaskState.COMPLETED
        ):
            self.hass.bus.async_fire(
                "navimow_mowing_complete",
                {
                    "device_sn": self.device_sn,
                    "area": data.telemetry.current_mowing_area,
                    "total_mowing_time": data.telemetry.total_mowing_time,
                },
            )

        # Fire schedule started event when task transitions to scheduled_mowing
        if (
            current_task_state == TaskState.SCHEDULED_MOWING
            and self._previous_task_state is not None
            and self._previous_task_state != TaskState.SCHEDULED_MOWING
        ):
            self.hass.bus.async_fire(
                "navimow_schedule_started",
                {
                    "device_sn": self.device_sn,
                    "task_state": current_task_state.value,
                },
            )

        # Fire maintenance event when maintenance hints are present
        hints = data.maintenance.maintenance_hints
        if isinstance(hints, list) and len(hints) > 0:
            self.hass.bus.async_fire(
                "navimow_maintenance",
                {
                    "device_sn": self.device_sn,
                    "status": data.maintenance.maintenance_status,
                    "hints": [
                        {
                            "type": hint.hint_type,
                            "title": hint.title,
                            "description": hint.description,
                        }
                        for hint in hints
                    ],
                },
            )

        # Update previous state tracking
        self._previous_state = current_state
        self._previous_task_state = current_task_state

    # ─── Response Parsing ───────────────────────────────────────────────

    @staticmethod
    def _parse_device_info(raw: dict[str, Any]) -> DeviceInfo:
        """Parse raw device info response into DeviceInfo dataclass.

        Args:
            raw: Raw dictionary from the API.

        Returns:
            Parsed DeviceInfo instance.
        """
        fw_raw = raw.get("firmware_versions", {})
        firmware_versions = FirmwareVersions(
            ecu=fw_raw.get("ecu", "unknown"),
            bms=fw_raw.get("bms", "unknown"),
            gps=fw_raw.get("gps", "unknown"),
            bluetooth=fw_raw.get("bluetooth", "unknown"),
            wifi=fw_raw.get("wifi", "unknown"),
            blade_motor=fw_raw.get("blade_motor", "unknown"),
            charging_station=fw_raw.get("charging_station", "unknown"),
            iot=fw_raw.get("iot", "unknown"),
            audio=fw_raw.get("audio", "unknown"),
            bump_sensor=fw_raw.get("bump_sensor", "unknown"),
            vision_fence=fw_raw.get("vision_fence"),
        )
        return DeviceInfo(
            device_sn=raw.get("device_sn", ""),
            model=raw.get("model", ""),
            name=raw.get("name", ""),
            firmware_versions=firmware_versions,
        )

    @staticmethod
    def _parse_telemetry(raw: dict[str, Any]) -> DeviceTelemetry:
        """Parse raw telemetry response into DeviceTelemetry dataclass.

        Args:
            raw: Raw dictionary from the API.

        Returns:
            Parsed DeviceTelemetry instance.
        """
        state_str = raw.get("state", "standby")
        try:
            state = MowerState(state_str)
        except ValueError:
            _LOGGER.warning("Unknown mower state: %s, defaulting to standby", state_str)
            state = MowerState.STANDBY

        work_mode_str = raw.get("work_mode", "standard")
        try:
            work_mode = WorkMode(work_mode_str)
        except ValueError:
            work_mode = WorkMode.STANDARD

        task_state_str = raw.get("task_state", "no_task")
        try:
            task_state = TaskState(task_state_str)
        except ValueError:
            task_state = TaskState.NO_TASK

        return DeviceTelemetry(
            battery_level=int(raw.get("battery_level", 0)),
            battery_voltage=float(raw.get("battery_voltage", 0.0)),
            battery_temperature_fault=bool(raw.get("battery_temperature_fault", False)),
            state=state,
            work_mode=work_mode,
            task_state=task_state,
            mowing_progress=int(raw.get("mowing_progress", 0)),
            current_mowing_area=float(raw.get("current_mowing_area", 0.0)),
            total_mowing_area=float(raw.get("total_mowing_area", 0.0)),
            blade_usage_time=float(raw.get("blade_usage_time", 0.0)),
            blade_lifetime_hours=float(raw.get("blade_lifetime_hours", 200.0)),
            total_mowing_time=float(raw.get("total_mowing_time", 0.0)),
            network_type=str(raw.get("network_type", "")),
            cellular_signal=int(raw.get("cellular_signal", 0)),
            mqtt_connected=bool(raw.get("mqtt_connected", False)),
            wifi_ssid=raw.get("wifi_ssid"),
        )

    @staticmethod
    def _parse_location(raw: dict[str, Any]) -> LocationData:
        """Parse raw location response into LocationData dataclass.

        Args:
            raw: Raw dictionary from the API.

        Returns:
            Parsed LocationData instance.
        """
        return LocationData(
            latitude=float(raw.get("latitude", 0.0)),
            longitude=float(raw.get("longitude", 0.0)),
            altitude=float(raw.get("altitude", 0.0)),
            speed=float(raw.get("speed", 0.0)),
            hdop=float(raw.get("hdop", 0.0)),
            satellites_in_use=int(raw.get("satellites_in_use", 0)),
            satellites_in_view=int(raw.get("satellites_in_view", 0)),
            data_valid=bool(raw.get("data_valid", False)),
        )

    @staticmethod
    def _parse_schedule(raw: dict[str, Any]) -> ScheduleData:
        """Parse raw schedule response into ScheduleData dataclass.

        Args:
            raw: Raw dictionary from the API.

        Returns:
            Parsed ScheduleData instance.
        """
        schedules = []
        for entry_raw in raw.get("schedules", []):
            try:
                start_time = datetime.fromisoformat(entry_raw["start_time"])
                end_time = datetime.fromisoformat(entry_raw["end_time"])
                schedules.append(
                    ScheduleEntry(
                        start_time=start_time,
                        end_time=end_time,
                        zones=entry_raw.get("zones", []),
                        active=bool(entry_raw.get("active", False)),
                    )
                )
            except (KeyError, ValueError) as err:
                _LOGGER.debug("Skipping invalid schedule entry: %s", err)

        next_start = None
        next_end = None
        if raw.get("next_start"):
            try:
                next_start = datetime.fromisoformat(raw["next_start"])
            except ValueError:
                pass
        if raw.get("next_end"):
            try:
                next_end = datetime.fromisoformat(raw["next_end"])
            except ValueError:
                pass

        return ScheduleData(
            schedule_enabled=bool(raw.get("schedule_enabled", False)),
            next_start=next_start,
            next_end=next_end,
            schedules=schedules,
        )

    @staticmethod
    def _parse_settings(raw: dict[str, Any]) -> SettingsData:
        """Parse raw settings response into SettingsData dataclass.

        Args:
            raw: Raw dictionary from the API.

        Returns:
            Parsed SettingsData instance.
        """
        work_mode_str = raw.get("work_mode", "standard")
        try:
            work_mode = WorkMode(work_mode_str)
        except ValueError:
            work_mode = WorkMode.STANDARD

        return SettingsData(
            cutting_height=int(raw.get("cutting_height", 40)),
            work_mode=work_mode,
            rain_sensor=bool(raw.get("rain_sensor", False)),
            edge_mowing=bool(raw.get("edge_mowing", False)),
            mowing_cycle=bool(raw.get("mowing_cycle", False)),
            anti_theft=bool(raw.get("anti_theft", False)),
            dark_mode=bool(raw.get("dark_mode", False)),
            anti_interference=raw.get("anti_interference"),
            plan_switch=bool(raw.get("plan_switch", False)),
        )

    @staticmethod
    def _parse_errors(raw: list[dict[str, Any]]) -> list[ErrorInfo]:
        """Parse raw errors response into list of ErrorInfo dataclasses.

        Args:
            raw: Raw list of error dictionaries from the API.

        Returns:
            List of parsed ErrorInfo instances.
        """
        errors = []
        for error_raw in raw:
            try:
                timestamp_str = error_raw.get("timestamp", "")
                timestamp = (
                    datetime.fromisoformat(timestamp_str)
                    if timestamp_str
                    else datetime.now(tz=timezone.utc)
                )
                errors.append(
                    ErrorInfo(
                        code=int(error_raw.get("code", 0)),
                        title=str(error_raw.get("title", "")),
                        content=str(error_raw.get("content", "")),
                        severity=int(error_raw.get("severity", 1)),
                        timestamp=timestamp,
                    )
                )
            except (ValueError, TypeError) as err:
                _LOGGER.debug("Skipping invalid error entry: %s", err)
        return errors

    @staticmethod
    def _parse_trail_list(raw: list[dict[str, Any]]) -> list[TrailEntry]:
        """Parse raw trail list response into list of TrailEntry dataclasses.

        Args:
            raw: Raw list of trail dictionaries from the API.

        Returns:
            List of parsed TrailEntry instances.
        """
        trails = []
        for trail_raw in raw:
            try:
                date_str = trail_raw.get("date", "")
                date = (
                    datetime.fromisoformat(date_str)
                    if date_str
                    else datetime.now(tz=timezone.utc)
                )
                trails.append(
                    TrailEntry(
                        trail_id=str(trail_raw.get("trail_id", "")),
                        date=date,
                        duration=float(trail_raw.get("duration", 0.0)),
                        area=float(trail_raw.get("area", 0.0)),
                    )
                )
            except (ValueError, TypeError) as err:
                _LOGGER.debug("Skipping invalid trail entry: %s", err)
        return trails

    @staticmethod
    def _parse_firmware(raw: dict[str, Any]) -> FirmwareInfo:
        """Parse raw firmware response into FirmwareInfo dataclass.

        Args:
            raw: Raw dictionary from the API.

        Returns:
            Parsed FirmwareInfo instance.
        """
        versions_raw = raw.get("current_versions", {})
        current_versions = FirmwareVersions(
            ecu=versions_raw.get("ecu", "unknown"),
            bms=versions_raw.get("bms", "unknown"),
            gps=versions_raw.get("gps", "unknown"),
            bluetooth=versions_raw.get("bluetooth", "unknown"),
            wifi=versions_raw.get("wifi", "unknown"),
            blade_motor=versions_raw.get("blade_motor", "unknown"),
            charging_station=versions_raw.get("charging_station", "unknown"),
            iot=versions_raw.get("iot", "unknown"),
            audio=versions_raw.get("audio", "unknown"),
            bump_sensor=versions_raw.get("bump_sensor", "unknown"),
            vision_fence=versions_raw.get("vision_fence"),
        )
        return FirmwareInfo(
            update_available=bool(raw.get("update_available", False)),
            new_version=raw.get("new_version"),
            release_notes=raw.get("release_notes"),
            current_versions=current_versions,
        )

    @staticmethod
    def _build_maintenance_data(telemetry: DeviceTelemetry) -> MaintenanceData:
        """Build maintenance data from telemetry information.

        Args:
            telemetry: Parsed telemetry data.

        Returns:
            MaintenanceData with calculated blade life.
        """
        lifetime = telemetry.blade_lifetime_hours
        usage = telemetry.blade_usage_time

        if lifetime > 0:
            remaining_pct = max(0.0, (1 - usage / lifetime) * 100)
        else:
            remaining_pct = 0.0

        replacement_needed = remaining_pct < 10.0

        if replacement_needed:
            status = "blade_replacement_due"
        else:
            status = "ok"

        return MaintenanceData(
            blade_usage_hours=usage,
            blade_lifetime_hours=lifetime,
            blade_remaining_life_pct=remaining_pct,
            blade_replacement_needed=replacement_needed,
            maintenance_status=status,
            maintenance_hints=[],
        )
