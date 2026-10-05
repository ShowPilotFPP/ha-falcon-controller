![Falcon Controller icon](https://raw.githubusercontent.com/ShowPilotFPP/ha-falcon-controller/main/custom_components/falcon_controller/brand/icon.png)

# Falcon Controller for Home Assistant

Monitor and control the e-fuses on Falcon V5 pixel controllers (F16V5 and family) from Home Assistant, including ports on smart receivers. Comes with a dashboard view that builds itself from whatever is connected.

> **Unofficial.** This integration uses the same local JSON API the controller's own web UI uses. That API isn't documented by Falcon and could change with a firmware update.

## Supported controllers

| Controller | Status |
|---|---|
| F16V5 | Tested on hardware (firmware v38): 16 onboard ports + 4 differential chains |
| F48V5 | Supported per firmware v38 analysis (same API): 12 differential chains, no onboard ports. Hardware reports welcome. |

Smart receivers on any differential chain are supported. V4-mode receivers have no e-fuses, so their fuse controls are unavailable.

## Features

- **Per-port fuse state**: Good, Off, Blown, or Unknown, for every onboard port and every smart receiver port
- **Per-port current** in amps
- **Per-port fuse switches** to turn a port on or off
- **Controller-wide buttons**: reset all fuses, all fuses on, all fuses off
- **Fuse blown** problem sensor with a `blown_ports` attribute (e.g. `7, 18A`) for alerts
- **Online** and **Last seen** sensors that keep working while the controller is down
- **Smart receivers** appear as their own devices with a connectivity sensor, and new receivers are picked up automatically
- **Health sensors**: board temperature(s), processor temperature, input voltage(s) (diagnostic; the F48V5 has one of each)
- **Self-building dashboard**: one line of YAML gives you a full status page

## Installation

### HACS (custom repository)

1. In HACS, open the ⋮ menu → **Custom repositories**.
2. Add `https://github.com/ShowPilotFPP/ha-falcon-controller` with type **Integration**.
3. Install **Falcon Controller** and restart Home Assistant.

### Manual

Copy `custom_components/falcon_controller` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

**Settings → Devices & services → Add integration → Falcon Controller**, then enter the controller's IP address or hostname.

The polling interval (default 15 seconds) can be changed from the integration's **Configure** button. If the controller's IP changes, use **Reconfigure**.

## Dashboard

### As a view in an existing dashboard

Add a new view, open it with **Edit in YAML**, and replace its contents with:

```yaml
strategy:
  type: custom:falcon-controller
```

With more than one controller, the view shows all of them. To show just one, add its device ID:

```yaml
strategy:
  type: custom:falcon-controller
  device_id: 0123456789abcdef0123456789abcdef
```

### As a subview

To keep it off the tab bar and open it from a card on another page, add `subview: true` (and optionally where the back arrow should go):

```yaml
strategy:
  type: custom:falcon-controller
  subview: true
  back_path: /lovelace/home
```

Then link to the view's path from any card with a navigate action.

### As a whole dashboard

Create a new dashboard, open the raw configuration editor, and use:

```yaml
strategy:
  type: custom:falcon-controller
```

That creates one view per controller.

The page includes controller status, a warning card when a fuse blows, the global fuse buttons (each with a confirmation), a section of port tiles for the onboard ports and for each receiver, health sensors, and a current history graph. **Tap** a port to see details; **press and hold** to toggle its fuse (with a confirmation).

The page is generated when the dashboard loads, so new receivers show up after a refresh. To customize it, open the view's ⋮ menu → **Take control** to turn it into a normal editable view.

## Things to know

- **Off vs. Blown.** Controllers set to cut power when no data is being sent will report idle ports as **Off**. That's normal and doesn't trip the Fuse blown sensor; only **Blown** does.
- **Switches and power saving.** The controller only offers a fuse *toggle*, so switches check the current state before sending one. If the controller is set to turn ports off when idle, it may turn a port back off right after you switch it on outside of a show.
- **Offline receivers.** Ports on a receiver that isn't responding show fuse state **Unknown** and their switches become unavailable.
- **One request at a time.** The controller handles requests one at a time. Keep the polling interval reasonable during shows.

## Example: notify when a fuse blows

```yaml
alias: Falcon fuse blown alert
triggers:
  - trigger: state
    entity_id: binary_sensor.YOUR_CONTROLLER_fuse_blown
    to: "on"
actions:
  - action: notify.notify
    data:
      title: Falcon fuse blown
      message: >
        {% set p = state_attr('binary_sensor.YOUR_CONTROLLER_fuse_blown', 'blown_ports') %}
        {{ 'Ports ' ~ p ~ ' have' if ',' in p else 'Port ' ~ p ~ ' has' }} a blown fuse.
```

## Development

```bash
pip install pytest-homeassistant-custom-component==0.13.205 "pycares<4.9"
python -m pytest
```

Tests run against a simulated F16V5 built from a real controller's API responses.
