from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


def check_sum():
    # Packet 134: Cmd 4D
    # 08 4D 05 50 00 55 00 55 00 55 91 1B 00 60 B5 3E 8E
    pkt1 = [0x08, 0x4D, 0x05, 0x50, 0x00, 0x55, 0x00, 0x55, 
            0x00, 0x55, 0x91, 0x1B, 0x00, 0x60, 0xB5, 0x3E, 0x8E]
            
    s1 = sum(pkt1[:16])
    chk1 = pkt1[16]
    print(f"Cmd 4D: Sum={s1:X} Chk={chk1:X} Sum+Chk={(s1+chk1):X} (Expected x55 or matching Base)")

    # Packet 205: Cmd 01
    # 08 01 46 06 09 F5 1B 00 60 B5 3E 8E 86 84 FF FF 00
    pkt2 = [0x08, 0x01, 0x46, 0x06, 0x09, 0xF5, 0x1B, 0x00, 
            0x60, 0xB5, 0x3E, 0x8E, 0x86, 0x84, 0xFF, 0xFF, 0x00]
            
    s2 = sum(pkt2[:16])
    chk2 = pkt2[16]
    print(f"Cmd 01: Sum={s2:X} Chk={chk2:X} Sum+Chk={(s2+chk2):X}")

if __name__ == "__main__":
    check_sum()
