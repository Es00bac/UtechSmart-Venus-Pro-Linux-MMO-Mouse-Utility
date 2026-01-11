from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def recalc():
    with open("artifacts/txt/host_mouse_communication.txt", 'r') as f:
        lines = f.readlines()
        
    current_capture = "Unknown"
    pages = {} 
    
    print(f"{'CAP':<20} | {'PAGE':<4} | {'TERM_OFF':<8} | {'SUM':<4} | {'COUNT':<5} | {'TARGET':<6} | {'(InvS-C)'} | {'K_NEEDED':<8}")
    print("-" * 120)

    def process_pages(cap_name, pgs):
        for p_idx in sorted(pgs.keys()):
            buf = pgs[p_idx]
            for i in range(256 - 6):
                if buf[i] == 0x00 and buf[i+1] == 0x03 and buf[i+3] == 0x00 and buf[i+4] == 0x00:
                    inner = buf[i+2]
                    # Filter empty/garbage
                    if inner == 0 and i < 0x20: continue
                    
                    if i > 0x10:
                        payload = buf[0:i]
                        s_sum = sum(payload) & 0xFF
                        count = buf[0x1F]
                        
                        inv_sum = (~s_sum) & 0xFF
                        base_calc = (inv_sum - count) & 0xFF
                        k = (inner - base_calc) & 0xFF
                        
                        # Shorten capture name
                        short_cap = cap_name[:18]
                        print(f"{short_cap:<20} | {p_idx:02X}   | {i:02X}       | {s_sum:02X}   | {count:02X}    | {inner:02X}     | {base_calc:02X}       | {k:02X} ({k})")

    for line in lines:
        if line.startswith("["):
            # New capture, process previous
            if pages:
                process_pages(current_capture, pages)
            pages = {}
            current_capture = line.strip("[]\n")
            continue
            
        if "--> H2M | WRITE" not in line: continue
        parts = line.split('|')[2].strip().split()
        pkt = [int(b, 16) for b in parts]
        
        if pkt[1] != 0x07: continue
        
        page = pkt[2]
        offset = pkt[3]
        length = pkt[4]
        data = pkt[5:]
        
        if page not in pages: pages[page] = bytearray([0] * 256)
        
        valid_len = min(length, len(data))
        if valid_len > 0:
            for i in range(valid_len):
                if offset+i < 256:
                    pages[page][offset+i] = data[i]

    # Process final
    if pages:
        process_pages(current_capture, pages)

if __name__ == "__main__":
    recalc()
