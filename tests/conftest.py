"""Shared test fixtures for the Navimow integration tests."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Mock homeassistant modules (must be done before any custom_components import)
# ---------------------------------------------------------------------------

_ha_mock = ModuleType("homeassistant")
_ha_mock.config_entries = ModuleType("homeassistant.config_entries")
_ha_mock.config_entries.ConfigEntry = MagicMock
_ha_mock.core = ModuleType("homeassistant.core")
_ha_mock.core.HomeAssistant = MagicMock

_ha_helpers = ModuleType("homeassistant.helpers")

_ha_helpers_aiohttp = ModuleType("homeassistant.helpers.aiohttp_client")
_ha_helpers_aiohttp.async_get_clientsession = MagicMock()

_ha_helpers_network = ModuleType("homeassistant.helpers.network")
_ha_helpers_network.get_url = MagicMock(return_value="http://homeassistant.local:8123")

_ha_helpers_device_registry = ModuleType("homeassistant.helpers.device_registry")
_ha_helpers_device_registry.DeviceInfo = dict

_ha_helpers_entity = ModuleType("homeassistant.helpers.entity")
_ha_helpers_entity.EntityDescription = MagicMock

_ha_helpers_entity_platform = ModuleType("homeassistant.helpers.entity_platform")
_ha_helpers_entity_platform.AddEntitiesCallback = MagicMock

_ha_update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")


class _MockDataUpdateCoordinator:
    """Mock DataUpdateCoordinator base class."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, *, name, update_interval, config_entry=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.config_entry = config_entry


class _MockCoordinatorEntity:
    """Mock CoordinatorEntity base class."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def unique_id(self):
        """Return unique_id from _attr_unique_id."""
        return getattr(self, "_attr_unique_id", None)


class _MockUpdateFailed(Exception):
    """Mock UpdateFailed exception."""


_ha_update_coordinator.DataUpdateCoordinator = _MockDataUpdateCoordinator
_ha_update_coordinator.UpdateFailed = _MockUpdateFailed
_ha_update_coordinator.CoordinatorEntity = _MockCoordinatorEntity

sys.modules.setdefault("homeassistant", _ha_mock)
sys.modules.setdefault("homeassistant.config_entries", _ha_mock.config_entries)
sys.modules.setdefault("homeassistant.core", _ha_mock.core)
sys.modules.setdefault("homeassistant.helpers", _ha_helpers)
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", _ha_helpers_aiohttp)
sys.modules.setdefault("homeassistant.helpers.network", _ha_helpers_network)
sys.modules.setdefault("homeassistant.helpers.device_registry", _ha_helpers_device_registry)
sys.modules.setdefault("homeassistant.helpers.entity", _ha_helpers_entity)
sys.modules.setdefault("homeassistant.helpers.entity_platform", _ha_helpers_entity_platform)
sys.modules.setdefault("homeassistant.helpers.update_coordinator", _ha_update_coordinator)


# ---------------------------------------------------------------------------
# Mock aiohttp ClientSession
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Return a mock aiohttp ClientSession."""
    session = AsyncMock()
    session.closed = False

    # Default response mock
    response = AsyncMock()
    response.status = 200
    response.headers = {"Content-Type": "application/json"}
    response.json = AsyncMock(return_value={"code": 0, "data": {}})
    response.raise_for_status = MagicMock()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)

    session.get = MagicMock(return_value=response)
    session.post = MagicMock(return_value=response)
    session.request = MagicMock(return_value=response)

    return session


# ---------------------------------------------------------------------------
# Mock API response data
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_device_list_response() -> dict:
    """Return a mock response for the device list endpoint."""
    return {
        "code": 0,
        "data": [
            {
                "device_sn": "NVM1234567890",
                "name": "Front Yard Mower",
                "model": "Navimow i105",
                "online": True,
            },
            {
                "device_sn": "NVM0987654321",
                "name": "Back Yard Mower",
                "model": "Navimow i108",
                "online": False,
            },
        ],
    }


@pytest.fixture
def mock_device_info_response() -> dict:
    """Return a mock response for the device info endpoint."""
    return {
        "code": 0,
        "data": {
            "device_sn": "NVM1234567890",
            "model": "Navimow i105",
            "name": "Front Yard Mower",
            "firmware_versions": {
                "ecu": "1.2.3",
                "bms": "2.0.1",
                "gps": "3.1.0",
                "bluetooth": "1.0.5",
                "wifi": "2.1.0",
                "blade_motor": "1.1.0",
                "charging_station": "1.0.2",
                "iot": "2.2.0",
                "audio": "1.0.0",
                "bump_sensor": "1.0.1",
                "vision_fence": None,
            },
        },
    }


