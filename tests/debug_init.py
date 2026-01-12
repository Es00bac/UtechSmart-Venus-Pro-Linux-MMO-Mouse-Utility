import sys
import os
import time
import hid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import venus_protocol as vp

def main():
    print("--- Debug Init Script ---")
    
    # 1. Unlock (Aggressive)
    if vp.PYUSB_AVAILABLE:
        print("1. Unlocking device (PyUSB)...")
        try:
            vp.unlock_device()
            print("   Unlock command sent.")
        except Exception as e:
            print(f"   Unlock failed: {e}")
    else:
        print("1. PyUSB not available, skipping unlock.")

    # Simulating the delay/race condition in GUI startup
    # The GUI calls refresh immediately after unlock.
    print("2. Listing devices (hidapi)...")
    devices = vp.list_devices()
    
    if not devices:
        print("   No devices found.")
        return
        
    for i, dev_info in enumerate(devices):
        print(f"   Device {i}: {dev_info.product} ({dev_info.path})")

    target_info = devices[0]
    target_path = target_info.path
    
    print(f"3. Opening device: {target_path}...")
    
    device = None
    try:
        device = vp.VenusDevice(target_path)
        device.open()
        print("   Device opened.")
        
        # 4. Read Settings Sequence
        print("4. Attempting Read Settings Sequence...")
        
        # 4.1 Handshake (0x03)
        print("   Sending Handshake (0x03)...")
        pkt_03 = vp.build_simple(0x03)
        # Using send_reliable for handshake? GUI sends send(03) then loops read_flash.
        # But send_reliable waits for 09 03.
        # GUI _read_settings uses: device.send(vp.build_simple(0x03))
        
        device.send(pkt_03)
        print("   Handshake sent. (No wait)")
        
        # 4.2 Read Page 0
        print("   Reading Page 0 (8 bytes at offset 0)...")
        try:
            chunk = device.read_flash(0, 0, 8)
            print(f"   Success! Data: {chunk.hex()}")
        except Exception as e:
            print(f"   Read Failed: {e}")
            
    except Exception as e:
        print(f"   Open/Comm Error: {e}")
    finally:
        if device:
            device.close()
            print("   Device closed.")

if __name__ == "__main__":
    main()
