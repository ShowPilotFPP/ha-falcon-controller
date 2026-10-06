/*
 * Falcon Controller dashboard strategies.
 *
 * View strategy (add to any dashboard as a view):
 *   strategy:
 *     type: custom:falcon-controller
 *     device_id: <optional, limit to one controller>
 *     subview: true            <optional, hide from tabs; open via a navigate action>
 *     back_path: /lovelace/0   <optional, where the back arrow goes>
 *
 * Dashboard strategy (a whole dashboard, one view per controller):
 *   strategy:
 *     type: custom:falcon-controller
 *
 * Built only from entities that exist, so new receivers appear on their own.
 */

const DOMAIN = "falcon_controller";
const VERSION = "0.1.4";
console.info("Falcon Controller dashboard strategy " + VERSION + " loaded");
const natural = (a, b) => String(a).localeCompare(String(b), undefined, { numeric: true });

function deviceName(device) {
  return (device && (device.name_by_user || device.name)) || "Falcon";
}

/* Work out what an entity is. Prefers translation_key, falls back to attributes. */
function roleOf(entry, hass) {
  if (entry.translation_key) return entry.translation_key;
  const st = hass.states[entry.entity_id];
  const a = (st && st.attributes) || {};
  const domain = entry.entity_id.split(".")[0];
  if (domain === "switch" && a.port_label) return "port";
  if (domain === "sensor" && a.port_label) {
    return a.device_class === "current" ? "port_current" : "port_fuse";
  }
  if (domain === "binary_sensor") {
    if (a.receiver_label) return "receiver";
    if (a.device_class === "problem") return "fuse_blown";
    if (a.device_class === "connectivity") return "online";
  }
  if (domain === "sensor" && a.device_class === "timestamp") return "last_seen";
  const suffixes = {
    _reset_all_fuses: "reset_fuses",
    _all_fuses_on: "all_fuses_on",
    _all_fuses_off: "all_fuses_off",
    _temperature_1: "temperature_1",
    _temperature_2: "temperature_2",
    _processor_temperature: "processor_temperature",
    _voltage_1: "voltage_1",
    _voltage_2: "voltage_2",
  };
  for (const [suffix, role] of Object.entries(suffixes)) {
    if (entry.entity_id.endsWith(suffix)) return role;
  }
  return domain;
}

function collect(hass) {
  const entities = Object.values(hass.entities || {}).filter(
    (e) => e.platform === DOMAIN && !e.hidden
  );
  const items = entities.map((e) => ({
    ...e,
    role: roleOf(e, hass),
    attrs: (hass.states[e.entity_id] || {}).attributes || {},
  }));
  const devices = hass.devices || {};
  const controllers = Object.values(devices)
    .filter((d) => !d.via_device_id && items.some((i) => i.device_id === d.id))
    .sort((a, b) => natural(deviceName(a), deviceName(b)));
  return { items, devices, controllers };
}

function portTile(fuse, switchEntity) {
  const label = fuse.attrs.port_label ?? "?";
  const card = {
    type: "tile",
    entity: fuse.entity_id,
    name: `Port ${label}`,
    icon: "mdi:fuse",
    tap_action: { action: "more-info" },
    grid_options: { columns: 6 },
  };
  if (switchEntity) {
    card.hold_action = {
      action: "perform-action",
      perform_action: "switch.toggle",
      target: { entity_id: switchEntity.entity_id },
      confirmation: { text: `Toggle the fuse on port ${label}?` },
    };
  }
  return card;
}

function byPort(a, b) {
  return (a.attrs.port_index ?? 0) - (b.attrs.port_index ?? 0) ||
    (a.attrs.receiver ?? 0) - (b.attrs.receiver ?? 0);
}

