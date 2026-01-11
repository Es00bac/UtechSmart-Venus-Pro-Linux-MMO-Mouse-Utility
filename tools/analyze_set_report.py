from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import subprocess
import re

def analyze_pcap(pcap_file):
    print(f"Analyzing {pcap_file}...")
    
    # Extract frame number, direction, data fields
    cmd = [
        "tshark", "-r", pcap_file,
        "-T", "fields",
        "-e", "frame.number",
        "-e", "usb.endpoint_address",
        "-e", "usb.data_fragment",
        "-e", "usbhid.data",
        "-e", "usb.capdata",
        "-e", "usb.irp_info"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    for line in result.stdout.splitlines():
        parts = line.split('\t')
        if len(parts) < 6: continue
        
        fn = parts[0]
        ep = parts[1]
        
        # Try finding data in any of the fields
        data_hex = ""
        for p in parts[2:5]:
            if p:
                data_hex = p
                break
        
        if not data_hex: continue
        
        # Handle multiple values (comma separated)
        data_hex = data_hex.split(',')[0]
        
        try:
            raw_hex = data_hex.replace(':', '')
            data = bytes.fromhex(raw_hex)
        except:
            continue
            
        if len(data) < 17: continue
        
        # Take only 17 bytes if it's longer
        data = data[:17]
        
        report_id = data[0]
        payload = data[0:16]
        chk_pkt = data[16]
        
        s_sum = sum(payload) & 0xFF
        std_chk = (0x55 - s_sum) & 0xFF
        
        direction = "IN " if ep.startswith("0x8") else "OUT"
        
        print(f"Frame {fn:4}: {direction} EP={ep:4} ID={data[0]:02X} Cmd={data[1]:02X} Pg={data[3]:02X} Off={data[4]:02X} Chk={chk_pkt:02X} Std={std_chk:02X}", end="")
        if std_chk == chk_pkt:
            print(" [OK]")
        else:
            print(f" [MISMATCH! BaseDiff={(chk_pkt + s_sum) & 0xFF:02X}]")

if __name__ == "__main__":
    analyze_pcap("usbcap/create simple_macro dn-1 up-1 no delay bind to button 1.pcapng")
    print("\n" + "="*40 + "\n")
    analyze_pcap("usbcap/delete all existing macros from mouse memory.pcapng")
