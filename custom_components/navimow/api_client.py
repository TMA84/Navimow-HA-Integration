"""API client for the Navimow cloud platform.

Uses the openapi/smarthome endpoints matching the navimow-sdk pattern.
Auth is simple Bearer token + requestId header (no HMAC signing needed).
Response format uses code=1 for success.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .auth import NavimowAuth
from .const import API_BASE_URLS

_LOGGER = logging.getLogger(__name__)


class NavimowApiError(Exception):
    """Raised when an API request fails."""

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error description.
            retry_after: Seconds to wait before retrying (for rate limiting).
        """
        super().__init__(message)
        self.retry_after = retry_after


class NavimowApiClient:
    """Client for the Navimow cloud API.

    Uses the openapi/smarthome endpoints with Bearer token auth,
    matching the navimow-sdk implementation.
    """

    MAX_RETRIES = 3
    DEFAULT_RETRY_AFTER = 60

    def __init__(
        self,
        session: aiohttp.ClientSession,
        auth: NavimowAuth,
        region: str,
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session for HTTP requests.
            auth: Authentication handler for token management.
            region: Server region code (fra, ore, sg, bj, mos).
        """
        self._session = session
        self._auth = auth
        self._region = region

    @property
    def base_url(self) -> str:
        """Return regional API base URL."""
        return API_BASE_URLS.get(self._region, API_BASE_URLS["fra"])

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request with error handling.

        Handles:
        - 401: Attempts token refresh then retries once.
        - 429: Reads Retry-After header, raises NavimowApiError with backoff info.
        - 5xx: Retries up to 3 times with exponential backoff.

        Args:
            method: HTTP method (GET or POST).
            endpoint: API endpoint path (relative, starting with /).
            params: Query parameters for the request.
            data: JSON body data for POST requests.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            NavimowApiError: If the request fails after all retries.
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(1, self.MAX_RETRIES + 1):
            # Ensure token is valid (refreshes via OAuth2Session if expired)
            await self._auth.async_get_access_token()

            # Get auth headers (Bearer token + requestId)
            headers = self._auth.get_auth_headers()

            try:
                async with self._session.request(
                    method,
                    url,
                    params=params if method == "GET" else None,
                    json=data if method == "POST" else None,
                    headers=headers,
                ) as resp:
                    if resp.status == 401:
                        # Token may have been invalidated server-side
                        # Force a new token fetch (OAuth2Session will refresh)
                        _LOGGER.debug(
                            "Received 401 for %s, retrying with fresh token", endpoint
                        )
                        await self._auth.async_get_access_token()
                        headers = self._auth.get_auth_headers()
                        async with self._session.request(
                            method,
                            url,
                            params=params if method == "GET" else None,
                            json=data if method == "POST" else None,
                            headers=headers,
                        ) as retry_resp:
                            if retry_resp.status == 401:
                                raise NavimowApiError(
                                    f"Authentication failed for {endpoint} after token refresh"
                                )
                            retry_resp.raise_for_status()
                            return await retry_resp.json()

                    if resp.status == 429:
                        retry_after_header = resp.headers.get("Retry-After")
                        try:
                            retry_after = (
                                int(retry_after_header)
                                if retry_after_header
                                else self.DEFAULT_RETRY_AFTER
                            )
                        except (ValueError, TypeError):
                            retry_after = self.DEFAULT_RETRY_AFTER
                        if retry_after < 0:
                            retry_after = self.DEFAULT_RETRY_AFTER
                        raise NavimowApiError(
                            f"Rate limited on {endpoint}, retry after {retry_after}s",
                            retry_after=retry_after,
                        )

                    if resp.status >= 500:
                        if attempt < self.MAX_RETRIES:
                            delay = 2 ** (attempt - 1)
                            _LOGGER.warning(
                                "Server error %d for %s, retrying in %ds (attempt %d/%d)",
                                resp.status,
                                endpoint,
                                delay,
                                attempt,
                                self.MAX_RETRIES,
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise NavimowApiError(
                            f"Server error {resp.status} for {endpoint} after {self.MAX_RETRIES} retries"
                        )

                    if resp.status >= 400:
                        raise NavimowApiError(
                            f"Request failed for {endpoint} with status {resp.status}"
                        )

                    return await resp.json()

            except aiohttp.ClientError as err:
                if attempt < self.MAX_RETRIES:
                    delay = 2 ** (attempt - 1)
                    _LOGGER.warning(
                        "Network error for %s: %s, retrying in %ds (attempt %d/%d)",
                        endpoint,
                        err,
                        delay,
                        attempt,
                        self.MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise NavimowApiError(
                    f"Network error for {endpoint} after {self.MAX_RETRIES} retries: {err}"
                ) from err

        # Should not reach here, but just in case
        raise NavimowApiError(f"Request failed for {endpoint} after {self.MAX_RETRIES} retries")

    async def _get(
        self, endpoint: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated GET request.

        Args:
            endpoint: API endpoint path (starting with /).
            params: Query parameters.

        Returns:
            Parsed JSON response.
        """
        return await self._request("GET", endpoint, params=params)

    async def _post(
        self, endpoint: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated POST request.

        Args:
            endpoint: API endpoint path (starting with /).
            data: JSON body data.

        Returns:
            Parsed JSON response.
        """
        return await self._request("POST", endpoint, data=data)

    # ─── Smart Home API Endpoints (from SDK) ────────────────────────────

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get list of devices bound to the account.

        Uses /openapi/smarthome/authList endpoint.

        Returns:
            List of device dictionaries from the API.
        """
        result = await self._get("/openapi/smarthome/authList")
        if result.get("code") != 1:
            _LOGGER.error(
                "Device list request failed: %s", result.get("desc", "unknown")
            )
            return []
        payload = result.get("data", {}).get("payload", {})
        return payload.get("devices", [])

    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        """Get status for a single device.

        Uses /openapi/smarthome/getVehicleStatus endpoint.

        Args:
            device_id: Device identifier.

        Returns:
            Device status dictionary.
        """
        result = await self._post(
            "/openapi/smarthome/getVehicleStatus",
            data={"devices": [{"id": device_id}]},
        )
        if result.get("code") != 1:
            _LOGGER.error(
                "Device status request failed: %s", result.get("desc", "unknown")
            )
            return {}
        payload = result.get("data", {}).get("payload", {})
        devices = payload.get("devices", [])
        if devices:
            return devices[0]
        return {}

    async def get_device_statuses(
        self, device_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Get status for multiple devices.

        Uses /openapi/smarthome/getVehicleStatus endpoint.

        Args:
            device_ids: List of device identifiers.

        Returns:
            Mapping of device_id to status dictionary.
        """
        if not device_ids:
            return {}
        result = await self._post(
            "/openapi/smarthome/getVehicleStatus",
            data={"devices": [{"id": did} for did in device_ids]},
        )
        if result.get("code") != 1:
            _LOGGER.error(
                "Device statuses request failed: %s", result.get("desc", "unknown")
            )
            return {}
        payload = result.get("data", {}).get("payload", {})
        devices = payload.get("devices", [])
        return {d.get("id", ""): d for d in devices if d.get("id")}

    async def send_command(
        self, device_sn: str, command: str, params: dict[str, Any] | None = None
    ) -> bool:
        """Send a command to the device.

        Uses /openapi/smarthome/sendCommands endpoint.

        Args:
            device_sn: Device serial number / identifier.
            command: Command name (e.g., "action.devices.commands.StartStop").
            params: Optional command parameters.

        Returns:
            True if the command was accepted.

        Raises:
            NavimowApiError: If the command fails.
        """
        execution: dict[str, Any] = {"command": command}
        if params:
            execution["params"] = params

        result = await self._post(
            "/openapi/smarthome/sendCommands",
            data={
                "commands": [
                    {"devices": [{"id": device_sn}], "execution": execution}
                ]
            },
        )
        if result.get("code") != 1:
            raise NavimowApiError(
                f"Command failed: {result.get('desc', 'unknown error')}"
            )

        # Check individual command results
        payload = result.get("data", {}).get("payload", {})
        command_results = payload.get("commands", [])
        for cmd_result in command_results:
            if cmd_result.get("status") == "ERROR":
                error_code = cmd_result.get("errorCode") or "COMMAND_FAILED"
                # Device already in target state is treated as success
                if error_code == "alreadyInState":
                    continue
                raise NavimowApiError(
                    f"Command failed with error: {error_code}"
                )
        return True

    async def get_mqtt_info(self) -> dict[str, Any]:
        """Get MQTT connection information.

        Uses /openapi/mqtt/userInfo/get/v2 endpoint.

        Returns:
            MQTT connection info dictionary.
        """
        result = await self._get("/openapi/mqtt/userInfo/get/v2")
        if result.get("code") != 1:
            _LOGGER.error(
                "MQTT info request failed: %s", result.get("desc", "unknown")
            )
            return {}
        return result.get("data", {})

    # ─── Legacy Endpoints (kept for coordinator compatibility) ──────────

    async def get_device_info(self, device_sn: str) -> dict[str, Any]:
        """Get static device information.

        Falls back to the smart home device status if the legacy endpoint
        is not available.

        Args:
            device_sn: Device serial number.

        Returns:
            Device info dictionary.
        """
        # Try the smart home status endpoint which includes device info
        status = await self.get_device_status(device_sn)
        return status.get("deviceInfo", status)

    async def get_device_data(self, device_sn: str) -> dict[str, Any]:
        """Get real-time telemetry data for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            Telemetry data dictionary.
        """
        status = await self.get_device_status(device_sn)
        return status.get("states", status)

    async def get_today_plan(self, device_sn: str) -> dict[str, Any]:
        """Get today's mowing schedule for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            Schedule data dictionary.
        """
        status = await self.get_device_status(device_sn)
        return status.get("schedule", {})

    async def get_settings_status(self, device_sn: str) -> dict[str, Any]:
        """Get current device settings.

        Args:
            device_sn: Device serial number.

        Returns:
            Settings data dictionary.
        """
        status = await self.get_device_status(device_sn)
        return status.get("settings", {})

    async def get_location(self, device_sn: str) -> dict[str, Any]:
        """Get GPS location data for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            Location data dictionary.
        """
        status = await self.get_device_status(device_sn)
        return status.get("location", {})

    async def get_errors(self, device_sn: str) -> list[dict[str, Any]]:
        """Get active errors for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            List of error info dictionaries.
        """
        status = await self.get_device_status(device_sn)
        return status.get("errors", [])

    async def get_firmware_info(self, device_sn: str) -> dict[str, Any]:
        """Get firmware update information for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            Firmware info dictionary.
        """
        status = await self.get_device_status(device_sn)
        return status.get("firmware", {})

    async def get_trail_list(self, device_sn: str) -> list[dict[str, Any]]:
        """Get mowing trail history list.

        Args:
            device_sn: Device serial number.

        Returns:
            List of trail entry dictionaries.
        """
        status = await self.get_device_status(device_sn)
        return status.get("trails", [])

    async def set_setting(
        self, device_sn: str, key: str, value: Any
    ) -> bool:
        """Update a device setting via command.

        Args:
            device_sn: Device serial number.
            key: Setting key name.
            value: New setting value.

        Returns:
            True if the setting was updated successfully.

        Raises:
            NavimowApiError: If the setting update fails.
        """
        return await self.send_command(
            device_sn,
            "action.devices.commands.SetSetting",
            params={"key": key, "value": value},
        )

    async def set_power(self, device_sn: str, action: str) -> bool:
        """Control device power state.

        Args:
            device_sn: Device serial number.
            action: Power action (e.g., 'on', 'off').

        Returns:
            True if the power action was accepted.

        Raises:
            NavimowApiError: If the power action fails.
        """
        command = "action.devices.commands.StartStop"
        params = {"on": action == "on"}
        return await self.send_command(device_sn, command, params=params)
