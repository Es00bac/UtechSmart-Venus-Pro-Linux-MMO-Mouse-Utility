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

    def test_issue_27_profile_step_and_shortcut_records(self):
        # Factory records from issue #27, named by the vendor utility's table.
        for record, binding in (
            ((0x94, 0, 0, 0), ("Profile Up", {})),
            ((0x95, 0, 0, 0), ("Profile Down", {})),
            ((0x8F, 0x01, 0x1B, 0), ("Keyboard Key", {"key": 0x1B, "mod": 0x01})),  # Cut
            ((0x8F, 0x01, 0x09, 0), ("Keyboard Key", {"key": 0x09, "mod": 0x01})),  # Find
            ((0x8F, 0x08, 0x0F, 0), ("Keyboard Key", {"key": 0x0F, "mod": 0x08})),  # Win+L
        ):
            with self.subTest(record=bytes(record).hex()):
                self.assertEqual(
                    hp.button_action_to_gui(record[0], record[2], type_hi=record[1]),
                    binding)
                self.assertEqual(hp.build_button_entry(*binding), bytes(record))
        self.assertEqual(
            hp.build_button_entry("Keyboard Key", {"key": 0x04, "mod": 0}),
            bytes((hp.BTN_KEYBOARD, 0, 0x04, 0)))
        parsed = hp.parse_button_map(bytes((2, 0, 0x94, 0, 0, 0, 0x8F, 1, 0x06, 0)))
        self.assertEqual([entry["action"] for entry in parsed],
                         ["Profile Up", "Keyboard Key"])

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


if __name__ == "__main__":
    unittest.main()
