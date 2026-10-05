"""The Falcon Controller integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import FalconClient
from .const import DOMAIN, FRONTEND_SCRIPT, FRONTEND_URL_BASE, VERSION
from .coordinator import FalconConfigEntry, FalconCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard strategy and load it in the frontend."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_URL_BASE, str(Path(__file__).parent / "frontend"), True
            )
        ]
    )
    add_extra_js_url(hass, f"{FRONTEND_URL_BASE}/{FRONTEND_SCRIPT}?v={VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FalconConfigEntry) -> bool:
    client = FalconClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    coordinator = FalconCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FalconConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: FalconConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
