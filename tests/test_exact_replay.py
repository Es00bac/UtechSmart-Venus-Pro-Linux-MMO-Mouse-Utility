#!/usr/bin/env python3
"""
Test Exact Replay - Replays the exact packets from the "simple_macro" capture.
Goal: Verify Transport independent of Data Generation logic.

Capture Sequence:
1. Init/Commit-Start: 09 04 00 00 00 02 0a 01 [CHK]
2. Macro Data 1: 09 07 00 03 00 0a 18 73 00 69 00 6d 00 70 00 6c [FB]
3. Macro Data 2: 09 07 00 03 0a 0a 00 65 00 5f 00 6d 00 61 00 63 [39]
4. Macro Data 3: 09 07 00 03 14 0a 00 72 00 6f 00 00 00 00 00 00 [43]
5. Macro Data 4: 09 07 00 03 1e 0a 00 02 81 1e 00 00 03 41 1e 00 [17]
6. Macro Data 5: 09 07 00 03 28 06 00 03 4f 00 00 00 [C2]
7. Bind: 09 07 00 00 60 04 06 00 01 4e [8C]
8. Commit-End: 09 04 00 00 00 02 0a 01 [CHK]
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

# Packet Hex Strings (From Trace)
# Note: Checksums included in string, but we need to supply them or verify.
# To be safe, I'll send the bytes EXACTLY as captured.
PACKETS = [
    # 1. Init (Cmd 04) - Capture had repeating, taking one.
    # Raw: 0904000000020a0100000000000000003b
    "0904000000020a0100000000000000003b",
    
    # 2. Macro Data Chunks
    "09070003000a18730069006d0070006cfb",
    "090700030a0a0065005f006d0061006339",
    "09070003140a0072006f00000000000043",
    "090700031e0a0002811e000003411e0017",
    # Pkt 5 length 6? Padded? Capture was 0907...C2 with zero padding
    # Raw: 09070003280600034f00000000000000c2 (17 bytes)
    "09070003280600034f00000000000000c2",
    
    # 3. Bind
    # Raw: 0907000060040600014e0000000000008c
    "0907000060040600014e0000000000008c",
    
    # 4. Commit (Cmd 04 again)
    "0904000000020a0100000000000000003b"
]

def send_raw_packet(mouse, hex_str):
    data = bytes.fromhex(hex_str)
    # Ensure 17 bytes?
    if len(data) < 17:
        pad = 17 - len(data)
        data += bytes(pad)
        
    print(f"Sending: {data.hex(' ')}")
    mouse._dev.write(data)

def test_exact_replay():
    devs = vp.list_devices()
    target_dev = None
    for d in devs:
        if d.interface_number == 1:
            target_dev = d
            break
    if not target_dev and devs: target_dev = devs[0]
    
    if not target_dev:
        print("No device.")
        return

    print(f"Using {target_dev.path} (Iface {target_dev.interface_number})")
    mouse = vp.VenusDevice(target_dev.path)
    mouse.open()
    
    try:
        print("Replaying exact capture sequence...")
        
        # 1. Packet Interval? Capture was fast. 5-10ms.
        for i, hex_pkt in enumerate(PACKETS):
            send_raw_packet(mouse, hex_pkt)
            time.sleep(0.01)
            
        print("Done. Please test Side Button 1 (Should type '1').")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    test_exact_replay()
