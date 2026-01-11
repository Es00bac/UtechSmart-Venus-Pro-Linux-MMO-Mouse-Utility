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
    pkt = bytearray(17)
    pkt[0]=8; pkt[1]=3; pkt[16]=0x4A
    mouse.send(bytes(pkt))
    time.sleep(0.05)
    # Reset
    pkt = bytearray(17)
    pkt[0]=8; pkt[1]=9; pkt[16]=0x44
    mouse.send(bytes(pkt))
    time.sleep(0.05)
    # HS
    pkt = bytearray(17)
    pkt[0]=8; pkt[1]=3; pkt[16]=0x4A
    mouse.send(bytes(pkt))
    time.sleep(0.05)

def reset_mouse():
    devs = vp.list_devices()
    if not devs: return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    try:
        print("Initializing...")
        send_init(mouse)
        
        # Keys 1-9, 0, -, =
        keys = [
            0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2D, 0x2E
        ]
        
        for i in range(12):
            btn = i + 1
            key = keys[i]
            print(f"Binding Button {btn} to Key {key:02X}...")
            
            # Get Profile
            prof = vp.BUTTON_PROFILES[f"Button {btn}"]
            # Offset
            apply_off = prof.apply_offset
            # Pages?
            # Key Bind: 08 07 00 PAGE OFF LEN [TYPE=05] ...
            # Wait. Protocol for Key Bind is CMD 07 Write.
            # Page?
            # Standard Keys bind to Page 0? Or Page 1/2?
            # venus_protocol BUTTON_PROFILES has code_hi/lo.
            # e.g. Button 1: Hi 0x01, Lo 0x00.
            # Is this write target?
            # Yes. build_key_binding(code_hi, code_lo, key)
            
            reports = []
            
            # 1. Write Key Definition to Page 1/2
            # build_key_binding returns a LIST of reports
            kb_pkt = vp.build_key_binding(prof.code_hi, prof.code_lo, key)
            reports.extend(kb_pkt)
            
            # 2. Bind Button to Keyboard Mode (Entry in Page 0)
            # Offset: apply_off.
            # Payload: 00 PAGE OFFSET LEN [05] [00] [00] [55]...
            # This is "build_keyboard_bind"? 
            # Existing code: build_simple_key_bind doesnt exist?
            # Looking at build_key_binding... it constructs the definition.
            # How to link Button -> Definition?
            # Ah. The BUTTON PROFILE `apply_offset` 0x60... points to Type.
            # If Type 05 (Keyboard), it looks at Page 1/2 slot.
            # Packet: [00, 00, apply_off, 04, 05, 00, 00, 50, ...]
            # 50 is Checksum? 55 - 05 = 50. Yes.
            
            # Manual Bind Packet for Keyboard
            bind_payload = [0x00, 0x00, apply_off, 0x04, 0x05, 0x00, 0x00, 0x50, 0,0,0,0,0,0]
            bind_pkt = vp.build_report(0x07, bind_payload)
            reports.append(bind_pkt)
            
            # Commit
            reports.append(vp.build_simple(0x04))
            
            for r in reports:
                mouse.send(r)
                time.sleep(0.02)
                
        print("Reset Complete.")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    reset_mouse()