function portSection(title, deviceItems) {
  const fuses = deviceItems.filter((i) => i.role === "port_fuse").sort(byPort);
  if (!fuses.length) return null;
  const switches = deviceItems.filter((i) => i.role === "port");
  const cards = [{ type: "heading", heading: title }];
  for (const fuse of fuses) {
    const swId = fuse.attrs.switch_entity_id;
    const sw = swId
      ? { entity_id: swId }
      : switches.find((s) => s.attrs.port_label === fuse.attrs.port_label);
    cards.push(portTile(fuse, sw));
  }
  return { type: "grid", cards };
}

function controllerSections(hass, ctrl, items, devices) {
  const name = deviceName(ctrl);
  const receiverDevices = Object.values(devices)
    .filter((d) => d.via_device_id === ctrl.id)
    .sort((a, b) => natural(deviceName(a), deviceName(b)));
  const deviceIds = new Set([ctrl.id, ...receiverDevices.map((d) => d.id)]);
  const mine = items.filter((i) => deviceIds.has(i.device_id));
  const own = mine.filter((i) => i.device_id === ctrl.id);
  const find = (role) => own.find((i) => i.role === role);

  const sections = [];

  // --- Status ---
  const status = [{ type: "heading", heading: name }];
  const blown = find("fuse_blown");
  if (blown) {
    status.push({
      type: "conditional",
      conditions: [{ condition: "state", entity: blown.entity_id, state: "on" }],
      card: {
        type: "markdown",
        content: `## \u26A0\uFE0F Fuse blown\nPort(s): **{{ state_attr('${blown.entity_id}', 'blown_ports') }}**`,
      },
    });
  }
  const half = { columns: 6 };
  const online = find("online");
  if (online) status.push({ type: "tile", entity: online.entity_id, name: "Controller", grid_options: half });
  if (blown) status.push({ type: "tile", entity: blown.entity_id, name: "Blown fuses", grid_options: half });
  mine
    .filter((i) => i.role === "receiver")
    .sort(byPort)
    .forEach((r) =>
      status.push({
        type: "tile",
        entity: r.entity_id,
        name: `Receiver ${r.attrs.receiver_label || ""}`.trim(),
        grid_options: half,
      })
    );
  const lastSeen = find("last_seen");
  if (lastSeen) status.push({ type: "tile", entity: lastSeen.entity_id, name: "Last seen", grid_options: half });

  const buttons = [
    ["reset_fuses", "Reset all", "mdi:restart", "Reset every fuse on the controller?"],
    ["all_fuses_on", "All on", "mdi:power-plug", "Turn ALL fuses on?"],
    ["all_fuses_off", "All off", "mdi:power-plug-off", "Turn ALL fuses off?"],
  ];
  for (const [role, label, icon, confirm] of buttons) {
    const b = find(role);
    if (!b) continue;
    status.push({
      type: "tile",
      entity: b.entity_id,
      name: label,
      icon,
      hide_state: true,
      grid_options: { columns: 4 },
      tap_action: {
        action: "perform-action",
        perform_action: "button.press",
        target: { entity_id: b.entity_id },
        confirmation: { text: confirm },
      },
    });
  }
  sections.push({ type: "grid", cards: status });

  // --- Ports: onboard, then one section per receiver ---
  // F16V5: onboard ports (+ plain differential ports). F48V5: differential only.
  const ownPorts = own.filter((i) => i.role === "port_fuse");
  const hasOnboard = ownPorts.some((i) => (i.attrs.port_index ?? 99) < 16) &&
    (ctrl.model || "").startsWith("F16");
  const onboard = portSection(hasOnboard ? "Onboard ports" : "Ports", own);
  if (onboard) sections.push(onboard);
  for (const rx of receiverDevices) {
    const rxItems = mine.filter((i) => i.device_id === rx.id);
    const rxSensor = rxItems.find((i) => i.role === "receiver");
    const title = rxSensor && rxSensor.attrs.receiver_label
      ? `Receiver ${rxSensor.attrs.receiver_label}`
      : deviceName(rx);
    const section = portSection(title, rxItems);
    if (section) sections.push(section);
  }

  // --- Health (temperatures / voltages) ---
  const health = own.filter((i) =>
    ["temperature_1", "temperature_2", "processor_temperature", "voltage_1", "voltage_2"].includes(i.role)
  );
  if (health.length) {
    sections.push({
      type: "grid",
      cards: [
        { type: "heading", heading: "Health" },
        ...health.map((h) => ({ type: "tile", entity: h.entity_id, grid_options: half })),
      ],
    });
  }

  // --- Current history for ports that are in use ---
  const currents = mine
    .filter((i) => i.role === "port_current")
    .filter((i) => {
      // Skip ports whose fuse state is unknown (e.g. receiver offline).
      const fuse = mine.find(
        (f) => f.role === "port_fuse" && f.device_id === i.device_id &&
          f.attrs.port_label === i.attrs.port_label
      );
      const st = fuse && hass.states[fuse.entity_id];
      return st && !["unknown", "unavailable"].includes(st.state);
    })
    .sort(byPort)
    .map((i) => ({ entity: i.entity_id, name: `Port ${i.attrs.port_label}` }));
  if (currents.length) {
    sections.push({
      type: "grid",
      cards: [
        { type: "heading", heading: "Port current" },
        { type: "history-graph", hours_to_show: 6, entities: currents },
      ],
    });
  }
  return sections;
}

