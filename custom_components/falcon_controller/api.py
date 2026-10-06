"""Minimal client for the Falcon V5 controller's JSON API.

This is the same undocumented API the controller's own web UI uses: every
request is a POST to /api with a body of the form
{"T": "Q"|"S", "M": <command>, "B": <page>, "E": 0, "I": 0, "P": {...}}.
Responses may be split across pages; "F": 1 marks the final page.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

MAX_PAGES = 20


class FalconError(Exception):
    """Base error for the Falcon API."""


class FalconConnectionError(FalconError):
    """The controller could not be reached or did not answer."""


class FalconClient:
    """Talk to one Falcon controller."""

    def __init__(
        self, host: str, session: aiohttp.ClientSession, timeout: float = 10
    ) -> None:
        self.host = host
        self._session = session
        self._url = f"http://{host}/api"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        # The controller handles one request at a time; its own UI queues
        # requests, so do the same.
        self._lock = asyncio.Lock()

    async def _send(
        self, kind: str, method: str, batch: int = 0, params: dict | None = None
    ) -> dict[str, Any]:
        body = {"T": kind, "M": method, "B": batch, "E": 0, "I": 0, "P": params or {}}
        async with self._lock:
            for attempt in range(2):
                try:
                    # The controller's web server drops idle keep-alive
                    # connections, so ask for a fresh one every time.
                    async with self._session.post(
                        self._url,
                        json=body,
                        timeout=self._timeout,
                        headers={"Connection": "close"},
                    ) as resp:
                        resp.raise_for_status()
                        data = await resp.json(content_type=None)
                    break
                except (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as err:
                    if attempt == 0:
                        _LOGGER.debug("%s to %s: %s, retrying", method, self.host, err)
                        await asyncio.sleep(0.25)
                        continue
                    raise FalconConnectionError(
                        f"{method} request to {self.host} failed: {err}"
                    ) from err
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                    raise FalconConnectionError(
                        f"{method} request to {self.host} failed: {err}"
                    ) from err
        if not isinstance(data, dict):
            raise FalconError(f"Unexpected {method} response from {self.host}")
        code = data.get("R", 200)
        if code != 200:
            raise FalconError(f"{method} request to {self.host} returned R={code}")
        return data

    async def _query_pages(self, method: str) -> list[dict[str, Any]]:
        """Run a query and return the P payload of every page."""
        pages: list[dict[str, Any]] = []
        batch = 0
        while batch < MAX_PAGES:
            data = await self._send("Q", method, batch)
            payload = data.get("P")
            pages.append(payload if isinstance(payload, dict) else {})
            if data.get("F", 1) == 1:
                return pages
            batch = int(data.get("B", batch)) + 1
        _LOGGER.warning("%s response from %s exceeded %s pages", method, self.host, MAX_PAGES)
        return pages

    async def get_status(self) -> dict[str, Any]:
        """Return the merged status payload (name, firmware, temps, MAC...)."""
        merged: dict[str, Any] = {}
        for page in await self._query_pages("ST"):
            merged.update(page)
        return merged

    async def get_ports(self) -> list[dict[str, Any]]:
        """Return every port entry (current, fuse state) across all pages."""
        entries: list[dict[str, Any]] = []
        for page in await self._query_pages("CQ"):
            entries.extend(e for e in page.get("A", []) if isinstance(e, dict))
        return entries

    async def toggle_fuse(self, port: int, receiver: int) -> None:
        """Toggle one port's e-fuse (port is 0-based, receiver 0 = local)."""
        await self._send("S", "TF", params={"P": port, "R": receiver})

    async def reset_fuses(self) -> None:
        """Reset every e-fuse on the controller."""
        await self._send("S", "FR")

    async def set_all_fuses(self, on: bool) -> None:
        """Turn every e-fuse on or off."""
        await self._send("S", "FT", params={"T": 1 if on else 0})
