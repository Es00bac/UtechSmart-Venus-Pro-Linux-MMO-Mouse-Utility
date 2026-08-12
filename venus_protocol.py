from __future__ import annotations

import random
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from typing import Iterable

try:
    import hid
    HIDAPI_AVAILABLE = True
except ImportError:
    hid = None
    HIDAPI_AVAILABLE = False

try:
    import usb.core
    import usb.util
    PYUSB_AVAILABLE = True
except ImportError:
    PYUSB_AVAILABLE = False


def reclaim_device(vendor_id: int, product_id: int) -> bool:
    """Attempts to force re-attach the kernel driver to a device."""
    if not PYUSB_AVAILABLE:
        return False
    dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
    if dev is None:
        return False
        
    try:
        # For each interface through the vendor configuration interface, try
        # to re-attach.  Holtek uses interface 2, while Areson uses 1.
        # This will fail if another process has a persistent LOCK, 
        # but can break simple captures.
        for iface in range(expected_interface(vendor_id, product_id) + 1):
            try:
                # First, try to detach if a non-kernel driver is active
                # (PyUSB doesn't tell us WHO has it, just if it's kernel or not)
                if not dev.is_kernel_driver_active(iface):
                    # Attempt to attach
                    dev.attach_kernel_driver(iface)
            except:
                pass
        return True
    except:
        return False


def reset_usb_device(vendor_id: int, product_id: int) -> bool:
    """Performs a low-level USB bus reset."""
    if not PYUSB_AVAILABLE:
        return False
    dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
    if dev:
        try:
            dev.reset()
            return True
        except:
            return False
    return False


def is_device_busy(vendor_id: int, product_id: int) -> bool:
    """Checks if a device is on the bus but likely captured by another process."""
    if not PYUSB_AVAILABLE:
        return False
    
    dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
    if dev is None:
        return False
        
    # Check if any interface has a kernel driver active
    # If not active, and hidapi didn't see it, it's likely captured via usbfs
    try:
        busy = False
        for iface in range(expected_interface(vendor_id, product_id) + 1):
            if not dev.is_kernel_driver_active(iface):
                busy = True
                break
        return busy
    except:
        return True # Assume busy if we can't even check

def try_unlock_device() -> bool:
    """Deprecated compatibility shim.

    Captures and the vendor binary contain no ``0x4d`` unlock command.  Older
    versions also put the destructive ``0x09`` factory-reset command in an
    "unlock" path.  Session setup now belongs to :meth:`VenusDevice.start_session`
    and requires an already-selected config-interface path.
    """
    print("Unlock is obsolete; reconnect and use VenusDevice.start_session().", file=sys.stderr)
    return False


SUPPORTED_DEVICE_IDS = {
    (0x25A7, 0xFA07),  # Areson/Compx wireless receiver
    (0x25A7, 0xFA08),  # Areson/Compx wired connection
    (0x04D9, 0xFC55),  # Holtek wired variant (different protocol)
}
VENDOR_IDS = tuple(sorted({vid for vid, _ in SUPPORTED_DEVICE_IDS}))
PRODUCT_IDS = tuple(sorted({pid for _, pid in SUPPORTED_DEVICE_IDS}))
# Map for friendly names
DEVICE_NAMES = {
    (0x25A7, 0xFA07): "Venus Pro (Wireless)",
    (0x25A7, 0xFA08): "Venus Pro (Wired)",
    (0x04D9, 0xFC55): "Venus MMO (Wired)",
}

REPORT_ID = 0x08
RESPONSE_REPORT_ID = 0x09
REPORT_LEN = 17
CHECKSUM_BASE = 0x55
MAX_DATA_LEN = 10

CMD_CHALLENGE = 0x01
CMD_NOTIFY = 0x02
CMD_READY = 0x03
CMD_STATUS = 0x04
CMD_WRITE = 0x07
CMD_READ = 0x08
CMD_FACTORY_RESET = 0x09

# Captures show the Windows driver leaving roughly 25-35 ms after each ACK
# before its next feature report. Older live-write experiments used 50 ms
# successfully. The firmware can acknowledge a faster EEPROM write yet defer
# reloading its active setting until a hardware power-cycle, so retain the
# conservative interval for reliable command sequences.
REPORT_SETTLE_SECONDS = 0.05


@dataclass(frozen=True)
class ButtonProfile:
    label: str
    code_hi: int | None
    code_lo: int | None
    apply_offset: int | None


BUTTON_PROFILES = {
    # Verified from memory dumps and USB captures:
    # - Buttons 1-12: Side button grid (thumb panel)
    # - Button 13: Fire key (left of left mouse button)
    # - Button 14: Left mouse button
    # - Button 15: Middle mouse button (scroll click)
    # - Button 16: Right mouse button
    # 
    # Each button has:
    # - code_hi: Keyboard region page (0x01 for 1-6, 0x02 for 7-12, 0x03 for 13-16)
    # - code_lo: Keyboard region offset (0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0)
    # - apply_offset: Mouse region offset at page 0x00 (CONTIGUOUS: 0x60 + button_index * 4)
    #
    # Verified Layout from Dump Analysis:
    # Mouse Offsets are strictly sequential 0x60 -> 0x9C (skipping nothing relevant to slots).
    # Kbd Pages fill Pg1 (8 slots) then Pg2 (8 slots).
    # 
    # Pg1 Slots:
    # 00: Btn 1 (60)
    # 20: Btn 2 (64)
    # 40: Btn 3 (68)
    # 60: Btn 4 (6C)
    # 80: Btn 5 (70)
    # A0: Btn 6 (74)
    # C0: Btn 16 (Right) (78)  -> Found 'g' here
    # E0: Btn 14 (Left) (7C)   -> Found 'h' here
    #
    # Pg2 Slots:
    # 00: Btn 7 (80)           -> Found Key 7 here
    # 20: Btn 8 (84)           -> Found Key 8 here
    # 40: Btn 15 (Mid) (88)
    # 60: Btn 13 (Fire) (8C)
    # 80: Btn 9 (90)           -> Found Key 9 here
    # A0: Btn 10 (94)
    # C0: Btn 11 (98)
    # E0: Btn 12 (9C)
    
    "Button 1": ButtonProfile("Side Button 1", 0x01, 0x00, 0x60),
    "Button 2": ButtonProfile("Side Button 2", 0x01, 0x20, 0x64),
    "Button 3": ButtonProfile("Side Button 3", 0x01, 0x40, 0x68),
    "Button 4": ButtonProfile("Side Button 4", 0x01, 0x60, 0x6C),
    "Button 5": ButtonProfile("Side Button 5", 0x01, 0x80, 0x70),
    "Button 6": ButtonProfile("Side Button 6", 0x01, 0xA0, 0x74),
    "Button 7": ButtonProfile("Side Button 7", 0x02, 0x00, 0x80),
    "Button 8": ButtonProfile("Side Button 8", 0x02, 0x20, 0x84),
    "Button 9": ButtonProfile("Side Button 9", 0x02, 0x80, 0x90),
    "Button 10": ButtonProfile("Side Button 10", 0x02, 0xA0, 0x94),
    "Button 11": ButtonProfile("Side Button 11", 0x02, 0xC0, 0x98),
    "Button 12": ButtonProfile("Side Button 12", 0x02, 0xE0, 0x9C),
    "Button 13": ButtonProfile("Fire Key", 0x02, 0x60, 0x8C),
    "Button 14": ButtonProfile("Left Mouse Button", 0x01, 0xE0, 0x7C),
    "Button 15": ButtonProfile("Middle Mouse Button", 0x02, 0x40, 0x88),
    "Button 16": ButtonProfile("Right Mouse Button", 0x01, 0xC0, 0x78),
}



