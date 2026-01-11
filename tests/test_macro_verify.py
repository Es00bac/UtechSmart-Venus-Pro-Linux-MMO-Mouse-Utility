#!/usr/bin/env python3
"""
Test script to verify macro upload actually works after unlock.
1. Unlock device
2. Write a simple test macro to Slot 1
3. Bind Button 1 to Macro 1
4. Read back the data to verify it persisted
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import time
import venus_protocol as vp

def test_macro_write():
    print("="*60)
    print("MACRO WRITE VERIFICATION TEST")
    print("="*60)
    
    # Step 1: Find and open Interface 1
    print("\n[1] Connecting to device (Interface 1)...")
    target_dev_path = None
    target_product = ""
    
    # Try multiple times to find the device
    for attempt in range(5):
        # Include receivers because Wireless Config happens on Receiver Interface 1
        devices = vp.list_devices(exclude_receivers=False)
        
        for d in devices:
            if d.interface_number == 1:
                target_dev_path = d.path
                target_product = d.product
                break
        
        if target_dev_path:
            break
        time.sleep(0.5)
        print(f"    Retry {attempt+1}/5 (No Interface 1 found)...")
    
    if not target_dev_path:
        print("FAILED: No Interface 1 device found after 5 retries")
        return False
    
    dev = vp.VenusDevice(target_dev_path)
    dev.open()
    print(f"OK: Connected to {target_product}")
    
    try:
        # Step 2: Unlock ON THE SAME CONNECTION
        print("\n[2] Sending Magic Unlock sequence...")
        if dev.unlock():
            print("OK: Unlock sequence sent.")
        else:
            print("FAILED: Unlock failed.")
            return False

        # Step 3: Read Page 3 BEFORE writing (to compare later)
        print("\n[3] Reading Page 3 (Macro 1 slot) BEFORE write...")
        try:
            before = dev.read_flash(0x03, 0x00, 8)
            print(f"    Before: {before.hex()}")
        except Exception as e:
            print(f"    Read failed (expected on some devices): {e}")
            before = None
        
        # Step 4: Build a simple minimal test macro
        # Just a single "A" key press+release
        print("\n[4] Building test macro 'TestMacro'...")
        
        # Macro format (Corrected Layout + Correct Checksum):
        # 0x00: Name Byte Length
        # 0x01..0x1E: Name (30 bytes)
        # 0x1F: Event Count
        # 0x20: Events...
        
        macro_name_str = "TestMacro"
        name_utf16 = macro_name_str.encode('utf-16-le')
        name_len = len(name_utf16) 
        name_padded = name_utf16.ljust(30, b'\x00')[:30]
        
        event_count = 2
        
        # Build header part (0x00 - 0x1F)
        # [NameLen] [Name 30 bytes] [EventCount]
        # Total 32 bytes
        header = bytes([name_len]) + name_padded + bytes([event_count])
        
        # Events start at 0x20
        # Dump Analysis confirmed: 5 BYTES PER EVENT.
        # [Type] [Code] [DelayHi] [DelayLo] [Checksum]
        # Count field is (NumEvents * 3).
        
        # Copying exact events for "Press 1" and "Release 1" from Slot 0 dump
        # Event 1: 81 1e 00 00 7d (Press '1')
        # Event 2: 41 1e 00 00 bb (Release '1')
        events = bytes([
            0x81, 0x1e, 0x00, 0x00, 0x7d,  # Press '1'
            0x41, 0x1e, 0x00, 0x00, 0xbb,  # Release '1'
        ])
        
        # Count = 2 events * 3 = 6
        event_count = 6
        
        # Build header part (0x00 - 0x1F)
        # [NameLen] [Name 30 bytes] [EventCount]
        header = bytes([name_len]) + name_padded + bytes([event_count])
        
        full_data = header + events
        
        # Pad to align to 10-byte chunks
        pad_len = (10 - (len(full_data) % 10)) % 10
        full_data += bytes(pad_len)
        
        # Terminator: 03 [checksum] 00
        # Checksum calculation might depend on the new structure
        # (0x55 - Sum(data)) is standard
        # Terminator: 03 [checksum] 00
        # The Checksum is NOT 0x55 - Sum. It is specific to the Macro Data.
        # Logic from venus_protocol.py calculate_terminator_checksum:
        # Sum of ALL data (excluding terminator)
        # s_sum = sum(full_data)
        # inv_sum = (~s_sum) & 0xFF
        # count = full_data[0x1F]
        # correction = (macro_index + 1) ** 2  -> (0+1)^2 = 1
        # result = (inv_sum - count + correction) & 0xFF
        
        s_sum = sum(full_data) & 0xFF
        inv_sum = (~s_sum) & 0xFF
        count_val = full_data[0x1F]
        correction = 1  # For Macro Index 0 (Slot 1)
        
        chk = (inv_sum - count_val + correction) & 0xFF
        
        terminator = bytes([0x03, chk, 0x00])
        full_data += terminator
        
        print(f"    Macro data ({len(full_data)} bytes): {full_data[:20].hex()}...")
        
        # Step 5: Send Handshake, Write chunks, Commit
        print("\n[5] Uploading macro to Slot 1 (Page 0x03)...")
        
        # Handshake
        dev.send(vp.build_simple(0x03))
        time.sleep(0.05)
        
        # Write in 10-byte chunks
        page, offset = 0x03, 0x00
        for i in range(0, len(full_data), 10):
            chunk = full_data[i:i+10]
            chunk_page = page + ((offset + i) >> 8)
            chunk_off = (offset + i) & 0xFF
            pkt = vp.build_macro_chunk(chunk_off, chunk, chunk_page)
            dev.send(pkt)
            print(f"    Wrote chunk at Page 0x{chunk_page:02X} Offset 0x{chunk_off:02X}")
            time.sleep(0.01)
        
        # Commit
        dev.send(vp.build_simple(0x04))
        time.sleep(0.1)
        print("OK: Write sequence sent.")
        
        # Step 6: Read back to verify
        print("\n[6] Reading Page 3 AFTER write...")
        try:
            after = dev.read_flash(0x03, 0x00, 8)
            print(f"    After: {after.hex()}")
            
            if before and after == before:
                print("WARNING: Data unchanged! Write may have failed.")
            elif after == bytes(8):
                print("WARNING: Read returned zeros. Firmware may be blocking reads.")
            else:
                print("OK: Data changed, write appears successful!")
        except Exception as e:
            print(f"    Read failed: {e}")
        
        # Step 7: Bind Button 1 to Macro 1
        print("\n[7] Binding Button 1 to Macro 1...")
        
        # Handshake
        dev.send(vp.build_simple(0x03))
        time.sleep(0.05)
        
        # Build macro bind packet (Type 06)
        bind_pkt = vp.build_macro_bind(0x60, 0, vp.MACRO_REPEAT_ONCE)  # Button 1 offset = 0x60
        dev.send(bind_pkt)
        time.sleep(0.05)
        
        # Commit
        dev.send(vp.build_simple(0x04))
        time.sleep(0.1)
        print("OK: Bind command sent.")
        
        # Step 8: Read binding to verify
        print("\n[8] Reading Button 1 binding (Page 0, Offset 0x60)...")
        try:
            binding = dev.read_flash(0x00, 0x60, 4)
            print(f"    Binding: {binding.hex()}")
            if binding[0] == 0x06:
                print("OK: Button 1 is bound to Macro (Type 06)!")
            else:
                print(f"WARNING: Button 1 has Type 0x{binding[0]:02X}, not Macro (06)")
        except Exception as e:
            print(f"    Read failed: {e}")
        
        print("\n" + "="*60)
        print("TEST COMPLETE - Press Button 1 and check if 'a' is typed!")
        print("="*60)
        
        return True
        
    finally:
        dev.close()

if __name__ == "__main__":
    test_macro_write()
