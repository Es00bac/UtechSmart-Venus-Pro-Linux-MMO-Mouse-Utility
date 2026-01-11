#!/usr/bin/env python3
"""
Test macro upload using EXACT Windows flow from USB captures.

Windows flow for "wired - rebind 1 to macro called testing":
1. CMD 03 (handshake)
2. CMD 09 (simple unlock - NOT the complex 4D/01 sequence!)
3. CMD 03 (handshake again)
4. Write macro data chunks
5. Write binding
6. CMD 04 (commit - only ONE at the end!)
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
    """
    Build macro data matching EXACT Windows format.

    Args:
        name: Macro name (will be UTF-16LE encoded)
        events: List of (scancode, delay_ms) tuples for key presses
        macro_index: Which macro slot (0-based)

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
    header = bytes([name_len]) + name_padded + bytes([total_events])

    # Combine header + events
    full_data = header + bytes(event_data)

    # Calculate terminator checksum
    # VERIFIED: (~sum(data[:-2]) - count + (index+1)^2) & 0xFF
    # IMPORTANT: Exclude last 2 bytes (the "00 03" end marker) from checksum!
    data_for_checksum = full_data[:-2]  # Exclude the 00 03 end marker
    s_sum = sum(data_for_checksum) & 0xFF
    inv_sum = (~s_sum) & 0xFF
    count = total_events
    correction = (macro_index + 1) ** 2
    checksum = (inv_sum - count + correction) & 0xFF

    # Terminator is 4 bytes: [checksum] [00] [00] [00]
    terminator = bytes([checksum, 0x00, 0x00, 0x00])
    full_data += terminator

    # Pad to 10-byte boundary for chunked writes
    pad_len = (10 - (len(full_data) % 10)) % 10
    full_data += bytes(pad_len)

    return full_data


def test_exact_windows_flow():
    print("=" * 60)
    print("TEST: EXACT WINDOWS FLOW REPLICATION")
    print("=" * 60)

    # Connect to device
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
        # EXACT WINDOWS SEQUENCE:
        # 1. CMD 03 (handshake)
        print("\n[2] Step 1: CMD 03 (handshake)...")
        cmd03 = vp.build_simple(0x03)
        print(f"    Packet: {cmd03.hex()}")
        dev.send(cmd03)
        time.sleep(0.05)

        # 2. CMD 09 (simple unlock - NOT complex 4D/01!)
        print("\n[3] Step 2: CMD 09 (simple unlock)...")
        cmd09 = vp.build_simple(0x09)
        print(f"    Packet: {cmd09.hex()}")
        print(f"    Expected: 0809000000000000000000000000000044")
        dev.send(cmd09)
        time.sleep(0.05)

        # 3. CMD 03 (handshake again)
        print("\n[4] Step 3: CMD 03 (handshake again)...")
        dev.send(cmd03)
        time.sleep(0.05)

        # Build macro: press '1' (scancode 0x1E) with 125ms delay
        print("\n[5] Building macro 'Test1' (types '1')...")
        macro_data = build_test_macro_exact(
            name="Test1",
            events=[(0x1E, 125)],  # Press '1' with 125ms delay
            macro_index=0
        )

        print(f"    Macro size: {len(macro_data)} bytes")
        print(f"    Header[0:32]: {macro_data[:32].hex()}")
        print(f"    Events[32:42]: {macro_data[32:42].hex()}")
        print(f"    Terminator: {macro_data[42:46].hex()}")

        # Write macro in 10-byte chunks
        print("\n[6] Step 4: Write macro data to Page 0x03...")
        page, offset = 0x03, 0x00
        chunks_written = 0
        for i in range(0, len(macro_data), 10):
            chunk = macro_data[i:i+10]
            chunk_page = page + ((offset + i) >> 8)
            chunk_off = (offset + i) & 0xFF
            pkt = vp.build_macro_chunk(chunk_off, chunk, chunk_page)
            print(f"    Chunk {chunks_written}: {pkt.hex()}")
            dev.send(pkt)
            time.sleep(0.01)
            chunks_written += 1
        print(f"    Wrote {chunks_written} chunks")

        # Write binding (still part of step 4, before commit)
        print("\n[7] Step 5: Write binding (Page 0x00, Offset 0x60)...")
        # Windows uses 0x01 for repeat mode "once"
        # Binding: 06 00 01 4e
        #   06 = Macro type
        #   00 = Macro index 0
        #   01 = Repeat once
        #   4e = checksum: 0x55 - (0x06 + 0x00 + 0x01) = 0x4e
        bind_pkt = vp.build_macro_bind(0x60, 0, 0x01, page=0x00)  # 0x01 = repeat once (Windows value)
        print(f"    Bind packet: {bind_pkt.hex()}")
        print(f"    Expected:    0807000060040600014e0000000000008d")
        dev.send(bind_pkt)
        time.sleep(0.05)

        # 4. CMD 04 (commit - only ONE at the end!)
        print("\n[8] Step 6: CMD 04 (commit)...")
        cmd04 = vp.build_simple(0x04)
        print(f"    Packet: {cmd04.hex()}")
        dev.send(cmd04)
        time.sleep(0.1)

        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)

        # Read back button 1 binding
        print("\n[9] Reading Button 1 binding (Page 0x00, Offset 0x60)...")
        try:
            binding = dev.read_flash(0x00, 0x60, 8)
            print(f"    Binding: {binding.hex()}")
            if binding[0] == 0x06:
                print(f"    Type: 0x06 (Macro)")
                print(f"    Index: {binding[1]}")
                print(f"    Repeat: 0x{binding[2]:02X}")
                print(f"    Checksum: 0x{binding[3]:02X}")
        except Exception as e:
            print(f"    Read failed: {e}")

        # Read macro header
        print("\n[10] Reading Macro 0 header (Page 0x03)...")
        try:
            hdr = dev.read_flash(0x03, 0x00, 32)
            print(f"    Header: {hdr.hex()}")
            print(f"    Name len: {hdr[0]}")
            print(f"    Event count: {hdr[31]}")
        except Exception as e:
            print(f"    Read failed: {e}")

        # Read events
        print("\n[11] Reading Macro 0 events (Page 0x03, Offset 0x20)...")
        try:
            events = dev.read_flash(0x03, 0x20, 16)
            print(f"    Events: {events.hex()}")
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
    test_exact_windows_flow()
