from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import venus_protocol as vp
import time

def send_handshake(mouse):
    pkt = bytearray(17)
    pkt[0]=8; pkt[1]=3; pkt[16]=0x4A
    mouse.send(bytes(pkt))
    time.sleep(0.02)

def send_init_sequence(mouse):
    """Sends ONLY Handshake (Matches state when partial writes worked)."""
    # HS
    pkt = bytearray(17)
    pkt[0]=8; pkt[1]=3; pkt[16]=0x4A
    mouse.send(bytes(pkt))
    time.sleep(0.05)

def generate_macro_data(name):
    # Name "m1" -> UTF-16 "6D 00 31 00"
    name_utf16 = name.encode('utf-16le')
    length_byte = len(name_utf16) # 4
    
    # Header: [Len] [Name...]
    header = bytearray([length_byte]) + name_utf16
    
    # Events: KeyDn(1E), KeyUp(1E)
    count = 2
    events = bytearray()
    
    # Event 1: Key Down '1' (0x1E)
    events.extend([0x81, 0x1E, 0x00, 0x00, 0x10])
    
    # Event 2: Key Up '1' (0x1E)
    events.extend([0x41, 0x1E, 0x00, 0x00, 0x10])
    
    return header + bytearray([count]) + events

def test_macros():
    try:
        devs = vp.list_devices()
        if not devs:
            print("No device found.")
            return
            
        target_dev = devs[0]
        mouse = vp.VenusDevice(target_dev.path)
        print(f"Using device: {target_dev.path}")
        
        mouse.open()
        print("Initializing Device...")
        send_init_sequence(mouse)
        
        # 12 Buttons
        for i in range(12):
            # Map logical index 0-11 to physical macro slot index
            if hasattr(vp, 'SIDE_BUTTON_INDICES'):
                 macro_index = vp.SIDE_BUTTON_INDICES[i]
            else:
                 # Fallback if vp not updated yet (safety)
                 # 0-5, 8-9, 12-15
                 mapping = [0,1,2,3,4,5, 8,9, 12,13,14,15]
                 macro_index = mapping[i]
                 
            button_index = i + 1
            macro_name = f"m{button_index}"
            macro_data = generate_macro_data(macro_name)
            
            print(f"--- Configuring Macro {i} (Index {macro_index:02X}) ('{macro_name}') for Side Button {button_index} ---")
            
            # Get Page/Offset (using updated vp logic)
            page, offset = vp.get_macro_slot_info(macro_index)
            print(f"  Slot Target: Page 0x{page:02X} Offset 0x{offset:02X}")
            
            # Send Data Chunks
            chunk_size = 10
            total = len(macro_data)
            chunks = []
            
            for j in range(0, total, chunk_size):
                chunk = macro_data[j : j+chunk_size]
                pkt = vp.build_macro_chunk(offset + j, chunk, page)
                chunks.append(pkt)
            
            # Terminator
            term_off = offset + total
            term_pkt = vp.build_macro_terminator(term_off, page)
            chunks.append(term_pkt)
            
            # Send Writes with Handshakes
            for pkt in chunks:
                mouse.send(pkt)
                time.sleep(0.02)
                # HANDSHAKE (Confirmed by Replay Log Analysis)
                send_handshake(mouse)
            
            # Bind
            prof = vp.BUTTON_PROFILES[f"Button {button_index}"]
            bind_off = prof.apply_offset
            
            # Base 55 (Default)
            bind_pkt = vp.build_macro_bind(bind_off, macro_index, vp.MACRO_REPEAT_ONCE, 0x00)
            mouse.send(bind_pkt)
            time.sleep(0.02)
            send_handshake(mouse) # Handshake after Bind too? Replay showed it.

            # Cmd 04
            mouse.send(vp.build_simple(0x04))
            time.sleep(0.02)
            send_handshake(mouse)
            
            time.sleep(0.05) # Pause between buttons
            print("  Uploaded.")
            
        # 3. VERIFY: Read Back Macro 1 and Macro 7
        print("\n--- VERIFICATION: Reading Back Memory ---")
        time.sleep(1.0) # Wait for processing
        
        # Read Macro 1 (Index 0, Page 0x03, Offset 0x00)
        print("Reading Macro 1 (Page 0x03)...")
        data_m1 = mouse.read_flash(0x03, 0x00, 64) # Read 64 bytes
        if data_m1:
            print(f"M1 Data: {data_m1[:32].hex()} ...")
            # Expected Header for "m1": 04 6D 00 31 00 ...
            # Check for header match
            if data_m1[0] == 0x04 and data_m1[2] == 0x31:
                 print("  SUCCESS: M1 Header matches 'm1'.")
            else:
                 print("  FAILURE: M1 Data does not match expected 'm1'.")
        else:
            print("  READ ERROR: No data returned.")

        # Read Macro 7 (Index 8, Page 0x0F, Offset 0x00)
        print("Reading Macro 7 (Page 0x0F)...")
        data_m7 = mouse.read_flash(0x0F, 0x00, 64)
        if data_m7:
            print(f"M7 Data: {data_m7[:32].hex()} ...")
             # Expected Header for "m7": 04 6D 00 37 00 ...
            if data_m7[0] == 0x04 and data_m7[2] == 0x37:
                 print("  SUCCESS: M7 Header matches 'm7'.")
            else:
                 print("  FAILURE: M7 Data does not match expected 'm7'.")
        else:
            print("  READ ERROR: No data returned.")
            
    finally:
        mouse.close()

if __name__ == "__main__":
    test_macros()
