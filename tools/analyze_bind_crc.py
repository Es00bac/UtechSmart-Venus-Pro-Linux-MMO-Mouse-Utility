from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


def analyze_bind_crc():
    # Packet from artifacts/txt/host_mouse_communication.txt line 8426
    # 08 07 00 00 78 0A 06 07 01 00 00 00 00 00 F4 00 00
    pkt = [0x08, 0x07, 0x00, 0x00, 0x78, 0x0A, 0x06, 0x07, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF4, 0x00, 0x00]
    
    # Payload Bytes for Checksum (0-15? or just payload?)
    # Usually bytes 0-15. Checksum at 16.
    # Note: host_mouse_communication format might include timestamp/etc?
    # Assuming standard 17-byte report.
    # Byte 14 is F4?
    # 08(0) 07(1) 00(2) 00(3) 78(4) 0A(5) 06(6) 07(7) 01(8) 00(9) 00(10) 00(11) 00(12) 00(13) F4(14??)
    # Wait. Report len is 17?
    # 0,1,2,3,4,5,6,7,8,9,10,11,12,13.
    # Byte 14 is the 15th byte.
    # Byte 16 is 17th.
    # My build_report puts checksum at index 16.
    # But packet above has F4 at index 14.
    # Is the packet shorter?
    # 08 07 00 00 78 0A [06 07 01 00 00 00 00 00] (8 byte payload?)
    # 8+6 = 14 bytes used?
    # Header: 08 07 00 00 78 0A (6 bytes).
    # Payload: 06 07 01 00 00 00 00 00 (8 bytes).
    # Total 14 bytes.
    # Checksum at 14? (15th byte)
    # 08(0)... 00(13). F4(14).
    # build_report puts it at 16.
    
    # If standard drivers assume 17 byte packets but send short ones?
    # Or maybe I should put Checksum at `Len + Header`?
    # 6+8 = 14. So Index 14.
    # Let's check Sum(0..13) + F4.
    
    data = pkt[:14] # 0..13
    chk = pkt[14]
    
    s = sum(data)
    print(f"Sum(0-13): {s:X}")
    print(f"Chk: {chk:X}")
    print(f"Sum+Chk: {(s+chk):X}")
    
    # Test Base 55
    # (55 - S) & FF
    calc55 = (0x55 - s) & 0xFF
    print(f"Expected Chk (Base 55): {calc55:X}")
    
if __name__ == "__main__":
    analyze_bind_crc()
