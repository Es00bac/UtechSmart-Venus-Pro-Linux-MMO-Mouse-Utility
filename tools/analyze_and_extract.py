from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import os
import glob

class Colors:
    HEADER = '\033[95m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def extract_from_capture(filepath):
    print(f"{Colors.HEADER}Analyzing {os.path.basename(filepath)}...{Colors.ENDC}")
    
    with open(filepath, 'rb') as f:
        data = f.read()

    # Find valid HID reports
    packets = []
    i = 0
    while i < len(data) - 17:
        if data[i] in [0x08, 0x09] and data[i+1] <= 0x20:
            chunk = data[i:i+17]
            checksum = (0x55 - sum(chunk[:16])) & 0xFF
            if chunk[16] == checksum:
                packets.append(chunk)
                i += 17
                continue
        i += 1

    print(f"Parsed {len(packets)} packets")

    # Reconstruct Memory
    memory = {}
    
    for p in packets:
        if p[0] == 0x08 and p[1] == 0x07: # WRITE
            page = p[3]
            offset = p[4]
            length = p[5]
            payload = p[6:6+length]
            
            if page not in memory: memory[page] = {}
            for j, b in enumerate(payload):
                memory[page][offset + j] = b

    print(f"Reconstructed pages: {sorted(memory.keys())}")
    
    # Process each page
    for page_id, page_data in memory.items():
        if page_id < 0x03: continue
        
        # Sparse dictionary to bytes
        max_off = max(page_data.keys())
        pbytes = bytearray(max_off + 1)
        # Fill known
        for off, val in page_data.items():
            pbytes[off] = val
            
        print(f"Page 0x{page_id:02X}: Size {len(pbytes)} bytes")
        # DEBUG: Print hex dump
        # print(pbytes.hex())
        
        # Find Terminator
        found = False
        # Relaxed search and extended range
        for i in range(len(pbytes) - 5):
            # Check for terminator signature: 00 03 [INNER] 00 (first 4 bytes)
            if pbytes[i] == 0x00 and pbytes[i+1] == 0x03:
                # Potential match
                if i+3 < len(pbytes) and pbytes[i+3] == 0x00:
                    inner = pbytes[i+2]
                    term_offset = i
                    
                    print(f"  {Colors.OKGREEN}Terminator found at 0x{i:02X}, Inner=0x{inner:02X}{Colors.ENDC}")
                    
                    # Extract macro info
                    name_len = pbytes[0]
                    name = f"unk_{page_id:02x}"
                    if name_len > 0 and name_len < len(pbytes):
                        try:
                            # Verify valid name length
                            name_raw = pbytes[1:1+name_len]
                            name_decoded = name_raw.decode('utf-16le', errors='ignore').split('\x00')[0]
                            clean_name = "".join([c for c in name_decoded if c.isalnum()])
                            if clean_name: name = clean_name
                        except: pass
                    
                    fn = f"extract_{name}_{page_id:02X}_inner{inner:02X}.bin"
                    
                    with open(fn, 'wb') as out:
                        out.write(pbytes[0:term_offset])
                    print(f"  Saved {fn}")
                    found = True
        
        if not found:
            print(f"  {Colors.WARNING}No terminator found in Page 0x{page_id:02X}{Colors.ENDC}")
            # DEBUG: Show content at end of page
            if len(pbytes) > 10:
                print(f"  Last 16 bytes: {pbytes[-16:].hex()}")

if __name__ == "__main__":
    # Analyze the specific multi-macro file
    f = "usbcap/bind macros 123 to btns 1 and 6 -456 to 2 and 5 - 789 to 3 and 4 - 7 to ctrl-alt-del - 8 fire 3x with 40ms delay - 9 tripple click - 10 rgb 11 polling rate 12 stop 13 play.pcapng"
    extract_from_capture(f)
