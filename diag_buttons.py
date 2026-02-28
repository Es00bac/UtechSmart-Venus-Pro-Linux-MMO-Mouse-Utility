#!/usr/bin/env python3
"""Diagnostic: dump all 20 button entries from the Holtek device.

Run with: python3 diag_buttons.py

Shows the raw 4-byte entry at each memory index so we can verify
which physical button corresponds to which firmware slot.
"""
import holtek_protocol as hp

BUTTON_TYPE_NAMES = {
    0x00: "Disabled",
    0x81: "LMB",
    0x82: "RMB",
    0x83: "MMB",
    0x84: "Back",
    0x85: "Forward",
    0x8A: "DPI Up",
    0x8C: "DPI Down",
    0x8D: "Profile Switch",
    0x90: "Keyboard Key",
}

# HID key names for common scancodes
HID_KEY_NAMES = {
    0x04: "A", 0x05: "B", 0x06: "C", 0x07: "D", 0x08: "E", 0x09: "F",
    0x0A: "G", 0x0B: "H", 0x0C: "I", 0x0D: "J", 0x0E: "K", 0x0F: "L",
    0x10: "M", 0x11: "N", 0x12: "O", 0x13: "P", 0x14: "Q", 0x15: "R",
    0x16: "S", 0x17: "T", 0x18: "U", 0x19: "V", 0x1A: "W", 0x1B: "X",
    0x1C: "Y", 0x1D: "Z",
    0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4", 0x22: "5",
    0x23: "6", 0x24: "7", 0x25: "8", 0x26: "9", 0x27: "0",
    0x28: "Enter", 0x29: "Escape", 0x2A: "Backspace", 0x2B: "Tab",
    0x2C: "Space",
    0x3A: "F1", 0x3B: "F2", 0x3C: "F3", 0x3D: "F4", 0x3E: "F5",
    0x3F: "F6", 0x40: "F7", 0x41: "F8", 0x42: "F9", 0x43: "F10",
    0x44: "F11", 0x45: "F12",
    0x56: "Numpad -", 0x57: "Numpad +",
    0x59: "Numpad 1", 0x5A: "Numpad 2", 0x5B: "Numpad 3",
    0x5C: "Numpad 4", 0x5D: "Numpad 5", 0x5E: "Numpad 6",
    0x5F: "Numpad 7", 0x60: "Numpad 8", 0x61: "Numpad 9",
    0x62: "Numpad 0",
}

def describe_entry(raw: bytes) -> str:
    """Human-readable description of a 4-byte button entry."""
    type_lo, type_hi, code_lo, code_hi = raw
    type_name = BUTTON_TYPE_NAMES.get(type_lo, f"0x{type_lo:02X}")
    if type_lo == 0x90:  # Keyboard
        key_name = HID_KEY_NAMES.get(code_lo, f"0x{code_lo:02X}")
        return f"Keyboard: {key_name} (HID 0x{code_lo:02X})"
    elif type_lo in (0x81, 0x82, 0x83, 0x84, 0x85, 0x8A, 0x8C, 0x8D):
        return type_name
    elif type_lo == 0x00:
        return "Disabled"
    else:
        return f"type=0x{type_lo:02X} hi=0x{type_hi:02X} code=0x{code_lo:02X} code_hi=0x{code_hi:02X}"


def main():
    import venus_protocol as vp

    infos = vp.list_devices()
    holtek = [i for i in infos if i.vendor_id == 0x04D9 and i.product_id == 0xFC55]
    if not holtek:
        print("No Holtek device found!")
        return

    info = holtek[0]
    print(f"Device: {info.product} at {info.path}")
    print()

    dev = hp.HoltekDevice(info.path)
    dev.open()

    try:
        profile = dev.read_active_profile()
        print(f"Active profile: {profile}")
        print()

        for prof in range(5):
            btn_base = hp.ADDR_BUTTONS_PROFILE[prof]
            btn_end = btn_base + 2 + 20 * 4

            # Read button data
            button_data = bytearray()
            for addr in range(btn_base, btn_end, 8):
                chunk_len = min(8, btn_end - addr)
                chunk = dev.read_memory(addr, chunk_len)
                button_data.extend(chunk)

            count = button_data[0] | (button_data[1] << 8)
            print(f"=== Profile {prof} (base=0x{btn_base:04X}, count={count}) ===")

            # Current BUTTON_PROFILES mapping for reference
            current_map = {}
            for key, bp in hp.BUTTON_PROFILES.items():
                current_map[bp.index] = bp.label

            for i in range(min(count, 20)):
                offset = 2 + (i * 4)
                raw = button_data[offset:offset + 4]
                desc = describe_entry(raw)
                cur_label = current_map.get(i, "(not in BUTTON_PROFILES)")
                print(f"  Index {i:2d}  [{raw[0]:02X} {raw[1]:02X} {raw[2]:02X} {raw[3]:02X}]  "
                      f"{desc:30s}  currently mapped as: {cur_label}")
            print()

            if prof == profile:
                print("  ^^^ This is the ACTIVE profile ^^^")
                print()
    finally:
        dev.close()


if __name__ == "__main__":
    main()
