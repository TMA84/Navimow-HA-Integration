# Requirements Document

## Introduction

This document specifies the requirements for a Home Assistant custom integration for the Segway Navimow i105/i108 robotic lawn mower, distributed via HACS. The integration communicates with the Segway/Ninebot cloud platform to expose device status, sensors, controls, settings, maps, schedules, and error notifications as Home Assistant entities.

### APK Analysis Summary

Reverse engineering of the Navimow Android APK (com.segway.mower v1.5.1) revealed the following architecture:

- **Cloud API**: Regional REST API at `https://navimow-{region}.ninebot.com/` (regions: `fra`, `ore`, `sg`, `bj`, `mos`)
- **Authentication**: OAuth-based via Ninebot Passport service at `https://api-passport-{region}.ninebot.com` with `access_token` and `refresh_token`
- **Real-time Communication**: MQTT for live device state updates (NINEIOT protocol layer)
- **Local Communication**: Bluetooth Low Energy (BLE) via Ninebot BLE protocol with `NbFrame` command structure
- **Push Notifications**: Firebase Cloud Messaging (FCM) via Google project `segway-mower` (sender ID: 270118790436)
- **File Storage**: AWS S3 for map uploads and log files
- **Device Protocol**: IndexTypes-based command/response system with constants like `MOWER_STATE_BOOL`, `MOWER_QUERY`, `MOWER_SET`, `TASK_SET`
- **Network Encryption**: Enabled via `NbEncryption` native library (`libnbcrypto.so`)

### Key API Endpoints Discovered

- `user/user/login` — User authentication
- `user/user/userinfo` — User profile
- `vehicle/vehicle/index` — Device list
- `vehicle/vehicle/get-device-info` — Device details
- `vehicle/vehicle/get-data` — Device telemetry data
- `vehicle/vehicle/get-location` — GPS location
- `vehicle/vehicle/get-today-plan` — Today's mowing schedule
- `vehicle/set/status` — Device settings status
- `vehicle/set/set` — Update device settings
- `vehicle/set/set-power` — Power control
- `vehicle/map/trail-list` — Mowing trail history
- `vehicle/map/trail-detail` — Trail details
- `vehicle/vehicle/get-hint-error` — Active errors
- `vehicle/firmware/get-new-firmware` — Firmware update check
- `vehicle/vehicle/auth` — Device authorization
- `vehicle/vehicle/bms-detail` — Battery management system details

## Glossary

- **Integration**: The Home Assistant custom component that communicates with the Navimow cloud API
- **Coordinator**: The Home Assistant DataUpdateCoordinator responsible for polling and managing data refresh cycles
- **Navimow_API**: The cloud REST API service hosted at `navimow-{region}.ninebot.com` that provides device data and accepts commands
- **Passport_Service**: The Ninebot OAuth authentication service at `api-passport-{region}.ninebot.com`
- **MQTT_Broker**: The message broker used for real-time device state push updates
- **Config_Flow**: The Home Assistant UI-based setup wizard for adding the integration
- **HACS**: Home Assistant Community Store, a third-party integration distribution platform
- **IndexTypes**: The Ninebot protocol's enumeration of device data fields (e.g., `NINEIOT_GPS_LAT`, `MOWER_STATE_BOOL`)
- **NbEncryption**: The native encryption library used to sign and encrypt API requests
- **Region**: The geographic server region (`fra` for Europe, `ore` for US, `sg` for Asia-Pacific, `bj` for China, `mos` for Russia)
- **Device_SN**: The unique serial number identifying a specific Navimow mower
- **Work_Mode**: The mowing speed profile (`WORK_MODE_STANDARD`, `WORK_MODE_FAST`, `WORK_MODE_SILENT`)

## Requirements

### Requirement 1: User Authentication

**User Story:** As a Home Assistant user, I want to authenticate with my Segway/Ninebot account, so that the integration can access my Navimow device data.

#### Acceptance Criteria

