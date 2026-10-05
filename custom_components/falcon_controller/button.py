"""Controller-wide fuse buttons for the Falcon Controller integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import FalconClient
from .const import FUSE_STATES
from .coordinator import FalconConfigEntry, FalconCoordinator
from .entity import FalconEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class FalconButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[FalconClient], Awaitable[None]]


BUTTONS: tuple[FalconButtonDescription, ...] = (
    FalconButtonDescription(
        key="reset_fuses",
        translation_key="reset_fuses",
        press_fn=lambda client: client.reset_fuses(),
    ),
    FalconButtonDescription(
        key="all_fuses_on",
        translation_key="all_fuses_on",
        press_fn=lambda client: client.set_all_fuses(True),
    ),
    FalconButtonDescription(
        key="all_fuses_off",
        translation_key="all_fuses_off",
        press_fn=lambda client: client.set_all_fuses(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FalconConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(FalconButton(coordinator, desc) for desc in BUTTONS)


class FalconButton(FalconEntity, ButtonEntity):
    entity_description: FalconButtonDescription

    def __init__(
        self, coordinator: FalconCoordinator, description: FalconButtonDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        # In V4 receiver mode there are no e-fuses to control (the
        # controller's own UI disables these buttons).
        ports = self.coordinator.data.ports if self.coordinator.data else {}
        all_v4 = bool(ports) and all(
            FUSE_STATES.get(e.get("f")) == "v4" for e in ports.values() if e.get("X") == 1
        ) and any(e.get("X") == 1 for e in ports.values())
        return super().available and not all_v4

    async def async_press(self) -> None:
        client = self.coordinator.client
        await self.coordinator.async_command(
            lambda: self.entity_description.press_fn(client)
        )
