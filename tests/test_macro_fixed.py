#!/usr/bin/env python3
"""
FIXED Macro Upload Test

Key fixes from Windows capture analysis:
1. event_count = actual number of events (NOT events * 3)
2. Last event's delay MUST be 0x0003 (3ms) - this is the end-of-macro marker
3. Terminator is 4 bytes: [checksum] [00] [00] [00] - NO 0x03 prefix!
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import time
import venus_protocol as vp


def build_test_macro(name: str, events: list[tuple[int, int, int]], macro_index: int = 0) -> bytes:
    """
    Build macro data with CORRECT format.

    Args:
        name: Macro name (will be UTF-16LE encoded)
        events: List of (scancode, delay_ms, is_last) tuples for key presses
                Each key generates 2 events: press + release
        macro_index: Which macro slot (0-based) - affects checksum calculation

    Returns:
        Complete macro data ready to write to flash
    """
    # Encode name
    name_utf16 = name.encode('utf-16-le')
    name_len = len(name_utf16)
    name_padded = name_utf16.ljust(30, b'\x00')[:30]

    # Build events - each key = 2 events (press + release)
    event_data = bytearray()
    total_events = 0

    for i, (scancode, delay_ms) in enumerate(events):
        is_last = (i == len(events) - 1)

        # Key press event
        event_data.extend([
            0x81,  # Key down
            scancode,
            0x00,
            (delay_ms >> 8) & 0xFF,  # Delay high
            delay_ms & 0xFF,          # Delay low
        ])
        total_events += 1

        # Key release event
        # CRITICAL: Last release event MUST have delay = 0x0003
        release_delay = 0x0003 if is_last else delay_ms
        event_data.extend([
            0x41,  # Key up
            scancode,
            0x00,
            (release_delay >> 8) & 0xFF,
            release_delay & 0xFF,
        ])
        total_events += 1

    # Build header (32 bytes: name_len + name[30] + event_count)
    # CRITICAL: event_count = actual number of events, NOT events * 3
    header = bytes([name_len]) + name_padded + bytes([total_events])

    # Combine header + events
    full_data = header + bytes(event_data)

    # Calculate terminator checksum
    # VERIFIED FORMULA: (~sum(data[:-2]) - count + (index+1)^2) & 0xFF
    # IMPORTANT: Exclude last 2 bytes (the "00 03" end marker) from checksum!
    data_for_checksum = full_data[:-2]  # Exclude the 00 03 end marker
    s_sum = sum(data_for_checksum) & 0xFF
    inv_sum = (~s_sum) & 0xFF
    count = total_events
    correction = (macro_index + 1) ** 2
    checksum = (inv_sum - count + correction) & 0xFF

    # CRITICAL: Terminator is 4 bytes, NO 0x03 prefix!
    # The 0x03 people see is the last event's delay, not part of terminator
    terminator = bytes([checksum, 0x00, 0x00, 0x00])
    full_data += terminator

    # Pad to 10-byte boundary for chunked writes (AFTER adding terminator)
    pad_len = (10 - (len(full_data) % 10)) % 10
    full_data += bytes(pad_len)

    return full_data


def test_macro_upload():
    print("=" * 60)
    print("FIXED MACRO UPLOAD TEST")
    print("=" * 60)

    # Connect to device
    print("\n[1] Connecting to device...")
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
        # Unlock
        print("\n[2] Sending unlock sequence...")
        if not dev.unlock():
            print("FAILED: Unlock failed")
            return False
        print("OK: Unlocked")

        # Build a simple "type 1" macro
        # Key '1' has HID scancode 0x1E
        print("\n[3] Building macro 'Test1' (types '1')...")

        macro_data = build_test_macro(
            name="Test1",
            events=[(0x1E, 125)],  # Press '1' with 125ms delay
            macro_index=0
        )

        print(f"    Macro size: {len(macro_data)} bytes")
        print(f"    Header: {macro_data[:10].hex()}")
        print(f"    Events: {macro_data[32:42].hex()}")
        print(f"    Terminator: {macro_data[-4:].hex()}")

        # Write macro
        print("\n[4] Writing macro to Page 0x03...")

        # Handshake
        dev.send(vp.build_simple(0x03))
        time.sleep(0.05)

        # Write in 10-byte chunks
        page, offset = 0x03, 0x00
        for i in range(0, len(macro_data), 10):
            chunk = macro_data[i:i+10]
            chunk_page = page + ((offset + i) >> 8)
            chunk_off = (offset + i) & 0xFF
            pkt = vp.build_macro_chunk(chunk_off, chunk, chunk_page)
            dev.send(pkt)
            time.sleep(0.01)

        # Commit
        dev.send(vp.build_simple(0x04))
        time.sleep(0.1)
        print("OK: Macro written")

        # Bind button 1 to macro
        print("\n[5] Binding Button 1 to Macro 0...")
        dev.send(vp.build_simple(0x03))
        time.sleep(0.05)

        bind_pkt = vp.build_macro_bind(0x60, 0, vp.MACRO_REPEAT_ONCE)
        dev.send(bind_pkt)
        time.sleep(0.05)

        dev.send(vp.build_simple(0x04))
        time.sleep(0.1)
        print("OK: Button bound")

        # Verify
        print("\n[6] Verifying...")
        try:
            binding = dev.read_flash(0x00, 0x60, 4)
            print(f"    Button 1 binding: {binding.hex()}")
            if binding[0] == 0x06:
                print("OK: Button 1 bound to macro!")
        except Exception as e:
            print(f"    Read failed: {e}")

        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("Press Button 1 - it should type '1'")
        print("=" * 60)
        return True

    finally:
        dev.close()


if __name__ == "__main__":
    test_macro_upload()
