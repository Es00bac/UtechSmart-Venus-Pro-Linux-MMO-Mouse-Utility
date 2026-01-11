from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def analyze_bases():
    log_file = "artifacts/txt/host_mouse_communication.txt"
    print(f"Analyzing {log_file} for Packet Checksum Bases...")
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
        
    bases = {} # Map Type -> Set of Bases
    
    for line in lines:
        if "--> H2M | WRITE" not in line: continue
        
        parts = line.split('|')[2].strip().split()
        pkt = [int(b, 16) for b in parts]
        
        # Must be 17 bytes
        if len(pkt) != 17: continue
        
        # Pkt Structure: [08] [Cmd] [P1] [P2] [P3] [Len] [TYPE] ... [CHK]
        # Cmd is usually 07 (Write) or 03 (Handshake) or 09 (Reset)
        cmd = pkt[1]
        
        # Calculate Sum of 0-15
        s_sum = sum(pkt[0:16]) & 0xFF
        checksum = pkt[16]
        
        # Base = (Checksum + Sum) & 0xFF
        # Because Checksum = Base - Sum
        base = (checksum + s_sum) & 0xFF
        
        # Categorize by Cmd + Type (if Cmd=07)
        key = f"CMD_{cmd:02X}"
        if cmd == 0x07:
            # Type is usually at index 6 (if format 00 xx xx 04 TYPE)
            # Or if format is simple...
            # Check length at index 5?
            length = pkt[5]
            if length == 0x04:
                # Type at 6
                ptype = pkt[6]
                key = f"CMD_07_TYPE_{ptype:02X}"
            elif length == 0x0A:
                 # Macro Data
                 key = "CMD_07_MACRO_DATA"
            else:
                 key = f"CMD_07_LEN_{length:02X}"
                 
        if key not in bases: bases[key] = []
        bases[key].append(base)
        
    print("\nResults:")
    for key, val_list in bases.items():
        unique = set(val_list)
        count = len(val_list)
        print(f"{key}: {count} packets. Bases: {[hex(b) for b in unique]}")

if __name__ == "__main__":
    analyze_bases()
