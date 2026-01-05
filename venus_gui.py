from __future__ import annotations

import sys
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

import venus_protocol as vp


KEY_USAGE = {chr(ord("A") + i): 0x04 + i for i in range(26)}

DEFAULT_MACRO_EVENTS_HEX = (
    "000e811700005d411700009d810800005d41080000bc811600006d411600009c811700005e41170000"
    "9c810c00005e410c0000bc811100004e41110000cb810a00005e410a00"
)
DEFAULT_MACRO_TAIL_HEX = "000369000000"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Venus Pro Config (Reverse Engineering)")
        self.resize(1200, 780)

        self.device: vp.VenusDevice | None = None
        self.device_infos: list[vp.DeviceInfo] = []
        self.custom_profiles: dict[str, tuple[int, int, int]] = {}

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)

        main_layout = QtWidgets.QHBoxLayout(root)

        left_panel = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_panel, stretch=3)

        right_panel = QtWidgets.QVBoxLayout()
        main_layout.addLayout(right_panel, stretch=2)

        left_panel.addWidget(self._build_connection_group())
        left_panel.addWidget(self._build_tabs(), stretch=1)
        left_panel.addWidget(self._build_log())

        right_panel.addWidget(self._build_mouse_image())
        right_panel.addStretch(1)

        self._refresh_devices()

    def _build_connection_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Device")
        layout = QtWidgets.QGridLayout(group)

        self.device_combo = QtWidgets.QComboBox()
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.connect_button = QtWidgets.QPushButton("Connect")
        self.disconnect_button = QtWidgets.QPushButton("Disconnect")
        self.reset_button = QtWidgets.QPushButton("Reset to Default")
        self.status_label = QtWidgets.QLabel("Disconnected")

        layout.addWidget(QtWidgets.QLabel("Detected devices:"), 0, 0)
        layout.addWidget(self.device_combo, 0, 1, 1, 2)
        layout.addWidget(self.refresh_button, 0, 3)
        layout.addWidget(self.connect_button, 1, 1)
        layout.addWidget(self.disconnect_button, 1, 2)
        layout.addWidget(self.reset_button, 1, 3)
        layout.addWidget(self.status_label, 1, 4)

        self.refresh_button.clicked.connect(self._refresh_devices)
        self.connect_button.clicked.connect(self._connect_device)
        self.disconnect_button.clicked.connect(self._disconnect_device)
        self.reset_button.clicked.connect(self._factory_reset)

        return group

    def _build_tabs(self) -> QtWidgets.QTabWidget:
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._build_buttons_tab(), "Buttons")
        tabs.addTab(self._build_macros_tab(), "Macros")
        tabs.addTab(self._build_rgb_tab(), "RGB")
        tabs.addTab(self._build_polling_tab(), "Polling")
        tabs.addTab(self._build_dpi_tab(), "DPI")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        return tabs

    def _build_buttons_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.button_select = QtWidgets.QComboBox()
        for key, profile in vp.BUTTON_PROFILES.items():
            self.button_select.addItem(profile.label, key)

        self.action_select = QtWidgets.QComboBox()
        self.action_select.addItems(["Keyboard Key", "Forward", "Back", "Macro", "Reset Defaults"])

        self.key_select = QtWidgets.QComboBox()
        # Use extended key list from protocol module
        for key_name in sorted(vp.HID_KEY_USAGE.keys(), key=lambda x: (len(x) > 1, x)):
            self.key_select.addItem(key_name, vp.HID_KEY_USAGE[key_name])

        # Modifier key checkboxes
        self.mod_ctrl = QtWidgets.QCheckBox("Ctrl")
        self.mod_shift = QtWidgets.QCheckBox("Shift")
        self.mod_alt = QtWidgets.QCheckBox("Alt")
        self.mod_win = QtWidgets.QCheckBox("Win")
        
        mod_layout = QtWidgets.QHBoxLayout()
        mod_layout.addWidget(self.mod_ctrl)
        mod_layout.addWidget(self.mod_shift)
        mod_layout.addWidget(self.mod_alt)
        mod_layout.addWidget(self.mod_win)
        mod_layout.addStretch()

        self.macro_index_spin = QtWidgets.QSpinBox()
        self.macro_index_spin.setRange(1, 8)
        self.macro_index_spin.setValue(1)

        self.code_hi_spin = QtWidgets.QSpinBox()
        self.code_hi_spin.setRange(0, 255)
        self.code_hi_spin.setDisplayIntegerBase(16)
        self.code_hi_spin.setPrefix("0x")

        self.code_lo_spin = QtWidgets.QSpinBox()
        self.code_lo_spin.setRange(0, 255)
        self.code_lo_spin.setDisplayIntegerBase(16)
        self.code_lo_spin.setPrefix("0x")

        self.apply_offset_spin = QtWidgets.QSpinBox()
        self.apply_offset_spin.setRange(0, 255)
        self.apply_offset_spin.setDisplayIntegerBase(16)
        self.apply_offset_spin.setPrefix("0x")

        apply_button = QtWidgets.QPushButton("Apply Binding")
        apply_button.clicked.connect(self._apply_button_binding)

        layout.addRow("Button:", self.button_select)
        layout.addRow("Action:", self.action_select)
        layout.addRow("Key:", self.key_select)
        layout.addRow("Modifiers:", mod_layout)
        layout.addRow("Macro Index:", self.macro_index_spin)
        layout.addRow("Code hi:", self.code_hi_spin)
        layout.addRow("Code lo:", self.code_lo_spin)
        layout.addRow("Apply offset:", self.apply_offset_spin)
        layout.addRow("", apply_button)

        self.button_select.currentIndexChanged.connect(self._sync_button_profile_fields)
        self.code_hi_spin.valueChanged.connect(self._store_custom_profile)
        self.code_lo_spin.valueChanged.connect(self._store_custom_profile)
        self.apply_offset_spin.valueChanged.connect(self._store_custom_profile)
        self._sync_button_profile_fields()

        return widget

    def _build_macros_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.macro_name_edit = QtWidgets.QLineEdit("testing")
        
        # New: Instructions for macro format
        format_info = QtWidgets.QLabel(
            "Format: key-dn delay, key-up delay\n"
            "Example: t-dn 93, t-up 157, e-dn 93, e-up 188\n"
            "(Keys: A-Z, 0-9, F1-F12, Space, Enter, etc.)"
        )
        format_info.setStyleSheet("color: #666; font-size: 10px;")
        
        # Default value matches the 'testing' capture
        default_events = "t-dn 14, t-up 93, e-dn 157, e-up 93, s-dn 188, s-up 109, t-dn 156, t-up 94, i-dn 156, i-up 94, n-dn 188, n-up 78, g-dn 203, g-up 94"
        self.macro_events_edit = QtWidgets.QPlainTextEdit(default_events)
        self.macro_events_edit.setPlaceholderText("t-dn 93, t-up 157, ...")
        
        self.macro_button_select = QtWidgets.QComboBox()
        for key, profile in vp.BUTTON_PROFILES.items():
            self.macro_button_select.addItem(profile.label, key)

        self.macro_bind_index_spin = QtWidgets.QSpinBox()
        self.macro_bind_index_spin.setRange(1, 8)
        self.macro_bind_index_spin.setValue(1)

        upload_button = QtWidgets.QPushButton("Upload Macro")
        upload_button.clicked.connect(self._upload_macro)

        bind_button = QtWidgets.QPushButton("Bind Macro To Button")
        bind_button.clicked.connect(self._bind_macro_to_button)

        layout.addRow("Macro name:", self.macro_name_edit)
        layout.addRow("Macro events:", format_info)
        layout.addRow("", self.macro_events_edit)
        layout.addRow("Bind button:", self.macro_button_select)
        layout.addRow("Macro index (bind):", self.macro_bind_index_spin)
        layout.addRow("", upload_button)
        layout.addRow("", bind_button)

        return widget

    def _build_rgb_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        # Preset selector (quick options)
        self.rgb_select = QtWidgets.QComboBox()
        self.rgb_select.addItems(vp.RGB_PRESETS.keys())

        apply_preset_button = QtWidgets.QPushButton("Apply Preset")
        apply_preset_button.clicked.connect(self._apply_rgb_preset)

        layout.addRow("Presets:", self.rgb_select)
        layout.addRow("", apply_preset_button)

        # Separator
        layout.addRow(QtWidgets.QLabel(""))
        layout.addRow(QtWidgets.QLabel("Custom Color:"))

        # Color picker
        self.rgb_color_button = QtWidgets.QPushButton("Pick Color")
        self.rgb_color_button.setStyleSheet("background-color: #FF00FF; color: white; font-weight: bold;")
        self.rgb_color_button.clicked.connect(self._pick_rgb_color)
        self.rgb_current_color = QtGui.QColor(255, 0, 255)  # Default magenta
        
        # Mode selector
        self.rgb_mode = QtWidgets.QComboBox()
        self.rgb_mode.addItem("Off", vp.RGB_MODE_OFF)
        self.rgb_mode.addItem("Steady", vp.RGB_MODE_STEADY)
        self.rgb_mode.addItem("Breathing", vp.RGB_MODE_BREATHING)
        self.rgb_mode.setCurrentIndex(1)  # Default to Steady
        
        # Brightness slider
        self.rgb_brightness = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.rgb_brightness.setRange(0, 100)
        self.rgb_brightness.setValue(100)
        self.rgb_brightness_label = QtWidgets.QLabel("100%")
        self.rgb_brightness.valueChanged.connect(
            lambda v: self.rgb_brightness_label.setText(f"{v}%")
        )
        
        brightness_layout = QtWidgets.QHBoxLayout()
        brightness_layout.addWidget(self.rgb_brightness, stretch=1)
        brightness_layout.addWidget(self.rgb_brightness_label)

        apply_custom_button = QtWidgets.QPushButton("Apply Custom")
        apply_custom_button.clicked.connect(self._apply_rgb_custom)

        layout.addRow("Color:", self.rgb_color_button)
        layout.addRow("Mode:", self.rgb_mode)
        layout.addRow("Brightness:", brightness_layout)
        layout.addRow("", apply_custom_button)
        
        return widget

    def _pick_rgb_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self.rgb_current_color, self, "Pick LED Color")
        if color.isValid():
            self.rgb_current_color = color
            self.rgb_color_button.setStyleSheet(
                f"background-color: {color.name()}; color: {'white' if color.lightness() < 128 else 'black'}; font-weight: bold;"
            )

    def _build_polling_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.polling_select = QtWidgets.QComboBox()
        for rate in sorted(vp.POLLING_RATE_PAYLOADS.keys()):
            self.polling_select.addItem(f"{rate} Hz", rate)

        apply_button = QtWidgets.QPushButton("Apply Polling Rate")
        apply_button.clicked.connect(self._apply_polling_rate)

        layout.addRow("Polling rate:", self.polling_select)
        layout.addRow("", apply_button)
        return widget

    def _build_dpi_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        header = QtWidgets.QLabel("DPI slots (use presets or raw values from captures)")
        layout.addWidget(header)

        self.dpi_rows: list[tuple[QtWidgets.QComboBox, QtWidgets.QSpinBox, QtWidgets.QSpinBox]] = []
        for slot in range(5):
            row = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel(f"Slot {slot + 1}")
            label.setMinimumWidth(60)

            combo = QtWidgets.QComboBox()
            combo.addItem("Custom", None)
            for dpi in sorted(vp.DPI_PRESETS.keys()):
                combo.addItem(f"{dpi} DPI", dpi)
            combo.currentIndexChanged.connect(self._sync_dpi_presets)

            value_spin = QtWidgets.QSpinBox()
            value_spin.setRange(0, 255)
            tweak_spin = QtWidgets.QSpinBox()
            tweak_spin.setRange(0, 255)

            row.addWidget(label)
            row.addWidget(combo)
            row.addWidget(QtWidgets.QLabel("Value"))
            row.addWidget(value_spin)
            row.addWidget(QtWidgets.QLabel("Tweak"))
            row.addWidget(tweak_spin)
            layout.addLayout(row)

            self.dpi_rows.append((combo, value_spin, tweak_spin))

        apply_button = QtWidgets.QPushButton("Apply DPI Slots")
        apply_button.clicked.connect(self._apply_dpi)
        layout.addWidget(apply_button)
        layout.addStretch(1)

        self._sync_dpi_presets()
        return widget

    def _build_advanced_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.adv_command = QtWidgets.QLineEdit("07")
        self.adv_payload = QtWidgets.QLineEdit("")
        self.adv_raw = QtWidgets.QLineEdit("")

        send_built = QtWidgets.QPushButton("Send Built Report")
        send_raw = QtWidgets.QPushButton("Send Raw Report")

        send_built.clicked.connect(self._send_built_report)
        send_raw.clicked.connect(self._send_raw_report)

        layout.addRow("Command (hex):", self.adv_command)
        layout.addRow("Payload 14 bytes hex:", self.adv_payload)
        layout.addRow("", send_built)
        layout.addRow("Full report hex (17 bytes):", self.adv_raw)
        layout.addRow("", send_raw)
        return widget

    def _build_log(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Log")
        layout = QtWidgets.QVBoxLayout(group)
        self.log_area = QtWidgets.QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumBlockCount(2000)
        layout.addWidget(self.log_area)
        return group

    def _build_mouse_image(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Mouse")
        layout = QtWidgets.QVBoxLayout(group)
        label = QtWidgets.QLabel()
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        img_path = Path(__file__).resolve().parent / "mouseimg.png"
        if img_path.exists():
            pixmap = QtGui.QPixmap(str(img_path))
            label.setPixmap(pixmap.scaledToWidth(420, QtCore.Qt.TransformationMode.SmoothTransformation))
        else:
            label.setText("mouseimg.png not found")
        layout.addWidget(label)
        return group

    def _sync_button_profile_fields(self) -> None:
        button_key = self.button_select.currentData()
        if button_key is None:
            return
        profile = vp.BUTTON_PROFILES[button_key]
        custom = self.custom_profiles.get(button_key)
        if profile.code_hi is not None and profile.code_lo is not None and profile.apply_offset is not None:
            self.code_hi_spin.setValue(profile.code_hi)
            self.code_lo_spin.setValue(profile.code_lo)
            self.apply_offset_spin.setValue(profile.apply_offset)
            self.code_hi_spin.setEnabled(False)
            self.code_lo_spin.setEnabled(False)
            self.apply_offset_spin.setEnabled(False)
        else:
            if custom:
                self.code_hi_spin.setValue(custom[0])
                self.code_lo_spin.setValue(custom[1])
                self.apply_offset_spin.setValue(custom[2])
            else:
                self.code_hi_spin.setValue(0)
                self.code_lo_spin.setValue(0)
                self.apply_offset_spin.setValue(0)
            self.code_hi_spin.setEnabled(True)
            self.code_lo_spin.setEnabled(True)
            self.apply_offset_spin.setEnabled(True)

    def _store_custom_profile(self) -> None:
        button_key = self.button_select.currentData()
        if button_key is None:
            return
        profile = vp.BUTTON_PROFILES[button_key]
        if profile.code_hi is not None and profile.code_lo is not None and profile.apply_offset is not None:
            return
        self.custom_profiles[button_key] = (
            self.code_hi_spin.value(),
            self.code_lo_spin.value(),
            self.apply_offset_spin.value(),
        )

    def _resolve_profile(self, button_key: str, use_fallback: bool) -> tuple[int, int, int]:
        profile = vp.BUTTON_PROFILES[button_key]
        if profile.code_hi is not None and profile.code_lo is not None and profile.apply_offset is not None:
            return profile.code_hi, profile.code_lo, profile.apply_offset
        if button_key in self.custom_profiles:
            return self.custom_profiles[button_key]
        if use_fallback and button_key == self.button_select.currentData():
            code_hi = self.code_hi_spin.value()
            code_lo = self.code_lo_spin.value()
            apply_offset = self.apply_offset_spin.value()
            self.custom_profiles[button_key] = (code_hi, code_lo, apply_offset)
            return code_hi, code_lo, apply_offset
        raise ValueError("Unknown button profile. Fill code/offset values in the Buttons tab first.")

    def _log(self, text: str) -> None:
        self.log_area.appendPlainText(text)

    def _refresh_devices(self) -> None:
        self.device_infos = vp.list_devices()
        self.device_combo.clear()
        if not self.device_infos:
            self.device_combo.addItem("No Venus Pro devices found")
            return
        for info in self.device_infos:
            label = f"{info.product} (0x{info.product_id:04x}) {info.serial}".strip()
            self.device_combo.addItem(label, info)

    def _connect_device(self) -> None:
        if not self.device_infos:
            QtWidgets.QMessageBox.warning(self, "No device", "No supported devices detected.")
            return
        info = self.device_combo.currentData()
        if info is None:
            QtWidgets.QMessageBox.warning(self, "No device", "Pick a device entry first.")
            return
        try:
            self.device = vp.VenusDevice(info.path)
            self.device.open()
            self.status_label.setText("Connected")
            self._log(f"Connected to {info.product} ({info.serial})")
        except Exception as exc:
            self.device = None
            QtWidgets.QMessageBox.critical(self, "Connect failed", str(exc))

    def _disconnect_device(self) -> None:
        if self.device is None:
            return
        self.device.close()
        self.device = None
        self.status_label.setText("Disconnected")
        self._log("Disconnected")

    def _require_device(self) -> bool:
        if self.device is None:
            QtWidgets.QMessageBox.warning(self, "No device", "Connect to a device first.")
            return False
        return True

    def _send_reports(self, reports: list[bytes], label: str) -> None:
        if not self._require_device():
            return
        try:
            for report in reports:
                self.device.send(report)
                self._log(f"{label}: {report.hex()}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Send failed", str(exc))

    def _apply_button_binding(self) -> None:
        if not self._require_device():
            return
        button_key = self.button_select.currentData()
        action = self.action_select.currentText()
        reports = [vp.build_simple(0x03)]

        if action == "Keyboard Key":
            key_name = self.key_select.currentText()
            key_code = self.key_select.currentData()  # Get HID code from combo data
            
            # Compute modifier byte from checkboxes
            modifier = 0
            if self.mod_ctrl.isChecked():
                modifier |= vp.MODIFIER_CTRL
            if self.mod_shift.isChecked():
                modifier |= vp.MODIFIER_SHIFT
            if self.mod_alt.isChecked():
                modifier |= vp.MODIFIER_ALT
            if self.mod_win.isChecked():
                modifier |= vp.MODIFIER_WIN
            
            code_hi, code_lo, apply_offset = self._resolve_profile(button_key, use_fallback=True)
            reports.append(vp.build_key_binding(code_hi, code_lo, key_code, modifier))
            
            # Add second packet if modifiers are used
            apply_pkt = vp.build_key_binding_apply(code_hi, code_lo, key_code, modifier)
            if apply_pkt:
                reports.append(apply_pkt)
            
            reports.append(vp.build_apply_binding(apply_offset, action_type=0x05, action_code=0x50))
            reports.append(vp.build_simple(0x04))
            
            mod_str = ""
            if modifier:
                parts = []
                if modifier & vp.MODIFIER_CTRL: parts.append("Ctrl")
                if modifier & vp.MODIFIER_SHIFT: parts.append("Shift")
                if modifier & vp.MODIFIER_ALT: parts.append("Alt")
                if modifier & vp.MODIFIER_WIN: parts.append("Win")
                mod_str = "+".join(parts) + "+"
            
            self._send_reports(reports, f"Bind {button_key} -> {mod_str}{key_name}")
            return

        if action == "Forward":
            _, _, apply_offset = self._resolve_profile(button_key, use_fallback=True)
            reports.append(vp.build_forward_back(apply_offset, True))
            reports.append(vp.build_simple(0x04))
            self._send_reports(reports, f"Bind {button_key} -> Forward")
            return

        if action == "Back":
            _, _, apply_offset = self._resolve_profile(button_key, use_fallback=True)
            reports.append(vp.build_forward_back(apply_offset, False))
            reports.append(vp.build_simple(0x04))
            self._send_reports(reports, f"Bind {button_key} -> Back")
            return

        if action == "Macro":
            macro_index = self.macro_index_spin.value()
            _, _, apply_offset = self._resolve_profile(button_key, use_fallback=True)
            reports.append(vp.build_macro_bind(apply_offset, macro_index))
            reports.append(vp.build_simple(0x04))
            self._send_reports(reports, f"Bind {button_key} -> Macro {macro_index}")
            return

        if action == "Reset Defaults":
            self._send_reports([vp.build_simple(0x09)], "Reset defaults")
            return

    def _upload_macro(self) -> None:
        if not self._require_device():
            return
        name = self.macro_name_edit.text().strip() or "macro"
        events_text = self.macro_events_edit.toPlainText().strip()
        
        # Parse text-based macro events
        macro_events: list[vp.MacroEvent] = []
        try:
            # Format: 't-dn 93, t-up 157'
            parts = [p.strip() for p in events_text.replace(",", " ").split() if p.strip()]
            
            # Group into [event, duration] pairs
            for i in range(0, len(parts), 2):
                if i + 1 >= len(parts):
                    break
                
                event_type = parts[i].lower()
                delay_ms = int(parts[i+1])
                
                if "-dn" in event_type:
                    key_name = event_type.replace("-dn", "").upper()
                    is_down = True
                elif "-up" in event_type:
                    key_name = event_type.replace("-up", "").upper()
                    is_down = False
                else:
                    raise ValueError(f"Invalid event type: {event_type}")
                
                if key_name not in vp.HID_KEY_USAGE:
                    raise ValueError(f"Unknown key: {key_name}")
                
                macro_events.append(vp.MacroEvent(
                    keycode=vp.HID_KEY_USAGE[key_name],
                    is_down=is_down,
                    delay_ms=delay_ms
                ))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Parse Error", f"Failed to parse macro events: {exc}")
            return

        # Prepare name (UTF-16LE)
        name_bytes = name.encode("utf-16le")
        if len(name_bytes) > 0x1D:
            QtWidgets.QMessageBox.warning(self, "Name too long", "Macro name must be <= 29 bytes UTF-16LE.")
            return

        # Build macro buffer (0x70 bytes)
        buf = bytearray(0x70)
        buf[0] = len(name_bytes)
        buf[1 : 1 + len(name_bytes)] = name_bytes

        # Pack events into buffer starting at 0x1E
        event_offset = 0x1E
        for event in macro_events:
            event_data = event.to_bytes()
            if event_offset + len(event_data) > 0x64:
                self._log("Warning: Macro events truncated (reached 0x64 offset)")
                break
            buf[event_offset : event_offset + len(event_data)] = event_data
            event_offset += len(event_data)

        # Upload sequence
        reports = [vp.build_simple(0x04), vp.build_simple(0x03)]
        
        # Upload chunks of 10 bytes
        for offset in range(0x00, 0x64, 0x0A):
            chunk = bytes(buf[offset : offset + 10])
            reports.append(vp.build_macro_chunk(offset, chunk))
            
        # Add tail/terminator
        reports.append(vp.build_macro_terminator())
        reports.append(vp.build_simple(0x04))

        self._send_reports(reports, f"Upload macro {name} ({len(macro_events)} events)")

    def _bind_macro_to_button(self) -> None:
        if not self._require_device():
            return
        button_key = self.macro_button_select.currentData()
        macro_index = self.macro_bind_index_spin.value()
        try:
            _, _, apply_offset = self._resolve_profile(button_key, use_fallback=False)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Missing profile", str(exc))
            return
        reports = [vp.build_simple(0x03), vp.build_macro_bind(apply_offset, macro_index), vp.build_simple(0x04)]
        self._send_reports(reports, f"Bind macro {macro_index} -> {button_key}")

    def _apply_rgb_preset(self) -> None:
        preset_key = self.rgb_select.currentText()
        payload = vp.RGB_PRESETS[preset_key]
        reports = [vp.build_simple(0x03), vp.build_report(0x07, payload), vp.build_simple(0x04)]
        self._send_reports(reports, f"RGB Preset: {preset_key}")

    def _apply_rgb_custom(self) -> None:
        if not self._require_device():
            return
        r = self.rgb_current_color.red()
        g = self.rgb_current_color.green()
        b = self.rgb_current_color.blue()
        mode = self.rgb_mode.currentData()
        brightness = self.rgb_brightness.value()
        
        rgb_packet = vp.build_rgb(r, g, b, mode, brightness)
        reports = [vp.build_simple(0x03), rgb_packet, vp.build_simple(0x04)]
        
        mode_name = self.rgb_mode.currentText()
        self._send_reports(reports, f"RGB Custom: #{r:02x}{g:02x}{b:02x} {mode_name} {brightness}%")

    def _apply_polling_rate(self) -> None:
        rate = self.polling_select.currentData()
        payload = vp.POLLING_RATE_PAYLOADS[rate]
        reports = [vp.build_simple(0x03), vp.build_report(0x07, payload), vp.build_simple(0x04)]
        self._send_reports(reports, f"Polling {rate} Hz")

    def _sync_dpi_presets(self) -> None:
        for combo, value_spin, tweak_spin in self.dpi_rows:
            dpi_value = combo.currentData()
            if dpi_value is None:
                continue
            preset = vp.DPI_PRESETS[dpi_value]
            value_spin.blockSignals(True)
            tweak_spin.blockSignals(True)
            value_spin.setValue(preset["value"])
            tweak_spin.setValue(preset["tweak"])
            value_spin.blockSignals(False)
            tweak_spin.blockSignals(False)

    def _apply_dpi(self) -> None:
        reports = [vp.build_simple(0x04), vp.build_simple(0x03)]
        for slot, (_, value_spin, tweak_spin) in enumerate(self.dpi_rows):
            reports.append(vp.build_dpi(slot, value_spin.value(), tweak_spin.value()))
        reports.append(vp.build_simple(0x04))
        self._send_reports(reports, "DPI slots")

    def _send_built_report(self) -> None:
        if not self._require_device():
            return
        try:
            command = int(self.adv_command.text().strip(), 16)
            payload_hex = self.adv_payload.text().strip().replace(" ", "")
            payload = bytes.fromhex(payload_hex)
            report = vp.build_report(command, payload)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid input", str(exc))
            return
        self._send_reports([report], "Advanced built")

    def _send_raw_report(self) -> None:
        if not self._require_device():
            return
        try:
            raw_hex = self.adv_raw.text().strip().replace(" ", "")
            report = bytes.fromhex(raw_hex)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid hex", str(exc))
            return
        if len(report) != vp.REPORT_LEN:
            QtWidgets.QMessageBox.warning(self, "Invalid length", f"Report must be {vp.REPORT_LEN} bytes.")
            return
        self._send_reports([report], "Advanced raw")


    def _factory_reset(self) -> None:
        if not self._require_device():
            return
        
        reply = QtWidgets.QMessageBox.question(
            self, 
            "Confirm Reset", 
            "Are you sure you want to reset the device to factory defaults?\nThis will clear all custom button mappings, macros, and RGB settings.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._send_reports([vp.build_simple(0x09)], "Factory reset")
            QtWidgets.QMessageBox.information(self, "Reset Complete", "Factory reset command sent.")

def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
