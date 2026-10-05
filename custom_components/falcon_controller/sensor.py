"""Sensors for the Falcon Controller integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DUAL_SENSOR_BOARDS, FUSE_OPTIONS, FUSE_STATES
from .coordinator import FalconConfigEntry, FalconCoordinator
from .entity import FalconEntity, FalconPortEntity, should_create_port

PARALLEL_UPDATES = 0


def _tenths_temp(value: Any) -> float | None:
    try:
        temp = float(value) / 10
    except (TypeError, ValueError):
        return None
    # The controller reports nonsense values for absent sensors.
    return temp if -40 <= temp <= 150 else None


def _tenths(value: Any) -> float | None:
    try:
        return round(float(value) / 10, 1)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, kw_only=True)
class FalconStatusSensorDescription(SensorEntityDescription):
    """A sensor read from the status (ST) response."""

    status_key: str
    value_fn: Callable[[Any], float | None]
    dual_only: bool = False


STATUS_SENSORS: tuple[FalconStatusSensorDescription, ...] = (
    FalconStatusSensorDescription(
        key="temperature_1",
        translation_key="temperature_1",
        status_key="T1",
        value_fn=_tenths_temp,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FalconStatusSensorDescription(
        key="temperature_2",
        translation_key="temperature_2",
        status_key="T2",
        dual_only=True,
        value_fn=_tenths_temp,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FalconStatusSensorDescription(
        key="processor_temperature",
        translation_key="processor_temperature",
        status_key="PT",
        value_fn=_tenths_temp,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FalconStatusSensorDescription(
        key="voltage_1",
        translation_key="voltage_1",
        status_key="V1",
        value_fn=_tenths,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FalconStatusSensorDescription(
        key="voltage_2",
        translation_key="voltage_2",
        status_key="V2",
        dual_only=True,
        value_fn=_tenths,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FalconConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    status = coordinator.data.status

    entities: list[SensorEntity] = [FalconLastSeenSensor(coordinator)]
    board = coordinator.board_type
    entities.extend(
        FalconStatusSensor(coordinator, desc)
        for desc in STATUS_SENSORS
        if desc.status_key in status
        and not (desc.dual_only and board is not None and board not in DUAL_SENSOR_BOARDS)
    )
    async_add_entities(entities)

    known: set[tuple[int, int]] = set()

    @callback
    def _discover_ports() -> None:
        new: list[SensorEntity] = []
        for key, port_entry in coordinator.data.ports.items():
            if key in known or not should_create_port(key, port_entry):
                continue
            known.add(key)
            new.append(FalconFuseSensor(coordinator, *key))
            new.append(FalconCurrentSensor(coordinator, *key))
        if new:
            async_add_entities(new)

    _discover_ports()
    entry.async_on_unload(coordinator.async_add_listener(_discover_ports))


class FalconFuseSensor(FalconPortEntity, SensorEntity):
    """State of one port's e-fuse: good / off / blown / unknown."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = FUSE_OPTIONS
    _attr_translation_key = "port_fuse"

    def __init__(self, coordinator: FalconCoordinator, port: int, receiver: int) -> None:
        super().__init__(coordinator, port, receiver, "fuse")

    @property
    def native_value(self) -> str | None:
        entry = self.port_entry
        if entry is None:
            return None
        if not self.is_active:
            return "unknown"
        return FUSE_STATES.get(entry.get("f"), "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        # Lets the dashboard strategy pair each fuse tile with its switch.
        switch_id = er.async_get(self.hass).async_get_entity_id(
            "switch",
            DOMAIN,
            f"{self.coordinator.device_uid}_port_{self.port}_{self.receiver}_switch",
        )
        if switch_id:
            attrs["switch_entity_id"] = switch_id
        return attrs


class FalconCurrentSensor(FalconPortEntity, SensorEntity):
    """Current drawn by one port."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_translation_key = "port_current"

    def __init__(self, coordinator: FalconCoordinator, port: int, receiver: int) -> None:
        super().__init__(coordinator, port, receiver, "current")

    @property
    def native_value(self) -> float | None:
        entry = self.port_entry
        if entry is None:
            return None
        try:
            return float(entry.get("a", 0)) / 1000
        except (TypeError, ValueError):
            return None


class FalconStatusSensor(FalconEntity, SensorEntity):
    """A temperature or voltage from the status response."""

    entity_description: FalconStatusSensorDescription

    def __init__(
        self, coordinator: FalconCoordinator, description: FalconStatusSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(
            self.coordinator.data.status.get(self.entity_description.status_key)
        )


class FalconLastSeenSensor(FalconEntity, SensorEntity):
    """When the controller last answered a poll. Stays available when offline."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_seen"

    def __init__(self, coordinator: FalconCoordinator) -> None:
        super().__init__(coordinator, "last_seen")

    @property
    def available(self) -> bool:
        return self.coordinator.last_seen is not None

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_seen
