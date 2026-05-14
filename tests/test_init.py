"""Tests for the Navimow integration setup (__init__.py)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock homeassistant modules before importing the integration
_ha_mock = ModuleType("homeassistant")
_ha_mock.config_entries = ModuleType("homeassistant.config_entries")
_ha_mock.config_entries.ConfigEntry = MagicMock
_ha_mock.core = ModuleType("homeassistant.core")
_ha_mock.core.HomeAssistant = MagicMock

_ha_helpers = ModuleType("homeassistant.helpers")
_ha_helpers_aiohttp = ModuleType("homeassistant.helpers.aiohttp_client")
_ha_helpers_aiohttp.async_get_clientsession = MagicMock()

_ha_helpers_device_registry = ModuleType("homeassistant.helpers.device_registry")
_ha_helpers_device_registry.DeviceInfo = dict

_ha_helpers_entity = ModuleType("homeassistant.helpers.entity")
_ha_helpers_entity.EntityDescription = MagicMock

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


_ha_update_coordinator.DataUpdateCoordinator = _MockDataUpdateCoordinator
_ha_update_coordinator.UpdateFailed = Exception
_ha_update_coordinator.CoordinatorEntity = _MockCoordinatorEntity

sys.modules.setdefault("homeassistant", _ha_mock)
sys.modules.setdefault("homeassistant.config_entries", _ha_mock.config_entries)
sys.modules.setdefault("homeassistant.core", _ha_mock.core)
sys.modules.setdefault("homeassistant.helpers", _ha_helpers)
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", _ha_helpers_aiohttp)
sys.modules.setdefault("homeassistant.helpers.device_registry", _ha_helpers_device_registry)
sys.modules.setdefault("homeassistant.helpers.entity", _ha_helpers_entity)
sys.modules.setdefault("homeassistant.helpers.update_coordinator", _ha_update_coordinator)

from custom_components.navimow import async_setup_entry, async_unload_entry
from custom_components.navimow.const import DOMAIN, PLATFORMS


@pytest.fixture
def mock_hass() -> MagicMock:
    """Return a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_update_entry = MagicMock()
    return hass


