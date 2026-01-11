from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def analyze_replay():
    target_cap = "bind macros 123"
    with open("artifacts/txt/host_mouse_communication.txt", 'r') as f:
        lines = f.readlines()
        
    pages = {} # Map Page -> bytearray
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
        
        p = pkt[3]
        o = pkt[4]
        l = pkt[5]
        d = pkt[6:]
        
        if p not in pages: pages[p] = bytearray([0] * 256)
        valid = min(l, len(d))
        for i in range(valid):
            if o+i < 256:
                pages[p][o+i] = d[i]
                
    # Analyze M2 (Page 4, Offset 80)
    # Start: 80.
    # Term: DA (Line 64) -> 00 03 38
    print("--- Macro 2 (Index 1) ---")
    p4 = pages[4]
    start = 0x80
    term = 0xDA
    payload = p4[start:term] 
    
    count_offset = start + 0x1F # 9F
    count = p4[count_offset]
    
    s_sum = sum(payload) & 0xFF
    tgt = 0x38 
    inv_sum = (~s_sum) & 0xFF
    base = (inv_sum - count) & 0xFF
    k = (tgt - base) & 0xFF
    
    print(f"Buf[80:8A]: {' '.join([f'{b:02X}' for b in payload[:10]])}")
    print(f"Sum: {s_sum:02X} Count: {count:02X} Target: {tgt:02X} -> K_CALC: {k} (Expected 4)")
    
    # Analyze M3 (Page 6, Offset 00)
    print("\n--- Macro 3 (Index 2) ---")
    p6 = pages[6]
    start = 0x00
    term = 0x46 # Line 84: 46 00 03 8E
    # Wait. Line 84 packet offset 0x46.
    # Writes 46 06 00 03 8E ...
    # So Term is AT 46+2 = 48?
    # No, usually Term is [00 03 XX ...]
    # Packet: 08 07 00 06 46 06 -> Off 46, Len 6.
    # Data: 00 03 8E ...
    # So at Offset 46: 00. 47: 03. 48: 8E.
    # Term Offset is 46.
    
    payload = p6[start:term]
    count = p6[0x1F]
    s_sum = sum(payload) & 0xFF
    tgt = 0x8E
    inv_sum = (~s_sum) & 0xFF
    base = (inv_sum - count) & 0xFF
    k = (tgt - base) & 0xFF
    
    print(f"Buf[00:0A]: {' '.join([f'{b:02X}' for b in payload[:10]])}")
    print(f"Sum: {s_sum:02X} Count: {count:02X} Target: {tgt:02X} -> K_CALC: {k} (Expected 9)")

if __name__ == "__main__":
    analyze_replay()
