from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import glob
import os

# Output file
OUTPUT_FILE = "artifacts/txt/host_mouse_communication.txt"

def parse_capture(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()

    packets = []
    i = 0
    while i < len(data) - 17:
        if data[i] in [0x08, 0x09] and data[i+1] <= 0x20:
            chunk = data[i:i+17]
            checksum = (0x55 - sum(chunk[:16])) & 0xFF
            if chunk[16] == checksum:
                # Filter out pure mouse movement (Report ID 0x02 usually, but here we filter by CMD)
                # Config features are usually 0x08 (H2M) or 0x09 (M2H?) or 0x04/0x07 etc.
                # HID report ID for mouse movement is usually 0x01 or 0x02.
                # Our capture filter checks for signature data[i] in [0x08, 0x09] 
                # effectively filtering out report IDs 0x01/0x02 (mouse move).
                
                direction = "--> H2M" if chunk[0] == 0x08 else "<-- M2H"
                
                cmd_map = {
                    0x01: "CMD_01",
                    0x03: "HANDSHAKE",
                    0x04: "COMMIT",
                    0x07: "WRITE",
                    0x08: "READ",
                    0x09: "RESET/INIT"
                }
                cmd_name = cmd_map.get(chunk[1], f"UNK_{chunk[1]:02X}")
                
                # Format payload
                payload_str = " ".join([f"{b:02X}" for b in chunk])
                
                # Annotation
                annotation = ""
                if chunk[1] == 0x07: # Write
                    page = chunk[3]
                    offset = chunk[4]
                    length = chunk[5]
                    data_bytes = chunk[6:6+length]
                    annotation = f" [Page:0x{page:02X} Off:0x{offset:02X} Len:{length}]"
                    
                    # Try text decode for macro names
                    try:
                        txt = data_bytes.decode('utf-16le', errors='ignore').split('\x00')[0]
                        clean = "".join([c for c in txt if c.isalnum()])
                        if len(clean) > 1: annotation += f" Text:'{clean}'"
                    except: pass
                    
                    # Highlight Terminator
                    if length == 6 and data_bytes[0] == 0x00 and data_bytes[1] == 0x03:
                         annotation += f" ** TERMINATOR Inner=0x{data_bytes[2]:02X} **"

                packets.append(f"{direction} | {cmd_name:<10} | {payload_str} |{annotation}")
                i += 17
                continue
        i += 1
    return packets

def main():
    files = sorted(glob.glob("usbcap/*.pcapng"))
    
    with open(OUTPUT_FILE, 'w') as out:
        out.write("COMBINED HOST-MOUSE COMMUNICATION LOG\n")
        out.write("======================================\n\n")
        
        for f in files:
            fname = os.path.basename(f)
            out.write(f"\n[{fname}]\n")
            out.write("-" * len(fname) + "\n")
            
            packets = parse_capture(f)
            if not packets:
                out.write("  (No relevant config packets found)\n")
            else:
                for p in packets:
                    out.write(f"  {p}\n")
            out.write("\n")

    print(f"Log generated at {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    main()
