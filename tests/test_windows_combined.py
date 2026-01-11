#!/usr/bin/env python3
"""
Test macro upload combining complex unlock with Windows flow.

Hypothesis: The complex unlock (CMD 09, 4D, 01) is needed to enable writes,
then we follow Windows sequence for the actual upload.
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import time
import venus_protocol as vp


def build_test_macro_exact(name: str, events: list[tuple[int, int]], macro_index: int = 0) -> bytes:
    """Build macro data matching EXACT Windows format."""
    name_utf16 = name.encode('utf-16-le')
    name_len = len(name_utf16)
    name_padded = name_utf16.ljust(30, b'\x00')[:30]

    event_data = bytearray()
    total_events = 0

    for i, (scancode, delay_ms) in enumerate(events):
        is_last = (i == len(events) - 1)

        # Key press
        event_data.extend([
            0x81, scancode, 0x00,
            (delay_ms >> 8) & 0xFF, delay_ms & 0xFF,
        ])
        total_events += 1

        # Key release (last event has delay=3)
        release_delay = 0x0003 if is_last else delay_ms
        event_data.extend([
            0x41, scancode, 0x00,
            (release_delay >> 8) & 0xFF, release_delay & 0xFF,
        ])
        total_events += 1

    header = bytes([name_len]) + name_padded + bytes([total_events])
    full_data = header + bytes(event_data)

    # Checksum (exclude last 2 bytes)
    data_for_checksum = full_data[:-2]
    s_sum = sum(data_for_checksum) & 0xFF
    inv_sum = (~s_sum) & 0xFF
    correction = (macro_index + 1) ** 2
    checksum = (inv_sum - total_events + correction) & 0xFF

    terminator = bytes([checksum, 0x00, 0x00, 0x00])
    full_data += terminator

    pad_len = (10 - (len(full_data) % 10)) % 10
    full_data += bytes(pad_len)

    return full_data


def test_combined_flow():
    print("=" * 60)
    print("TEST: COMBINED UNLOCK + WINDOWS FLOW")
    print("=" * 60)

    # Connect
    print("\n[1] Connecting to device (Interface 1)...")
    target_path = None
    for attempt in range(5):
        devices = vp.list_devices(exclude_receivers=False)
        for d in devices:
            if d.interface_number == 1:
                target_path = d.path
                break
        if target_path:
            break
        time.sleep(0.5)

    if not target_path:
        print("FAILED: No Interface 1 device found")
        return False

    dev = vp.VenusDevice(target_path)
    dev.open()
    print(f"OK: Connected")

    try:
        # STEP A: Complex unlock first
        print("\n[2] Complex unlock (CMD 09, 4D, 01)...")
        if not dev.unlock():
            print("WARNING: Unlock returned False (may still work)")
        time.sleep(0.5)
        print("OK: Unlock sequence sent")

        # STEP B: Now follow Windows sequence
        print("\n[3] Windows flow: CMD 03...")
        cmd03 = vp.build_simple(0x03)
        dev.send(cmd03)
        time.sleep(0.05)

        print("\n[4] Windows flow: CMD 09...")
        cmd09 = vp.build_simple(0x09)
        dev.send(cmd09)
        time.sleep(0.05)

        print("\n[5] Windows flow: CMD 03 again...")
        dev.send(cmd03)
        time.sleep(0.05)

        # Build macro
        print("\n[6] Building macro 'Test1' (types '1')...")
        macro_data = build_test_macro_exact(
            name="Test1",
            events=[(0x1E, 125)],
            macro_index=0
        )
        print(f"    Size: {len(macro_data)} bytes")

        # Write macro
        print("\n[7] Writing macro chunks to Page 0x03...")
        page, offset = 0x03, 0x00
        for i in range(0, len(macro_data), 10):
            chunk = macro_data[i:i+10]
            chunk_page = page + ((offset + i) >> 8)
            chunk_off = (offset + i) & 0xFF
            pkt = vp.build_macro_chunk(chunk_off, chunk, chunk_page)
            dev.send(pkt)
            time.sleep(0.01)
        print("    Done")

        # Write binding
        print("\n[8] Writing binding (Button 1 -> Macro 0)...")
        bind_pkt = vp.build_macro_bind(0x60, 0, 0x01, page=0x00)
        print(f"    Packet: {bind_pkt.hex()}")
        dev.send(bind_pkt)
        time.sleep(0.05)

        # Commit
        print("\n[9] CMD 04 (commit)...")
        cmd04 = vp.build_simple(0x04)
        dev.send(cmd04)
        time.sleep(0.2)

        # Verify
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)

        print("\n[10] Reading Button 1 binding...")
        try:
            binding = dev.read_flash(0x00, 0x60, 8)
            print(f"    Raw: {binding.hex()}")
            print(f"    Type: 0x{binding[0]:02X} ({'Macro' if binding[0] == 0x06 else 'Other'})")
            if binding[0] == 0x06:
                print(f"    Macro Index: {binding[1]}")
                print(f"    Repeat Mode: 0x{binding[2]:02X}")
        except Exception as e:
            print(f"    Read failed: {e}")

        print("\n[11] Reading Macro 0 header (bytes 0-32)...")
        try:
            hdr = dev.read_flash(0x03, 0x00, 32)
            print(f"    Header: {hdr.hex()}")
            if hdr[0] != 0:
                print(f"    Name length: {hdr[0]}")
                print(f"    Event count: {hdr[31]}")
        except Exception as e:
            print(f"    Read failed: {e}")

        print("\n[12] Reading Macro 0 events (bytes 32-48)...")
        try:
            events = dev.read_flash(0x03, 0x20, 16)
            print(f"    Events: {events.hex()}")
        except Exception as e:
            print(f"    Read failed: {e}")

        print("\n" + "=" * 60)
        print("TEST COMPLETE - Press Button 1 to test")
        print("=" * 60)
        return True

    finally:
        dev.close()


if __name__ == "__main__":
    test_combined_flow()
