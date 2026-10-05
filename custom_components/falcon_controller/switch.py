"""Per-port e-fuse switches for the Falcon Controller integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FUSE_STATES
from .coordinator import FalconConfigEntry, FalconCoordinator
from .entity import FalconPortEntity, should_create_port

PARALLEL_UPDATES = 1

# A switch only makes sense when the controller reports a definite state.
CONTROLLABLE = {"good", "off", "blown"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FalconConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[tuple[int, int]] = set()

    @callback
    def _discover_ports() -> None:
        new = []
        for key, port_entry in coordinator.data.ports.items():
            if key in known or not should_create_port(key, port_entry):
                continue
            known.add(key)
            new.append(FalconFuseSwitch(coordinator, *key))
        if new:
            async_add_entities(new)

    _discover_ports()
    entry.async_on_unload(coordinator.async_add_listener(_discover_ports))


class FalconFuseSwitch(FalconPortEntity, SwitchEntity):
    """Turn one port's e-fuse on or off.

    The controller only offers a toggle, so the switch checks the current
    state first. Note: controllers set to cut power when no data is being
    sent may switch a port back off on their own.
    """

    _attr_translation_key = "port"

    def __init__(self, coordinator: FalconCoordinator, port: int, receiver: int) -> None:
        super().__init__(coordinator, port, receiver, "switch")

    @property
    def _fuse_state(self) -> str | None:
        entry = self.port_entry
        return FUSE_STATES.get(entry.get("f")) if entry else None

    @property
    def available(self) -> bool:
        return (
            super().available and self.is_active and self._fuse_state in CONTROLLABLE
        )

    @property
    def is_on(self) -> bool:
        return self._fuse_state == "good"

    async def _toggle(self) -> None:
        if self._fuse_state not in CONTROLLABLE:
            raise HomeAssistantError(f"Port {self.label} is not controllable right now")
        await self.coordinator.async_command(
            self.coordinator.client.toggle_fuse, self.port, self.receiver
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self.is_on:
            await self._toggle()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on:
            await self._toggle()
