from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import venus_protocol as vp
import time

def generate_macro_no_header(name):
    """Generates simple macro 'name' without 0x0A header."""
    buf = bytearray(300)
    name_bytes = name.encode('utf-16le')
    # buf[0] = len
    buf[0] = len(name_bytes)
    buf[1:1+len(name_bytes)] = name_bytes
    
    events = []
    # Short typing
    for c in name:
        if c in vp.HID_KEY_USAGE:
            code = vp.HID_KEY_USAGE[c]
            events.append(vp.MacroEvent(code, True, 10))
            events.append(vp.MacroEvent(code, False, 10))
            
    buf[0x1F] = len(events)
    offset = 0x20
    for evt in events:
        d = evt.to_bytes()
        buf[offset:offset+len(d)] = d
        offset += len(d)
        
    return buf, offset

def calibrate():
    devs = vp.list_devices()
    if not devs: return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    # Test Pattern
    # Slot 1: K=4 (Test if Slot 1 is Index 1)
    # Slot 2: K=4 (Control: Worked before)
    # Slot 3: K=9 (Expected)
    # Slot 4: K=1 (Maybe Index 0?)
    # Slot 5: K=16 (Index 3?)
    # Slot 6: K=0 (Null)
    
    configs = [
        (1, 4),
        (2, 4),
        (3, 9),
        (4, 1),
        (5, 16),
        (6, 0),
        (7, 2), # OhShit fallback
        (8, 1), # Retry K=1
    ]
    
    try:
        for slot, k_val in configs:
            name = f"k{k_val}"
            print(f"--- Slot {slot}: Macro '{name}' Checksum K={k_val} ---")
            
            buf, event_end = generate_macro_no_header(name)
            
            # Calculate Sum
            s_sum = sum(buf[0:event_end]) & 0xFF
            count = buf[0x1F]
            inv_sum = (~s_sum) & 0xFF
            # Inner = ~Sum - Count + K
            inner = (inv_sum - count + k_val) & 0xFF
            
            print(f"  Sum: {s_sum:02X} Count: {count:02X} K: {k_val} -> Inner: {inner:02X}")
            
            # Terminator
            # Term Offset can be calculated
            term_off = event_end
            
            # Upload
            page, off = vp.get_macro_slot_info(slot)
            reports = [vp.build_simple(0x04), vp.build_simple(0x03)]
            
            # Data
            for i in range(0, event_end, 10):
                chunk = bytes(buf[i:i+10])
                abs_a = (page << 8) | off + i
                reports.append(vp.build_macro_chunk(abs_a & 0xFF, chunk, (abs_a >> 8) & 0xFF))
                
            # Terminator
            t_abs = (page << 8) | off + term_off
            t_pay = bytes([0x00, 0x03, inner, 0x00, 0x00, 0x00])
            reports.append(vp.build_macro_chunk(t_abs & 0xFF, t_pay, (t_abs >> 8) & 0xFF))
            
            # Bind (Profile 1)
            btn_key = f"Button {slot}"
            if btn_key in vp.BUTTON_PROFILES:
                bp = vp.BUTTON_PROFILES[btn_key]
                # Index is slot-1
                # Format: Index, Mode=3
                bind = vp.build_macro_bind(bp.apply_offset, slot-1, 0x03, 0x00)
                reports.append(bind)
                
            reports.append(vp.build_simple(0x04))
            
            for r in reports:
                mouse.send(r)
                time.sleep(0.015)
                
            print("  Done.")
            time.sleep(0.1)
            
    finally:
        mouse.close()

if __name__ == "__main__":
    calibrate()