@pytest.fixture
def mock_telemetry_response() -> dict:
    """Return a mock response for the device telemetry endpoint."""
    return {
        "code": 0,
        "data": {
            "battery_level": 78,
            "battery_voltage": 25.6,
            "battery_temperature_fault": False,
            "state": "mowing",
            "work_mode": "standard",
            "task_state": "scheduled_mowing",
            "mowing_progress": 45,
            "current_mowing_area": 120.5,
            "total_mowing_area": 5400.0,
            "blade_usage_time": 85.3,
            "blade_lifetime_hours": 200.0,
            "total_mowing_time": 320.5,
            "network_type": "4G",
            "cellular_signal": 22,
            "mqtt_connected": True,
            "wifi_ssid": None,
        },
    }


@pytest.fixture
def mock_schedule_response() -> dict:
    """Return a mock response for the today plan endpoint."""
    now = datetime.now(tz=timezone.utc)
    return {
        "code": 0,
        "data": {
            "schedule_enabled": True,
            "next_start": (now + timedelta(hours=2)).isoformat(),
            "next_end": (now + timedelta(hours=4)).isoformat(),
            "schedules": [
                {
                    "start_time": (now + timedelta(hours=2)).isoformat(),
                    "end_time": (now + timedelta(hours=4)).isoformat(),
                    "zones": ["zone_1", "zone_2"],
                    "active": True,
                },
            ],
        },
    }


@pytest.fixture
def mock_settings_response() -> dict:
    """Return a mock response for the settings status endpoint."""
    return {
        "code": 0,
        "data": {
            "cutting_height": 40,
            "work_mode": "standard",
            "rain_sensor": True,
            "edge_mowing": True,
            "mowing_cycle": False,
            "anti_theft": True,
            "dark_mode": False,
            "anti_interference": None,
            "plan_switch": True,
        },
    }


@pytest.fixture
def mock_location_response() -> dict:
    """Return a mock response for the location endpoint."""
    return {
        "code": 0,
        "data": {
            "latitude": 51.5074,
            "longitude": -0.1278,
            "altitude": 11.0,
            "speed": 0.3,
            "hdop": 1.2,
            "satellites_in_use": 12,
            "satellites_in_view": 18,
            "data_valid": True,
        },
    }


@pytest.fixture
def mock_errors_response() -> dict:
    """Return a mock response for the errors endpoint."""
    return {
        "code": 0,
        "data": [
            {
                "code": 15,
                "title": "Mower lifted",
                "content": "The mower has been lifted during operation.",
                "severity": 2,
                "timestamp": "2024-06-15T10:30:00Z",
            },
        ],
    }


@pytest.fixture
def mock_trail_list_response() -> dict:
    """Return a mock response for the trail list endpoint."""
    return {
        "code": 0,
        "data": [
            {
                "trail_id": "trail_001",
                "date": "2024-06-15T08:00:00Z",
                "duration": 95.0,
                "area": 350.0,
            },
            {
                "trail_id": "trail_002",
                "date": "2024-06-14T09:00:00Z",
                "duration": 110.0,
                "area": 420.0,
            },
        ],
    }


@pytest.fixture
def mock_firmware_response() -> dict:
    """Return a mock response for the firmware info endpoint."""
    return {
        "code": 0,
        "data": {
            "update_available": True,
            "new_version": "1.3.0",
            "release_notes": "Bug fixes and performance improvements.",
            "current_versions": {
                "ecu": "1.2.3",
                "bms": "2.0.1",
                "gps": "3.1.0",
                "bluetooth": "1.0.5",
                "wifi": "2.1.0",
                "blade_motor": "1.1.0",
                "charging_station": "1.0.2",
                "iot": "2.2.0",
                "audio": "1.0.0",
                "bump_sensor": "1.0.1",
                "vision_fence": None,
            },
        },
    }


@pytest.fixture
def mock_bms_detail_response() -> dict:
    """Return a mock response for the BMS detail endpoint."""
    return {
        "code": 0,
        "data": {
            "voltage": 25.6,
            "current": 1.2,
            "temperature": 28.5,
            "cycles": 142,
            "health": 95,
        },
    }


@pytest.fixture
def mock_map_data_response() -> dict:
    """Return a mock response for map data."""
    return {
        "code": 0,
        "data": {
            "boundaries": [
                [(51.507, -0.128), (51.508, -0.128), (51.508, -0.127), (51.507, -0.127)]
            ],
            "islands": [],
            "channels": [],
            "zones": [
                {
                    "zone_id": "zone_1",
                    "name": "Front Lawn",
                    "area": 200.0,
                    "active": True,
                },
                {
                    "zone_id": "zone_2",
                    "name": "Side Garden",
                    "area": 80.0,
                    "active": True,
                },
            ],
            "map_status": "valid",
            "total_area": 280.0,
        },
    }


