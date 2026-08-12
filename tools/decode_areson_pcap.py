#!/usr/bin/env python3
"""Decode Areson Venus feature requests and interrupt responses from USBPcap."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


COMMANDS = {
    0x01: "challenge",
    0x02: "notify/driver-state",
    0x03: "ready",
    0x04: "battery/status",
    0x07: "EEPROM write",
    0x08: "EEPROM read",
    0x09: "FACTORY RESET",
}


def region(address: int) -> str:
    if address == 0:
        return "polling"
    if 0x000C <= address <= 0x002B:
        return f"DPI slot {(address - 0x000C) // 4}"
    if 0x002C <= address <= 0x005F:
        return "lighting/DPI-color"
    if 0x0060 <= address <= 0x009F:
        return f"button action {(address - 0x0060) // 4}"
    if 0x0100 <= address <= 0x02FF:
        return f"event definition {(address - 0x0100) // 0x20}"
    if 0x0300 <= address <= 0x1AFF:
        slot = (address - 0x0300) // 0x180
        offset = (address - 0x0300) % 0x180
        return f"macro {slot} +0x{offset:03x}"
    return "unknown region"


def describe(packet: bytes) -> str:
    direction = "REQ" if packet[0] == 0x08 else "RSP"
    command = packet[1]
    name = COMMANDS.get(command, "unknown")
    length = packet[5]
    data = packet[6:6 + min(length, 10)]
    valid = "ok" if sum(packet) & 0xFF == 0x55 else "BAD-CHECKSUM"
    prefix = f"{direction} cmd={command:02x} {name} checksum={valid}"

    if command in (0x07, 0x08):
        address = int.from_bytes(packet[3:5], "big")
        return (f"{prefix} addr={address:04x} len={length} "
                f"data={data.hex() or '-'} [{region(address)}]")
    if command == 0x04 and direction == "RSP" and length >= 2:
        battery = (f"{data[0] * 10}%" if data[0] <= 10
                   else f"invalid-step-{data[0]}")
        return (f"{prefix} battery={battery} "
                f"cable={bool(data[1])} raw={data[:2].hex()}")
    if command == 0x01 and length == 4:
        return f"{prefix} value={data.hex()}"
    if length:
        return f"{prefix} len={length} data={data.hex()}"
    return prefix


def extract(path: Path):
    if shutil.which("tshark") is None:
        raise RuntimeError("tshark is required (install Wireshark CLI tools)")
    command = [
        "tshark", "-r", str(path),
        "-Y", "usb.data_fragment || usbhid.data",
        "-T", "fields", "-E", "separator=|", "-E", "occurrence=f",
        "-e", "frame.number", "-e", "frame.time_relative",
        "-e", "usb.endpoint_address", "-e", "usb.data_fragment",
        "-e", "usbhid.data",
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    for line in result.stdout.splitlines():
        columns = line.split("|")
        if len(columns) != 5:
            continue
        frame, timestamp, endpoint, control_data, interrupt_data = columns
        value = control_data or interrupt_data
        try:
            packet = bytes.fromhex(value.replace(":", ""))
        except ValueError:
            continue
        if len(packet) == 17 and packet[0] in (0x08, 0x09):
            yield frame, timestamp, endpoint, packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--hex", action="store_true", help="append the raw report")
    args = parser.parse_args()
    if not args.capture.is_file():
        parser.error(f"capture does not exist: {args.capture}")

    try:
        for frame, timestamp, endpoint, packet in extract(args.capture):
            raw = f" raw={packet.hex()}" if args.hex else ""
            print(f"{int(frame):6d} {float(timestamp):10.6f} ep={endpoint or 'ctrl':>4} "
                  f"{describe(packet)}{raw}")
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
