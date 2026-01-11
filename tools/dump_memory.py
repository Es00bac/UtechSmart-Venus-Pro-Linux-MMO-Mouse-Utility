from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import sys
import os
import time
from venus_protocol import VenusDevice, VENDOR_ID, PRODUCT_IDS, list_devices

def main():
    avail = list_devices()
    if not avail:
        print("No Venus Pro devices found on Interface 1.")
        sys.exit(1)
    
    # Prioritize "Dual Mode Mouse" over "Wireless Receiver"
    # The receiver doesn't seem to respond to flash reads.
    selected = avail[0]
    for d in avail:
        if "Dual Mode Mouse" in d.product:
            selected = d
            break
            
    print(f"Opening {selected.product} at {selected.path}")
    
    try:
        device = VenusDevice(selected.path)
        device.open()
        print(f"Connected.")
    except Exception as e:
        print(f"Failed to open device: {e}")
        sys.exit(1)

    # The mouse memory consists of 256 pages of 256 bytes each.
    # We dump all of them by default now.
    pages_to_dump = list(range(0, 256))
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "full":
            # This is now the default, but keeping it for compatibility
            pass
        elif sys.argv[1] in ("-h", "--help", "help"):
            print("Usage: python3 tools/dump_memory.py [page1] [page2] ... | full")
            print("Default: dumps all 256 pages.")
            sys.exit(0)
        else:
            try:
                pages_to_dump = [int(p, 16) if p.startswith("0x") else int(p) for p in sys.argv[1:]]
            except ValueError:
                print("Usage: python3 tools/dump_memory.py [page1] [page2] ... | full")
                sys.exit(1)

    print(f"Dumping {len(pages_to_dump)} pages.")
    
    timestamp = int(time.time())
    out_dir = f"dumps/dump_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)
    
    for i, page in enumerate(pages_to_dump):
        print(f"[{i+1}/{len(pages_to_dump)}] Reading Page 0x{page:02X}...", end="", flush=True)
        page_data = bytearray()
        
        # Each page is typically 256 bytes?
        # Let's try to read 0x00 to 0xFF in 8-byte chunks
        try:
            for offset in range(0, 256, 8):
                chunk = device.read_flash(page, offset, 8)
                page_data.extend(chunk)
                if offset % 64 == 0:
                    print(".", end="", flush=True)
            
            # Save to file
            with open(f"{out_dir}/page_{page:02X}.bin", "wb") as f:
                f.write(page_data)
            
            # Save hex visual
            with open(f"{out_dir}/page_{page:02X}.txt", "w") as f:
                for i in range(0, len(page_data), 16):
                    line = page_data[i:i+16]
                    hex_str = " ".join(f"{b:02x}" for b in line)
                    f.write(f"{i:04x}: {hex_str}\n")
            
            print(" Done")
        except Exception as e:
            print(f" Error: {e}")

    print(f"\nDump saved to {out_dir}")
    device.close()

if __name__ == "__main__":
    main()