RGB_PRESETS = {
    "Neon (Magenta)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0xFF, 0x57, 0x03, 0x52, 0x3C, 0x19, 0x00, 0x00]
    ),
    "Breathing (Magenta)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0xFF, 0x57, 0x02, 0x53, 0x3C, 0x19, 0x00, 0x00]
    ),
    "Off": bytes([0x00, 0x00, 0x58, 0x02, 0x00, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    "Steady (Magenta, 20%)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0xFF, 0x57, 0x01, 0x54, 0x3C, 0x19, 0x00, 0x00]
    ),
    "Steady (Red, 20%)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0x00, 0x56, 0x01, 0x54, 0x3C, 0x19, 0x00, 0x00]
    ),
    "Steady (Red, Low)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0x00, 0x56, 0x01, 0x54, 0x01, 0x54, 0x00, 0x00]
    ),
    "Steady (Red, High)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0x00, 0x56, 0x01, 0x54, 0xFF, 0x56, 0x00, 0x00]
    ),
}

# The 27 Quick Pick colors from the Windows utility
RGB_QUICK_PICKS = [
    (0xFF, 0x00, 0x00), (0xE4, 0x00, 0x7F), (0xE8, 0x38, 0x28),
    (0xEA, 0x55, 0x14), (0xF3, 0x98, 0x00), (0xFF, 0xF1, 0x00),
    (0xF8, 0xB6, 0x2D), (0x8F, 0xC3, 0x1F), (0x00, 0xFF, 0x00),
    (0x2E, 0xA7, 0xE0), (0x03, 0x6E, 0xB8), (0x17, 0x2A, 0x88),
    (0x17, 0x1C, 0x61), (0x60, 0x19, 0x86), (0xA4, 0x0B, 0x5D),
    (0x00, 0xA2, 0x9A), (0x00, 0x00, 0xFF), (0xC2, 0x41, 0x94),
    (0xE8, 0xF0, 0xD3), (0xBA, 0xD1, 0x7B), (0x8C, 0xB3, 0x24),
    (0x69, 0x86, 0x1B), (0xBF, 0x75, 0x26), (0xFF, 0x9C, 0x33),
    (0xFF, 0xC4, 0x85), (0xD1, 0x71, 0xAE), (0xB3, 0x12, 0x79)
]



POLLING_RATE_CODES = {125: 0x08, 250: 0x04, 500: 0x02, 1000: 0x01}
POLLING_CODE_TO_RATE = {code: rate for rate, code in POLLING_RATE_CODES.items()}
POLLING_RATE_PAYLOADS = {
    rate: bytes([0x00, 0x00, 0x00, 0x02, code, (0x55 - code) & 0xFF]) + bytes(8)
    for rate, code in POLLING_RATE_CODES.items()
}


DPI_PRESETS = {
    1000: {"value": 0x0B, "tweak": 0x3F},
    2000: {"value": 0x17, "tweak": 0x27},
    4000: {"value": 0x2F, "tweak": 0xF7},
    8000: {"value": 0x5F, "tweak": 0x97},
    10000: {"value": 0xBD, "tweak": 0xDB},
}

DPI_VALUE_POINTS = sorted((dpi, info["value"]) for dpi, info in DPI_PRESETS.items())
DPI_VALUE_POINTS_BY_VALUE = sorted((info["value"], dpi) for dpi, info in DPI_PRESETS.items())


def dpi_value_to_tweak(value: int) -> int:
    return (0x55 - ((value * 2) & 0xFF)) & 0xFF


def dpi_to_value(dpi: int) -> int:
    """Convert DPI to the raw byte value using linear interpolation."""
    points = DPI_VALUE_POINTS
    if not points:
        return 0
    if dpi <= points[0][0]:
        (x1, y1), (x2, y2) = points[0], points[1]
    elif dpi >= points[-1][0]:
        (x1, y1), (x2, y2) = points[-2], points[-1]
    else:
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            if x1 <= dpi <= x2:
                break
    if x2 == x1:
        return int(max(0, min(255, round(y1))))
    value = y1 + (dpi - x1) * (y2 - y1) / (x2 - x1)
    return int(max(0, min(255, round(value))))


def value_to_dpi(value: int) -> int:
    """Convert raw DPI byte value to an approximate DPI."""
    points = DPI_VALUE_POINTS_BY_VALUE
    if not points:
        return 0
    if value <= points[0][0]:
        (x1, y1), (x2, y2) = points[0], points[1]
    elif value >= points[-1][0]:
        (x1, y1), (x2, y2) = points[-2], points[-1]
    else:
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            if x1 <= value <= x2:
                break
    if x2 == x1:
        return int(round(y1))
    dpi = y1 + (value - x1) * (y2 - y1) / (x2 - x1)
    return int(round(dpi))


# Macro Repeat Modes
# Verified from capture: bind macros 123...
# D2 byte in Bind Packet (cmd 0x06)
# Modifier key bit flags (standard HID modifier byte)
MODIFIER_CTRL = 0x01
MODIFIER_SHIFT = 0x02
MODIFIER_ALT = 0x04
MODIFIER_WIN = 0x08

# HID keyboard usage codes (extended beyond basic A-Z)
HID_KEY_USAGE = {
    # Letters A-Z
    **{chr(ord("A") + i): 0x04 + i for i in range(26)},
    # Numbers 1-9, 0
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
    # Function keys
    "F1": 0x3A, "F2": 0x3B, "F3": 0x3C, "F4": 0x3D, "F5": 0x3E, "F6": 0x3F,
    "F7": 0x40, "F8": 0x41, "F9": 0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,
    "F13": 0x68, "F14": 0x69, "F15": 0x6A, "F16": 0x6B, "F17": 0x6C, "F18": 0x6D,
    "F19": 0x6E, "F20": 0x6F, "F21": 0x70, "F22": 0x71, "F23": 0x72, "F24": 0x73,
    # Special keys
    "Enter": 0x28, "Return": 0x28, 
    "Escape": 0x29, "Esc": 0x29,
    "Backspace": 0x2A, 
    "Tab": 0x2B, 
    "Space": 0x2C, " ": 0x2C,
    "Minus": 0x2D, "-": 0x2D, "_": 0x2D,
    "Equal": 0x2E, "=": 0x2E, "+": 0x2E,
    "LeftBracket": 0x2F, "[": 0x2F, "{": 0x2F, "BracketLeft": 0x2F,
    "RightBracket": 0x30, "]": 0x30, "}": 0x30, "BracketRight": 0x30,
    "Backslash": 0x31, "\\": 0x31, "|": 0x31,
    "Semicolon": 0x33, ";": 0x33, ":": 0x33,
    "Quote": 0x34, "'": 0x34, "\"": 0x34, "Apostrophe": 0x34,
    "Grave": 0x35, "`": 0x35, "~": 0x35, "Tilde": 0x35,
    "Comma": 0x36, ",": 0x36, "<": 0x36,
    "Period": 0x37, ".": 0x37, ">": 0x37,
    "Slash": 0x38, "/": 0x38, "?": 0x38,
    "CapsLock": 0x39,
    
    # Navigation
    "Insert": 0x49, "Home": 0x4A, "PageUp": 0x4B,
    "Delete": 0x4C, "End": 0x4D, "PageDown": 0x4E,
    "Right": 0x4F, "Left": 0x50, "Down": 0x51, "Up": 0x52,
    # System
    "PrintScreen": 0x46, "ScrollLock": 0x47, "Pause": 0x48,
    "Menu": 0x65, "NumLock": 0x53,
    # Keypad
    "Keypad /": 0x54, "Keypad *": 0x55, "Keypad -": 0x56, "Keypad +": 0x57,
    "Keypad Enter": 0x58, "Keypad .": 0x63,
    "Keypad 1": 0x59, "Keypad 2": 0x5A, "Keypad 3": 0x5B,
    "Keypad 4": 0x5C, "Keypad 5": 0x5D, "Keypad 6": 0x5E,
    "Keypad 7": 0x5F, "Keypad 8": 0x60, "Keypad 9": 0x61,
    "Keypad 0": 0x62,
    # Modifier keys (standalone HID Usage Table 0xE0-0xE7)
    "Left Ctrl": 0xE0, "Left Shift": 0xE1, "Left Alt": 0xE2, "Left GUI": 0xE3,
    "Right Ctrl": 0xE4, "Right Shift": 0xE5, "Right Alt": 0xE6, "Right GUI": 0xE7,
    # Legacy alias for macro events (uses different code)
    "Shift": 0x20,
}

