#!/usr/bin/env python3
"""
Test macro upload using EXACT bytes from Windows capture.
This verifies the protocol is correct by bypassing all Python encoding logic.
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import venus_protocol as vp
import time

# EXACT packets from "wired - rebind 1 to macro called testing" capture
CAPTURE_PACKETS = [
    # bytes.fromhex("080300000000000000000000000000004a"),  # Prepare
    bytes.fromhex("0804000000000000000000000000000049"),  # Finalize
    bytes.fromhex("0804000000000000000000000000000049"),  # Finalize
    bytes.fromhex("080300000000000000000000000000004a"),  # Prepare
    bytes.fromhex("080300000000000000000000000000004a"),  # Prepare
    # Name chunks
    bytes.fromhex("08070003000a0e74006500730074006902"),  # Offset 0x00: name "testi..."
    bytes.fromhex("080700030a0a006e00670000000000005a"),  # Offset 0x0A: "ng"
    bytes.fromhex("08070003140a0000000000000000000025"),  # Offset 0x14: padding
    # Event chunks
    bytes.fromhex("080700031e0a000e811700005d411700c0"),  # T down+up
    bytes.fromhex("08070003280a009d810800005d41080045"),  # E down+up
    bytes.fromhex("08070003320a00bc811600006d411600f0"),  # S down+up
    bytes.fromhex("080700033c0a009c811700005e41170013"),  # T down+up
    bytes.fromhex("08070003460a009c810c00005e410c001f"),  # I down+up
    bytes.fromhex("08070003500a00bc811100004e411100fb"),  # N down+up
    bytes.fromhex("080700035a0a00cb810a00005e410a00e0"),  # G down+up
    # Terminator
    bytes.fromhex("080700036406000369000000000000006d"),
    # Bind
    bytes.fromhex("0807000060040600014e0000000000008d"),
    # Commit
    bytes.fromhex("0804000000000000000000000000000049"),
]


def main():
    print("Macro Upload Test - Using EXACT Capture Bytes")
    print("=" * 60)
    
    # Find device
    devices = vp.list_devices()
    if not devices:
        print("No Venus device found!")
        return
    
    print(f"Found device: {devices[0].product}")
    
    # Open device
    dev = vp.VenusDevice(devices[0].path)
    dev.open()
    print("Connected to device")
    print()
    
    print("Sending EXACT capture packets (Button 1 -> Macro 'testing')...")
    print()
    
    for i, packet in enumerate(CAPTURE_PACKETS):
        print(f"  Packet {i+1:2d}: {packet.hex()}")
        dev.send(packet)
        time.sleep(0.05)  # 50ms delay as protocol requires
    
    print()
    print("Upload complete!")
    print("Press Button 1 (Side Button 1) to test - it should type 'testing'")
    
    dev.close()


if __name__ == "__main__":
    main()
