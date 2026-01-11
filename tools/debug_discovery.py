from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import hid
import time
import sys

VENDOR_ID = 0x25A7
PRODUCT_IDS = (0xFA07, 0xFA08)

def calc_checksum(data):
    return (0x55 - sum(data[:16])) & 0xFF

def main():
    devices = []
    for d in hid.enumerate(VENDOR_ID):
        if d['product_id'] in PRODUCT_IDS and d['interface_number'] == 1:
            devices.append(d)
    
    if not devices:
        print("No device found")
        return

    dinfo = devices[0]
    dev = hid.device()
    dev.open_path(dinfo['path'])
    dev.set_nonblocking(False)

    print("Testing Flash Read with CMD 0x08 and Interrupt Read...")

    # Addresses to test:
    # Page 0, Offset 0x60 (Button 1 config)
    # Page 0x03, Offset 0x00 (Button 1 macro name)
    tests = [
        ("Read Page 0 Offset 0x60", [0x00, 0x00, 0x60, 0x08]),
        ("Read Page 3 Offset 0x00", [0x00, 0x03, 0x00, 0x08]),
        ("Read Page 1 Offset 0x00", [0x00, 0x01, 0x00, 0x08]), # Page 1 is keyboard
    ]

    for label, params in tests:
        print(f"\n--- {label} ---")
        payload = bytearray(14)
        payload[0:len(params)] = params
        pkt = bytearray([0x08, 0x08, *payload])
        pkt.append(calc_checksum(pkt))
        
        print(f">> {pkt.hex()}")
        dev.send_feature_report(pkt)
        time.sleep(0.05)
        
        resp = dev.read(128, timeout_ms=500)
        if resp:
            print(f"<< Interrupt: {bytes(resp).hex()}")
        else:
            print("<< No data on Interrupt In")

    dev.close()

if __name__ == "__main__":
    main()
