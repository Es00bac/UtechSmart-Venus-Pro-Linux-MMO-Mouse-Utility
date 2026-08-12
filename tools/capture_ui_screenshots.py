#!/usr/bin/env python3
"""Render deterministic, hardware-free screenshots for the README."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import random
import sys
from tempfile import TemporaryDirectory
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtCore, QtGui, QtWidgets

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import holtek_protocol as hp
import venus_gui as gui
import venus_protocol as vp


def _save_window(window: gui.MainWindow, output: Path) -> None:
    QtWidgets.QApplication.processEvents()
    window.repaint()
    QtWidgets.QApplication.processEvents()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(output), "PNG"):
        raise RuntimeError(f"failed to save {output}")
    print(output)


def _areson_assignments() -> dict[str, dict]:
    assignments = {
        key: {"action": "Disabled", "params": {}}
        for key in vp.BUTTON_PROFILES
    }
    assignments.update({
        "Button 1": {
            "action": "Keyboard Key",
            "params": {
                "key": vp.HID_KEY_USAGE["1"],
                "mod": vp.MODIFIER_CTRL | vp.MODIFIER_SHIFT,
            },
        },
        "Button 2": {
            "action": "Macro",
            "params": {"index": 1, "mode": vp.MACRO_REPEAT_ONCE},
        },
        "Button 3": {"action": "Left Click", "params": {}},
        "Button 4": {
            "action": "Media Key",
            "params": {"code": vp.MEDIA_KEY_CODES["PlayPause"]},
        },
        "Button 5": {
            "action": "DPI Control", "params": {"func": 2}},
        "Button 6": {
            "action": "RGB Toggle", "params": {}},
        "Button 7": {
            "action": "Polling Rate Toggle", "params": {}},
    })
    return assignments


def _prepare_areson(window: gui.MainWindow) -> None:
    window.device_type = "venus_pro"
    window.active_button_profiles = vp.BUTTON_PROFILES
    window._sync_device_specific_ui()
    window._rebuild_button_table()
    window.button_assignments = _areson_assignments()
    window.staging_manager.load_base_state(window.button_assignments)
    window._update_staged_visuals()
    window.status_label.setText("Ready: Venus Pro (Wireless)")
    window.status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")


def _capture_areson(window: gui.MainWindow, output_dir: Path) -> None:
    _prepare_areson(window)
    window.tabs.setCurrentIndex(0)
    window.btn_table.selectRow(0)
    window.log_area.setPlainText(
        "Configuration read successfully.\n"
        "Select a button, stage a binding, then apply all changes.")
    _save_window(window, output_dir / "Buttons.png")

    window.tabs.setCurrentIndex(1)
    window.macro_name_edit.setText("Chat greeting")
    window.quick_text_edit.setPlainText("Hello, Venus!")
    window.text_timing_mode.setCurrentIndex(
        window.text_timing_mode.findData("random"))
    window.text_random_min_spin.setValue(70)
    window.text_random_max_spin.setValue(160)
    window.text_word_pause_spin.setValue(80)
    with mock.patch.object(
            gui.vp.random, "SystemRandom", return_value=random.Random(7)):
        window._generate_text_macro()
    window.log_area.setPlainText(
        "Generated a text macro with randomized inter-key delays.\n"
        "32 of 69 hardware events used; no device write performed.")
    _save_window(window, output_dir / "Macros.png")

    window.macro_builder_tabs.setCurrentIndex(1)
    window._clear_macro_events()
    window.add_action_combo.setCurrentIndex(
        window.add_action_combo.findData("tap"))
    window.add_hold_spin.setValue(35)
    window.add_delay_spin.setValue(120)
    for mouse_index in (0, 1, 2):
        window.add_key_combo.setCurrentIndex(mouse_index)
        window._add_manual_event()
    window.add_key_combo.setCurrentIndex(2)
    window.log_area.setPlainText(
        "Added native left-, right-, and middle-click press/release pairs.\n"
        "Back and Forward are also available from the event menu.")
    _save_window(window, output_dir / "MacroManual.png")

    window.tabs.setCurrentIndex(2)
    window._set_custom_color(QtGui.QColor(76, 175, 80))
    window.rgb_mode.setCurrentIndex(
        window.rgb_mode.findData(vp.RGB_MODE_STEADY))
    window.rgb_brightness.setValue(15)
    window.battery_led_checkbox.blockSignals(True)
    window.battery_led_checkbox.setChecked(True)
    window.battery_led_checkbox.blockSignals(False)
    window.log_area.setPlainText(
        "Battery LED gauge: low brightness, 10% update steps.\n"
        "Manual lighting is restored when the controller exits normally.")
    _save_window(window, output_dir / "RGB.png")

    window.tabs.setCurrentIndex(4)
    window.dpi_stage_count_spin.setValue(5)
    for row, dpi in enumerate((1000, 2000, 4000, 8000, 10000)):
        combo, dpi_spin, _, _ = window.dpi_rows[row]
        preset = combo.findData(dpi)
        combo.setCurrentIndex(preset if preset >= 0 else 0)
        dpi_spin.setValue(dpi)
    window.log_area.setPlainText(
        "Five Areson DPI stages loaded.\n"
        "Preset raw values are capture-backed; custom conversion is approximate.")
    _save_window(window, output_dir / "DPI.png")


def _capture_holtek(window: gui.MainWindow, output_dir: Path) -> None:
    window.device_type = "holtek"
    window.active_button_profiles = hp.BUTTON_PROFILES
    window._sync_device_specific_ui()
    window._rebuild_button_table()
    assignments = {
        key: {"action": "Disabled", "params": {}}
        for key in hp.BUTTON_PROFILES
    }
    assignments["Button 5"] = {
        "action": "Keyboard Key",
        "params": {"key": vp.HID_KEY_USAGE["PageUp"], "mod": 0},
    }
    assignments["Button 6"] = {
        "action": "Keyboard Key",
        "params": {"key": vp.HID_KEY_USAGE["PageDown"], "mod": 0},
    }
    assignments["Button 20"] = {
        "action": "Profile Switch", "params": {}}
    window.button_assignments = assignments
    window.staging_manager.load_base_state(assignments)
    window._update_staged_visuals()
    window.status_label.setText("Ready: Venus MMO (Holtek) — Profile 1")
    window.status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
    window.profile_label.setVisible(True)
    window.profile_combo.setVisible(True)
    window.tabs.setCurrentIndex(0)
    window.btn_table.selectRow(4)
    window.log_area.setPlainText(
        "Holtek profile 1 read successfully.\n"
        "Physical DPI Up is rebound to PageUp; DPI Down is rebound to PageDown.")
    _save_window(window, output_dir / "HoltekButtons.png")

    window.tabs.setCurrentIndex(4)
    window.dpi_stage_count_spin.setValue(6)
    window.dpi_active_stage_spin.setValue(3)
    for row, dpi in enumerate((800, 1200, 1600, 2400, 3200, 6400)):
        combo, dpi_spin, _, _ = window.dpi_rows[row]
        preset = combo.findData(dpi)
        combo.setCurrentIndex(preset if preset >= 0 else 0)
        dpi_spin.setValue(dpi)
    window.log_area.setPlainText(
        "Holtek profile 1: six enabled DPI stages; stage 3 is current.\n"
        "Per-stage LED color indices are preserved during DPI edits.")
    _save_window(window, output_dir / "HoltekDPI.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=REPO_ROOT,
        help="directory for Buttons.png, Macros.png, and related images")
    args = parser.parse_args()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle("Fusion")
    with TemporaryDirectory() as temporary_home, \
            mock.patch.object(gui.Path, "home",
                              return_value=Path(temporary_home)), \
            mock.patch.object(gui.vp, "list_devices", return_value=[]), \
            mock.patch.object(
                gui.QtWidgets.QSystemTrayIcon, "isSystemTrayAvailable",
                return_value=False):
        window = gui.MainWindow()
        window.resize(1500, 900)
        window.show()
        _capture_areson(window, args.output_dir)
        _capture_holtek(window, args.output_dir)
        window.close()
        window.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
