from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import subprocess
import os
import sys

def analyze_pcap():
    pcap_path = "usbcap/create simple_macro dn-1 up-1 no delay bind to button 1.pcapng"
    
    cmd = [
        "tshark",
        "-r", pcap_path,
        "-Y", "usbhid.data",  # Filter
        "-T", "fields",
        "-e", "usbhid.data"
    ]
    
    print(f"Running tshark on {pcap_path}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running tshark: {e}")
        # Try usb.capdata if usbhid.data fails to produce output?
        cmd[2] = "usb.capdata"
        cmd[4] = "usb.capdata"
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    lines = result.stdout.splitlines()
    print(f"Extracted {len(lines)} packets.")
    
    # DEBUG: Print first 20 lines
    for i in range(min(20, len(lines))):
        print(f"RAW[{i}]: {lines[i]}")
    
    macro_packets = []
    
    macro_packets = []
    
    found_config = False
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        hex_str = line.replace(':', '')
        
        # Look for signature of Write Command: 08 07
        if "0807" in hex_str or "0804" in hex_str or "0809" in hex_str:
            
            try:
                data = bytes.fromhex(hex_str)
            except:
                continue

            # Naive parsing: Look for 08 07 sequence
            # Create a bytes object to search in? Or just string search and convert back?
            # String search is easier given USBPcap often has prefixes
            
            idx07 = hex_str.find("0807")
            if idx07 != -1 and idx07 % 2 == 0:
                 # It's byte-aligned (08 07)
                 idx = idx07 // 2
                 pkt = data[idx:]
                 # Must have enough length for a valid packet
                 if len(pkt) >= 17:
                     page = pkt[3]
                     offset = pkt[4]
                     length = pkt[5]
                     payload = pkt[6:6+length]
                     
                     # Checksum Check for verification
                     # Checksum is at index 16.
                     # Formula: (0x55 - Sum(0..15)) & 0xFF
                     calc_sum = (0x55 - sum(pkt[0:16])) & 0xFF
                     pkt_sum = pkt[16]
                     valid = (calc_sum == pkt_sum)
                     valid_str = "OK" if valid else f"BAD (Exp {calc_sum:02X})"
                     
                     print(f"WRITE: Page={page:02X} Off={offset:02X} Len={length:02X} Data={payload.hex(' ')} [{valid_str}]")
                     found_config = True
                     
                     if page >= 0x03:
                         macro_packets.append(pkt)
            
            if "0804" in hex_str:
                print("CMD 04 (Commit)")
                
            if "0809" in hex_str:
                # Potential Unlock 08 09 ...
                if "0809" in hex_str:
                     print(f"CMD 09 (Unlock/Reset?): {hex_str}")

    if not found_config:
        print("No configuration packets found via simple search.")

    # Analyze Macro Structure
    if macro_packets:
        print("\n--- MACRO DATA ANALYSIS ---")
        full_buffer = bytearray()
        # Sort/Assemble? Assuming sequential in pcap
        # We need to detect where the stream starts/ends.
        # Just concat payload for now?
        # Note: Packets have offsets.
        
        # Group by Page
        last_page = -1
        last_offset = -1
        
        current_macro_data = bytearray(300) # Pre-fill 00?
        
        for pkt in macro_packets:
            page = pkt[3]
            offset = pkt[4]
            length = pkt[5]
            payload = pkt[6:6+length]
            
            print(f"M-PKT: Pg{page:02X} +{offset:02X} [{length}] : {payload.hex(' ')}")

if __name__ == "__main__":
    analyze_pcap()
