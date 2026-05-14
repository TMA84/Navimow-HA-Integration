"""Authentication handler for the Navimow API."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import aiohttp

from .const import PASSPORT_BASE_URL
from .encryption import NbEncryption

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)


class NavimowAuthError(Exception):
    """Raised when authentication fails."""


class NavimowAuth:
    """Authentication handler for Navimow API."""

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

        If the current token is expired, this will automatically refresh
        it before returning.

        Returns:
            A valid access token string.

        Raises:
            NavimowAuthError: If token refresh fails.
        """
        now = datetime.now(timezone.utc)
        if now >= self._token_expiry:
            _LOGGER.debug("Access token expired, refreshing")
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

    def sign_request(self, params: dict[str, str]) -> dict[str, str]:
        """Sign request parameters with NbEncryption.

        Generates a nonce, timestamp, and HMAC signature for the given
        parameters, then builds the signed HTTP headers.

        Args:
            params: Dictionary of request parameters to sign.

        Returns:
            Dictionary of HTTP headers with authentication and signature.
        """
        nonce = NbEncryption.generate_nonce()
        timestamp = int(time.time())
        signature = NbEncryption.sign_params(
            params=params,
            access_token=self._access_token,
            timestamp=timestamp,
            nonce=nonce,
        )
        return NbEncryption.build_signed_headers(
            access_token=self._access_token,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )

    @staticmethod
    async def async_login(
        session: aiohttp.ClientSession,
        region: str,
        username: str,
        password: str,
    ) -> tuple[str, str, datetime]:
        """Perform initial login, return tokens.

        Args:
            session: aiohttp client session for HTTP requests.
            region: Server region code (fra, ore, sg, bj, mos).
            username: User's email or phone number.
            password: User's password.

        Returns:
            Tuple of (access_token, refresh_token, token_expiry).

        Raises:
            NavimowAuthError: If login fails.
        """
        passport_url = PASSPORT_BASE_URL.format(region=region)
        url = f"{passport_url}oauth/access_token"
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
        }

        try:
            async with session.post(url, data=data) as resp:
                if resp.status != 200:
                    raise NavimowAuthError(
                        f"Login failed with status {resp.status}"
                    )
                result = await resp.json()
        except aiohttp.ClientError as err:
            raise NavimowAuthError(f"Login request failed: {err}") from err

        if "access_token" not in result:
            raise NavimowAuthError("Login response missing access_token")

        access_token = result["access_token"]
        refresh_token = result["refresh_token"]
        expires_in = int(result.get("expires_in", 3600))

        token_expiry = datetime.now(timezone.utc).replace(
            microsecond=0
        ) + timedelta(seconds=expires_in)

        return access_token, refresh_token, token_expiry