1. WHEN the user initiates setup, THE Config_Flow SHALL present fields for email/phone, password, and server region selection.
2. THE Integration SHALL authenticate against the Passport_Service using the `oauth/access_token` endpoint and store the resulting `access_token` and `refresh_token` securely.
3. WHEN the `access_token` expires, THE Integration SHALL automatically refresh it using the stored `refresh_token` without user intervention.
4. IF the `refresh_token` becomes invalid (e.g., after 6 months of inactivity), THEN THE Integration SHALL notify the user via a persistent notification and mark the integration as requiring re-authentication.
5. THE Integration SHALL support all five server regions (`fra`, `ore`, `sg`, `bj`, `mos`) and route API requests to the correct regional endpoint.
6. THE Integration SHALL encrypt API requests using the NbEncryption protocol with the appropriate `appfrom=navimow` and `appbrand=Android` identifiers.

### Requirement 2: Device Discovery and Setup

**User Story:** As a Home Assistant user, I want the integration to automatically discover my Navimow mowers after login, so that I do not need to manually configure each device.

#### Acceptance Criteria

1. WHEN authentication succeeds, THE Integration SHALL query the `vehicle/vehicle/index` endpoint to retrieve all mowers bound to the account.
2. THE Config_Flow SHALL present a list of discovered devices and allow the user to select which devices to add.
3. THE Integration SHALL store the Device_SN, device name, and device model (e.g., i105, i108) for each selected device.
4. WHEN a new device is bound to the account after initial setup, THE Integration SHALL detect it during the next polling cycle and create a new device entry automatically.
5. IF no devices are found on the account, THEN THE Config_Flow SHALL display an informative error message and allow the user to retry or abort.

### Requirement 3: Data Polling and Coordination

**User Story:** As a Home Assistant user, I want the integration to regularly fetch updated device data, so that my dashboard reflects the current state of my mower.

#### Acceptance Criteria

1. THE Coordinator SHALL poll the Navimow_API at a configurable interval with a default of 30 seconds.
2. WHILE the mower is actively mowing (state `WORK_MOWING`), THE Coordinator SHALL increase the polling frequency to 10 seconds.
3. WHILE the mower is idle or charging (states `IDLE_CHARGING`, `IDLE_STANDBY`, `IDLE_PARKING`), THE Coordinator SHALL reduce the polling frequency to 60 seconds.
4. THE Coordinator SHALL batch multiple API calls (`get-device-info`, `get-data`, `get-today-plan`, `status`) into a single update cycle to minimize API load.
5. IF an API request fails due to a network error, THEN THE Coordinator SHALL retry with exponential backoff (initial delay 30 seconds, maximum delay 5 minutes).
6. IF three consecutive polling cycles fail, THEN THE Integration SHALL mark the device as unavailable in Home Assistant.

### Requirement 4: Sensor Entities — Battery and Power

**User Story:** As a Home Assistant user, I want to see battery and charging information, so that I know when my mower is ready to work.

#### Acceptance Criteria

1. THE Integration SHALL expose a `sensor.navimow_battery_level` entity reporting the battery percentage (0–100%) from the `batteryLevel` field.
2. THE Integration SHALL expose a `binary_sensor.navimow_charging` entity that is ON when the device state is `IDLE_CHARGING`.
3. THE Integration SHALL expose a `sensor.navimow_battery_voltage` entity reporting the battery voltage from the `NINEIOT_BAT_VOLT` IndexType.
4. WHEN the battery level drops below 20%, THE Integration SHALL set the battery sensor's icon to a low-battery variant.
5. IF battery temperature is too high or too low for charging, THEN THE Integration SHALL expose this as a `binary_sensor.navimow_battery_temperature_fault` entity.

### Requirement 5: Sensor Entities — Mower Status and Activity

**User Story:** As a Home Assistant user, I want to see the current operational state of my mower, so that I know what it is doing at any time.

#### Acceptance Criteria

1. THE Integration SHALL expose a `sensor.navimow_status` entity with states mapped from the device work states: `mowing`, `returning`, `charging`, `standby`, `paused`, `error`, `mapping`, `calibrating`, `idle_parking`.
2. THE Integration SHALL expose a `sensor.navimow_mowing_progress` entity reporting the current mowing progress percentage (0–100%) from the `MOWER_TEST_PROGRESS` or task progress field.
3. THE Integration SHALL expose a `sensor.navimow_current_task` entity with values: `scheduled_mowing`, `manual_mowing`, `no_task`, `waiting`, `cancelled`, `completed`.
4. WHEN the mower is performing a scheduled task, THE Integration SHALL expose `sensor.navimow_schedule_end_time` with the expected end time.
5. THE Integration SHALL expose a `sensor.navimow_work_mode` entity reporting the current work mode: `standard`, `fast`, or `silent`.

