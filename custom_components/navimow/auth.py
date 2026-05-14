"""Authentication handler for the Navimow integration.

Uses the same OAuth2 flow as the official NavimowHA integration:
- LocalOAuth2Implementation for the authorize/token exchange
- OAuth2Session for automatic token refresh
- NavimowAuth wrapper for API client usage
"""

from __future__ import annotations

import logging
import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.config_entry_oauth2_flow import LocalOAuth2Implementation

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN

_LOGGER = logging.getLogger(__name__)


class NavimowOAuth2Implementation(LocalOAuth2Implementation):
    """OAuth2 implementation for Navimow, matching the official integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        """Initialize the OAuth2 implementation.

        Args:
            hass: Home Assistant instance.
            domain: Integration domain.
            client_id: OAuth2 client ID.
            client_secret: OAuth2 client secret.
        """
        super().__init__(
            hass=hass,
            domain=domain,
            client_id=client_id,
            client_secret=client_secret,
            authorize_url=OAUTH2_AUTHORIZE,
            token_url=OAUTH2_TOKEN,
        )

    @property
    def name(self) -> str:
        """Return the name of this implementation."""
        return "Navimow"

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Generate the authorize URL ensuring channel=homeassistant is present.

        Args:
            flow_id: The config flow ID for the callback.

        Returns:
            The full authorize URL with all required parameters.
        """
        url = await super().async_generate_authorize_url(flow_id)
        # Ensure channel=homeassistant is in the URL
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("channel", "homeassistant")
        return urlunparse(parsed._replace(query=urlencode(query)))

    async def _async_refresh_token(self, token: dict) -> dict:
        """Refresh the access token.

        Raises ConfigEntryAuthFailed if no refresh token is available
        or if the token is permanently invalid.

        Args:
            token: The current token dict containing refresh_token.

        Returns:
            New token dict with refreshed access_token.

        Raises:
            ConfigEntryAuthFailed: If refresh token is missing or permanently invalid.
        """
        if "refresh_token" not in token:
            raise ConfigEntryAuthFailed("No refresh token available")

        try:
            return await super()._async_refresh_token(token)
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            err_str = str(err).lower()
            if any(k in err_str for k in ("401", "403", "invalid", "expired")):
                raise ConfigEntryAuthFailed(
                    f"Token expired or invalid: {err}"
                ) from err
            raise


class NavimowAuth:
    """Auth wrapper that gets token from HA's OAuth2 session.

    Provides a simple interface for the API client to get valid
    access tokens and auth headers.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        implementation: NavimowOAuth2Implementation,
    ) -> None:
        """Initialize the auth wrapper.

        Args:
            hass: Home Assistant instance.
            config_entry: The config entry containing token data.
            implementation: The OAuth2 implementation for token refresh.
        """
        self._hass = hass
        self._config_entry = config_entry
        self._implementation = implementation
        self._session = config_entry_oauth2_flow.OAuth2Session(
            hass, config_entry, implementation
        )

    async def async_get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary.

        Returns:
            A valid access token string.

        Raises:
            ConfigEntryAuthFailed: If the token cannot be refreshed.
        """
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]

    def get_auth_headers(self) -> dict[str, str]:
        """Get auth headers for API requests.

        Returns:
            Dictionary with Authorization Bearer header and a unique requestId.
        """
        token = self._config_entry.data.get("token", {})
        return {
            "Authorization": f"Bearer {token.get('access_token', '')}",
            "requestId": str(uuid.uuid4()),
        }
