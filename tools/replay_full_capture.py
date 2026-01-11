from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import subprocess
import time
import venus_protocol as vp
import threading

def replay_traffic():
    # 1. Parse Capture
    print("Parsing Capture...")
    cmd = [
        "tshark", "-x", "-r", "usbcap/macros set to all 12 buttons.pcapng",
        "-Y", "usb.transfer_type == 0x02 && usb.endpoint_address == 0x02" 
        # Endpoint 0x02 is usually OUT (Host->Mouse) for this device?
        # Need to verify endpoint from earlier analysis.
        # dump_sequence.py used filtering logic.
        # Let's use loose filtering and check payload.
    ]
    # Actually, simpler: Dump ALL, filter by "Source = Host".
    # But tshark hex dump doesn't label source easily in -x mode without -V.
    # Alternative: Use existing analyze_hex_dump logic but extract ALL packets.
    pass

def parse_and_replay():
    # Use tshark -x to get raw hex and timestamps?
    # -x gives Hex+ASCII. Hard to parse time.
    # Use -T fields for time, -x for data? No.
    # Use -x only and ignore time? User wants "monitor...".
    # Sequence is more important than exact timing.
    # Let's use analyze_hex_dump logic but extract ALL packets.
    
    cmd = [
        "tshark", "-x", "-r", "usbcap/macros set to all 12 buttons.pcapng"
    ]
    
    print("Running tshark...")
    p = subprocess.run(cmd, capture_output=True, text=True)
    hex_data_raw = p.stdout.replace('\n', '').replace(' ', '')
    
    # Filter non-hex
    clean = "".join([c for c in hex_data_raw if c in '0123456789ABCDEFabcdef'])
    import binascii
    data_stream = binascii.unhexlify(clean)
    
    # Extract 17-byte packets starting with 08
    packets = []
    i = 0
    while i < len(data_stream) - 17:
        # Check for 08 prefix
        if data_stream[i] == 0x08:
            pkt = data_stream[i:i+17]
            # Heuristic: Valid Cmd Packet usually has Type byte at 1?
            # 08 07, 08 09, 08 4D, 08 01, 08 00...
            # And Checksum at 16 (or Magic).
            # Let's blindly trust '08' prefix for replay "All Traffic".
            
            # Filter Noise? (Cmd 00)
            # User wants "All Traffic".
            # Include Cmd 00? Maybe burst them.
            # But continuous stream of 00 might slow us down.
            # Let's skip Cmd 00 for efficiency unless it matters for keepalive.
            # Actually, User said "replay all the traffic".
            # I will include Cmd 00 but throttle replay if they are identical.
            
            packets.append(pkt)
            i += 17 # Jump Packet
        else:
            i += 1 # Slide
            
    print(f"Loaded {len(packets)} packets.")
    
    # Connect
    devs = vp.list_devices()
    if not devs:
        print("No device found.")
        return
    mouse = vp.VenusDevice(devs[0].path)
    mouse.open()
    
    try:
        # Replay
        start_replay_time = time.time()
        base_capture_time = packets[0][0]
        
        print("Starting Replay...")
        for i, data in enumerate(packets):
            # Timing Sync
            # target_delay = ts - base_capture_time
            # current_elapsed = time.time() - start_replay_time
            # wait = target_delay - current_elapsed
            # if wait > 0:
            #     time.sleep(wait)
            
            # Fast Replay (preserve order, minimize delay but respect order)
            # 0.002s delay
            time.sleep(0.002)
            
            # Send
            # print(f"[{i}] Sending {data.hex()}")
            try:
                mouse.send(data)
            except Exception as e:
                print(f"Error sending packet {i}: {e}")
                
            # Read?
            # User asked to "monitor what the mouse sends back".
            # Non-blocking read
            try:
                d = mouse._dev.read(64, timeout_ms=1)
                if d:
                    print(f"Response: {bytes(d).hex()}")
            except:
                pass
                
        print("Replay Complete.")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    parse_and_replay()
