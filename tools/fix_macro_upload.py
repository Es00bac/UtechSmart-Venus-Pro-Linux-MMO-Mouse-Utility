#!/usr/bin/env python3
"""
Fix Macro Upload - Corrects the data structure padding and checksum calculation.
Based on test_final_solution.py but with proper 31-byte header padding.
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import venus_protocol as vp
import time
import struct

def send_handshake(mouse):
    pkt = bytearray(17)
    pkt[0]=8; pkt[1]=3; pkt[16]=0x4A
    mouse.send(bytes(pkt))
    time.sleep(0.02)

def send_init_sequence(mouse):
    """Sends ONLY Handshake (Matches state when partial writes worked)."""
    # HS - Is this needed? Trace didn't show it explicitly at start.
    # Trace started with Cmd 04 (Output Report).
    pass 

def generate_macro_data_fixed(name, events_list=None):
    """
    Generates correctly padded macro data.
    Header: [Len] [Name (UTF-16LE)... padded to 30 bytes]
    Total Header size: 31 bytes.
    Byte 0x1F: Event Count.
    Byte 0x20...: Events (5 bytes each).
    """
    # 1. Name Encoding (UTF-16LE)
    name_utf16 = name.encode('utf-16le')
    length_byte = len(name_utf16) # Should be even
    
    # 2. Build Header Padded to 31 bytes (Indices 0x00 to 0x1E)
    # [Len] + [Name...] + [00...]
    # We need exactly 31 bytes before the count byte.
    header = bytearray([length_byte]) + name_utf16
    padding_needed = 31 - len(header)
    if padding_needed < 0:
        raise ValueError(f"Macro name '{name}' is too long!")
    header += bytes(padding_needed)
    
    # 3. Events
    if events_list is None:
        # Default: Type "1"
        # Key '1' is 0x1E
        # Event format: [Status] [Key] 00 [DelayHi] [DelayLo]
        # Status: 0x81 (Dn), 0x41 (Up)
        events = bytearray()
        # Key Down '1', Delay 16ms (0x10)
        events.extend([0x81, 0x1E, 0x00, 0x00, 0x10])
        # Key Up '1', Delay 16ms
        events.extend([0x41, 0x1E, 0x00, 0x00, 0x10])
        count = 2
    else:
        events = events_list
        count = len(events) // 5

    # 4. Combine: Header + Count + Events
    # Count is at index 0x1F
    full_data = header + bytearray([count]) + events
    
    return full_data, count

# Helper to send Output Report (ID 0x09) instead of Feature Report
def send_output_report(mouse, payload_16_bytes):
    """Sends 17-byte packet: [09] [Payload...] via Interrupt Out (write)."""
    # Construct 17-byte packet with Report ID 0x09
    pkt = bytearray([0x09]) + payload_16_bytes
    
    # Calculate checksum for the packet itself
    # Checksum formula: 0x55 - Sum(0..15)
    # Payload 0..15 corresponds to Pkt[0]..Pkt[15]
    # Pkt[0] is 0x09.
    
    s_sum = sum(pkt[:-1]) & 0xFF
    checksum = (0x55 - s_sum) & 0xFF
    pkt[-1] = checksum
    
    # Use HID write (Interrupt Out)
    mouse._dev.write(bytes(pkt))

def send_feature_report_as_09(mouse, feature_pkt):
    """Takes a standard 'feature packet' (ID 08...) and converts to ID 09 write."""
    # Convert 08... to 09... and fix checksum
    # Feature Pkt: 08 [15 bytes] [CHK]
    # Output Pkt: 09 [15 bytes] [NEW_CHK]
    
    data = bytearray(feature_pkt)
    data[0] = 0x09
    
    # Recalculate checksum (last byte)
    s_sum = sum(data[:-1]) & 0xFF
    chk = (0x55 - s_sum) & 0xFF
    data[-1] = chk
    
    mouse._dev.write(bytes(data))


def calculate_checksum_inner(data, count, macro_index):
    """
    Calculates the 'Inner Byte' checksum for the macro terminator.
    Formula: Checksum = (~Sum - Count + Correction) & 0xFF
    Correction = (MacroIndex + 1)^2
    
    Wait. The hypothesis 0x68-Sum was wrong because verified packet checksums used 0x55.
    But this is for the INNER checksum (inside payload).
    Old formula: (~Sum - Count + Correction).
    Let's stick to the 0x68-based formula if the user's test works?
    Wait, user said PREVIOUS attempt (0x68 base) FAILED. "button 1 does nothing still".
    So 0x68 was WRONG for the Inner Checksum too, or Transport was wrong.
    
    Re-evaluating Inner Checksum logic from Trace:
    Macro Data Sum = 0x19. Terminator Checksum = 0x4F.
    0x55 - 0x19 = 0x3C != 0x4F.
    ~0x19 = E6. E6 - 2 + 1 = E5 != 4F.
    
    What about just Sum?
    Sum 0x19. Target 0x4F. Diff 0x36 (54).
    Is 54 constant?
    
    Let's proceed with the hypothesis that TRANSPORT was the main failure, 
    and maybe the checksum logic IS the standard one?
    Let's revert to standard one or try the Diff 36?
    Actually, 0x4F = 79.
    79 = 0x55 + 10 (Len 10?) - Sum?
    Let's assume the previous FAILED test was due to Transport (ID 08 vs 09).
    BUT, if the mouse ignores ID 08, then it never WRITES the macro.
    So the checksum doesn't matter yet.
    I should fix Transport AND try the most likely checksum.
    The most likely checksum is matching the capture. 0x68 Base matched the capture.
    So I will KEEP 0x68 Base, but Fix Transport.
    """
    s_sum = sum(data) & 0xFF
    base = 0x68 
    final_chk = (base - s_sum) & 0xFF
    return final_chk

def test_fix_upload():
    try:
        devs = vp.list_devices()
        print(f"Found {len(devs)} devices:")
        for d in devs:
             print(f"  {d.path} | VID:PID {d.vendor_id:04X}:{d.product_id:04X} | Iface: {d.interface_number}")
             
        if not devs:
            print("No device found.")
            return
            
        # Target Interface 1 explicitly
        target_dev = None
        for d in devs:
            if d.interface_number == 1:
                target_dev = d
                break
        
        if not target_dev:
             print("Interface 1 not found! Falling back to first device...")
             target_dev = devs[0]
             
        mouse = vp.VenusDevice(target_dev.path)
        print(f"Using device: {target_dev.path} (Interface {target_dev.interface_number})")
        
        mouse.open()
        print("Initializing Device...")
        
        # Init Sequence: Cmd 04 (09 04...)
        send_feature_report_as_09(mouse, vp.build_simple(0x04))
        time.sleep(0.05)
        
        test_buttons = [0, 6] 
        
        indices_to_test = []
        indices_to_test.append((1, 0)) # Button 1
        indices_to_test.append((7, 8)) # Button 7
        
        for btn_num, macro_index in indices_to_test:
            macro_name = f"m{btn_num}"
            print(f"\n--- Configuring Button {btn_num} (Macro Index {macro_index}) ('{macro_name}') ---")
            
            # 1. Macro Data
            macro_data, count = generate_macro_data_fixed(macro_name)
            
            # 2. Chunks
            page, offset = vp.get_macro_slot_info(macro_index)
            
            chunk_size = 10
            total = len(macro_data)
            chunks = []
            for j in range(0, total, chunk_size):
                chunk = macro_data[j : j+chunk_size]
                pkt = vp.build_macro_chunk(offset + j, chunk, page)
                chunks.append(pkt)
            
            # 3. Checksum
            checksum = calculate_checksum_inner(macro_data, count, macro_index)
            print(f"  Calculated Tail Checksum (Inner): 0x{checksum:02X}")
            
            # 4. Terminator
            term_off = offset + total
            term_pkt = vp.build_macro_terminator(term_off, checksum, page)
            chunks.append(term_pkt)
            
            # 5. Send Writes (Output Report ID 09)
            print("  Sending Sequence (Output Reports ID 09)...")
            
            for pkt in chunks:
                send_feature_report_as_09(mouse, pkt)
                time.sleep(0.005)
                
            # 6. Bind to Button
            prof = vp.BUTTON_PROFILES[f"Button {btn_num}"]
            bind_off = prof.apply_offset
            bind_pkt = vp.build_macro_bind(bind_off, macro_index, vp.MACRO_REPEAT_ONCE, 0x00)
            
            send_feature_report_as_09(mouse, bind_pkt)
            time.sleep(0.01)
            
            # Commit
            cmd4 = vp.build_simple(0x04)
            send_feature_report_as_09(mouse, cmd4)
            time.sleep(0.05)
            
            print("  Done.")
            time.sleep(0.1)
            
        print("\nSkipping Read Verification. Please Test Physically.")
            
    finally:
        mouse.close()

if __name__ == "__main__":
    test_fix_upload()
