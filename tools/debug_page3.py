from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def debug_page3():
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
        
        # indices assuming [08, 07, 00, 03, OFF, LEN, DATA...]
        # My previous recalc assumed: 08 07 00 PAGE OFF LEN
        # Let's verify standard packet: 
        # Line 13: 08 07 00 03 00 0A 06 31 ...
        # 0:08, 1:07, 2:00, 3:03, 4:00, 5:0A, 6:06...
        
        offset = pkt[4]
        length = pkt[5]
        data = pkt[6:]
        
        # Remove checksum from end? No, write is raw.
        # But wait, 9D at end of Line 13 is Checksum?
        # If Len 10, Data has 10 bytes..
        # 06 31 00 32 00 33 00 00 00 00 -> 10 bytes.
        # 9D is byte 16 (index 16).
        # Packet len 17.
        # So data IS pkt[6:16].
        
        valid = min(length, len(data))
        for i in range(valid):
            if offset+i < 256:
                page3[offset+i] = data[i]
                
    # Dump buffer
    print("Page 3 Buffer Dump:")
    print(" ".join([f"{b:02X}" for b in page3[:128]]))
    
    # Calculate Sum for M1 (Term at 78)
    payload = page3[0:0x78]
    s_sum = sum(payload) & 0xFF
    print(f"Sum(0:78) = {s_sum:02X}")
    
    # Checksum logic
    # Term at 78: 00 03 E8 ...
    # Inner E8.
    # Count: 1F (12)
    count = page3[0x1F]
    print(f"Count (1F) = {count:02X}")
    
    # Calc K
    # Inner = ~Sum - Count + K
    inv_sum = (~s_sum) & 0xFF
    base = (inv_sum - count) & 0xFF
    k = (0xE8 - base) & 0xFF
    print(f"Target E8. Base {base:02X}. K = {k:02X} ({k})")

if __name__ == "__main__":
    debug_page3()
