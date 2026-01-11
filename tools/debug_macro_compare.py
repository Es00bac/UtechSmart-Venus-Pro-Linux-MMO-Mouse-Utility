#!/usr/bin/env python3
"""
Debug script to compare our macro output vs Windows capture.
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import venus_protocol as vp

# Windows capture for "testing" macro (types "testing")
# From artifacts/txt/capture_analysis_full.txt
WINDOWS_PACKETS = [
    # Offset 0x00: name length + "testi"
    bytes.fromhex("0e74006500730074006900"),  # Note: only 10 bytes shown
    # Offset 0x0A: "ng" + padding
    bytes.fromhex("006e006700000000000000"),
    # Offset 0x14: padding
    bytes.fromhex("00000000000000000000"),
    # Offset 0x1E: padding, count=14, events start
    bytes.fromhex("000e811700005d41170000"),
    # ... more event data
]

# Windows "123" macro from dump (types "1234567890")
WINDOWS_123_HEADER = bytes.fromhex("06310032003300000000000000000000")  # offset 0x00-0x0F
WINDOWS_123_HEADER2 = bytes.fromhex("00000000000000000000000000000012")  # offset 0x10-0x1F (count=18)
WINDOWS_123_EVENTS_START = bytes.fromhex("811e00007d411e0000bb")  # First 2 events

def build_our_macro():
    """Build a simple macro the way our fixed code does it."""
    name = "Test1"
    name_utf16 = name.encode('utf-16-le')
    name_len = len(name_utf16)
    name_padded = name_utf16.ljust(30, b'\x00')[:30]

    # Events: Press '1' (0x1E) with 125ms delay, Release '1' with 3ms delay
    events = [
        bytes([0x81, 0x1E, 0x00, 0x00, 0x7D]),  # Press '1', 125ms
        bytes([0x41, 0x1E, 0x00, 0x00, 0x03]),  # Release '1', 3ms (end marker)
    ]
    event_count = len(events)

    # Header: [name_len] + [name_30b] + [event_count]
    header = bytes([name_len]) + name_padded + bytes([event_count])

    # Events
    event_data = b''.join(events)

    # Full data
    full_data = header + event_data

    # Pad to 10-byte boundary
    pad_len = (10 - (len(full_data) % 10)) % 10
    full_data += bytes(pad_len)

    # Checksum
    s_sum = sum(full_data) & 0xFF
    inv_sum = (~s_sum) & 0xFF
    correction = 1  # (0+1)^2 = 1
    chk = (inv_sum - event_count + correction) & 0xFF

    # Terminator
    terminator = bytes([chk, 0x00, 0x00, 0x00])

    return full_data + terminator, header, event_data, chk


def main():
    print("=" * 70)
    print("MACRO FORMAT COMPARISON")
    print("=" * 70)

    our_data, header, events, chk = build_our_macro()

    print("\n[OUR MACRO 'Test1']")
    print(f"Header (32 bytes): {header.hex()}")
    print(f"  - Name length: {header[0]} (0x{header[0]:02X})")
    print(f"  - Name bytes: {header[1:11].hex()} = '{header[1:11].decode('utf-16-le', errors='ignore')}'")
    print(f"  - Event count at [0x1F]: {header[31]} (0x{header[31]:02X})")
    print(f"Events ({len(events)} bytes): {events.hex()}")
    print(f"Checksum: 0x{chk:02X}")
    print(f"Full data ({len(our_data)} bytes):")
    for i in range(0, len(our_data), 16):
        hex_str = our_data[i:i+16].hex()
        print(f"  {i:04X}: {' '.join(hex_str[j:j+2] for j in range(0, len(hex_str), 2))}")

    print("\n[WINDOWS '123' MACRO (from dump)]")
    print(f"Header 0x00-0x0F: {WINDOWS_123_HEADER.hex()}")
    print(f"Header 0x10-0x1F: {WINDOWS_123_HEADER2.hex()}")
    print(f"  - Name length: {WINDOWS_123_HEADER[0]} (0x{WINDOWS_123_HEADER[0]:02X})")
    print(f"  - Event count: {WINDOWS_123_HEADER2[15]} (0x{WINDOWS_123_HEADER2[15]:02X}) = {WINDOWS_123_HEADER2[15]} events")
    print(f"First events: {WINDOWS_123_EVENTS_START.hex()}")

    print("\n[KEY DIFFERENCES TO CHECK]")
    print("1. Header structure: [name_len][name_30b][count] vs Windows")
    print("2. Event format: 5 bytes [type][code][0x00][delay_hi][delay_lo]")
    print("3. Last event delay: must be 0x0003")
    print("4. Terminator: [checksum][00][00][00] - NO 0x03 prefix")

    # Try to read what's actually on the device
    print("\n" + "=" * 70)
    print("READING DEVICE MEMORY")
    print("=" * 70)

    devices = vp.list_devices(exclude_receivers=False)
    target = None
    for d in devices:
        if d.interface_number == 1:
            target = d
            break

    if not target:
        print("No device found on interface 1")
        return

    dev = vp.VenusDevice(target.path)
    dev.open()

    try:
        # Read button 1 binding
        print("\n[Button 1 Binding (Page 0x00, Offset 0x60)]")
        try:
            binding = dev.read_flash(0x00, 0x60, 8)
            print(f"  Raw: {binding.hex()}")
            print(f"  Type: 0x{binding[0]:02X} ({'Macro' if binding[0] == 0x06 else 'Other'})")
            if binding[0] == 0x06:
                print(f"  Macro Index: {binding[1]}")
                print(f"  Repeat Mode: 0x{binding[2]:02X}")
        except Exception as e:
            print(f"  Read failed: {e}")

        # Read macro slot 0 header
        print("\n[Macro Slot 0 Header (Page 0x03, Offset 0x00)]")
        try:
            macro_header = dev.read_flash(0x03, 0x00, 8)
            print(f"  Bytes 0x00-0x07: {macro_header.hex()}")
            macro_header2 = dev.read_flash(0x03, 0x18, 8)
            print(f"  Bytes 0x18-0x1F: {macro_header2.hex()}")
            print(f"  Event count at 0x1F: {macro_header2[7]} (0x{macro_header2[7]:02X})")
        except Exception as e:
            print(f"  Read failed: {e}")

        # Read first events
        print("\n[Macro Slot 0 Events (Page 0x03, Offset 0x20)]")
        try:
            events = dev.read_flash(0x03, 0x20, 8)
            print(f"  Bytes 0x20-0x27: {events.hex()}")
        except Exception as e:
            print(f"  Read failed: {e}")

    finally:
        dev.close()


if __name__ == "__main__":
    main()
