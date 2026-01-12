import subprocess
import re
import time
import os
import signal
import sys
from datetime import datetime

# Configuration
TARGET_VENDOR_PRODUCT = "25a7:fa07"
OUTPUT_DIR = "new-usbcap"
USBMON_DEBUG_PATH = "/sys/kernel/debug/usb/usbmon"

def get_device_info():
    """Finds the bus and device number for the target device."""
    try:
        lsusb_output = subprocess.check_output(["lsusb"], text=True)
        for line in lsusb_output.splitlines():
            if TARGET_VENDOR_PRODUCT in line:
                # Example: Bus 003 Device 062: ID 25a7:fa07 Areson Technology Corp 2.4G Wireless Receiver
                match = re.search(r"Bus (\d+) Device (\d+):", line)
                if match:
                    return int(match.group(1)), int(match.group(2))
    except subprocess.CalledProcessError:
        print("Error running lsusb")
    return None, None

def main():
    if os.geteuid() != 0:
        print("This script must be run as root (use sudo).")
        sys.exit(1)

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    bus, dev = get_device_info()
    if bus is None:
        print(f"Device {TARGET_VENDOR_PRODUCT} not found.")
        sys.exit(1)

    print(f"Found device on Bus {bus}, Device {dev}")

    # USBMON device ID (e.g., usbmon3)
    usbmon_dev = f"usbmon{bus}"
    
    # Text interface path (e.g., /sys/kernel/debug/usb/usbmon/3u)
    text_debug_file = f"{USBMON_DEBUG_PATH}/{bus}u"

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{OUTPUT_DIR}/{timestamp}_bus{bus}_dev{dev}.pcapng"

    print(f"Starting capture on {usbmon_dev}...")
    print(f"Saving to {filename}")
    print("Press Ctrl+C to stop.")

    # Start dumpcap
    # -i usbmonX: interface
    # -w filename: write to file
    dumpcap_cmd = ["dumpcap", "-i", usbmon_dev, "-w", filename] 
    
    dumpcap_process = subprocess.Popen(dumpcap_cmd)
    
    # Signal handling for graceful exit on timeout or kill
    def signal_handler(sig, frame):
        print("\nReceived signal to stop.")
        raise KeyboardInterrupt
    
    signal.signal(signal.SIGTERM, signal_handler)
    
    dev_str = f":{dev:03d}:" 
    
    cat_process = subprocess.Popen(["cat", text_debug_file], stdout=subprocess.PIPE, text=True, bufsize=1)

    try:
        while True:
            # Read line from text interface
            line = cat_process.stdout.readline()
            if not line:
                break
            
            # Filter for our device
            target_pattern = f":{bus}:{dev:03d}:"
            
            if target_pattern in line:
                print(line.strip())
                
    except KeyboardInterrupt:
        print("\nStopping capture...")
    finally:
        # Cleanup
        dumpcap_process.terminate()
        cat_process.terminate()
        try:
            dumpcap_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            dumpcap_process.kill()
        
        print(f"Capture saved to {filename}")
        
        # Verify file exists
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            print(f"File size: {size} bytes")
        else:
            print("Warning: Capture file not found.")

if __name__ == "__main__":
    main()