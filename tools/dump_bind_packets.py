from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def dump_binds():
    with open("artifacts/txt/host_mouse_communication.txt", 'r') as f:
        lines = f.readlines()
        
    print("Extracting Macro Binds (Type 06)...")
    for line in lines:
        if "--> H2M | WRITE" not in line: continue
        parts = line.split('|')[2].strip().split()
        pkt = [int(b, 16) for b in parts]
        
        # Check Type 06
        # Pkt[6]? if 08 07 00 00 60 04 06 ...
        if len(pkt) > 7 and pkt[6] == 0x06:
            # Found Type 06
             print(f"Bind Pkt: {' '.join([f'{b:02X}' for b in pkt])}")
             
             # Verify Packet Checksum (Byte 16)
             s_sum = sum(pkt[0:16]) & 0xFF
             calc_chk = (0x55 - s_sum) & 0xFF
             print(f"  Sum(0-15): {s_sum:02X}. 55-Sum: {calc_chk:02X}. Actual: {pkt[16]:02X}")
             if calc_chk != pkt[16]:
                 print("  MISMATCH!")
             
             # Payload Checksum D3
             # Payload: ... Type[6] D1[7] D2[8] D3[9]
             type_b = pkt[6]
             d1 = pkt[7]
             d2 = pkt[8]
             d3 = pkt[9]
             psum = (type_b + d1 + d2) & 0xFF
             
             # Try Bases
             base55 = (d3 + psum) & 0xFF
             print(f"  P-Sum: {psum:02X}. D3: {d3:02X}. Base (D3+Sum): {base55:02X}")

if __name__ == "__main__":
    dump_binds()
