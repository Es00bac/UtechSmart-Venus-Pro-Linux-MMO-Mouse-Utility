from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import subprocess

def find_button1_bind():
    # Run Tshark
    cmd = [
        "tshark", "-x", "-r", "usbcap/macros set to all 12 buttons.pcapng"
    ]
    print("Running tshark...")
    p = subprocess.run(cmd, capture_output=True, text=True)
    hex_data = p.stdout.replace('\n', '').replace(' ', '')
    
    # Filter non-hex for safety
    clean = "".join([c for c in hex_data if c in '0123456789ABCDEFabcdef'])
    
    import binascii
    data = binascii.unhexlify(clean)
        
    print(f"Scanning {len(data)} bytes...")
    
    found = False
    i = 0
    while i < len(data) - 17:
        if data[i] == 0x08 and data[i+1] == 0x07:
            # Check Offset 0x60 (Byte 4)
            # 08 07 PG OFF
            if data[i+4] == 0x60:
                 print(f"Found Write to Offset 60: {data[i:i+17].hex()}")
                 found = True
            
            i += 17
        else:
            i += 1
            
    if not found:
        print("No Packet found for Offset 60.")

if __name__ == "__main__":
    find_button1_bind()
