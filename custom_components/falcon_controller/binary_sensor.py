"""Binary sensors for the Falcon Controller integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FUSE_STATES, X_ACTIVE, group_start, port_label, receiver_label
from .coordinator import FalconConfigEntry, FalconCoordinator
from .entity import FalconEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FalconConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [FalconOnlineSensor(coordinator), FalconFuseBlownSensor(coordinator)]
    )

    known: set[tuple[int, int]] = set()

    @callback
    def _discover_receivers() -> None:
        new = []
        for port, receiver in coordinator.data.ports:
            if receiver == 0:
                continue
            key = (group_start(port), receiver)
            if key not in known:
                known.add(key)
                new.append(FalconReceiverSensor(coordinator, *key))
        if new:
            async_add_entities(new)

    _discover_receivers()
    entry.async_on_unload(coordinator.async_add_listener(_discover_receivers))


class FalconOnlineSensor(FalconEntity, BinarySensorEntity):
    """Whether the controller is answering API polls. Never unavailable."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "online"

    def __init__(self, coordinator: FalconCoordinator) -> None:
        super().__init__(coordinator, "online")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class FalconFuseBlownSensor(FalconEntity, BinarySensorEntity):
    """On when any port reports a blown fuse (not when idle-off)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "fuse_blown"

    def __init__(self, coordinator: FalconCoordinator) -> None:
        super().__init__(coordinator, "fuse_blown")

    def _blown(self) -> list[str]:
        ports = self.coordinator.data.ports if self.coordinator.data else {}
        return [
            port_label(*key)
            for key, entry in sorted(ports.items())
            if FUSE_STATES.get(entry.get("f")) == "blown"
        ]

    @property
    def is_on(self) -> bool:
        return bool(self._blown())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        blown = self._blown()
        return {"blown_ports": ", ".join(blown), "blown_port_list": blown}


class FalconReceiverSensor(FalconEntity, BinarySensorEntity):
    """Whether a smart receiver is responding."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "receiver"

    def __init__(self, coordinator: FalconCoordinator, group: int, receiver: int) -> None:
        super().__init__(coordinator, f"receiver_{group}_{receiver}")
        self.group = group
        self.receiver = receiver
        self.label = receiver_label(group, receiver)
        self._attr_device_info = coordinator.receiver_device_info(group, receiver)

    @property
    def is_on(self) -> bool:
        ports = self.coordinator.data.ports if self.coordinator.data else {}
        return any(
            group_start(port) == self.group
            and receiver == self.receiver
            and entry.get("X") == X_ACTIVE
            for (port, receiver), entry in ports.items()
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "receiver_label": self.label,
            "port_index": self.group,
            "receiver": self.receiver,
        }
