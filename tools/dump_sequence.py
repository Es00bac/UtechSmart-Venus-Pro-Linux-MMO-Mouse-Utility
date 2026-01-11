from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import subprocess

def dump_sequence():
    print("Running tshark...")
    cmd = ['tshark', '-r', 'usbcap/macros set to all 12 buttons.pcapng', '-x']
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    hex_output = result.stdout
    
    clean_hex = ""
    for line in hex_output.splitlines():
        parts = line.strip().split('  ')
        if len(parts) > 1:
            clean_hex += parts[1].replace(' ', '')
            
    try:
        data = bytes.fromhex(clean_hex)
    except:
        import re
        clean_hex = re.sub(r'[^0-9a-fA-F]', '', clean_hex)
        data = bytes.fromhex(clean_hex)
        
    print(f"Total Bytes: {len(data)}")
    
    # Iterate and print Command structure
    i = 0
    packet_count = 0
    
    # Iterate and print Command structure
    i = 0
    packet_count = 0
    history = []
    
    found_first_write = False
    
    # Iterate and print Command structure
    i = 0
    packet_count = 0
    
    while i < len(data) - 17:
        if data[i] == 0x08 or data[i] == 0x09:
            pkt = data[i:i+17]
            is_host = (data[i] == 0x08)
            cmd = pkt[1]
            
            # Print Range 100-300
            if 100 <= packet_count <= 300:
                desc = ""
                if is_host:
                    prefix = "H2M"
                    if cmd == 0x07:
                         desc = f"WRITE LEN {pkt[5]:02X}"
                    elif cmd == 0x03:
                        desc = "HANDSHAKE"
                    elif cmd == 0x09:
                        desc = "RESET"
                    elif cmd == 0x04:
                        desc = "CMD 04"
                    elif cmd == 0x01:
                        desc = "CMD 01"
                    elif cmd == 0x4D:
                        desc = "CMD 4D (UNLOCK?)"
                    else:
                        desc = f"CMD {cmd:02X}"
                else:
                    prefix = "M2H"
                    desc = f"RSP {cmd:02X}"
                
                print(f"[{packet_count:04d}] {prefix} {desc} ({pkt.hex()})")
            
            i += 17
            packet_count += 1
        else:
            i += 1
            
    print("Done.")

if __name__ == "__main__":
    dump_sequence()
