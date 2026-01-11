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
    time.sleep(0.05)

def inject_replay():
    devs = vp.list_devices()
    if not devs: return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    print("Injecting Replay Data for M1...")
    
    # Init
    send_handshake(mouse)
    
    # Replay M1 Data (Page 3)
    # Copied from log. 
    # Offset 0: 0A 06 31 00 32 00 33 00 00 00 00 (Check 9D?)
    # Packet Checksums will be auto-calced by build_report 
    # so we just need chunks.
    
    chunks = [
        (0x00, bytes([0x06, 0x31, 0x00, 0x32, 0x00, 0x33, 0x00, 0x00, 0x00, 0x00])),
        (0x0A, bytes([0x00] * 10)),
        (0x14, bytes([0x00] * 10)),
        (0x1E, bytes([0x00, 0x12, 0x81, 0x1E, 0x00, 0x00, 0x7D, 0x41, 0x1E, 0x00])), # Count 12 at 1F
        (0x28, bytes([0xBB, 0x81, 0x1F, 0x00, 0x00, 0x7D, 0x41, 0x1F, 0x00, 0xD9])), # D9?? Data
        # ... Skip middle ...
        # Term at 78: 00 03 E8 ...
        (0x78, bytes([0x00, 0x03, 0xE8, 0x00, 0x00, 0x00]))
    ]
    
    # We should fill the gap to be safe? Replay sent all chunks.
    # Just send crucial ones: Header, Count, Term.
    
    page = 0x03
    reports = [vp.build_simple(0x04), vp.build_simple(0x03)]
    
    for off, data in chunks:
        reports.append(vp.build_macro_chunk(off, data, page))
        
    # Bind Packet (M1 -> Btn 1)
    # Offset 0x60. Type 06. Idx 00. Mode 03.
    # Checksum 48.
    bind_load = [0x00, 0x00, 0x60, 0x04, 0x06, 0x00, 0x03, 0x48, 0,0,0,0,0,0]
    # Checksum base 55? 51?
    # Manual load means we bypass build_macro_bind logic.
    # We rely on build_report to sign Byte 16.
    reports.append(vp.build_report(0x07, bind_load))
    
    reports.append(vp.build_simple(0x04))
    
    for r in reports:
        mouse.send(r)
        time.sleep(0.02)
        
    print("Injection Done.")

if __name__ == "__main__":
    inject_replay()
