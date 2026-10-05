"""Config flow for the Falcon Controller integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .api import FalconClient, FalconConnectionError, FalconError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class FalconConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Falcon controller by IP or hostname."""

    VERSION = 1

    async def _probe(self, host: str) -> tuple[dict[str, Any] | None, str | None]:
        client = FalconClient(host, async_get_clientsession(self.hass))
        try:
            status = await client.get_status()
            await client.get_ports()
        except FalconConnectionError:
            return None, "cannot_connect"
        except FalconError:
            return None, "invalid_response"
        except Exception:
            _LOGGER.exception("Unexpected error talking to Falcon controller at %s", host)
            return None, "unknown"
        return status, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            status, error = await self._probe(host)
            if error:
                errors["base"] = error
            else:
                mac = status.get("C")
                await self.async_set_unique_id(format_mac(str(mac)) if mac else host)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=str(status.get("N") or f"Falcon {host}"),
                    data={CONF_HOST: host},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the controller's address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            status, error = await self._probe(host)
            if error:
                errors["base"] = error
            else:
                mac = status.get("C")
                if mac and entry.unique_id and format_mac(str(mac)) != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FalconOptionsFlow()


class FalconOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    )
                }
            ),
        )
