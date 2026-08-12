"""Offline regression tests backed by captures and the vendor converter."""

from __future__ import annotations

import random
import unittest
from unittest import mock

import venus_protocol as vp


def response_for(request: bytes, data: bytes = b"") -> bytes:
    response = bytearray(request)
    response[0] = vp.RESPONSE_REPORT_ID
    if data:
        response[5] = len(data)
        response[6:16] = data.ljust(10, b"\x00")
    response[16] = vp.calc_checksum(response[:16])
    return bytes(response)


class FakeHandle:
    def __init__(self):
        self.pending = []
        self.commands = []
        self.status_data = b"\x07\x00"

    def set_nonblocking(self, value):
        pass

    def send_feature_report(self, request):
        request = bytes(request)
        self.commands.append(request[1])
        command = request[1]
        if command == vp.CMD_READY:
            data = b"\x01"
        elif command == vp.CMD_CHALLENGE:
            data = vp.challenge_response(request[6:10])
        elif command == vp.CMD_NOTIFY:
            data = b"\x01"
        elif command == vp.CMD_STATUS:
            data = self.status_data
        elif command == vp.CMD_READ:
            data = bytes(request[5])
        else:
            data = b""
        self.pending.append(response_for(request, data))
        return len(request)

    def read(self, length, timeout_ms=0):
        return list(self.pending.pop(0)) if self.pending else []

    def close(self):
        pass


