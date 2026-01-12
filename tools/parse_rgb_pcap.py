import struct
import sys

def parse_pcapng(filename):
    with open(filename, "rb") as f:
        data = f.read()
        
    offset = 0
    packets = []
    
    while offset < len(data):
        # Block Type (4 bytes), Block Length (4 bytes)
        if offset + 8 > len(data): break
        
        blk_type, blk_len = struct.unpack("<II", data[offset:offset+8])
        
        if blk_type == 6: # Enhanced Packet Block
            # EPB Structure:
            # Type (4), Len (4), Interface (4), Timestamp High (4), Timestamp Low (4), CapLen (4), OrgLen (4), Packet Data...
            if offset + 32 > len(data): break
            
            cap_len = struct.unpack("<I", data[offset+20:offset+24])[0]
            
            packet_data = data[offset+28 : offset+28+cap_len]
            
            # USBMON Header is usually 48 or 64 bytes. 
            # Venus packets are 17 bytes.
            # We are looking for the payload which starts with 08 07 ...
            
            # Brute force search for signature in packet data
            # Signature: 08 07 00 00 54 08 (Write RGB)
            sig = b'\x08\x07\x00\x00\x54\x08'
            
            idx = packet_data.find(sig)
            if idx != -1:
                # Extract the 17-byte packet starting from 08
                # Actually, the 08 07 is the command.
                # The raw packet is 17 bytes.
                # 08 07 00 00 54 08 [R] [G] [B] [Mode] [Speed] [?] [B1] [B2] [00] [00] [Chk]
                # Length check: 08 07 ... is 6 bytes.
                # Total payload is 14 bytes (after cmd).
                # Wait, Report 08 Cmd 07 Payload...
                # Byte 0: 08
                # Byte 1: 07
                # Byte 2: 00 (Page)
                # Byte 3: 00 (Page)
                # Byte 4: 54 (Offset)
                # Byte 5: 08 (Length)
                # Byte 6: R
                # Byte 7: G
                # Byte 8: B
                # Byte 9: Mode
                # Byte 10: Speed?
                # Byte 11: ?
                # Byte 12: B1
                # Byte 13: B2
                # Byte 14: 00
                # Byte 15: 00
                # Byte 16: Checksum
                
                # So we want 17 bytes starting at idx
                if idx + 17 <= len(packet_data):
                    full_pkt = packet_data[idx : idx+17]
                    packets.append(full_pkt)
        
        offset += blk_len
        
    return packets

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_pcapng.py <file.pcapng>")
        return

    packets = parse_pcapng(sys.argv[1])
    print(f"Found {len(packets)} RGB packets.")
    
    unique_colors = []
    
    for pkt in packets:
        # R, G, B are at offsets 6, 7, 8
        r, g, b = pkt[6], pkt[7], pkt[8]
        mode = pkt[9]
        b1 = pkt[12]
        
        color = (r, g, b)
        if color not in unique_colors:
            unique_colors.append(color)
            print(f"RGB: {r:02X} {g:02X} {b:02X} (Mode {mode:02X}, B1 {b1:02X})")
            print(f"RAW: {pkt.hex()}")

if __name__ == "__main__":
    main()
