from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import venus_protocol as vp
import time

def replay_capture():
    target_cap = "bind macros 123"
    log_file = "artifacts/txt/host_mouse_communication.txt"
    
    print(f"Searching for capture '{target_cap}' in {log_file}...")
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
        
    packet_sequence = []
    in_target = False
    
    for line in lines:
        if line.startswith("["):
            # specific strict check
            if target_cap in line:
                in_target = True
                print("Found target capture start.")
            else:
                if in_target:
                    print("End of target capture block.")
                in_target = False
            continue
            
        if not in_target: continue
        
        # We only want Host To Mouse packets
        if "--> H2M" not in line: continue
        
        # Extract hex
        # Line format: "   --> H2M | COMMAND  | 08 07 ... | ..."
        parts = line.split('|')
        if len(parts) < 3: continue
        
        hex_str = parts[2].strip()
        # "08 07 00 ..."
        hex_bytes = [int(b, 16) for b in hex_str.split()]
        
        packet_sequence.append(bytes(hex_bytes))
        
    print(f"Extracted {len(packet_sequence)} packets to replay.")
    
    if not packet_sequence:
        print("No packets found!")
        return

    # Connect
    devs = vp.list_devices()
    if not devs:
        print("No device found.")
        return
        
    mouse = vp.VenusDevice(devs[0].path)
    # Using raw hid handle to bypass any logic if needed, 
    # but VenusDevice.send() is just dev.send_feature_report.
    # We'll use mouse.open() then mouse.send().
    mouse.open()
    
    try:
        print("Starting Replay...")
        for i, pkt in enumerate(packet_sequence):
            # Hex dump for user visibility
            hex_fmt = " ".join([f"{b:02X}" for b in pkt])
            print(f"[{i+1}/{len(packet_sequence)}] Sending: {hex_fmt}")
            
            try:
                # Venus Device expects 17 bytes usually?
                # The log packets are usually 17 bytes (last byte is checksum/magic?)
                # Let's just send what we got.
                if len(pkt) == 17:
                    mouse.send(pkt) 
                else:
                    # If it's not 17, maybe pad it? Or try raw send?
                    # Logs seem to always be 17 for Venus.
                    # Let's pad if short, truncate if long?
                    # Actually valid Venus packets strictly 17?
                    if len(pkt) < 17:
                        print(f"Warning: Packet length {len(pkt)} < 17. Padding.")
                        pkt = pkt + bytes([0]* (17-len(pkt)))
                        mouse.send(pkt)
                    elif len(pkt) > 17:
                         print(f"Warning: Packet length {len(pkt)} > 17. Truncating.")
                         mouse.send(pkt[:17])
            except Exception as e:
                print(f"Error sending packet {i}: {e}")
                
            # Timing from log? Log doesn't have timestamps easily parsed here.
            # Use small delay.
            time.sleep(0.02)
            
        print("Replay Complete.")
        
    finally:
        mouse.close()

if __name__ == "__main__":
    replay_capture()
