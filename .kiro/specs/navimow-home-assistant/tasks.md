# Implementation Plan: Navimow Home Assistant Integration

## Overview

This plan implements a HACS-compatible Home Assistant custom integration for the Segway Navimow i105/i108 robotic lawn mower. The implementation follows an incremental approach: scaffolding first, then core API/auth layers, followed by entity platforms, and finally advanced features like maps, maintenance, and firmware updates. Property-based tests are placed close to the code they validate.

## Tasks

- [x] 1. Project scaffolding and HACS structure
  - [x] 1.1 Create directory structure and manifest files
    - Create `custom_components/navimow/` directory
    - Create `manifest.json` with domain `navimow`, `iot_class: cloud_polling`, `config_flow: true`, `requirements: ["aiohttp>=3.8.0"]`, `version: 1.0.0`, `homeassistant: 2024.1.0`
    - Create `hacs.json` at repository root with `name`, `homeassistant`, and `render_readme` fields
    - Create `custom_components/navimow/const.py` with DOMAIN, PLATFORMS list, default intervals, region constants, and IndexType constants
    - Create empty `custom_components/navimow/__init__.py` with basic integration setup stub (platform forwarding)
    - _Requirements: 16.1, 16.2, 16.5_

  - [x] 1.2 Create test infrastructure
    - Create `tests/` directory with `conftest.py` containing shared fixtures (mock aiohttp session, mock API responses, mock coordinator)
    - Set up `pytest`, `pytest-asyncio`, and `hypothesis` in test dependencies
    - _Requirements: 16.5_

- [x] 2. Core API client and authentication
  - [x] 2.1 Implement NbEncryption request signing
    - Create `custom_components/navimow/encryption.py`
    - Implement `sign_params()` with HMAC-based signature generation
    - Implement `generate_nonce()` for random nonce creation
    - Implement `build_signed_headers()` with `appfrom=navimow` and `appbrand=Android`
    - _Requirements: 1.6, 21.2_

  - [x] 2.2 Write property test for request signing determinism
    - **Property 2: Request Signing Determinism**
    - Test that identical inputs always produce identical signatures
    - Test that signed headers always contain `appfrom=navimow` and `appbrand=Android`
    - **Validates: Requirements 1.6**

  - [x] 2.3 Implement NavimowAuth token management
    - Create `custom_components/navimow/auth.py`
    - Implement `async_get_access_token()` with automatic refresh when expired
    - Implement `async_refresh_token()` using refresh_token grant
    - Implement `async_login()` static method for initial authentication
    - Implement `sign_request()` delegating to NbEncryption
    - Regional passport URL construction: `https://api-passport-{region}.ninebot.com/`
    - _Requirements: 1.2, 1.3, 1.5, 17.1, 17.2_

  - [x] 2.4 Write property test for token refresh on expiry
    - **Property 3: Token Refresh on Expiry**
    - Test that expired tokens trigger refresh before API requests
    - Test that refreshed token (not expired one) is used for the request
    - **Validates: Requirements 1.3, 17.1**

  - [x] 2.5 Implement NavimowApiClient
    - Create `custom_components/navimow/api_client.py`
    - Implement regional base URL construction: `https://navimow-{region}.ninebot.com/`
    - Implement all GET endpoints: `get_devices`, `get_device_info`, `get_device_data`, `get_today_plan`, `get_settings_status`, `get_location`, `get_trail_list`, `get_trail_detail`, `get_errors`, `get_firmware_info`, `get_bms_detail`
    - Implement command endpoints: `send_command`, `set_setting`, `set_power`
    - Implement HTTP error handling (401 → token refresh, 429 → backoff, 5xx → retry)
    - _Requirements: 1.5, 1.6, 17.1, 17.4, 21.2, 21.4_

  - [x] 2.6 Write property tests for API client
    - **Property 1: Regional URL Construction**
    - Test that all valid regions produce correct API and passport URLs
    - **Property 10: Rate Limit Backoff Duration**
    - Test that Retry-After header is respected, defaults to 60s when absent
    - **Validates: Requirements 1.5, 17.4**

