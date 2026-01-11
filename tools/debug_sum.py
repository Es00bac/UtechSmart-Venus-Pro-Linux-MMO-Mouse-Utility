from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def debug_sum():
    target_cap = "bind macros 123"
    with open("artifacts/txt/host_mouse_communication.txt", 'r') as f:
        lines = f.readlines()
        
    page3 = bytearray([0] * 256)
    in_target = False
    
    for line in lines:
        if line.startswith("["):
            in_target = (target_cap in line)
            continue
        if not in_target: continue
        if "--> H2M | WRITE" not in line: continue
        
        parts = line.split('|')[2].strip().split()
        pkt = [int(b, 16) for b in parts]
        if pkt[1] != 0x07: continue
        if pkt[3] != 0x03: continue # Only Page 3
        
        offset = pkt[4]
        length = pkt[5]
        data = pkt[6:]
        
        valid = min(length, len(data))
        for i in range(valid):
            if offset+i < 256:
                page3[offset+i] = data[i]
                
    # Manual Sum Trace
    print("Tracing sum for Page 3 (0-78):")
    current_sum = 0
    payload = page3[0:0x78]
    
    for i, b in enumerate(payload):
        if b != 0:
            old = current_sum
            current_sum += b
            print(f"[{i:02X}]: {b:02X} | Sum {old:02X} + {b:02X} -> {current_sum:02X} (ModFF: {current_sum & 0xFF:02X})")
            
    print(f"Final Sum: {current_sum & 0xFF:02X}")
    
    term_inner = page3[0x7A] # 78 00 03 XX
    # Wait. Term structure: 00 03 XX.
    # At 78: 00. 79: 03. 7A: XX.
    print(f"Terminator Inner (7A): {term_inner:02X}")

if __name__ == "__main__":
    debug_sum()