# USB HID Consumer Page codes (for media keys)
# These use a different packet format than standard keycodes
MEDIA_KEY_CODES = {
    "PlayPause": 0xCD,
    "NextTrack": 0xB5,
    "PrevTrack": 0xB6,
    "Mute": 0xE2,
    "VolumeUp": 0xE9,
    "VolumeDown": 0xEA,
}

# Button action types (from wired USB captures)
BUTTON_TYPE_DISABLED = 0x00
BUTTON_TYPE_MOUSE = 0x01
BUTTON_TYPE_DPI_LEGACY = 0x02 # Acts as Keyboard (Simple) but specific combos trigger DPI!
BUTTON_TYPE_SPECIAL = 0x04  # Fire Key, Triple Click - uses (delay_ms, repeat_count)
BUTTON_TYPE_KEYBOARD = 0x05 # Standard Keyboard (Complex/Media) - Safe for normal keys
BUTTON_TYPE_MEDIA = 0x05    # Alias for Keyboard
BUTTON_TYPE_MACRO = 0x06
BUTTON_TYPE_POLL_RATE = 0x07  # Toggle polling rate
BUTTON_TYPE_RGB_TOGGLE = 0x08  # Toggle RGB LED

# RGB LED modes
RGB_MODE_OFF = 0x00
RGB_MODE_STEADY = 0x01
# These are application-facing values retained for compatibility.  The Areson
# EEPROM uses 0x02 for Respiration and 0x03 for Neon, so animated modes are
# translated by rgb_mode_to_hardware() rather than written verbatim.
RGB_MODE_NEON = 0x02
RGB_MODE_BREATHING = 0x03
RGB_EFFECT_SPEED_DEFAULT = 3
RGB_EFFECT_SPEED_MIN = 1
RGB_EFFECT_SPEED_MAX = 5
RGB_MIN_BRIGHTNESS = 0  # build_rgb encodes this as the captured raw minimum 0x01
# Raw minimum is excellent for a single channel but the physical LED's green
# channel overwhelms red there, making mixed battery colors look pure green.
# Ten percent is the next capture-confirmed setting and remains deliberately
# dim while rendering yellow/orange transitions reliably.
BATTERY_LED_BRIGHTNESS = 10

# ASCII to HID mapping for Quick Text Macro
# Maps char -> (keycode, modifier_mask)
ASCII_TO_HID = {
    # Lowercase
    **{chr(ord('a') + i): (0x04 + i, 0) for i in range(26)},
    # Uppercase (Shift)
    **{chr(ord('A') + i): (0x04 + i, MODIFIER_SHIFT) for i in range(26)},
    # Numbers
    '1': (0x1E, 0), '2': (0x1F, 0), '3': (0x20, 0), '4': (0x21, 0), '5': (0x22, 0),
    '6': (0x23, 0), '7': (0x24, 0), '8': (0x25, 0), '9': (0x26, 0), '0': (0x27, 0),
    # Symbols (Assuming US Layout)
    '!': (0x1E, MODIFIER_SHIFT), '@': (0x1F, MODIFIER_SHIFT), '#': (0x20, MODIFIER_SHIFT),
    '$': (0x21, MODIFIER_SHIFT), '%': (0x22, MODIFIER_SHIFT), '^': (0x23, MODIFIER_SHIFT),
    '&': (0x24, MODIFIER_SHIFT), '*': (0x25, MODIFIER_SHIFT), '(': (0x26, MODIFIER_SHIFT),
    ')': (0x27, MODIFIER_SHIFT),
    ' ': (0x2C, 0), '.': (0x37, 0), ',': (0x36, 0), '?': (0x38, MODIFIER_SHIFT),
    '<': (0x36, MODIFIER_SHIFT), '>': (0x37, MODIFIER_SHIFT),
    '/': (0x38, 0), ';': (0x33, 0), ':': (0x33, MODIFIER_SHIFT), "'": (0x34, 0),
    '"': (0x34, MODIFIER_SHIFT), '[': (0x2F, 0), '{': (0x2F, MODIFIER_SHIFT),
    ']': (0x30, 0), '}': (0x30, MODIFIER_SHIFT), '\\': (0x31, 0), '|': (0x31, MODIFIER_SHIFT),
    '-': (0x2D, 0), '_': (0x2D, MODIFIER_SHIFT), '=': (0x2E, 0), '+': (0x2E, MODIFIER_SHIFT),
    '`': (0x35, 0), '~': (0x35, MODIFIER_SHIFT),
    '\n': (0x28, 0), '\r': (0x28, 0), '\t': (0x2B, 0),
}

ASCII_FROM_HID: dict[tuple[int, bool], str] = {}
for _character, (_usage, _modifier) in ASCII_TO_HID.items():
    # Prefer newline to its carriage-return alias in text previews.
    if _character == '\r':
        continue
    ASCII_FROM_HID.setdefault(
        (_usage, bool(_modifier & MODIFIER_SHIFT)), _character)



# Macro Repeat Modes (from Windows USB captures)
MACRO_REPEAT_ONCE = 0x01     # Play macro once
MACRO_REPEAT_COUNT = 0x02    # Multi-repeat mode (GUI sentinel)
MACRO_REPEAT_HOLD = 0xFE     # Repeat while button held
MACRO_REPEAT_TOGGLE = 0xFF   # Toggle on/off
# Note: Any value 0x01-0xFD is interpreted as a repeat count.
MACRO_SLOT_SIZE = 0x180
MACRO_HEADER_SIZE = 0x20
MACRO_TERMINATOR_SIZE = 4

# Stored macros do not use the HID report modifier byte used by direct button
# bindings.  These are the one-byte codes emitted by the vendor driver's
# StMacro_To_HdMacro converter.  Left/right GUI collapse to the same 0x08 code.
MACRO_MODIFIER_CODES = {
    "Left Ctrl": 0x01,
    "Left Shift": 0x02,
    "Left Alt": 0x04,
    "GUI": 0x08,
    "Right Ctrl": 0x10,
    "Right Shift": 0x20,
    "Right Alt": 0x40,
}
MACRO_MODIFIER_NAMES = {
    code: name for name, code in MACRO_MODIFIER_CODES.items()
}
MACRO_SHIFT_CODES = frozenset((
    MACRO_MODIFIER_CODES["Left Shift"],
    MACRO_MODIFIER_CODES["Right Shift"],
))
MACRO_NON_TEXT_MODIFIER_CODES = frozenset(
    code for code in MACRO_MODIFIER_NAMES if code not in MACRO_SHIFT_CODES
)

# Backward-compatible name used by the text builder.  Existing captures of
# shifted text use the vendor's right-Shift code, so keep generating that exact
# byte while accepting both left and right Shift everywhere else.
MACRO_SHIFT_CODE = MACRO_MODIFIER_CODES["Right Shift"]
MACRO_MIN_DELAY_MS = 3
MACRO_MAX_EVENTS = (
    MACRO_SLOT_SIZE - MACRO_HEADER_SIZE - MACRO_TERMINATOR_SIZE
) // 5


