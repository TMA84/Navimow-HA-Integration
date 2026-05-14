"""API client for the Navimow cloud platform."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .auth import NavimowAuth
from .const import API_BASE_URL

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
    """Client for the Navimow cloud API."""

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
            auth: Authentication handler for token management and signing.
            region: Server region code (fra, ore, sg, bj, mos).
        """
        self._session = session
        self._auth = auth
        self._region = region

    @property
    def base_url(self) -> str:
        """Return regional API base URL."""
        return API_BASE_URL.format(region=self._region)

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
            endpoint: API endpoint path (relative to base_url).
            params: Query parameters for the request.
            data: JSON body data for POST requests.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            NavimowApiError: If the request fails after all retries.
        """
        url = f"{self.base_url}{endpoint}"
        request_params = params or {}

        for attempt in range(1, self.MAX_RETRIES + 1):
            # Get a valid token (refreshes if expired)
            await self._auth.async_get_access_token()

            # Sign the request parameters
            headers = self._auth.sign_request(request_params)

            try:
                async with self._session.request(
                    method,
                    url,
                    params=request_params if method == "GET" else None,
                    json=data if method == "POST" else None,
                    headers=headers,
                ) as resp:
                    if resp.status == 401:
                        # Token may have been invalidated server-side; refresh and retry once
                        _LOGGER.debug(
                            "Received 401 for %s, refreshing token", endpoint
                        )
                        await self._auth.async_refresh_token()
                        # Retry with new token
                        headers = self._auth.sign_request(request_params)
                        async with self._session.request(
                            method,
                            url,
                            params=request_params if method == "GET" else None,
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
            endpoint: API endpoint path.
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
            endpoint: API endpoint path.
            data: JSON body data.

        Returns:
            Parsed JSON response.
        """
        return await self._request("POST", endpoint, data=data)

    # ─── Device Endpoints ───────────────────────────────────────────────

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get list of devices bound to the account.

        Returns:
            List of device dictionaries from the API.
        """
        result = await self._get("vehicle/vehicle/index")
        return result.get("data", [])

    async def get_device_info(self, device_sn: str) -> dict[str, Any]:
        """Get static device information.

        Args:
            device_sn: Device serial number.

        Returns:
            Device info dictionary.
        """
        result = await self._get(
            "vehicle/vehicle/get-device-info", params={"sn": device_sn}
        )
        return result.get("data", {})

    async def get_device_data(self, device_sn: str) -> dict[str, Any]:
        """Get real-time telemetry data for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            Telemetry data dictionary.
        """
        result = await self._get(
            "vehicle/vehicle/get-data", params={"sn": device_sn}
        )
        return result.get("data", {})

    async def get_today_plan(self, device_sn: str) -> dict[str, Any]:
        """Get today's mowing schedule for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            Schedule data dictionary.
        """
        result = await self._get(
            "vehicle/vehicle/get-today-plan", params={"sn": device_sn}
        )
        return result.get("data", {})

    async def get_settings_status(self, device_sn: str) -> dict[str, Any]:
        """Get current device settings.

        Args:
            device_sn: Device serial number.

        Returns:
            Settings data dictionary.
        """
        result = await self._get(
            "vehicle/set/status", params={"sn": device_sn}
        )
        return result.get("data", {})

    async def get_location(self, device_sn: str) -> dict[str, Any]:
        """Get GPS location data for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            Location data dictionary.
        """
        result = await self._get(
            "vehicle/vehicle/get-location", params={"sn": device_sn}
        )
        return result.get("data", {})

    async def get_trail_list(self, device_sn: str) -> list[dict[str, Any]]:
        """Get mowing trail history list.

        Args:
            device_sn: Device serial number.

        Returns:
            List of trail entry dictionaries.
        """
        result = await self._get(
            "vehicle/map/trail-list", params={"sn": device_sn}
        )
        return result.get("data", [])

    async def get_trail_detail(self, trail_id: str) -> dict[str, Any]:
        """Get detailed trail data for a specific trail.

        Args:
            trail_id: Trail identifier.

        Returns:
            Trail detail dictionary.
        """
        result = await self._get(
            "vehicle/map/trail-detail", params={"id": trail_id}
        )
        return result.get("data", {})

    async def get_errors(self, device_sn: str) -> list[dict[str, Any]]:
        """Get active errors for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            List of error info dictionaries.
        """
        result = await self._get(
            "vehicle/vehicle/get-hint-error", params={"sn": device_sn}
        )
        return result.get("data", [])

    async def get_firmware_info(self, device_sn: str) -> dict[str, Any]:
        """Get firmware update information for a device.

        Args:
            device_sn: Device serial number.

        Returns:
            Firmware info dictionary.
        """
        result = await self._get(
            "vehicle/firmware/get-new-firmware", params={"sn": device_sn}
        )
        return result.get("data", {})

    async def get_bms_detail(self, device_sn: str) -> dict[str, Any]:
        """Get battery management system details.

        Args:
            device_sn: Device serial number.

        Returns:
            BMS detail dictionary.
        """
        result = await self._get(
            "vehicle/vehicle/bms-detail", params={"sn": device_sn}
        )
        return result.get("data", {})

    # ─── Command Endpoints ──────────────────────────────────────────────

    async def send_command(
        self, device_sn: str, command: str, params: dict[str, Any] | None = None
    ) -> bool:
        """Send a command to the device.

        Args:
            device_sn: Device serial number.
            command: Command identifier (e.g., MOWER_HANDLE_MOW).
            params: Optional command parameters.

        Returns:
            True if the command was accepted.

        Raises:
            NavimowApiError: If the command fails.
        """
        payload: dict[str, Any] = {"sn": device_sn, "command": command}
        if params:
            payload["params"] = params
        result = await self._post("vehicle/vehicle/command", data=payload)
        return result.get("code", -1) == 0

    async def set_setting(
        self, device_sn: str, key: str, value: Any
    ) -> bool:
        """Update a device setting.

        Args:
            device_sn: Device serial number.
            key: Setting key name.
            value: New setting value.

        Returns:
            True if the setting was updated successfully.

        Raises:
            NavimowApiError: If the setting update fails.
        """
        payload: dict[str, Any] = {"sn": device_sn, "key": key, "value": value}
        result = await self._post("vehicle/set/set", data=payload)
        return result.get("code", -1) == 0

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
        payload: dict[str, Any] = {"sn": device_sn, "action": action}
        result = await self._post("vehicle/set/set-power", data=payload)
        return result.get("code", -1) == 0
