from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import unittest
import venus_protocol as vp
import time

class TestHardware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        devs = vp.list_devices()
        if not devs:
            raise unittest.SkipTest("No mouse found")
        # Target Interface 1
        cls.target = next((d for d in devs if d.interface_number == 1), devs[0])
        print(f"Testing on {cls.target.path}")

    def test_read_flash_header(self):
        mouse = vp.VenusDevice(self.target.path)
        mouse.open()
        try:
            # Read Macro 1 Header (Page 3, Offset 0)
            data = mouse.read_flash(0x03, 0x00, 8)
            self.assertEqual(len(data), 8)
            # Should have non-zero name length or events if initialized
            print(f"Macro Header: {data.hex()}")
        finally:
            mouse.close()

    def test_reliable_handshake(self):
        mouse = vp.VenusDevice(self.target.path)
        mouse.open()
        try:
            # Try a simple 'Prepare' command with reliable handshake
            success = mouse.send_reliable(vp.build_simple(0x04))
            self.assertTrue(success, "Reliable handshake (0x04) failed")
        finally:
            mouse.close()

if __name__ == '__main__':
    unittest.main()
