# Segway Navimow Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Home Assistant custom integration for the Segway Navimow i105/i108 robotic lawn mower. Communicates with the Segway/Ninebot cloud platform to expose device status, sensors, controls, settings, schedules, and error notifications as Home Assistant entities.

## Features

### Lawn Mower

- Start, pause, and dock commands via the `lawn_mower` platform

### Sensors

- **Battery**: Battery level (%), battery voltage
- **Status**: Mower state, mowing progress, current task, work mode
- **GPS**: Satellites in use, satellites in view, HDOP, speed, altitude
- **Connectivity**: Network type, cellular signal strength, Wi-Fi SSID
- **Area & Statistics**: Total mowing area, current session area, total mowing time, map area
- **Schedule**: Next schedule start/end times, schedule end time
- **Trail History**: Last mowing date, duration, and area (with 7-day history as attributes)
- **Maintenance**: Blade usage time, blade remaining life (%), maintenance status
- **Diagnostics**: Device model, firmware version
- **Errors**: Error code, error message
- **Zones**: Active zones, map status

### Binary Sensors

- Charging state
- Battery temperature fault
- MQTT connection status
- Active error indicator
- Blade replacement needed

### Switches

- Schedule enabled/disabled
- Rain sensor
- Edge mowing
- Mowing cycle (continuous)
- Anti-theft alarm
- Dark mode (LED dimming)
- Anti-interference mode (4G, where supported)

### Select

- Work mode (Standard, Fast, Silent)
- Mowing zone selection (when multiple zones defined)

### Number

- Cutting height (20–60mm, model-dependent)

### Button

- Cancel today's schedule
- Reset blade counter

### Device Tracker

- GPS location with latitude/longitude
- State set to `unknown` when GPS data is invalid

### Update

- Firmware update availability and version info
- Diagnostic attributes for all firmware components (ECU, BMS, GPS, Bluetooth, Wi-Fi, blade motor, charging station, IoT, audio, bump sensor, VisionFence)

## Supported Devices

| Device | Model |
|--------|-------|
| Segway Navimow i105 | i105 |
| Segway Navimow i108 | i108 |

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three-dot menu in the top right and select **Custom repositories**
3. Add the repository URL: `https://github.com/navimow-ha/navimow-home-assistant`
4. Select category: **Integration**
5. Click **Add**
6. Search for "Segway Navimow" in HACS and install it
7. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [GitHub releases page](https://github.com/navimow-ha/navimow-home-assistant/releases)
2. Copy the `custom_components/navimow/` directory to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

This integration is configured entirely through the Home Assistant UI. No YAML configuration is needed.

### Setup Flow

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "Segway Navimow"
3. Enter your Segway/Ninebot account credentials:
   - **Email or phone number**
   - **Password**
   - **Server region** (select the region matching your account)
4. The integration will authenticate and discover your mowers
5. Select which devices to add
6. Done — entities will appear under the new device

### Region Selection

Choose the server region that matches where your Segway account was created:

| Region Code | Region | Endpoint |
|-------------|--------|----------|
| `fra` | Europe | `navimow-fra.ninebot.com` |
| `ore` | North America | `navimow-ore.ninebot.com` |
| `sg` | Asia-Pacific | `navimow-sg.ninebot.com` |
| `bj` | China | `navimow-bj.ninebot.com` |
| `mos` | Russia | `navimow-mos.ninebot.com` |

## Troubleshooting

### Invalid Credentials

- Verify your email/phone and password are correct
- Ensure you are selecting the correct server region for your account
- Try logging in to the Segway Navimow mobile app to confirm your credentials work

### No Devices Found

- Ensure your mower is bound to your Segway account in the Navimow mobile app
- Check that the mower has been set up and is online at least once
- Verify you selected the correct server region

### Re-authentication Required

If your session expires (e.g., after extended inactivity), the integration will show a re-authentication notification:

1. Go to **Settings → Devices & Services**
2. Find the Navimow integration and click **Reconfigure** or the re-authentication prompt
3. Re-enter your credentials
4. The integration will resume normal operation

### Network Errors

- The integration retries failed requests with exponential backoff (30s initial, up to 5 minutes)
- After 3 consecutive failures, the device is marked unavailable
- Once connectivity is restored, the device will automatically recover on the next successful poll

### Device Shows Unavailable

- Check your internet connection
- Verify the Navimow cloud service is reachable
- Check Home Assistant logs for specific error messages: **Settings → System → Logs**, filter for `navimow`

## Development

### Prerequisites

- Python 3.11+
- Home Assistant development environment (optional, for integration testing)

### Running Tests

```bash
# Install test dependencies
pip install -r requirements_test.txt

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_api_client.py

# Run property-based tests only
pytest -k "hypothesis"
```

### Project Structure

```
custom_components/navimow/
├── __init__.py           # Integration setup, platform forwarding
├── config_flow.py        # UI-based setup wizard
├── const.py              # Constants, domains, defaults
├── coordinator.py        # Adaptive polling coordinator
├── entity.py             # Base entity class
├── models.py             # Data classes and enums
├── api_client.py         # HTTP API client
├── auth.py               # OAuth token management
├── encryption.py         # Request signing (NbEncryption)
├── errors.py             # Error codes and custom exceptions
├── security.py           # Log redaction and security utilities
├── sensor.py             # Sensor platform
├── binary_sensor.py      # Binary sensor platform
├── switch.py             # Switch platform
├── select.py             # Select platform
├── number.py             # Number platform
├── button.py             # Button platform
├── lawn_mower.py         # Lawn mower platform
├── device_tracker.py     # Device tracker platform
├── update.py             # Firmware update platform
├── manifest.json         # HA integration manifest
├── strings.json          # Default strings
└── translations/
    └── en.json           # English translations
tests/
├── conftest.py           # Shared fixtures
├── test_api_client.py    # API client tests
├── test_auth.py          # Authentication tests
├── test_config_flow.py   # Config flow tests
├── test_coordinator.py   # Coordinator tests
├── test_device_tracker.py# Device tracker tests
├── test_encryption.py    # Encryption tests
├── test_entity.py        # Entity base tests
├── test_errors.py        # Error handling tests
├── test_init.py          # Integration setup tests
├── test_maintenance.py   # Maintenance tests
├── test_models.py        # Data model tests
└── test_security.py      # Security tests
```

## License

This project is licensed under the MIT License.
