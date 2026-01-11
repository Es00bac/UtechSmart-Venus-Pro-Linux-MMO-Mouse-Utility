from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import unittest
import venus_protocol as vp

class TestProtocol(unittest.TestCase):
    def test_packet_checksum(self):
        # Cmd 04 (Prepare)
        # 08 04 ... (total 16 bytes)
        # Sum = 0x0C (8+4)
        # Checksum = 0x55 - 0x0C = 0x49
        pkt = vp.build_simple(0x04)
        self.assertEqual(pkt[16], 0x49)
        
    def test_macro_terminator_checksum(self):
        # Formula: (~sum(events) - event_count + 0x56) & 0xFF
        events = bytes([0x81, 0x04, 0x00, 0x00, 0x03, 0x41, 0x04, 0x00, 0x00, 0x03])
        data = bytes(0x20) + events
        chk = vp.calculate_terminator_checksum(data, event_count=2)
        self.assertEqual(chk, 0x83)
        
    def test_macro_bind_packet(self):
        # Type 0x06, Slot 0, Once (0x01)
        # Internal Chk = 0x55 - (6 + 0 + 1) = 0x4E
        pkt = vp.build_macro_bind(0x60, 0, 1)
        # Payload starts at pkt[6] (D0=Len, D1=Type, D2=Slot, D3=Mode, D4=Chk)
        # Wait, check build_flash_write: payload = [0x00, page, offset, len, data...]
        # data = [btype, index, repeat, chk, ...]
        # pkt[0]=0x08, pkt[1]=0x07, pkt[2]=0x00, pkt[3]=0x00, pkt[4]=0x60, pkt[5]=0x08
        # pkt[6]=0x06, pkt[7]=0x00, pkt[8]=0x01, pkt[9]=0x4E
        self.assertEqual(pkt[9], 0x4E)

if __name__ == '__main__':
    unittest.main()
