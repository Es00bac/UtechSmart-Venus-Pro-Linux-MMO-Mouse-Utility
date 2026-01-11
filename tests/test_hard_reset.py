from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import venus_protocol as vp
import time

def test_hard_reset():
    devs = vp.list_devices()
    if not devs:
        print("No device found.")
        return
        
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    try:
        print("Sending Hard Reset (Cmd 09)...")
        # 08 09 00... 44 (Checksum for empty payload)
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=9; pkt[16]=0x44
        mouse.send(bytes(pkt))
        time.sleep(1.0) # Wait for reboot
        
        print("Sending Handshake (Cmd 03)...")
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=3; pkt[16]=0x4A
        mouse.send(bytes(pkt))
        time.sleep(0.1)
        
        print("Reset Command Sent. Please test buttons 1-12.")
        print("Expectation: Factory Default (1, 2, 3... -, =).")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    test_hard_reset()
