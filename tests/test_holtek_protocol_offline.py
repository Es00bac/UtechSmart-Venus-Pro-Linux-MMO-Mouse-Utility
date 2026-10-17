"""Hardware-safe checks for confirmed Holtek profile records."""

from __future__ import annotations

import unittest

import holtek_protocol as hp


class HoltekProtocolTests(unittest.TestCase):
    def test_profile_switch_and_fire_actions_round_trip(self):
        self.assertEqual(
            hp.build_button_entry("Profile Switch", {}),
            bytes((hp.BTN_PROFILE, 0, 0, 0)),
        )
        fire = hp.build_button_entry("Fire Key", {"repeat": 7})
        self.assertEqual(fire, bytes((hp.BTN_FIRE, 7, 1, 0)))
        self.assertEqual(
            hp.button_action_to_gui(fire[0], fire[2], type_hi=fire[1]),
            ("Fire Key", {"repeat": 7}),
        )
        with self.assertRaisesRegex(ValueError, "Unsupported Holtek"):
            hp.build_button_entry("Macro", {})

    def test_dpi_packets_preserve_current_stage_and_colors(self):
        packets = hp.build_dpi_packets(
            [800, 1600, 3200], profile=2, current_stage=1,
            color_indices=[4, 5, 6])
        header = packets[0]
        self.assertEqual(
            (header[2], header[3]),
            (hp.PROFILE_BASE_ADDRS[2] & 0xFF,
             hp.PROFILE_BASE_ADDRS[2] >> 8),
        )
        self.assertEqual(header[8:12], bytes((3, 0, 1, 0)))

        entry_bytes = b"".join(
            packet[8:8 + packet[4]] for packet in packets[1:])
        self.assertEqual(
            entry_bytes,
            bytes((
                1, 4, 4, 0, 0, 0,
                1, 8, 5, 0, 0, 0,
                1, 16, 6, 0, 0, 0,
            )),
        )

    def test_dpi_packet_validation(self):
        with self.assertRaisesRegex(ValueError, "1..10"):
            hp.build_dpi_packets([])
        with self.assertRaisesRegex(ValueError, "outside"):
            hp.build_dpi_packets([800], current_stage=1)
        with self.assertRaisesRegex(ValueError, "0..4"):
            hp.build_dpi_packets([800], profile=5)

    def test_dpi_profile_reader_returns_all_metadata(self):
        base = hp.PROFILE_BASE_ADDRS[1]
        memory = bytearray(0x500)
        memory[base:base + 4] = bytes((3, 0, 2, 0))
        memory[base + 4:base + 22] = bytes((
            1, 4, 9, 0, 0, 0,
            1, 8, 8, 0, 0, 0,
            1, 16, 7, 0, 0, 0,
        ))
        device = hp.HoltekDevice(b"/dev/fake")
        device.read_memory = lambda address, length: bytes(
            memory[address:address + length])

        profile = device.read_dpi_profile(1)
        self.assertEqual(profile["stages"], [800, 1600, 3200])
        self.assertEqual(profile["colors"], [9, 8, 7])
        self.assertEqual(profile["current_stage"], 2)


class HoltekPollingTests(unittest.TestCase):
    def test_polling_is_written_per_profile_as_hid_exe_does(self):
        # hid.exe 0x410230: two F3 records at 0x32/0x38, codes 08/04/02/01.
        packets = hp.build_polling_packets([8, 4, 2, 1, 2])
        self.assertEqual(packets[0][:14], bytes.fromhex("02f33200060000000800040002 00".replace(" ", "")))
        self.assertEqual(packets[1][:12], bytes.fromhex("02f338000400000001000200"))
        self.assertEqual(hp.polling_code(1000), 0x01)
        with self.assertRaises(ValueError):
            hp.polling_code(333)

    def test_set_polling_rate_keeps_other_profiles(self):
        memory = bytearray(0x500)
        memory[hp.ADDR_POLLING:hp.ADDR_POLLING + 10] = bytes((8, 0, 4, 0, 2, 0, 1, 0, 2, 0))
        sent = []
        device = hp.HoltekDevice(b"/dev/fake")
        device.read_memory = lambda address, length: bytes(memory[address:address + length])
        device.send_feature = sent.append
        device.set_polling_rate(1000, profile=1)
        writes = [bytes(p) for p in sent if p[1] == 0xF3]
        self.assertEqual(writes[0][8:14], bytes((8, 0, 1, 0, 2, 0)))
        self.assertEqual(writes[1][8:12], bytes((1, 0, 2, 0)))
        self.assertNotIn(0xF5, [p[1] for p in sent])


if __name__ == "__main__":
    unittest.main()
