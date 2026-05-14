"""Config flow for the Navimow integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import NavimowAuth, NavimowAuthError
from .const import API_BASE_URL, DOMAIN, REGIONS

_LOGGER = logging.getLogger(__name__)

REGION_LABELS = {
    "fra": "Europe (Frankfurt)",
    "ore": "North America (Oregon)",
    "sg": "Asia-Pacific (Singapore)",
    "bj": "China (Beijing)",
    "mos": "Russia (Moscow)",
}

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Required("region"): vol.In(REGION_LABELS),
    }
)


class NavimowConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Navimow integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: str | None = None
        self._region: str | None = None
        self._username: str | None = None
        self._devices: list[dict[str, Any]] = []
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-initiated setup (credentials + region)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input["username"]
            password = user_input["password"]
            region = user_input["region"]

            session = async_get_clientsession(self.hass)

            try:
                access_token, refresh_token, token_expiry = (
                    await NavimowAuth.async_login(
                        session=session,
                        region=region,
                        username=username,
                        password=password,
                    )
                )
            except NavimowAuthError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                # Store credentials for the devices step
                self._access_token = access_token
                self._refresh_token = refresh_token
                self._token_expiry = token_expiry.isoformat()
                self._region = region
                self._username = username

                # Fetch devices
                try:
                    devices = await self._fetch_devices(
                        session, region, access_token
                    )
                except (aiohttp.ClientError, TimeoutError):
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error fetching devices")
                    errors["base"] = "unknown"
                else:
                    if not devices:
                        errors["base"] = "no_devices"
                    else:
                        self._devices = devices
                        return await self.async_step_devices()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device selection after successful auth."""
        if user_input is not None:
            selected_devices = user_input["devices"]

            # Set unique ID based on username to prevent duplicate entries
            await self.async_set_unique_id(self._username)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Navimow ({self._username})",
                data={
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "token_expiry": self._token_expiry,
                    "region": self._region,
                    "username": self._username,
                    "devices": selected_devices,
                },
            )

        # Build device selection schema
        device_options = {
            device["device_sn"]: f"{device.get('name', device['device_sn'])} ({device.get('model', 'Unknown')})"
            for device in self._devices
        }

        device_schema = vol.Schema(
            {
                vol.Required("devices", default=list(device_options.keys())): vol.All(
                    [vol.In(device_options)],
                    vol.Length(min=1),
                ),
            }
        )

        return self.async_show_form(
            step_id="devices",
            data_schema=device_schema,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when tokens expire."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input["username"]
            password = user_input["password"]
            region = user_input["region"]

            session = async_get_clientsession(self.hass)

            try:
                access_token, refresh_token, token_expiry = (
                    await NavimowAuth.async_login(
                        session=session,
                        region=region,
                        username=username,
                        password=password,
                    )
                )
            except NavimowAuthError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during re-authentication")
                errors["base"] = "unknown"
            else:
                # Update the existing config entry with new tokens
                assert self._reauth_entry is not None
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "token_expiry": token_expiry.isoformat(),
                        "region": region,
                        "username": username,
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        # Pre-fill with existing data if available
        existing_data = {}
        if self._reauth_entry:
            existing_data = {
                "username": self._reauth_entry.data.get("username", ""),
                "region": self._reauth_entry.data.get("region", "fra"),
            }

        reauth_schema = vol.Schema(
            {
                vol.Required(
                    "username", default=existing_data.get("username", "")
                ): str,
                vol.Required("password"): str,
                vol.Required(
                    "region", default=existing_data.get("region", "fra")
                ): vol.In(REGION_LABELS),
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=reauth_schema,
            errors=errors,
        )

    async def _fetch_devices(
        self,
        session: aiohttp.ClientSession,
        region: str,
        access_token: str,
    ) -> list[dict[str, Any]]:
        """Fetch devices from the API after successful login.

        Args:
            session: aiohttp client session.
            region: Server region code.
            access_token: Valid access token.

        Returns:
            List of device dictionaries.
        """
        base_url = API_BASE_URL.format(region=region)
        url = f"{base_url}vehicle/vehicle/index"

        from .encryption import NbEncryption
        import time

        nonce = NbEncryption.generate_nonce()
        timestamp = int(time.time())
        signature = NbEncryption.sign_params(
            params={},
            access_token=access_token,
            timestamp=timestamp,
            nonce=nonce,
        )
        headers = NbEncryption.build_signed_headers(
            access_token=access_token,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )

        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise aiohttp.ClientError(
                    f"Failed to fetch devices: HTTP {resp.status}"
                )
            result = await resp.json()

        devices = result.get("data", [])
        return [
            {
                "device_sn": d.get("sn", d.get("device_sn", "")),
                "name": d.get("name", ""),
                "model": d.get("model", ""),
                "online": d.get("online", False),
            }
            for d in devices
            if d.get("sn") or d.get("device_sn")
        ]