@pytest.fixture
def mock_entry() -> MagicMock:
    """Return a mock config entry with valid data."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id_123"
    entry.data = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "token_expiry": (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat(),
        "region": "fra",
        "username": "test@example.com",
        "devices": ["NVM1234567890", "NVM0987654321"],
    }
    return entry


@pytest.fixture
def mock_entry_single_device() -> MagicMock:
    """Return a mock config entry with a single device."""
    entry = MagicMock()
    entry.entry_id = "test_entry_single"
    entry.data = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "token_expiry": (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat(),
        "region": "ore",
        "username": "user@example.com",
        "devices": ["NVM_SINGLE"],
    }
    return entry


class TestAsyncSetupEntry:
    """Tests for async_setup_entry."""

    @pytest.mark.asyncio
    async def test_setup_creates_coordinators_per_device(
        self, mock_hass, mock_entry
    ):
        """Test that a coordinator is created for each device in the entry."""
        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ) as mock_auth_cls,
            patch(
                "custom_components.navimow.NavimowApiClient"
            ) as mock_api_cls,
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_get_session.return_value = AsyncMock()
            mock_auth_cls.return_value = MagicMock()
            mock_api_cls.return_value = MagicMock()

            mock_coordinator = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coordinator

            result = await async_setup_entry(mock_hass, mock_entry)

            assert result is True
            # Two devices → two coordinator instances
            assert mock_coord_cls.call_count == 2

    @pytest.mark.asyncio
    async def test_setup_stores_data_in_hass(self, mock_hass, mock_entry):
        """Test that coordinators and clients are stored in hass.data."""
        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ) as mock_auth_cls,
            patch(
                "custom_components.navimow.NavimowApiClient"
            ) as mock_api_cls,
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_get_session.return_value = AsyncMock()
            mock_auth_instance = MagicMock()
            mock_auth_cls.return_value = mock_auth_instance
            mock_api_instance = MagicMock()
            mock_api_cls.return_value = mock_api_instance

            mock_coordinator = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_entry)

            stored = mock_hass.data[DOMAIN][mock_entry.entry_id]
            assert "coordinators" in stored
            assert "api_client" in stored
            assert "auth" in stored
            assert stored["api_client"] is mock_api_instance
            assert stored["auth"] is mock_auth_instance

    @pytest.mark.asyncio
    async def test_setup_forwards_platforms(self, mock_hass, mock_entry):
        """Test that all platforms are forwarded during setup."""
        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ),
            patch(
                "custom_components.navimow.NavimowApiClient"
            ),
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_get_session.return_value = AsyncMock()
            mock_coordinator = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_entry)

            mock_hass.config_entries.async_forward_entry_setups.assert_called_once_with(
                mock_entry, PLATFORMS
            )

    @pytest.mark.asyncio
    async def test_setup_calls_first_refresh(
        self, mock_hass, mock_entry_single_device
    ):
        """Test that async_config_entry_first_refresh is called for each coordinator."""
        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ),
            patch(
                "custom_components.navimow.NavimowApiClient"
            ),
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_get_session.return_value = AsyncMock()
            mock_coordinator = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_entry_single_device)

            mock_coordinator.async_config_entry_first_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_creates_auth_with_correct_params(
        self, mock_hass, mock_entry
    ):
        """Test that NavimowAuth is created with correct parameters from entry data."""
        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ) as mock_auth_cls,
            patch(
                "custom_components.navimow.NavimowApiClient"
            ),
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_session = AsyncMock()
            mock_get_session.return_value = mock_session
            mock_auth_cls.return_value = MagicMock()

            mock_coordinator = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_entry)

            mock_auth_cls.assert_called_once()
            call_kwargs = mock_auth_cls.call_args[1]
            assert call_kwargs["session"] is mock_session
            assert call_kwargs["region"] == "fra"
            assert call_kwargs["access_token"] == "test_access_token"
            assert call_kwargs["refresh_token"] == "test_refresh_token"

    @pytest.mark.asyncio
    async def test_setup_creates_api_client_with_correct_params(
        self, mock_hass, mock_entry
    ):
        """Test that NavimowApiClient is created with session, auth, and region."""
        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ) as mock_auth_cls,
            patch(
                "custom_components.navimow.NavimowApiClient"
            ) as mock_api_cls,
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_session = AsyncMock()
            mock_get_session.return_value = mock_session
            mock_auth_instance = MagicMock()
            mock_auth_cls.return_value = mock_auth_instance
            mock_api_cls.return_value = MagicMock()

            mock_coordinator = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_entry)

            mock_api_cls.assert_called_once_with(
                session=mock_session,
                auth=mock_auth_instance,
                region="fra",
            )

    @pytest.mark.asyncio
    async def test_setup_handles_empty_devices_list(self, mock_hass):
        """Test setup with no devices in the entry."""
        entry = MagicMock()
        entry.entry_id = "test_no_devices"
        entry.data = {
            "access_token": "token",
            "refresh_token": "refresh",
            "token_expiry": datetime.now(tz=timezone.utc).isoformat(),
            "region": "fra",
            "username": "user@test.com",
            "devices": [],
        }

        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ),
            patch(
                "custom_components.navimow.NavimowApiClient"
            ),
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_get_session.return_value = AsyncMock()

            result = await async_setup_entry(mock_hass, entry)

            assert result is True
            # No coordinators should be created
            mock_coord_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_handles_invalid_token_expiry(self, mock_hass):
        """Test setup gracefully handles invalid token_expiry format."""
        entry = MagicMock()
        entry.entry_id = "test_bad_expiry"
        entry.data = {
            "access_token": "token",
            "refresh_token": "refresh",
            "token_expiry": "not-a-valid-date",
            "region": "sg",
            "username": "user@test.com",
            "devices": ["NVM_TEST"],
        }

        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ) as mock_auth_cls,
            patch(
                "custom_components.navimow.NavimowApiClient"
            ),
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_get_session.return_value = AsyncMock()
            mock_auth_cls.return_value = MagicMock()

            mock_coordinator = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coordinator

            # Should not raise, falls back to current time
            result = await async_setup_entry(mock_hass, entry)
            assert result is True


class TestAsyncUnloadEntry:
    """Tests for async_unload_entry."""

    @pytest.mark.asyncio
    async def test_unload_removes_data(self, mock_hass, mock_entry):
        """Test that unloading removes the entry data from hass.data."""
        mock_hass.data[DOMAIN] = {
            mock_entry.entry_id: {
                "coordinators": {},
                "api_client": MagicMock(),
                "auth": MagicMock(),
            }
        }

        result = await async_unload_entry(mock_hass, mock_entry)

        assert result is True
        assert mock_entry.entry_id not in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_unload_calls_unload_platforms(self, mock_hass, mock_entry):
        """Test that unloading calls async_unload_platforms with all platforms."""
        mock_hass.data[DOMAIN] = {mock_entry.entry_id: {"coordinators": {}}}

        await async_unload_entry(mock_hass, mock_entry)

        mock_hass.config_entries.async_unload_platforms.assert_called_once_with(
            mock_entry, PLATFORMS
        )

    @pytest.mark.asyncio
    async def test_unload_keeps_data_on_failure(self, mock_hass, mock_entry):
        """Test that data is kept if platform unload fails."""
        mock_hass.data[DOMAIN] = {
            mock_entry.entry_id: {"coordinators": {}, "api_client": MagicMock()}
        }
        mock_hass.config_entries.async_unload_platforms = AsyncMock(
            return_value=False
        )

        result = await async_unload_entry(mock_hass, mock_entry)

        assert result is False
        assert mock_entry.entry_id in mock_hass.data[DOMAIN]


class TestTokenRefreshCallback:
    """Tests for the on_token_refresh callback."""

    @pytest.mark.asyncio
    async def test_token_refresh_updates_config_entry(self, mock_hass, mock_entry):
        """Test that token refresh callback updates the config entry data."""
        captured_callback = None

        with (
            patch(
                "custom_components.navimow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.NavimowAuth"
            ) as mock_auth_cls,
            patch(
                "custom_components.navimow.NavimowApiClient"
            ),
            patch(
                "custom_components.navimow.NavimowCoordinator"
            ) as mock_coord_cls,
        ):
            mock_get_session.return_value = AsyncMock()

            def capture_auth_init(**kwargs):
                nonlocal captured_callback
                captured_callback = kwargs.get("on_token_refresh")
                return MagicMock()

            mock_auth_cls.side_effect = capture_auth_init

            mock_coordinator = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_cls.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_entry)

        # Now invoke the captured callback
        assert captured_callback is not None
        new_expiry = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        await captured_callback("new_token", "new_refresh", new_expiry)

        mock_hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = mock_hass.config_entries.async_update_entry.call_args[1]
        assert call_kwargs["data"]["access_token"] == "new_token"
        assert call_kwargs["data"]["refresh_token"] == "new_refresh"
        assert call_kwargs["data"]["token_expiry"] == new_expiry.isoformat()