# Mapping of Side Buttons (1-12) to internal Macro Slot Indices
# Derived from USB Capture "macros set to all 12 buttons.pcapng"
# Gaps exist at 6, 7, 10, 11 (Offsets 0x78, 0x7C, 0x88, 0x8C seem skipped/reserved)
SIDE_BUTTON_INDICES = [
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05,  # Buttons 1-6
    0x08, 0x09,                          # Buttons 7-8
    0x0C, 0x0D, 0x0E, 0x0F               # Buttons 9-12
]


def calc_checksum(prefix: Iterable[int]) -> int:
    return (CHECKSUM_BASE - (sum(prefix) & 0xFF)) & 0xFF


def build_report(command: int, payload: Iterable[int]) -> bytes:
    """Build one 17-byte request feature report.

    Byte 2 is reserved and is part of the command payload.  EEPROM commands
    use bytes 3..4 as one big-endian 16-bit address; referring to them as a
    profile and offset obscured the fact that this model has one profile.
    """
    r = bytearray(REPORT_LEN)
    r[0] = REPORT_ID
    r[1] = command & 0xFF
    
    # Payload
    payload_bytes = bytes(payload)
    if len(payload_bytes) > 14:
        raise ValueError("report payload must be at most 14 bytes")
    r[2:2 + len(payload_bytes)] = payload_bytes
    
    # Packet Checksum
    s_sum = sum(r[0:16]) & 0xFF
    r[16] = (CHECKSUM_BASE - s_sum) & 0xFF
    return bytes(r)

def build_simple(command: int) -> bytes:
    return build_report(command, bytes(14))


def report_checksum_valid(report: Iterable[int]) -> bool:
    raw = bytes(report)
    return len(raw) == REPORT_LEN and (sum(raw) & 0xFF) == CHECKSUM_BASE


def build_memory_write(address: int, data: bytes) -> bytes:
    """Build an EEPROM write for an absolute 16-bit address."""
    if not 0 <= address <= 0xFFFF:
        raise ValueError("address must be 0x0000..0xffff")
    if not 1 <= len(data) <= MAX_DATA_LEN:
        raise ValueError(f"write data must contain 1..{MAX_DATA_LEN} bytes")
    payload = bytes([
        0x00,
        (address >> 8) & 0xFF,
        address & 0xFF,
        len(data),
    ]) + data.ljust(MAX_DATA_LEN, b"\x00")
    return build_report(CMD_WRITE, payload)


def build_flash_write(page: int, offset: int, data: bytes) -> bytes:
    """Compatibility wrapper around :func:`build_memory_write`."""
    return build_memory_write(((page & 0xFF) << 8) | (offset & 0xFF), data)


def build_flash_read(page: int, offset: int, length: int) -> bytes:
    """Build a memory read; its response is interrupt-IN report ``0x09``."""
    if not 1 <= length <= MAX_DATA_LEN:
        raise ValueError(f"read length must be 1..{MAX_DATA_LEN}")
    payload = bytes([0x00, page & 0xFF, offset & 0xFF, length & 0xFF]) + bytes(10)
    return build_report(CMD_READ, payload)


def build_challenge(challenge: bytes) -> bytes:
    if len(challenge) != 4:
        raise ValueError("challenge must be exactly four bytes")
    return build_report(CMD_CHALLENGE, bytes([0, 0, 0, 4]) + challenge + bytes(6))


def challenge_response(challenge: bytes) -> bytes:
    """Return the response expected by the vendor application's check."""
    if len(challenge) != 4:
        raise ValueError("challenge must be exactly four bytes")
    a, b, c, d = challenge
    return bytes(((a + b + 5) & 0xFF, (2 * b + c) & 0xFF,
                  (3 * c + d) & 0xFF, (4 * d + a) & 0xFF))


def build_notify_enable() -> bytes:
    return build_report(CMD_NOTIFY, bytes([0, 0, 0, 1, 1]) + bytes(9))


def _definition_write_packets(code_hi: int, code_lo: int, body: bytes) -> list[bytes]:
    packets = []
    address = ((code_hi & 0xFF) << 8) | (code_lo & 0xFF)
    for start in range(0, len(body), MAX_DATA_LEN):
        packets.append(build_memory_write(address + start, body[start:start + MAX_DATA_LEN]))
    return packets


def _definition_checksum(events: bytes, count: int) -> int:
    return calc_checksum(bytes([count]) + events)


def build_key_binding(code_hi: int, code_lo: int, hid_key: int,
                      modifier: int = 0x00) -> list[bytes]:
    """Build the event-definition writes for one keyboard binding.
    
    Args:
        code_hi: High byte of keyboard region address (page)
        code_lo: Low byte of keyboard region address (offset)
        hid_key: HID keycode to bind
        modifier: Modifier byte (combination of MODIFIER_CTRL/SHIFT/ALT/WIN)
    
    Based on captures:
    - shift-1: 08 07 00 01 00 0a 04 80 02 00 81 1e 00 40 02 00 [checksum]
    - ctrl-alt-1: 08 07 00 01 00 0a 06 80 01 00 80 04 00 81 1e [checksum]
    """
    
    if not 0 <= hid_key <= 0xFF:
        raise ValueError("hid_key must fit in one byte")
    if modifier & ~0x0F:
        raise ValueError("modifier may contain Ctrl, Shift, Alt, and Win only")

    # The firmware does not accept a combined modifier mask as one event.  The
    # Windows utility emits one event for every set bit, in this order.
    modifier_values = [bit for bit in (MODIFIER_CTRL, MODIFIER_SHIFT,
                                       MODIFIER_ALT, MODIFIER_WIN)
                       if modifier & bit]
    events = bytearray()
    for value in modifier_values:
        events.extend((0x80, value, 0x00))
    events.extend((0x81, hid_key, 0x00))
    for value in modifier_values:
        events.extend((0x40, value, 0x00))
    events.extend((0x41, hid_key, 0x00))

    count = 2 + 2 * len(modifier_values)
    body = bytes([count]) + bytes(events)
    body += bytes([_definition_checksum(events, count)])
    return _definition_write_packets(code_hi, code_lo, body)


def build_consumer_binding(code_hi: int, code_lo: int, usage: int) -> list[bytes]:
    """Build a two-event USB Consumer Page definition (media key)."""
    if not 0 <= usage <= 0xFFFF:
        raise ValueError("consumer usage must fit in 16 bits")
    lo, hi = usage & 0xFF, (usage >> 8) & 0xFF
    events = bytes((0x82, lo, hi, 0x42, lo, hi))
    count = 2
    body = bytes([count]) + events + bytes([_definition_checksum(events, count)])
    return _definition_write_packets(code_hi, code_lo, body)

def rgb_mode_to_hardware(mode: int) -> int:
    """Translate an application lighting mode to the Areson EEPROM value."""
    mapping = {
        RGB_MODE_OFF: 0x00,
        RGB_MODE_STEADY: 0x01,
        RGB_MODE_NEON: 0x03,
        RGB_MODE_BREATHING: 0x02,
    }
    if mode not in mapping:
        raise ValueError(f"unsupported RGB mode {mode}")
    return mapping[mode]


def rgb_mode_from_hardware(mode: int) -> int:
    """Translate an Areson EEPROM lighting value to the application mode."""
    mapping = {
        0x00: RGB_MODE_OFF,
        0x01: RGB_MODE_STEADY,
        0x02: RGB_MODE_BREATHING,
        0x03: RGB_MODE_NEON,
    }
    return mapping.get(mode, RGB_MODE_OFF)