### Requirement 6: Sensor Entities — GPS and Positioning

**User Story:** As a Home Assistant user, I want to see the GPS location and signal quality of my mower, so that I can track it and verify positioning accuracy.

#### Acceptance Criteria

1. THE Integration SHALL expose a `device_tracker.navimow` entity with latitude and longitude from `NINEIOT_GPS_LAT` and `NINEIOT_GPS_LNG` IndexTypes.
2. THE Integration SHALL expose a `sensor.navimow_gps_satellites_in_use` entity from the `NINEIOT_GPS_SAT_IN_USE` IndexType.
3. THE Integration SHALL expose a `sensor.navimow_gps_satellites_in_view` entity from the `NINEIOT_GPS_SAT_IN_VIEW` IndexType.
4. THE Integration SHALL expose a `sensor.navimow_gps_hdop` entity reporting horizontal dilution of precision from `NINEIOT_GPS_HDOP`.
5. THE Integration SHALL expose a `sensor.navimow_gps_speed` entity reporting the current speed from `NINEIOT_GPS_SPEED`.
6. THE Integration SHALL expose a `sensor.navimow_gps_altitude` entity from `NINEIOT_GPS_ALTITUDE`.
7. IF the GPS data is marked invalid (`NINEIOT_GPS_DATA_VALID` is false), THEN THE device_tracker entity SHALL report its state as `unknown`.

### Requirement 7: Sensor Entities — Connectivity

**User Story:** As a Home Assistant user, I want to see the network connectivity status of my mower, so that I can diagnose communication issues.

#### Acceptance Criteria

1. THE Integration SHALL expose a `sensor.navimow_network_type` entity reporting the connection type (`4G`, `Wi-Fi`, `Bluetooth`) from `NINEIOT_DEVICE_TYPE`.
2. THE Integration SHALL expose a `sensor.navimow_cellular_signal` entity reporting the 4G signal strength (CSQ value) from `NINEIOT_GPRS_CSQ`.
3. THE Integration SHALL expose a `binary_sensor.navimow_mqtt_connected` entity reflecting the MQTT connection state from `NINEIOT_MQTT_STATE`.
4. THE Integration SHALL expose a `sensor.navimow_wifi_ssid` entity reporting the connected Wi-Fi network name from `NINEIOT_DEVICE_WIFI_SSID`.
5. WHEN the MQTT connection is lost, THE Integration SHALL set the `binary_sensor.navimow_mqtt_connected` to OFF within one polling cycle.

### Requirement 8: Sensor Entities — Area and Statistics

**User Story:** As a Home Assistant user, I want to see mowing statistics, so that I can track my mower's productivity and maintenance needs.

#### Acceptance Criteria

1. THE Integration SHALL expose a `sensor.navimow_total_mowing_area` entity reporting the cumulative mowed area in square meters from `MAP_TOTAL_AREA`.
2. THE Integration SHALL expose a `sensor.navimow_current_mowing_area` entity reporting the area mowed in the current session from `mowing_area`.
3. THE Integration SHALL expose a `sensor.navimow_total_mowing_time` entity reporting cumulative mowing hours.
4. THE Integration SHALL expose a `sensor.navimow_map_area` entity reporting the total mapped lawn area from the map data.

### Requirement 9: Control Entities — Mowing Operations

**User Story:** As a Home Assistant user, I want to start, stop, pause, and dock my mower from Home Assistant, so that I can control it without the Segway app.

#### Acceptance Criteria

