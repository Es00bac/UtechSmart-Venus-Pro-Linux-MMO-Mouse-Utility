from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


def solve_rgb():
    # Packet Sample 1: FF 00 FF 57 01 54 3C 19 00 00 -> EB (Checksum)
    # R=FF, G=00, B=FF. Mode=01 (Steady?).
    
    # Packet Sample 2 (from log above):
    # FF 00 FF 57 01 54 01 54 00 00 -> EB (Same checksum?)
    # Wait, payload changed! 3C 19 -> 01 54.
    # But checksum is still EB??
    # If checksum is EB, and payload changed, but sum matches?
    # 3C+19 = 55.
    # 01+54 = 55.
    # Sum is invariant!
    
    samples = [
        # Payload (after 08 07 00 00 54 08) -> Checksum
        ([0xFF, 0x00, 0xFF, 0x57, 0x01, 0x54, 0x3C, 0x19, 0x00, 0x00], 0xEB),
        ([0xFF, 0x00, 0xFF, 0x57, 0x01, 0x54, 0x01, 0x54, 0x00, 0x00], 0xEB),
        ([0xFF, 0x00, 0xFF, 0x57, 0x01, 0x54, 0x1E, 0x37, 0x00, 0x00], 0xEB), 
        ([0xFF, 0x00, 0xFF, 0x57, 0x01, 0x54, 0x5A, 0xFB, 0x00, 0x00], 0xEB),
        ([0xFF, 0x00, 0xFF, 0x57, 0x01, 0x54, 0x80, 0xD5, 0x00, 0x00], 0xEB),
    ]
    
    print("Solving RGB Checksum...")
    
    for i, (data, tgt) in enumerate(samples):
        s_sum = sum(data) & 0xFF
        # K = Tgt + Sum
        k = (tgt + s_sum) & 0xFF
        print(f"Sample {i}: Sum={s_sum:02X} Target={tgt:02X} -> K={k:02X}")
        
    # Analyze Payload Changes
    # Bytes 6 and 7 are changing.
    # 3C 19 -> Sum 55
    # 01 54 -> Sum 55
    # 1E 37 -> Sum 55
    # 5A FB -> Sum 55 (90 + 251 = 341 = 0x155? No. 5A=90. FB=251. 341&FF = 55. YES)
    # 80 D5 -> Sum 55 (128 + 213 = 341 = 55).
    
    # CONCLUSION: Bytes 6 and 7 are COMPLEMENTARY so their sum is constant!
    # Byte 7 = 0x55 - Byte 6?
    # 19 = 25. 55 - 60 (3C) = negative.
    # Let's check: 0x55 - 0x3C = 0x19. MATCH!
    # 0x55 - 0x01 = 0x54. MATCH!
    # 0x55 - 0x1E = 0x37. MATCH!
    
    # What is Byte 6?
    # 3C = 60
    # 01 = 1
    # 1E = 30
    # 5A = 90
    # 80 = 128
    
    # Is it Brightness?
    # Log says "Brightness: 71%".
    # 128/255 = 50%?
    # 60/100?
    
    print("\nByte 6/7 Analysis: Byte 7 seems to be (0x55 - Byte 6).")

if __name__ == "__main__":
    solve_rgb()
