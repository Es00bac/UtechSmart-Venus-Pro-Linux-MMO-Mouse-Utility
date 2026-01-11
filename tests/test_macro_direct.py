#!/usr/bin/env python3
"""
Standalone macro upload test - bypasses GUI to test protocol directly.
Run with: python3 tests/test_macro_direct.py
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import hid
import time
import struct

# Device identifiers
VID = 0x25A7
PID_MOUSE = 0xFA08  # "2.4G Dual Mode Mouse" - THIS IS THE CORRECT ONE
PID_RECEIVER = 0xFA07  # "2.4G Wireless Receiver"
REPORT_ID = 0x08

# Button offsets in Page 0
BUTTON_OFFSETS = {
    1: 0x60, 2: 0x64, 3: 0x68, 4: 0x6C, 5: 0x70, 6: 0x74,
    7: 0x80, 8: 0x84, 9: 0x90, 10: 0x94, 11: 0x98, 12: 0x9C
}

# HID key codes (US layout)
KEY_CODES = {
    'a': 0x04, 'b': 0x05, 'c': 0x06, 'd': 0x07, 'e': 0x08, 'f': 0x09,
    'g': 0x0A, 'h': 0x0B, 'i': 0x0C, 'j': 0x0D, 'k': 0x0E, 'l': 0x0F,
    'm': 0x10, 'n': 0x11, 'o': 0x12, 'p': 0x13, 'q': 0x14, 'r': 0x15,
    's': 0x16, 't': 0x17, 'u': 0x18, 'v': 0x19, 'w': 0x1A, 'x': 0x1B,
    'y': 0x1C, 'z': 0x1D, '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21,
    '5': 0x22, '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
    ' ': 0x2C, '?': 0x38,  # ? is Shift+/
    '/': 0x38, '!': 0x1E,  # ! is Shift+1
}

# Characters that need Shift
SHIFT_CHARS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+{}|:"<>?')


def build_report(cmd: int, payload: bytes) -> bytes:
    """Build a 17-byte HID report with checksum."""
    if len(payload) != 14:
        payload = payload[:14].ljust(14, b'\x00')
    report = bytes([REPORT_ID, cmd]) + payload
    checksum = (0x55 - sum(report)) & 0xFF
    return report + bytes([checksum])


def build_simple(cmd: int) -> bytes:
    """Build a simple command (0x03, 0x04, 0x09)."""
    return build_report(cmd, bytes(14))


def build_macro_chunk(page: int, offset: int, data: bytes) -> bytes:
    """Build a write command for macro data."""
    length = min(len(data), 10)
    padded = data[:10].ljust(10, b'\x00')
    payload = bytes([0x00, page, offset, length]) + padded
    return build_report(0x07, payload)


def build_binding(button_offset: int, macro_slot: int, repeat_mode: int = 0x03) -> bytes:
    """Build a macro binding packet.
    
    repeat_mode: 0x01 = Windows default, 0x03 = Once, 0xFE = Hold, 0xFF = Toggle
    """
    btype = 0x06  # Macro type
    d1 = macro_slot & 0xFF
    d2 = repeat_mode & 0xFF
    d3 = (0x55 - (btype + d1 + d2)) & 0xFF
    
    payload = bytes([0x00, 0x00, button_offset, 0x04, btype, d1, d2, d3, 0, 0, 0, 0, 0, 0])
    return build_report(0x07, payload)


def text_to_events(text: str, delay_ms: int = 35) -> list:
    """Convert text to list of (status, keycode, delay) tuples.
    
    Matches Windows format: no shift for lowercase, shift for uppercase/symbols.
    For 'sh' in 'shit', Windows sends them overlapping (s_down, h_down, s_up, h_up).
    But for simplicity, we'll do sequential.
    """
    events = []
    delay_bytes = [(delay_ms >> 8) & 0xFF, delay_ms & 0xFF]
    
    for char in text:
        lower = char.lower()
        needs_shift = char in SHIFT_CHARS
        
        # Get keycode
        if lower in KEY_CODES:
            keycode = KEY_CODES[lower]
        else:
            print(f"Warning: Unknown char '{char}', skipping")
            continue
        
        if needs_shift:
            # Shift modifier sequence: MOD_DN, KEY_DN, MOD_UP, KEY_UP
            events.append(bytes([0x80, 0x02, 0x00] + delay_bytes))  # Shift down
            events.append(bytes([0x81, keycode, 0x00] + delay_bytes))  # Key down
            events.append(bytes([0x40, 0x02, 0x00, 0x00, 0x03]))  # Shift up (short delay)
            events.append(bytes([0x41, keycode, 0x00] + delay_bytes))  # Key up
        else:
            # Simple key: KEY_DN, KEY_UP
            events.append(bytes([0x81, keycode, 0x00] + delay_bytes))  # Key down
            events.append(bytes([0x41, keycode, 0x00] + delay_bytes))  # Key up
    
    return events


def upload_macro(device, name: str, text: str, macro_slot: int, button: int):
    """Upload a text macro and bind to button."""
    print(f"\n=== Uploading macro '{name}' to slot {macro_slot}, button {button} ===")
    print(f"Text: '{text}'")
    
    # Build macro buffer
    name_bytes = name.encode('utf-16le')[:28]
    events = text_to_events(text)
    
    print(f"Name length: {len(name_bytes)} bytes")
    print(f"Event count: {len(events)}")
    
    # Build buffer: [name_len] [name...] [...zeros to 0x1F] [event_count] [events...]
    buf = bytearray(512)
    buf[0] = len(name_bytes)
    buf[1:1+len(name_bytes)] = name_bytes
    buf[0x1F] = len(events)  # Event count
    
    # Pack events starting at 0x20
    offset = 0x20
    for event in events:
        buf[offset:offset+5] = event
        offset += 5
    
    events_end = offset
    term_offset = events_end - 2  # Terminator at events_end - 2
    
    print(f"Events end: 0x{events_end:02X}, terminator at: 0x{term_offset:02X}")
    
    # Calculate macro page
    # Slot 0 = Page 0x03, Slot 1 = Page 0x04 offset 0x80, etc.
    if macro_slot == 0:
        macro_page = 0x03
        macro_start = 0x00
    else:
        macro_page = 0x03 + ((macro_slot * 3) // 2)
        macro_start = 0x80 if (macro_slot % 2 != 0) else 0x00
    
    print(f"Macro page: 0x{macro_page:02X}, start offset: 0x{macro_start:02X}")
    
    # Send sequence
    reports = []
    
    # 1. Enter config mode (like Windows: COMMIT x2, then HANDSHAKE)
    reports.append(build_simple(0x04))
    reports.append(build_simple(0x03))
    
    # 2. Upload macro data chunks
    for buf_off in range(0, events_end, 10):
        chunk = bytes(buf[buf_off:buf_off+10])
        abs_off = macro_start + buf_off
        page = macro_page + (abs_off >> 8)
        off = abs_off & 0xFF
        reports.append(build_macro_chunk(page, off, chunk))
    
    # 3. Terminator
    abs_term = macro_start + term_offset
    term_page = macro_page + (abs_term >> 8)
    term_off = abs_term & 0xFF
    term_data = bytes([0x00, 0x03, term_offset & 0xFF, 0x00, 0x00, 0x00])
    reports.append(build_macro_chunk(term_page, term_off, term_data))
    
    # 4. Binding
    button_offset = BUTTON_OFFSETS.get(button, 0x60)
    reports.append(build_binding(button_offset, macro_slot, 0x01))  # Try 0x01 like Windows
    
    # 5. Commit
    reports.append(build_simple(0x04))
    
    # Send all reports
    for i, report in enumerate(reports):
        print(f"  Sending: {report.hex()}")
        try:
            device.send_feature_report(report)
            time.sleep(0.01)  # Small delay between packets
        except Exception as e:
            print(f"  Error: {e}")
            return False
    
    print(f"Macro '{name}' uploaded successfully!")
    return True


def read_flash(device, page: int, offset: int, length: int = 8) -> bytes:
    """Read data from device flash memory.
    
    Read responses come on interrupt endpoint with Report ID 0x09.
    """
    # Flush pending data
    while True:
        r = device.read(128, timeout_ms=10)
        if not r:
            break
    
    payload = bytes([0x00, page, offset, length, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    report = build_report(0x08, payload)
    
    try:
        device.send_feature_report(report)
        
        # Read response from interrupt endpoint
        start = time.time()
        while (time.time() - start) < 0.2:  # 200ms timeout
            resp = device.read(128, timeout_ms=50)
            if resp and len(resp) > 6 and resp[0] == 0x09 and resp[1] == 0x08:
                # Format: 09 08 00 [page] [offset] [len] [data...]
                if resp[3] == page and resp[4] == offset:
                    data_len = resp[5]
                    return bytes(resp[6:6+data_len])
    except Exception as e:
        pass  # Silent fail, return zeros
    
    return bytes(length)


def verify_bindings(device):
    """Read and display current button bindings."""
    print("\n=== Reading current button bindings ===")
    
    # First do handshake
    device.send_feature_report(build_simple(0x03))
    time.sleep(0.05)
    
    # Read Page 0 button region (0x60-0x9F)
    for btn in range(1, 7):
        offset = BUTTON_OFFSETS.get(btn, 0x60)
        data = read_flash(device, 0x00, offset, 4)
        btype = data[0]
        d1 = data[1]
        d2 = data[2]
        d3 = data[3]
        
        type_names = {0x01: 'Mouse', 0x04: 'Special', 0x05: 'Keyboard', 0x06: 'Macro'}
        type_name = type_names.get(btype, f'0x{btype:02X}')
        
        print(f"  Button {btn} (0x{offset:02X}): Type={type_name} D1=0x{d1:02X} D2=0x{d2:02X} D3=0x{d3:02X}")


def verify_macro_data(device, slot: int):
    """Read and display macro data from a slot."""
    print(f"\n=== Reading macro slot {slot} ===")
    
    if slot == 0:
        page = 0x03
        start = 0x00
    else:
        page = 0x03 + ((slot * 3) // 2)
        start = 0x80 if (slot % 2 != 0) else 0x00
    
    print(f"  Page 0x{page:02X}, Offset 0x{start:02X}")
    
    # Read first 32 bytes of macro data
    data = bytearray()
    for off in range(0, 32, 10):
        chunk = read_flash(device, page, start + off, 10)
        data.extend(chunk)
    
    name_len = data[0]
    event_count = data[0x1F] if len(data) > 0x1F else 0
    
    print(f"  Name length: {name_len}")
    print(f"  Event count: {event_count}")
    print(f"  First 16 bytes: {data[:16].hex()}")
    print(f"  Bytes 0x1E-0x27: {data[0x1E:0x28].hex() if len(data) > 0x27 else 'N/A'}")


def main():
    print("=== Macro Direct Upload Test ===\n")
    
    # Find and open device - try PID_MOUSE first (0xFA08), then PID_RECEIVER (0xFA07)
    device_path = None
    for pid in [PID_MOUSE, PID_RECEIVER]:
        for dev in hid.enumerate(VID, pid):
            product = dev.get("product_string", "")
            interface = dev.get("interface_number", -1)
            usage_page = dev.get("usage_page", 0)
            print(f"Found: {product} (if={interface}, page=0x{usage_page:04X})")
            # Look for the configurable interface (usually usage_page 0xFF03 or 0xFF01)
            if "Mouse" in product and usage_page in [0xFF03, 0xFF01]:
                device_path = dev["path"]
                print(f"  -> Selected this one!")
                break
        if device_path:
            break
    
    if not device_path:
        print("Device not found!")
        return
    
    device = hid.device()
    try:
        device.open_path(device_path)
        print("Device opened")
        
        # First, read current state
        print("\n=== BEFORE UPLOAD ===")
        verify_bindings(device)
        
        # Upload macro 1: LOWERCASE "oh shit! " to match Windows exactly (no shift for letters)
        upload_macro(device, "ohshit", "oh shit! ", macro_slot=0, button=1)
        
        time.sleep(0.1)
        
        # Upload macro 2: "test 1234" (lowercase, no ?)
        upload_macro(device, "test", "test 1234", macro_slot=1, button=2)
        
        time.sleep(0.2)
        
        # Read back to verify
        print("\n\n=== AFTER UPLOAD ===")
        verify_bindings(device)
        verify_macro_data(device, 0)
        verify_macro_data(device, 1)
        
        print("\n=== Done! Test button 1 and 2 ===")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        device.close()


if __name__ == "__main__":
    main()
