"""The Segway Navimow integration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import NavimowApiClient
from .auth import NavimowAuth
from .const import DOMAIN, PLATFORMS
from .coordinator import NavimowCoordinator
from .security import NavimowLogFilter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Navimow from a config entry.

    Creates the API client, auth handler, and a coordinator per device.
    Forwards entity platforms and stores coordinators in hass.data.
    """
    hass.data.setdefault(DOMAIN, {})

    # Set up log filter for credential redaction
    log_filter = NavimowLogFilter()
    integration_logger = logging.getLogger("custom_components.navimow")
    integration_logger.addFilter(log_filter)

    session = async_get_clientsession(hass)

    # Parse token expiry from stored ISO format string
    token_expiry_str = entry.data.get("token_expiry", "")
    try:
        token_expiry = datetime.fromisoformat(token_expiry_str)
    except (ValueError, TypeError):
        token_expiry = datetime.now(tz=timezone.utc)

    region = entry.data["region"]

    # Register known sensitive values with the log filter
    access_token = entry.data["access_token"]
    refresh_token = entry.data["refresh_token"]
    log_filter.add_sensitive_value(access_token)
    log_filter.add_sensitive_value(refresh_token)

    async def _on_token_refresh(
        access_token: str, refresh_token: str, expiry: datetime
    ) -> None:
        """Persist refreshed tokens to the config entry."""
        # Update log filter with new token values
        log_filter.add_sensitive_value(access_token)
        log_filter.add_sensitive_value(refresh_token)

        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expiry": expiry.isoformat(),
            },
        )

    auth = NavimowAuth(
        session=session,
        region=region,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expiry=token_expiry,
        on_token_refresh=_on_token_refresh,
    )

    api_client = NavimowApiClient(
        session=session,
        auth=auth,
        region=region,
    )

    # Create a coordinator per selected device
    devices: list[str] = entry.data.get("devices", [])
    coordinators: dict[str, NavimowCoordinator] = {}

    for device_sn in devices:
        coordinator = NavimowCoordinator(
            hass=hass,
            config_entry=entry,
            api_client=api_client,
            device_sn=device_sn,
        )
        await coordinator.async_config_entry_first_refresh()
        coordinators[device_sn] = coordinator

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinators": coordinators,
        "api_client": api_client,
        "auth": auth,
        "log_filter": log_filter,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Navimow config entry.

    Cancels all coordinator listeners, removes log filter, and removes stored data.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, None)
        # Remove the log filter on unload
        if entry_data and "log_filter" in entry_data:
            integration_logger = logging.getLogger("custom_components.navimow")
            integration_logger.removeFilter(entry_data["log_filter"])

    return unload_ok
