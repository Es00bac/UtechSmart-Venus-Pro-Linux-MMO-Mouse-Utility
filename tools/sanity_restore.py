from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import venus_protocol as vp
import time

def generate_simple_macro(name):
    """No 0A header. Just [Len] [Bytes...]."""
    buf = bytearray(300)
    name_bytes = name.encode('utf-16le')
    buf[0] = len(name_bytes)
    buf[1:1+len(name_bytes)] = name_bytes
    
    events = []
    # Key '1' for m1, '2' for m2...
    char = name[-1] # "1" from "test1"
    if char in vp.HID_KEY_USAGE:
        code = vp.HID_KEY_USAGE[char]
        events.append(vp.MacroEvent(code, True, 10))
        events.append(vp.MacroEvent(code, False, 10))
    
    buf[0x1F] = len(events)
    offset = 0x20
    for evt in events:
        d = evt.to_bytes()
        buf[offset:offset+len(d)] = d
        offset += len(d)
        
    return buf, offset


def send_handshake(mouse):
    # 08 03 ...
    pkt = bytearray(17)
    pkt[0] = 0x08
    pkt[1] = 0x03
    pkt[16] = 0x4A # Checksum? 03 -> 4A? Fixed?
    # Log: 08 03 ... 4A.
    # If 0x55 - 3 = 52. 4A is close.
    # Maybe hardcoded.
    mouse.send(bytes(pkt))
    time.sleep(0.05)

def send_reset(mouse):
    # 08 09 ... 44
    pkt = bytearray(17)
    pkt[0] = 0x08
    pkt[1] = 0x09
    pkt[16] = 0x44 
    mouse.send(bytes(pkt))
    time.sleep(0.05)

def run_sanity():
    devs = vp.list_devices()
    if not devs: return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    # Init Sequence from Log
    print("Sending Init Sequence...")
    send_handshake(mouse)
    # Read response? (Not implemented in simple script, blindly sending)
    send_reset(mouse)
    send_handshake(mouse)
    print("Init Done.")
    
    # Test Cases
    # Slot 1: K=1 (Theoretical Match)
    # Slot 2: K=4 (Proven Work)
    # Slot 3: K=4 (Test if K=4 applies everywhere?)
    
    cases = [
        (1, 1, "s1_k1"),
        (2, 4, "s2_k4"),
        (3, 4, "s3_k4"),
        (4, 9, "s4_k9"),
        (5, 1, "s5_k1"), # Retest K=1 on other slot
    ]
    
    try:
        for slot, k_val, name in cases:
            print(f"--- Uploading {name} to Slot {slot} (K={k_val}) ---")
            buf, end_off = generate_simple_macro(name)
            
            # Checksum
            s_sum = sum(buf[0:end_off]) & 0xFF
            count = buf[0x1F]
            inner = (~s_sum - count + k_val) & 0xFF
            print(f"  Sum:{s_sum:02X} K:{k_val} -> Inner:{inner:02X}")
            
            # Packets
            page, off = vp.get_macro_slot_info(slot)
            reports = [vp.build_simple(0x04), vp.build_simple(0x03)]
            
            for i in range(0, end_off, 10):
                chunk = bytes(buf[i:i+10])
                addr = (page << 8) | off + i
                reports.append(vp.build_macro_chunk(addr & 0xFF, chunk, (addr >> 8) & 0xFF))
                
            # Term
            t_addr = (page << 8) | off + end_off
            t_pay = bytes([0x00, 0x03, inner, 0x00, 0x00, 0x00])
            reports.append(vp.build_macro_chunk(t_addr & 0xFF, t_pay, (t_addr >> 8) & 0xFF))
            
            # Bind
            bp = vp.BUTTON_PROFILES[f"Button {slot}"]
            reports.append(vp.build_macro_bind(bp.apply_offset, slot-1, 0x03, 0x00))
            
            reports.append(vp.build_simple(0x04))
            
            for r in reports:
                mouse.send(r)
                time.sleep(0.05) # SLOW DOWN!
                
            print("  Done.")
            time.sleep(0.5)
            
    finally:
        mouse.close()

if __name__ == "__main__":
    run_sanity()
