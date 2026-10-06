"""Serve and register the dashboard strategy script."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import FRONTEND_SCRIPT, FRONTEND_URL_BASE, VERSION

_LOGGER = logging.getLogger(__name__)

SCRIPT_PATH = f"{FRONTEND_URL_BASE}/{FRONTEND_SCRIPT}"
SCRIPT_URL = f"{SCRIPT_PATH}?v={VERSION}"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the strategy script and make sure dashboards load it."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL_BASE, str(Path(__file__).parent / "frontend"), True)]
    )
    # Loaded only as a dashboard resource. Loading it as an early "extra"
    # script too made it register before the companion app's custom-element
    # compatibility layer was installed, so Home Assistant never saw it.
    await async_ensure_resource(hass)


def _resources(hass: HomeAssistant) -> Any | None:
    """Return the Lovelace resource collection, across Home Assistant versions."""
    data = hass.data.get("lovelace")
    if data is None:
        return None
    if isinstance(data, dict):
        return data.get("resources")
    return getattr(data, "resources", None)


def _ours(item: dict) -> bool:
    return str(item.get("url", "")).split("?")[0] == SCRIPT_PATH


async def async_ensure_resource(hass: HomeAssistant) -> None:
    """Add the strategy script as a dashboard resource, or update its version."""
    resources = _resources(hass)
    if resources is None or not hasattr(resources, "async_create_item"):
        # Dashboards in YAML mode: resources can't be changed from code.
        _LOGGER.info(
            "Dashboards are in YAML mode; add %s as a JavaScript module resource "
            "to use the Falcon Controller dashboard",
            SCRIPT_URL,
        )
        return
    try:
        await resources.async_get_info()  # loads the collection if needed
        found = False
        for item in list(resources.async_items()):
            if not _ours(item):
                continue
            if found:
                # Duplicate entry, e.g. one added by hand: keep just one.
                await resources.async_delete_item(item["id"])
                continue
            found = True
            if item.get("url") != SCRIPT_URL:
                await resources.async_update_item(item["id"], {"url": SCRIPT_URL})
        if not found:
            await resources.async_create_item({"res_type": "module", "url": SCRIPT_URL})
    except Exception:  # never block setup over a dashboard convenience
        _LOGGER.exception("Could not register the Falcon Controller dashboard resource")


async def async_remove_resource(hass: HomeAssistant) -> None:
    """Remove the dashboard resource (when the integration is removed)."""
    resources = _resources(hass)
    if resources is None or not hasattr(resources, "async_delete_item"):
        return
    try:
        await resources.async_get_info()
        for item in list(resources.async_items()):
            if _ours(item):
                await resources.async_delete_item(item["id"])
    except Exception:
        _LOGGER.exception("Could not remove the Falcon Controller dashboard resource")
