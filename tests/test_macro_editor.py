"""Headless behavior checks for the slot-oriented macro editor."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtGui, QtWidgets

    import venus_gui as gui
    import venus_protocol as vp
except ImportError:  # pragma: no cover - minimal test hosts
    QtWidgets = None
    gui = None
    vp = None


@unittest.skipIf(QtWidgets is None, "PyQt6 is not installed")
class MacroEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_home = TemporaryDirectory()
        self.home_patch = mock.patch.object(
            gui.Path, "home", return_value=Path(self.temp_home.name))
        self.device_patch = mock.patch.object(
            gui.vp, "list_devices", return_value=[])
        self.tray_patch = mock.patch.object(
            gui.QtWidgets.QSystemTrayIcon,
            "isSystemTrayAvailable",
            return_value=False,
        )
        self.home_patch.start()
        self.device_patch.start()
        self.tray_patch.start()
        self.window = gui.MainWindow()

    def tearDown(self):
        self.window.battery_timer.stop()
        self.window.close()
        self.window.deleteLater()
        self.tray_patch.stop()
        self.device_patch.stop()
        self.home_patch.stop()
        self.temp_home.cleanup()

    def test_fixed_text_generation_and_append(self):
        self.window.quick_text_edit.setPlainText("ab")
        self.window.text_hold_spin.setValue(35)
        self.window.text_fixed_delay_spin.setValue(90)
        self.window._generate_text_macro()

        events = self.window._get_macro_events_from_table()
        self.assertEqual(len(events), 4)
        self.assertEqual([event.delay_ms for event in events], [35, 90, 35, 3])
        self.assertIn('Output: "ab"', self.window.macro_preview_label.text())
        self.assertEqual(self.window.macro_capacity_bar.value(), 4)

        self.window.text_output_mode.setCurrentIndex(
            self.window.text_output_mode.findData("append"))
        self.window.quick_text_edit.setPlainText("c")
        self.window._generate_text_macro()

        events = self.window._get_macro_events_from_table()
        self.assertEqual(len(events), 6)
        self.assertEqual(vp.macro_events_to_text(events), "abc")
        self.assertEqual(self.window.macro_capacity_bar.value(), 6)

    def test_manual_mouse_tap_creates_a_matched_pair(self):
        self.window.add_key_combo.setCurrentIndex(0)
        self.window.add_action_combo.setCurrentIndex(
            self.window.add_action_combo.findData("tap"))
        self.window.add_hold_spin.setValue(25)
        self.window.add_delay_spin.setValue(120)
        self.window._add_manual_event()

        events = self.window._get_macro_events_from_table()
        self.assertEqual(
            events,
            [
                vp.MacroEvent.mouse(0x01, True, 25),
                vp.MacroEvent.mouse(0x01, False, 120),
            ],
        )
        self.assertIn("[Left click]", self.window.macro_preview_label.text())
        self.assertNotIn("still pressed", self.window.macro_preview_label.text())

    def test_manual_builder_exposes_every_hardware_modifier(self):
        modifier_items = {}
        for index in range(self.window.add_key_combo.count()):
            event_data = self.window.add_key_combo.itemData(index)
            if event_data and event_data[0] == "modifier":
                modifier_items[self.window.add_key_combo.itemText(index)] = (
                    event_data[1])

        self.assertEqual(
            modifier_items,
            {
                f"Modifier: {name}": code
                for name, code in vp.MACRO_MODIFIER_CODES.items()
            },
        )

    def test_recording_ctrl_c_keeps_modifier_press_and_release(self):
        self.window._toggle_recording(True)
        events = (
            QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyPress,
                QtCore.Qt.Key.Key_Control,
                QtCore.Qt.KeyboardModifier.ControlModifier,
            ),
            QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyPress,
                QtCore.Qt.Key.Key_C,
                QtCore.Qt.KeyboardModifier.ControlModifier,
                "c",
            ),
            QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyRelease,
                QtCore.Qt.Key.Key_C,
                QtCore.Qt.KeyboardModifier.ControlModifier,
                "c",
            ),
            QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyRelease,
                QtCore.Qt.Key.Key_Control,
                QtCore.Qt.KeyboardModifier.NoModifier,
            ),
        )
        for event in events:
            self.assertTrue(self.window.eventFilter(self.window, event))
        self.window._stop_recording()

        recorded = self.window._get_macro_events_from_table()
        self.assertEqual(
            [(event.keycode, event.is_down, event.is_modifier)
             for event in recorded],
            [
                (vp.MACRO_MODIFIER_CODES["Left Ctrl"], True, True),
                (vp.HID_KEY_USAGE["C"], True, False),
                (vp.HID_KEY_USAGE["C"], False, False),
                (vp.MACRO_MODIFIER_CODES["Left Ctrl"], False, True),
            ],
        )
        self.assertIn("[Left Ctrl+C]", self.window.macro_preview_label.text())
        self.assertNotIn("still pressed", self.window.macro_preview_label.text())

    def test_alt_meta_and_shift_are_recorded_as_modifier_events(self):
        cases = (
            (QtCore.Qt.Key.Key_Alt, "Left Alt"),
            (QtCore.Qt.Key.Key_Meta, "GUI"),
            (QtCore.Qt.Key.Key_Shift, "Left Shift"),
        )
        for qt_key, expected_name in cases:
            key_event = QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyPress,
                qt_key,
                QtCore.Qt.KeyboardModifier.NoModifier,
            )
            self.assertEqual(
                self.window._qt_key_to_macro_modifier(key_event),
                (expected_name, vp.MACRO_MODIFIER_CODES[expected_name]),
            )

    def test_native_right_modifier_metadata_selects_right_code(self):
        right_ctrl = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_Control,
            QtCore.Qt.KeyboardModifier.ControlModifier,
            105,
            0xFFE4,
            0,
        )
        self.assertEqual(
            self.window._qt_key_to_macro_modifier(right_ctrl),
            ("Right Ctrl", vp.MACRO_MODIFIER_CODES["Right Ctrl"]),
        )

    def test_press_only_is_boolean_and_warns_when_unreleased(self):
        self.window.add_action_combo.setCurrentIndex(
            self.window.add_action_combo.findData("press"))
        self.window._add_manual_event()

        event = self.window._get_macro_events_from_table()[0]
        self.assertIs(event.is_down, True)
        self.assertIn("still pressed", self.window.macro_preview_label.text())

    def test_capacity_and_unsupported_text_disable_generation(self):
        self.window.quick_text_edit.setPlainText("a" * 34)
        self.assertTrue(self.window.gen_text_btn.isEnabled())
        self.window._generate_text_macro()
        self.assertEqual(self.window.macro_event_table.rowCount(), 68)

        self.window.text_output_mode.setCurrentIndex(
            self.window.text_output_mode.findData("append"))
        self.window.quick_text_edit.setPlainText("a")
        self.assertFalse(self.window.gen_text_btn.isEnabled())
        self.assertIn("holds 69", self.window.text_builder_status.text())

        self.window.text_output_mode.setCurrentIndex(
            self.window.text_output_mode.findData("replace"))
        self.window.quick_text_edit.setPlainText("\N{SNOWMAN}")
        self.assertFalse(self.window.gen_text_btn.isEnabled())
        self.assertIn("Unsupported", self.window.text_builder_status.text())

    def test_macro_slot_selection_does_not_restage_button_editor(self):
        self.window.macro_index_spin.setValue(4)
        self.window.macro_bind_index_spin.setValue(9)
        self.assertEqual(self.window.macro_index_spin.value(), 4)
        self.window.macro_list.setCurrentRow(11)
        self.assertEqual(self.window.macro_index_spin.value(), 4)

    def test_holtek_ui_exposes_only_supported_actions(self):
        self.window.device_type = "holtek"
        self.window.active_button_profiles = gui.hp.BUTTON_PROFILES
        self.window._sync_device_specific_ui()

        actions = {
            self.window.action_select.itemText(index)
            for index in range(self.window.action_select.count())
        }
        self.assertIn("Profile Switch", actions)
        self.assertIn("DPI Control", actions)
        for unsupported in (
                "Macro", "Media Key", "RGB Toggle",
                "Polling Rate Toggle", "Triple Click"):
            self.assertNotIn(unsupported, actions)
        self.assertFalse(self.window.mod_ctrl.isEnabled())
        self.assertTrue(self.window.special_delay_spin.isHidden())
        self.assertFalse(self.window.export_button.isEnabled())

        tabs = {
            self.window.tabs.tabText(index): index
            for index in range(self.window.tabs.count())
        }
        self.assertFalse(self.window.tabs.isTabEnabled(tabs["Macros"]))
        self.assertFalse(self.window.tabs.isTabEnabled(tabs["Advanced"]))
        self.assertFalse(self.window.dpi_profile_controls.isHidden())
        self.assertEqual(self.window.dpi_rows[0][1].minimum(), 200)
        self.assertEqual(self.window.dpi_rows[0][1].maximum(), 28000)

        self.window.dpi_stage_count_spin.setValue(6)
        self.assertFalse(self.window.dpi_row_widgets[5].isHidden())
        self.assertTrue(self.window.dpi_row_widgets[6].isHidden())

    def test_holtek_profile_switch_builds_confirmed_record(self):
        self.window.device_type = "holtek"
        self.window.active_button_profiles = gui.hp.BUTTON_PROFILES
        packets = self.window._build_packets_for_key(
            "Button 20", "Profile Switch", {})
        self.assertEqual(len(packets), 1)
        self.assertEqual(
            packets[0][8:12],
            bytes((gui.hp.BTN_PROFILE, 0, 0, 0)),
        )

    def test_every_exposed_button_action_has_a_packet_path(self):
        areson_params = {
            "Keyboard Key": {"key": 0x04, "mod": 0},
            "Macro": {"index": 1, "mode": vp.MACRO_REPEAT_ONCE},
            "Fire Key": {"delay": 40, "repeat": 3},
            "Triple Click": {"delay": 50, "repeat": 3},
            "Media Key": {"code": vp.MEDIA_KEY_CODES["PlayPause"]},
            "DPI Control": {"func": 1},
        }
        self.window.device_type = "venus_pro"
        self.window.active_button_profiles = vp.BUTTON_PROFILES
        self.window._sync_device_specific_ui()
        for index in range(self.window.action_select.count()):
            action = self.window.action_select.itemText(index)
            packets = self.window._build_packets_for_key(
                "Button 1", action, areson_params.get(action, {}))
            self.assertTrue(packets, action)

        holtek_params = {
            "Keyboard Key": {"key": 0x04, "mod": 0},
            "DPI Control": {"func": 2},
            "Fire Key": {"repeat": 3},
        }
        self.window.device_type = "holtek"
        self.window.active_button_profiles = gui.hp.BUTTON_PROFILES
        self.window._sync_device_specific_ui()
        for index in range(self.window.action_select.count()):
            action = self.window.action_select.itemText(index)
            packets = self.window._build_packets_for_key(
                "Button 1", action, holtek_params.get(action, {}))
            self.assertTrue(packets, action)


if __name__ == "__main__":
    unittest.main()