- [x] 3. Data models and constants
  - [x] 3.1 Implement data models and enums
    - Create `custom_components/navimow/models.py`
    - Implement all dataclasses: `NavimowDevice`, `DeviceInfo`, `FirmwareVersions`, `DeviceTelemetry`, `MaintenanceData`, `MaintenanceHint`, `LocationData`, `ScheduleData`, `ScheduleEntry`, `SettingsData`, `MapData`, `ZoneInfo`, `ErrorInfo`, `TrailEntry`, `FirmwareInfo`, `BmsDetail`, `NavimowDeviceData`
    - Implement enums: `MowerState`, `WorkMode`, `TaskState`
    - Implement state mapping function from API state codes to `MowerState`
    - Implement `MowerState` to `LawnMowerActivity` mapping function
    - _Requirements: 5.1, 9.1_

  - [x] 3.2 Write property tests for state mappings
    - **Property 6: API State Code to MowerState Mapping**
    - Test that every valid API state code maps to exactly one MowerState
    - **Property 7: MowerState to LawnMowerActivity Mapping**
    - Test that every MowerState maps to exactly one LawnMowerActivity
    - **Validates: Requirements 5.1, 9.1**

  - [x] 3.3 Implement error code mapping
    - Create `custom_components/navimow/errors.py`
    - Define error code to message mapping (69 vehicle errors, 9 map errors)
    - Implement `get_error_message(code: int) -> str` function
    - Define custom exceptions: `NavimowApiError`, `NavimowAuthError`, `NavimowCommandError`
    - _Requirements: 14.1, 14.2_

  - [x] 3.4 Write property test for error code mapping
    - **Property 9: Error Code to Message Mapping**
    - Test that all valid error codes (1–69 vehicle, 1–9 map) return non-empty strings
    - Test that error code 0 returns empty string or "No error"
    - **Validates: Requirements 14.2**

- [x] 4. Checkpoint - Ensure core layers work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Coordinator with adaptive polling
  - [x] 5.1 Implement NavimowCoordinator
    - Create `custom_components/navimow/coordinator.py`
    - Extend `DataUpdateCoordinator[NavimowDeviceData]`
    - Implement `_async_update_data()` batching calls to `get_device_info`, `get_device_data`, `get_today_plan`, `get_settings_status`, `get_location`, `get_errors`
    - Implement `_adjust_polling_interval()` based on MowerState (10s active, 30s default, 60s idle)
    - Implement exponential backoff on failures: `min(30 * 2^(N-1), 300)` seconds
    - Mark device unavailable after 3 consecutive failures
    - Implement firmware check at reduced frequency (once per hour)
    - Implement trail history fetch (once per hour or on task completion)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 5.2 Write property test for polling interval mapping
    - **Property 4: State-to-Polling-Interval Mapping**
    - Test that active states (mowing, returning, mapping, calibrating) → 10s
    - Test that idle states (charging, standby, idle_parking) → 60s
    - Test that other states (paused, error) → 30s
    - **Validates: Requirements 3.2, 3.3**

  - [x] 5.3 Write property test for exponential backoff
    - **Property 5: Exponential Backoff Calculation**
    - Test that delay = min(30 * 2^(N-1), 300) for any N ≥ 1
    - Test that delay never exceeds 300s and never falls below 30s
    - **Validates: Requirements 3.5**

- [x] 6. Config flow
  - [x] 6.1 Implement config flow
    - Create `custom_components/navimow/config_flow.py`
    - Implement `async_step_user()`: email/phone, password, region selection form
    - Implement `async_step_devices()`: device selection after successful auth
    - Implement `async_step_reauth()` and `async_step_reauth_confirm()` for re-authentication
    - Handle errors: invalid credentials, no devices found, network errors
    - Store tokens in config entry data
    - _Requirements: 1.1, 1.4, 2.1, 2.2, 2.3, 2.5, 17.2, 17.3, 21.1_

  - [x] 6.2 Create translations
    - Create `custom_components/navimow/strings.json` with all config flow strings
    - Create `custom_components/navimow/translations/en.json` with entity names and config flow translations
    - _Requirements: 16.4_

  - [x] 6.3 Write unit tests for config flow
    - Test happy path: login → device selection → entry creation
    - Test error paths: invalid credentials, no devices, network error
    - Test reauth flow trigger and completion
    - _Requirements: 1.1, 1.4, 2.5_

- [x] 7. Entity base class and device registry
  - [x] 7.1 Implement entity base class and integration setup
    - Create `custom_components/navimow/entity.py` with `NavimowEntity` base class
    - Implement `device_info` property returning manufacturer `Segway`, model, serial number, firmware version, configuration URL `https://navimow.segway.com/`
    - Update `custom_components/navimow/__init__.py` with full `async_setup_entry()`: create API client, auth, coordinator per device; forward platforms; handle unload
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5_

