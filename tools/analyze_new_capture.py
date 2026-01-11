from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def analyze_new_capture():
    file_path = "artifacts/txt/new_capture_dump.txt"
    print(f"Reading {file_path}...")
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
        
    print(f"Found {len(lines)} lines/packets.")
    
    bind_packets = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # tshark output: 08:07:00:00:60:04:06:00:01:4e:00:00:00:00:00:00:8d
        # remove colons
        hex_str = line.replace(':', '')
        # Must be at least 17 bytes (34 hex chars)
        if len(hex_str) < 34: continue
        
        # Parse bytes
        try:
            pkt = bytes.fromhex(hex_str)
        except ValueError:
            continue
            
        # Check for Write Command (08 07)
        if pkt[0] != 0x08 or pkt[1] != 0x07:
            continue
            
        # Check Length (Byte 5? or 3? 08 07 00 PAGE OFFSET LEN)
        # 08 07 00 00 60 04
        # Byte 0=08, 1=07, 2=00, 3=00(pg), 4=60(off), 5=04(len)
        if len(pkt) < 7: continue
        
        length = pkt[5]
        
        # Check Type 06 (Macro Bind)
        # Type is at index 6
        if length == 0x04 and pkt[6] == 0x06:
            bind_packets.append(pkt)
            print(f"Found Type 06 Bind: {line}")
            
    print(f"\nAnalyzed {len(bind_packets)} Bind Packets.")
    
    for pkt in bind_packets:
        # Pkt Structure: [08] [07] [P] [O] [L] [06] [IDX] [MODE] [CHK] ...
        idx = pkt[7]
        mode = pkt[8]
        chk = pkt[9]
        
        # Calculate Sum
        part_sum = (0x06 + idx + mode) & 0xFF
        
        # Solve Base: Base = Chk + Sum
        base = (chk + part_sum) & 0xFF
        
        print(f"Idx: {idx:02X} Mode: {mode:02X} Chk: {chk:02X} PartSum: {part_sum:02X} -> BASE: {base:02X}")

if __name__ == "__main__":
    analyze_new_capture()
