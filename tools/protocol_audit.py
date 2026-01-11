from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re
import sys

# Protocol Knowledge Base
# We define "Expectations" for each packet type.
# If a byte matches the expectation (Value or Wildcard), it's "Understood".
# If not, it's a "Mystery".

# Packet Format:
# [CMD] [PAGE] [OFFSET] [LEN] [TYPE] [D1] [D2] [D3] [ZERO...]

def audit_captures():
    try:
        with open("artifacts/txt/host_mouse_communication.txt", 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("Error: artifacts/txt/host_mouse_communication.txt not found. Please run analyze_captures_to_log.py first.")
        return

    unknowns = {} # Key: PacketType, Value: List of (PacketHex, Explanation)

    for line in lines:
        if "--> H2M | WRITE" not in line:
            continue
            
        # Extract Hex
        parts = line.split('|')[2].strip().split()
        pkt = [int(b, 16) for b in parts]
        
        if len(pkt) < 8: continue # Too short to judge (e.g. 0x04 cmd)
        
        cmd = pkt[0]
        
        # We focus on CMD 0x07 (Write Data) or 0x08 (Wrapper depending on view)
        # But in the log it looks like "08 07 00 60 04 05 00 00 4B ..."
        
        # 0: Report ID (08)
        # 1: Command (07 = Write, 03 = Handshake)
        
        if pkt[1] == 0x03:
            # Handshake. Should be 08 03 ... 
            # Check padding.
            if any(b != 0 for b in pkt[2:]):
                log_unknown(unknowns, "HANDSHAKE", pkt, "Non-zero padding in Handshake")
            continue
            
        if pkt[1] == 0x09:
             # Reset?
             continue
             
        if pkt[1] != 0x07:
            continue
            
        # WRITE PACKET PARSING
        page = pkt[2]
        offset = pkt[3]
        length = pkt[4] # Valid Data Length
        
        # The payload starts at pkt[5]
        # BUT, if Length is 04 (Standard Binding), the structure is:
        # [05: Type] [06: D1] [07: D2] [08: D3]
        
        payload = pkt[5:]
        
        # Check Padding (Data after length)
        # Actual Data ends at 5 + length
        # Remaining bytes should be 00?
        padding_start = 5 + length
        if padding_start < len(pkt):
            padding = pkt[padding_start:]
            if any(b != 0 for b in padding):
                 log_unknown(unknowns, "PADDING", pkt, f"Non-zero data after len {length}")
                 
        # ANALYZE CONTENT BASED ON TYPE
        if length == 4:
            btype = payload[0]
            d1 = payload[1]
            d2 = payload[2]
            d3 = payload[3]
            
            # CHECK CHECKSUM
            # Formula: D3 = 0x55 - (Type + D1 + D2)
            expected_d3 = (0x55 - (btype + d1 + d2)) & 0xFF
            
            # --- TYPE 01: MOUSE BUTTON ---
            if btype == 0x01:
                # D1 = Button Mask (1=Left, 2=Right, 4=Mid, 8=Back, 10=Fwd)
                # D2 = 00
                # D3 = ???
                if d2 != 0:
                     log_unknown(unknowns, "TYPE 01 (MOUSE)", pkt, f"D2 is {d2:02X} (Expected 00)")
                
                # Check D3 logic
                # User says: "Decode every char". 
                # Is D3 random? Or specific code?
                # Checksum formula applies?
                if d3 != expected_d3:
                     # Log it as "D3 is specific"
                     log_unknown(unknowns, "TYPE 01 (MOUSE) BAD CHECKSUM", pkt, f"D3={d3:02X} Exp={expected_d3:02X}")
                     
            # --- TYPE 05: KEYBOARD ---
            elif btype == 0x05:
                # D1 = Key Code, D2 = Modifiers
                # D3 = Checksum?
                if d3 != expected_d3:
                    log_unknown(unknowns, "TYPE 05 (KBD)", pkt, f"Checksum fail? D3={d3:02X} Exp={expected_d3:02X}")
                    
            # --- TYPE 06: MACRO ---
            elif btype == 0x06:
                # D1 = Index, D2 = Repeat
                # D3 = Checksum
                if d3 != expected_d3:
                    log_unknown(unknowns, "TYPE 06 (MACRO)", pkt, f"Checksum fail? D3={d3:02X} Exp={expected_d3:02X}")
                    
            # --- TYPE 04: SPECIAL ---
            elif btype == 0x04:
                # Fire Key / Triple Click
                # D1 = Delay, D2 = Reps
                if d3 != expected_d3:
                    log_unknown(unknowns, "TYPE 04 (SPECIAL)", pkt, f"Checksum fail? D3={d3:02X} Exp={expected_d3:02X}")
                    
            # --- TYPE 07: POLL RATE ---
            elif btype == 0x07:
                 if d3 != expected_d3:
                    log_unknown(unknowns, "TYPE 07 (POLL)", pkt, f"Checksum fail? D3={d3:02X} Exp={expected_d3:02X}")
            
            # --- TYPE 02: DPI LEGACY? ---
            elif btype == 0x02:
                 pass
                 
            # --- TYPE 08: RGB TOGGLE ---
            elif btype == 0x08:
                 if d3 != expected_d3:
                    log_unknown(unknowns, "TYPE 08 (RGB)", pkt, f"Checksum fail? D3={d3:02X} Exp={expected_d3:02X}")

            elif btype == 0x00: # Disabled
                 pass
                 
            else:
                 # Check if it matches the "Polling Rate" signature
                 # 04 0A 00 03 ...
                 log_unknown(unknowns, f"UNKNOWN TYPE {btype:02X}", pkt, f"D1={d1:02X} D2={d2:02X} D3={d3:02X}")

        # LONG WRITES or SPECIAL HEADERS
        elif length == 0:
             # Header packet?
             # 08 07 00 03 00 0A ...
             # Page 00, Offset 03, Len 00.
             # Maybe Offset 03 is special?
             # Payload: 0A 06 31 ...
             
             # Let's frame it as: It's NOT length 0.
             # Maybe the byte at index 4 isn't ALWAYS length?
             # But for standard packets (Offset > 0x04) it seems to be.
             
             log_unknown(unknowns, "ZERO LEN", pkt, "Payload: " + " ".join([f"{b:02X}" for b in payload]))
             
        elif length > 4:
            # RGB is usually len 10 (0x0A) or 14 (0x0E)
            # Offset 0x54 check
            if offset == 0x54:
                # RGB Packet
                pass
            
            # Macro Data
            elif page >= 0x03:
                # Macro data chunks.
                # Just verify the terminator if present
                pass
                
    # PRINT REPORT
    print("=== PROTOCOL AUDIT: UNKNOWN BYTES ===")
    for cat, items in unknowns.items():
        print(f"\n[{cat}]")
        for pkt, msg in items[:5]: # Show top 5
            hex_str = " ".join([f"{b:02X}" for b in pkt])
            print(f"  {hex_str} -> {msg}")
        if len(items) > 5:
            print(f"  ... and {len(items)-5} more.")

def log_unknown(db, cat, pkt, msg):
    if cat not in db: db[cat] = []
    db[cat].append((pkt, msg))

if __name__ == "__main__":
    audit_captures()
