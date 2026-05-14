"""Config flow for the Navimow integration.

Uses OAuth2 Authorization Code Flow with an external browser login step.
The user selects a region, then is directed to the Navimow login page in
their browser. After successful login, the browser redirects back to
Home Assistant with an authorization code, which is exchanged for tokens.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url

from .auth import NavimowAuth, NavimowAuthError
from .const import API_BASE_URLS, DOMAIN, OAUTH_LOGIN_URLS, REGIONS

_LOGGER = logging.getLogger(__name__)

REGION_LABELS = {
    "fra": "Europe (Frankfurt)",
    "ore": "North America (Oregon)",
    "sg": "Asia-Pacific (Singapore)",
    "bj": "China (Beijing)",
    "mos": "Russia (Moscow)",
}


class NavimowConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Navimow integration using OAuth2 external browser login."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: str | None = None
        self._region: str | None = None
        self._devices: list[dict[str, Any]] = []
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: User selects their server region."""
        if user_input is not None:
            self._region = user_input["region"]
            return await self.async_step_auth()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("region", default="fra"): vol.In(REGION_LABELS),
                }
            ),
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Open external browser for Navimow login.

        Directs the user to the Navimow login page. After login, the page
        redirects back to Home Assistant with the authorization code.
        """
        if user_input is not None:
            # This is called when the external step completes
            return await self.async_step_auth_complete(user_input)

        login_url = self._build_login_url()
        return self.async_external_step(step_id="auth", url=login_url)

    async def async_step_auth_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Handle callback after browser login completes.

        The external auth callback provides the token data from the redirect.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Token data received from the external auth callback
            access_token = user_input.get("access_token", "")
            refresh_token = user_input.get("refresh_token", "")
            expires_in = int(user_input.get("expires_in", 3600))

            if not access_token:
                errors["base"] = "invalid_auth"
            else:
                from datetime import datetime, timedelta, timezone

                self._access_token = access_token
                self._refresh_token = refresh_token
                token_expiry = datetime.now(timezone.utc).replace(
                    microsecond=0
                ) + timedelta(seconds=expires_in)
                self._token_expiry = token_expiry.isoformat()

                # Fetch devices using the obtained token
                session = async_get_clientsession(self.hass)
                try:
                    devices = await self._fetch_devices(
                        session, self._region, access_token
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
                        return self.async_external_step_done(
                            next_step_id="devices"
                        )

        # If we got here with errors, abort and let user retry
        if errors:
            return self.async_abort(reason=errors.get("base", "unknown"))

        return self.async_external_step_done(next_step_id="devices")

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: Device selection after successful auth."""
        if user_input is not None:
            selected_devices = user_input["devices"]

            # Set unique ID based on region + first device to prevent duplicates
            unique_id = f"navimow_{self._region}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Navimow ({REGION_LABELS.get(self._region, self._region)})",
                data={
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "token_expiry": self._token_expiry,
                    "region": self._region,
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
        self._region = entry_data.get("region", "fra")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-authentication by opening browser login again."""
        if user_input is not None:
            # Region may have been updated
            if "region" in user_input:
                self._region = user_input["region"]
            return await self.async_step_reauth_auth()

        # Show form to confirm region before re-auth
        existing_region = "fra"
        if self._reauth_entry:
            existing_region = self._reauth_entry.data.get("region", "fra")

        reauth_schema = vol.Schema(
            {
                vol.Required("region", default=existing_region): vol.In(
                    REGION_LABELS
                ),
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=reauth_schema,
        )

    async def async_step_reauth_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Open browser for re-authentication."""
        if user_input is not None:
            return await self.async_step_reauth_complete(user_input)

        login_url = self._build_login_url()
        return self.async_external_step(step_id="reauth_auth", url=login_url)

    async def async_step_reauth_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete re-authentication with new tokens."""
        if user_input and user_input.get("access_token"):
            from datetime import datetime, timedelta, timezone

            access_token = user_input["access_token"]
            refresh_token = user_input.get("refresh_token", "")
            expires_in = int(user_input.get("expires_in", 3600))
            token_expiry = datetime.now(timezone.utc).replace(
                microsecond=0
            ) + timedelta(seconds=expires_in)

            # Update the existing config entry with new tokens
            assert self._reauth_entry is not None
            self.hass.config_entries.async_update_entry(
                self._reauth_entry,
                data={
                    **self._reauth_entry.data,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_expiry": token_expiry.isoformat(),
                    "region": self._region,
                },
            )
            await self.hass.config_entries.async_reload(
                self._reauth_entry.entry_id
            )
            return self.async_abort(reason="reauth_successful")

        return self.async_abort(reason="invalid_auth")

    def _build_login_url(self) -> str:
        """Build the Navimow OAuth login URL with redirect back to HA.

        Returns:
            Full login URL with redirect_uri parameter.
        """
        region = self._region or "fra"
        base_login_url = OAUTH_LOGIN_URLS.get(
            region, OAUTH_LOGIN_URLS["fra"]
        )

        # Build redirect URI pointing back to Home Assistant
        try:
            ha_url = get_url(self.hass, prefer_external=True)
        except Exception:  # noqa: BLE001
            ha_url = "http://homeassistant.local:8123"

        redirect_uri = f"{ha_url}/auth/external/callback"

        params = {
            "redirect_uri": redirect_uri,
            "flow_id": self.flow_id,
        }

        return f"{base_login_url}?{urlencode(params)}"

    async def _fetch_devices(
        self,
        session: aiohttp.ClientSession,
        region: str,
        access_token: str,
    ) -> list[dict[str, Any]]:
        """Fetch devices from the API after successful login.

        Uses the openapi/smarthome/authList endpoint (matching the SDK).

        Args:
            session: aiohttp client session.
            region: Server region code.
            access_token: Valid access token.

        Returns:
            List of device dictionaries.
        """
        import uuid

        base_url = API_BASE_URLS.get(region, API_BASE_URLS["fra"])
        url = f"{base_url}/openapi/smarthome/authList"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "requestId": str(uuid.uuid4()),
        }

        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise aiohttp.ClientError(
                    f"Failed to fetch devices: HTTP {resp.status}"
                )
            result = await resp.json()

        # SDK response format: code=1 for success, data.payload.devices
        if result.get("code") != 1:
            _LOGGER.error(
                "Device list request failed: %s", result.get("desc", "unknown")
            )
            return []

        payload = result.get("data", {}).get("payload", {})
        devices = payload.get("devices", [])

        return [
            {
                "device_sn": d.get("id", d.get("sn", d.get("device_sn", ""))),
                "name": d.get("name", d.get("customName", "")),
                "model": d.get("model", d.get("type", "")),
                "online": d.get("online", d.get("isOnline", False)),
            }
            for d in devices
            if d.get("id") or d.get("sn") or d.get("device_sn")
        ]
