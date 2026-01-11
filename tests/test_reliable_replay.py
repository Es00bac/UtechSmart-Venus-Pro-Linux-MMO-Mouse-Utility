#!/usr/bin/env python3
"""
Test Reliable Replay - Replays the "simple_macro" capture using correct transport.
1. Sends Feature Report (ID 0x08).
2. Waits for Input Report (ID 0x09) as acknowledgment.
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import sys
import time
import venus_protocol as vp

# Packet bytes (including 0x08 ID and checksum)
# These are EXACTLY from the working Windows trace "simple_macro"
SEQUENCE = [
    # Frame 895: Cmd 04 (Commit Start)
    "0804000000000000000000000000000049",
    # Frame 3159: Cmd 03 (Handshake)
    "080300000000000000000000000000004a",
    # Frame 3527...: Macro Data (Page 03)
    "08070003000a18730069006d0070006cfc",
    "080700030a0a0065005f006d006100633a",
    "08070003140a0072006f00000000000044",
    "080700031e0a0002811e000003411e0018",
    "08070003280600034f00000000000000c3",
    # Frame 3547: Bind Macro 0 to Button 1
    "0807000060040600014e0000000000008d",
    # Frame 3719: Cmd 04 (Commit End)
    "0804000000000000000000000000000049"
]

def send_and_wait(mouse, hex_cmd):
    cmd_data = bytes.fromhex(hex_cmd)
    
    print(f"OUT: {cmd_data.hex(' ')}")
    
    # Send Feature Report
    # Note: hidapi.send_feature_report takes Report ID as first byte of buffer?
    # Actually, for send_feature_report, the first byte MUST be the Report ID.
    res = mouse._dev.send_feature_report(cmd_data)
    if res < 0:
        print(f"  ERROR: Send failed ({res})")
        return False
        
    # Wait for Input Report (ID 0x09)
    # hid_read reads from the interrupt endpoint.
    start = time.time()
    while time.time() - start < 0.5: # 500ms timeout
        ack = mouse._dev.read(17, timeout_ms=100)
        if ack:
            if ack[0] == 0x09:
                # Match Cmd and Page/Offset?
                # Usually byte 1 is Cmd, 3 is Page, 4 is Off
                print(f"IN : {bytes(ack).hex(' ')}")
                if ack[1] == cmd_data[1]:
                    # Match success
                    return True
                else:
                    print(f"  Warning: Cmd mismatch in ack (Exp {cmd_data[1]:02X}, Got {ack[1]:02X})")
                    return True # Still an ack
            else:
                print(f"  Ignore non-0x09 packet: {bytes(ack).hex(' ')}")
    
    print("  TIMEOUT: No acknowledgment received.")
    return False

def test_reliable_replay():
    devs = vp.list_devices()
    target_dev = None
    for d in devs:
        if d.interface_number == 1:
            target_dev = d
            break
            
    if not target_dev:
        print("Interface 1 not found.")
        return

    print(f"Connecting to {target_dev.path} (Iface {target_dev.interface_number})")
    mouse = vp.VenusDevice(target_dev.path)
    mouse.open()
    
    try:
        print("Replaying sequence with Acknowledgment logic...")
        # Clear input buffer first
        mouse._dev.read(64, timeout_ms=10)
        
        for hex_pkt in SEQUENCE:
            if not send_and_wait(mouse, hex_pkt):
                print("ABORTING due to failure.")
                break
            time.sleep(0.01) # Small gap
            
        print("\nDone. Please test Side Button 1 (Should type '1').")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    test_reliable_replay()
