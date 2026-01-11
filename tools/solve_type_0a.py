from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


def solve_0a():
    # Samples: [Type, D1, D2, TargetD3]
    samples = [
        [0x0A, 0x00, 0x03, 0x41], # Polling 125Hz?
        [0x0A, 0x00, 0x7D, 0x81], # Debounce 125ms? (Offset 07)
    ]
    
    print("Solving specific Type 0x0A checksums...")
    
    # Try linear combinations: K - Sum?
    # Tgt = K - (T+D1+D2)
    # K = Tgt + Sum
    
    k_vals = set()
    for s in samples:
        t, d1, d2, tgt = s
        s_sum = (t + d1 + d2) & 0xFF
        k = (tgt + s_sum) & 0xFF
        k_vals.add(k)
        print(f"Sample {s}: Sum={s_sum:02X} Target={tgt:02X} -> K={k:02X}")
        
    if len(k_vals) == 1:
        print(f"MATCH! Formula is: D3 = (0x{list(k_vals)[0]:02X} - Sum) & 0xFF")
        return

    # Try XOR
    # Tgt = K ^ XOR_SUM
    k_vals = set()
    for s in samples:
        t, d1, d2, tgt = s
        x_sum = t ^ d1 ^ d2
        k = tgt ^ x_sum
        k_vals.add(k)
        print(f"Sample {s}: Xor={x_sum:02X} Target={tgt:02X} -> K={k:02X}")

    if len(k_vals) == 1:
        print(f"MATCH! Formula is: D3 = 0x{list(k_vals)[0]:02X} ^ XorSum")
        return
        
if __name__ == "__main__":
    solve_0a()
