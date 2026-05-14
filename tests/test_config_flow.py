"""Tests for the Navimow config flow (OAuth2 external browser auth)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

# ---------------------------------------------------------------------------
# Mock homeassistant modules before importing config_flow
# ---------------------------------------------------------------------------


class _MockConfigFlow:
    """Mock ConfigFlow base class."""

    def __init_subclass__(cls, *, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    def __init__(self):
        self.hass = None
        self.context = {}
        self.flow_id = "test_flow_id_123"

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    def async_external_step(self, **kwargs):
        return {"type": "external", **kwargs}

    def async_external_step_done(self, **kwargs):
        return {"type": "external_done", **kwargs}

    async def async_set_unique_id(self, unique_id):
        pass

    def _abort_if_unique_id_configured(self):
        pass


class _MockConfigFlowResult(dict):
    """Mock ConfigFlowResult."""
    pass


# Ensure homeassistant modules exist in sys.modules
if "homeassistant" not in sys.modules:
    _ha_mock = ModuleType("homeassistant")
    sys.modules["homeassistant"] = _ha_mock

if "homeassistant.config_entries" not in sys.modules:
    _ha_config_entries = ModuleType("homeassistant.config_entries")
    sys.modules["homeassistant.config_entries"] = _ha_config_entries

if "homeassistant.core" not in sys.modules:
    _ha_core = ModuleType("homeassistant.core")
    sys.modules["homeassistant.core"] = _ha_core

if "homeassistant.helpers" not in sys.modules:
    sys.modules["homeassistant.helpers"] = ModuleType("homeassistant.helpers")

if "homeassistant.helpers.aiohttp_client" not in sys.modules:
    sys.modules["homeassistant.helpers.aiohttp_client"] = ModuleType(
        "homeassistant.helpers.aiohttp_client"
    )

if "homeassistant.helpers.network" not in sys.modules:
    _ha_network = ModuleType("homeassistant.helpers.network")
    _ha_network.get_url = MagicMock(return_value="http://homeassistant.local:8123")
    sys.modules["homeassistant.helpers.network"] = _ha_network

# Now add the attributes we need to the existing modules
_ha_config_entries_mod = sys.modules["homeassistant.config_entries"]
_ha_config_entries_mod.ConfigEntry = MagicMock
_ha_config_entries_mod.ConfigFlow = _MockConfigFlow
_ha_config_entries_mod.ConfigFlowResult = _MockConfigFlowResult

_ha_core_mod = sys.modules["homeassistant.core"]
_ha_core_mod.HomeAssistant = MagicMock

_ha_aiohttp_mod = sys.modules["homeassistant.helpers.aiohttp_client"]
_ha_aiohttp_mod.async_get_clientsession = MagicMock()

# Now we can import the config flow
from custom_components.navimow.config_flow import (
    REGION_LABELS,
    NavimowConfigFlow,
)
from custom_components.navimow.const import DOMAIN, OAUTH_LOGIN_URLS, API_BASE_URLS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_hass():
    """Return a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.config = MagicMock()
    hass.config.external_url = "http://homeassistant.local:8123"
    return hass


@pytest.fixture
def mock_flow(mock_hass):
    """Return a NavimowConfigFlow instance with mocked hass."""
    flow = NavimowConfigFlow()
    flow.hass = mock_hass
    flow.context = {"entry_id": "test_entry_id"}
    flow.flow_id = "test_flow_id_123"
    return flow


# ---------------------------------------------------------------------------
# Tests: async_step_user (region selection)
# ---------------------------------------------------------------------------