1. THE Integration SHALL expose a `lawn_mower.navimow` entity implementing the Home Assistant LawnMower platform with `start_mowing`, `pause`, and `dock` services.
2. WHEN the user calls `start_mowing`, THE Integration SHALL send the `MOWER_HANDLE_MOW` command via the Navimow_API.
3. WHEN the user calls `pause`, THE Integration SHALL send the `MOWER_HANDLE_STOP` command via the Navimow_API.
4. WHEN the user calls `dock`, THE Integration SHALL send the `MOWER_HANDLE_PARK` command via the Navimow_API.
5. IF a command fails due to the mower being in an incompatible state (e.g., already docked when `dock` is called), THEN THE Integration SHALL raise a HomeAssistantError with a descriptive message.
6. THE Integration SHALL update the entity state within 10 seconds of a successful command execution.

### Requirement 10: Control Entities — Schedule Management

**User Story:** As a Home Assistant user, I want to view and manage mowing schedules, so that I can automate my mowing routine from Home Assistant.

#### Acceptance Criteria

1. THE Integration SHALL expose a `switch.navimow_schedule_enabled` entity to enable or disable the mowing schedule via the `plan_switch` setting.
2. THE Integration SHALL expose a `sensor.navimow_next_schedule_start` entity reporting the next scheduled mowing start time from `vehicle/vehicle/get-today-plan`.
3. THE Integration SHALL expose a `sensor.navimow_next_schedule_end` entity reporting the next scheduled mowing end time.
4. THE Integration SHALL expose a `button.navimow_cancel_today_schedule` entity that cancels today's scheduled mowing task.
5. THE Integration SHALL fire a `navimow_schedule_started` event when a scheduled mowing task begins.
6. THE Integration SHALL support up to 4 schedules per day as enforced by the device firmware.

### Requirement 11: Configuration Entities — Mowing Settings

**User Story:** As a Home Assistant user, I want to adjust mowing settings like cutting height and work mode, so that I can fine-tune my mower's behavior.

#### Acceptance Criteria

1. THE Integration SHALL expose a `number.navimow_cutting_height` entity allowing adjustment of the global cutting height (range determined by device model, typically 20–60mm).
2. THE Integration SHALL expose a `select.navimow_work_mode` entity with options `Standard`, `Fast`, and `Silent` mapped to `WORK_MODE_STANDARD`, `WORK_MODE_FAST`, `WORK_MODE_SILENT`.
3. THE Integration SHALL expose a `switch.navimow_rain_sensor` entity to enable or disable the rain sensor via the `rainSensor` setting.
4. THE Integration SHALL expose a `switch.navimow_edge_mowing` entity to enable or disable edge mowing via the `edgeMowingSwitch` setting.
5. THE Integration SHALL expose a `switch.navimow_mowing_cycle` entity to enable or disable continuous mowing cycles (mow again after 100% completion).
6. WHEN a setting is changed, THE Integration SHALL send the update via `vehicle/set/set` and confirm the change by re-reading the setting within the next polling cycle.
7. IF a setting change fails, THEN THE Integration SHALL revert the entity state to the previous value and log a warning.

### Requirement 12: Configuration Entities — Device Settings

**User Story:** As a Home Assistant user, I want to manage device-level settings like anti-theft and dark mode, so that I have full control over my mower's configuration.

#### Acceptance Criteria

1. THE Integration SHALL expose a `switch.navimow_anti_theft` entity to enable or disable the anti-theft alarm system.
2. THE Integration SHALL expose a `switch.navimow_dark_mode` entity to enable or disable the LED dark mode (dimming at night).
3. WHERE the device supports 4G anti-interference mode, THE Integration SHALL expose a `switch.navimow_anti_interference` entity.
4. THE Integration SHALL expose a `sensor.navimow_device_model` diagnostic entity reporting the device model string.
5. THE Integration SHALL expose a `sensor.navimow_firmware_version` diagnostic entity reporting the current firmware versions (ECU, BMS, GPS, Bluetooth, Wi-Fi, blade motor, charging station, IoT).

### Requirement 13: Map and Zone Support

**User Story:** As a Home Assistant user, I want to see my mowing map and zones, so that I can understand my mower's coverage and select specific zones.

#### Acceptance Criteria