# ---------------------------------------------------------------------------
# Mock NavimowAuth
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_auth() -> AsyncMock:
    """Return a mock NavimowAuth instance."""
    auth = AsyncMock()
    auth.region = "fra"
    auth.access_token = "mock_access_token_abc123"
    auth.refresh_token = "mock_refresh_token_xyz789"
    auth.token_expiry = datetime.now(tz=timezone.utc) + timedelta(hours=1)

    auth.async_get_access_token = AsyncMock(return_value="mock_access_token_abc123")
    auth.async_refresh_token = AsyncMock(
        return_value=(
            "new_access_token_def456",
            "new_refresh_token_uvw321",
            datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )
    )
    auth.get_auth_headers = MagicMock(
        return_value={
            "Authorization": "Bearer mock_access_token_abc123",
            "requestId": "mock-request-id-uuid",
        }
    )
    auth.sign_request = MagicMock(
        return_value={
            "Authorization": "Bearer mock_access_token_abc123",
            "requestId": "mock-request-id-uuid",
        }
    )

    # Passport URL property
    auth.passport_url = "https://api-passport-fra.ninebot.com/"

    return auth


# ---------------------------------------------------------------------------
# Mock NavimowApiClient
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api_client(mock_auth) -> AsyncMock:
    """Return a mock NavimowApiClient instance."""
    client = AsyncMock()
    client.auth = mock_auth
    client.region = "fra"
    client.base_url = "https://navimow-fra.ninebot.com/"

    # Default return values for API methods
    client.get_devices = AsyncMock(return_value=[])
    client.get_device_info = AsyncMock(return_value=None)
    client.get_device_data = AsyncMock(return_value=None)
    client.get_today_plan = AsyncMock(return_value=None)
    client.get_settings_status = AsyncMock(return_value=None)
    client.get_location = AsyncMock(return_value=None)
    client.get_trail_list = AsyncMock(return_value=[])
    client.get_trail_detail = AsyncMock(return_value=None)
    client.get_errors = AsyncMock(return_value=[])
    client.get_firmware_info = AsyncMock(return_value=None)
    client.get_bms_detail = AsyncMock(return_value=None)

    # Command methods
    client.send_command = AsyncMock(return_value=True)
    client.set_setting = AsyncMock(return_value=True)
    client.set_power = AsyncMock(return_value=True)

    return client


# ---------------------------------------------------------------------------
# Mock NavimowCoordinator
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_coordinator(mock_api_client) -> MagicMock:
    """Return a mock NavimowCoordinator instance."""
    coordinator = MagicMock()
    coordinator.api_client = mock_api_client
    coordinator.device_sn = "NVM1234567890"
    coordinator.last_update_success = True
    coordinator.update_interval = timedelta(seconds=30)

    # Mock device data (NavimowDeviceData-like structure)
    coordinator.data = MagicMock()
    coordinator.data.device_info = MagicMock(
        device_sn="NVM1234567890",
        model="Navimow i105",
        name="Front Yard Mower",
        manufacturer="Segway",
    )
    coordinator.data.telemetry = MagicMock(
        battery_level=78,
        battery_voltage=25.6,
        battery_temperature_fault=False,
        state="mowing",
        work_mode="standard",
        task_state="scheduled_mowing",
        mowing_progress=45,
        current_mowing_area=120.5,
        total_mowing_area=5400.0,
        blade_usage_time=85.3,
        blade_lifetime_hours=200.0,
        total_mowing_time=320.5,
        network_type="4G",
        cellular_signal=22,
        mqtt_connected=True,
        wifi_ssid=None,
    )
    coordinator.data.location = MagicMock(
        latitude=51.5074,
        longitude=-0.1278,
        altitude=11.0,
        speed=0.3,
        hdop=1.2,
        satellites_in_use=12,
        satellites_in_view=18,
        data_valid=True,
    )
    coordinator.data.schedule = MagicMock(
        schedule_enabled=True,
        next_start=datetime.now(tz=timezone.utc) + timedelta(hours=2),
        next_end=datetime.now(tz=timezone.utc) + timedelta(hours=4),
        schedules=[],
    )
    coordinator.data.settings = MagicMock(
        cutting_height=40,
        work_mode="standard",
        rain_sensor=True,
        edge_mowing=True,
        mowing_cycle=False,
        anti_theft=True,
        dark_mode=False,
        anti_interference=None,
        plan_switch=True,
    )
    coordinator.data.errors = []
    coordinator.data.trail_history = []
    coordinator.data.map_data = None
    coordinator.data.firmware = MagicMock(
        update_available=False,
        new_version=None,
        release_notes=None,
    )
    coordinator.data.bms = MagicMock(
        voltage=25.6,
        current=1.2,
        temperature=28.5,
        cycles=142,
        health=95,
    )
    coordinator.data.maintenance = MagicMock(
        blade_usage_hours=85.3,
        blade_lifetime_hours=200.0,
        blade_remaining_life_pct=57.35,
        blade_replacement_needed=False,
        maintenance_status="ok",
        maintenance_hints=[],
    )

    # Coordinator methods
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_set_updated_data = MagicMock()

    return coordinator
