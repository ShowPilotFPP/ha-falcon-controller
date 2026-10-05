"""Base entities for the Falcon Controller integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import X_ACTIVE, group_start, port_label
from .coordinator import FalconCoordinator


class FalconEntity(CoordinatorEntity[FalconCoordinator]):
    """An entity attached to the controller device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FalconCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_{key}"
        self._attr_device_info = coordinator.controller_device_info()


class FalconPortEntity(FalconEntity):
    """An entity for one output port (onboard or on a smart receiver)."""

    def __init__(
        self, coordinator: FalconCoordinator, port: int, receiver: int, key: str
    ) -> None:
        super().__init__(coordinator, f"port_{port}_{receiver}_{key}")
        self.port = port
        self.receiver = receiver
        self.label = port_label(port, receiver)
        self._attr_translation_placeholders = {"port": self.label}
        if receiver:
            self._attr_device_info = coordinator.receiver_device_info(
                group_start(port), receiver
            )

    @property
    def port_entry(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.ports.get((self.port, self.receiver))

    @property
    def available(self) -> bool:
        # Ports on an offline receiver stay available (fuse reads "unknown")
        # so the dashboard keeps their labels; switches are stricter.
        return super().available and self.port_entry is not None

    @property
    def is_active(self) -> bool:
        entry = self.port_entry
        return entry is not None and entry.get("X") == X_ACTIVE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "port_label": self.label,
            "port_index": self.port,
            "receiver": self.receiver,
        }


def should_create_port(key: tuple[int, int], entry: dict[str, Any]) -> bool:
    """Decide whether a CQ entry is a real port worth exposing.

    Smart receiver ports are always exposed (even when the receiver is
    offline, so they show as unavailable). Local ports are exposed once they
    report as active; unused differential outputs report X=0 and are skipped.
    """
    _, receiver = key
    return receiver > 0 or entry.get("X") == X_ACTIVE