def build_rgb(r: int, g: int, b: int, mode: int = RGB_MODE_STEADY,
              brightness: int = 100) -> bytes:
    """Build the primary RGB LED EEPROM record.
    
    Args:
        r, g, b: Color values 0-255
        mode: RGB_MODE_OFF (0), RGB_MODE_STEADY (1), RGB_MODE_NEON (2), RGB_MODE_BREATHING (3)
        brightness: Brightness percentage 0-100
    
    Packet formats (from USB captures):
    
    Steady/Respiration/Neon (offset 0x54):
    [00, 00, 54, 08, R, G, B, ColorChk, Mode, ModeChk, B1, B2, 00, 00]
    - Hardware mode: 0x01=Steady, 0x02=Respiration, 0x03=Neon
    - ModeChk = (0x55 - Mode) & 0xFF
    - ColorChk = (0x55 - (R + G + B)) & 0xFF
    - B1 = brightness * 3, B2 = (0x55 - B1) & 0xFF
    
    Off (offset 0x58):
    [00, 00, 58, 02, 00, 55, 00, 00, 00, 00, 00, 00, 00, 00]

    Animated modes also need the speed record at 0x5C; callers applying a
    complete effect should use :func:`build_rgb_packets`.
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    if mode == RGB_MODE_OFF:
        # Off mode uses special packet at offset 0x58
        payload = bytes([
            0x00, 0x00, 0x58, 0x02, 0x00, 0x55,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        ])
    else:
        # All enabled modes store their color/mode/brightness at offset 0x54.
        # Calculate Color Checksum
        color_sum = (r + g + b) & 0xFF
        color_chk = (0x55 - color_sum) & 0xFF
        
        # Brightness encoding
        b1 = max(1, min(255, int(brightness * 3)))
        b2 = (0x55 - b1) & 0xFF
        
        hw_mode = rgb_mode_to_hardware(mode)
        mode_chk = (0x55 - hw_mode) & 0xFF
        
        payload = bytes([
            0x00,
            0x00,
            0x54,       # RGB offset for Steady/Neon
            0x08,       # Data marker
            r,
            g,
            b,
            color_chk,  # Checksum for color
            hw_mode,    # 0x01=Steady, 0x02=Respiration, 0x03=Neon
            mode_chk,
            b1,         # Brightness value
            b2,         # Brightness complement
            0x00,
            0x00,
        ])
    
    return build_report(0x07, payload)


def build_rgb_effect_speed(speed: int = RGB_EFFECT_SPEED_DEFAULT) -> bytes:
    """Build the captured Areson animation-speed record at offset 0x005C."""
    if not RGB_EFFECT_SPEED_MIN <= speed <= RGB_EFFECT_SPEED_MAX:
        raise ValueError(
            f"effect speed must be {RGB_EFFECT_SPEED_MIN}..{RGB_EFFECT_SPEED_MAX}")
    payload = bytes([
        0x00, 0x00, 0x5C, 0x02, speed, (0x55 - speed) & 0xFF,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ])
    return build_report(CMD_WRITE, payload)


def build_rgb_packets(r: int, g: int, b: int,
                      mode: int = RGB_MODE_STEADY,
                      brightness: int = 100,
                      effect_speed: int = RGB_EFFECT_SPEED_DEFAULT) -> list[bytes]:
    """Build every EEPROM record required to apply one lighting effect."""
    primary = build_rgb(r, g, b, mode, brightness)
    if mode in (RGB_MODE_BREATHING, RGB_MODE_NEON):
        return [primary, build_rgb_effect_speed(effect_speed)]
    return [primary]


def battery_gradient_rgb(percent: int) -> tuple[int, int, int]:
    """Map battery percent onto red -> yellow -> green at full saturation."""
    level = max(0, min(100, int(percent)))
    if level <= 50:
        return 255, round(255 * level / 50), 0
    return round(255 * (100 - level) / 50), 255, 0


def build_battery_indicator_rgb(percent: int) -> bytes:
    """Build a dim steady battery color with reliable mixed-channel output."""
    return build_rgb(
        *battery_gradient_rgb(percent),
        mode=RGB_MODE_STEADY,
        brightness=BATTERY_LED_BRIGHTNESS,
    )


def build_apply_binding(apply_offset: int, action_type: int,
                        action_code: int | None = None,
                        action_index: int = 0x00, modifier: int = 0x00,
                        page: int = 0x00) -> bytes:
    """Build a four-byte button action record.

    The historical argument names are retained for callers: ``modifier`` is
    action byte d1 and ``action_index`` is d2.  d3 is always the inner
    checksum; accepting guessed d3 values was the cause of broken click and
    DPI bindings.  ``action_code`` is ignored except for API compatibility.
    """
    del action_code
    d1 = modifier & 0xFF
    d2 = action_index & 0xFF
    record = bytes((action_type & 0xFF, d1, d2,
                    calc_checksum((action_type, d1, d2))))
    return build_memory_write(((page & 0xFF) << 8) | (apply_offset & 0xFF), record)


def build_keyboard_bind(apply_offset: int, page: int = 0x00) -> bytes:
    """Build a standard keyboard binding packet (Type 05).
    
    This binds the button (at apply_offset) to the Key Definition stored in Page N.
    Format:
    [00] [Page] [Offset] [Len=04] [Type=05] [D1=00] [D2=00] [D3=Chk] ...
    
    Inner Checksum (D3) = 0x55 - (Type + D1 + D2)
    """
    btype = BUTTON_TYPE_KEYBOARD # 0x05
    d1 = 0x00
    d2 = 0x00
    d3 = (0x55 - (btype + d1 + d2)) & 0xFF # 0x50
    
    return build_memory_write(((page & 0xFF) << 8) | apply_offset,
                              bytes((btype, d1, d2, d3)))


def build_mouse_param(apply_offset: int, val: int, page: int = 0x00) -> bytes:
    """Build a native mouse-button binding.
    
    Args:
        apply_offset: Button offset.
        val: Mouse button code (1=Left, 2=Right, 4=Middle, 8=Back, 10=Forward).
        page: High address byte; the exposed Areson action table uses page 0.
        
    The mask values are the same as HID mouse-button bits.  The final byte is
    simply ``0x55 - (type + mask)`` for all five supported buttons.
    """
    if val not in (0x01, 0x02, 0x04, 0x08, 0x10):
        raise ValueError("mouse mask must be Left, Right, Middle, Back, or Forward")
    return build_apply_binding(apply_offset, BUTTON_TYPE_MOUSE,
                               modifier=val, page=page)


def build_forward_back(apply_offset: int, forward: bool, page: int = 0x00) -> bytes:
    return build_mouse_param(apply_offset, 0x10 if forward else 0x08, page)


def build_dpi_control(apply_offset: int, function: int,
                      page: int = 0x00) -> bytes:
    if function not in (1, 2, 3):
        raise ValueError("DPI function must be 1=loop, 2=up, or 3=down")
    return build_apply_binding(apply_offset, BUTTON_TYPE_DPI_LEGACY,
                               modifier=function, page=page)


def build_special_binding(apply_offset: int, delay_ms: int, repeat_count: int, page: int = 0x00) -> bytes:
    """Build a special button binding (Fire Key, Triple Click, etc.).
    
    Args:
        apply_offset: Button's mouse region offset (e.g., 0x6C for button 4)
        delay_ms: Delay between repeats in milliseconds (0-255)
        repeat_count: Number of repeats (0-255)
        page: High byte of the destination address. Areson Venus Pro devices
            have only one exposed profile, whose action table is on page 0.
    
    Format from Windows capture:
    - Type = 0x04, D1 = delay_ms, D2 = repeat_count
    - D3 = 0x55 - (Type + D1 + D2)
    """
    btype = BUTTON_TYPE_SPECIAL  # 0x04
    d1 = delay_ms & 0xFF
    d2 = repeat_count & 0xFF
    d3 = (0x55 - (btype + d1 + d2)) & 0xFF
    
    return build_memory_write(((page & 0xFF) << 8) | apply_offset,
                              bytes((btype, d1, d2, d3)))


def build_poll_rate_toggle(apply_offset: int, page: int = 0x00) -> bytes:
    """Build a polling rate toggle binding for a button."""
    btype = BUTTON_TYPE_POLL_RATE  # 0x07
    d1, d2 = 0x00, 0x00
    d3 = (0x55 - (btype + d1 + d2)) & 0xFF  # = 0x4E
    
    return build_memory_write(((page & 0xFF) << 8) | apply_offset,
                              bytes((btype, d1, d2, d3)))


def build_rgb_toggle(apply_offset: int, page: int = 0x00) -> bytes:
    """Build an RGB LED toggle binding for a button."""
    btype = BUTTON_TYPE_RGB_TOGGLE  # 0x08
    d1, d2 = 0x00, 0x00
    d3 = (0x55 - (btype + d1 + d2)) & 0xFF  # = 0x4D
    
    return build_memory_write(((page & 0xFF) << 8) | apply_offset,
                              bytes((btype, d1, d2, d3)))


def build_disabled(apply_offset: int, page: int = 0x00) -> bytes:
    """Build a disabled binding for a button."""
    return build_memory_write(((page & 0xFF) << 8) | apply_offset,
                              bytes((BUTTON_TYPE_DISABLED, 0, 0, 0x55)))


@dataclass(frozen=True)
class MacroEvent:
    keycode: int
    is_down: bool
    delay_ms: int
    is_modifier: bool = False  # Modifiers use different status codes
    event_type: str = "keyboard"  # keyboard, modifier, or mouse

    @classmethod
    def mouse(cls, button_mask: int, is_down: bool, delay_ms: int) -> "MacroEvent":
        if button_mask not in (0x01, 0x02, 0x04, 0x08, 0x10):
            raise ValueError("unsupported macro mouse-button mask")
        return cls(button_mask, is_down, delay_ms, False, "mouse")

    def to_bytes(self) -> bytes:
        """Convert to the 5-byte format expected by the mouse hardware.
        Format from memory dumps: [STATUS] [KEYCODE] 0x00 [DELAY_HI] [DELAY_LO]
        
        Status codes:
        - 0x81 = Key Down, 0x41 = Key Up (regular keys)
        - 0x80 = Modifier Down, 0x40 = Modifier Up
        - 0x84 = Mouse Down, 0x44 = Mouse Up

        The vendor converter accepts event classes 0, 1, and 4 only.  Relative
        mouse movement is therefore not representable in this format.
        """
        if not 0 <= self.delay_ms <= 0xFFFF:
            raise ValueError("macro delay must be 0..65535 ms")
        event_type = "modifier" if self.is_modifier else self.event_type
        if event_type == "mouse":
            if self.keycode not in (0x01, 0x02, 0x04, 0x08, 0x10):
                raise ValueError("invalid mouse-button mask")
            status = 0x84 if self.is_down else 0x44
        elif event_type == "modifier":
            status = 0x80 if self.is_down else 0x40
        elif event_type == "keyboard":
            status = 0x81 if self.is_down else 0x41
        else:
            raise ValueError(f"unsupported macro event type: {event_type}")
        return bytes([status, self.keycode, 0x00, (self.delay_ms >> 8) & 0xFF, self.delay_ms & 0xFF])


def text_macro_requirements(text: str) -> tuple[int, tuple[str, ...]]:
    """Return the event count and unsupported characters for US-layout text."""
    event_count = 0
    unsupported: list[str] = []
    for character in text:
        mapping = ASCII_TO_HID.get(character)
        if mapping is None:
            if character not in unsupported:
                unsupported.append(character)
            continue
        _, modifier = mapping
        event_count += 4 if modifier & MODIFIER_SHIFT else 2
    return event_count, tuple(unsupported)


def build_text_macro_events(
    text: str,
    *,
    key_hold_ms: int = 35,
    delay_min_ms: int = 80,
    delay_max_ms: int | None = None,
    extra_word_pause_ms: int = 0,
    rng=None,
) -> list[MacroEvent]:
    """Build a natural press/release stream for a US-layout text macro.

    ``delay_min_ms``/``delay_max_ms`` control the time from one key's release
    to the next key.  Equal values produce fixed timing; a range produces a
    fresh random delay for each character.  Shifted characters use the exact
    modifier code and event order emitted by the vendor converter.
    """
    delay_max_ms = delay_min_ms if delay_max_ms is None else delay_max_ms
    for label, value, minimum in (
        ("key hold", key_hold_ms, MACRO_MIN_DELAY_MS),
        ("minimum inter-key delay", delay_min_ms, MACRO_MIN_DELAY_MS),
        ("maximum inter-key delay", delay_max_ms, MACRO_MIN_DELAY_MS),
        ("extra word pause", extra_word_pause_ms, 0),
    ):
        if not minimum <= value <= 0xFFFF:
            raise ValueError(f"{label} must be {minimum}..65535 ms")
    if delay_min_ms > delay_max_ms:
        raise ValueError("minimum inter-key delay cannot exceed maximum")
    if delay_max_ms + extra_word_pause_ms > 0xFFFF:
        raise ValueError("inter-key delay plus word pause exceeds 65535 ms")

    required, unsupported = text_macro_requirements(text)
    if unsupported:
        display = ", ".join(repr(character) for character in unsupported)
        raise ValueError(f"unsupported text character(s): {display}")
    if required > MACRO_MAX_EVENTS:
        raise ValueError(
            f"text needs {required} events; a macro slot holds "
            f"{MACRO_MAX_EVENTS}")

    random_source = rng if rng is not None else random.SystemRandom()
    events: list[MacroEvent] = []
    last_index = len(text) - 1
    for index, character in enumerate(text):
        keycode, modifier = ASCII_TO_HID[character]
        if index == last_index:
            inter_key_delay = MACRO_MIN_DELAY_MS
        else:
            inter_key_delay = random_source.randint(
                delay_min_ms, delay_max_ms)
            if character in (" ", "\n", "\r", "\t"):
                inter_key_delay += extra_word_pause_ms

        if modifier & MODIFIER_SHIFT:
            events.extend((
                MacroEvent(MACRO_SHIFT_CODE, True, MACRO_MIN_DELAY_MS,
                           True, "modifier"),
                MacroEvent(keycode, True, key_hold_ms),
                MacroEvent(MACRO_SHIFT_CODE, False, MACRO_MIN_DELAY_MS,
                           True, "modifier"),
                MacroEvent(keycode, False, inter_key_delay),
            ))
        else:
            events.extend((
                MacroEvent(keycode, True, key_hold_ms),
                MacroEvent(keycode, False, inter_key_delay),
            ))
    return events


def macro_events_to_text(events: Iterable[MacroEvent]) -> str:
    """Best-effort text preview for keyboard events in a hardware macro."""
    active_modifiers: set[int] = set()
    characters: list[str] = []
    for event in events:
        event_type = "modifier" if event.is_modifier else event.event_type
        if event_type == "modifier":
            if event.is_down:
                active_modifiers.add(event.keycode)
            else:
                active_modifiers.discard(event.keycode)
        elif (event_type == "keyboard" and event.is_down and
              not active_modifiers.intersection(
                  MACRO_NON_TEXT_MODIFIER_CODES)):
            shift_active = bool(
                active_modifiers.intersection(MACRO_SHIFT_CODES))
            character = ASCII_FROM_HID.get((event.keycode, shift_active))
            if character is not None:
                characters.append(character)
    return "".join(characters)


def build_macro_image(name: str, events: Iterable[MacroEvent]) -> bytes:
    """Serialize one complete, unpadded 0x180-byte-slot macro image.

    EEPROM writes may contain fewer than ten data bytes, so padding the final
    chunk is unnecessary.  In particular, padding a 69-event image would grow
    it from 381 to 390 bytes and corrupt the following slot.
    """
    event_list = tuple(events)
    if len(event_list) > MACRO_MAX_EVENTS:
        raise ValueError(
            f"a macro slot holds at most {MACRO_MAX_EVENTS} events")

    encoded_name = bytearray()
    for character in name:
        encoded_character = character.encode("utf-16-le")
        if len(encoded_name) + len(encoded_character) > 30:
            break
        encoded_name.extend(encoded_character)
    name_bytes = bytes(encoded_name)
    header = (
        bytes((len(name_bytes),))
        + name_bytes.ljust(30, b"\x00")
        + bytes((len(event_list),))
    )
    event_bytes = b"".join(event.to_bytes() for event in event_list)
    checksum = calculate_terminator_checksum(header + event_bytes,
                                             len(event_list))
    image = header + event_bytes + bytes((checksum, 0, 0, 0))
    if len(image) > MACRO_SLOT_SIZE:
        raise ValueError("serialized macro exceeds its EEPROM slot")
    return image


def build_macro_chunk(offset: int, chunk: bytes, macro_page: int = 0x03) -> bytes:
    """Build one write into the absolute macro storage region.
    
    Args:
        offset: Byte offset within the macro data region
        chunk: The data bytes to write (max 10 bytes)
        macro_page: High byte of the absolute macro address. Slots have a
            stride of ``0x180``, so odd slots begin at offset ``0x80``.
    """
    return build_memory_write(((macro_page & 0xFF) << 8) | (offset & 0xFF), chunk)


def build_macro_terminator(offset: int, checksum: int, macro_page: int = 0x03) -> bytes:
    """Build the macro terminator write packet.

    IMPORTANT: The terminator is 4 bytes: [checksum] [00] [00] [00]
    The 0x03 seen in memory dumps is the LAST EVENT's delay (3ms), NOT part of terminator!

    Args:
        offset: Byte offset where terminator should be written (after last event)
        checksum: ``(0x55 - event_count - sum(event_bytes)) & 0xff``.
        macro_page: Memory page for macro storage
    """
    tail = bytes([checksum, 0x00, 0x00, 0x00])
    return build_macro_chunk(offset, tail, macro_page)


def build_macro_bind(apply_offset: int, index: int, repeat: int = 0x01, page: int = 0x00) -> bytes:
    """Build a macro bind packet.
    
    Verified from captures:
    - Type = 0x06 (Macro)
    - D1 = macro slot index (0-based)
    - D2 = repeat count (1-253) or mode (0xFE=Hold, 0xFF=Toggle)
    - Chk = 0x55 - sum(bytes 0-2)
    """
    if not 0 <= index <= 0x0F:
        raise ValueError("macro index must be 0..15")
    if not 1 <= repeat <= 0xFF:
        raise ValueError("macro repeat must be 1..255")
    return build_apply_binding(apply_offset, BUTTON_TYPE_MACRO,
                               action_index=repeat, modifier=index, page=page)


def get_macro_slot_info(macro_index: int) -> tuple[int, int]:
    """Get the start page and offset for a macro slot.
    
    Each slot is 384 bytes (0x180).
    Base Address for Macro 0 (Index 0) is Page 0x03, Offset 0x00 (0x300).
    """
    if not 0 <= macro_index <= 15:
        raise ValueError("macro index must be 0..15")
    base_addr = 0x300
    stride = 0x180
    
    abs_addr = base_addr + (macro_index * stride)
    
    page = (abs_addr >> 8) & 0xFF
    offset = abs_addr & 0xFF
    return page, offset


def build_dpi(slot_index: int, value: int, tweak: int) -> bytes:
    if not 0 <= slot_index <= 7:
        raise ValueError("slot_index must be 0..7")
    offset = 0x0C + (slot_index * 4)
    return build_memory_write(offset, bytes((value & 0xFF, value & 0xFF,
                                             0x00, tweak & 0xFF)))


def build_dpi_stage_count(count: int) -> bytes:
    """Build the confirmed enabled-DPI-stage count record at ``0x0002``."""
    if not 1 <= count <= 8:
        raise ValueError("Areson DPI stage count must be 1..8")
    return build_memory_write(0x0002, bytes((count, calc_checksum((count,)))))


@dataclass(frozen=True)
class DeviceInfo:
    path: bytes | str
    product: str
    manufacturer: str
    vendor_id: int
    product_id: int
    serial: str
    interface_number: int = -1
    usage_page: int = 0
    usage: int = 0
    access_error: str = ""
    selection_note: str = ""

    @property
    def display_path(self) -> str:
        if isinstance(self.path, bytes):
            return self.path.decode(errors="backslashreplace")
        return self.path


@dataclass(frozen=True)
class BatteryStatus:
    level: int
    percent: int
    cable_connected: bool
    raw: bytes


class DeviceAccessError(RuntimeError):
    pass


class ProtocolError(RuntimeError):
    pass


class ProtocolTimeout(ProtocolError):
    pass


def expected_interface(vendor_id: int, product_id: int) -> int:
    return 2 if (vendor_id, product_id) == (0x04D9, 0xFC55) else 1


def expected_usage_page(vendor_id: int, product_id: int) -> int:
    return 0xFFA0 if (vendor_id, product_id) == (0x04D9, 0xFC55) else 0xFF02


def _format_open_error(path: bytes | str, exc: BaseException) -> str:
    shown = path.decode(errors="backslashreplace") if isinstance(path, bytes) else str(path)
    detail = str(exc).strip() or exc.__class__.__name__
    lowered = detail.lower()
    if "permission" in lowered or "access denied" in lowered:
        return (f"Permission denied opening {shown}. Install 99-venus-pro.rules, "
                "reload udev rules, then unplug and reconnect the mouse/receiver.")
    return (f"Cannot open config interface {shown}: {detail}. Check the udev ACL "
            "and close Wine, virtual machines, or capture tools that may have claimed it.")


def _probe_open(path: bytes | str) -> str:
    if not HIDAPI_AVAILABLE:
        return "python-hidapi is not installed"
    handle = None
    try:
        handle = hid.device()
        raw_path = path.encode() if isinstance(path, str) else path
        handle.open_path(raw_path)
        return ""
    except Exception as exc:
        return _format_open_error(path, exc)
    finally:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass


def _device_sort_key(info: DeviceInfo) -> tuple[int, int, int, str]:
    product_lower = info.product.lower()
    # Check string OR explicit PID for receiver
    is_receiver = "receiver" in product_lower or info.product_id == 0xFA07

    wanted = expected_interface(info.vendor_id, info.product_id)
    interface_rank = 0 if info.interface_number == wanted else 1
    access_rank = 1 if info.access_error else 0
    return (access_rank, 1 if is_receiver else 0, interface_rank, info.product)


def list_devices(exclude_receivers: bool = False) -> list[DeviceInfo]:
    """Enumerate only usable vendor configuration interfaces.

    A HID device exposes separate mouse, keyboard, and vendor interfaces.  The
    old fallback opened by VID/PID and then fabricated an unusable path, which
    is the direct cause of many ``open failed`` reports.  Linux hidapi always
    supplies a real hidraw path, so entries without one are never returned.
    """
    if not HIDAPI_AVAILABLE:
        return []

    devices: list[DeviceInfo] = []
    for vid, pid in sorted(SUPPORTED_DEVICE_IDS):
        try:
            entries = list(hid.enumerate(vid, pid))
        except Exception:
            continue
        if not entries:
            continue

        wanted_interface = expected_interface(vid, pid)
        wanted_page = expected_usage_page(vid, pid)
        exact = [entry for entry in entries
                 if entry.get("interface_number", -1) == wanted_interface]
        usage_matches = [entry for entry in entries
                         if entry.get("usage_page", 0) == wanted_page]
        unknown_interface = [entry for entry in entries
                             if entry.get("interface_number", -1) < 0]
        unknown_paths = {entry.get("path") for entry in unknown_interface
                         if entry.get("path")}

        if exact:
            exact_vendor_usage = [entry for entry in exact
                                  if entry.get("usage_page", 0) == wanted_page]
            candidates = exact_vendor_usage or exact
            note = ""
        elif usage_matches:
            candidates = usage_matches
            note = "Selected by vendor usage page; interface number was unavailable."
        elif len(unknown_paths) == 1:
            candidates = unknown_interface
            note = "Interface metadata unavailable; selected the only HID candidate."
        else:
            # Do not open the boot mouse/keyboard interfaces and pretend they
            # are configuration paths.
            continue

        seen_paths: set[bytes | str] = set()
        for item in candidates:
            path = item.get("path")
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            product = item.get("product_string") or DEVICE_NAMES.get((vid, pid), "Unknown")
            if exclude_receivers and (pid == 0xFA07 or "receiver" in product.lower()):
                continue
            devices.append(DeviceInfo(
                path=path,
                product=product,
                manufacturer=item.get("manufacturer_string") or "Unknown",
                vendor_id=vid,
                product_id=pid,
                serial=item.get("serial_number") or "",
                interface_number=item.get("interface_number", -1),
                usage_page=item.get("usage_page", 0),
                usage=item.get("usage", 0),
                access_error=_probe_open(path),
                selection_note=note,
            ))

    devices.sort(key=_device_sort_key)
    return devices


class VenusDevice:
    # Interrupt responses are consumed from one hidraw queue. Serializing
    # handles prevents the tray poller from stealing a configuration ACK.
    _io_lock = threading.Lock()

    def __init__(self, path: bytes | str):
        self._path = path
        self._dev = None
        self._lock_held = False
        self.last_error = ""

    def open(self) -> None:
        if self._dev is not None:
            return
        if not HIDAPI_AVAILABLE:
            raise DeviceAccessError("python-hidapi is not installed")
        if not self._io_lock.acquire(timeout=1.0):
            raise DeviceAccessError("mouse configuration interface is busy")
        self._lock_held = True
        dev = None
        try:
            dev = hid.device()
            dev.open_path(self._path.encode() if isinstance(self._path, str) else self._path)
            dev.set_nonblocking(True)
            self._dev = dev
        except Exception as exc:
            try:
                if dev is not None:
                    dev.close()
            except Exception:
                pass
            self._io_lock.release()
            self._lock_held = False
            raise DeviceAccessError(_format_open_error(self._path, exc)) from exc

    def close(self) -> None:
        if self._dev is None:
            return
        try:
            self._dev.close()
        finally:
            self._dev = None
            if self._lock_held:
                self._io_lock.release()
                self._lock_held = False

    def send(self, report: bytes) -> None:
        if self._dev is None:
            raise RuntimeError("device not open")
        if len(report) != REPORT_LEN:
            raise ValueError(f"report must be {REPORT_LEN} bytes")
        if report[0] != REPORT_ID or not report_checksum_valid(report):
            raise ValueError("invalid Areson feature report")
        written = self._dev.send_feature_report(report)
        if written is not None and written <= 0:
            raise ProtocolError("hidapi rejected the feature report")

    def _read(self, length: int, timeout_ms: int) -> bytes:
        if self._dev is None:
            raise RuntimeError("device not open")
        try:
            value = self._dev.read(length, timeout_ms)
        except TypeError:
            value = self._dev.read(length, timeout_ms=timeout_ms)
        return bytes(value or ())

    def flush_input(self) -> None:
        if self._dev is None:
            return
        while self._read(64, 1):
            pass

    def exchange(self, report: bytes, timeout_ms: int = 500) -> bytes:
        """Send report 0x08 and return its matching interrupt response 0x09."""
        self.flush_input()
        self.send(report)
        command = report[1]
        address = report[3:5]
        deadline = time.monotonic() + timeout_ms / 1000.0
        invalid_checksum_seen = False
        while time.monotonic() < deadline:
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            response = self._read(64, min(50, remaining))
            if not response:
                continue
            if len(response) < REPORT_LEN:
                continue
            response = response[:REPORT_LEN]
            if response[0] != RESPONSE_REPORT_ID or response[1] != command:
                continue
            if command in (CMD_WRITE, CMD_READ) and response[3:5] != address:
                continue
            if not report_checksum_valid(response):
                invalid_checksum_seen = True
                continue
            return response
        suffix = " (a response had a bad checksum)" if invalid_checksum_seen else ""
        raise ProtocolTimeout(f"command 0x{command:02x} timed out{suffix}")

    def send_reliable(self, report: bytes, timeout_ms: int = 500) -> bool:
        """Exchange one report and leave the capture-backed firmware gap."""
        try:
            self.exchange(report, timeout_ms)
            time.sleep(REPORT_SETTLE_SECONDS)
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def ready(self) -> bool:
        response = self.exchange(build_simple(CMD_READY))
        return response[5] >= 1 and response[6] == 1

    def authenticate(self, challenge: bytes | None = None) -> bool:
        if challenge is None:
            challenge = bytes(secrets.randbelow(100) + 1 for _ in range(4))
        response = self.exchange(build_challenge(challenge))
        return response[5] == 4 and response[6:10] == challenge_response(challenge)

    def enable_notifications(self) -> bool:
        response = self.exchange(build_notify_enable())
        return response[5] == 1 and response[6] == 1

    def start_session(self) -> bool:
        """Run the non-destructive startup sequence used by the Windows app."""
        if not self.ready() or not self.authenticate():
            return False
        self.read_flash(0x00, 0x04, 2)
        return self.enable_notifications()

    def begin_write(self) -> bool:
        """Request ready state before one or more immediately-persistent writes."""
        accepted = self.ready()
        if accepted:
            time.sleep(REPORT_SETTLE_SECONDS)
        return accepted

    def unlock(self) -> bool:
        """Deprecated safe alias for :meth:`start_session`."""
        try:
            return self.start_session()
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def query_status(self) -> BatteryStatus:
        """Read battery level (0..10) and cable/power-source flag."""
        response = self.exchange(build_simple(CMD_STATUS))
        if response[5] < 2:
            raise ProtocolError("status response is shorter than two bytes")
        level = response[6]
        if level > 10:
            raise ProtocolError(f"invalid battery step {level}; expected 0..10")
        percent = level * 10
        return BatteryStatus(level, percent, bool(response[7]), response[6:8])

    def factory_reset(self) -> None:
        """Erase settings and macros.  Call only after explicit confirmation."""
        self.exchange(build_simple(CMD_FACTORY_RESET), timeout_ms=1000)

    def read_flash(self, page: int, offset: int, length: int) -> bytes:
        """Read up to ten bytes from an EEPROM page/offset."""
        if self._dev is None:
            raise RuntimeError("device not open")
        req = build_flash_read(page, offset, length)
        response = self.exchange(req)
        data_len = response[5]
        if data_len != length or data_len > MAX_DATA_LEN:
            raise ProtocolError(
                f"read at 0x{page:02x}{offset:02x} returned invalid length {data_len}")
        return response[6:6 + data_len]


def calculate_terminator_checksum(
    data: bytes,
    event_count: int | None = None,
) -> int:
    """Calculate the checksum byte that immediately follows macro events.

    The equivalent compact formula is
    ``(0x55 - event_count - sum(events)) & 0xff``.
    """
    if event_count is None:
        event_count = data[0x1F] if len(data) > 0x1F else 0

    events_start = 0x20
    events_end = events_start + (event_count * 5)
    if events_end > len(data):
        events = data[events_start:]
    else:
        events = data[events_start:events_end]

    return (CHECKSUM_BASE - event_count - sum(events)) & 0xFF