- [x] 8. Checkpoint - Ensure config flow and coordinator work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Sensor entities
  - [x] 9.1 Implement battery and power sensors
    - Create `custom_components/navimow/sensor.py`
    - Implement `sensor.navimow_battery_level` (0–100%, low-battery icon below 20%)
    - Implement `sensor.navimow_battery_voltage`
    - _Requirements: 4.1, 4.3, 4.4_

  - [x] 9.2 Implement status and activity sensors
    - Implement `sensor.navimow_status` with mapped states
    - Implement `sensor.navimow_mowing_progress` (0–100%)
    - Implement `sensor.navimow_current_task` with TaskState values
    - Implement `sensor.navimow_schedule_end_time`
    - Implement `sensor.navimow_work_mode`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 9.3 Implement GPS and positioning sensors
    - Implement `sensor.navimow_gps_satellites_in_use`
    - Implement `sensor.navimow_gps_satellites_in_view`
    - Implement `sensor.navimow_gps_hdop`
    - Implement `sensor.navimow_gps_speed`
    - Implement `sensor.navimow_gps_altitude`
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 9.4 Implement connectivity sensors
    - Implement `sensor.navimow_network_type`
    - Implement `sensor.navimow_cellular_signal`
    - Implement `sensor.navimow_wifi_ssid`
    - _Requirements: 7.1, 7.2, 7.4_

  - [x] 9.5 Implement area and statistics sensors
    - Implement `sensor.navimow_total_mowing_area`
    - Implement `sensor.navimow_current_mowing_area`
    - Implement `sensor.navimow_total_mowing_time`
    - Implement `sensor.navimow_map_area`
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 9.6 Implement schedule sensors
    - Implement `sensor.navimow_next_schedule_start`
    - Implement `sensor.navimow_next_schedule_end`
    - _Requirements: 10.2, 10.3_

  - [x] 9.7 Implement diagnostic sensors
    - Implement `sensor.navimow_device_model` (diagnostic)
    - Implement `sensor.navimow_firmware_version` (diagnostic)
    - _Requirements: 12.4, 12.5_

- [x] 10. Binary sensor entities
  - [x] 10.1 Implement binary sensors
    - Create `custom_components/navimow/binary_sensor.py`
    - Implement `binary_sensor.navimow_charging` (ON when state is IDLE_CHARGING)
    - Implement `binary_sensor.navimow_battery_temperature_fault`
    - Implement `binary_sensor.navimow_mqtt_connected`
    - Implement `binary_sensor.navimow_has_error`
    - _Requirements: 4.2, 4.5, 7.3, 7.5, 14.7_

- [x] 11. Control entities
  - [x] 11.1 Implement lawn mower entity
    - Create `custom_components/navimow/lawn_mower.py`
    - Implement `lawn_mower.navimow` with `start_mowing`, `pause`, `dock` services
    - Map MowerState to LawnMowerActivity
    - Handle command errors with `HomeAssistantError`
    - Trigger coordinator refresh after successful command (within 10s)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 11.2 Implement switch entities
    - Create `custom_components/navimow/switch.py`
    - Implement `switch.navimow_schedule_enabled` (plan_switch setting)
    - Implement `switch.navimow_rain_sensor`
    - Implement `switch.navimow_edge_mowing`
    - Implement `switch.navimow_mowing_cycle`
    - Implement `switch.navimow_anti_theft`
    - Implement `switch.navimow_dark_mode`
    - Implement `switch.navimow_anti_interference` (conditional on device support)
    - Implement setting change with rollback on failure
    - _Requirements: 10.1, 11.3, 11.4, 11.5, 11.6, 11.7, 12.1, 12.2, 12.3_

  - [x] 11.3 Implement select entities
    - Create `custom_components/navimow/select.py`
    - Implement `select.navimow_work_mode` with options Standard, Fast, Silent
    - _Requirements: 11.2_

  - [x] 11.4 Implement number entities
    - Create `custom_components/navimow/number.py`
    - Implement `number.navimow_cutting_height` with model-appropriate range (20–60mm)
    - _Requirements: 11.1_

  - [x] 11.5 Implement button entities
    - Create `custom_components/navimow/button.py`
    - Implement `button.navimow_cancel_today_schedule`
    - _Requirements: 10.4_

