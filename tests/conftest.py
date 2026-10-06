"""Fixtures: a fake Falcon F16V5 that answers the /api calls."""

from __future__ import annotations

import copy
import json
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)
from yarl import URL

HOST = "192.168.1.100"
URL_API = f"http://{HOST}/api"


def _real_ports() -> list[dict]:
    """The CQ response captured from a real F16V5 (all fuses idle-off)."""
    ports = [{"p": p, "r": 0, "i": -1, "pc": -1, "a": 1, "f": 1, "X": 1} for p in range(16)]
    for p in range(16, 20):
        ports.append({"p": p, "r": 1, "i": 0, "pc": -1, "a": 0, "f": 1, "X": 1})
        ports.append({"p": p, "r": 2, "i": -1, "pc": -1, "a": 0, "f": -1, "X": 0})
    ports += [{"p": p, "r": 0, "i": -1, "pc": -1, "a": 0, "f": -1, "X": 0} for p in range(20, 32)]
    return ports


class FakeFalcon:
    def __init__(self) -> None:
        self.ports = _real_ports()
        self.status = {
            "N": "F16V5",
            "BR": 165,
            "FW": "38",
            "C": "00:1E:C0:AA:BB:CC",
            "T1": 312,
            "T2": 298,
            "PT": 455,
            "V1": 121,
            "V2": 120,
        }
        self.online = True
        self.page_size = 100  # entries per CQ page
        self.commands: list[tuple[str, dict]] = []
        self.drop_next = 0  # simulate the controller closing the connection

    def entry(self, port: int, receiver: int) -> dict:
        return next(e for e in self.ports if e["p"] == port and e["r"] == receiver)

    async def handle(self, method, url, data):
        if not self.online:
            from aiohttp import ClientConnectionError

            raise ClientConnectionError("controller offline")
        if self.drop_next:
            self.drop_next -= 1
            from aiohttp import ServerDisconnectedError

            raise ServerDisconnectedError()
        body = data if isinstance(data, dict) else json.loads(data)
        kind, cmd, batch = body["T"], body["M"], body["B"]
        resp = {"R": 200, "T": kind, "M": cmd, "B": batch, "F": 1, "RB": 0, "P": {}}
        if cmd == "ST":
            resp["P"] = copy.deepcopy(self.status)
        elif cmd == "CQ":
            start = batch * self.page_size
            chunk = self.ports[start : start + self.page_size]
            resp["P"] = {"A": copy.deepcopy(chunk)}
            resp["F"] = 1 if start + self.page_size >= len(self.ports) else 0
        elif cmd == "TF":
            self.commands.append((cmd, body["P"]))
            e = self.entry(body["P"]["P"], body["P"]["R"])
            e["f"] = 1 if e["f"] == 0 else 0
        elif cmd == "FR":
            self.commands.append((cmd, body["P"]))
            for e in self.ports:
                if e["f"] == 2:
                    e["f"] = 0
        elif cmd == "FT":
            self.commands.append((cmd, body["P"]))
            for e in self.ports:
                if e["f"] in (0, 1, 2):
                    e["f"] = 0 if body["P"]["T"] else 1
        return AiohttpClientMockResponse(method, URL(url), json=resp)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_command_delay():
    with patch(
        "custom_components.falcon_controller.coordinator.asyncio.sleep",
        return_value=None,
    ):
        yield


@pytest.fixture(autouse=True)
def no_frontend(hass):
    """Skip serving the strategy JS (needs the full frontend package)."""
    hass.config.components.update({"frontend", "http", "lovelace"})
    with patch(
        "custom_components.falcon_controller.async_setup", return_value=True
    ):
        yield


def make_f48(fake: FakeFalcon) -> None:
    """Turn the fake into an F48V5: 12 differential chains, no onboard ports.

    Chain 1 has smart receivers A (online) and B (offline); the rest are idle.
    Single temperature/voltage sensor, so T2/V2 read as junk.
    """
    fake.status.update({"N": "F48V5", "BR": 485, "T2": 0, "V2": 0})
    fake.ports = []
    for p in range(48):
        if p < 4:
            fake.ports.append({"p": p, "r": 1, "i": 0, "pc": -1, "a": 120, "f": 0, "X": 1})
            fake.ports.append({"p": p, "r": 2, "i": -1, "pc": -1, "a": 0, "f": -1, "X": 0})
        else:
            fake.ports.append({"p": p, "r": 0, "i": -1, "pc": -1, "a": 0, "f": -1, "X": 0})


@pytest.fixture
def falcon(aioclient_mock) -> FakeFalcon:
    fake = FakeFalcon()
    aioclient_mock.post(URL_API, side_effect=fake.handle)
    return fake
