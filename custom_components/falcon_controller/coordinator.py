"""Data coordinator for the Falcon Controller integration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FalconClient, FalconError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, receiver_label

_LOGGER = logging.getLogger(__name__)

type FalconConfigEntry = ConfigEntry[FalconCoordinator]


@dataclass
class FalconData:
    """One poll's worth of controller data."""

    status: dict[str, Any] = field(default_factory=dict)
    # (0-based port, receiver) -> raw CQ entry
    ports: dict[tuple[int, int], dict[str, Any]] = field(default_factory=dict)


class FalconCoordinator(DataUpdateCoordinator[FalconData]):
    """Poll one Falcon controller."""

    config_entry: FalconConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: FalconConfigEntry, client: FalconClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.device_uid = entry.unique_id or entry.entry_id
        self.last_seen: datetime | None = None

    async def _async_update_data(self) -> FalconData:
        try:
            status = await self.client.get_status()
            entries = await self.client.get_ports()
        except FalconError as err:
            raise UpdateFailed(str(err)) from err

        ports: dict[tuple[int, int], dict[str, Any]] = {}
        for entry in entries:
            try:
                key = (int(entry["p"]), int(entry["r"]))
            except (KeyError, TypeError, ValueError):
                continue
            ports[key] = entry
        self.last_seen = dt_util.utcnow()
        return FalconData(status=status, ports=ports)

    async def async_command(
        self, func: Callable[..., Awaitable[None]], *args: Any
    ) -> None:
        """Send a command, then refresh so entities reflect the result."""
        try:
            await func(*args)
        except FalconError as err:
            raise HomeAssistantError(f"Falcon controller command failed: {err}") from err
        # Give the controller a moment to apply the change before re-reading.
        await asyncio.sleep(1)
        await self.async_request_refresh()

    @property
    def board_type(self) -> int | None:
        try:
            return int(self.data.status["BR"]) if self.data else None
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def model(self) -> str:
        """Model string the way the controller's UI builds it (165 -> F16V5)."""
        board = self.board_type
        if board in (165, 485):
            return f"F{board // 10}V5"
        if board:
            return f"F{board}V5"
        return "Falcon controller"

    @property
    def controller_name(self) -> str:
        name = self.data.status.get("N") if self.data else None
        return str(name) if name else f"Falcon {self.client.host}"

    def controller_device_info(self) -> DeviceInfo:
        status = self.data.status if self.data else {}
        info = DeviceInfo(
            identifiers={(DOMAIN, self.device_uid)},
            name=self.controller_name,
            manufacturer="Pixel Controller",
            model=self.model,
            configuration_url=f"http://{self.client.host}/",
        )
        if status.get("FW") is not None:
            info["sw_version"] = str(status["FW"])
        if status.get("C"):
            info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(str(status["C"])))}
        return info

    def receiver_device_info(self, group: int, receiver: int) -> DeviceInfo:
        label = receiver_label(group, receiver)
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.device_uid}_rx_{group}_{receiver}")},
            name=f"{self.controller_name} Receiver {label}",
            manufacturer="Pixel Controller",
            model="Smart receiver",
            via_device=(DOMAIN, self.device_uid),
        )
