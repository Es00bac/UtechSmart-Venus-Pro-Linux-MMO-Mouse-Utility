from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import hid


VENDOR_ID = 0x25A7
PRODUCT_IDS = (0xFA07, 0xFA08)

REPORT_ID = 0x08
REPORT_LEN = 17
CHECKSUM_BASE = 0x55


@dataclass(frozen=True)
class ButtonProfile:
    label: str
    code_hi: int | None
    code_lo: int | None
    apply_offset: int | None


BUTTON_PROFILES = {
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
    "Button 13": ButtonProfile("Button 13 (Upper Side)", 0x02, 0x60, 0x8C),
    "Button 14": ButtonProfile("Button 14 (Left Click)", 0x02, 0x40, 0x88),
    "Button 15": ButtonProfile("Button 15 (Middle Click)", 0x03, 0x00, 0xA0),
    "Button 16": ButtonProfile("Button 16 (Right Click)", 0x03, 0x20, 0xA4),
}


RGB_PRESETS = {
    "Neon (Magenta)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0xFF, 0x57, 0x02, 0x53, 0x3C, 0x19, 0x00, 0x00]
    ),
    "Breathing (Magenta)": bytes(
        [0x00, 0x00, 0x5C, 0x02, 0x03, 0x52, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
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


POLLING_RATE_PAYLOADS = {
    250: bytes([0x00, 0x00, 0x00, 0x02, 0x04, 0x51, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    500: bytes([0x00, 0x00, 0x00, 0x02, 0x02, 0x53, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    1000: bytes([0x00, 0x00, 0x00, 0x02, 0x01, 0x54, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
}


DPI_PRESETS = {
    1600: {"value": 0x12, "tweak": 0x31},
    2400: {"value": 0x1B, "tweak": 0x1F},
    4900: {"value": 0x3A, "tweak": 0xE1},
    8900: {"value": 0x6A, "tweak": 0x81},
    14100: {"value": 0xA8, "tweak": 0x05},
}


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
    # Special keys
    "Enter": 0x28, "Escape": 0x29, "Backspace": 0x2A, "Tab": 0x2B, "Space": 0x2C,
    "Minus": 0x2D, "Equal": 0x2E, "LeftBracket": 0x2F, "RightBracket": 0x30,
    "Backslash": 0x31, "Semicolon": 0x33, "Quote": 0x34, "Grave": 0x35,
    "Comma": 0x36, "Period": 0x37, "Slash": 0x38,
    # Navigation
    "Insert": 0x49, "Home": 0x4A, "PageUp": 0x4B,
    "Delete": 0x4C, "End": 0x4D, "PageDown": 0x4E,
    "Right": 0x4F, "Left": 0x50, "Down": 0x51, "Up": 0x52,
    # Media keys (consumer page, may need different handling)
    "Mute": 0x7F, "VolumeUp": 0x80, "VolumeDown": 0x81,
}

# RGB LED modes
RGB_MODE_OFF = 0x00
RGB_MODE_STEADY = 0x01
RGB_MODE_BREATHING = 0x02
RGB_MODE_NEON = 0x02  # Same as breathing with different params


def calc_checksum(prefix: Iterable[int]) -> int:
    return (CHECKSUM_BASE - (sum(prefix) & 0xFF)) & 0xFF


def build_report(command: int, payload: bytes) -> bytes:
    if len(payload) != 14:
        raise ValueError(f"payload must be 14 bytes, got {len(payload)}")
    data = bytearray([REPORT_ID, command, *payload])
    data.append(calc_checksum(data))
    return bytes(data)


def build_simple(command: int) -> bytes:
    return build_report(command, bytes(14))


def build_key_binding(code_hi: int, code_lo: int, hid_key: int, modifier: int = 0x00) -> bytes:
    """Build a key binding packet.
    
    Args:
        code_hi: High byte of keyboard region address (page)
        code_lo: Low byte of keyboard region address (offset)
        hid_key: HID keycode to bind
        modifier: Modifier byte (combination of MODIFIER_CTRL/SHIFT/ALT/WIN)
    
    Based on captures:
    - shift-1: 08 07 00 01 00 0a 04 80 02 00 81 1e 00 40 02 00 [checksum]
    - ctrl-alt-1: 08 07 00 01 00 0a 06 80 01 00 80 04 00 81 1e [checksum]
    """
    if modifier == 0x00:
        # Simple key binding (no modifiers) - original format
        guard = (0x91 - (hid_key * 2)) & 0xFF
        payload = bytes(
            [
                0x00,
                code_hi,
                code_lo,
                0x08,
                0x02,
                0x81,
                hid_key,
                0x00,
                0x41,
                hid_key,
                0x00,
                guard,
                0x00,
                0x00,
            ]
        )
    else:
        # Key binding with modifiers - packet format from USB captures
        # Format: 08 07 00 [page] [offset] 0A 04 80 [modifier] 00 81 [keycode] 00 40 [modifier] 00
        payload = bytes(
            [
                0x00,
                code_hi,
                code_lo,
                0x0A,  # Different length indicator for modifier packets
                0x04,
                0x80,
                modifier,
                0x00,
                0x81,
                hid_key,
                0x00,
                0x40,
                modifier,
                0x00,
            ]
        )
    return build_report(0x07, payload)


def build_key_binding_apply(code_hi: int, code_lo: int, hid_key: int, modifier: int = 0x00) -> bytes:
    """Build the second packet for key binding with modifiers.
    
    Captures show a second packet is needed for modifier keys:
    shift-1: 08 07 00 01 0a 04 41 1e 00 8f 00 00 00 00 00 00 [checksum]
    """
    if modifier == 0x00:
        return b""  # Not needed for simple bindings
    
    # Second packet format from captures
    guard = (0x8F - hid_key) & 0xFF
    payload = bytes(
        [
            0x00,
            code_hi,
            code_lo + 0x0A,  # Offset is 0x0A after the first packet offset
            0x04,
            0x41,
            hid_key,
            0x00,
            guard,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_rgb(r: int, g: int, b: int, mode: int = RGB_MODE_STEADY, brightness: int = 100) -> bytes:
    """Build an RGB LED control packet.
    
    Args:
        r, g, b: Color values 0-255
        mode: RGB_MODE_OFF, RGB_MODE_STEADY, or RGB_MODE_BREATHING
        brightness: Brightness percentage 0-100
    
    Packet format from captures at offset 0x54:
    08 07 00 00 54 08 [R] [G] [B] [color_checksum] [mode] 54 [bright_lo] [bright_hi] 00 00 [checksum]
    
    Brightness mapping from captures:
    - 0x01 = lowest, 0xFF = highest
    - bright_hi seems to be (0x55 - brightness adjustment)
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    # Color checksum from captures appears to be: 0x56 - (color adjustments)
    color_sum = (r + g + b) & 0xFF
    color_check = (0x56 + (0xFF - color_sum)) & 0xFF
    
    # Brightness: 0% = 0x01, 100% = 0xFF
    bright_val = max(1, min(255, int(brightness * 2.55)))
    # The second brightness byte appears to track the first in captures
    bright_check = (0x55 - (bright_val >> 2)) & 0xFF
    
    payload = bytes(
        [
            0x00,
            0x00,
            0x54,  # RGB offset
            0x08,
            r,
            g,
            b,
            color_check,
            mode,
            0x54,
            bright_val,
            bright_check,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_apply_binding(apply_offset: int, action_type: int, action_code: int, action_index: int = 0x00) -> bytes:
    payload = bytes(
        [
            0x00,
            0x00,
            apply_offset,
            0x04,
            action_type,
            0x00,
            action_index,
            action_code,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_forward_back(apply_offset: int, forward: bool) -> bytes:
    payload = bytes(
        [
            0x00,
            0x00,
            apply_offset,
            0x04,
            0x01,
            0x10 if forward else 0x08,
            0x00,
            0x44 if forward else 0x4C,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


@dataclass(frozen=True)
class MacroEvent:
    keycode: int
    is_down: bool
    delay_ms: int

    def to_bytes(self) -> bytes:
        # Format: [delay_high, delay_low, status, keycode, padding]
        # status: 0x81 for down, 0x41 for up
        status = 0x81 if self.is_down else 0x41
        return bytes([(self.delay_ms >> 8) & 0xFF, self.delay_ms & 0xFF, status, self.keycode, 0x00])


def build_macro_chunk(offset: int, chunk: bytes) -> bytes:
    if len(chunk) > 10:
        raise ValueError("macro chunk must be <= 10 bytes")
    chunk_len = len(chunk)
    padded = chunk.ljust(10, b"\x00")
    # Macro write command 0x07 on page 0x03
    payload = bytes([0x00, 0x03, offset & 0xFF, chunk_len & 0xFF, *padded])
    return build_report(0x07, payload)


def build_macro_terminator() -> bytes:
    """Build the standard macro tail/terminator found in captures."""
    # From capture: 00 03 69 00 00 00
    tail = bytes([0x00, 0x03, 0x69, 0x00, 0x00, 0x00])
    return build_macro_chunk(0x64, tail)


def build_macro_bind(apply_offset: int, macro_index: int = 0x01) -> bytes:
    action_code = (0x4F - macro_index) & 0xFF
    payload = bytes(
        [
            0x00,
            0x00,
            apply_offset,
            0x04,
            0x06,
            0x00,
            macro_index & 0xFF,
            action_code,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_dpi(slot_index: int, value: int, tweak: int) -> bytes:
    if not 0 <= slot_index <= 4:
        raise ValueError("slot_index must be 0..4")
    offset = 0x0C + (slot_index * 4)
    payload = bytes(
        [
            0x00,
            0x00,
            offset & 0xFF,
            0x04,
            value & 0xFF,
            value & 0xFF,
            0x00,
            tweak & 0xFF,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    product: str
    manufacturer: str
    vendor_id: int
    product_id: int
    serial: str


def list_devices() -> list[DeviceInfo]:
    devices = []
    seen_paths = set()
    for item in hid.enumerate(VENDOR_ID, 0):
        if item["product_id"] not in PRODUCT_IDS:
            continue
        # win.md: Use HID interface 1 for configuration commands.
        if item["interface_number"] != 1:
            continue
        
        path_str = item["path"].decode() if isinstance(item["path"], bytes) else item["path"]
        if path_str in seen_paths:
            continue
        seen_paths.add(path_str)

        devices.append(
            DeviceInfo(
                path=path_str,
                product=item.get("product_string") or "Unknown",
                manufacturer=item.get("manufacturer_string") or "Unknown",
                vendor_id=item["vendor_id"],
                product_id=item["product_id"],
                serial=item.get("serial_number") or "",
            )
        )
    return devices


class VenusDevice:
    def __init__(self, path: str):
        self._path = path
        self._dev: Optional[hid.device] = None

    def open(self) -> None:
        if self._dev is not None:
            return
        dev = hid.device()
        dev.open_path(self._path.encode() if isinstance(self._path, str) else self._path)
        dev.set_nonblocking(True)
        self._dev = dev

    def close(self) -> None:
        if self._dev is None:
            return
        self._dev.close()
        self._dev = None

    def send(self, report: bytes) -> None:
        if self._dev is None:
            raise RuntimeError("device not open")
        if len(report) != REPORT_LEN:
            raise ValueError(f"report must be {REPORT_LEN} bytes")
        self._dev.send_feature_report(report)
