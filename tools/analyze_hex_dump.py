from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import subprocess
import re

def analyze_hex():
    print("Running tshark...")
    # Use subprocess to get output directly
    cmd = ['tshark', '-r', 'usbcap/macros set to all 12 buttons.pcapng', '-x']
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    hex_output = result.stdout
    
    print(f"Got {len(hex_output)} chars of hex data.")
    
    # We want to find "08 07" usage.
    # The hex dump format is: offset  hex  ascii
    # We can just sanitize the hex part and look for the byte sequences.
    
    # 1. Clean up: remove offsets and ascii
    clean_hex = ""
    for line in hex_output.splitlines():
        # Line format: "0020  01 00 11 00 08 07 ..."
        # Match hex part (2 chars + space)
        # Grep roughly columns 6 to 54 typically
        # But easier to regex match valid hex pairs
        parts = line.strip().split('  ')
        if len(parts) > 1:
            hex_part = parts[1]
            # remove spaces
            hex_part = hex_part.replace(' ', '')
            clean_hex += hex_part
            
    # Now valid hex stream.
    # Search for "080700" (Write + Page 0?)
    # Or just "0807"
    
    # Convert to bytes for easier searching
    try:
        data = bytes.fromhex(clean_hex)
    except:
        # fallback if messy
        data = b''
        import binascii
        # try strictly extracting
        clean_hex = re.sub(r'[^0-9a-fA-F]', '', clean_hex)
        data = binascii.unhexlify(clean_hex)
        
    print(f"Total Bytes: {len(data)}")
    
    # Analyze Bind Packets (Type 06)
    print("\n--- ANALYZING TYPE 06 BINDINGS ---")
    
    i = 0
    count = 0
    while i < len(data) - 17:
        if data[i] == 0x08 and data[i+1] == 0x07:
            # Check Payload Type
            # Payload starts at index 6?
            # 08 07 00 PG OFF LEN [TYPE]
            length = data[i+5]
            if length == 0x0A:
                 # Check Type byte (Index 6)
                 pkt_type = data[i+6]
                 if pkt_type == 0x06:
                     print(f"Packet: {data[i:i+17].hex()}  Len: {length:02X}  Type: {pkt_type:02X}")
                     count += 1
                     if count >= 5: break
            
            i += 17
        else:
            i += 1
    return
    
    # Analyze unique Page/Offset combinations (Start of slots)
    # Slots usually start at Offset 0x00 or 0x80.
    # Group by Page/Offset
    starts = sorted(list(set(macro_writes)))
    
    print("\nUnique Write Targets (Page, Offset):")
    for p, o in starts:
        # Check if this looks like a slot start (00 or 80)
        # Note: Large macros span multiple chunks (00, 0A, 14...)
        # We only care about the MINIMUM offset for each Page/Block
        pass
        
    # Heuristic: Filter for 0x00 and 0x80 markers which denote Slot Starts?
    # Or just print them all? There might be hundreds.
    # Better: identify "Slot Starts".
    # A slot start usually has offset 0x00 or 0x80.
    
    slot_starts = []
    for p, o in starts:
        if o == 0x00 or o == 0x80:
            slot_starts.append((p, o))
            
    print(f"Potential Slot Starts (0x00/0x80): {len(slot_starts)}")
    for p, o in slot_starts:
        # Calculate Linear Index?
        # Addr = P*256 + O.
        # Base 0x300.
        # Idx = (Addr - 0x300) / 0x180 ?
        addr = (p << 8) | o
        rel = addr - 0x300
        if rel >= 0 and rel % 0x180 == 0:
            calc_idx = rel // 0x180
            print(f"  Page {p:02X} Off {o:02X} -> Linear Index {calc_idx}")
        else:
            print(f"  Page {p:02X} Off {o:02X} -> Unknown Alignment (Rel {rel:X})")

if __name__ == "__main__":
    analyze_hex()
