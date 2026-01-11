from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import venus_protocol as vp
import time
import struct

def generate_macro_data(name, text):
    """Generates a macro buffer for typing the given text."""
    # Buffer structure:
    # 00: 0x0A (Type?)
    # 01: Name Len
    # 02-1F: Name (UTF-16LE)
    # 1F: Event Count (if Short name)
    # 20+: Events
    
    buf = bytearray(300)
    
    # Header
    buf[0] = 0x0A
    
    # Name
    name_bytes = name.encode('utf-16le')
    buf[1] = len(name_bytes)
    buf[2:2+len(name_bytes)] = name_bytes
    
    # Events
    events = []
    # Simple typing: KeyDown -> Delay -> KeyUp -> Delay
    # Just lowercase letters for simplicity
    for char in text:
        if char.isalpha() or char.isdigit():
            key = char.upper()
            if key in vp.HID_KEY_USAGE:
                code = vp.HID_KEY_USAGE[key]
                # Press
                events.append(vp.MacroEvent(keycode=code, is_down=True, delay_ms=10))
                # Release
                events.append(vp.MacroEvent(keycode=code, is_down=False, delay_ms=10))
                
    buf[0x1F] = len(events)
    
    offset = 0x20
    for evt in events:
        data = evt.to_bytes()
        buf[offset:offset+len(data)] = data
        offset += len(data)
        
    # Terminator (at offset)
    # [00] [03] [Inner] [00] [00] [00]
    term_offset = offset - 2 # Overwrite last delay bytes?
    if term_offset < 0x20: term_offset = 0x20
    
    # Return buffer and where the events end (event_offset)
    return buf, offset, term_offset

def test_12_macros():
    # Find device
    devs = vp.list_devices()
    if not devs:
        print("No Venus Pro device found.")
        return
        
    target = devs[0]
    print(f"Using device: {target.path}")
    
    mouse = vp.VenusDevice(target.path)
    mouse.open()
    
    try:
        # Loop for 12 macros
        for i in range(12):
            macro_index = i + 1 # 1-12
            button_index = i + 1 # 1-12
            
            macro_name = f"m{macro_index}"
            macro_text = f"m{macro_index}"
            
            print(f"--- Configure Macro {macro_index} ('{macro_text}') on Button {button_index} ---")
            
            # 1. Generate Data
            buf, event_end, term_off = generate_macro_data(macro_name, macro_text)
            
            # 2. Calculate Checksum
            # Slice: [0 : event_end]
            data_slice = buf[0:event_end]
            # Use Instance method as Unbound or create instance? 
            # We have 'mouse' instance.
            checksum = mouse.calculate_terminator_checksum(data_slice, macro_index=i) # 0-based index
            
            print(f"  Checksum for Index {i}: 0x{checksum:02X}")
            
            # 3. Upload Sequence
            # Start Page/Offset
            start_page, start_offset = vp.get_macro_slot_info(macro_index)
            
            reports = [vp.build_simple(0x04), vp.build_simple(0x03)] # Header
            
            # Chunks
            for boff in range(0, event_end, 10):
                chunk = bytes(buf[boff : boff+10])
                abs_addr = (start_page << 8) | start_offset + boff
                p = (abs_addr >> 8) & 0xFF
                o = abs_addr & 0xFF
                reports.append(vp.build_macro_chunk(o, chunk, p))
                
            # Terminator
            abs_term = (start_page << 8) | start_offset + term_off
            tp = (abs_term >> 8) & 0xFF
            to = abs_term & 0xFF
            term_payload = bytes([0x00, 0x03, checksum, 0x00, 0x00, 0x00])
            reports.append(vp.build_macro_chunk(to, term_payload, tp))
            
            # Bind to Button
            # Get Button Apply Offset (Profile 1)
            # Button 1 is 1. Button 13 is 13.
            # Buttons map 1->1, etc?
            # Need to get Button Key for index
            # Keys in BUTTON_PROFILES are "Button 1", "Button 2"...
            btn_key = f"Button {button_index}"
            if btn_key not in vp.BUTTON_PROFILES:
                 print(f"  Unknown button {btn_key}, skipping bind.")
                 continue
                 
            profile = vp.BUTTON_PROFILES[btn_key]
            apply_offset = profile.apply_offset
            
            # Bind Packet
            # Page 0 (Profile 1)
            # Index is 0-based (i)
            # Repeat = ONCE (0x03)
            bind_pkt = vp.build_macro_bind(apply_offset, macro_index=i, repeat_mode=vp.MACRO_REPEAT_ONCE, page=0x00)
            reports.append(bind_pkt)
            
            # Commit
            reports.append(vp.build_simple(0x04))
            
            # Send all
            for r in reports:
                mouse.send(r)
                time.sleep(0.02)
                
            print("  Uploaded and Bound.")
            time.sleep(0.1)
            
    finally:
        mouse.close()
        
if __name__ == "__main__":
    test_12_macros()
