from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import hid
import time
import sys

try:
    import usb.core
    import usb.util
    PYUSB_AVAILABLE = True
except ImportError:
    PYUSB_AVAILABLE = False


def unlock_device():
    """
    Performs the 'Magic Unlock' sequence to enable writing to Macro/Page 3 memory.
    Requires root permissions to detach kernel driver.
    """
    if not PYUSB_AVAILABLE:
        print("PyUSB not available, skipping unlock.")
        return False

    print("Attempting to unlock device...")
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_IDS[1]) # FA08 Wireless
    if dev is None:
        dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_IDS[0]) # FA07 Wired
    
    if dev is None:
        print("Unlock: No device found.")
        return False

    # Detach Kernel Driver
    reattach = []
    for iface in [0, 1]:
        if dev.is_kernel_driver_active(iface):
            try:
                dev.detach_kernel_driver(iface)
                reattach.append(iface)
                print(f"Detached kernel driver from iface {iface}")
            except Exception as e:
                print(f"Failed to detach iface {iface}: {e}")
                return False

    try:
        usb.util.claim_interface(dev, 1)
        
        # Helper to send feature report to Interface 1
        def send_magic(data):
            padded = data.ljust(17, b'\x00')
            dev.ctrl_transfer(0x21, 0x09, 0x0308, 1, padded)

        # 1. Reset (Cmd 09)
        send_magic(bytes([0x08, 0x09]))
        time.sleep(0.5)
        
        # 2. Magic packet 1 (CMD 4D)
        # 08 4D 05 50 00 55 00 55 00 55 91
        send_magic(bytes([0x08, 0x4D, 0x05, 0x50, 0x00, 0x55, 0x00, 0x55, 0x00, 0x55, 0x91]))
        time.sleep(0.05)
        
        # 3. Magic packet 2 (CMD 01)
        # 08 01 00 00 00 04 56 57 3d 1b 00 00
        send_magic(bytes([0x08, 0x01, 0x00, 0x00, 0x00, 0x04, 0x56, 0x57, 0x3d, 0x1b, 0x00, 0x00]))
        time.sleep(0.05)
        
        print("Unlock sequence sent.")
        
    except Exception as e:
        print(f"Unlock error: {e}")
    finally:
        # Re-attach Check
        for iface in reattach:
            try:
                dev.attach_kernel_driver(iface)
                print(f"Re-attached kernel driver to iface {iface}")
            except:
                pass
        # Wait for device to re-enumerate after driver re-attach
        time.sleep(1.0)
    return True


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



