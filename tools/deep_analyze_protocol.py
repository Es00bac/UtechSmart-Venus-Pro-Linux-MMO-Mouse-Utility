from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import os
import glob
import struct

# ANSI Colors for formatting
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
    # Specific data types
    CMD = '\033[38;5;208m'      # Orange for commands
    PAGE = '\033[38;5;141m'     # Purple for Page IDs
    OFFSET = '\033[38;5;39m'    # Blue for Offsets
    DATA_ZERO = '\033[90m'      # Gray for zeros
    DATA_VAL = '\033[97m'       # White for values
    EVENT_KEY = '\033[38;5;118m' # Green for Keycodes
    EVENT_TIME = '\033[38;5;226m'# Yellow for Time
    UNKNOWN = '\033[41;97m'     # Red BG for interesting unknowns

def colorize_hex(data, annotation_type=None):
    s = []
    for b in data:
        if b == 0:
            s.append(f"{Colors.DATA_ZERO}{b:02X}{Colors.ENDC}")
        else:
            if annotation_type == 'event':
                s.append(f"{Colors.EVENT_KEY}{b:02X}{Colors.ENDC}")
            elif annotation_type == 'delay':
                s.append(f"{Colors.EVENT_TIME}{b:02X}{Colors.ENDC}")
            else:
                s.append(f"{Colors.DATA_VAL}{b:02X}{Colors.ENDC}")
    return " ".join(s)

def parse_pcap_packets(filepath):
    """
    Rudimentary parser for our specific pcapng files to extract HID payloads.
    Reliable output requires actual pcap library, but we'll try to grep 
    for the specific HID report signatures (0x08, 0x09 + 15 bytes + checksum)
    since we don't have scapy/pyshark installed in this env.
    """
    with open(filepath, 'rb') as f:
        raw = f.read()

    packets = []
    i = 0
    # Search for logical blocks that look like our 17-byte HID reports
    # Signature: [ID] [CMD] ... [CHECKSUM]
    # Checksum = (0x55 - sum(bytes 0..15)) & 0xFF
    while i < len(raw) - 17:
        chunk = raw[i:i+17]
        # Heuristic: First byte is Report ID (0x08 or 0x09)
        # Second byte is valid command (0x01-0x09)
        if chunk[0] in [0x08, 0x09] and chunk[1] <= 0x20:
            checksum = (0x55 - sum(chunk[:16])) & 0xFF
            if chunk[16] == checksum:
                packets.append({
                    'offset': i,
                    'data': chunk,
                    'direction': 'H2M' if chunk[0] == 0x08 else 'M2H'
                })
                i += 17
                continue
        i += 1
    return packets

def analyze_capture(filepath):
    print(f"\n{Colors.HEADER}=== Analyzing: {os.path.basename(filepath)} ==={Colors.ENDC}")
    packets = parse_pcap_packets(filepath)
    print(f"Found {len(packets)} valid HID packets.")
    
    # Track the "Conversation"
    for idx, p in enumerate(packets):
        d = p['data']
        rep_id = d[0]
        cmd = d[1]
        
        dir_arrow = "-->" if p['direction'] == 'H2M' else "<--"
        dir_color = Colors.OKGREEN if p['direction'] == 'H2M' else Colors.OKCYAN
        
        cmd_name = "UNKNOWN"
        if cmd == 0x03: cmd_name = "HANDSHAKE"
        elif cmd == 0x04: cmd_name = "COMMIT"
        elif cmd == 0x07: cmd_name = "WRITE"
        elif cmd == 0x08: cmd_name = "READ"
        elif cmd == 0x09: cmd_name = "INIT/RESET"
        
        # Detail extraction
        details = ""
        if cmd == 0x07 or cmd == 0x08: # Write/Read
            page = d[3]
            offset = d[4]
            length = d[5]
            payload = d[6:6+length]
            
            details = f"Page:{Colors.PAGE}0x{page:02X}{Colors.ENDC} Off:{Colors.OFFSET}0x{offset:02X}{Colors.ENDC} Len:{length}"
            if cmd == 0x07:
                # Colorize payload based on macros
                if page >= 0x03: # Macro pages
                    details += f" Data: {colorize_hex(payload)}"
                    # text decode
                    try: 
                        txt = payload.decode('utf-16le', errors='ignore')
                        clean_txt = "".join([c for c in txt if c.isprintable()])
                        if len(clean_txt) > 1: details += f" '{clean_txt}'"
                    except: pass
                else:
                    details += f" Data: {colorize_hex(payload)}"
        
        print(f"{Colors.DATA_ZERO}[{idx:03d}]{Colors.ENDC} {dir_color}{dir_arrow}{Colors.ENDC} {Colors.CMD}{cmd_name:<10}{Colors.ENDC} ({cmd:02X}) {details}")
        
    print(f"    {Colors.WARNING}>>> TERMINATOR DETECTED: InnerByte=0x{d[8]:02X}{Colors.ENDC}")

    return packets

def reconstruct_memory(packets):
    """Reconstructs the mouse memory state based on WRITE commands."""
    memory = {} # {page: {offset: byte}}
    
    for p in packets:
        d = p['data']
        cmd = d[1]
        if cmd == 0x07: # WRITE
            page = d[3]
            offset = d[4]
            length = d[5]
            payload = d[6:6+length]
            
            if page not in memory: memory[page] = {}
            for i, b in enumerate(payload):
                memory[page][offset + i] = b
                
    return memory

