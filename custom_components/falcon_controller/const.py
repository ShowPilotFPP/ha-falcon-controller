"""Constants for the Falcon Controller integration."""

from __future__ import annotations

DOMAIN = "falcon_controller"
VERSION = "0.1.7"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300

# Fuse codes reported by the controller ("f" field of the CQ response).
FUSE_STATES: dict[int, str] = {
    -1: "unknown",
    0: "good",
    1: "off",
    2: "blown",
    3: "v4",
}
FUSE_OPTIONS = ["good", "off", "blown", "unknown", "v4"]

# "X" field of a CQ entry: 1 = responding/active. 0 = configured but not
# responding (or an unused differential port). 2 = detected but unconfigured.
X_ACTIVE = 1

# Board types whose UI shows a second board temperature and voltage
# (F16V4 = 16, F16V5 = 165). Others, like the F48V5 (485), have only one.
DUAL_SENSOR_BOARDS = {16, 165}

FRONTEND_URL_BASE = "/falcon_controller_static"
FRONTEND_SCRIPT = "falcon-controller-strategy.js"


def port_label(port: int, receiver: int) -> str:
    """Return the label the Falcon UI uses, e.g. (0, 0) -> '1', (16, 2) -> '17B'."""
    return f"{port + 1}{chr(64 + receiver) if receiver else ''}"


def group_start(port: int) -> int:
    """Return the first (0-based) port of the 4-port group a port belongs to."""
    return (port // 4) * 4


def receiver_label(group: int, receiver: int) -> str:
    """Return a smart receiver's label, e.g. (16, 1) -> '17A'."""
    return port_label(group, receiver)
