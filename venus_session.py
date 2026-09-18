"""UI-independent device session for the Venus Pro configuration utility.

``VenusSession`` owns everything a front end needs that is not a widget:
device discovery and controller detection, reading and parsing the device
configuration, the staging manager and its transaction, hardware macros,
lighting, DPI, polling, factory reset, raw reports, profile export/import,
the battery-status query and the battery-colour LED controller, plus the
per-user JSON settings.  It sends exactly the reports the Qt Widgets window
sends; the QindaTK front end (``venus_qml_backend``) is a thin adapter on
top of it, and ``venus_gui`` can adopt it the same way.

Nothing here imports Qt.  Progress and message boxes are the caller's job:
operations return results or raise ``SessionError`` with a user-facing text.
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import device_driver as dd
import holtek_protocol as hp
import venus_protocol as vp
from staging_manager import StagingManager
from transaction_controller import TransactionController
from venus_macro_draft import HID_USAGE_TO_NAME, MacroDraft

Logger = Callable[[str], None]

APP_ID = "com.github.es00bac.venusprolinux"
CONFIG_DIR_NAME = "venus_pro_linux"

ARESON_ACTIONS = [
    "Keyboard Key", "Left Click", "Right Click", "Middle Click",
    "Forward", "Back", "Macro", "Fire Key", "Triple Click",
    "Media Key", "RGB Toggle", "Polling Rate Toggle",
    "DPI Control", "Disabled",
]
HOLTEK_ACTIONS = [
    "Keyboard Key", "Left Click", "Right Click", "Middle Click",
    "Forward", "Back", "DPI Control", "Fire Key",
    "Profile Switch", "Disabled",
]
MOUSE_ACTION_VALUES = {"Left Click": 0x01, "Right Click": 0x02,
                       "Middle Click": 0x04, "Back": 0x08, "Forward": 0x10}
MOUSE_VALUE_ACTIONS = {value: name for name, value in MOUSE_ACTION_VALUES.items()}

# Keys offered by the "special key" picker (those without a text glyph).
SPECIAL_KEY_NAMES = [name for name in (
    "F13", "F14", "F15", "F16", "F17", "F18", "F19", "F20", "F21", "F22",
    "F23", "F24", "PrintScreen", "ScrollLock", "Pause", "Insert", "Home",
    "PageUp", "Delete", "End", "PageDown", "NumLock", "Menu",
    "Left Shift", "Left Ctrl", "Left Alt", "Left GUI",
    "Right Shift", "Right Ctrl", "Right Alt", "Right GUI",
    "Keypad /", "Keypad *", "Keypad -", "Keypad +", "Keypad Enter",
    "Keypad .", "Keypad 0", "Keypad 1", "Keypad 2", "Keypad 3", "Keypad 4",
    "Keypad 5", "Keypad 6", "Keypad 7", "Keypad 8", "Keypad 9",
) if name in vp.HID_KEY_USAGE]

MACRO_REPEAT_MODES = [
    ("Run Once", vp.MACRO_REPEAT_ONCE),
    ("Repeat Count", vp.MACRO_REPEAT_COUNT),
    ("Repeat While Held", vp.MACRO_REPEAT_HOLD),
    ("Loop Until Toggle", vp.MACRO_REPEAT_TOGGLE),
]
DPI_FUNCTIONS_ARESON = [("DPI Loop", 0x01), ("DPI +", 0x02), ("DPI -", 0x03)]
DPI_FUNCTIONS_HOLTEK = [("DPI +", 0x02), ("DPI -", 0x03)]
RGB_MODES = [("Off", vp.RGB_MODE_OFF), ("Steady", vp.RGB_MODE_STEADY),
             ("Breathing", vp.RGB_MODE_BREATHING), ("Neon", vp.RGB_MODE_NEON)]
POLLING_RATES = sorted(vp.POLLING_RATE_PAYLOADS)
MACRO_SLOT_COUNT = 16

_DISPLAY_KEY_NAMES = {
    "Enter": "Return", "Escape": "Esc", "Delete": "Del", "Insert": "Ins",
    "PageUp": "PgUp", "PageDown": "PgDown", "Space": "Space",
}


class SessionError(RuntimeError):
    """An operation failed; ``str(exc)`` is the text to show the user."""


class NotSupported(SessionError):
    """The connected controller does not implement the operation."""


class DemoDevice(SessionError):
    """Raised for every hardware operation while running in demo mode."""


@dataclass
class RgbState:
    r: int = 255
    g: int = 0
    b: int = 255
    mode: int = vp.RGB_MODE_STEADY
    brightness: int = 100
    speed: int = vp.RGB_EFFECT_SPEED_DEFAULT

    def to_dict(self) -> dict[str, int]:
        return {"r": self.r, "g": self.g, "b": self.b, "mode": self.mode,
                "brightness": self.brightness, "speed": self.speed}

    @classmethod
    def from_dict(cls, data: dict) -> "RgbState":
        return cls(
            r=max(0, min(255, int(data.get("r", 255)))),
            g=max(0, min(255, int(data.get("g", 0)))),
            b=max(0, min(255, int(data.get("b", 255)))),
            mode=max(0, min(3, int(data.get("mode", vp.RGB_MODE_STEADY)))),
            brightness=max(0, min(255, int(data.get("brightness", 100)))),
            speed=max(0, min(255, int(data.get("speed", vp.RGB_EFFECT_SPEED_DEFAULT)))),
        )


@dataclass
class DpiStage:
    dpi: int
    raw: int = 0
    tweak: int = 0
    preset: bool = False


@dataclass
class DeviceConfig:
    """What a read returns: everything the pages describe, already decoded."""
    buttons: dict[str, dict] = field(default_factory=dict)
    dpi_stage_count: int | None = None
    dpi_stages: list[DpiStage] = field(default_factory=list)
    dpi_active_stage: int = 0
    dpi_colors: list[int] = field(default_factory=list)
    polling_rate: int | None = None
    rgb: RgbState | None = None
    holtek_profile: int | None = None


@dataclass
class ConnectResult:
    found: bool = False
    name: str = ""
    device_type: str = "venus_pro"
    access_error: str = ""
    note: str = ""
    read: DeviceConfig | None = None
    read_error: str = ""


@dataclass
class CommitResult:
    ok: bool
    error: str = ""
    partial: bool = False


def describe_binding(action: str, params: dict, device_type: str = "venus_pro") -> str:
    """One-line description of a binding, as shown in the button list."""
    if action == "Keyboard Key":
        hid_key = params.get("key", 0)
        modifier = params.get("mod", 0)
        key_name = HID_USAGE_TO_NAME.get(hid_key, f"0x{hid_key:02X}")
        display_key = _DISPLAY_KEY_NAMES.get(key_name, key_name)
        mods = []
        if modifier & vp.MODIFIER_CTRL:
            mods.append("Ctrl")
        if modifier & vp.MODIFIER_SHIFT:
            mods.append("Shift")
        if modifier & vp.MODIFIER_ALT:
            mods.append("Alt")
        if modifier & vp.MODIFIER_WIN:
            mods.append("Win")
        if mods:
            return f"Key: {display_key} ({'+'.join(mods)})"
        return f"Key: {display_key}"
    if action == "Macro":
        index = params.get("index", 1)
        mode_val = params.get("mode", 1)
        if mode_val == vp.MACRO_REPEAT_ONCE:
            mode_str = "Once"
        elif mode_val == vp.MACRO_REPEAT_HOLD:
            mode_str = "Hold"
        elif mode_val == vp.MACRO_REPEAT_TOGGLE:
            mode_str = "Toggle"
        else:
            mode_str = f"x{mode_val}"
        return f"Macro {index} ({mode_str})"
    if action == "DPI Control":
        func = params.get("func", 1)
        return f"DPI {({1: 'Loop', 2: 'Up', 3: 'Down'}).get(func, 'Unknown')}"
    if action == "Disabled":
        return "Disabled"
    if action == "Media Key":
        code = params.get("code", 0)
        name = next((k for k, v in vp.MEDIA_KEY_CODES.items() if v == code), "Unknown")
        return f"Media: {name}"
    if action in ("Fire Key", "Triple Click"):
        repeat = params.get("repeat", 3)
        if device_type == "holtek":
            return f"{action} (x{repeat})"
        return f"{action} ({params.get('delay', 40)}ms, x{repeat})"
    return action


def parse_areson_config(page0: bytes, page1: bytes, page2: bytes,
                        macro_names: dict[int, str] | None = None,
                        log: Logger | None = None) -> DeviceConfig:
    """Decode the Areson configuration block and keyboard definition pages.

    ``page0`` is the first 0xA0+ bytes of page 0; ``page1``/``page2`` are the
    256-byte keyboard-definition pages.  Pure: no device access.
    """
    macro_names = macro_names or {}
    log = log or (lambda _text: None)
    config = DeviceConfig()

    stage_count = page0[0x02]
    if 1 <= stage_count <= 5:
        config.dpi_stage_count = stage_count
    for offset in (0x0C, 0x10, 0x14, 0x18, 0x1C):
        value = page0[offset]
        closest_dpi, min_diff = 1000, 999
        for dpi, info in vp.DPI_PRESETS.items():
            if abs(info["value"] - value) < min_diff:
                min_diff = abs(info["value"] - value)
                closest_dpi = dpi
        exact = vp.DPI_PRESETS.get(closest_dpi, {}).get("value") == value
        config.dpi_stages.append(DpiStage(
            dpi=closest_dpi if exact else vp.value_to_dpi(value),
            raw=value, tweak=page0[offset + 3], preset=exact))

    config.polling_rate = vp.POLLING_CODE_TO_RATE.get(page0[0x00])

    brightness_b1 = page0[0x5A]
    brightness = (100 if brightness_b1 == 0xFF else
                  0 if brightness_b1 <= 1 else min(100, round(brightness_b1 / 3)))
    config.rgb = RgbState(
        r=page0[0x54], g=page0[0x55], b=page0[0x56],
        mode=vp.rgb_mode_from_hardware(page0[0x58]),
        brightness=brightness,
        speed=max(vp.RGB_EFFECT_SPEED_MIN,
                  min(vp.RGB_EFFECT_SPEED_MAX, page0[0x5C])))

    for button_key, profile in vp.BUTTON_PROFILES.items():
        offset = profile.apply_offset
        btype, d1, d2 = page0[offset], page0[offset + 1], page0[offset + 2]
        action, params = "Disabled", {}
        if btype == vp.BUTTON_TYPE_MOUSE:
            action = MOUSE_VALUE_ACTIONS.get(d1, f"Mouse Button (0x{d1:02X})")
        elif btype == vp.BUTTON_TYPE_KEYBOARD:
            definition_page = page1 if profile.code_hi == 0x01 else page2
            block = bytes(definition_page[profile.code_lo:profile.code_lo + 0x20])
            count = block[0] if block else 0
            needed = 1 + count * 3 + 1
            if count == 0 or needed > len(block):
                action = "Invalid Key Definition"
            else:
                if sum(block[:needed]) & 0xFF != 0x55:
                    log(f"  Warning: {button_key} key definition checksum is invalid")
                modifiers, keycode, consumer_usage = 0, None, None
                for event_index in range(count):
                    start = 1 + event_index * 3
                    status, code_lo, code_hi = block[start:start + 3]
                    if status == 0x80:
                        modifiers |= code_lo
                    elif status == 0x81 and keycode is None:
                        keycode = code_lo
                    elif status == 0x82 and consumer_usage is None:
                        consumer_usage = code_lo | (code_hi << 8)
                if consumer_usage is not None:
                    action, params = "Media Key", {"code": consumer_usage}
                elif keycode is not None:
                    action, params = "Keyboard Key", {"key": keycode, "mod": modifiers}
                else:
                    action = "Unknown Key Definition"
        elif btype == vp.BUTTON_TYPE_DPI_LEGACY:
            action, params = "DPI Control", {"func": d1}
        elif btype == vp.BUTTON_TYPE_MACRO:
            action = "Macro"
            params = {"index": d1 + 1, "mode": d2,
                      "count": d2 if 0x01 <= d2 <= 0xFD else 1,
                      "name": macro_names.get(d1 + 1, f"Macro {d1 + 1}")}
        elif btype == vp.BUTTON_TYPE_SPECIAL:
            action = "Triple Click" if d1 == 50 else "Fire Key"
            params = {"delay": d1, "repeat": d2}
        elif btype == vp.BUTTON_TYPE_POLL_RATE:
            action = "Polling Rate Toggle"
        elif btype == vp.BUTTON_TYPE_RGB_TOGGLE:
            action = "RGB Toggle"
        config.buttons[button_key] = {"action": action, "params": params}
    return config


def sorted_button_keys(profiles: dict) -> list[str]:
    return sorted(profiles.keys(), key=lambda k: int(k.split()[1]))


class VenusSession:
    """Device state and operations shared by every front end."""

    def __init__(self, log: Logger | None = None,
                 idle: Callable[[], None] | None = None,
                 config_dir: Path | None = None) -> None:
        self.log: Logger = log or (lambda _text: None)
        self.idle: Callable[[], None] = idle or (lambda: None)
        self.config_dir = config_dir or Path.home() / ".config" / CONFIG_DIR_NAME
        self.macro_config_file = self.config_dir / "macros.json"
        self.settings_file = self.config_dir / "settings.json"

        self.device_path: bytes | str | None = None
        self.device_infos: list[vp.DeviceInfo] = []
        self.device_info: vp.DeviceInfo | None = None
        self.device_type = "venus_pro"
        self.device_name = ""
        self.holtek_profile = 0
        self.holtek_dpi_colors: list[int] = []
        self.active_button_profiles: dict = vp.BUTTON_PROFILES
        self.button_assignments: dict[str, dict] = {}
        self.staging = StagingManager()
        self.demo = False

        self.macro_names: dict[int, str] = {}
        self.battery_led_enabled = False
        self.battery_led_restore: dict[str, int] | None = None
        self.last_battery_led_level: int | None = None
        self.config_errors: list[str] = []

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.load_macro_names()
        self.load_app_settings()
        self.initialize_default_assignments()

    # -- persistent settings ---------------------------------------------
    def load_macro_names(self) -> None:
        if self.macro_config_file.exists():
            try:
                data = json.loads(self.macro_config_file.read_text(encoding="utf-8"))
                self.macro_names = {int(k): str(v) for k, v in data.items()}
            except Exception as exc:
                self.config_errors.append(f"Config: Failed to load macro names: {exc}")
        for slot in range(1, MACRO_SLOT_COUNT + 1):
            self.macro_names.setdefault(slot, f"Macro {slot}")

    def save_macro_names(self) -> None:
        try:
            self.macro_config_file.write_text(
                json.dumps(self.macro_names, indent=2), encoding="utf-8")
        except Exception as exc:
            self.log(f"Config: Failed to save macro names: {exc}")

    def load_app_settings(self) -> None:
        if not self.settings_file.exists():
            return
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("settings root must be an object")
            restore = data.get("battery_led_restore")
            self.battery_led_enabled = bool(data.get("battery_led_enabled", False))
            self.battery_led_restore = (
                RgbState.from_dict(restore).to_dict() if isinstance(restore, dict)
                else None)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.config_errors.append(f"Config: Failed to load settings: {exc}")

    def save_app_settings(self) -> None:
        payload = {"battery_led_enabled": self.battery_led_enabled,
                   "battery_led_restore": self.battery_led_restore}
        temporary = self.settings_file.with_suffix(".json.tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.settings_file)
        except OSError as exc:
            self.log(f"Config: Failed to save settings: {exc}")

    # -- static tables -----------------------------------------------------
    @property
    def is_holtek(self) -> bool:
        return self.device_type == "holtek"

    @property
    def actions(self) -> list[str]:
        return list(HOLTEK_ACTIONS if self.is_holtek else ARESON_ACTIONS)

    @property
    def dpi_functions(self) -> list[tuple[str, int]]:
        return list(DPI_FUNCTIONS_HOLTEK if self.is_holtek else DPI_FUNCTIONS_ARESON)

    @property
    def button_keys(self) -> list[str]:
        return sorted_button_keys(self.active_button_profiles)

    def button_label(self, key: str) -> str:
        profile = self.active_button_profiles.get(key)
        return profile.label if profile else key

    def describe(self, action: str, params: dict) -> str:
        return describe_binding(action, params, self.device_type)

    def initialize_default_assignments(self) -> None:
        self.button_assignments = {
            key: {"action": "Disabled", "params": {}}
            for key in self.active_button_profiles}
        self.staging.load_base_state(self.button_assignments)

    # -- discovery ---------------------------------------------------------
    def refresh_devices(self) -> vp.DeviceInfo | None:
        """Enumerate vendor interfaces and remember the best candidate."""
        if self.demo:
            return self.device_info
        self.device_infos = vp.list_devices()
        self.device_info = None
        self.device_path = None
        if not vp.HIDAPI_AVAILABLE:
            self.log("Detection: python-hidapi is not installed")
            return None
        if not self.device_infos:
            return None
        chosen = next((item for item in self.device_infos if not item.access_error),
                      self.device_infos[0])
        self.device_info = chosen
        self.device_path = chosen.path
        if chosen.access_error:
            self.log(f"Detection: {chosen.access_error}")
        return chosen

    def connect(self, read: bool = True) -> ConnectResult:
        """Refresh, detect the controller type and optionally read settings."""
        result = ConnectResult()
        self.log("Connect: Refreshing device list...")
        info = self.refresh_devices()
        if info is None:
            self.log("Connect: No devices found.")
            self.device_name = ""
            return result

        new_type = dd.detect_device_type(info)
        if new_type != self.device_type:
            self.log(f"Connect: Device type changed: {self.device_type} -> {new_type}")
        self.set_device_type(new_type)
        self.last_battery_led_level = None

        result.found = True
        result.device_type = self.device_type
        result.name = vp.DEVICE_NAMES.get((info.vendor_id, info.product_id), info.product)
        result.access_error = info.access_error
        result.note = info.selection_note
        self.device_name = result.name
        self.log(f"Connect: Found {result.name} ({self.device_type}) at {info.display_path}")
        if info.selection_note:
            self.log(f"Connect: {info.selection_note}")
        if info.access_error:
            self.log(f"Connect: {info.access_error}")
            return result
        if read:
            self.log("Connect: Triggering auto-read settings...")
            try:
                result.read = (self.read_settings_holtek(use_active_profile=True)
                               if self.is_holtek else self.read_settings())
            except SessionError as exc:
                result.read_error = str(exc)
        return result

    def set_device_type(self, device_type: str) -> None:
        self.device_type = device_type
        self.active_button_profiles = dd.get_button_profiles(device_type)
        for key in self.active_button_profiles:
            self.button_assignments.setdefault(key, {"action": "Disabled", "params": {}})
        for key in list(self.button_assignments):
            if key not in self.active_button_profiles:
                del self.button_assignments[key]
        self.staging.load_base_state(self.button_assignments)

    def require_device(self) -> None:
        if self.demo:
            raise DemoDevice("Demo mode: no mouse is attached.")
        if self.device_path is None:
            self.refresh_devices()
        if self.device_path is None:
            raise SessionError("No device found. Please connect your mouse.")

    # -- transport helpers ------------------------------------------------
    def send_reports(self, reports: list[bytes], label: str, quiet: bool = False) -> bool:
        """Send reports over a transient connection; raise unless ``quiet``."""
        if quiet and (self.device_path is None or self.demo):
            return False
        try:
            self.require_device()
        except SessionError:
            if quiet:
                return False
            raise
        device = None
        try:
            device = dd.create_device(self.device_type, self.device_path)
            device.open()
            for report in reports:
                if device.send_reliable(report):
                    self.log(f"{label}: {report.hex()}")
                else:
                    self.log(f"TIMEOUT: {report.hex()}")
                    raise RuntimeError(
                        getattr(device, "last_error", "") or
                        f"Device timed out on command {report[1]:02X}")
            return True
        except Exception as exc:
            self.log(f"{label}: {exc}")
            if quiet:
                return False
            raise SessionError(str(exc)) from exc
        finally:
            if device:
                try:
                    device.close()
                except Exception:
                    pass

    def _open_areson(self, start_session: bool = True) -> vp.VenusDevice:
        device = vp.VenusDevice(self.device_path)
        device.open()
        if start_session:
            try:
                if not device.start_session():
                    raise vp.ProtocolError("startup challenge was rejected")
            except Exception:
                device.close()
                raise
        return device

    # -- reading ----------------------------------------------------------
    def read_settings(self) -> DeviceConfig:
        """Read the Areson configuration block; updates assignments."""
        self.require_device()
        if self.is_holtek:
            return self.read_settings_holtek()
        self.log("--- Reading from Device ---")
        device = None
        try:
            device = vp.VenusDevice(self.device_path)
            device.open()
            for attempt in range(3):
                try:
                    if not device.start_session():
                        raise vp.ProtocolError("startup challenge was rejected")
                    break
                except Exception as exc:
                    if attempt < 2:
                        self.log(f"Read handshake failed (Attempt {attempt + 1}): {exc}. Retrying...")
                        time.sleep(0.5)
                        device.close()
                        time.sleep(0.1)
                        device.open()
                    else:
                        raise
            page0 = bytearray()
            for offset in range(0, 0xA0, 10):
                page0.extend(device.read_flash(0, offset, 10))
            pages = []
            for page in (1, 2):
                data = bytearray()
                for offset in range(0, 256, 10):
                    data.extend(device.read_flash(page, offset, min(10, 256 - offset)))
                pages.append(bytes(data))
            self.log("Flash pages 0 and 1 read complete.")
            config = parse_areson_config(bytes(page0), pages[0], pages[1],
                                         self.macro_names, self.log)
        except Exception as exc:
            self.log(f"Error reading configuration: {exc}")
            raise SessionError(str(exc)) from exc
        finally:
            if device:
                device.close()

        if config.dpi_stage_count:
            self.log(f"  Enabled DPI stages: {config.dpi_stage_count}")
        if config.polling_rate:
            self.log(f"  Polling Rate: {config.polling_rate}Hz")
        rgb = config.rgb
        self.log(f"  RGB: ({rgb.r},{rgb.g},{rgb.b}), Mode: {rgb.mode}, "
                 f"Brightness: {rgb.brightness}%")
        for key, entry in config.buttons.items():
            self.log(f"  {key}: {entry['action']} {entry['params']}")
        self.button_assignments = deepcopy(config.buttons)
        self.staging.load_base_state(self.button_assignments)
        self.log("--- Done Reading ---")
        return config

    def read_settings_holtek(self, use_active_profile: bool = False) -> DeviceConfig:
        """Read one Holtek profile (the active one when asked)."""
        self.require_device()
        profile = self.holtek_profile
        description = "active profile" if use_active_profile else f"Profile {profile + 1}"
        self.log(f"--- Reading from Holtek Device ({description}) ---")
        device = None
        try:
            device = hp.HoltekDevice(self.device_path)
            device.open()
            raw = hp.read_all_config(
                device, profile=None if use_active_profile else profile)
        except Exception as exc:
            self.log(f"Error reading Holtek configuration: {exc}")
            raise SessionError(str(exc)) from exc
        finally:
            if device:
                device.close()

        if use_active_profile:
            profile = max(0, min(4, int(raw.get("active_profile", 0))))
            self.holtek_profile = profile
        config = DeviceConfig(holtek_profile=profile)
        self.log(f"  Read {len(raw['buttons'])} button entries from device")
        for info in raw["buttons"]:
            key = f"Button {info['index'] + 1}"
            if key not in self.active_button_profiles:
                continue
            action, params = hp.button_action_to_gui(
                info["type"], info["code"], type_hi=info.get("type_hi", 0))
            config.buttons[key] = {"action": action, "params": params}
            self.log(f"  {key}: {action} {params}")
        for key in self.active_button_profiles:
            config.buttons.setdefault(key, {"action": "Disabled", "params": {}})

        stages = raw.get("dpi_stages", [])
        if stages:
            self.log(f"  DPI stages: {stages}")
            config.dpi_stage_count = len(stages)
            config.dpi_active_stage = max(
                0, min(len(stages) - 1, int(raw.get("dpi_stage_current", 0))))
            config.dpi_colors = list(raw.get("dpi_colors", []))
            self.holtek_dpi_colors = list(config.dpi_colors)
            config.dpi_stages = [
                DpiStage(dpi=value, raw=hp.dpi_to_raw(value),
                         preset=value in hp.DPI_PRESETS) for value in stages]
        led = raw.get("led", {})
        if led:
            config.rgb = RgbState(
                r=led.get("r", 0), g=led.get("g", 0), b=led.get("b", 0),
                mode=led.get("mode", 3), brightness=led.get("brightness", 5),
                speed=led.get("speed", 1))
            self.log(f"  LED: #{config.rgb.r:02x}{config.rgb.g:02x}{config.rgb.b:02x} "
                     f"mode={config.rgb.mode} brightness={config.rgb.brightness} "
                     f"speed={config.rgb.speed}")
        for name in ("dpi_raw", "led_raw"):
            if raw.get(name):
                self.log(f"  {name.replace('_', ' ').upper()}: {raw[name].hex()}")
        self.button_assignments = deepcopy(config.buttons)
        self.staging.load_base_state(self.button_assignments)
        self.log(f"--- Done Reading Holtek (Profile {profile + 1}) ---")
        return config

    def select_holtek_profile(self, profile: int) -> DeviceConfig | None:
        """Switch the edited Holtek profile; staged changes belong to the old one."""
        self.holtek_profile = max(0, min(4, int(profile)))
        self.log(f"Profile switched to {self.holtek_profile + 1}")
        if self.staging.has_changes():
            self.staging.clear_stage()
        if self.device_path and self.is_holtek and not self.demo:
            return self.read_settings_holtek()
        return None

    # -- staging ----------------------------------------------------------
    def stage_binding(self, key: str, action: str, params: dict) -> bool:
        """Stage a change unless it equals the effective state."""
        effective = self.staging.get_effective_state(key)
        if (effective is not None and effective.get("action") == action
                and effective.get("params") == params):
            return False
        self.staging.stage_change(key, action, params)
        return True

    def effective_binding(self, key: str) -> dict | None:
        return self.staging.get_effective_state(key) or self.button_assignments.get(key)

    def build_packets_for_key(self, key: str, action: str, params: dict) -> list[bytes]:
        if self.is_holtek:
            profile = self.active_button_profiles.get(key)
            if profile is None:
                raise ValueError(f"Unknown button: {key}")
            return hp.build_write_packets(profile.index, action, params,
                                          profile=self.holtek_profile)
        profile = vp.BUTTON_PROFILES.get(key)
        if profile is None or profile.apply_offset is None:
            raise ValueError(f"Unknown button profile: {key}")
        code_hi, code_lo, apply_offset = profile.code_hi, profile.code_lo, profile.apply_offset
        reports: list[bytes] = []
        if action == "Keyboard Key":
            reports.extend(vp.build_key_binding(
                code_hi, code_lo, params.get("key", 0), params.get("mod", 0)))
            reports.append(vp.build_keyboard_bind(apply_offset))
        elif action == "Media Key":
            reports.extend(vp.build_consumer_binding(code_hi, code_lo, params.get("code", 0)))
            reports.append(vp.build_keyboard_bind(apply_offset))
        elif action == "Disabled":
            reports.append(vp.build_disabled(apply_offset))
        elif action in MOUSE_ACTION_VALUES:
            reports.append(vp.build_mouse_param(apply_offset, MOUSE_ACTION_VALUES[action]))
        elif action == "DPI Control":
            reports.append(vp.build_dpi_control(apply_offset, params.get("func", 1)))
        elif action in ("Fire Key", "Triple Click"):
            reports.append(vp.build_special_binding(
                apply_offset, params.get("delay", 40), params.get("repeat", 3)))
        elif action == "Polling Rate Toggle":
            reports.append(vp.build_poll_rate_toggle(apply_offset))
        elif action == "RGB Toggle":
            reports.append(vp.build_rgb_toggle(apply_offset))
        elif action == "Macro":
            reports.append(vp.build_macro_bind(
                apply_offset, params.get("index", 1) - 1,
                params.get("mode", vp.MACRO_REPEAT_ONCE)))
        else:
            raise ValueError(f"Unsupported button action: {action}")
        return reports

    def commit_staged(self, progress: Callable[[str], None] | None = None) -> CommitResult:
        """Write every staged binding; Areson writes persist per packet."""
        self.require_device()
        if not self.staging.has_changes():
            return CommitResult(True)
        progress = progress or (lambda _text: None)
        session = self

        class PacketBuilder:
            def build_packets(self, key, action, params):
                return session.build_packets_for_key(key, action, params)

        device = None
        success = False
        try:
            device = dd.create_device(self.device_type, self.device_path)
            device.open()
            if self.is_holtek:
                device.enter_write_mode()
            elif not device.begin_write():
                raise RuntimeError(device.last_error or "Mouse did not enter ready state")
            progress("Applying changes...")
            controller = TransactionController(device, PacketBuilder(), logger=self.log)
            success = controller.execute_transaction(self.staging)
            if self.is_holtek and success:
                progress("Restarting device, please wait...")
                self.idle()
                device.commit_writes(categories=0x02)
                try:
                    device.close()
                except Exception:
                    pass
                device = None
                self.holtek_reconnect()
        except Exception as exc:
            return CommitResult(False, str(exc))
        finally:
            if device:
                try:
                    device.close()
                except Exception:
                    pass
        if success:
            self.button_assignments = deepcopy(self.staging.base_state)
            return CommitResult(True)
        return CommitResult(
            False, "A write failed. Earlier acknowledged changes may already be "
            "stored on the device; read settings again before retrying.", partial=True)

    def discard_staged(self) -> None:
        self.staging.clear_stage()

    def holtek_reconnect(self) -> None:
        """Wait for the Holtek device to re-enumerate after a reset."""
        self.log("  Waiting for device to reconnect...")
        deadline = time.time() + 2.0
        while time.time() < deadline:
            self.idle()
            time.sleep(0.1)
        deadline = time.time() + 8.0
        while time.time() < deadline:
            new_path = hp.find_device_path()
            if new_path:
                self.device_path = new_path
                self.log(f"  Device reconnected: {new_path}")
                return
            self.idle()
            time.sleep(0.3)
        self.log("  Warning: device did not reconnect within timeout")

    # -- macros -----------------------------------------------------------
    def validate_macro_name(self, slot: int, name: str) -> str | None:
        """Return the reason a name cannot be saved to ``slot``, else None."""
        if not name:
            return "Macro name cannot be empty."
        if len(name.encode("utf-16-le")) > 30:
            return ("A hardware macro name can contain at most 15 UTF-16 code "
                    "units. Shorten the name before saving.")
        for other, existing in self.macro_names.items():
            if other != slot and existing.lower() == name.lower():
                return f"Macro name '{name}' is already used by Slot {other}."
        return None

    def upload_macro(self, slot: int, name: str, events: list[vp.MacroEvent]) -> None:
        """Write a macro image to a 1-based slot; raises SessionError."""
        self.require_device()
        if self.is_holtek:
            raise NotSupported("Hardware macros use the Areson protocol and are "
                               "not available on the Holtek Venus MMO.")
        macro_index = slot - 1
        if not 0 <= macro_index <= 15:
            raise SessionError("Macro Index must be 1-16.")
        if not events:
            raise SessionError("No valid events to upload.")
        if len(events) > vp.MACRO_MAX_EVENTS:
            raise SessionError(
                f"A hardware macro slot holds at most {vp.MACRO_MAX_EVENTS} events.")
        full_macro = vp.build_macro_image(name or "Macro", events)
        page, offset = vp.get_macro_slot_info(macro_index)
        self.log(f"Uploading Macro {slot} ({name}) to Page 0x{page:02X} Offset 0x{offset:02X}...")
        reports = [vp.build_simple(vp.CMD_READY)]
        address = (page << 8) | offset
        for start in range(0, len(full_macro), 10):
            chunk_address = address + start
            reports.append(vp.build_macro_chunk(
                chunk_address & 0xFF, full_macro[start:start + 10],
                (chunk_address >> 8) & 0xFF))
        self.send_reports(reports, f"Macro {slot} Upload ({len(full_macro)} bytes)")

    def save_macro(self, slot: int, name: str, draft: MacroDraft) -> None:
        """Validate, upload and remember the name; raises SessionError."""
        error = self.validate_macro_name(slot, name)
        if error:
            raise SessionError(error)
        draft.normalize_final_delay()
        self.upload_macro(slot, name, draft.to_macro_events())
        self.macro_names[slot] = name
        self.save_macro_names()
        self.log(f"Macro '{name}' saved to slot {slot}")

    def load_macro_slot(self, slot: int, draft: MacroDraft) -> str:
        """Read one slot into ``draft``; returns the name to display."""
        self.require_device()
        if self.is_holtek:
            raise NotSupported("The Holtek controller has no confirmed hardware macro format.")
        start_page, start_offset = vp.get_macro_slot_info(slot - 1)
        self.log(f"Reading macro slot {slot} (Page 0x{start_page:02X}, Offset 0x{start_offset:02X})")
        device = None
        try:
            device = self._open_areson()
            data = bytearray()
            slot_address = (start_page << 8) | start_offset
            for relative in range(0, vp.MACRO_SLOT_SIZE, vp.MAX_DATA_LEN):
                address = slot_address + relative
                length = min(vp.MAX_DATA_LEN, vp.MACRO_SLOT_SIZE - relative)
                data.extend(device.read_flash((address >> 8) & 0xFF, address & 0xFF, length))
            name, warnings = draft.load_slot_image(bytes(data))
        except Exception as exc:
            self.log(f"Failed to load macro: {exc}")
            raise SessionError(str(exc)) from exc
        finally:
            if device:
                device.close()
        for warning in warnings:
            self.log(f"  Warning: {warning}")
        if name:
            self.macro_names[slot] = name
            self.save_macro_names()
        self.log(f"Loaded macro slot {slot}")
        return name or f"Macro {slot}"

    def bind_macro(self, button_key: str, slot: int, mode: int, count: int) -> CommitResult:
        """Stage a macro binding and write it immediately."""
        effective = count if mode == vp.MACRO_REPEAT_COUNT else mode
        self.staging.stage_change(button_key, "Macro", {"index": slot, "mode": effective})
        self.log(f"Binding macro slot {slot} to {button_key} (repeat 0x{effective:02X})")
        return self.commit_staged()

    # -- lighting ---------------------------------------------------------
    def apply_rgb(self, state: RgbState, mode_name: str = "",
                  progress: Callable[[str], None] | None = None) -> None:
        self.require_device()
        if self.is_holtek:
            self._apply_rgb_holtek(state, mode_name, progress or (lambda _t: None))
            return
        if self.battery_led_enabled:
            self.set_battery_led_enabled(False, state, restore=False)
        reports = [vp.build_simple(vp.CMD_READY),
                   *vp.build_rgb_packets(state.r, state.g, state.b, state.mode,
                                         state.brightness, state.speed)]
        self.send_reports(reports, f"RGB Custom: #{state.r:02x}{state.g:02x}{state.b:02x} "
                                   f"{mode_name} {state.brightness}%")

    def _apply_rgb_holtek(self, state: RgbState, mode_name: str,
                          progress: Callable[[str], None]) -> None:
        device = None
        try:
            progress("Applying lighting...")
            device = hp.HoltekDevice(self.device_path)
            device.open()
            device.enter_write_mode()
            for packet in hp.build_led_packets(state.r, state.g, state.b, state.mode,
                                               state.brightness, state.speed,
                                               profile=self.holtek_profile):
                device.send_feature(packet)
                time.sleep(0.008)
            progress("Restarting device, please wait...")
            self.idle()
            device.commit_writes(categories=0x08)
            try:
                device.close()
            except Exception:
                pass
            device = None
            self.log(f"Holtek RGB (profile {self.holtek_profile + 1}): "
                     f"#{state.r:02x}{state.g:02x}{state.b:02x} {mode_name} "
                     f"brightness={state.brightness} speed={state.speed}")
            self.holtek_reconnect()
        except Exception as exc:
            raise SessionError(str(exc)) from exc
        finally:
            if device:
                device.close()

    # -- polling ----------------------------------------------------------
    def apply_polling(self, rate: int) -> None:
        self.require_device()
        if self.is_holtek:
            device = None
            try:
                device = hp.HoltekDevice(self.device_path)
                device.open()
                device.set_polling_rate(rate)
                self.log(f"Holtek Polling: {rate} Hz")
            except Exception as exc:
                raise SessionError(str(exc)) from exc
            finally:
                if device:
                    device.close()
            return
        payload = vp.POLLING_RATE_PAYLOADS[rate]
        self.send_reports([vp.build_simple(vp.CMD_READY),
                           vp.build_report(vp.CMD_WRITE, payload)], f"Polling {rate} Hz")

    # -- DPI --------------------------------------------------------------
    def apply_dpi(self, stages: list[DpiStage], stage_count: int, active_stage: int = 0,
                  progress: Callable[[str], None] | None = None) -> None:
        """Write the first ``stage_count`` stages (Areson raw, Holtek DPI)."""
        self.require_device()
        stages = stages[:stage_count]
        if self.is_holtek:
            progress = progress or (lambda _t: None)
            device = None
            try:
                progress("Applying DPI...")
                device = hp.HoltekDevice(self.device_path)
                device.open()
                device.enter_write_mode()
                dpi_values = [stage.dpi for stage in stages]
                for packet in hp.build_dpi_packets(
                        dpi_values, profile=self.holtek_profile,
                        current_stage=active_stage,
                        color_indices=self.holtek_dpi_colors):
                    device.send_feature(packet)
                    time.sleep(0.008)
                progress("Restarting device, please wait...")
                self.idle()
                device.commit_writes(categories=0x04)
                try:
                    device.close()
                except Exception:
                    pass
                device = None
                self.log(f"Holtek DPI (profile {self.holtek_profile + 1}): {dpi_values}")
                self.holtek_reconnect()
            except Exception as exc:
                raise SessionError(str(exc)) from exc
            finally:
                if device:
                    device.close()
            return
        reports = [vp.build_simple(vp.CMD_READY), vp.build_dpi_stage_count(stage_count)]
        for slot, stage in enumerate(stages):
            reports.append(vp.build_dpi(slot, stage.raw, vp.dpi_value_to_tweak(stage.raw)))
        self.send_reports(reports, "DPI slots")

    # -- advanced ---------------------------------------------------------
    def send_built_report(self, command_hex: str, payload_hex: str) -> None:
        self.require_device()
        if self.is_holtek:
            raise NotSupported("Built reports use the 17-byte Areson format and "
                               "cannot be sent to a Holtek device.")
        try:
            command = int(command_hex.strip(), 16)
            payload = bytes.fromhex(payload_hex.strip().replace(" ", ""))
            report = vp.build_report(command, payload)
        except Exception as exc:
            raise SessionError(f"Invalid input: {exc}") from exc
        self.send_reports([report], "Advanced built")

    def send_raw_report(self, raw_hex: str) -> None:
        self.require_device()
        if self.is_holtek:
            raise NotSupported("Raw reports use the 17-byte Areson format and "
                               "cannot be sent to a Holtek device.")
        try:
            report = bytes.fromhex(raw_hex.strip().replace(" ", ""))
        except ValueError as exc:
            raise SessionError(f"Invalid hex: {exc}") from exc
        if len(report) != vp.REPORT_LEN:
            raise SessionError(f"Report must be {vp.REPORT_LEN} bytes.")
        self.send_reports([report], "Advanced raw")

    def factory_reset(self) -> None:
        """Erase Areson settings and macros.  The caller confirms first."""
        self.require_device()
        if self.is_holtek:
            raise NotSupported("Factory reset is not yet supported for the Holtek "
                               "Venus MMO. Please use the Windows software.")
        self.send_reports([vp.build_simple(vp.CMD_FACTORY_RESET)], "Factory reset")

    def reclaim(self) -> bool:
        """Ask the kernel to re-attach its driver on every supported device."""
        self.log("USB: Attempting to reclaim Venus devices from other processes...")
        found = False
        for vid, pid in sorted(vp.SUPPORTED_DEVICE_IDS):
            if vp.reclaim_device(vid, pid):
                self.log(f"USB: Reclaim attempt sent to {vid:04X}:{pid:04X}")
                found = True
        if found:
            self.log("USB: Reclaim sequence complete. Refreshing...")
            time.sleep(1.0)
        else:
            self.log("USB: No devices found to reclaim.")
        return found

    # -- profiles ---------------------------------------------------------
    def export_profile(self, path: Path,
                       progress: Callable[[int], bool] | None = None) -> bool:
        """Dump all 256 pages to ``path``; ``progress(page)`` may return False to cancel."""
        self.require_device()
        if self.is_holtek:
            raise NotSupported("Profile export is not yet supported for the Holtek Venus MMO.")
        progress = progress or (lambda _page: True)
        device = None
        cancelled = False
        try:
            device = self._open_areson()
            with open(path, "wb") as handle:
                for page in range(256):
                    if not progress(page):
                        cancelled = True
                        break
                    page_data = bytearray()
                    for offset in range(0, 256, 10):
                        page_data.extend(device.read_flash(page, offset, min(10, 256 - offset)))
                    handle.write(page_data)
        except Exception as exc:
            self.log(f"Export failed: {exc}")
            raise SessionError(str(exc)) from exc
        finally:
            if device:
                device.close()
        if cancelled:
            self.log(f"Profile export canceled; partial dump remains at {path}")
            return False
        self.log(f"Profile exported to {path}")
        return True

    def import_profile(self, path: Path,
                       progress: Callable[[int], bool] | None = None) -> bool:
        """Write a 64 KiB dump to the device.  The caller confirms first."""
        self.require_device()
        if self.is_holtek:
            raise NotSupported("Profile import is not yet supported for the Holtek Venus MMO.")
        data = Path(path).read_bytes()
        if len(data) != 65536:
            raise SessionError(f"File size must be exactly 64KB (got {len(data)} bytes).")
        progress = progress or (lambda _page: True)
        device = None
        cancelled = False
        try:
            device = self._open_areson()
            if not device.begin_write():
                raise RuntimeError(device.last_error or "Mouse did not enter ready state")
            for page in range(256):
                if not progress(page):
                    cancelled = True
                    break
                page_data = data[page * 256:(page + 1) * 256]
                for offset in range(0, 256, 10):
                    packet = vp.build_flash_write(page, offset, page_data[offset:offset + 10])
                    if not device.send_reliable(packet):
                        raise RuntimeError(device.last_error or
                                           f"Write failed at 0x{page:02x}{offset:02x}")
        except Exception as exc:
            self.log(f"Import failed: {exc}")
            raise SessionError(str(exc)) from exc
        finally:
            if device:
                device.close()
        if cancelled:
            self.log("Profile import canceled; the device contains a partial write")
            return False
        self.log(f"Profile imported from {path}")
        return True

    # -- battery ----------------------------------------------------------
    @staticmethod
    def query_battery(path: bytes | str) -> vp.BatteryStatus:
        """Blocking status exchange on its own handle (run it off the UI thread)."""
        device = vp.VenusDevice(path)
        try:
            device.open()
            return device.query_status()
        finally:
            try:
                device.close()
            except Exception:
                pass

    @property
    def battery_led_supported(self) -> bool:
        return self.device_type == "venus_pro"

    def set_battery_led_enabled(self, enabled: bool, current: RgbState,
                                restore: bool = True) -> RgbState | None:
        """Toggle the battery-colour controller.

        Returns the lighting the UI should now show (the restored manual
        state when the controller was disabled with ``restore``), or None.
        """
        enabled = bool(enabled)
        if enabled and not self.battery_led_supported:
            return None
        if enabled == self.battery_led_enabled:
            return None
        was_enabled = self.battery_led_enabled
        if enabled:
            self.battery_led_restore = current.to_dict()
            self.battery_led_enabled = True
            self.last_battery_led_level = None
            self.log("Battery LED: enabled (low brightness; updates on battery-step changes)")
        else:
            self.battery_led_enabled = False
            self.last_battery_led_level = None
            self.log("Battery LED: disabled")
        self.save_app_settings()
        if not enabled and was_enabled and restore:
            return self.restore_battery_led(quiet=False)
        return None

    def restore_battery_led(self, quiet: bool) -> RgbState | None:
        """Send the lighting captured when the controller was enabled."""
        settings = self.battery_led_restore
        self.last_battery_led_level = None
        if not settings:
            return None
        state = RgbState.from_dict(settings)
        if self.battery_led_supported and self.device_path is not None and not self.demo:
            packets = vp.build_rgb_packets(state.r, state.g, state.b, state.mode,
                                           state.brightness, state.speed)
            self.send_reports([vp.build_simple(vp.CMD_READY), *packets],
                              "Battery LED restore", quiet=quiet)
        return state

    def apply_battery_led_status(self, status: vp.BatteryStatus) -> bool:
        if not self.battery_led_enabled or status.level == self.last_battery_led_level:
            return False
        r, g, b = vp.battery_gradient_rgb(status.percent)
        success = self.send_reports(
            [vp.build_simple(vp.CMD_READY), vp.build_battery_indicator_rgb(status.percent)],
            f"Battery LED {status.percent}% ({r},{g},{b})", quiet=True)
        if success:
            self.last_battery_led_level = status.level
            self.log(f"Battery LED: {status.percent}% -> RGB({r}, {g}, {b}) at "
                     f"{vp.BATTERY_LED_BRIGHTNESS}% brightness")
        return success

    # -- demo mode --------------------------------------------------------
    def load_demo(self, device_type: str = "venus_pro") -> DeviceConfig:
        """Populate illustrative state without touching hardware."""
        self.demo = True
        self.device_path = None
        self.set_device_type(device_type)
        if device_type == "holtek":
            self.device_name = "Venus MMO (Wired)"
            self.holtek_profile = 0
            assignments = {key: {"action": "Disabled", "params": {}}
                           for key in hp.BUTTON_PROFILES}
            assignments["Button 5"] = {"action": "Keyboard Key",
                                       "params": {"key": vp.HID_KEY_USAGE["PageUp"], "mod": 0}}
            assignments["Button 6"] = {"action": "Keyboard Key",
                                       "params": {"key": vp.HID_KEY_USAGE["PageDown"], "mod": 0}}
            assignments["Button 20"] = {"action": "Profile Switch", "params": {}}
            config = DeviceConfig(
                buttons=assignments, dpi_stage_count=6, dpi_active_stage=2,
                dpi_stages=[DpiStage(d, hp.dpi_to_raw(d), preset=d in hp.DPI_PRESETS)
                            for d in (800, 1200, 1600, 2400, 3200, 6400)],
                polling_rate=1000, rgb=RgbState(76, 175, 80, 3, 5, 1), holtek_profile=0)
        else:
            self.device_name = "Venus Pro (Wireless)"
            assignments = {key: {"action": "Disabled", "params": {}}
                           for key in vp.BUTTON_PROFILES}
            assignments.update({
                "Button 1": {"action": "Keyboard Key",
                             "params": {"key": vp.HID_KEY_USAGE["1"],
                                        "mod": vp.MODIFIER_CTRL | vp.MODIFIER_SHIFT}},
                "Button 2": {"action": "Macro", "params": {"index": 1, "mode": vp.MACRO_REPEAT_ONCE}},
                "Button 3": {"action": "Left Click", "params": {}},
                "Button 4": {"action": "Media Key",
                             "params": {"code": vp.MEDIA_KEY_CODES["PlayPause"]}},
                "Button 5": {"action": "DPI Control", "params": {"func": 2}},
                "Button 6": {"action": "RGB Toggle", "params": {}},
                "Button 7": {"action": "Polling Rate Toggle", "params": {}},
                "Button 14": {"action": "Left Click", "params": {}},
                "Button 15": {"action": "Middle Click", "params": {}},
                "Button 16": {"action": "Right Click", "params": {}},
            })
            config = DeviceConfig(
                buttons=assignments, dpi_stage_count=5,
                dpi_stages=[DpiStage(d, vp.DPI_PRESETS[d]["value"],
                                     vp.DPI_PRESETS[d]["tweak"], True)
                            for d in (1000, 2000, 4000, 8000, 10000)],
                polling_rate=1000, rgb=RgbState(76, 175, 80, vp.RGB_MODE_STEADY, 15))
        self.button_assignments = deepcopy(config.buttons)
        self.staging.load_base_state(self.button_assignments)
        self.log(f"Demo: illustrative {self.device_name} configuration loaded; no device I/O.")
        return config
