"""Holtek Venus MMO (04D9:FC55) USB HID Protocol Implementation.

Reverse-engineered from Windows driver hid.exe v1.3.4 binary analysis and live
device probing. Uses Interface 2 (vendor HID, Usage Page 0xFFA0) with feature
reports. Report ID 0x02 (16 bytes) and 0x03 (64 bytes). No checksums.

Communication: send_feature_report -> get_feature_report (NOT interrupt reads).

Key discovery from binary analysis: F3 writes persist to flash but DO NOT take
effect until the firmware receives a category-specific F1 commit command. The F1
commit byte 3 is a bitmask: 0x01=enter write mode, 0x02=commit buttons,
0x04=commit DPI, 0x08=commit LED, 0x10=exit/finalize.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import hid
import time


# -- Device Constants --
VENDOR_ID = 0x04D9
PRODUCT_ID = 0xFC55
INTERFACE = 2  # Vendor HID config interface

# Report IDs
RID_SHORT = 0x02  # 16 bytes total
RID_LONG = 0x03   # 64 bytes total

# Commands (byte 1 after report ID)
CMD_WRITE_CTRL = 0xF1
CMD_READ = 0xF2
CMD_WRITE_DATA = 0xF3
CMD_POLLING = 0xF5

# -- F1 Write Control Sub-commands --
# Byte 2 = 0x02 means "flash write control", byte 3 is category bitmask.
# These are the CRITICAL commit commands that make F3 writes take effect.
CTRL_ENTER_WRITE   = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x02, 0x01])  # Enter write mode
CTRL_COMMIT_BTN    = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x02, 0x02])  # Commit button writes
CTRL_COMMIT_DPI    = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x02, 0x04])  # Commit DPI writes
CTRL_COMMIT_LED    = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x02, 0x08])  # Commit LED writes
CTRL_EXIT_WRITE    = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x02, 0x10])  # Exit write mode / finalize
# Legacy aliases (byte 2 = 0x00 variants, used in post-commit cleanup)
CTRL_POST_COMMIT_1 = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x00, 0x04])
CTRL_POST_COMMIT_2 = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x00, 0x01])
CTRL_RESET         = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x00, 0x00])
CTRL_FLASH_ACK     = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x00, 0x08])

# Backward compat alias
CTRL_COMMIT = CTRL_COMMIT_BTN

# -- Memory Addresses --
# DPI summary region (status mirror, NOT used by firmware for active DPI)
ADDR_DPI_SUMMARY     = 0x0020  # 10 bytes: mirrors DPI values (not authoritative)
ADDR_DPI_STAGE       = 0x002C  # 2 bytes: [current_stage, 0x00]
ADDR_LED_SETTINGS    = 0x0032  # 5 bytes: LED mode/color settings
ADDR_LED_EXTRA       = 0x0038  # 3 bytes: additional LED config
ADDR_ACTIVE_PROFILE  = 0x003D  # 1 byte: (value & 0x7F) = active profile index

# Profile base addresses
PROFILE_BASE_ADDRS = [0x0040, 0x0100, 0x01B0, 0x0260, 0x0310]

# Per-profile DPI addresses (verified working by user testing)
# Header at profile_base: [num_stages, 0x00, current_stage_idx, 0x00]
# DPI entries at profile_base + 4: 6 bytes each [0x01, raw_dpi, color, 0, 0, 0]
# raw_dpi * 200 = DPI in CPI. color = LED color index for stage indicator.
ADDR_DPI_PROFILE = [base + 0x04 for base in PROFILE_BASE_ADDRS]
# = [0x0044, 0x0104, 0x01B4, 0x0264, 0x0314]
DPI_ENTRY_SIZE = 6  # bytes per DPI stage entry

# Per-profile LED addresses (verified from device memory dump)
# Format: [0x80, R, G, B, mode, brightness, speed, extra] = 8 bytes each
# Factory defaults: profile 0=Red, 1=Blue, 2=Green, 3=Magenta, 4=Yellow
ADDR_LED_PROFILE = [0x0448, 0x0450, 0x0458, 0x0460, 0x0468]

# LED color table at 0x0400 (used for color cycling modes)
ADDR_LED_COLOR_TABLE = 0x0400

# Per-profile button map addresses
# Each profile has: 2-byte LE count + 20×4 byte entries starting at profile_base + 0x40
ADDR_BUTTONS_PROFILE = [base + 0x40 for base in PROFILE_BASE_ADDRS]
# = [0x0080, 0x0140, 0x01F0, 0x02A0, 0x0350]

# Legacy aliases (profile 0)
ADDR_BUTTONS       = ADDR_BUTTONS_PROFILE[0]  # Button map start (2-byte count + 20x4 bytes)
ADDR_BUTTONS_DATA  = ADDR_BUTTONS + 2          # First button entry (after 2-byte count)
ADDR_BUTTONS_END   = ADDR_BUTTONS + 2 + 20*4   # End of button map region

# Legacy aliases for backward compat
ADDR_DPI = ADDR_DPI_SUMMARY
ADDR_LED = ADDR_LED_SETTINGS
ADDR_POLLING = ADDR_LED_EXTRA  # Polling is set via F5, not memory write

# Button type constants
BTN_LMB = 0x81
BTN_RMB = 0x82
BTN_MMB = 0x83
BTN_BACK = 0x84
BTN_FORWARD = 0x85
BTN_DPI_UP = 0x8A
BTN_DPI_DOWN = 0x89  # Holtek uses 0x89 (not 0x8C like Venus Pro)
BTN_PROFILE = 0x8D
BTN_KEYBOARD = 0x90
BTN_FIRE = 0x92      # Fire Key / rapid click (Holtek-specific)
BTN_DISABLED = 0x00

# Human-readable type names
BUTTON_TYPE_NAMES = {
    BTN_LMB: "Left Click",
    BTN_RMB: "Right Click",
    BTN_MMB: "Middle Click",
    BTN_BACK: "Back",
    BTN_FORWARD: "Forward",
    BTN_DPI_UP: "DPI Up",
    BTN_DPI_DOWN: "DPI Down",
    BTN_PROFILE: "Profile Switch",
    BTN_KEYBOARD: "Keyboard Key",
    BTN_FIRE: "Fire Key",
    BTN_DISABLED: "Disabled",
}

# Action name to button type constant (for GUI -> protocol)
ACTION_TO_BTN_TYPE = {
    "Left Click": BTN_LMB,
    "Right Click": BTN_RMB,
    "Middle Click": BTN_MMB,
    "Back": BTN_BACK,
    "Forward": BTN_FORWARD,
    "DPI Up": BTN_DPI_UP,
    "DPI Down": BTN_DPI_DOWN,
    "DPI Control": None,  # handled specially
    "Profile Switch": BTN_PROFILE,
    "Keyboard Key": BTN_KEYBOARD,
    "Fire Key": BTN_FIRE,
    "Disabled": BTN_DISABLED,
}


@dataclass(frozen=True)
class HoltekButtonProfile:
    label: str
    index: int  # 0-based index into the 20-button map


# 20-button memory map — derived from factory defaults read off device.
# Verified 2026-02-14 by comparing factory defaults across profiles 1-4:
#   Index 3 = Fire Key (factory 0x92), Index 5 = DPI Down (factory 0x89),
#   Index 19 = Profile Switch (factory 0x8D), Index 18 = unused (factory 0x00).
# Side buttons 1-12 at indices 6-17 (side N defaults to Numpad N, so side 8 at 6+7=13).
# Physical buttons: LMB, RMB, MMB, Fire, DPI Up, DPI Down, Side 1-12, Profile Switch = 19 buttons.
# Device firmware has 20 memory slots; index 18 has no physical button.
BUTTON_PROFILES = {
    "Button 1":  HoltekButtonProfile("Left Mouse Button", 0),
    "Button 2":  HoltekButtonProfile("Right Mouse Button", 1),
    "Button 3":  HoltekButtonProfile("Middle Mouse Button", 2),
    "Button 4":  HoltekButtonProfile("Fire Key", 3),
    "Button 5":  HoltekButtonProfile("DPI Up", 4),
    "Button 6":  HoltekButtonProfile("DPI Down", 5),
    "Button 7":  HoltekButtonProfile("Side Button 1", 6),
    "Button 8":  HoltekButtonProfile("Side Button 2", 7),
    "Button 9":  HoltekButtonProfile("Side Button 3", 8),
    "Button 10": HoltekButtonProfile("Side Button 4", 9),
    "Button 11": HoltekButtonProfile("Side Button 5", 10),
    "Button 12": HoltekButtonProfile("Side Button 6", 11),
    "Button 13": HoltekButtonProfile("Side Button 7", 12),
    "Button 14": HoltekButtonProfile("Side Button 8", 13),
    "Button 15": HoltekButtonProfile("Side Button 9", 14),
    "Button 16": HoltekButtonProfile("Side Button 10", 15),
    "Button 17": HoltekButtonProfile("Side Button 11", 16),
    "Button 18": HoltekButtonProfile("Side Button 12", 17),
    "Button 20": HoltekButtonProfile("Profile Switch", 19),
}

# Default button assignments (factory defaults from profiles 1-4).
# Side buttons 1-12 default to Numpad 1-9, 0, -, + (HID 0x59-0x62, 0x56, 0x57).
DEFAULT_BUTTON_MAP = [
    (BTN_LMB, 0x00, 0x00, 0x00),        #  0: Left Mouse Button
    (BTN_RMB, 0x00, 0x00, 0x00),        #  1: Right Mouse Button
    (BTN_MMB, 0x00, 0x00, 0x00),        #  2: Middle Mouse Button
    (BTN_FIRE, 0x03, 0x01, 0x00),       #  3: Fire Key (factory default)
    (BTN_DPI_UP, 0x00, 0x00, 0x00),     #  4: DPI Up
    (BTN_DPI_DOWN, 0x00, 0x00, 0x00),   #  5: DPI Down
    (BTN_KEYBOARD, 0x00, 0x59, 0x00),   #  6: Side 1  → Numpad 1
    (BTN_KEYBOARD, 0x00, 0x5A, 0x00),   #  7: Side 2  → Numpad 2
    (BTN_KEYBOARD, 0x00, 0x5B, 0x00),   #  8: Side 3  → Numpad 3
    (BTN_KEYBOARD, 0x00, 0x5C, 0x00),   #  9: Side 4  → Numpad 4
    (BTN_KEYBOARD, 0x00, 0x5D, 0x00),   # 10: Side 5  → Numpad 5
    (BTN_KEYBOARD, 0x00, 0x5E, 0x00),   # 11: Side 6  → Numpad 6
    (BTN_KEYBOARD, 0x00, 0x5F, 0x00),   # 12: Side 7  → Numpad 7
    (BTN_KEYBOARD, 0x00, 0x60, 0x00),   # 13: Side 8  → Numpad 8
    (BTN_KEYBOARD, 0x00, 0x61, 0x00),   # 14: Side 9  → Numpad 9
    (BTN_KEYBOARD, 0x00, 0x62, 0x00),   # 15: Side 10 → Numpad 0
    (BTN_KEYBOARD, 0x00, 0x56, 0x00),   # 16: Side 11 → Numpad -
    (BTN_KEYBOARD, 0x00, 0x57, 0x00),   # 17: Side 12 → Numpad +
    (BTN_DISABLED, 0x00, 0x00, 0x00),   # 18: (unused slot - no physical button)
    (BTN_PROFILE, 0x00, 0x00, 0x00),    # 19: Profile Switch
]

# HID keyboard scancodes (same as Venus Pro HID_KEY_USAGE for the most part)
# Reuse venus_protocol's HID_KEY_USAGE via import in the GUI
# Here we just need the mapping for building packets


# Polling rates supported by Holtek
POLLING_RATES = {
    125: 0x08,   # Code for 125Hz
    250: 0x04,   # Code for 250Hz
    500: 0x02,   # Code for 500Hz
    1000: 0x01,  # Code for 1000Hz
}

POLLING_CODE_TO_RATE = {v: k for k, v in POLLING_RATES.items()}


# -- DPI Encoding --
# From the DPI lookup table in hid.exe .rdata at 0x47e4c8:
# Formula: raw_value * 200 = DPI in CPI
# raw_value range: 0x01 (200 DPI) to 0x8C (28000 DPI)
DPI_STEP = 200  # Each raw unit = 200 DPI


def dpi_to_raw(dpi: int) -> int:
    """Convert DPI value to raw byte for the device.

    DPI must be a multiple of 200 in range [200, 28000].
    """
    raw = dpi // DPI_STEP
    if raw < 1:
        raw = 1
    elif raw > 0x8C:
        raw = 0x8C
    return raw


def raw_to_dpi(raw: int) -> int:
    """Convert raw device byte to DPI value."""
    return raw * DPI_STEP


# Common DPI presets from the Windows driver lookup table
DPI_PRESETS = {
    800: 0x04,
    1200: 0x06,
    1600: 0x08,
    2400: 0x0C,
    3200: 0x10,
    4000: 0x14,
    4800: 0x18,
    6400: 0x20,
    8000: 0x28,
    12000: 0x3C,
    16000: 0x50,
    16400: 0x52,  # Mouse's advertised max
}


class HoltekDevice:
    """Device wrapper for Holtek Venus MMO (04D9:FC55).

    Uses HID feature reports on Interface 2.
    Communication: send_feature_report + get_feature_report (no interrupt reads).
    """

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

    def send_feature(self, data: bytes) -> None:
        """Send a feature report (raw bytes including report ID)."""
        if self._dev is None:
            raise RuntimeError("device not open")
        self._dev.send_feature_report(data)

    def get_feature(self, report_id: int, size: int) -> bytes:
        """Get a feature report response."""
        if self._dev is None:
            raise RuntimeError("device not open")
        # Prepend report ID for get_feature_report
        buf = bytes([report_id]) + bytes(size - 1)
        result = self._dev.get_feature_report(report_id, size)
        return bytes(result) if result else b""

    def send_reliable(self, report: bytes, timeout_ms: int = 500) -> bool:
        """Send a feature report with a short delay (fire-and-forget).

        Holtek has no ACK mechanism. We just send and wait briefly.
        Always returns True unless an exception occurs.
        """
        self.send_feature(report)
        time.sleep(0.008)  # 8ms inter-packet delay
        return True

    def read_memory(self, addr: int, length: int) -> bytes:
        """Read device memory at the given address.

        Sends F2 read command, then gets feature report for response.
        Response format: [rid, 0x08, addr_lo, status, length, 0x00, 0xFA, 0xFA, data...]
        """
        if self._dev is None:
            raise RuntimeError("device not open")

        addr_lo = addr & 0xFF
        addr_hi = (addr >> 8) & 0xFF

        # Build read request
        req = bytearray(16)
        req[0] = RID_SHORT
        req[1] = CMD_READ
        req[2] = addr_lo
        req[3] = addr_hi
        req[4] = length & 0xFF

        self._dev.send_feature_report(bytes(req))
        time.sleep(0.005)

        # Get response
        resp = self._dev.get_feature_report(RID_SHORT, 16)
        if not resp:
            raise RuntimeError(f"Read failed at 0x{addr:04X}: no response")

        resp = bytes(resp)
        # Verify response header
        if len(resp) < 8 + length:
            raise RuntimeError(f"Read failed at 0x{addr:04X}: short response ({len(resp)} bytes)")

        # Data starts at offset 8 (after header: rid, 0x08, addr_lo, status, length, 0x00, 0xFA, 0xFA)
        return resp[8:8 + length]

    def read_memory_long(self, addr: int, length: int) -> bytes:
        """Read device memory using long (64-byte) feature reports for larger reads."""
        if self._dev is None:
            raise RuntimeError("device not open")

        addr_lo = addr & 0xFF
        addr_hi = (addr >> 8) & 0xFF

        # Build read request using short report
        req = bytearray(16)
        req[0] = RID_SHORT
        req[1] = CMD_READ
        req[2] = addr_lo
        req[3] = addr_hi
        req[4] = length & 0xFF

        self._dev.send_feature_report(bytes(req))
        time.sleep(0.005)

        # For larger reads, get response on long report ID
        if length > 8:
            resp = self._dev.get_feature_report(RID_LONG, 64)
        else:
            resp = self._dev.get_feature_report(RID_SHORT, 16)

        if not resp:
            raise RuntimeError(f"Read failed at 0x{addr:04X}: no response")

        resp = bytes(resp)
        return resp[8:8 + length]

    def write_memory(self, addr: int, data: bytes) -> None:
        """Write data to device memory using F3 command.

        Packet format: [RID, F3, addr_lo, addr_hi, length, 0x00, 0x00, 0x00, data...]
        Data starts at byte 8. Max 8 data bytes for short report, 56 for long.
        Byte 5 MUST be 0x00 or the device will STALL (EPIPE).
        """
        addr_lo = addr & 0xFF
        addr_hi = (addr >> 8) & 0xFF

        if len(data) <= 8:
            # Short report (16 bytes): 8 header + 8 data max
            pkt = bytearray(16)
            pkt[0] = RID_SHORT
            pkt[1] = CMD_WRITE_DATA
            pkt[2] = addr_lo
            pkt[3] = addr_hi
            pkt[4] = len(data)
            # pkt[5:8] = 0x00 (already zero)
            pkt[8:8 + len(data)] = data
            self.send_feature(bytes(pkt))
        else:
            # Long report (64 bytes): 8 header + 56 data max
            pkt = bytearray(64)
            pkt[0] = RID_LONG
            pkt[1] = CMD_WRITE_DATA
            pkt[2] = addr_lo
            pkt[3] = addr_hi
            pkt[4] = len(data)
            # pkt[5:8] = 0x00 (already zero)
            pkt[8:8 + len(data)] = data
            self.send_feature(bytes(pkt))
        time.sleep(0.008)

    def enter_write_mode(self) -> None:
        """Enter flash write mode. Must be called before any F3 writes."""
        self.send_feature(CTRL_ENTER_WRITE.ljust(16, b'\x00'))
        time.sleep(0.01)

    def commit_buttons(self) -> None:
        """Commit button binding writes to flash (F1 category 0x02)."""
        self.send_feature(CTRL_COMMIT_BTN.ljust(16, b'\x00'))
        time.sleep(0.01)

    def commit_dpi(self) -> None:
        """Commit DPI writes to flash (F1 category 0x04).

        This is the CRITICAL missing step. F3 writes go to flash storage
        but the firmware does NOT load them until this F1 commit is sent.
        """
        self.send_feature(CTRL_COMMIT_DPI.ljust(16, b'\x00'))
        time.sleep(0.01)

    def commit_led(self) -> None:
        """Commit LED writes to flash (F1 category 0x08).

        Like DPI, LED F3 writes persist to flash but don't affect behavior
        until this category-specific F1 commit command is sent.
        """
        self.send_feature(CTRL_COMMIT_LED.ljust(16, b'\x00'))
        time.sleep(0.01)

    def exit_write_mode(self) -> None:
        """Exit write mode / finalize (F1 category 0x10)."""
        self.send_feature(CTRL_EXIT_WRITE.ljust(16, b'\x00'))
        time.sleep(0.01)

    def commit_writes(self, categories: int = 0x0E, reset: bool = True) -> None:
        """Commit flash writes with category-specific F1 commands.

        Args:
            categories: Bitmask of categories to commit.
                0x02 = buttons, 0x04 = DPI, 0x08 = LED.
                Default 0x0E = all three (buttons + DPI + LED).
            reset: If True, send device reset after commit so firmware
                reloads settings from flash. The device will USB-disconnect
                and reconnect — the handle becomes invalid after this.

        The Windows driver sends individual category commits after each
        group of related F3 writes, then triggers a device reset so the
        firmware reloads the new settings from flash.
        """
        if categories & 0x02:
            self.commit_buttons()
        if categories & 0x04:
            self.commit_dpi()
        if categories & 0x08:
            self.commit_led()
        self.exit_write_mode()
        if reset:
            self.reset_device()

    def reset_device(self) -> None:
        """Trigger a device reset so firmware reloads settings from flash.

        Sends [F1, 0x00, 0x00] which causes the device to USB-disconnect
        and reconnect. After this call, the device handle is INVALID —
        caller must close() and reopen on the new hidraw path.
        """
        self.send_feature(CTRL_RESET.ljust(16, b'\x00'))
        # Device disconnects immediately — no delay needed

    def set_polling_rate(self, rate: int) -> None:
        """Set polling rate directly using F5 command.

        This takes effect immediately (no F1 commit needed).
        """
        code = POLLING_RATES.get(rate)
        if code is None:
            raise ValueError(f"Unsupported polling rate: {rate}Hz")
        pkt = bytearray(16)
        pkt[0] = RID_SHORT
        pkt[1] = CMD_POLLING
        pkt[2] = code
        self.send_feature(bytes(pkt))
        time.sleep(0.10)  # Windows driver uses 100ms delay after polling change

    # -- DPI Methods (verified by user testing 2026-02-14) --

    def read_active_profile(self) -> int:
        """Read the active profile index (0-4)."""
        data = self.read_memory(ADDR_ACTIVE_PROFILE, 1)
        return data[0] & 0x7F

    def read_dpi_stages(self, profile: int = 0) -> list[int]:
        """Read DPI stage values from the per-profile region.

        Header at profile_base: [num_stages, 0x00, current_idx, 0x00]
        Entries at profile_base+4: 6 bytes each [0x01, raw_dpi, color, 0, 0, 0]

        Returns:
            List of DPI values in CPI (e.g., [800, 1600, 3200, ...]).
        """
        if profile < 0 or profile > 4:
            raise ValueError(f"Profile must be 0-4, got {profile}")

        base = PROFILE_BASE_ADDRS[profile]

        # Read header to get stage count
        header = self.read_memory(base, 4)
        num_stages = header[0]
        if num_stages == 0 or num_stages > 10:
            num_stages = 5  # fallback

        # Read DPI entries (6 bytes each, starting at base+4)
        entry_addr = base + 4
        total_bytes = num_stages * DPI_ENTRY_SIZE
        # Read in chunks
        raw_data = bytearray()
        for offset in range(0, total_bytes, 8):
            addr = entry_addr + offset
            chunk = self.read_memory(addr, min(8, total_bytes - offset))
            raw_data.extend(chunk)

        dpi_list = []
        for i in range(num_stages):
            entry_start = i * DPI_ENTRY_SIZE
            if entry_start + 1 >= len(raw_data):
                break
            raw_dpi = raw_data[entry_start + 1]  # byte 1 = raw DPI value
            if raw_dpi == 0:
                break
            dpi_list.append(raw_to_dpi(raw_dpi))
        return dpi_list

    def read_current_dpi_stage(self, profile: int = 0) -> int:
        """Read the current DPI stage index from per-profile header."""
        base = PROFILE_BASE_ADDRS[profile] if 0 <= profile <= 4 else PROFILE_BASE_ADDRS[0]
        header = self.read_memory(base, 4)
        return header[2]  # byte 2 = current stage index

    def write_dpi_stages(self, dpi_values: list[int], profile: int = 0) -> None:
        """Write DPI stage values to the per-profile region and commit.

        Per-profile DPI at profile_base + 4, 6 bytes per entry:
        [0x01, raw_dpi, 0x00, 0x00, 0x00, 0x00]

        Args:
            dpi_values: List of DPI values in CPI (multiples of 200).
            profile: Profile index (0-4).
        """
        if profile < 0 or profile > 4:
            raise ValueError(f"Profile must be 0-4, got {profile}")
        if not dpi_values:
            raise ValueError("At least one DPI value required")
        if len(dpi_values) > 10:
            raise ValueError("Maximum 10 DPI stages")

        base = PROFILE_BASE_ADDRS[profile]

        # Write header: [num_stages, 0x00, current_stage=0, 0x00]
        self.write_memory(base, bytes([len(dpi_values), 0x00, 0x00, 0x00]))

        # Build 6-byte entries
        entry_data = bytearray()
        for dpi in dpi_values:
            entry_data.extend([0x01, dpi_to_raw(dpi), 0x00, 0x00, 0x00, 0x00])

        # Write entries at base+4 in 8-byte chunks
        entry_addr = base + 4
        for offset in range(0, len(entry_data), 8):
            chunk = bytes(entry_data[offset:offset + 8])
            self.write_memory(entry_addr + offset, chunk)

        # Commit DPI and reset
        self.commit_dpi()
        self.exit_write_mode()
        self.reset_device()

    def set_current_dpi_stage(self, stage: int) -> None:
        """Set the active DPI stage index.

        Writes to address 0x002C and commits with F1 enter-write (0x01).
        """
        self.write_memory(ADDR_DPI_STAGE, bytes([stage, 0x00]))
        self.send_feature(CTRL_ENTER_WRITE.ljust(16, b'\x00'))
        time.sleep(0.01)

    # -- LED Methods (corrected from binary analysis) --

    def read_led_settings(self, profile: int = 0) -> dict:
        """Read LED settings from the per-profile address.

        Per-profile LED at 0x0448 + profile * 8, format:
        [0x80, R, G, B, mode, brightness, speed, extra]
        """
        if profile < 0 or profile > 4:
            raise ValueError(f"Profile must be 0-4, got {profile}")

        addr = ADDR_LED_PROFILE[profile]
        data = self.read_memory(addr, 8)

        return {
            'r': data[1],
            'g': data[2],
            'b': data[3],
            'mode': data[4],
            'brightness': data[5],
            'speed': data[6],
            'raw': bytes(data),
        }

    def write_led_settings(self, r: int, g: int, b: int,
                           mode: int = 3, brightness: int = 5,
                           speed: int = 1, profile: int = 0) -> None:
        """Write LED configuration and commit to flash.

        Per-profile LED at 0x0448 + profile * 8 (8 bytes).
        Format: [0x80, R, G, B, mode, brightness, speed, extra]

        Factory defaults per profile:
            0: Red (FF,00,00), 1: Blue (00,00,FF), 2: Green (00,FF,00),
            3: Magenta (FF,00,FF), 4: Yellow (FF,FF,00)
            All with mode=3, brightness=5, speed=1, extra=3.

        Args:
            r, g, b: Color values (0-255).
            mode: LED mode (factory default 3).
            brightness: Brightness level (factory default 5).
            speed: Animation speed (factory default 1).
            profile: Profile index (0-4).
        """
        if profile < 0 or profile > 4:
            raise ValueError(f"Profile must be 0-4, got {profile}")

        # Write per-profile LED at 0x0448 + profile * 8
        addr = ADDR_LED_PROFILE[profile]
        led_data = bytes([0x80, r & 0xFF, g & 0xFF, b & 0xFF,
                          mode & 0xFF, brightness & 0xFF,
                          speed & 0xFF, 0x03])
        self.write_memory(addr, led_data)

        # Commit LED changes and reset so firmware reloads them
        self.commit_led()
        self.exit_write_mode()
        self.reset_device()


def read_all_config(device: HoltekDevice, profile: int | None = None) -> dict:
    """Read full device configuration for a specific profile.

    Args:
        device: Open HoltekDevice instance.
        profile: Profile index (0-4). If None, reads the active profile from device.

    Returns dict with keys: 'dpi_stages', 'dpi_stage_current', 'active_profile',
    'led', 'buttons', 'raw_button_data', 'dpi_raw', 'led_raw'
    """
    config = {}

    # Read active profile from device
    config['active_profile'] = device.read_active_profile()

    # Use specified profile or fall back to active
    if profile is not None and 0 <= profile <= 4:
        read_profile = profile
    else:
        read_profile = config['active_profile']

    # Read DPI stages for the selected profile
    try:
        config['dpi_stages'] = device.read_dpi_stages(read_profile)
    except Exception:
        config['dpi_stages'] = []

    # Read current DPI stage index
    try:
        config['dpi_stage_current'] = device.read_current_dpi_stage(read_profile)
    except Exception:
        config['dpi_stage_current'] = 0

    # Read LED settings from per-profile address
    try:
        config['led'] = device.read_led_settings(read_profile)
    except Exception:
        config['led'] = {}

    # Read DPI summary region (0x20-0x2F) for backward compat
    settings_data = bytearray()
    for addr in range(0x20, 0x40, 8):
        chunk = device.read_memory(addr, 8)
        settings_data.extend(chunk)
    config['dpi_raw'] = bytes(settings_data[0:16])
    config['led_raw'] = bytes(settings_data[16:32])

    # Read button map region for the selected profile
    btn_base = ADDR_BUTTONS_PROFILE[read_profile]
    btn_end = btn_base + 2 + 20 * 4  # 2-byte count + 20×4 data bytes
    button_data = bytearray()
    for addr in range(btn_base, btn_end, 8):
        chunk_len = min(8, btn_end - addr)
        chunk = device.read_memory(addr, chunk_len)
        button_data.extend(chunk)

    # Parse buttons
    config['raw_button_data'] = bytes(button_data)
    config['buttons'] = parse_button_map(button_data)

    return config


def parse_button_map(data: bytes) -> list[dict]:
    """Parse the button map from raw data starting at address 0x80.

    Format: 2-byte LE count, then count x 4-byte entries.
    Each entry: [type_lo, type_hi, code_lo, code_hi]
    """
    if len(data) < 2:
        return []

    count = data[0] | (data[1] << 8)
    buttons = []

    for i in range(min(count, 20)):
        offset = 2 + (i * 4)
        if offset + 4 > len(data):
            break

        type_lo = data[offset]
        type_hi = data[offset + 1]
        code_lo = data[offset + 2]
        code_hi = data[offset + 3]

        btn_type = type_lo  # Primary type byte
        hid_code = code_lo  # HID scancode for keyboard keys

        action = BUTTON_TYPE_NAMES.get(btn_type, f"Unknown (0x{btn_type:02X})")

        buttons.append({
            'index': i,
            'type': btn_type,
            'type_hi': type_hi,
            'code': hid_code,
            'code_hi': code_hi,
            'action': action,
            'raw': bytes(data[offset:offset + 4]),
        })

    return buttons


def build_button_entry(action: str, params: dict) -> bytes:
    """Build a 4-byte button map entry for a given action.

    Args:
        action: Action name (e.g., "Left Click", "Keyboard Key")
        params: Parameters dict (e.g., {"key": 0x04} for keyboard)

    Returns:
        4-byte entry: [type_lo, type_hi, code_lo, code_hi]
    """
    if action == "Keyboard Key":
        hid_key = params.get("key", 0)
        return bytes([BTN_KEYBOARD, 0x00, hid_key, 0x00])

    elif action == "Left Click":
        return bytes([BTN_LMB, 0x00, 0x00, 0x00])
    elif action == "Right Click":
        return bytes([BTN_RMB, 0x00, 0x00, 0x00])
    elif action == "Middle Click":
        return bytes([BTN_MMB, 0x00, 0x00, 0x00])
    elif action == "Back":
        return bytes([BTN_BACK, 0x00, 0x00, 0x00])
    elif action == "Forward":
        return bytes([BTN_FORWARD, 0x00, 0x00, 0x00])

    elif action == "DPI Control":
        func = params.get("func", 1)
        if func == 2:  # DPI Up
            return bytes([BTN_DPI_UP, 0x00, 0x00, 0x00])
        elif func == 3:  # DPI Down
            return bytes([BTN_DPI_DOWN, 0x00, 0x00, 0x00])
        else:  # DPI Loop / default
            return bytes([BTN_DPI_UP, 0x00, 0x00, 0x00])

    elif action == "Profile Switch":
        return bytes([BTN_PROFILE, 0x00, 0x00, 0x00])

    elif action == "Fire Key":
        # Holtek fire key: type 0x92, type_hi=repeat, code_lo=0x01
        repeat = params.get("repeat", 3)
        return bytes([BTN_FIRE, repeat & 0xFF, 0x01, 0x00])

    elif action == "Disabled":
        return bytes([BTN_DISABLED, 0x00, 0x00, 0x00])

    # Default: disabled
    return bytes([BTN_DISABLED, 0x00, 0x00, 0x00])


def build_write_packets(button_index: int, action: str, params: dict,
                        profile: int = 0) -> list[bytes]:
    """Build feature report packets to write a single button entry.

    The button map starts at ADDR_BUTTONS_PROFILE[profile] + 2 (after 2-byte count).
    Each button is 4 bytes: addr = base + 2 + button_index * 4.

    Returns list of raw feature report bytes (F3 commands).
    """
    entry = build_button_entry(action, params)
    base = ADDR_BUTTONS_PROFILE[profile] if 0 <= profile <= 4 else ADDR_BUTTONS_PROFILE[0]
    addr = base + 2 + (button_index * 4)

    # Build F3 write packet (data at byte 8)
    pkt = bytearray(16)
    pkt[0] = RID_SHORT
    pkt[1] = CMD_WRITE_DATA
    pkt[2] = addr & 0xFF
    pkt[3] = (addr >> 8) & 0xFF
    pkt[4] = len(entry)  # length
    # pkt[5:8] = 0x00 (reserved, must be zero)
    pkt[8:8 + len(entry)] = entry

    return [bytes(pkt)]


def build_button_map_packets(buttons: list[tuple[str, dict]],
                             profile: int = 0) -> list[bytes]:
    """Build packets to write the full button map.

    Args:
        buttons: List of (action, params) tuples for all 20 buttons.
        profile: Profile index (0-4).

    Returns list of F3 write packets.
    """
    packets = []
    base = ADDR_BUTTONS_PROFILE[profile] if 0 <= profile <= 4 else ADDR_BUTTONS_PROFILE[0]

    # Write count first (2 bytes LE at base address)
    count = len(buttons)
    count_pkt = bytearray(16)
    count_pkt[0] = RID_SHORT
    count_pkt[1] = CMD_WRITE_DATA
    count_pkt[2] = base & 0xFF
    count_pkt[3] = (base >> 8) & 0xFF
    count_pkt[4] = 2     # length = 2 bytes
    # count_pkt[5:8] = 0x00 (reserved)
    count_pkt[8] = count & 0xFF
    count_pkt[9] = (count >> 8) & 0xFF
    packets.append(bytes(count_pkt))

    # Write each button entry
    for i, (action, params) in enumerate(buttons):
        packets.extend(build_write_packets(i, action, params, profile=profile))

    return packets


def build_dpi_packets(dpi_values: list[int], profile: int = 0) -> list[bytes]:
    """Build packets to write DPI configuration to the per-profile region.

    Per-profile DPI at profile_base + 4, 6 bytes per entry:
    [0x01, raw_dpi, 0x00, 0x00, 0x00, 0x00]
    Header at profile_base: [num_stages, 0x00, 0x00, 0x00]

    IMPORTANT: Caller must send F1 commit with category 0x04 (CTRL_COMMIT_DPI)
    and then reset_device() for the changes to take effect.
    """
    packets = []

    if not dpi_values or profile < 0 or profile > 4:
        return packets

    base = PROFILE_BASE_ADDRS[profile]

    # Write header: [num_stages, 0x00, current_stage=0, 0x00]
    hdr_pkt = bytearray(16)
    hdr_pkt[0] = RID_SHORT
    hdr_pkt[1] = CMD_WRITE_DATA
    hdr_pkt[2] = base & 0xFF
    hdr_pkt[3] = (base >> 8) & 0xFF
    hdr_pkt[4] = 4  # 4 header bytes
    hdr_pkt[8] = len(dpi_values)
    hdr_pkt[9] = 0x00
    hdr_pkt[10] = 0x00  # current stage = 0
    hdr_pkt[11] = 0x00
    packets.append(bytes(hdr_pkt))

    # Build 6-byte entries
    entry_data = bytearray()
    for dpi in dpi_values:
        entry_data.extend([0x01, dpi_to_raw(dpi), 0x00, 0x00, 0x00, 0x00])

    # Write entries at base+4 in 8-byte chunks
    entry_addr = base + 4
    for offset in range(0, len(entry_data), 8):
        chunk = entry_data[offset:offset + 8]
        pkt = bytearray(16)
        pkt[0] = RID_SHORT
        pkt[1] = CMD_WRITE_DATA
        pkt[2] = (entry_addr + offset) & 0xFF
        pkt[3] = ((entry_addr + offset) >> 8) & 0xFF
        pkt[4] = len(chunk)
        pkt[8:8 + len(chunk)] = chunk
        packets.append(bytes(pkt))

    return packets


def build_led_packets(r: int, g: int, b: int, mode: int = 3,
                      brightness: int = 5, speed: int = 1,
                      profile: int = 0) -> list[bytes]:
    """Build packets to write LED configuration.

    Per-profile LED at 0x0448 + profile * 8, format:
    [0x80, R, G, B, mode, brightness, speed, extra]

    IMPORTANT: Caller must send F1 commit with category 0x08 (CTRL_COMMIT_LED)
    after sending these packets for the changes to take effect.
    """
    packets = []

    if 0 <= profile <= 4:
        addr = ADDR_LED_PROFILE[profile]
        pkt = bytearray(16)
        pkt[0] = RID_SHORT
        pkt[1] = CMD_WRITE_DATA
        pkt[2] = addr & 0xFF
        pkt[3] = (addr >> 8) & 0xFF
        pkt[4] = 8  # 8 bytes
        pkt[8] = 0x80  # LED enabled flag
        pkt[9] = r & 0xFF
        pkt[10] = g & 0xFF
        pkt[11] = b & 0xFF
        pkt[12] = mode & 0xFF
        pkt[13] = brightness & 0xFF
        pkt[14] = speed & 0xFF
        pkt[15] = 0x03  # extra byte (factory default)
        packets.append(bytes(pkt))

    return packets


def build_polling_packet(rate: int) -> bytes:
    """Build F5 polling rate packet."""
    code = POLLING_RATES.get(rate)
    if code is None:
        raise ValueError(f"Unsupported polling rate: {rate}Hz")
    pkt = bytearray(16)
    pkt[0] = RID_SHORT
    pkt[1] = CMD_POLLING
    pkt[2] = code
    return bytes(pkt)


def button_action_to_gui(btn_type: int, code: int) -> tuple[str, dict]:
    """Convert Holtek button type/code to GUI action/params format.

    Returns: (action_name, params_dict) matching the GUI's format.
    """
    if btn_type == BTN_LMB:
        return "Left Click", {}
    elif btn_type == BTN_RMB:
        return "Right Click", {}
    elif btn_type == BTN_MMB:
        return "Middle Click", {}
    elif btn_type == BTN_BACK:
        return "Back", {}
    elif btn_type == BTN_FORWARD:
        return "Forward", {}
    elif btn_type == BTN_DPI_UP:
        return "DPI Control", {"func": 2}
    elif btn_type == BTN_DPI_DOWN:
        return "DPI Control", {"func": 3}
    elif btn_type == BTN_PROFILE:
        return "Profile Switch", {}
    elif btn_type == BTN_FIRE:
        return "Fire Key", {"repeat": code}
    elif btn_type == BTN_KEYBOARD:
        return "Keyboard Key", {"key": code, "mod": 0}
    elif btn_type == BTN_DISABLED:
        return "Disabled", {}
    else:
        return f"Unknown (0x{btn_type:02X})", {}


def find_device_path() -> Optional[str]:
    """Find the hidraw path for the Holtek Venus MMO device (Interface 2).

    Returns the path string, or None if not found.
    """
    for info in hid.enumerate(VENDOR_ID, PRODUCT_ID):
        if info["interface_number"] == INTERFACE:
            path = info["path"]
            return path.decode() if isinstance(path, bytes) else path
    return None


def wait_for_device(timeout: float = 5.0) -> Optional[str]:
    """Wait for the device to appear after a reset/replug.

    Args:
        timeout: Maximum seconds to wait.

    Returns:
        The new device path, or None if timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        path = find_device_path()
        if path:
            return path
        time.sleep(0.3)
    return None
