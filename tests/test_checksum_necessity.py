from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import hid
import time
import sys
import os

# Device constants
VENDOR_ID = 0x25a7
PRODUCT_IDS = [0xfa08, 0xfa07] # Wired, Wireless

def get_device():
    # Enumerate matches
    for d in hid.enumerate(VENDOR_ID):
        if d['product_id'] in PRODUCT_IDS:
             # We need the specific interface?
             # HIDAPI usually opens the first interface or we filter by usage page
             # UtechSmart uses Usage Page 0xFF00 usually for config
             # But let's just try opening path
             print(f"Found device: {d['path']}")
             try:
                 h = hid.device()
                 h.open_path(d['path'])
                 return h
             except Exception as e:
                 print(f"Failed to open {d['path']}: {e}")
                 
    raise ValueError("Device not found via HIDAPI")

def send_report(dev, data):
    # HIDAPI expects Report ID as first byte in data for send_feature_report
    # Our data starts with 0x08, which IS the Report ID.
    # But we need to pad to 144 bytes?
    # Actually, HIDAPI handles report ID.
    # If data[0] is Report ID, send_feature_report(data) works.
    
    # Ensure data is 144 bytes (padded)
    # Actually HIDAPI usually takes exact length for SetFeature?
    # But windows capture shows 144.
    if len(data) < 144:
        data = list(data) + [0] * (144 - len(data))
    
    dev.send_feature_report(data)
    time.sleep(0.05)

def test_upload(inner_byte_val):
    print(f"=== Testing Upload with Inner Byte 0x{inner_byte_val:02X} ===")
    dev = get_device()
    
    # 1. Load working artifacts/bin/ohshit.bin
    if not os.path.exists("artifacts/bin/ohshit.bin"):
        print("Error: artifacts/bin/ohshit.bin not found!")
        return

    with open("artifacts/bin/ohshit.bin", "rb") as f:
        macro_data = bytearray(f.read())
        
    # 2. Modify Inner Byte
    # Terminator is at 0x82: 00 03 45 00 00 00
    # Page 0x03 start at 0x300
    term_idx = 0x300 + 0x82
    # Verify signature
    # 00 03 45 00 00 00
    if len(macro_data) > term_idx+2 and macro_data[term_idx] == 0x00 and macro_data[term_idx+1] == 0x03:
         print(f"Found terminator at 0x{term_idx:X}. Original: 0x{macro_data[term_idx+2]:02X}")
         macro_data[term_idx+2] = inner_byte_val
         print(f"Modified Inner to: 0x{inner_byte_val:02X}")
    else:
        print("Terminator not found at expected location, scanning...")
        idx = macro_data.find(b'\x00\x03\x45\x00\x00\x00')
        if idx != -1:
             print(f"Found at 0x{idx:X}")
             macro_data[idx+2] = inner_byte_val
        else:
             print("Terminator not found.")
             return

    # 3. Upload Page 0x03
    page_start = 0x300
    page_data = macro_data[page_start : page_start+256]
    
    # Handshake
    # 08 03 ...
    hs = [0x08, 0x03] + [0]*13 + [0x4A] # Is checksum always 4A for 08 03? 
    # 0x55 - 0x08 - 0x03 = 0x4A. Yes.
    # Note: send_feature_report expects list of ints or bytes
    send_report(dev, hs)
    
    # Write in 10 byte chunks
    print("Writing data...")
    for i in range(0, 256, 10):
        chunk_len = min(10, 256 - i)
        chunk = page_data[i : i+chunk_len]
        
        # Header [08 07 00 03 OFFSET LEN]
        header = [0x08, 0x07, 0x00, 0x03, i, chunk_len]
        payload = list(chunk)
        packet = header + payload
        
        # Checksum
        cs = (0x55 - sum(packet)) & 0xFF
        packet.append(cs)
        
        send_report(dev, packet)
        
    print("Upload complete.")
    
    # 4. Bind to Button 4
    print("Binding Macro 3 to Button 4...")
    # 08 07 00 00 6C 04 06 03 01 [CS]
    bind_pkt = [0x08, 0x07, 0x00, 0x00, 0x6C, 0x04, 0x06, 0x03, 0x01]
    cs = (0x55 - sum(bind_pkt)) & 0xFF
    bind_pkt.append(cs)
    send_report(dev, bind_pkt)
    
    # Commit
    # 08 04 ...
    cm = [0x08, 0x04] + [0]*13
    cs = (0x55 - sum(cm[:-1])) & 0xFF # Checksum (0x49)
    # 08+04=0C. 55-0C=49.
    cm.append(0x49)
    send_report(dev, cm)
    
    print("Bind complete.")

if __name__ == "__main__":
    test_upload(0x00) # Test 0x00