class ProtocolBuilderTests(unittest.TestCase):
    def test_packet_checksum_invariant(self):
        packets = [
            vp.build_simple(vp.CMD_READY),
            vp.build_memory_write(0x0060, b"\x01\x01\x00\x53"),
            vp.build_flash_read(0x12, 0x34, 10),
        ]
        self.assertTrue(all(len(packet) == 17 for packet in packets))
        self.assertTrue(all(vp.report_checksum_valid(packet) for packet in packets))
        with self.assertRaises(ValueError):
            vp.build_report(vp.CMD_READY, bytes(15))

    def test_challenge_formula_matches_independent_captures(self):
        pairs = {
            "15251e09": "3f686339",
            "56573d1b": "b2ebd2c2",
            "57605d4d": "bc1d648b",
            "211f3553": "4573f26d",
            "64282615": "917687b8",
        }
        for challenge, expected in pairs.items():
            self.assertEqual(vp.challenge_response(bytes.fromhex(challenge)).hex(), expected)

    def test_mouse_action_records_match_capture(self):
        expected = {
            0x01: "01010053",
            0x02: "01020052",
            0x04: "01040050",
            0x08: "0108004c",
            0x10: "01100044",
        }
        for mask, record in expected.items():
            packet = vp.build_mouse_param(0x60, mask)
            self.assertEqual(packet[6:10].hex(), record)

    def test_multi_modifier_definition_matches_capture(self):
        packets = vp.build_key_binding(
            0x01, 0x00, 0x1E, vp.MODIFIER_CTRL | vp.MODIFIER_SHIFT)
        body = b"".join(packet[6:6 + packet[5]] for packet in packets)
        self.assertEqual(
            body.hex(),
            "06800100800200811e00400100400200411e00cb",
        )
        self.assertEqual(sum(body) & 0xFF, 0x55)

    def test_consumer_definition_is_16_bit(self):
        packets = vp.build_consumer_binding(1, 0, 0x0183)
        body = b"".join(packet[6:6 + packet[5]] for packet in packets)
        self.assertEqual(body[:7], bytes.fromhex("02828301428301"))
        self.assertEqual(sum(body) & 0xFF, 0x55)

    def test_polling_codes(self):
        self.assertEqual(vp.POLLING_RATE_CODES,
                         {125: 0x08, 250: 0x04, 500: 0x02, 1000: 0x01})
        for rate, code in vp.POLLING_RATE_CODES.items():
            self.assertEqual(vp.POLLING_RATE_PAYLOADS[rate][4:6],
                             bytes((code, (0x55 - code) & 0xFF)))

    def test_dpi_stage_count_record(self):
        packet = vp.build_dpi_stage_count(5)
        self.assertEqual(packet[3:6], bytes((0x00, 0x02, 0x02)))
        self.assertEqual(packet[6:8], bytes((0x05, 0x50)))
        self.assertTrue(vp.report_checksum_valid(packet))
        with self.assertRaisesRegex(ValueError, "1..8"):
            vp.build_dpi_stage_count(0)

    def test_battery_led_gradient_uses_low_mixed_color_brightness(self):
        self.assertEqual(vp.battery_gradient_rgb(0), (255, 0, 0))
        self.assertEqual(vp.battery_gradient_rgb(25), (255, 128, 0))
        self.assertEqual(vp.battery_gradient_rgb(50), (255, 255, 0))
        self.assertEqual(vp.battery_gradient_rgb(75), (128, 255, 0))
        self.assertEqual(vp.battery_gradient_rgb(100), (0, 255, 0))

        packet = vp.build_battery_indicator_rgb(60)
        self.assertEqual(packet[6:9], bytes((204, 255, 0)))
        self.assertEqual(packet[10], vp.RGB_MODE_STEADY)
        self.assertEqual(packet[12:14], b"\x1e\x37")
        self.assertTrue(vp.report_checksum_valid(packet))
        self.assertEqual(
            vp.build_battery_indicator_rgb(0)[6:14],
            bytes.fromhex("ff00005601541e37"),
        )

    def test_macro_mouse_events_and_checksum(self):
        down = vp.MacroEvent.mouse(0x01, True, 50)
        up = vp.MacroEvent.mouse(0x01, False, 3)
        self.assertEqual(down.to_bytes(), bytes.fromhex("8401000032"))
        self.assertEqual(up.to_bytes(), bytes.fromhex("4401000003"))
        events = down.to_bytes() + up.to_bytes()
        header = bytes(31) + b"\x02"
        checksum = vp.calculate_terminator_checksum(header + events, 2)
        self.assertEqual((2 + sum(events) + checksum) & 0xFF, 0x55)

    def test_text_macro_uses_captured_shift_order_and_timing(self):
        self.assertEqual(vp.text_macro_requirements("aA!"), (10, ()))
        events = vp.build_text_macro_events(
            "aA!", key_hold_ms=35, delay_min_ms=80)

        self.assertEqual(len(events), 10)
        self.assertEqual(
            [event.to_bytes().hex() for event in events],
            [
                "8104000023", "4104000050",
                "8020000003", "8104000023",
                "4020000003", "4104000050",
                "8020000003", "811e000023",
                "4020000003", "411e000003",
            ],
        )
        self.assertEqual(vp.macro_events_to_text(events), "aA!")

    def test_text_macro_random_delays_are_bounded_and_repeatable(self):
        first = vp.build_text_macro_events(
            "a b", delay_min_ms=70, delay_max_ms=90,
            extra_word_pause_ms=50, rng=random.Random(7))
        second = vp.build_text_macro_events(
            "a b", delay_min_ms=70, delay_max_ms=90,
            extra_word_pause_ms=50, rng=random.Random(7))

        self.assertEqual(first, second)
        release_delays = [first[index].delay_ms for index in (1, 3, 5)]
        self.assertTrue(70 <= release_delays[0] <= 90)
        self.assertTrue(120 <= release_delays[1] <= 140)
        self.assertEqual(release_delays[2], vp.MACRO_MIN_DELAY_MS)

    def test_text_macro_rejects_unsupported_and_oversized_text(self):
        self.assertEqual(
            vp.text_macro_requirements("a\N{SNOWMAN}a"),
            (4, ("\N{SNOWMAN}",)),
        )
        with self.assertRaisesRegex(ValueError, "unsupported"):
            vp.build_text_macro_events("snow \N{SNOWMAN}")
        with self.assertRaisesRegex(ValueError, "70 events"):
            vp.build_text_macro_events("a" * 35)

    def test_macro_slot_addresses_use_0x180_stride(self):
        self.assertEqual(vp.get_macro_slot_info(0), (0x03, 0x00))
        self.assertEqual(vp.get_macro_slot_info(1), (0x04, 0x80))
        self.assertEqual(vp.get_macro_slot_info(2), (0x06, 0x00))
        self.assertEqual(vp.get_macro_slot_info(15), (0x19, 0x80))
        with self.assertRaises(ValueError):
            vp.get_macro_slot_info(16)

    def test_maximum_macro_image_stays_inside_its_slot(self):
        events = [vp.MacroEvent(0x04, True, 3)] * vp.MACRO_MAX_EVENTS
        image = vp.build_macro_image("A\U0001f600B", events)
        self.assertEqual(len(image), 381)
        self.assertLessEqual(len(image), vp.MACRO_SLOT_SIZE)
        # The astral character occupies two UTF-16 code units, but the stored
        # name length must still describe exactly the bytes in the header.
        self.assertEqual(image[0], 8)
        self.assertEqual(image[0x1F], 69)
        terminator_offset = vp.MACRO_HEADER_SIZE + len(events) * 5
        self.assertEqual(
            image[terminator_offset],
            vp.calculate_terminator_checksum(image, len(events)),
        )
        with self.assertRaisesRegex(ValueError, "at most 69"):
            vp.build_macro_image("too many", events + events[:1])


