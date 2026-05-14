"""Authentication handler for the Navimow API.

Uses OAuth2 Authorization Code Flow with an external browser login step.
The SDK expects a pre-obtained Bearer token - no HMAC signing is needed
for the openapi endpoints.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import aiohttp

from .const import API_BASE_URLS, PASSPORT_BASE_URL

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)


class NavimowAuthError(Exception):
    """Raised when authentication fails."""


class NavimowAuth:
    """Authentication handler for Navimow API.

    Manages Bearer token lifecycle including refresh. Auth headers follow
    the SDK pattern: Authorization: Bearer {token} + requestId: {uuid}.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        region: str,
        access_token: str,
        refresh_token: str,
        token_expiry: datetime,
        on_token_refresh: Callable[[str, str, datetime], Awaitable[None]],
    ) -> None:
        """Initialize the auth handler.

        Args:
            session: aiohttp client session for HTTP requests.
            region: Server region code (fra, ore, sg, bj, mos).
            access_token: Current OAuth access token.
            refresh_token: OAuth refresh token for obtaining new access tokens.
            token_expiry: Datetime when the current access token expires.
            on_token_refresh: Callback invoked after successful token refresh
                to persist the new tokens.
        """
        self._session = session
        self._region = region
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expiry = token_expiry
        self._on_token_refresh = on_token_refresh

    @property
    def passport_url(self) -> str:
        """Return regional passport URL."""
        return PASSPORT_BASE_URL.format(region=self._region)

    async def async_get_access_token(self) -> str:
        """Return valid access token, refreshing if needed.

        If the current token is expired or about to expire (within 60s),
        this will automatically refresh it before returning.

        Returns:
            A valid access token string.

        Raises:
            NavimowAuthError: If token refresh fails.
        """
        now = datetime.now(timezone.utc)
        # Refresh 60 seconds before actual expiry to avoid race conditions
        if now >= (self._token_expiry - timedelta(seconds=60)):
            _LOGGER.debug("Access token expired or expiring soon, refreshing")
            await self.async_refresh_token()
        return self._access_token

    async def async_refresh_token(self) -> tuple[str, str, datetime]:
        """Refresh the access token using refresh_token grant.

        Returns:
            Tuple of (new_access_token, new_refresh_token, new_expiry).

        Raises:
            NavimowAuthError: If the refresh request fails.
        """
        url = f"{self.passport_url}oauth/access_token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        try:
            async with self._session.post(url, data=data) as resp:
                if resp.status != 200:
                    raise NavimowAuthError(
                        f"Token refresh failed with status {resp.status}"
                    )
                result = await resp.json()
        except aiohttp.ClientError as err:
            raise NavimowAuthError(
                f"Token refresh request failed: {err}"
            ) from err

        if "access_token" not in result:
            raise NavimowAuthError("Token refresh response missing access_token")

        self._access_token = result["access_token"]
        self._refresh_token = result.get("refresh_token", self._refresh_token)

        expires_in = int(result.get("expires_in", 3600))
        self._token_expiry = datetime.now(timezone.utc).replace(
            microsecond=0
        ) + timedelta(seconds=expires_in)

        _LOGGER.debug("Token refreshed successfully, expires in %d seconds", expires_in)

        await self._on_token_refresh(
            self._access_token, self._refresh_token, self._token_expiry
        )

        return self._access_token, self._refresh_token, self._token_expiry

    def get_auth_headers(self) -> dict[str, str]:
        """Get auth headers matching the SDK pattern.

        Returns:
            Dictionary with Authorization Bearer header and a unique requestId.
        """
        return {
            "Authorization": f"Bearer {self._access_token}",
            "requestId": str(uuid.uuid4()),
        }

    def sign_request(self, params: dict[str, str] | None = None) -> dict[str, str]:
        """Get request headers for API calls.

        The openapi endpoints use simple Bearer token auth (matching the SDK).
        This method replaces the old NbEncryption-based signing.

        Args:
            params: Unused, kept for backward compatibility with coordinator.

        Returns:
            Dictionary of HTTP headers with Bearer auth and requestId.
        """
        return self.get_auth_headers()
