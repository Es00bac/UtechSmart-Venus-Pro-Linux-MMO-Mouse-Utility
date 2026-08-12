"""Headless lifecycle checks for the battery-colour LED controller."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    import venus_gui as gui
    import venus_protocol as vp
except ImportError:  # pragma: no cover - exercised on minimal test hosts
    QtWidgets = None
    gui = None
    vp = None


@unittest.skipIf(QtWidgets is None, "PyQt6 is not installed")
class BatteryLedControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_home = TemporaryDirectory()
        self.home_patch = mock.patch.object(
            gui.Path, "home", return_value=Path(self.temp_home.name))
        self.device_patch = mock.patch.object(gui.vp, "list_devices", return_value=[])
        self.tray_patch = mock.patch.object(
            gui.QtWidgets.QSystemTrayIcon,
            "isSystemTrayAvailable",
            return_value=False,
        )
        self.home_patch.start()
        self.device_patch.start()
        self.tray_patch.start()
        self.window = gui.MainWindow()
        self.window.device_type = "venus_pro"
        self.window.device_path = b"/dev/fake"
        self.window._request_battery_refresh = mock.Mock()

    def tearDown(self):
        self.window.battery_timer.stop()
        self.window.close()
        self.window.deleteLater()
        self.tray_patch.stop()
        self.device_patch.stop()
        self.home_patch.stop()
        self.temp_home.cleanup()

    def test_toggle_updates_once_per_step_then_restores_manual_lighting(self):
        manual = self.window._capture_rgb_restore()
        self.window._set_battery_led_enabled(True)

        self.assertTrue(self.window.battery_led_enabled)
        self.assertEqual(self.window._battery_led_restore, manual)
        self.window._request_battery_refresh.assert_called_once_with()

        send = mock.Mock(return_value=True)
        self.window._send_reports = send
        status = vp.BatteryStatus(6, 60, False, b"\x06\x00")
        self.window._apply_battery_led_status(status)
        self.window._apply_battery_led_status(status)

        send.assert_called_once()
        indicator_reports = send.call_args.args[0]
        self.assertEqual(
            indicator_reports[1], vp.build_battery_indicator_rgb(60))

        self.window._set_battery_led_enabled(False)
        self.assertFalse(self.window.battery_led_enabled)
        self.assertEqual(send.call_count, 2)
        restore_reports = send.call_args.args[0]
        self.assertEqual(
            restore_reports[1],
            vp.build_rgb(
                manual["r"], manual["g"], manual["b"],
                manual["mode"], manual["brightness"],
            ),
        )

        saved = json.loads(self.window.settings_file.read_text(encoding="utf-8"))
        self.assertFalse(saved["battery_led_enabled"])

    def test_automatic_connect_requests_a_silent_read(self):
        info = vp.DeviceInfo(
            path=b"/dev/fake",
            product="Test receiver",
            manufacturer="Test",
            vendor_id=0x25A7,
            product_id=0xFA07,
            serial="",
            interface_number=1,
            usage_page=0xFF02,
            usage=2,
        )
        self.window._read_settings = mock.Mock()
        with mock.patch.object(gui.vp, "list_devices", return_value=[info]):
            self.window._refresh_and_connect(silent=True)
        self.window._read_settings.assert_called_once_with(silent=True)


if __name__ == "__main__":
    unittest.main()
