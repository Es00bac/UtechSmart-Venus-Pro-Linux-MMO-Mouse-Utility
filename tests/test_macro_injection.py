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

def inject_macro():
    devs = vp.list_devices()
    if not devs: return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    try:
        print("Initializing (Reset)...")
        send_init(mouse)
        
        # Define Macro 1 Data
        # Name "m1" -> 04 6D 00 31 00
        # Events -> 1E dn/up
        macro_index = 0
        page = 0x03
        offset = 0x00
        
        name = "m1"
        name_utf16 = name.encode('utf-16le')
        header = bytearray([len(name_utf16)]) + name_utf16
        # Key 'a' = 0x04
        events = bytearray([0x81, 0x04, 0x00, 0x00, 0x10, 0x41, 0x04, 0x00, 0x00, 0x10])
        macro_data = header + bytearray([2]) + events # Count=2
        
        print(f"Writing Macro Data to Page {page:02X} Offset {offset:02X}...")
        
        # Chunk and Write
        chunk_size = 10
        total = len(macro_data)
        chunks = []
        for j in range(0, total, chunk_size):
            chunk = macro_data[j : j+chunk_size]
            # Use vp.build_macro_chunk logic but verified manually
            # Data Packet: 08 07 00 PAGE OFF LEN [DATA] [CHK]
            pkt = bytearray(17)
            pkt[0]=8; pkt[1]=7; pkt[3]=page; pkt[4]=offset+j; pkt[5]=0x0A
            
            # Payload
            # Pad chunk to 10
            padded = chunk.ljust(10, b'\x00')
            pkt[6:16] = padded
            
            # Checksum
            s = sum(pkt[:16])
            pkt[16] = (0x55 - s) & 0xFF
            
            chunks.append(pkt)
            
        # Terminator
        term_off = offset + total
        # Terminator Packet: 08 07 00 PAGE OFF 0A [FF]*10 [CHK]
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=7; pkt[3]=page; pkt[4]=term_off; pkt[5]=0x0A
        pkt[6:16] = b'\xFF' * 10
        s = sum(pkt[:16])
        # Correction Factor? (MacroIndex+1)^2 ?
        # Step 2043 logic: (~Sum - Count + (MacroIndex+1)**2)
        # Wait. build_terminator logic is complex.
        # Let's use vp.build_macro_terminator if we trust it.
        # Or just trust 0x55?
        # Step 2232 confirmed 0x55 for DATA.
        # Terminator is DATA? Yes.
        pkt[16] = (0x55 - s) & 0xFF
        chunks.append(pkt)
        
        for p in chunks:
            mouse.send(bytes(p))
            time.sleep(0.02)
            # Handshake? reset_to_default didn't use per-packet HS for bindings?
            # It just sent list.
            # But test_final meant per-packet HS.
            # Let's NO-HS first (like reset_to_default).
            
        # Bind Button 1
        print("Binding Button 1 to Macro...")
        prof = vp.BUTTON_PROFILES["Button 1"]
        bind_off = prof.apply_offset # 0x60
        
        # Macro Bind Packet (Type 06)
        # 08 07 00 00 OFF 0A [Type06] [Idx] [Rpt] [00] [FF]...
        # Replay Captured Bind Packets (Exact Hex)
        # Packet 1: 0807000060040600014e00000030000000 (17 bytes)
        # Packet 2: 08070000600406000100104e0000000000 (17 bytes)
        
        raw_pkt1 = bytes.fromhex("0807000060040600014e00000030000000")
        print(f"Sending Raw Bind 1: {raw_pkt1.hex()}")
        mouse.send(raw_pkt1)
        time.sleep(0.02)
        
        raw_pkt2 = bytes.fromhex("08070000600406000100104e0000000000")
        print(f"Sending Raw Bind 2: {raw_pkt2.hex()}")
        mouse.send(raw_pkt2)
        time.sleep(0.02)
        
        # Commit
        print("Committing...")
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=4; pkt[16]=0x51
        mouse.send(bytes(pkt))
        
        print("Done. Testing Button 1...")
        time.sleep(0.5)
        d = mouse.read_flash(0x03, 0x00, 64)
        if d: print(d[:32].hex())
        else: print("Read Error")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    inject_macro()