def solve_terminator_checksum(memory):
    """Tries to find the formula for the Terminator Inner Byte."""
    print(f"\n{Colors.HEADER}=== Solving Terminator Checksums ==={Colors.ENDC}")
    
    # Locate all terminators in memory
    # A terminator is [00 03 XX 00 00 00]
    # We look for the sequence in the reconstructed pages
    
    for page_id, page_data in memory.items():
        if page_id < 0x03: continue # Skip setting pages
        
        # reconstruct byte array for page
        max_off = max(page_data.keys())
        pbytes = bytearray(max_off + 1)
        for off, val in page_data.items():
            pbytes[off] = val
            
        # Scan for terminator pattern 00 03
        for i in range(len(pbytes) - 6):
            if pbytes[i] == 0x00 and pbytes[i+1] == 0x03 and pbytes[i+3]==0x00:
                inner = pbytes[i+2]
                term_offset = i
                
                # We found a terminator. Now let's define the "Macro Body"
                # Macros start at 0x00 (header) or 0x20 (events)
                # Let's assume header is 0x00-0x20, Events 0x20-Terminator
                
                # Check Header Info
                name_len = pbytes[0]
                event_count = pbytes[0x1F]
                
                print(f"Page {Colors.PAGE}0x{page_id:02X}{Colors.ENDC}: Found Terminator at {Colors.OFFSET}0x{term_offset:02X}{Colors.ENDC} Inner=0x{inner:02X}")
                print(f"  NameLen: {name_len}, EventCount: {event_count}")
                
                # Extract Event Data
                events_start = 0x20
                events_end = term_offset
                event_data = pbytes[events_start:events_end]
                
                # Verify Event Count vs Data Size
                # Each event is 5 bytes? 
                calc_events = len(event_data) // 5
                print(f"  Calculated Events from size: {calc_events} (Matches Header? {calc_events == event_count})")
                
                # Brute Force Checksums
                print(f"  {Colors.OKBLUE}Testing Hypotheses:{Colors.ENDC}")
                
                # 1. Simple Sum
                s = sum(event_data) & 0xFF
                if s == inner: print(f"    [MATCH] Sum(Events) & 0xFF")
                
                # 2. 0x55 - Sum
                if (0x55 - s) & 0xFF == inner: print(f"    [MATCH] 0x55 - Sum(Events)")
                
                # 3. Sum + Offset
                if (s + term_offset) & 0xFF == inner: print(f"    [MATCH] Sum(Events) + Offset")
                
                # 4. Length based
                if (len(event_data) + 0x45) & 0xFF == inner: print(f"    [MATCH] Len + 0x45")
                
                # 5. Last Byte theories
                if len(event_data) > 0:
                    last_byte = event_data[-1]
                    if last_byte == inner: print(f"    [MATCH] Last Byte of Data")
                    if (last_byte + term_offset) & 0xFF == inner: print("    [MATCH] LastByte + Offset")
                
                # 6. Sum of Delays (Bytes 3,4 of every 5-byte chunk)
                delay_sum = 0
                for j in range(0, len(event_data), 5):
                    if j+4 < len(event_data):
                        delay = (event_data[j+3] << 8) | event_data[j+4]
                        delay_sum += delay
                
                if (delay_sum & 0xFF) == inner: print(f"    [MATCH] Sum(Delays) & 0xFF")
                if ((delay_sum >> 8) & 0xFF) == inner: print(f"    [MATCH] Sum(Delays) >> 8")
                
                # 7. XOR Sum
                x = 0
                for b in event_data: x ^= b
                if x == inner: print(f"    [MATCH] XOR Sum")

                # 8. Events End + 3 (The "Testing" pattern found earlier)
                # events_end is term_offset + 2 (since terminator overwrites last 2 bytes usually?)
                # Wait, earlier analysis said `events_end (0x66) + 3 = 0x69`
                # Here `events_end` corresponds to `term_offset + 2` essentially.
                if (term_offset + 2 + 3) & 0xFF == inner: print(f"    [MATCH] (TermOffset + 2) + 3")
                
                # 9. Events End - 0x3F (The "OhShit" pattern)
                if (term_offset + 2 - 0x3F) & 0xFF == inner: print(f"    [MATCH] (TermOffset + 2) - 0x3F")
                
                # SAVE BINARY FOR BRUTE FORCE
                try: 
                    # Name is at 0x01, length is at 0x00 (in bytes, so chars * 2)
                    name_bytes_len = pbytes[0]
                    name_raw = pbytes[1:1+name_bytes_len]
                    valid_name = name_raw.decode('utf-16le', errors='ignore').split('\x00')[0]
                    # Filter filename safely
                    valid_name = "".join([c for c in valid_name if c.isalnum() or c in ('_','-')]) 
                    if not valid_name: valid_name = "unk"
                    fn = f"macro_{valid_name}_{page_id:02x}.bin"
                except:
                    fn = f"macro_unk_{page_id:02x}_{term_offset:02x}.bin"
                    
                # We save from 0x00 up to (but not including) the terminator
                # Because the terminator itself contains the check byte we are solving for!
                with open(fn, "wb") as f:
                    f.write(pbytes[0:term_offset])
                print(f"  {Colors.OKGREEN}Saved binary to {fn}{Colors.ENDC}")


if __name__ == "__main__":
    files = sorted(glob.glob("usbcap/*.pcapng"))
    # Analyze specific interesting files
    targets = ["bind macros 123", "ohshit", "testing"]
    
    for filename in targets:
        # Find partial match
        match = next((f for f in files if filename in f.lower()), None)
        if match:
            packets = analyze_capture(match)
            mem = reconstruct_memory(packets)
            solve_terminator_checksum(mem)
