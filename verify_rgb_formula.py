def verify_formula():
    # R, G, B, Mode(Chk)
    samples = [
        (0xFF, 0x00, 0xFF, 0x57),
        (0xFF, 0x00, 0x00, 0x56),
        (0xE4, 0x00, 0x7F, 0xF2),
        (0xE8, 0x38, 0x28, 0x0D),
        (0xF3, 0x98, 0x00, 0xCA),
        (0x00, 0x00, 0xFF, 0x56),
    ]
    
    print("Verifying RGB Formula: Checksum = (0x55 - (R+G+B)) & 0xFF")
    
    for r, g, b, chk in samples:
        calc = (0x55 - (r + g + b)) & 0xFF
        status = "PASS" if calc == chk else "FAIL"
        print(f"RGB {r:02X} {g:02X} {b:02X} | Target: {chk:02X} | Calc: {calc:02X} -> {status}")

if __name__ == "__main__":
    verify_formula()
