"""Config flow for the Navimow integration.

Uses the standard Home Assistant OAuth2 flow (AbstractOAuth2FlowHandler),
matching the official NavimowHA integration pattern.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow

from .auth import NavimowOAuth2Implementation
from .const import API_BASE_URLS, CLIENT_ID, CLIENT_SECRET, DOMAIN

_LOGGER = logging.getLogger(__name__)


class NavimowOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle the OAuth2 config flow for Navimow."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data to include in the authorize URL."""
        return {"channel": "homeassistant"}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - start OAuth2 flow."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        # Register our OAuth2 implementation
        impl = NavimowOAuth2Implementation(
            self.hass, DOMAIN, CLIENT_ID, CLIENT_SECRET
        )
        config_entry_oauth2_flow.async_register_implementation(
            self.hass, DOMAIN, impl
        )

        return await super().async_step_user(user_input)

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create the config entry after successful OAuth2 auth.

        Device discovery happens in the coordinator's first refresh,
        matching the official integration pattern.

        Args:
            data: OAuth2 token data from the flow.

        Returns:
            The created config entry result.
        """
        return self.async_create_entry(
            title="Navimow",
            data={
                "auth_implementation": DOMAIN,
                **data,
                "api_base_url": API_BASE_URLS.get("fra"),
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when tokens expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication and redirect to OAuth2 authorize."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")

        # Register our OAuth2 implementation for the reauth flow
        impl = NavimowOAuth2Implementation(
            self.hass, DOMAIN, CLIENT_ID, CLIENT_SECRET
        )
        config_entry_oauth2_flow.async_register_implementation(
            self.hass, DOMAIN, impl
        )

        return await super().async_step_user()
