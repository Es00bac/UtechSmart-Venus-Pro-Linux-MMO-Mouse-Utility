from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def analyze_0a():
    try:
        with open("artifacts/txt/host_mouse_communication.txt", 'r') as f:
            lines = f.readlines()
    except:
        return

    print(f"{'OFFSET':<6} | {'LEN':<4} | {'TYPE':<4} | {'D1':<4} | {'D2':<4} | {'D3':<4} | {'REM (Hex/ASCII)'}")
    print("-" * 80)

    for line in lines:
        if "--> H2M | WRITE" not in line: continue
        parts = line.split('|')[2].strip().split()
        pkt = [int(b, 16) for b in parts]
        if len(pkt) < 8: continue
        
        # 08 07 PAGE OFF LEN ...
        page = pkt[2]
        offset = pkt[3]
        length = pkt[4]
        payload = pkt[5:]
        
        # Check if basic Type 0A
        is_type_0a = False
        d1, d2, d3 = 0,0,0
        rem = []
        
        if length == 4 and payload[0] == 0x0A:
             is_type_0a = True
             d1, d2, d3 = payload[1], payload[2], payload[3]
             rem = payload[4:]
             
        elif length == 0:
             # Check for 0A in payload start
             if len(payload) > 0 and payload[0] == 0x0A:
                 is_type_0a = True
                 # Variable length? 
                 # Usually 0A [Size] [Data...]
                 if len(payload) > 1:
                     d1 = payload[1] # Size?
                     # D2/D3 not applicable in fixed slots maybe
                     rem = payload[2:]
        
        if is_type_0a:
            rem_hex = " ".join([f"{b:02X}" for b in rem])
            # Try ASCII for rem
            txt = ""
            try:
                # UTF-16LE??
                # rem is list of ints
                # Need even number of bytes
                if len(rem) % 2 == 0:
                     b = bytes(rem)
                     txt = b.decode('utf-16le')
            except: pass
            
            clean_txt = "".join([c if c.isprintable() else '.' for c in txt])
            
            print(f"{offset:02X}     | {length:02X}   | 0A   | {d1:02X}   | {d2:02X}   | {d3:02X}   | {rem_hex} ({clean_txt})")

if __name__ == "__main__":
    analyze_0a()
