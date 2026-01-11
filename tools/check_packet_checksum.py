from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


def check_sum():
    # Packets from trace (Hex strings)
    packets = [
        "09070003000a18730069006d0070006cfb",
        "090700030a0a0065005f006d0061006339",
        "09070003140a0072006f00000000000043",
        "090700031e0a0002811e000003411e0017",
        "09070003280600034f00000000000000c2",
        "0907000060040600014e0000000000008c"
    ]
    
    for i, p_hex in enumerate(packets):
        data = bytes.fromhex(p_hex)
        # Checksum is last byte
        pkt_chk = data[-1]
        
        # Calculate standard 0x55 checksum on bytes 0..15
        payload = data[:-1]
        s_sum = sum(payload) & 0xFF
        calc_chk = (0x55 - s_sum) & 0xFF
        
        match = (calc_chk == pkt_chk)
        print(f"Pkt {i}: {p_hex}")
        print(f"  Sum: {s_sum:02X} | Calc: {calc_chk:02X} | Pkt: {pkt_chk:02X} | Match: {match}")
        
if __name__ == "__main__":
    check_sum()
