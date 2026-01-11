from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import usb.core
import usb.util
import time
import sys

def test_unlock():
    print("Trying Magic Unlock Sequence with PyUSB (Interface 1)...")
    
    # 1. Find Device (25A7:FA08 Wireless or FA07 Wired)
    dev = usb.core.find(idVendor=0x25A7, idProduct=0xFA08)
    if dev is None:
        dev = usb.core.find(idVendor=0x25A7, idProduct=0xFA07)
    
    if dev is None:
        print("No device found")
        return

    # 2. Detach Kernel Driver from Interface 1 (and 0?)
    # Usually we need to detach from the interface we want to claim.
    # Protocol uses Interface 1 for Config?
    # Capture setup: 21 09 ... wIndex=01
    
    # Try detaching both to be safe
    for iface in [0, 1]:
        if dev.is_kernel_driver_active(iface):
            try:
                dev.detach_kernel_driver(iface)
                print(f"Kernel driver detached from Interface {iface}.")
            except usb.core.USBError as e:
                print(f"Could not detach kernel driver from {iface}: {e}")

    try:
        # 3. Claim Interface 1
        # Interface 0 is Mouse, Interface 1 is Keyboard/Consumer?
        # Configuration commands go to Interface 1.
        usb.util.claim_interface(dev, 1)
        print("Interface 1 claimed.")
        
        # 4. Initialization (Cmd 09 - Reset)
        print("Sending Cmd 09 (Reset)...")
        
        def send_feature(data):
            # Capture showed 17 bytes: 08 ...
            padded = data.ljust(17, b'\x00')
            # wValue = 0x0308 (Report Type 3, ID 8)
            # wIndex = 1 (Interface 1)
            try:
                dev.ctrl_transfer(0x21, 0x09, 0x0308, 1, padded)
            except usb.core.USBError as e:
                print(f"Send Error: {e}")

        send_feature(bytes([0x08, 0x09])) 
        time.sleep(1.0) # Wait for reset
        
        # 5. Magic Sequence
        # Capture: 08 4D 05 50 00 55 00 55 00 55 91
        print("Sending Magic Packet 1 (4D)...")
        send_feature(bytes([0x08, 0x4D, 0x05, 0x50, 0x00, 0x55, 0x00, 0x55, 0x00, 0x55, 0x91]))
        time.sleep(0.05)
        
        # Capture: 08 01 00 00 00 04 56 57 3d 1b 00 00
        print("Sending Magic Packet 2 (01)...")
        send_feature(bytes([0x08, 0x01, 0x00, 0x00, 0x00, 0x04, 0x56, 0x57, 0x3d, 0x1b, 0x00, 0x00]))
        time.sleep(0.05)
        
        # 6. Read Test (Page 3)
        print("Sending Read Request (Page 3)...")
        send_feature(bytes([0x08, 0x08, 0x03, 0x00, 0x10]))
        time.sleep(0.05)
        
        # Read Response from EP IN on Interface 1
        cfg = dev.get_active_configuration()
        intf = cfg[(1,0)] # Interface 1, Alt 0
        ep_in = [ep for ep in intf if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN][0]
        
        print(f"Reading from Endpoint {ep_in.bEndpointAddress:02X}...")
        try:
            resp = dev.read(ep_in.bEndpointAddress, 64, timeout=2000)
            print(f"Read Data: {bytes(resp).hex()}")
        except usb.core.USBError as e:
            print(f"Read Error: {e}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Re-attach is hard from script reliably, user might need to replug
        pass

if __name__ == "__main__":
    test_unlock()
