"""End-to-end tests against the fake controller."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.falcon_controller.const import DOMAIN

from .conftest import HOST, FakeFalcon, make_f48


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: HOST}, unique_id="00:1e:c0:aa:bb:cc")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _poll(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=20))
    await hass.async_block_till_done()


async def test_config_flow(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    with patch(
        "custom_components.falcon_controller.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )
    assert result["type"] == "create_entry"
    assert result["title"] == "F16V5"
    assert result["result"].unique_id == "00:1e:c0:aa:bb:cc"


async def test_config_flow_cannot_connect(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    falcon.online = False
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_entities_match_real_controller(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    await _setup(hass)
    # Onboard ports idle-off
    assert hass.states.get("sensor.f16v5_port_1_fuse").state == "off"
    assert hass.states.get("switch.f16v5_port_1").state == STATE_OFF
    assert float(hass.states.get("sensor.f16v5_port_1_current").state) == 0.001
    # Receiver A responding, B configured but offline
    assert hass.states.get("sensor.f16v5_receiver_17a_port_17a_fuse").state == "off"
    assert hass.states.get("sensor.f16v5_receiver_17b_port_17b_fuse").state == "unknown"
    assert hass.states.get("switch.f16v5_receiver_17b_port_17b").state == STATE_UNAVAILABLE
    assert hass.states.get("binary_sensor.f16v5_receiver_17a_connected").state == STATE_ON
    assert hass.states.get("binary_sensor.f16v5_receiver_17b_connected").state == STATE_OFF
    # Unused differential ports are not created
    assert hass.states.get("sensor.f16v5_port_21_fuse") is None
    # Controller-level
    assert hass.states.get("binary_sensor.f16v5_online").state == STATE_ON
    assert hass.states.get("binary_sensor.f16v5_fuse_blown").state == STATE_OFF
    assert float(hass.states.get("sensor.f16v5_processor_temperature").state) == 45.5
    assert float(hass.states.get("sensor.f16v5_voltage_1").state) == 12.1

    ent_reg = er.async_get(hass)
    entities = [e for e in ent_reg.entities.values() if e.platform == DOMAIN]
    # 16 onboard + 8 receiver ports, x3 (fuse, current, switch)
    assert sum(e.domain == "switch" for e in entities) == 24
    dev_reg = dr.async_get(hass)
    controller = dev_reg.async_get_device(identifiers={(DOMAIN, "00:1e:c0:aa:bb:cc")})
    assert controller.sw_version == "38"
    assert controller.model == "F16V5"
    receivers = [d for d in dev_reg.devices.values() if d.via_device_id == controller.id]
    assert sorted(d.name for d in receivers) == ["F16V5 Receiver 17A", "F16V5 Receiver 17B"]


async def test_switch_toggles_only_when_needed(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.f16v5_port_1"}, blocking=True
    )
    await hass.async_block_till_done()
    assert falcon.commands == [("TF", {"P": 0, "R": 0})]
    assert hass.states.get("sensor.f16v5_port_1_fuse").state == "good"
    assert hass.states.get("switch.f16v5_port_1").state == STATE_ON
    # Already on: no second toggle
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.f16v5_port_1"}, blocking=True
    )
    assert len(falcon.commands) == 1
    # Receiver port uses its receiver number
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.f16v5_receiver_17a_port_18a"}, blocking=True
    )
    assert falcon.commands[-1] == ("TF", {"P": 17, "R": 1})


async def test_blown_fuse_and_reset(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    await _setup(hass)
    falcon.entry(6, 0)["f"] = 2
    falcon.entry(17, 1)["f"] = 2
    await _poll(hass)
    blown = hass.states.get("binary_sensor.f16v5_fuse_blown")
    assert blown.state == STATE_ON
    assert blown.attributes["blown_ports"] == "7, 18A"
    assert hass.states.get("sensor.f16v5_port_7_fuse").state == "blown"
    assert hass.states.get("switch.f16v5_port_7").state == STATE_OFF

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.f16v5_reset_all_fuses"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.f16v5_fuse_blown").state == STATE_OFF


async def test_offline_keeps_online_and_last_seen(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    await _setup(hass)
    seen = hass.states.get("sensor.f16v5_last_seen").state
    falcon.online = False
    await _poll(hass)
    assert hass.states.get("binary_sensor.f16v5_online").state == STATE_OFF
    assert hass.states.get("sensor.f16v5_last_seen").state == seen
    assert hass.states.get("switch.f16v5_port_1").state == STATE_UNAVAILABLE


async def test_pagination_and_new_receiver(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    falcon.page_size = 10  # force 4 pages
    await _setup(hass)
    assert hass.states.get("sensor.f16v5_receiver_17a_port_20a_fuse").state == "off"
    # A receiver C shows up on the second chain
    for p in range(20, 24):
        falcon.ports.append({"p": p, "r": 3, "i": 0, "pc": -1, "a": 250, "f": 0, "X": 1})
    await _poll(hass)
    assert hass.states.get("sensor.f16v5_receiver_21c_port_21c_fuse").state == "good"
    assert float(hass.states.get("sensor.f16v5_receiver_21c_port_21c_current").state) == 0.25
    assert hass.states.get("binary_sensor.f16v5_receiver_21c_connected").state == STATE_ON


async def test_f48v5_layout(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    make_f48(falcon)
    await _setup(hass)
    dev_reg = dr.async_get(hass)
    controller = dev_reg.async_get_device(identifiers={(DOMAIN, "00:1e:c0:aa:bb:cc")})
    assert controller.model == "F48V5"
    receivers = sorted(d.name for d in dev_reg.devices.values() if d.via_device_id == controller.id)
    assert receivers == ["F48V5 Receiver 1A", "F48V5 Receiver 1B"]
    assert hass.states.get("sensor.f48v5_receiver_1a_port_1a_fuse").state == "good"
    assert float(hass.states.get("sensor.f48v5_receiver_1a_port_4a_current").state) == 0.12
    assert hass.states.get("sensor.f48v5_receiver_1b_port_1b_fuse").state == "unknown"
    assert hass.states.get("binary_sensor.f48v5_receiver_1b_connected").state == STATE_OFF
    # Idle chains create nothing; the board's single temp/voltage only
    assert hass.states.get("sensor.f48v5_port_5_fuse") is None
    assert hass.states.get("sensor.f48v5_temperature_1") is not None
    assert hass.states.get("sensor.f48v5_temperature_2") is None
    assert hass.states.get("sensor.f48v5_voltage_2") is None
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.f48v5_receiver_1a_port_3a"}, blocking=True
    )
    assert falcon.commands[-1] == ("TF", {"P": 2, "R": 1})


async def test_v4_receivers_have_no_fuse_controls(hass: HomeAssistant, falcon: FakeFalcon) -> None:
    make_f48(falcon)
    for e in falcon.ports:
        if e["X"] == 1:
            e["f"] = 3
    await _setup(hass)
    assert hass.states.get("sensor.f48v5_receiver_1a_port_1a_fuse").state == "v4"
    assert hass.states.get("switch.f48v5_receiver_1a_port_1a").state == STATE_UNAVAILABLE
    assert hass.states.get("button.f48v5_reset_all_fuses").state == STATE_UNAVAILABLE
