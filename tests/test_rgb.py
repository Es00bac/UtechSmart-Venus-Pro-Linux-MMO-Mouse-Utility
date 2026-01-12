import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import venus_protocol as vp

class TestRGB(unittest.TestCase):
    def test_build_rgb_steady_red(self):
        # Red: FF 00 00 -> Checksum (85 - 255) = -170 = 0x56
        # Payload: 00 00 54 08 [FF 00 00 56] [01 54] [B1 B2 00 00]
        # B1 for 100%: 100 * 3 = 300 -> 255 (FF). B2 = 55 - FF = 56.
        # Wait, captures showed B1=3C for 71% brightness?
        # Let's verify brightness logic too.
        # But for packet building, let's assume max brightness.
        
        pkt = vp.build_rgb(0xFF, 0x00, 0x00, vp.RGB_MODE_STEADY, 100)
        
        # Check payload (starts at byte 6)
        # Cmd bytes: 08 07 00 00 54 08
        self.assertEqual(pkt[6], 0xFF) # R
        self.assertEqual(pkt[7], 0x00) # G
        self.assertEqual(pkt[8], 0x00) # B
        self.assertEqual(pkt[9], 0x56) # Checksum
        
    def test_build_rgb_steady_magenta(self):
        # Magenta: FF 00 FF -> Checksum (85 - 510) = 0x57
        pkt = vp.build_rgb(0xFF, 0x00, 0xFF, vp.RGB_MODE_STEADY, 100)
        
        self.assertEqual(pkt[6], 0xFF) # R
        self.assertEqual(pkt[7], 0x00) # G
        self.assertEqual(pkt[8], 0xFF) # B
        self.assertEqual(pkt[9], 0x57) # Checksum

    def test_build_rgb_custom_arbitrary(self):
        # E4 00 7F -> Checksum F2
        pkt = vp.build_rgb(0xE4, 0x00, 0x7F, vp.RGB_MODE_STEADY, 100)
        self.assertEqual(pkt[9], 0xF2)

if __name__ == '__main__':
    unittest.main()
