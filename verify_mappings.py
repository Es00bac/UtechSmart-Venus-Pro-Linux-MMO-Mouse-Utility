import venus_protocol as vp

# Expected values from win.md calculations
# Format: (code_hi, code_lo, apply_offset)
EXPECTED = {
    "Button 1": (0x01, 0x00, 0x60),  # Index 0
    "Button 2": (0x01, 0x20, 0x64),  # Index 1
    "Button 7": (0x02, 0x00, 0x80),  # Index 8
    "Button 8": (0x02, 0x20, 0x84),  # Index 9
    "Button 9": (0x02, 0x80, 0x90),  # Index 12
    "Button 10": (0x02, 0xA0, 0x94), # Index 13
    "Button 11": (0x02, 0xC0, 0x98), # Index 14
    "Button 12": (0x02, 0xE0, 0x9C), # Index 15
    "Button 13": (0x02, 0x60, 0x8C), # Index 11
    "Button 14": (0x02, 0x40, 0x88), # Index 10
    "Button 15": (0x03, 0x00, 0xA0), # Index 16
    "Button 16": (0x03, 0x20, 0xA4), # Index 17
}

def verify():
    failed = False
    for btn_name, expected in EXPECTED.items():
        if btn_name not in vp.BUTTON_PROFILES:
            print(f"FAIL: {btn_name} not found in BUTTON_PROFILES")
            failed = True
            continue
            
        profile = vp.BUTTON_PROFILES[btn_name]
        actual = (profile.code_hi, profile.code_lo, profile.apply_offset)
        
        if actual != expected:
            print(f"FAIL: {btn_name}")
            print(f"  Expected: {expected}")
            print(f"  Actual:   {actual}")
            failed = True
        else:
            print(f"PASS: {btn_name}")

    if not failed:
        print("\nAll checks PASSED")
    else:
        print("\nSome checks FAILED")
        exit(1)

if __name__ == "__main__":
    verify()