POLLING_RATE_PAYLOADS = {
    # Polling rate encoding: code = log2(1000/rate)
    # From wired USB captures:
    # 125Hz = code 0x04 (but pattern suggests 0x03?), 250Hz = 0x02, 500Hz = 0x01, 1000Hz = 0x00
    125: bytes([0x00, 0x00, 0x00, 0x02, 0x04, 0x51, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    250: bytes([0x00, 0x00, 0x00, 0x02, 0x02, 0x53, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    500: bytes([0x00, 0x00, 0x00, 0x02, 0x01, 0x54, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    1000: bytes([0x00, 0x00, 0x00, 0x02, 0x00, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
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
    "Enter": 0x28, "Escape": 0x29, "Backspace": 0x2A, "Tab": 0x2B, "Space": 0x2C,
    "Minus": 0x2D, "Equal": 0x2E, "LeftBracket": 0x2F, "RightBracket": 0x30,
    "Backslash": 0x31, "Semicolon": 0x33, "Quote": 0x34, "Grave": 0x35,
    "Comma": 0x36, "Period": 0x37, "Slash": 0x38,
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
    # Modifiers (for macro support)
    # Note: Shift uses 0x20 in macro events, NOT 0x02 (which is the HID modifier bit)
    "Shift": 0x20,  # Left Shift for macro events
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
RGB_MODE_BREATHING = 0x02
RGB_MODE_NEON = 0x02  # Same as breathing with different params

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
    '/': (0x38, 0), ';': (0x33, 0), ':': (0x33, MODIFIER_SHIFT), "'": (0x34, 0),
    '"': (0x34, MODIFIER_SHIFT), '[': (0x2F, 0), '{': (0x2F, MODIFIER_SHIFT),
    ']': (0x30, 0), '}': (0x30, MODIFIER_SHIFT), '\\': (0x31, 0), '|': (0x31, MODIFIER_SHIFT),
    '-': (0x2D, 0), '_': (0x2D, MODIFIER_SHIFT), '=': (0x2E, 0), '+': (0x2E, MODIFIER_SHIFT),
    '`': (0x35, 0), '~': (0x35, MODIFIER_SHIFT),
    '\n': (0x28, 0), # Enter
}



# Macro Repeat Modes (from Windows USB captures)
MACRO_REPEAT_ONCE = 0x01     # Play macro once
MACRO_REPEAT_COUNT = 0x02    # Multi-repeat mode (GUI sentinel)
MACRO_REPEAT_HOLD = 0xFE     # Repeat while button held
MACRO_REPEAT_TOGGLE = 0xFF   # Toggle on/off
# Note: Any value 0x01-0xFD is interpreted as a repeat count.


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
    """Builds a 17-byte HID report with checksum at byte 16."""
    r = bytearray(REPORT_LEN)
    r[0] = REPORT_ID
    r[1] = command
    
    # Payload
    payload_bytes = bytes(payload)
    plen = min(len(payload_bytes), 14)
    r[2:2+plen] = payload_bytes[:plen]
    
    # Packet Checksum
    s_sum = sum(r[0:16]) & 0xFF
    r[16] = (CHECKSUM_BASE - s_sum) & 0xFF
    return bytes(r)

def build_simple(command: int) -> bytes:
    return build_report(command, bytes(14))


def build_flash_write(page: int, offset: int, data: bytes) -> bytes:
    """Generic flash write packet (Cmd 0x07).
    
    Payload: [0x00, Page, Offset, Len, Data...]
    Data is padded to 10 bytes.
    """
    dlen = len(data)
    payload = bytes([0x00, page & 0xFF, offset & 0xFF, dlen & 0xFF]) + data.ljust(10, b'\x00')
    return build_report(0x07, payload)


def build_flash_read(page: int, offset: int, length: int) -> bytes:
    """Build a flash memory read request.
    
    The response will arrive on the Interrupt In endpoint (Report ID 0x09).
    Max reliable length per report is 10-11 bytes.
    """
    payload = bytes([0x00, page & 0xFF, offset & 0xFF, length & 0xFF]) + bytes(10)
    return build_report(0x08, payload)


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
    
    events = bytearray()
    
    if modifier != 0:
        # Complex Binding with Modifiers - FULL 4-EVENT STREAM
        # Based on actual Windows dump analysis of Shift+A (B12):
        # Data: 04 80 02 00 81 04 00 40 02 00 41 04 00 c3
        # Format: [Count=4] [ModDn] [KeyDn] [ModUp] [KeyUp] [Guard]
        
        events.extend([0x80, modifier, 0x00])  # Event 1: ModDn
        events.extend([0x81, hid_key, 0x00])   # Event 2: KeyDn
        events.extend([0x40, modifier, 0x00])  # Event 3: ModUp
        events.extend([0x41, hid_key, 0x00])   # Event 4: KeyUp
        
        count = 4  # Always 4 events for modifier bindings
        full_payload = bytearray([count]) + events
        
        # Guard byte for complex bindings
        # From dump: Shift+A (mod=0x02, key=0x04) -> Guard=0xC3
        # Empirical formula: Simple guard + offset for event stream
        simple_guard = (0x91 - (hid_key * 2)) & 0xFF
        # The modifier events add ~0x3E offset based on analysis
        guard = (simple_guard + 0x3A) & 0xFF
        full_payload.append(guard)
        
        # Total: 1 + 12 + 1 = 14 bytes (will split into 10 + 4)
        
    else:
        # Simple Binding (No Modifiers)
        # Format: [Count=2] [KeyDn] [KeyUp] [Guard] = 8 bytes
        events.extend([0x81, hid_key, 0x00])  # KeyDn
        events.extend([0x41, hid_key, 0x00])  # KeyUp
        
        count = 2
        full_payload = bytearray([count]) + events
        
        # Guard byte: 0x91 - (key * 2)
        guard = (0x91 - (hid_key * 2)) & 0xFF
        full_payload.append(guard)
        
        # Total: 1 + 6 + 1 = 8 bytes (fits in 1 packet)
    
    # Split payload into chunks of max 10 bytes for the 0x07 write command
    packets = []
    chunk_size = 10
    total_len = len(full_payload)
    
    for i in range(0, total_len, chunk_size):
        chunk = full_payload[i : i + chunk_size]
        current_len = len(chunk)
        
        # Build Write Packet (Cmd 0x07)
        # Payload: [00] [Page] [Offset+i] [Len] [Data...]
        # Data chunk must be padded to 10 bytes to satisfy strict 14-byte payload check in build_report
        padded_chunk = chunk.ljust(10, b'\x00')
        
        pkt_payload = bytes([
            0x00,
            code_hi,
            code_lo + i,
            current_len,
        ]) + padded_chunk
        
        packets.append(build_report(0x07, pkt_payload))
        
    return packets

def build_key_binding_apply(code_hi: int, code_lo: int, hid_key: int, modifier: int = 0x00) -> bytes:
    """Build the second packet for key binding with modifiers.
    
    With Type 02 packets (which we now use exclusively), this second packet is NOT needed.
    """
    return b""


def build_rgb(r: int, g: int, b: int, mode: int = RGB_MODE_STEADY, brightness: int = 100) -> bytes:
    """Build an RGB LED control packet.
    
    Args:
        r, g, b: Color values 0-255
        mode: RGB_MODE_OFF, RGB_MODE_STEADY, or RGB_MODE_BREATHING
        brightness: Brightness percentage 0-100
    
    Packet format (Reverse Engineered 2026-01-11):
    [00, 00, 54, 08, R, G, B, ColorChk, Mode, 54, B1, B2, 00, 00]
    
    Color Checksum (Offset 9):
    - ColorChk = (0x55 - (R + G + B)) & 0xFF
    
    Mode (Offset 10):
    - 0x01 = Steady
    - 0x02 = Breathing/Neon (Assumed)
    
    Brightness (Offset 12/13):
    - B1 = percent × 3, capped at 255, minimum 1
    - B2 = (0x55 - B1) & 0xFF
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    # Calculate Color Checksum
    color_sum = (r + g + b) & 0xFF
    color_chk = (0x55 - color_sum) & 0xFF
    
    # Brightness encoding
    b1 = max(1, min(255, int(brightness * 3)))
    b2 = (0x55 - b1) & 0xFF
    
    payload = bytes(
        [
            0x00,
            0x00,
            0x54,  # RGB offset
            0x08,  # Data marker
            r,
            g,
            b,
            color_chk,  # Checksum for color
            mode,       # Mode (0x01=Steady)
            0x54,       # Constant
            b1,         # Brightness value
            b2,         # Brightness complement
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_apply_binding(apply_offset: int, action_type: int, action_code: int, action_index: int = 0x00, modifier: int = 0x00, page: int = 0x00) -> bytes:
    # Packet structure for Page 0 (or Profile N) binding entry:
    # [00] [Page] [Offset] [Len=04] [Type] [D1=Modifier] [D2=action_index] [D3=action_code] ...
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            action_type,
            modifier,      # D1: Modifier goes here (Shift=0x02, Ctrl=0x01, etc.)
            action_index,  # D2
            action_code,   # D3
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


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
    
    payload = bytes([
        0x00,
        page,
        apply_offset,
        0x04,
        btype,
        d1,
        d2,
        d3,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ])
    return build_report(0x07, payload)


def build_mouse_param(apply_offset: int, val: int, page: int = 0x00) -> bytes:
    """Build a mouse button binding (Left/Right/etc).
    
    Args:
        apply_offset: Button offset.
        val: Mouse button code (1=Left, 2=Right, 4=Middle, 8=Back, 10=Forward).
        page: Memory page (0x00, 0x40, etc).
        
    Packet structure inferred from capture contexts:
    [00] [Page] [Offset] [Len=04] [Type=01] [Val] [00] [Code] ...
    
    Code mapping (Val -> Code):
    - 0x01 (Left) -> 0xF0 (Guess/Standard?) - Wait, Forward/Back used 0x44/0x4C.
    - Let's assume Code is not critical or is derived.
    - Actually, build_forward_back uses explicit codes.
    - If capture for Left Click (Btn 14, Offset 0x7C) is confusing, let's look at build_forward_back logic.
    - Forward (0x10) -> 0x44. Back (0x08) -> 0x4c.
    - Left/Right likely follow similar pattern or are hardcoded.
    - Standard Mouse is Type 0x01.
    """
    # Just use the generic payload with Type 0x01.
    # What is D3 (Action Code)?
    # For Forward/Back it was 0x44/0x4C.
    # For Left/Right?
    # Let's assume generic Type 0x01 doesn't STRICTLY verify D3 or it is 0x00?
    # Or maybe valid vals: 
    # Left (1) -> F0?
    # Right (2) -> F1?
    # Middle (4) -> F2?
    # D3 seems to be 'Index'?
    
    # Safest bet: Just replicate build_apply_binding functionality for Type 0x01.
    # D1 = val. D2 = 00. D3 = ?
    # Let's assume D3 is not strictly checked for basic buttons or is 0.
    
    # Wait, build_forward_back sets D3=44/4C.
    # Maybe I should just expose build_apply_binding and let caller handle code?
    # But venus_gui calls build_mouse_param(offset, val).
    
    # Let's map val to something reasonable or just 0 if unknown.
    code = 0x00
    if val == 0x10: code = 0x44 # Forward
    elif val == 0x08: code = 0x4C # Back
    elif val == 0x01: code = 0xF0 # Left (Guess)
    elif val == 0x02: code = 0xF1 # Right (Guess)
    elif val == 0x04: code = 0xF2 # Middle (Guess)
        
    return build_apply_binding(apply_offset, action_type=BUTTON_TYPE_MOUSE, action_code=code, modifier=val, page=page)


def build_forward_back(apply_offset: int, forward: bool, page: int = 0x00) -> bytes:
    payload = bytes(
        [
            0x00,
            page,
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


def build_special_binding(apply_offset: int, delay_ms: int, repeat_count: int, page: int = 0x00) -> bytes:
    """Build a special button binding (Fire Key, Triple Click, etc.).
    
    Args:
        apply_offset: Button's mouse region offset (e.g., 0x6C for button 4)
        delay_ms: Delay between repeats in milliseconds (0-255)
        repeat_count: Number of repeats (0-255)
        page: Memory page (0x00 for Profile 1, 0x40 for Profile 2, etc.)
    
    Format from Windows capture:
    - Type = 0x04, D1 = delay_ms, D2 = repeat_count
    - D3 = 0x55 - (Type + D1 + D2)
    """
    btype = BUTTON_TYPE_SPECIAL  # 0x04
    d1 = delay_ms & 0xFF
    d2 = repeat_count & 0xFF
    d3 = (0x55 - (btype + d1 + d2)) & 0xFF
    
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,  # Length
            btype,
            d1,
            d2,
            d3,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_poll_rate_toggle(apply_offset: int, page: int = 0x00) -> bytes:
    """Build a polling rate toggle binding for a button."""
    btype = BUTTON_TYPE_POLL_RATE  # 0x07
    d1, d2 = 0x00, 0x00
    d3 = (0x55 - (btype + d1 + d2)) & 0xFF  # = 0x4E
    
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            btype,
            d1,
            d2,
            d3,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_rgb_toggle(apply_offset: int, page: int = 0x00) -> bytes:
    """Build an RGB LED toggle binding for a button."""
    btype = BUTTON_TYPE_RGB_TOGGLE  # 0x08
    d1, d2 = 0x00, 0x00
    d3 = (0x55 - (btype + d1 + d2)) & 0xFF  # = 0x4D
    
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            btype,
            d1,
            d2,
            d3,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_disabled(apply_offset: int, page: int = 0x00) -> bytes:
    """Build a disabled binding for a button."""
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            BUTTON_TYPE_DISABLED,  # 0x00
            0x00,
            0x00,
            0x55,  # Validation byte
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
    is_modifier: bool = False  # Modifiers use different status codes

    def to_bytes(self) -> bytes:
        """Convert to the 5-byte format expected by the mouse hardware.
        Format from memory dumps: [STATUS] [KEYCODE] 0x00 [DELAY_HI] [DELAY_LO]
        
        Status codes:
        - 0x81 = Key Down, 0x41 = Key Up (regular keys)
        - 0x80 = Modifier Down, 0x40 = Modifier Up (Shift, Ctrl, Alt)
        """
        if self.is_modifier:
            status = 0x80 if self.is_down else 0x40
        else:
            status = 0x81 if self.is_down else 0x41
        return bytes([status, self.keycode, 0x00, (self.delay_ms >> 8) & 0xFF, self.delay_ms & 0xFF])


def build_macro_chunk(offset: int, chunk: bytes, macro_page: int = 0x03) -> bytes:
    """Build a macro data chunk packet.
    
    Args:
        offset: Byte offset within the macro data region
        chunk: The data bytes to write (max 10 bytes)
        macro_page: Memory page for macro storage. 
                   From captures: button 1 uses 0x03, button 11 uses 0x18
    """
    if len(chunk) > 10:
        raise ValueError("macro chunk must be <= 10 bytes")
    chunk_len = len(chunk)
    padded = chunk.ljust(10, b"\x00")
    payload = bytes([0x00, macro_page & 0xFF, offset & 0xFF, chunk_len & 0xFF, *padded])
    return build_report(0x07, payload)


def build_flash_write(page: int, offset: int, data: bytes) -> bytes:
    """Write data to flash memory.
    
    This is a generic wrapper around the same packet structure used for macros.
    Max 10 bytes per packet.
    """
    return build_macro_chunk(offset, data, page)



def get_macro_page(apply_offset: int) -> int:
    """Calculate the macro memory page for a button.
    
    With contiguous button offsets (0x60-0x9C), the flash_index is simply:
    flash_index = (apply_offset - 0x60) // 4
    
    Macros are stored starting at page 0x03, with each button getting dedicated pages.
    From memory dumps, macros appear in slots starting at page 0x03.
    """
    flash_index = (apply_offset - 0x60) // 4
    # Simple linear mapping: button 0 -> page 0x03, button 1 -> page 0x04, etc.
    return 0x03 + flash_index


def build_macro_terminator(offset: int, checksum: int, macro_page: int = 0x03) -> bytes:
    """Build the macro terminator write packet.

    IMPORTANT: The terminator is 4 bytes: [checksum] [00] [00] [00]
    The 0x03 seen in memory dumps is the LAST EVENT's delay (3ms), NOT part of terminator!

    Args:
        offset: Byte offset where terminator should be written (after last event)
        checksum: Calculated checksum using formula: (~sum(data) - count + (index+1)^2) & 0xFF
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
    btype = 0x06
    chk = (0x55 - (btype + index + repeat)) & 0xFF
    data = bytes([btype, index, repeat, chk, 0x00, 0x00, 0x00, 0x00])
    return build_flash_write(0x00, apply_offset, data)


def get_macro_slot_info(macro_index: int) -> tuple[int, int]:
    """Get the start page and offset for a macro slot.
    
    Each slot is 384 bytes (0x180).
    Base Address for Macro 0 (Index 0) is Page 0x03, Offset 0x00 (0x300).
    """
    base_addr = 0x300
    stride = 0x180
    
    abs_addr = base_addr + (macro_index * stride)
    
    page = (abs_addr >> 8) & 0xFF
    offset = abs_addr & 0xFF
    return page, offset


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
    interface_number: int = 0  # Added to track interface


def _device_sort_key(info: DeviceInfo) -> tuple[int, int, str]:
    product_lower = info.product.lower()
    is_receiver = "receiver" in product_lower
    if info.interface_number == 1:
        interface_rank = 0
    elif info.interface_number == 0:
        interface_rank = 1
    else:
        interface_rank = 2
    return (1 if is_receiver else 0, interface_rank, info.product)


def list_devices(exclude_receivers: bool = False) -> list[DeviceInfo]:
    devices = []
    seen_paths = set()
    for item in hid.enumerate(VENDOR_ID, 0):
        if item["product_id"] not in PRODUCT_IDS:
            continue
        
        product = item.get("product_string") or "Unknown"
        
        # Filter out "Wireless Receiver" only when explicitly requested.
        if exclude_receivers and "receiver" in product.lower():
            continue
        
        # Prefer "Dual Mode Mouse" on Interface 0 (the actual configurable device)
        # Also accept Interface 1 for compatibility with some firmware versions
        interface = item.get("interface_number", -1)
        if interface not in [0, 1]:
            continue
        
        path_str = item["path"].decode() if isinstance(item["path"], bytes) else item["path"]
            
        if path_str in seen_paths:
            continue
        seen_paths.add(path_str)

        devices.append(
            DeviceInfo(
                path=path_str,
                product=product,
                manufacturer=item.get("manufacturer_string") or "Unknown",
                vendor_id=item["vendor_id"],
                product_id=item["product_id"],
                serial=item.get("serial_number") or "",
                interface_number=interface,
            )
        )
        
    # Sort devices: non-receiver first, then preferred interface (1 before 0).
    devices.sort(key=_device_sort_key)
    
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

    def send_reliable(self, report: bytes, timeout_ms: int = 500) -> bool:
        """Sends a Feature Report (0x08) and waits for acknowledgment (0x09)."""
        self.send(report)
        
        cmd = report[1]
        # For bulk writes (Cmd 07), we also want to match Page and Offset if possible
        page = report[3]
        off = report[4]
        
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            resp = self._dev.read(64, timeout_ms=50)
            if resp and resp[0] == 0x09 and resp[1] == cmd:
                # If it's a memory write, verify page/offset too
                if cmd == 0x07:
                    if resp[3] == page and resp[4] == off:
                        return True
                else:
                    return True
        return False

    def unlock(self) -> bool:
        """Sends the Magic Unlock sequence (Cmd 09, 4D, 01) reliably."""
        if self._dev is None:
            return False
            
        try:
            # 1. Reset (Cmd 09)
            self.send_reliable(build_simple(0x09))
            
            # 2. Magic Packet 1 (Cmd 4D)
            magic1 = bytes([0x08, 0x4D, 0x05, 0x50, 0x00, 0x55, 0x00, 0x55, 0x00, 0x55, 0x91])
            self.send_reliable(magic1.ljust(17, b'\x00'))
            
            # 3. Magic Packet 2 (Cmd 01)
            magic2 = bytes([0x08, 0x01, 0x00, 0x00, 0x00, 0x04, 0x56, 0x57, 0x3d, 0x1b, 0x00, 0x00])
            self.send_reliable(magic2.ljust(17, b'\x00'))
            
            return True
        except Exception as e:
            print(f"Unlock failed: {e}")
            return False

    def read_flash(self, page: int, offset: int, length: int) -> bytes:
        """Read 8 bytes from flash memory at the given page and offset.
        
        Note: Currently fixed to 8 bytes per read to ensure reliability.
        """
        if self._dev is None:
            raise RuntimeError("device not open")
        
        # Flush any pending reports
        while True:
            r = self._dev.read(128, timeout_ms=10)
            if not r:
                break
        
        req = build_flash_read(page, offset, length)
        self._dev.send_feature_report(req)
        
        # Responses arrive on Interrupt endpoint, Report ID 0x09
        # Wait up to 100ms for response
        start_time = time.time()
        while (time.time() - start_time) < 0.2: # 200ms timeout
            resp = self._dev.read(128, timeout_ms=50)
            if resp and resp[0] == 0x09 and resp[1] == 0x08:
                # Format: 09 08 00 [page] [offset] [len] [data...]
                # Check consistency
                if resp[3] == page and resp[4] == offset:
                    # Successfully read data
                    data_len = resp[5]
                    return bytes(resp[6 : 6 + data_len])
        
        raise RuntimeError(f"Flash read timeout at Page=0x{page:02X} Offset=0x{offset:02X}")


def calculate_terminator_checksum(
    data: bytes,
    event_count: int | None = None,
) -> int:
    """
    Calculate the macro terminator checksum.

    Verified from working Windows macros:
      checksum = (~sum(events) - event_count + 0x56) & 0xFF
    """
    if event_count is None:
        event_count = data[0x1F] if len(data) > 0x1F else 0

    events_start = 0x20
    events_end = events_start + (event_count * 5)
    if events_end > len(data):
        events = data[events_start:]
    else:
        events = data[events_start:events_end]

    s_sum = sum(events) & 0xFF
    inv_sum = (~s_sum) & 0xFF
    return (inv_sum - event_count + 0x56) & 0xFF


def get_macro_slot_info(index: int) -> tuple[int, int]:
    """Returns (page, offset) for a given macro index (0-based).
    Stride is 384 bytes (0x180), NOT 256 bytes.
    Base Address is 0x300 (Page 3, Offset 0).
    """
    base_addr = 0x300
    stride = 0x180
    abs_addr = base_addr + (index * stride)
    
    page = (abs_addr >> 8) & 0xFF
    offset = abs_addr & 0xFF
    return page, offset
