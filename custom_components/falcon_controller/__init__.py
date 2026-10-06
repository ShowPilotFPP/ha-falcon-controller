"""The Falcon Controller integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import FalconClient
from .const import DOMAIN
from .coordinator import FalconConfigEntry, FalconCoordinator
from .frontend import async_register_frontend, async_remove_resource

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard strategy and make sure dashboards load it."""
    await async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FalconConfigEntry) -> bool:
    client = FalconClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    coordinator = FalconCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_register_controller()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FalconConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: FalconConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: FalconConfigEntry) -> None:
    """Clean up the dashboard resource when the last controller is removed."""
    if not hass.config_entries.async_entries(DOMAIN):
        await async_remove_resource(hass)
