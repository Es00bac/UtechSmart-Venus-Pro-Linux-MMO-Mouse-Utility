from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import venus_protocol as vp
import time

def send_init(mouse):
    # HS
    mouse.send(bytes([8,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x4A]))
    time.sleep(0.05)
    # Reset
    mouse.send(bytes([8,9,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x44]))
    time.sleep(1.0)
    # HS
    mouse.send(bytes([8,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x4A]))
    time.sleep(0.05)

def inject_key_bind():
    devs = vp.list_devices()
    if not devs: return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    try:
        print("Initializing (Reset)...")
        send_init(mouse)
        
        # 1. Write Key Definition 'a' (0x04)
        # Using build_key_binding logic manually
        # Simple Binding: [Count=2] [81 04 00] [41 04 00] [Guard]
        # Guard: 91 - (4*2) = 89 (0x59)
        # Type 07 Len 04
        # Page 01 Offset 00 (Button 1 Slot)
        
        page = 0x01
        offset = 0x00
        hid_key = 0x04
        guard = (0x91 - (hid_key*2)) & 0xFF
        
        # Payload (8 bytes)
        # 02 81 04 00 41 04 00 89
        payload = [0x02, 0x81, hid_key, 0x00, 0x41, hid_key, 0x00, guard]
        
        # Pad to 10 bytes? build_key_binding loops chunks of 10.
        # Yes.
        chunk = bytearray(payload).ljust(10, b'\x00')
        
        # Packet
        # 08 07 00 01 00 0A ...
        # Wait. build_key_binding uses 0x0A (10) for data chunk length?
        # Step 2276 view code says:
        # "len = min(len(payload), 14)".
        # "Chunk size 10". "current_len = len(chunk)".
        # "pkt_payload = ... current_len ...".
        # So writes ARE Len 0A for Key Defs too.
        
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=7; pkt[3]=page; pkt[4]=offset; pkt[5]=0x0A
        pkt[6:16] = chunk
        s = sum(pkt[:16])
        pkt[16] = (0x55 - s) & 0xFF
        
        print("Writing Key Def...")
        mouse.send(bytes(pkt))
        time.sleep(0.02)
        
        # 2. Bind Button 1 to Keyboard Mode (Type 05)
        # Offset 0x60
        # Payload: 00 00 60 04 05 00 00 50
        # Wait. 04 is length?
        # reset_to_default used: [00, 00, apply_off, 04, 05, 00, 00, 50]
        # Packet: 08 07 00 00 OFF 04 ...
        
        print("Binding Button 1 to 'a'...")
        bind_pkt = bytearray(17)
        pkt[0]=8; pkt[1]=7; pkt[4]=0x60; pkt[5]=0x04
        pkt[6]=0x05 # Type 05
        # Padding 00
        # Checksum
        # 08 07 60 04 05 = 78 (0x4E)? + 50 (80) = CE.
        # 55 - 78 = DE? (negative).
        # Wait. reset_to_default used Base 55.
        s = sum(pkt[:16])
        pkt[16] = (0x55 - s) & 0xFF
        
        mouse.send(bytes(pkt))
        time.sleep(0.02)
        
        # Commit
        print("Committing...")
        mouse.send(bytes([8,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x51]))
        
        print("Done. Please test Button 1 (Should type 'a').")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    inject_key_bind()
