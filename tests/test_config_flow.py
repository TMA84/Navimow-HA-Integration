"""Tests for the Navimow config flow."""

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

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

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
from custom_components.navimow.auth import NavimowAuthError
from custom_components.navimow.config_flow import (
    REGION_LABELS,
    STEP_USER_DATA_SCHEMA,
    NavimowConfigFlow,
)
from custom_components.navimow.const import DOMAIN


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
    return hass


@pytest.fixture
def mock_flow(mock_hass):
    """Return a NavimowConfigFlow instance with mocked hass."""
    flow = NavimowConfigFlow()
    flow.hass = mock_hass
    flow.context = {"entry_id": "test_entry_id"}
    return flow


@pytest.fixture
def valid_user_input():
    """Return valid user input for the user step."""
    return {
        "username": "user@example.com",
        "password": "securepassword123",
        "region": "fra",
    }


@pytest.fixture
def mock_login_success():
    """Return a mock for successful login."""
    token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    return ("access_token_123", "refresh_token_456", token_expiry)


# ---------------------------------------------------------------------------
# Tests: async_step_user
# ---------------------------------------------------------------------------


class TestAsyncStepUser:
    """Tests for the user step of the config flow."""

    @pytest.mark.asyncio
    async def test_show_form_when_no_input(self, mock_flow):
        """Test that the form is shown when no user input is provided."""
        result = await mock_flow.async_step_user(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    @pytest.mark.asyncio
    async def test_successful_login_proceeds_to_devices(
        self, mock_flow, valid_user_input, mock_login_success
    ):
        """Test that successful login proceeds to device selection."""
        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                return_value=mock_login_success,
            ),
            patch.object(
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
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_user(user_input=valid_user_input)

        # Should proceed to devices step (show form for device selection)
        assert result["type"] == "form"
        assert result["step_id"] == "devices"

    @pytest.mark.asyncio
    async def test_invalid_credentials_shows_error(
        self, mock_flow, valid_user_input
    ):
        """Test that invalid credentials show an error."""
        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                side_effect=NavimowAuthError("Invalid credentials"),
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_user(user_input=valid_user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_network_error_shows_cannot_connect(
        self, mock_flow, valid_user_input
    ):
        """Test that network errors show cannot_connect error."""
        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                side_effect=aiohttp.ClientError("Connection failed"),
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_user(user_input=valid_user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_timeout_error_shows_cannot_connect(
        self, mock_flow, valid_user_input
    ):
        """Test that timeout errors show cannot_connect error."""
        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                side_effect=TimeoutError(),
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_user(user_input=valid_user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_no_devices_shows_error(
        self, mock_flow, valid_user_input, mock_login_success
    ):
        """Test that no devices found shows an error."""
        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                return_value=mock_login_success,
            ),
            patch.object(
                mock_flow,
                "_fetch_devices",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_user(user_input=valid_user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "no_devices"}

    @pytest.mark.asyncio
    async def test_device_fetch_network_error(
        self, mock_flow, valid_user_input, mock_login_success
    ):
        """Test that network error during device fetch shows cannot_connect."""
        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                return_value=mock_login_success,
            ),
            patch.object(
                mock_flow,
                "_fetch_devices",
                new_callable=AsyncMock,
                side_effect=aiohttp.ClientError("Network error"),
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_user(user_input=valid_user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "cannot_connect"}


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
        mock_flow._username = "user@example.com"
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
        assert result["title"] == "Navimow (user@example.com)"
        assert result["data"]["access_token"] == "access_token_123"
        assert result["data"]["refresh_token"] == "refresh_token_456"
        assert result["data"]["token_expiry"] == "2024-01-01T12:00:00+00:00"
        assert result["data"]["region"] == "fra"
        assert result["data"]["username"] == "user@example.com"
        assert result["data"]["devices"] == ["NVM1234567890"]

    @pytest.mark.asyncio
    async def test_create_entry_with_multiple_devices(self, mock_flow):
        """Test that multiple devices can be selected."""
        mock_flow._access_token = "access_token_123"
        mock_flow._refresh_token = "refresh_token_456"
        mock_flow._token_expiry = "2024-01-01T12:00:00+00:00"
        mock_flow._region = "ore"
        mock_flow._username = "user@example.com"
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
        """Test that reauth step shows the confirmation form."""
        mock_entry = MagicMock()
        mock_entry.data = {
            "username": "user@example.com",
            "region": "fra",
        }
        mock_hass.config_entries.async_get_entry.return_value = mock_entry

        result = await mock_flow.async_step_reauth(entry_data={})

        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

    @pytest.mark.asyncio
    async def test_reauth_confirm_success(self, mock_flow, mock_hass):
        """Test successful re-authentication."""
        mock_entry = MagicMock()
        mock_entry.data = {
            "username": "user@example.com",
            "region": "fra",
            "access_token": "old_token",
            "refresh_token": "old_refresh",
            "token_expiry": "2024-01-01T00:00:00+00:00",
            "devices": ["NVM1234567890"],
        }
        mock_entry.entry_id = "test_entry_id"
        mock_hass.config_entries.async_get_entry.return_value = mock_entry
        mock_flow._reauth_entry = mock_entry

        token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                return_value=("new_access_token", "new_refresh_token", token_expiry),
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_reauth_confirm(
                user_input={
                    "username": "user@example.com",
                    "password": "newpassword",
                    "region": "fra",
                }
            )

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        mock_hass.config_entries.async_update_entry.assert_called_once()
        mock_hass.config_entries.async_reload.assert_called_once_with("test_entry_id")

    @pytest.mark.asyncio
    async def test_reauth_confirm_invalid_credentials(self, mock_flow, mock_hass):
        """Test re-authentication with invalid credentials."""
        mock_entry = MagicMock()
        mock_entry.data = {
            "username": "user@example.com",
            "region": "fra",
        }
        mock_flow._reauth_entry = mock_entry

        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                side_effect=NavimowAuthError("Invalid credentials"),
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_reauth_confirm(
                user_input={
                    "username": "user@example.com",
                    "password": "wrongpassword",
                    "region": "fra",
                }
            )

        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"
        assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_reauth_confirm_network_error(self, mock_flow, mock_hass):
        """Test re-authentication with network error."""
        mock_entry = MagicMock()
        mock_entry.data = {
            "username": "user@example.com",
            "region": "fra",
        }
        mock_flow._reauth_entry = mock_entry

        with (
            patch(
                "custom_components.navimow.config_flow.async_get_clientsession"
            ) as mock_get_session,
            patch(
                "custom_components.navimow.config_flow.NavimowAuth.async_login",
                new_callable=AsyncMock,
                side_effect=aiohttp.ClientError("Connection failed"),
            ),
        ):
            mock_get_session.return_value = AsyncMock()
            result = await mock_flow.async_step_reauth_confirm(
                user_input={
                    "username": "user@example.com",
                    "password": "password",
                    "region": "fra",
                }
            )

        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"
        assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# Tests: _fetch_devices
# ---------------------------------------------------------------------------


class TestFetchDevices:
    """Tests for the _fetch_devices helper method."""

    @pytest.mark.asyncio
    async def test_fetch_devices_success(self, mock_flow):
        """Test successful device fetching."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "code": 0,
                "data": [
                    {
                        "sn": "NVM1234567890",
                        "name": "Front Yard Mower",
                        "model": "Navimow i105",
                        "online": True,
                    },
                ],
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch(
            "custom_components.navimow.encryption.NbEncryption"
        ) as mock_encryption:
            mock_encryption.generate_nonce.return_value = "test_nonce"
            mock_encryption.sign_params.return_value = "test_signature"
            mock_encryption.build_signed_headers.return_value = {
                "Authorization": "Bearer token",
            }

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
        """Test device fetching with empty response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"code": 0, "data": []}
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch(
            "custom_components.navimow.encryption.NbEncryption"
        ) as mock_encryption:
            mock_encryption.generate_nonce.return_value = "test_nonce"
            mock_encryption.sign_params.return_value = "test_signature"
            mock_encryption.build_signed_headers.return_value = {}

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

        with patch(
            "custom_components.navimow.encryption.NbEncryption"
        ) as mock_encryption:
            mock_encryption.generate_nonce.return_value = "test_nonce"
            mock_encryption.sign_params.return_value = "test_signature"
            mock_encryption.build_signed_headers.return_value = {}

            with pytest.raises(aiohttp.ClientError):
                await mock_flow._fetch_devices(
                    mock_session, "fra", "access_token_123"
                )

    @pytest.mark.asyncio
    async def test_fetch_devices_filters_invalid_entries(self, mock_flow):
        """Test that devices without serial numbers are filtered out."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "code": 0,
                "data": [
                    {
                        "sn": "NVM1234567890",
                        "name": "Valid Mower",
                        "model": "i105",
                        "online": True,
                    },
                    {
                        "name": "Invalid Mower",
                        "model": "i108",
                        "online": False,
                    },
                ],
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch(
            "custom_components.navimow.encryption.NbEncryption"
        ) as mock_encryption:
            mock_encryption.generate_nonce.return_value = "test_nonce"
            mock_encryption.sign_params.return_value = "test_signature"
            mock_encryption.build_signed_headers.return_value = {}

            devices = await mock_flow._fetch_devices(
                mock_session, "fra", "access_token_123"
            )

        assert len(devices) == 1
        assert devices[0]["device_sn"] == "NVM1234567890"


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

    def test_user_schema_has_required_fields(self):
        """Test that the user schema has all required fields."""
        schema_keys = [str(k) for k in STEP_USER_DATA_SCHEMA.schema]
        assert "username" in schema_keys
        assert "password" in schema_keys
        assert "region" in schema_keys

    def test_config_flow_version(self):
        """Test that the config flow version is set."""
        assert NavimowConfigFlow.VERSION == 1
