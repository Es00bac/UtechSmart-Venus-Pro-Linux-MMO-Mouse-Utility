#!/usr/bin/env python3
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import venus_protocol as vp
import time

def verify_macro_slot(slot=0):
    devs = vp.list_devices()
    if not devs:
        print("No devices found")
        return
    
    target = next((d for d in devs if d.interface_number == 1), devs[0])
    print(f"Connecting to {target.path}")
    
    mouse = vp.VenusDevice(target.path)
    mouse.open()
    
    try:
        # 1. Check Binding for Button 1 (Offset 0x60)
        print("\n--- Button 1 Binding (Page 0, Offset 0x60) ---")
        bind_data = mouse.read_flash(0x00, 0x60, 8)
        print(f"Raw Data: {bind_data.hex(' ')}")
        # Expected for Macro 1: 06 00 01 [chk] ...
        
        # 2. Check Macro 1 Header (Page 03, Offset 0x00)
        print("\n--- Macro 1 Header (Page 03, Offset 0x00) ---")
        header_chunk1 = mouse.read_flash(0x03, 0x00, 8)
        header_chunk2 = mouse.read_flash(0x03, 0x08, 8)
        header_chunk3 = mouse.read_flash(0x03, 0x10, 8)
        header_chunk4 = mouse.read_flash(0x03, 0x18, 8)
        
        full_header = header_chunk1 + header_chunk2 + header_chunk3 + header_chunk4
        print(f"Name Length: {full_header[0]}")
        name = full_header[1:31].decode('utf-16le', errors='ignore').strip('\x00')
        print(f"Macro Name : {name}")
        print(f"Event Count: {full_header[31]} (at 0x1F)")
        
        # 3. Check First Event
        print("\n--- Macro 1 First Event (Page 03, Offset 0x20) ---")
        event_chunk = mouse.read_flash(0x03, 0x20, 8)
        print(f"Event 1: {event_chunk[:5].hex(' ')}")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    verify_macro_slot(0)