function emptyView() {
  return {
    type: "sections",
    sections: [
      {
        type: "grid",
        cards: [
          {
            type: "markdown",
            content:
              "No Falcon controllers found. Add one under **Settings \u2192 Devices & services \u2192 Add integration \u2192 Falcon Controller**.",
          },
        ],
      },
    ],
  };
}

function errorView(err) {
  console.error("Falcon Controller strategy failed", err);
  const detail = String((err && (err.stack || err.message)) || err).slice(0, 1500);
  return {
    type: "sections",
    sections: [
      {
        type: "grid",
        cards: [
          {
            type: "markdown",
            content:
              "**Falcon Controller dashboard error** (v" + VERSION + ")\n\n" +
              "Please report this at github.com/ShowPilotFPP/ha-falcon-controller/issues\n\n" +
              "```\n" + detail + "\n```",
          },
        ],
      },
    ],
  };
}

class FalconControllerViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    try {
      return FalconControllerViewStrategy._generate(config || {}, hass);
    } catch (err) {
      return errorView(err);
    }
  }

  static _generate(config, hass) {
    const { items, devices, controllers } = collect(hass);
    const chosen = config.device_id
      ? controllers.filter((c) => c.id === config.device_id)
      : controllers;
    const view = chosen.length
      ? {
          type: "sections",
          max_columns: config.max_columns ?? 3,
          sections: chosen.flatMap((c) => controllerSections(hass, c, items, devices)),
        }
      : emptyView();
    if (config.subview) view.subview = true;
    if (config.back_path) view.back_path = config.back_path;
    return view;
  }
}

class FalconControllerDashboardStrategy extends HTMLElement {
  static async generate(config, hass) {
    try {
      return FalconControllerDashboardStrategy._generate(config || {}, hass);
    } catch (err) {
      return { views: [{ title: "Falcon", ...errorView(err) }] };
    }
  }

  static _generate(config, hass) {
    const { controllers } = collect(hass);
    if (!controllers.length) return { views: [{ title: "Falcon", ...emptyView() }] };
    return {
      title: "Falcon",
      views: controllers.map((c) => ({
        title: deviceName(c),
        path: deviceName(c).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || c.id,
        icon: "mdi:string-lights",
        strategy: { type: "custom:falcon-controller", device_id: c.id },
      })),
    };
  }
}

if (!customElements.get("ll-strategy-view-falcon-controller")) {
  customElements.define("ll-strategy-view-falcon-controller", FalconControllerViewStrategy);
}
if (!customElements.get("ll-strategy-dashboard-falcon-controller")) {
  customElements.define("ll-strategy-dashboard-falcon-controller", FalconControllerDashboardStrategy);
}

// Exposed for testing outside the browser.
if (typeof module !== "undefined") {
  module.exports = { FalconControllerViewStrategy, FalconControllerDashboardStrategy };
}
