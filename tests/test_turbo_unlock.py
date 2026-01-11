from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import venus_protocol as vp
import time
import threading

def spam_keep_alive(mouse, stop_event):
    # Packet 132: 08 00...
    pkt = bytes([0x08, 0x00, 0x01, 0x03, 0x00, 0x01, 0x00, 0x00,
                 0x02, 0x00, 0x00, 0x00, 0x00, 0x03, 0x1B, 0x00, 0x60])
    while not stop_event.is_set():
        try:
            mouse.send(pkt)
            time.sleep(0.002) # 2ms -> 500Hz
        except:
            pass

def turbo_unlock_test():
    devs = vp.list_devices()
    if not devs: return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    stop_spam = threading.Event()
    spammer = threading.Thread(target=spam_keep_alive, args=(mouse, stop_spam))
    
    try:
        print("Starting 500Hz Keep-Alive Spam...")
        spammer.start()
        time.sleep(0.1)
        
        # 1. Soft Reset / Handshake
        print("Sending Soft Reset...")
        mouse.send(bytes([0x08, 0x00, 0x01, 0x03, 0x00, 0x01, 0x00, 0x00,
                          0x02, 0x00, 0x00, 0x00, 0x00, 0x03, 0x1B, 0x00, 0x60]))
        # 2. Cmd 4D
        print("Sending Cmd 4D...")
        pkt1 = bytes([0x08, 0x4D, 0x05, 0x50, 0x00, 0x55, 0x00, 0x55, 
                      0x00, 0x55, 0x91, 0x1B, 0x00, 0x60, 0xB5, 0x3E, 0x8E])
        mouse.send(pkt1)
        
        print("Waiting/Draining (with Spam)...")
        # Drain for 2 seconds
        start = time.time()
        while time.time() - start < 2.0:
            mouse._dev.read(64, timeout_ms=5)
            
        # 3. Cmd 01
        print("Sending Cmd 01...")
        pkt2 = bytes([0x08, 0x01, 0x46, 0x06, 0x09, 0xF5, 0x1B, 0x00, 
                      0x60, 0xB5, 0x3E, 0x8E, 0x86, 0x84, 0xFF, 0xFF, 0x00])
        mouse.send(pkt2)
        
        # Drain 1s
        start = time.time()
        while time.time() - start < 1.0:
            mouse._dev.read(64, timeout_ms=5)
            
        print("Unlock Sequence Done. Stopping Spam.")
        stop_spam.set()
        spammer.join()
        
        # Now Write Macro
        # Handshake
        print("Sending Handshake...")
        mouse.send(bytes([0x08, 0x03, 0,0,0,0,0,0,0,0,0,0,0,0,0,0, 0x4A]))
        time.sleep(0.05)
        
        # Data M1
        print("Writing Macro Data (Page 3)...")
        # Header (m1) + Events (1)
        # 04 6D 00 31 00 ...
        # Same as test_macro_injection logic
        
        macro_index = 0
        page = 0x03
        offset = 0x00
        
        name = "m1"
        name_utf16 = name.encode('utf-16le')
        header = bytearray([len(name_utf16)]) + name_utf16
        events = bytearray([0x81, 0x1E, 0x00, 0x00, 0x10, 0x41, 0x1E, 0x00, 0x00, 0x10])
        macro_data = header + bytearray([2]) + events # Count=2
        
        # Write
        chunk = macro_data[:10]
        chunk = chunk.ljust(10, b'\x00')
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=7; pkt[3]=page; pkt[4]=offset; pkt[5]=0x0A
        pkt[6:16] = chunk
        s = sum(pkt[:16])
        pkt[16] = (0x55 - s) & 0xFF
        mouse.send(bytes(pkt))
        time.sleep(0.02)
        
        # Terminator
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=7; pkt[3]=page; pkt[4]=offset+len(macro_data); pkt[5]=0x0A
        pkt[6:16] = b'\xFF' * 10
        s = sum(pkt[:16])
        pkt[16] = (0x55 - s) & 0xFF
        mouse.send(bytes(pkt))
        time.sleep(0.02)
        
        # Bind
        print("Binding...")
        prof = vp.BUTTON_PROFILES["Button 1"]
        bind_off = prof.apply_offset
        pkt = bytearray(17)
        pkt[0]=8; pkt[1]=7; pkt[4]=bind_off; pkt[5]=0x0A
        pkt[6]=0x06; pkt[7]=0x00; pkt[8]=0x01
        pkt[10:16] = b'\x00' * 6
        s = sum(pkt[:16])
        pkt[16] = (0x55 - s) & 0xFF
        mouse.send(bytes(pkt))
        time.sleep(0.02)
        
        # Commit
        mouse.send(vp.build_simple(0x04))
        
        print("Done. Read Back...")
        time.sleep(0.5)
        d = mouse.read_flash(0x03, 0x00, 64)
        if d: print(d[:32].hex())
        
    finally:
        stop_spam.set()
        mouse.close()

if __name__ == "__main__":
    turbo_unlock_test()