- [x] 12. Device tracker entity
  - [x] 12.1 Implement device tracker
    - Create `custom_components/navimow/device_tracker.py`
    - Implement `device_tracker.navimow` with latitude/longitude from GPS data
    - Set state to `unknown` when GPS data is invalid
    - Expose map boundary coordinates as device attributes
    - _Requirements: 6.1, 6.7, 13.5_

  - [x] 12.2 Write property test for GPS validity
    - **Property 8: GPS Validity to Device Tracker State**
    - Test that `data_valid=False` → state is `unknown`
    - Test that `data_valid=True` → state is `home` or `not_home` with valid coordinates
    - **Validates: Requirements 6.7**

- [x] 13. Checkpoint - Ensure all entity platforms work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Error handling and events
  - [x] 14.1 Implement error sensor entities
    - Implement `sensor.navimow_error_code` (0 if no error)
    - Implement `sensor.navimow_error_message` (human-readable from error code mapping)
    - _Requirements: 14.1, 14.2_

  - [x] 14.2 Implement event firing
    - Fire `navimow_error` event on new error (code, title, content, severity)
    - Fire `navimow_mowing_complete` event on task completion (area, duration)
    - Fire `navimow_alert` event on lift/stuck detection
    - Fire `navimow_schedule_started` event when scheduled task begins
    - Create persistent notification for severity level 3 errors
    - _Requirements: 14.3, 14.4, 14.5, 14.6, 10.5_

- [x] 15. Maintenance entities
  - [x] 15.1 Implement maintenance sensors and controls
    - Implement `sensor.navimow_blade_usage_time`
    - Implement `sensor.navimow_blade_remaining_life` (calculated percentage, warning icon below 20%)
    - Implement `binary_sensor.navimow_blade_replacement_needed` (ON when < 10% or hint received)
    - Implement `sensor.navimow_maintenance_status` with maintenance hints as attributes
    - Implement `button.navimow_reset_blade_counter`
    - Fire `navimow_maintenance` event on maintenance hints
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8_

  - [x] 15.2 Write property test for blade life calculation
    - **Property 12: Blade Remaining Life Calculation**
    - Test that remaining life = max(0, (1 - U/L) * 100) for any U ≥ 0, L > 0
    - Test that result is always in [0, 100]
    - Test that blade_replacement_needed is True iff remaining life < 10%
    - **Validates: Requirements 20.2, 20.3**

- [x] 16. Map and zone support
  - [x] 16.1 Implement map and zone entities
    - Implement `sensor.navimow_active_zones`
    - Implement `select.navimow_mowing_zone` (conditional on multiple zones)
    - Implement `sensor.navimow_map_status`
    - Retrieve and parse map data (boundaries, islands, channels) in coordinator
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 17. Trail history entities
  - [x] 17.1 Implement trail history sensors
    - Implement `sensor.navimow_last_mowing_date`
    - Implement `sensor.navimow_last_mowing_duration`
    - Implement `sensor.navimow_last_mowing_area`
    - Store last 7 days of trail data as attributes
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5_

- [x] 18. Firmware update entity
  - [x] 18.1 Implement update entity
    - Create `custom_components/navimow/update.py`
    - Implement `update.navimow_firmware` using Home Assistant Update platform
    - Report new version and update availability
    - Expose all firmware component versions as diagnostic attributes (ECU, BMS, GPS, Bluetooth, Wi-Fi, NCU, CGS, IoT, MSC, bump sensor, VisionFence)
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

- [x] 19. Security and logging
  - [x] 19.1 Implement credential redaction and security measures
    - Add log filter to redact tokens and passwords from all log output
    - Ensure all API requests use HTTPS with TLS 1.2+
    - Validate SSL certificates, reject self-signed
    - Implement cleanup on integration removal (delete stored credentials and cached data)
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5_

  - [x] 19.2 Write property test for credential redaction
    - **Property 11: Credential Redaction in Logs**
    - Test that no log message at any level contains literal token or password values
    - **Validates: Requirements 21.3**

- [x] 20. Checkpoint - Ensure all features work end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 21. Documentation
  - [x] 21.1 Create README.md
    - Write installation instructions (HACS and manual)
    - Document feature list with all supported entities
    - Write configuration guide (setup flow, region selection)
    - Document supported devices (i105, i108)
    - Include troubleshooting section (common errors, re-authentication)
    - _Requirements: 16.6_

- [x] 22. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The integration uses Python with `aiohttp` for async HTTP, `hypothesis` for property-based testing
- All entity platforms follow Home Assistant's `CoordinatorEntity` pattern for consistent state management
