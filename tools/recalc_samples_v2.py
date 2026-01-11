from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def recalc_v2():
    target_cap = "bind macros 123"
    
    with open("artifacts/txt/host_mouse_communication.txt", 'r') as f:
        lines = f.readlines()
        
    pages = {}
    in_target = False
    
    for line in lines:
        if line.startswith("["):
            if target_cap in line:
                in_target = True
                print("Found target capture.")
                pages = {}
            else:
                in_target = False
            continue
            
        if not in_target: continue
        
        if "--> H2M | WRITE" not in line: continue
        parts = line.split('|')[2].strip().split()
        pkt = [int(b, 16) for b in parts]
        if len(pkt) > 5 and pkt[1] == 0x07:
             print(f"Debug: Pkt: {pkt[:6]}")
        if pkt[1] != 0x07: continue
        
        page = pkt[2]
        offset = pkt[3]
        length = pkt[4]
        data = pkt[5:]
        
        if page not in pages: pages[page] = bytearray([0] * 256)
        valid_len = min(length, len(data))
        for i in range(valid_len):
            if offset+i < 256:
                pages[page][offset+i] = data[i]
        # Debug
        # print(f"Wrote Page {page:02X} Off {offset:02X}")
                
    # Analyze
    print(f"Analysis: {len(pages)} pages found: {[hex(k) for k in pages.keys()]}")
    print(f"{'PAGE':<4} | {'TERM_OFF':<8} | {'SUM':<4} | {'COUNT':<5} | {'TARGET':<6} | {'(InvS-C)'} | {'K_NEEDED':<8}")
    print("-" * 80)
    
    for p_idx in sorted(pages.keys()):
        buf = pages[p_idx]
        for i in range(256 - 6):
            if buf[i] == 0x00 and buf[i+1] == 0x03 and buf[i+3] == 0x00 and buf[i+4] == 0x00:
                inner = buf[i+2]
                if inner == 0 and i < 0x20: continue
                
                # Payload: 0 to i
                payload = buf[0:i]
                s_sum = sum(payload) & 0xFF
                count = buf[0x1F]
                
                inv_sum = (~s_sum) & 0xFF
                base_calc = (inv_sum - count) & 0xFF
                k = (inner - base_calc) & 0xFF
                
                print(f"{p_idx:02X}   | {i:02X}       | {s_sum:02X}   | {count:02X}    | {inner:02X}     | {base_calc:02X}       | {k:02X} ({k})")

if __name__ == "__main__":
    recalc_v2()