class TestAsyncStepUser:
    """Tests for the user step (region selection) of the config flow."""

    @pytest.mark.asyncio
    async def test_show_form_when_no_input(self, mock_flow):
        """Test that the region selection form is shown when no input."""
        result = await mock_flow.async_step_user(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_region_selection_proceeds_to_auth(self, mock_flow):
        """Test that selecting a region proceeds to the external auth step."""
        result = await mock_flow.async_step_user(user_input={"region": "fra"})

        # Should proceed to external auth step
        assert result["type"] == "external"
        assert result["step_id"] == "auth"
        assert "url" in result
        assert mock_flow._region == "fra"

    @pytest.mark.asyncio
    async def test_region_selection_ore(self, mock_flow):
        """Test that selecting Oregon region works."""
        result = await mock_flow.async_step_user(user_input={"region": "ore"})

        assert result["type"] == "external"
        assert mock_flow._region == "ore"
        # URL should contain the ore login URL
        assert "ore" in result["url"]


# ---------------------------------------------------------------------------
# Tests: async_step_auth (external browser login)
# ---------------------------------------------------------------------------


class TestAsyncStepAuth:
    """Tests for the external auth step."""

    @pytest.mark.asyncio
    async def test_auth_step_opens_external_url(self, mock_flow):
        """Test that the auth step opens the external login URL."""
        mock_flow._region = "fra"
        result = await mock_flow.async_step_auth(user_input=None)

        assert result["type"] == "external"
        assert result["step_id"] == "auth"
        assert "navimow-h5-fra-willand.com" in result["url"]
        assert "redirect_uri" in result["url"]
        assert "flow_id" in result["url"]

    @pytest.mark.asyncio
    async def test_auth_step_url_contains_redirect(self, mock_flow):
        """Test that the login URL includes the HA redirect URI."""
        mock_flow._region = "fra"
        result = await mock_flow.async_step_auth(user_input=None)

        url = result["url"]
        assert "homeassistant.local" in url
        assert "redirect_uri=" in url


# ---------------------------------------------------------------------------
# Tests: async_step_auth_complete (token callback)
# ---------------------------------------------------------------------------


class TestAsyncStepAuthComplete:
    """Tests for the auth completion step."""

    @pytest.mark.asyncio
    async def test_successful_auth_with_devices(self, mock_flow):
        """Test successful auth callback proceeds to device selection."""
        mock_flow._region = "fra"

        with patch.object(
            mock_flow,
            "_fetch_devices",
            new_callable=AsyncMock,
            return_value=[
                {
                    "device_sn": "NVM1234567890",
                    "name": "Front Yard Mower",
                    "model": "Navimow i105",
                    "online": True,
                }
            ],
        ), patch(
            "custom_components.navimow.config_flow.async_get_clientsession"
        ) as mock_get_session:
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_auth_complete(
                user_input={
                    "access_token": "test_access_token_123",
                    "refresh_token": "test_refresh_token_456",
                    "expires_in": 7200,
                }
            )

        assert result["type"] == "external_done"
        assert result["next_step_id"] == "devices"
        assert mock_flow._access_token == "test_access_token_123"
        assert mock_flow._refresh_token == "test_refresh_token_456"

    @pytest.mark.asyncio
    async def test_auth_with_empty_token_aborts(self, mock_flow):
        """Test that empty access token aborts the flow."""
        mock_flow._region = "fra"

        result = await mock_flow.async_step_auth_complete(
            user_input={
                "access_token": "",
                "refresh_token": "",
                "expires_in": 3600,
            }
        )

        assert result["type"] == "abort"
        assert result["reason"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_auth_with_no_devices_aborts(self, mock_flow):
        """Test that no devices found aborts the flow."""
        mock_flow._region = "fra"

        with patch.object(
            mock_flow,
            "_fetch_devices",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "custom_components.navimow.config_flow.async_get_clientsession"
        ) as mock_get_session:
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_auth_complete(
                user_input={
                    "access_token": "valid_token",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                }
            )

        assert result["type"] == "abort"
        assert result["reason"] == "no_devices"

    @pytest.mark.asyncio
    async def test_auth_with_network_error_aborts(self, mock_flow):
        """Test that network error during device fetch aborts."""
        mock_flow._region = "fra"

        with patch.object(
            mock_flow,
            "_fetch_devices",
            new_callable=AsyncMock,
            side_effect=aiohttp.ClientError("Connection failed"),
        ), patch(
            "custom_components.navimow.config_flow.async_get_clientsession"
        ) as mock_get_session:
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_auth_complete(
                user_input={
                    "access_token": "valid_token",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                }
            )

        assert result["type"] == "abort"
        assert result["reason"] == "cannot_connect"


# ---------------------------------------------------------------------------
# Tests: async_step_devices
# ---------------------------------------------------------------------------


class TestAsyncStepDevices:
    """Tests for the device selection step."""

    @pytest.mark.asyncio
    async def test_show_device_selection_form(self, mock_flow):
        """Test that device selection form is shown."""
        mock_flow._devices = [
            {
                "device_sn": "NVM1234567890",
                "name": "Front Yard Mower",
                "model": "Navimow i105",
                "online": True,
            },
        ]

        result = await mock_flow.async_step_devices(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "devices"

    @pytest.mark.asyncio
    async def test_create_entry_with_selected_devices(self, mock_flow):
        """Test that selecting devices creates a config entry."""
        mock_flow._access_token = "access_token_123"
        mock_flow._refresh_token = "refresh_token_456"
        mock_flow._token_expiry = "2024-01-01T12:00:00+00:00"
        mock_flow._region = "fra"
        mock_flow._devices = [
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
        ]

        result = await mock_flow.async_step_devices(
            user_input={"devices": ["NVM1234567890"]}
        )

        assert result["type"] == "create_entry"
        assert "Navimow" in result["title"]
        assert result["data"]["access_token"] == "access_token_123"
        assert result["data"]["refresh_token"] == "refresh_token_456"
        assert result["data"]["token_expiry"] == "2024-01-01T12:00:00+00:00"
        assert result["data"]["region"] == "fra"
        assert result["data"]["devices"] == ["NVM1234567890"]

    @pytest.mark.asyncio
    async def test_create_entry_with_multiple_devices(self, mock_flow):
        """Test that multiple devices can be selected."""
        mock_flow._access_token = "access_token_123"
        mock_flow._refresh_token = "refresh_token_456"
        mock_flow._token_expiry = "2024-01-01T12:00:00+00:00"
        mock_flow._region = "ore"
        mock_flow._devices = [
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
        ]

        result = await mock_flow.async_step_devices(
            user_input={"devices": ["NVM1234567890", "NVM0987654321"]}
        )

        assert result["type"] == "create_entry"
        assert result["data"]["devices"] == ["NVM1234567890", "NVM0987654321"]
        assert result["data"]["region"] == "ore"


# ---------------------------------------------------------------------------
# Tests: async_step_reauth
# ---------------------------------------------------------------------------


class TestAsyncStepReauth:
    """Tests for the re-authentication flow."""

    @pytest.mark.asyncio
    async def test_reauth_shows_confirm_form(self, mock_flow, mock_hass):
        """Test that reauth step shows the region confirmation form."""
        mock_entry = MagicMock()
        mock_entry.data = {
            "region": "fra",
            "access_token": "old_token",
            "refresh_token": "old_refresh",
        }
        mock_hass.config_entries.async_get_entry.return_value = mock_entry

        result = await mock_flow.async_step_reauth(
            entry_data={"region": "fra"}
        )

        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

    @pytest.mark.asyncio
    async def test_reauth_confirm_opens_browser(self, mock_flow, mock_hass):
        """Test that confirming reauth opens the browser login."""
        mock_entry = MagicMock()
        mock_entry.data = {"region": "fra"}
        mock_flow._reauth_entry = mock_entry
        mock_flow._region = "fra"

        result = await mock_flow.async_step_reauth_auth(user_input=None)

        assert result["type"] == "external"
        assert result["step_id"] == "reauth_auth"
        assert "navimow-h5-fra-willand.com" in result["url"]

    @pytest.mark.asyncio
    async def test_reauth_complete_success(self, mock_flow, mock_hass):
        """Test successful re-authentication updates the entry."""
        mock_entry = MagicMock()
        mock_entry.data = {
            "region": "fra",
            "access_token": "old_token",
            "refresh_token": "old_refresh",
            "token_expiry": "2024-01-01T00:00:00+00:00",
            "devices": ["NVM1234567890"],
        }
        mock_entry.entry_id = "test_entry_id"
        mock_flow._reauth_entry = mock_entry
        mock_flow._region = "fra"

        result = await mock_flow.async_step_reauth_complete(
            user_input={
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "expires_in": 7200,
            }
        )

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        mock_hass.config_entries.async_update_entry.assert_called_once()
        mock_hass.config_entries.async_reload.assert_called_once_with("test_entry_id")

    @pytest.mark.asyncio
    async def test_reauth_complete_no_token_aborts(self, mock_flow, mock_hass):
        """Test re-authentication without token aborts."""
        mock_flow._reauth_entry = MagicMock()
        mock_flow._region = "fra"

        result = await mock_flow.async_step_reauth_complete(
            user_input={"access_token": "", "refresh_token": ""}
        )

        assert result["type"] == "abort"
        assert result["reason"] == "invalid_auth"


# ---------------------------------------------------------------------------
# Tests: _fetch_devices
# ---------------------------------------------------------------------------


class TestFetchDevices:
    """Tests for the _fetch_devices helper method."""

    @pytest.mark.asyncio
    async def test_fetch_devices_success(self, mock_flow):
        """Test successful device fetching via openapi/smarthome/authList."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "code": 1,
                "data": {
                    "payload": {
                        "devices": [
                            {
                                "id": "NVM1234567890",
                                "name": "Front Yard Mower",
                                "model": "Navimow i105",
                                "isOnline": True,
                            },
                        ]
                    }
                },
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        devices = await mock_flow._fetch_devices(
            mock_session, "fra", "access_token_123"
        )

        assert len(devices) == 1
        assert devices[0]["device_sn"] == "NVM1234567890"
        assert devices[0]["name"] == "Front Yard Mower"
        assert devices[0]["model"] == "Navimow i105"
        assert devices[0]["online"] is True

    @pytest.mark.asyncio
    async def test_fetch_devices_empty_response(self, mock_flow):
        """Test device fetching with empty device list."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "code": 1,
                "data": {"payload": {"devices": []}},
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        devices = await mock_flow._fetch_devices(
            mock_session, "fra", "access_token_123"
        )

        assert devices == []

    @pytest.mark.asyncio
    async def test_fetch_devices_http_error(self, mock_flow):
        """Test device fetching with HTTP error."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with pytest.raises(aiohttp.ClientError):
            await mock_flow._fetch_devices(
                mock_session, "fra", "access_token_123"
            )

    @pytest.mark.asyncio
    async def test_fetch_devices_uses_correct_url(self, mock_flow):
        """Test that _fetch_devices calls the correct API endpoint."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "code": 1,
                "data": {"payload": {"devices": []}},
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        await mock_flow._fetch_devices(mock_session, "fra", "token123")

        # Verify the correct URL was called
        call_args = mock_session.get.call_args
        url = call_args[0][0]
        assert url == "https://navimow-fra.ninebot.com/openapi/smarthome/authList"

    @pytest.mark.asyncio
    async def test_fetch_devices_uses_bearer_auth(self, mock_flow):
        """Test that _fetch_devices uses Bearer token auth."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "code": 1,
                "data": {"payload": {"devices": []}},
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        await mock_flow._fetch_devices(mock_session, "fra", "my_token_abc")

        # Verify Bearer auth header
        call_args = mock_session.get.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer my_token_abc"
        assert "requestId" in headers

    @pytest.mark.asyncio
    async def test_fetch_devices_api_error_code(self, mock_flow):
        """Test that non-success API code returns empty list."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "code": 0,
                "desc": "unauthorized",
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        devices = await mock_flow._fetch_devices(
            mock_session, "fra", "invalid_token"
        )

        assert devices == []


# ---------------------------------------------------------------------------
# Tests: _build_login_url
# ---------------------------------------------------------------------------


class TestBuildLoginUrl:
    """Tests for the _build_login_url helper."""

    def test_login_url_contains_region_base(self, mock_flow):
        """Test that login URL uses the correct regional base."""
        mock_flow._region = "fra"
        url = mock_flow._build_login_url()
        assert "navimow-h5-fra-willand.com/smartHome/login" in url

    def test_login_url_contains_redirect_uri(self, mock_flow):
        """Test that login URL includes redirect_uri parameter."""
        mock_flow._region = "fra"
        url = mock_flow._build_login_url()
        assert "redirect_uri=" in url
        assert "auth%2Fexternal%2Fcallback" in url

    def test_login_url_contains_flow_id(self, mock_flow):
        """Test that login URL includes flow_id parameter."""
        mock_flow._region = "fra"
        url = mock_flow._build_login_url()
        assert "flow_id=" in url

    def test_login_url_different_regions(self, mock_flow):
        """Test that different regions produce different URLs."""
        mock_flow._region = "ore"
        url_ore = mock_flow._build_login_url()
        mock_flow._region = "sg"
        url_sg = mock_flow._build_login_url()

        assert "ore" in url_ore
        assert "sg" in url_sg
        assert url_ore != url_sg


# ---------------------------------------------------------------------------
# Tests: Constants and schema validation
# ---------------------------------------------------------------------------


class TestConfigFlowConstants:
    """Tests for config flow constants and schema."""

    def test_region_labels_cover_all_regions(self):
        """Test that all regions have labels."""
        from custom_components.navimow.const import REGIONS

        for region in REGIONS:
            assert region in REGION_LABELS

    def test_domain_is_navimow(self):
        """Test that the domain is correctly set."""
        assert DOMAIN == "navimow"

    def test_oauth_login_urls_cover_all_regions(self):
        """Test that all regions have OAuth login URLs."""
        from custom_components.navimow.const import REGIONS

        for region in REGIONS:
            assert region in OAUTH_LOGIN_URLS
            assert "smartHome/login" in OAUTH_LOGIN_URLS[region]

    def test_api_base_urls_cover_all_regions(self):
        """Test that all regions have API base URLs."""
        from custom_components.navimow.const import REGIONS

        for region in REGIONS:
            assert region in API_BASE_URLS
            assert "ninebot.com" in API_BASE_URLS[region]

    def test_config_flow_version(self):
        """Test that the config flow version is set."""
        assert NavimowConfigFlow.VERSION == 1