1. THE Integration SHALL retrieve map data including boundaries, off-limit islands, and channels from the device.
2. THE Integration SHALL expose a `sensor.navimow_active_zones` entity listing the currently selected mowing zones.
3. WHERE the device has multiple zones defined, THE Integration SHALL expose a `select.navimow_mowing_zone` entity allowing zone selection for the next mowing task.
4. THE Integration SHALL expose a `sensor.navimow_map_status` entity reporting the map state (valid, needs update, no map).
5. THE Integration SHALL expose map boundary coordinates as device attributes on the `device_tracker` entity for use with map cards.

### Requirement 14: Error Handling and Notifications

**User Story:** As a Home Assistant user, I want to receive notifications about mower errors and events, so that I can respond to problems promptly.

#### Acceptance Criteria

1. THE Integration SHALL expose a `sensor.navimow_error_code` entity reporting the current active error code (0 if no error).
2. THE Integration SHALL expose a `sensor.navimow_error_message` entity reporting the human-readable error description from the error code list (69 vehicle errors, 9 map errors).
3. WHEN a new error occurs, THE Integration SHALL fire a `navimow_error` event containing the error code, title, content, and severity level (1–3).
4. WHEN the mower completes a mowing task, THE Integration SHALL fire a `navimow_mowing_complete` event with the area mowed and duration.
5. WHEN the mower is lifted or stuck, THE Integration SHALL fire a `navimow_alert` event with the specific alert type.
6. IF the mower reports error level 3 (critical), THEN THE Integration SHALL create a persistent notification in Home Assistant.
7. THE Integration SHALL expose a `binary_sensor.navimow_has_error` entity that is ON when any active error exists.

### Requirement 15: Firmware Information and Updates

**User Story:** As a Home Assistant user, I want to see firmware versions and available updates, so that I can keep my mower up to date.

#### Acceptance Criteria

1. THE Integration SHALL expose an `update.navimow_firmware` entity implementing the Home Assistant Update platform.
2. THE Integration SHALL check for firmware updates via the `vehicle/firmware/get-new-firmware` endpoint during each polling cycle (or at a reduced frequency of once per hour).
3. WHEN a firmware update is available, THE `update.navimow_firmware` entity SHALL report the new version and set its state to indicate an update is available.
4. THE Integration SHALL expose diagnostic attributes listing all firmware component versions: ECU, BMS, GPS, Bluetooth, Wi-Fi, blade motor (NCU), charging station (CGS), IoT (Telematics BOX), audio (MSC), bump sensor, and VisionFence (if equipped).

### Requirement 16: HACS Distribution and Integration Structure

**User Story:** As a Home Assistant user, I want to install this integration via HACS, so that I can easily install and update it.

#### Acceptance Criteria

1. THE Integration SHALL include a valid `hacs.json` manifest file with `name`, `homeassistant` minimum version, and `render_readme` fields.
2. THE Integration SHALL include a `manifest.json` file with `domain` set to `navimow`, appropriate `version`, `requirements` for Python dependencies, `codeowners`, and `iot_class` set to `cloud_polling`.
3. THE Integration SHALL implement the Home Assistant config flow (`config_flow.py`) for UI-based setup without YAML configuration.
4. THE Integration SHALL include `translations/en.json` for all user-facing strings in the config flow and entity names.
5. THE Integration SHALL follow the Home Assistant integration file structure: `__init__.py`, `config_flow.py`, `const.py`, `coordinator.py`, `entity.py`, and platform files (`sensor.py`, `binary_sensor.py`, `switch.py`, `select.py`, `number.py`, `button.py`, `lawn_mower.py`, `device_tracker.py`, `update.py`).
6. THE Integration SHALL include a `README.md` with installation instructions, feature list, and configuration guide.

### Requirement 17: Error Recovery and Reconnection

**User Story:** As a Home Assistant user, I want the integration to handle network failures gracefully, so that it recovers automatically without my intervention.

#### Acceptance Criteria

1. IF the API returns HTTP 401 (Unauthorized), THEN THE Integration SHALL attempt to refresh the access token before retrying the request.
2. IF token refresh fails, THEN THE Integration SHALL create a re-authentication flow and notify the user.
3. WHEN Home Assistant restarts, THE Integration SHALL restore the previous session using stored credentials without requiring re-login.
4. IF the API returns HTTP 429 (Rate Limited), THEN THE Integration SHALL back off for the duration specified in the response headers or a default of 60 seconds.
5. THE Integration SHALL log all API errors at the `warning` level and connection state changes at the `info` level.
6. WHILE the integration is in a disconnected state, THE Integration SHALL attempt reconnection every 60 seconds.

