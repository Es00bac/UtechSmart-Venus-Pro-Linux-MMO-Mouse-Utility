from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


def solve_name_checksum():
    # Payload: 0A 06 31 00 32 00 33 00 00 00 00
    # Target: 9D
    
    data = [0x0A, 0x06, 0x31, 0x00, 0x32, 0x00, 0x33, 0x00, 0x00, 0x00, 0x00]
    target = 0x9D
    
    s_sum = sum(data) & 0xFF
    # Sum is A6.
    
    print(f"Sum: {s_sum:02X}, Target: {target:02X}")
    
    # Try K - Sum
    # K = Tgt + Sum = 9D + A6 = 143 = 43
    print(f"K - Sum: K would be 0x{(target + s_sum) & 0xFF:02X}")
    
    # Try XOR
    xor_sum = 0
    for b in data: xor_sum ^= b
    # XOR Sum ??
    print(f"XOR Sum: {xor_sum:02X}")
    print(f"XOR K: 0x{(target ^ xor_sum):02X}")
    
    # Try CRC8?
    
if __name__ == "__main__":
    solve_name_checksum()
