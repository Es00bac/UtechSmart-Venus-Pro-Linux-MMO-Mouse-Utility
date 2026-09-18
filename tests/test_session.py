"""Offline checks for the UI-independent device session."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import holtek_protocol as hp  # noqa: E402
import venus_protocol as vp  # noqa: E402
import venus_session as vs  # noqa: E402
from venus_macro_draft import MacroDraft  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DUMP = REPO / "dumps" / "dump_1767830656"


class ParserTests(unittest.TestCase):
    def test_real_dump_decodes_like_the_widgets_window(self):
        page0 = (DUMP / "page_00.bin").read_bytes()
        page1 = (DUMP / "page_01.bin").read_bytes()
        config = vs.parse_areson_config(page0, page1, bytes(256))
        self.assertEqual(config.dpi_stage_count, 5)
        self.assertEqual([stage.dpi for stage in config.dpi_stages],
                         [1000, 2000, 4000, 8000, 10000])
        self.assertTrue(all(stage.preset for stage in config.dpi_stages))
        self.assertEqual(config.polling_rate, 125)
        self.assertEqual((config.rgb.r, config.rgb.g, config.rgb.b), (255, 0, 255))
        self.assertEqual(config.rgb.mode, vp.rgb_mode_from_hardware(page0[0x58]))
        self.assertEqual(config.buttons["Button 14"]["action"], "Left Click")
        self.assertEqual(config.buttons["Button 16"]["action"], "Right Click")
        self.assertEqual(config.buttons["Button 13"],
                         {"action": "Fire Key", "params": {"delay": 20, "repeat": 3}})
        self.assertEqual(config.buttons["Button 2"]["action"], "Keyboard Key")
        self.assertEqual(config.buttons["Button 2"]["params"]["key"], vp.HID_KEY_USAGE["2"])
        # Page 2 was not read for this dump, so its definitions are invalid.
        self.assertEqual(config.buttons["Button 7"]["action"], "Invalid Key Definition")

    def test_parser_decodes_every_button_type(self):
        page0 = bytearray(0xA0)
        page0[0x02] = 3
        page0[0x00] = vp.POLLING_RATE_CODES[500]
        page0[0x54:0x57] = bytes((1, 2, 3))
        page0[0x58] = vp.rgb_mode_to_hardware(vp.RGB_MODE_BREATHING)
        page0[0x5A] = 0xFF
        page0[0x5C] = 9
        profiles = vp.BUTTON_PROFILES
        page0[profiles["Button 1"].apply_offset:profiles["Button 1"].apply_offset + 3] = (0x01, 0x10, 0)
        page0[profiles["Button 2"].apply_offset:profiles["Button 2"].apply_offset + 3] = (0x02, 0x03, 0)
        page0[profiles["Button 3"].apply_offset:profiles["Button 3"].apply_offset + 3] = (0x06, 0x04, 0xFE)
        page0[profiles["Button 4"].apply_offset:profiles["Button 4"].apply_offset + 3] = (0x04, 50, 3)
        page0[profiles["Button 5"].apply_offset:profiles["Button 5"].apply_offset + 3] = (0x07, 0, 0)
        page0[profiles["Button 6"].apply_offset:profiles["Button 6"].apply_offset + 3] = (0x08, 0, 0)
        page0[profiles["Button 7"].apply_offset:profiles["Button 7"].apply_offset + 3] = (0x05, 0, 0)
        page1 = bytearray(256)
        page2 = bytearray(256)
        media_block = bytes((1, 0x82, 0xCD, 0x00))
        media_block += bytes(((0x55 - sum(media_block)) & 0xFF,))
        code_lo = profiles["Button 7"].code_lo
        page2[code_lo:code_lo + len(media_block)] = media_block

        config = vs.parse_areson_config(bytes(page0), bytes(page1), bytes(page2),
                                        {5: "Nuke"})
        self.assertEqual(config.dpi_stage_count, 3)
        self.assertEqual(config.polling_rate, 500)
        self.assertEqual(config.rgb, vs.RgbState(1, 2, 3, vp.RGB_MODE_BREATHING, 100, 5))
        self.assertEqual(config.buttons["Button 1"]["action"], "Forward")
        self.assertEqual(config.buttons["Button 2"], {"action": "DPI Control", "params": {"func": 3}})
        self.assertEqual(config.buttons["Button 3"]["params"],
                         {"index": 5, "mode": 0xFE, "count": 1, "name": "Nuke"})
        self.assertEqual(config.buttons["Button 4"]["action"], "Triple Click")
        self.assertEqual(config.buttons["Button 5"]["action"], "Polling Rate Toggle")
        self.assertEqual(config.buttons["Button 6"]["action"], "RGB Toggle")
        self.assertEqual(config.buttons["Button 7"], {"action": "Media Key", "params": {"code": 0xCD}})
        self.assertEqual(config.buttons["Button 8"]["action"], "Disabled")

    def test_descriptions(self):
        self.assertEqual(vs.describe_binding("Keyboard Key", {"key": 0x1E, "mod": 3}),
                         "Key: 1 (Ctrl+Shift)")
        self.assertEqual(vs.describe_binding("Keyboard Key", {"key": 0x28, "mod": 0}),
                         "Key: Return")
        self.assertEqual(vs.describe_binding("Macro", {"index": 2, "mode": 0xFF}),
                         "Macro 2 (Toggle)")
        self.assertEqual(vs.describe_binding("Macro", {"index": 1, "mode": 7}), "Macro 1 (x7)")
        self.assertEqual(vs.describe_binding("Media Key", {"code": 0xCD}), "Media: PlayPause")
        self.assertEqual(vs.describe_binding("Fire Key", {"delay": 40, "repeat": 3}),
                         "Fire Key (40ms, x3)")
        self.assertEqual(vs.describe_binding("Fire Key", {"repeat": 3}, "holtek"),
                         "Fire Key (x3)")
        self.assertEqual(vs.describe_binding("Left Click", {}), "Left Click")


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.lines: list[str] = []
        self.session = vs.VenusSession(log=self.lines.append,
                                       config_dir=Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_defaults_and_settings_round_trip(self):
        self.assertEqual(self.session.macro_names[1], "Macro 1")
        self.assertEqual(len(self.session.button_assignments), 16)
        self.assertFalse(self.session.staging.has_changes())
        state = vs.RgbState(1, 2, 3, vp.RGB_MODE_NEON, 50, 4)
        self.session.set_battery_led_enabled(True, state)
        self.assertTrue(self.session.battery_led_enabled)
        reloaded = vs.VenusSession(config_dir=Path(self.temp.name))
        self.assertTrue(reloaded.battery_led_enabled)
        self.assertEqual(reloaded.battery_led_restore, state.to_dict())

    def test_every_exposed_action_has_a_packet_path(self):
        areson_params = {
            "Keyboard Key": {"key": 0x04, "mod": 0},
            "Macro": {"index": 1, "mode": vp.MACRO_REPEAT_ONCE},
            "Fire Key": {"delay": 40, "repeat": 3},
            "Triple Click": {"delay": 50, "repeat": 3},
            "Media Key": {"code": vp.MEDIA_KEY_CODES["PlayPause"]},
            "DPI Control": {"func": 1},
        }
        for action in self.session.actions:
            packets = self.session.build_packets_for_key(
                "Button 1", action, areson_params.get(action, {}))
            self.assertTrue(packets, action)
            for packet in packets:
                self.assertTrue(vp.report_checksum_valid(packet), action)

        self.session.set_device_type("holtek")
        holtek_params = {"Keyboard Key": {"key": 0x04, "mod": 0},
                         "DPI Control": {"func": 2}, "Fire Key": {"repeat": 3}}
        for action in self.session.actions:
            packets = self.session.build_packets_for_key(
                "Button 1", action, holtek_params.get(action, {}))
            self.assertTrue(packets, action)
        profile_switch = self.session.build_packets_for_key("Button 20", "Profile Switch", {})
        self.assertEqual(profile_switch[0][8:12], bytes((hp.BTN_PROFILE, 0, 0, 0)))

    def test_keyboard_binding_packets_match_the_protocol_builders(self):
        packets = self.session.build_packets_for_key(
            "Button 3", "Keyboard Key", {"key": 0x1E, "mod": vp.MODIFIER_SHIFT})
        profile = vp.BUTTON_PROFILES["Button 3"]
        expected = vp.build_key_binding(profile.code_hi, profile.code_lo, 0x1E, vp.MODIFIER_SHIFT)
        expected.append(vp.build_keyboard_bind(profile.apply_offset))
        self.assertEqual(packets, expected)

    def test_staging_skips_unchanged_bindings(self):
        self.assertTrue(self.session.stage_binding("Button 1", "Left Click", {}))
        self.assertFalse(self.session.stage_binding("Button 1", "Left Click", {}))
        self.assertTrue(self.session.staging.has_changes())
        self.assertTrue(self.session.staging.undo())
        self.assertFalse(self.session.staging.has_changes())
        self.assertTrue(self.session.staging.redo())
        self.session.discard_staged()
        self.assertFalse(self.session.staging.has_changes())

    def test_commit_sends_every_staged_packet_in_order(self):
        self.session.device_path = b"/dev/fake"
        self.session.stage_binding("Button 1", "Right Click", {})
        self.session.stage_binding("Button 2", "Middle Click", {})
        device = mock.Mock()
        device.begin_write.return_value = True
        device.send_reliable.return_value = True
        with mock.patch.object(vs.dd, "create_device", return_value=device):
            result = self.session.commit_staged()
        self.assertTrue(result.ok, result.error)
        sent = [call.args[0] for call in device.send_reliable.call_args_list]
        self.assertEqual(sent, [
            vp.build_mouse_param(vp.BUTTON_PROFILES["Button 1"].apply_offset, 0x02),
            vp.build_mouse_param(vp.BUTTON_PROFILES["Button 2"].apply_offset, 0x04),
        ])
        self.assertEqual(self.session.button_assignments["Button 1"]["action"], "Right Click")
        self.assertFalse(self.session.staging.has_changes())
        device.close.assert_called()

    def test_failed_commit_keeps_staging_and_reports_partial_write(self):
        self.session.device_path = b"/dev/fake"
        self.session.stage_binding("Button 1", "Right Click", {})
        device = mock.Mock()
        device.begin_write.return_value = True
        device.send_reliable.return_value = False
        with mock.patch.object(vs.dd, "create_device", return_value=device):
            result = self.session.commit_staged()
        self.assertFalse(result.ok)
        self.assertTrue(result.partial)
        self.assertTrue(self.session.staging.has_changes())

    def test_send_reports_wraps_transport_errors(self):
        self.session.device_path = b"/dev/fake"
        device = mock.Mock()
        device.send_reliable.return_value = False
        device.last_error = "command 0x03 timed out"
        with mock.patch.object(vs.dd, "create_device", return_value=device):
            with self.assertRaises(vs.SessionError) as raised:
                self.session.send_reports([vp.build_simple(vp.CMD_READY)], "Test")
            self.assertIn("timed out", str(raised.exception))
            self.assertFalse(self.session.send_reports(
                [vp.build_simple(vp.CMD_READY)], "Test", quiet=True))

    def test_rgb_apply_sends_ready_then_lighting_records(self):
        self.session.device_path = b"/dev/fake"
        device = mock.Mock()
        device.send_reliable.return_value = True
        state = vs.RgbState(10, 20, 30, vp.RGB_MODE_BREATHING, 60, 5)
        with mock.patch.object(vs.dd, "create_device", return_value=device):
            self.session.apply_rgb(state, "Breathing")
        sent = [call.args[0] for call in device.send_reliable.call_args_list]
        self.assertEqual(sent, [vp.build_simple(vp.CMD_READY),
                                *vp.build_rgb_packets(10, 20, 30, vp.RGB_MODE_BREATHING,
                                                      60, effect_speed=5)])

    def test_battery_led_updates_once_per_step_and_restores_manual_lighting(self):
        self.session.device_path = b"/dev/fake"
        manual = vs.RgbState(1, 2, 3, vp.RGB_MODE_STEADY, 100, 3)
        device = mock.Mock()
        device.send_reliable.return_value = True
        with mock.patch.object(vs.dd, "create_device", return_value=device):
            self.assertIsNone(self.session.set_battery_led_enabled(True, manual))
            status = vp.BatteryStatus(6, 60, False, b"\x06\x00")
            self.assertTrue(self.session.apply_battery_led_status(status))
            self.assertFalse(self.session.apply_battery_led_status(status))
            self.assertEqual(device.send_reliable.call_args_list[1].args[0],
                             vp.build_battery_indicator_rgb(60))
            restored = self.session.set_battery_led_enabled(False, manual)
        self.assertEqual(restored, manual)
        self.assertEqual(device.send_reliable.call_args_list[-1].args[0],
                         vp.build_rgb(1, 2, 3, vp.RGB_MODE_STEADY, 100))
        self.assertFalse(self.session.battery_led_enabled)

    def test_macro_upload_builds_chunked_image_writes(self):
        self.session.device_path = b"/dev/fake"
        draft = MacroDraft()
        draft.generate_text("ok", key_hold_ms=35, delay_min_ms=90,
                            delay_max_ms=90, extra_word_pause_ms=0, append=False)
        device = mock.Mock()
        device.send_reliable.return_value = True
        with mock.patch.object(vs.dd, "create_device", return_value=device):
            self.session.save_macro(3, "Okay", draft)
        sent = [call.args[0] for call in device.send_reliable.call_args_list]
        image = vp.build_macro_image("Okay", draft.to_macro_events())
        page, offset = vp.get_macro_slot_info(2)
        expected = [vp.build_simple(vp.CMD_READY)]
        address = (page << 8) | offset
        for start in range(0, len(image), 10):
            chunk_address = address + start
            expected.append(vp.build_macro_chunk(chunk_address & 0xFF, image[start:start + 10],
                                                 chunk_address >> 8))
        self.assertEqual(sent, expected)
        self.assertEqual(self.session.macro_names[3], "Okay")
        self.assertEqual(self.session.validate_macro_name(4, "okay"),
                         "Macro name 'okay' is already used by Slot 3.")

    def test_macro_load_reads_one_slot(self):
        self.session.device_path = b"/dev/fake"
        image = vp.build_macro_image("Loaded", [vp.MacroEvent(0x04, True, 35),
                                                vp.MacroEvent(0x04, False, 3)])
        image = image.ljust(vp.MACRO_SLOT_SIZE, b"\x00")

        def read_flash(page, offset, length):
            start = ((page << 8) | offset) - 0x300
            return image[start:start + length]

        device = mock.Mock()
        device.start_session.return_value = True
        device.read_flash.side_effect = read_flash
        draft = MacroDraft()
        with mock.patch.object(vs.vp, "VenusDevice", return_value=device):
            name = self.session.load_macro_slot(1, draft)
        self.assertEqual(name, "Loaded")
        self.assertEqual(draft.preview().output, "a")
        self.assertEqual(self.session.macro_names[1], "Loaded")

    def test_holtek_operations_that_are_not_supported_raise(self):
        self.session.set_device_type("holtek")
        self.session.device_path = "/dev/fake"
        with self.assertRaises(vs.NotSupported):
            self.session.factory_reset()
        with self.assertRaises(vs.NotSupported):
            self.session.send_raw_report("00" * 17)
        with self.assertRaises(vs.NotSupported):
            self.session.upload_macro(1, "x", [vp.MacroEvent(4, True, 3)])
        self.assertEqual(self.session.actions, vs.HOLTEK_ACTIONS)
        self.assertEqual(len(self.session.button_keys), 19)

    def test_demo_mode_refuses_hardware_access(self):
        config = self.session.load_demo()
        self.assertEqual(self.session.device_name, "Venus Pro (Wireless)")
        self.assertEqual(config.buttons["Button 1"]["action"], "Keyboard Key")
        with self.assertRaises(vs.DemoDevice):
            self.session.read_settings()
        with self.assertRaises(vs.DemoDevice):
            self.session.factory_reset()
        holtek = self.session.load_demo("holtek")
        self.assertEqual(holtek.dpi_stage_count, 6)
        self.assertEqual(self.session.button_keys[-1], "Button 20")


if __name__ == "__main__":
    unittest.main()