### Requirement 18: Device Registry Integration

**User Story:** As a Home Assistant user, I want my Navimow to appear as a proper device in Home Assistant, so that all entities are grouped and identifiable.

#### Acceptance Criteria

1. THE Integration SHALL register each mower as a device in the Home Assistant device registry with manufacturer `Segway`, model from the device info (e.g., `Navimow i105`), and serial number from Device_SN.
2. THE Integration SHALL set the device firmware version from the ECU firmware version field.
3. THE Integration SHALL group all entities for a single mower under its device registry entry.
4. THE Integration SHALL provide a device configuration URL pointing to the Navimow web portal or support page (`https://navimow.segway.com/`).
5. WHEN the user renames the device in Home Assistant, THE Integration SHALL use the custom name as the entity name prefix.

### Requirement 19: Mowing Trail History

**User Story:** As a Home Assistant user, I want to see the mowing trail history, so that I can review past mowing sessions.

#### Acceptance Criteria

1. THE Integration SHALL expose a `sensor.navimow_last_mowing_date` entity reporting the date and time of the last completed mowing session.
2. THE Integration SHALL expose a `sensor.navimow_last_mowing_duration` entity reporting the duration of the last mowing session.
3. THE Integration SHALL expose a `sensor.navimow_last_mowing_area` entity reporting the area covered in the last mowing session.
4. THE Integration SHALL retrieve trail history from the `vehicle/map/trail-list` endpoint.
5. THE Integration SHALL store the last 7 days of mowing trail data as attributes on the history sensor.

### Requirement 20: Maintenance and Blade Management

**User Story:** As a Home Assistant user, I want to see maintenance status including blade wear and cleaning reminders, so that I can keep my mower in optimal condition.

#### Acceptance Criteria

1. THE Integration SHALL expose a `sensor.navimow_blade_usage_time` entity reporting cumulative blade operating hours.
2. THE Integration SHALL expose a `sensor.navimow_blade_remaining_life` entity reporting the estimated remaining blade life as a percentage (0–100%), calculated from blade usage time relative to the manufacturer-recommended replacement interval (typically 200 hours).
3. THE Integration SHALL expose a `binary_sensor.navimow_blade_replacement_needed` entity that is ON when the blade remaining life drops below 10% or when the device reports a blade maintenance hint.
4. THE Integration SHALL expose a `sensor.navimow_maintenance_status` entity reporting the current maintenance state: `ok`, `blade_replacement_due`, `cleaning_needed`, `service_required`.
5. WHEN the device sends a maintenance hint via the `vehicle/vehicle/get-hint-error` endpoint (e.g., blade wear warning, cleaning reminder), THE Integration SHALL fire a `navimow_maintenance` event containing the maintenance type, title, and description.
6. THE Integration SHALL expose a `button.navimow_reset_blade_counter` entity that resets the blade usage counter after a blade replacement (if supported by the API via `vehicle/set/set`).
7. WHEN the blade remaining life drops below 20%, THE Integration SHALL set the blade sensor's icon to a warning variant.
8. THE Integration SHALL expose maintenance hints from the API as attributes on the `sensor.navimow_maintenance_status` entity, including the hint timestamp and recommended action.

### Requirement 21: Security and Data Protection

**User Story:** As a Home Assistant user, I want my credentials and device data to be handled securely, so that my account is protected.

#### Acceptance Criteria

1. THE Integration SHALL store authentication tokens exclusively in the Home Assistant credential store (config entry data), never in plain text files.
2. THE Integration SHALL transmit all API requests over HTTPS with TLS 1.2 or higher.
3. THE Integration SHALL not log access tokens, refresh tokens, or passwords at any log level.
4. THE Integration SHALL validate SSL certificates on all API connections and reject self-signed certificates.
5. IF the user removes the integration, THEN THE Integration SHALL delete all stored credentials and cached data.
