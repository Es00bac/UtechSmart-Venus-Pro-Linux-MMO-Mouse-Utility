#!/usr/bin/env python3
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import struct

def analyze_dump():
    with open('dumps/Good_Config_Windows.bin', 'rb') as f:
        data = f.read()
    
    # Macro slots start at Page 3 (0x300)
    # Stride is 0x180 (384 bytes) per macro? Or 256?
    # Let's check the stride by looking for headers.
    # Headers usually start with NameLen (small byte) or similar.
    
    print(f"File size: {len(data)}")
    
    # Known macros in this dump? "testing"?
    # Search for "testing" UTF-16
    match = b't\x00e\x00s\x00t\x00i\x00n\x00g\x00'
    pos = data.find(match)
    if pos != -1:
        print(f"Found 'testing' at offset 0x{pos:X}")
        # The slot start should be near.
        # If header is ~32 bytes, slot start ~ pos - 2 - header_len.
    
    # Assume 12 slots.
    # Standard spacing is likely 0x100 (256) or 0x180 (384).
    # Task memory map says Page 3, 4, ...
    
    # Let's look at offsets 0x300, 0x400, etc.
    # And 0x300, 0x480 (if stride 0x180).
    
    offsets = []
    # Try stride 0x180 first (suggested by venus_protocol.py)
    # 0: 0x300
    # 1: 0x480
    # 2: 0x600
    # ...
    base = 0x300
    stride = 0x100 # Let's try 256 first as it aligns with Pages
    
    print("\n--- Scanning Potential Macro Headers ---")
    for i in range(12):
        off = base + (i * stride)
        if off + 32 > len(data): break
        header = data[off:off+32]
        print(f"Slot {i} (0x{off:X}): {header.hex()}")
        
    print("\n--- Analyzing Slot 1 (0x300) Detailed ---")
    slot1 = data[0x300:0x300+100]
    print(f"Hex: {slot1.hex()}")
    
    # Check Terminator
    # Terminator usually 03 [chk] 00.
    # Scan for 03 .. 00 sequences in the slot.
    
    print("\n--- Searching for Terminators in Slot 1 ---")
    # Slot 1 ends at 0x400 (if 256 bytes) or 0x480
    slot1_full = data[0x300:0x480]
    for j in range(len(slot1_full)-3):
        if slot1_full[j] == 0x03 and slot1_full[j+2] == 0x00:
            term = slot1_full[j:j+3]
            print(f"Potential Terminator at +0x{j:X}: {term.hex()}")
            
            # Checksum verification attempt
            # Data before terminator
            payload = slot1_full[:j]
            payload_sum = sum(payload) & 0xFF
            chk = term[1]
            
            # Test 0x55 - Sum
            c1 = (0x55 - payload_sum) & 0xFF
            print(f"  Calc (0x55 - Sum): 0x{c1:02X} [{'MATCH' if c1==chk else 'No'}]")
            
            # Test ~Sum + Correction
            # Correction = (Index+1)^2??
            idx = 0
            corr = (idx+1)**2
            inv_sum = (~payload_sum) & 0xFF
            # Count? At 0x1F?
            count = payload[0x1F] if len(payload) > 0x1F else 0
            
            c2 = (inv_sum - count + corr) & 0xFF
            print(f"  Calc (~Sum - Count + {corr}): 0x{c2:02X} [{'MATCH' if c2==chk else 'No'}]")

if __name__ == "__main__":
    analyze_dump()
