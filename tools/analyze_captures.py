#!/usr/bin/env python3
"""
Analyze USB captures to extract HID protocol data for Venus mouse.
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break

import subprocess
import re
from pathlib import Path


def extract_hid_data(pcap_file: str) -> list[tuple[int, bytes]]:
    """Extract HID feature reports from a pcap file."""
    result = subprocess.run(
        ["tshark", "-r", pcap_file, "-Y", "usb.data_len >= 17", "-x"],
        capture_output=True,
        text=True
    )
    
    packets = []
    current_hex = []
    in_usb_control = False
    
    for line in result.stdout.split('\n'):
        # Look for "USB Control" or "Packet" headers
        if line.startswith("USB Control"):
            in_usb_control = True
            current_hex = []
        elif line.startswith("Packet") or (line == "" and current_hex):
            if current_hex and in_usb_control:
                # Parse the hex lines
                hex_bytes = b''
                for hex_line in current_hex:
                    # Pattern: 0000  xx xx xx xx...   ascii
                    match = re.match(r'^[0-9a-f]{4}\s+((?:[0-9a-f]{2}\s+)+)', hex_line)
                    if match:
                        hex_str = match.group(1).replace(' ', '')
                        hex_bytes += bytes.fromhex(hex_str)
                if len(hex_bytes) >= 17:
                    packets.append(hex_bytes)
                current_hex = []
                in_usb_control = False
            if line.startswith("Packet"):
                in_usb_control = False
        elif in_usb_control and re.match(r'^[0-9a-f]{4}\s+', line):
            current_hex.append(line)
    
    return packets


def analyze_modifier_key_packet(data: bytes) -> dict:
    """Analyze a key binding packet to extract modifier information."""
    if len(data) < 17:
        return {}
    
    # Skip the first setup bytes (8 bytes for setup header: 09 08 03 01 00 11 00)
    # The actual HID data starts after that
    if data[0:2] == b'\x09\x08':
        report_data = data[7:]  # Skip setup header
    else:
        report_data = data
    
    if len(report_data) < 17:
        return {}
    
    report_id = report_data[0]
    cmd = report_data[1]
    
    info = {
        "report_id": report_id,
        "command": cmd,
        "raw": report_data[:17].hex()
    }
    
    if cmd == 0x07:  # Write command
        page = report_data[3]
        offset = report_data[4]
        info["page"] = page
        info["offset"] = offset
        
        # Key binding detection
        if page >= 0x01 and report_data[5] == 0x08:  # Keyboard binding data
            modifier = report_data[9]  # Modifier byte
            keycode = report_data[8]   # HID keycode
            info["type"] = "key_binding"
            info["keycode"] = keycode
            info["modifier"] = modifier
            info["modifier_bits"] = {
                "ctrl": bool(modifier & 0x01),
                "shift": bool(modifier & 0x02),
                "alt": bool(modifier & 0x04),
                "win": bool(modifier & 0x08)
            }
        elif page == 0x00 and offset >= 0x54 and offset <= 0x60:
            info["type"] = "rgb_or_config"
        elif page == 0x00 and offset >= 0x60:
            info["type"] = "button_apply"
    
    return info


def main():
    usbcap_dir = Path("usbcap")
    
    # Analyze modifier key captures
    modifier_captures = [
        "wireless - rebind 1 to shift-1.pcapng",
        "wireless - rebind shift-1 to shift-ctrl-1.pcapng",
        "wireless - rebind shift-ctrl-1 to ctrl-alt-1.pcapng",
        "wireless - rebind ctrl-alt-1 to ctrl-win-1.pcapng",
    ]
    
    print("=" * 80)
    print("MODIFIER KEY ANALYSIS")
    print("=" * 80)
    
    for capture in modifier_captures:
        path = usbcap_dir / capture
        if not path.exists():
            print(f"Not found: {capture}")
            continue
        
        print(f"\n## {capture}")
        packets = extract_hid_data(str(path))
        for pkt in packets:
            info = analyze_modifier_key_packet(pkt)
            if info:  # Print all valid packets
                print(f"  CMD {info.get('command'):02X}: {info['raw']}")
                if info.get("command") == 0x07 and "modifier" in info:
                    print(f"    Keycode: 0x{info['keycode']:02x}, Modifier: 0x{info['modifier']:02x}")
                    print(f"    Modifiers: {info['modifier_bits']}")
    
    # Analyze RGB LED captures
    rgb_captures = [
        "rgb led from neon to steady magenta to steady red to lowest brightness to highest brightness to 20 percent bright.pcapng",
        "wired - led cycle through colors on steady then set brightness to 10 20 30 40 50 60 70 80 90 100 percent - see wired-colors-png.pcapng",
    ]
    
    print("\n" + "=" * 80)
    print("RGB LED ANALYSIS")
    print("=" * 80)
    
    for capture in rgb_captures:
        path = usbcap_dir / capture
        if not path.exists():
            print(f"Not found: {capture}")
            continue
        
        print(f"\n## {capture[:60]}...")
        packets = extract_hid_data(str(path))
        for pkt in packets:
            info = analyze_modifier_key_packet(pkt)
            if info:
                 print(f"  CMD {info.get('command'):02X}: {info['raw']}")
    
    # Analyze Macro captures
    macro_captures = [
        "wired - rebind 1 to macro called testing - t-dn 93ms t-up 157ms e-dn 93ms e-up 188ms s-dn 109ms s-up 156ms t-dn 94ms t-up 156ms i-dn 94ms i-up 188mc n-dn 78ms n-up 203ms g-dn 94ms g-up.pcapng",
        "wireless - rebind 11 to macro called testing - t-dn 93ms t-up 157ms e-dn 93ms e-up 188ms s-dn 109ms s-up 156ms t-dn 94ms t-up 156ms i-dn 94ms i-up 188mc n-dn 78ms n-up 203ms g-dn 94ms g-up.pcapng",
        "create new macro - record macro - apply macro _testing_ to side button 1.pcapng",
    ]
    
    print("\n" + "=" * 80)
    print("MACRO ANALYSIS")
    print("=" * 80)
    
    for capture in macro_captures:
        path = usbcap_dir / capture
        if not path.exists():
            print(f"Not found: {capture}")
            continue
        
        print(f"\n## {capture[:60]}...")
        packets = extract_hid_data(str(path))
        for pkt in packets:
            info = analyze_modifier_key_packet(pkt)
            if info:
                print(f"  CMD {info.get('command'):02X}: {info['raw']}")


if __name__ == "__main__":
    main()
