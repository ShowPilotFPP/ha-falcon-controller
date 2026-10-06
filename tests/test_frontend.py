"""Dashboard resource registration, against Home Assistant's real resource store."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.falcon_controller import frontend
from custom_components.falcon_controller.frontend import (
    SCRIPT_PATH,
    SCRIPT_URL,
    async_ensure_resource,
    async_remove_resource,
)


class _NoLegacyConfig:
    async def async_load(self, force):
        raise HomeAssistantError


async def _storage(hass: HomeAssistant) -> ResourceStorageCollection:
    col = ResourceStorageCollection(hass, _NoLegacyConfig())
    hass.data["lovelace"] = {"resources": col}
    return col


def _ours(col) -> list[dict]:
    return [i for i in col.async_items() if i["url"].split("?")[0] == SCRIPT_PATH]


async def test_adds_resource_on_install(hass: HomeAssistant) -> None:
    col = await _storage(hass)
    await async_ensure_resource(hass)
    items = _ours(col)
    assert len(items) == 1
    assert items[0]["url"] == SCRIPT_URL and items[0]["type"] == "module"
    # Running again (every restart) doesn't duplicate it
    await async_ensure_resource(hass)
    assert len(_ours(col)) == 1


async def test_upgrades_hand_added_entry_and_removes_duplicates(hass: HomeAssistant) -> None:
    col = await _storage(hass)
    await col.async_get_info()
    await col.async_create_item({"res_type": "module", "url": f"{SCRIPT_PATH}?v=0.1.5"})
    await col.async_create_item({"res_type": "module", "url": SCRIPT_PATH})
    await col.async_create_item({"res_type": "module", "url": "/local/other-card.js"})
    await async_ensure_resource(hass)
    items = _ours(col)
    assert [i["url"] for i in items] == [SCRIPT_URL]
    # Other people's resources are left alone
    assert any(i["url"] == "/local/other-card.js" for i in col.async_items())


async def test_version_bump_updates_url(hass: HomeAssistant) -> None:
    col = await _storage(hass)
    await async_ensure_resource(hass)
    new_url = f"{SCRIPT_PATH}?v=9.9.9"
    with patch.object(frontend, "SCRIPT_URL", new_url):
        await async_ensure_resource(hass)
    assert [i["url"] for i in _ours(col)] == [new_url]


async def test_yaml_mode_is_left_alone(hass: HomeAssistant, caplog) -> None:
    hass.data["lovelace"] = {"resources": ResourceYAMLCollection([])}
    await async_ensure_resource(hass)
    assert "YAML mode" in caplog.text


async def test_newer_data_layout_and_removal(hass: HomeAssistant) -> None:
    col = ResourceStorageCollection(hass, _NoLegacyConfig())

    class LovelaceData:  # newer Home Assistant versions use an object
        resources = col

    hass.data["lovelace"] = LovelaceData()
    await async_ensure_resource(hass)
    assert len(_ours(col)) == 1
    await async_remove_resource(hass)
    assert _ours(col) == []
