#!/usr/bin/env python3
"""Test by writing EXACT Windows artifacts/bin/ohshit.bin data to device."""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import hid
import time

VID = 0x25A7
PID = 0xFA08

def build_report(cmd: int, payload: bytes) -> bytes:
    if len(payload) != 14:
        payload = payload[:14].ljust(14, b'\x00')
    report = bytes([0x08, cmd]) + payload
    checksum = (0x55 - sum(report)) & 0xFF
    return report + bytes([checksum])

def build_simple(cmd: int) -> bytes:
    return build_report(cmd, bytes(14))

def build_chunk(page: int, offset: int, data: bytes) -> bytes:
    length = min(len(data), 10)
    padded = data[:10].ljust(10, b'\x00')
    payload = bytes([0x00, page, offset, length]) + padded
    return build_report(0x07, payload)

def main():
    # Load Windows artifacts/bin/ohshit.bin - extract macro data from page 0x03
    with open('artifacts/bin/ohshit.bin', 'rb') as f:
        win = f.read()
    
    win_macro = win[0x03 * 256 : 0x03 * 256 + 0x88]
    win_binding = win[0x60:0x64]  # Button 1 binding
    
    print(f"Windows macro data (page 0x03): {len(win_macro)} bytes")
    print(f"Windows binding at 0x60: {win_binding.hex()}")
    
    # Find device
    device_path = None
    for dev in hid.enumerate(VID, PID):
        if dev.get('usage_page') == 0xFF03:
            device_path = dev['path']
            break
    
    if not device_path:
        print("Device not found!")
        return
    
    device = hid.device()
    device.open_path(device_path)
    print("Device opened")
    
    reports = []
    
    # Enter config mode
    reports.append(build_simple(0x04))
    reports.append(build_simple(0x03))
    
    # Write EXACT Windows macro data to page 0x03
    for off in range(0, len(win_macro), 10):
        chunk = win_macro[off:off+10]
        reports.append(build_chunk(0x03, off, chunk))
    
    # Write EXACT Windows binding
    reports.append(build_chunk(0x00, 0x60, win_binding))
    
    # Commit
    reports.append(build_simple(0x04))
    
    print(f"Sending {len(reports)} packets...")
    for r in reports:
        print(f"  {r.hex()}")
        device.send_feature_report(r)
        time.sleep(0.01)
    
    device.close()
    print("\nDone! Test button 1 now.")

if __name__ == "__main__":
    main()
