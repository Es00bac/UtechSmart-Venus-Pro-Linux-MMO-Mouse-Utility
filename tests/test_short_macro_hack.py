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

def inject_short_macro():
    devs = vp.list_devices()
    if not devs: return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    try:
        print("Initializing (Reset)...")
        send_init(mouse)
        
        # Construct "Trojan Horse" Payload for Page 01 (Key Def)
        # Standard Key: [Count=2] [81 Key 00] [41 Key 00] [Gurad]
        # Trojan: "ab" -> [Count=4] [81 04 00] [41 04 00] [81 05 00] [41 05 00] [Guard]
        
        # 'a' = 0x04. 'b' = 0x05.
        events = [
            0x81, 0x04, 0x00, # Dn a
            0x41, 0x04, 0x00, # Up a
            0x81, 0x05, 0x00, # Dn b
            0x41, 0x05, 0x00  # Up b
        ]
        count = 4
        
        # Guard Calculation (Standard formula: 91 - Key*2)
        # But here we have multiple keys.
        # Step 2276 notes: "Guard = SimpleGuard + Offset".
        # Let's try 0x00 Guard first? Or calc based on last key (0x05)?
        # 91 - 10 = 81 (0x51).
        # Plus offset for stream length?
        # Let's guess standard guard 0x51.
        guard = 0x51 
        
        payload = [count] + events + [guard]
        # Len = 1 + 12 + 1 = 14 bytes.
        # Fits in 2 packets of 10.
        # Packet 1: 10 bytes. Packet 2: 4 bytes.
        
        chunks = []
        chunk_size = 10
        total = len(payload)
        
        # Page 01, Offset 00 (Button 1)
        page = 0x01
        offset = 0x00
        
        print(f"Writing Sequence 'ab' to Page 01 Offset 00...")
        
        for i in range(0, total, chunk_size):
            chunk = payload[i : i+chunk_size]
            current_len = len(chunk)
            
            # Pad to 10 bytes?
            # Cmd 07 packets usually have Len in Byte 5.
            # And Payload at 6.
            # If standard writes use Len 0A.
            chunk_bytes = bytearray(chunk).ljust(10, b'\x00')
            
            pkt = bytearray(17)
            pkt[0]=8; pkt[1]=7; pkt[3]=page; pkt[4]=offset+i; pkt[5]=0x0A
            pkt[6:16] = chunk_bytes
            s = sum(pkt[:16])
            pkt[16] = (0x55 - s) & 0xFF
            
            chunks.append(pkt)
            
        for p in chunks:
            mouse.send(bytes(p))
            time.sleep(0.02)
            
        # Bind Button 1 to Key (Type 05)
        # Offset 0x60
        print("Binding Button 1 (Type 05)...")
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=7; pkt[4]=0x60; pkt[5]=0x04
        pkt[6]=0x05 # Type 05
        # Payload 00 Padding
        # Offset to Page 01 slot is implicit in Type 05?
        # reset_to_default passed "00 00 apply_off 04 05 ...".
        # apply_off = 0x60.
        # So yes, implicit.
        
        # Checksum (Subtractive 55)
        s = sum(pkt[:16])
        pkt[16] = (0x55 - s) & 0xFF
        
        mouse.send(bytes(pkt))
        time.sleep(0.02)
        
        # Commit
        print("Committing...")
        mouse.send(bytes([8,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x51]))
        
        print("Done. Please test Button 1 (Should type 'ab').")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    inject_short_macro()