class DeviceTests(unittest.TestCase):
    def test_status_and_safe_unlock_alias(self):
        handle = FakeHandle()
        device = vp.VenusDevice(b"/dev/fake")
        device._dev = handle
        status = device.query_status()
        self.assertEqual((status.level, status.percent, status.cable_connected),
                         (7, 70, False))
        self.assertTrue(device.unlock())
        self.assertNotIn(vp.CMD_FACTORY_RESET, handle.commands)

    def test_status_rejects_out_of_range_battery_steps(self):
        handle = FakeHandle()
        handle.status_data = b"\xff\x00"
        device = vp.VenusDevice(b"/dev/fake")
        device._dev = handle
        with self.assertRaisesRegex(vp.ProtocolError, "battery step"):
            device.query_status()

    def test_reliable_sequences_leave_the_captured_firmware_gap(self):
        handle = FakeHandle()
        device = vp.VenusDevice(b"/dev/fake")
        device._dev = handle
        with mock.patch.object(vp.time, "sleep") as sleep:
            self.assertTrue(
                device.send_reliable(vp.build_simple(vp.CMD_READY)))
            sleep.assert_called_once_with(vp.REPORT_SETTLE_SECONDS)

            sleep.reset_mock()
            self.assertTrue(device.begin_write())
            sleep.assert_called_once_with(vp.REPORT_SETTLE_SECONDS)

    def test_enumeration_selects_real_config_interface(self):
        entries = [
            {"vendor_id": 0x25A7, "product_id": 0xFA08,
             "path": b"/dev/hidraw-mouse", "interface_number": 0,
             "product_string": "Venus Pro"},
            {"vendor_id": 0x25A7, "product_id": 0xFA08,
             "path": b"/dev/hidraw-config", "interface_number": 1,
             "usage_page": 0x0001, "usage": 0x0006,
             "product_string": "Venus Pro"},
            # hidapi enumerates every top-level collection separately, often
            # with the same hidraw path. Prefer the actual vendor collection.
            {"vendor_id": 0x25A7, "product_id": 0xFA08,
             "path": b"/dev/hidraw-config", "interface_number": 1,
             "usage_page": 0xFF02, "product_string": "Venus Pro"},
        ]

        fake_hid = mock.Mock()
        fake_hid.enumerate.side_effect = lambda vid, pid: (
            entries if (vid, pid) == (0x25A7, 0xFA08) else [])
        fake_handle = mock.Mock()
        fake_hid.device.return_value = fake_handle
        with mock.patch.object(vp, "hid", fake_hid), \
             mock.patch.object(vp, "HIDAPI_AVAILABLE", True):
            devices = vp.list_devices()

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].path, b"/dev/hidraw-config")
        self.assertEqual(devices[0].usage_page, 0xFF02)
        fake_handle.open_path.assert_called_with(b"/dev/hidraw-config")


if __name__ == "__main__":
    unittest.main()
