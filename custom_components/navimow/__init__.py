"""The Segway Navimow integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import NavimowApiClient
from .auth import NavimowAuth, NavimowOAuth2Implementation
from .const import CLIENT_ID, CLIENT_SECRET, DOMAIN, PLATFORMS
from .coordinator import NavimowCoordinator

try:
    from .security import NavimowLogFilter
except ImportError:
    NavimowLogFilter = None  # type: ignore[assignment, misc]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Navimow from a config entry.

    Creates the OAuth2 session, API client, and a coordinator per device.
    Forwards entity platforms and stores coordinators in hass.data.
    """
    hass.data.setdefault(DOMAIN, {})

    # Set up log filter for credential redaction (if available)
    log_filter = NavimowLogFilter() if NavimowLogFilter else None
    if log_filter:
        integration_logger = logging.getLogger("custom_components.navimow")
        integration_logger.addFilter(log_filter)

    # Set up OAuth2 implementation and session
    implementation = NavimowOAuth2Implementation(
        hass, DOMAIN, CLIENT_ID, CLIENT_SECRET
    )
    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN, implementation
    )

    # Create the auth wrapper that manages token refresh via OAuth2Session
    auth = NavimowAuth(hass, entry, implementation)

    # Register sensitive values with the log filter
    token_data = entry.data.get("token", {})
    if log_filter and token_data:
        if token_data.get("access_token"):
            log_filter.add_sensitive_value(token_data["access_token"])
        if token_data.get("refresh_token"):
            log_filter.add_sensitive_value(token_data["refresh_token"])

    session = async_get_clientsession(hass)
    api_client = NavimowApiClient(
        session=session,
        auth=auth,
        region="fra",
    )

    # Discover devices on first refresh (matching official integration pattern)
    # First, get the list of devices from the API
    devices = await api_client.get_devices()
    device_sns = [
        d.get("id", d.get("sn", d.get("device_sn", "")))
        for d in devices
        if d.get("id") or d.get("sn") or d.get("device_sn")
    ]

    if not device_sns:
        _LOGGER.warning("No Navimow devices found on this account")

    # Create a coordinator per discovered device
    coordinators: dict[str, NavimowCoordinator] = {}

    for device_sn in device_sns:
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
    }
    if log_filter:
        hass.data[DOMAIN][entry.entry_id]["log_filter"] = log_filter

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
