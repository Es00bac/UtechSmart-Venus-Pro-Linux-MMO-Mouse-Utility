from __future__ import annotations

import sys
import json
import time
from pathlib import Path
from copy import deepcopy

from PyQt6 import QtCore, QtGui, QtWidgets

import venus_protocol as vp
import holtek_protocol as hp
import device_driver as dd
from staging_manager import StagingManager
from transaction_controller import TransactionController


class KeyCaptureEdit(QtWidgets.QLineEdit):
    """Key capture widget that distinguishes numpad keys from regular keys.

    QKeySequenceEdit cannot tell Numpad 1 from regular 1. This widget checks
    Qt.KeyboardModifier.KeypadModifier and maps to the correct HID key name
    (e.g. "Keypad 1" vs "1").
    """

    keyChanged = QtCore.pyqtSignal()

    # Qt.Key → HID_KEY_USAGE name (regular keys)
    _QT_TO_HID = {
        **{getattr(QtCore.Qt.Key, f"Key_{chr(c)}"): chr(c)
           for c in range(ord("A"), ord("Z") + 1)},
        QtCore.Qt.Key.Key_1: "1", QtCore.Qt.Key.Key_2: "2",
        QtCore.Qt.Key.Key_3: "3", QtCore.Qt.Key.Key_4: "4",
        QtCore.Qt.Key.Key_5: "5", QtCore.Qt.Key.Key_6: "6",
        QtCore.Qt.Key.Key_7: "7", QtCore.Qt.Key.Key_8: "8",
        QtCore.Qt.Key.Key_9: "9", QtCore.Qt.Key.Key_0: "0",
        QtCore.Qt.Key.Key_F1: "F1", QtCore.Qt.Key.Key_F2: "F2",
        QtCore.Qt.Key.Key_F3: "F3", QtCore.Qt.Key.Key_F4: "F4",
        QtCore.Qt.Key.Key_F5: "F5", QtCore.Qt.Key.Key_F6: "F6",
        QtCore.Qt.Key.Key_F7: "F7", QtCore.Qt.Key.Key_F8: "F8",
        QtCore.Qt.Key.Key_F9: "F9", QtCore.Qt.Key.Key_F10: "F10",
        QtCore.Qt.Key.Key_F11: "F11", QtCore.Qt.Key.Key_F12: "F12",
        QtCore.Qt.Key.Key_F13: "F13", QtCore.Qt.Key.Key_F14: "F14",
        QtCore.Qt.Key.Key_F15: "F15", QtCore.Qt.Key.Key_F16: "F16",
        QtCore.Qt.Key.Key_F17: "F17", QtCore.Qt.Key.Key_F18: "F18",
        QtCore.Qt.Key.Key_F19: "F19", QtCore.Qt.Key.Key_F20: "F20",
        QtCore.Qt.Key.Key_F21: "F21", QtCore.Qt.Key.Key_F22: "F22",
        QtCore.Qt.Key.Key_F23: "F23", QtCore.Qt.Key.Key_F24: "F24",
        QtCore.Qt.Key.Key_Return: "Enter", QtCore.Qt.Key.Key_Escape: "Escape",
        QtCore.Qt.Key.Key_Backspace: "Backspace", QtCore.Qt.Key.Key_Tab: "Tab",
        QtCore.Qt.Key.Key_Space: "Space",
        QtCore.Qt.Key.Key_Minus: "-", QtCore.Qt.Key.Key_Equal: "=",
        QtCore.Qt.Key.Key_BracketLeft: "[", QtCore.Qt.Key.Key_BracketRight: "]",
        QtCore.Qt.Key.Key_Backslash: "\\", QtCore.Qt.Key.Key_Semicolon: ";",
        QtCore.Qt.Key.Key_Apostrophe: "'", QtCore.Qt.Key.Key_QuoteLeft: "`",
        QtCore.Qt.Key.Key_Comma: ",", QtCore.Qt.Key.Key_Period: ".",
        QtCore.Qt.Key.Key_Slash: "/", QtCore.Qt.Key.Key_CapsLock: "CapsLock",
        QtCore.Qt.Key.Key_Insert: "Insert", QtCore.Qt.Key.Key_Home: "Home",
        QtCore.Qt.Key.Key_PageUp: "PageUp", QtCore.Qt.Key.Key_Delete: "Delete",
        QtCore.Qt.Key.Key_End: "End", QtCore.Qt.Key.Key_PageDown: "PageDown",
        QtCore.Qt.Key.Key_Right: "Right", QtCore.Qt.Key.Key_Left: "Left",
        QtCore.Qt.Key.Key_Down: "Down", QtCore.Qt.Key.Key_Up: "Up",
        QtCore.Qt.Key.Key_Print: "PrintScreen",
        QtCore.Qt.Key.Key_ScrollLock: "ScrollLock",
        QtCore.Qt.Key.Key_Pause: "Pause", QtCore.Qt.Key.Key_Menu: "Menu",
        QtCore.Qt.Key.Key_NumLock: "NumLock",
        # Modifier keys (standalone binding)
        QtCore.Qt.Key.Key_Shift: "Left Shift", QtCore.Qt.Key.Key_Control: "Left Ctrl",
        QtCore.Qt.Key.Key_Alt: "Left Alt", QtCore.Qt.Key.Key_Meta: "Left GUI",
    }

    # When KeypadModifier is active, override these keys → "Keypad X"
    _KEYPAD_MAP = {
        QtCore.Qt.Key.Key_0: "Keypad 0", QtCore.Qt.Key.Key_1: "Keypad 1",
        QtCore.Qt.Key.Key_2: "Keypad 2", QtCore.Qt.Key.Key_3: "Keypad 3",
        QtCore.Qt.Key.Key_4: "Keypad 4", QtCore.Qt.Key.Key_5: "Keypad 5",
        QtCore.Qt.Key.Key_6: "Keypad 6", QtCore.Qt.Key.Key_7: "Keypad 7",
        QtCore.Qt.Key.Key_8: "Keypad 8", QtCore.Qt.Key.Key_9: "Keypad 9",
        QtCore.Qt.Key.Key_Slash: "Keypad /", QtCore.Qt.Key.Key_Asterisk: "Keypad *",
        QtCore.Qt.Key.Key_Minus: "Keypad -", QtCore.Qt.Key.Key_Plus: "Keypad +",
        QtCore.Qt.Key.Key_Enter: "Keypad Enter",
        QtCore.Qt.Key.Key_Period: "Keypad .",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click here, then press a key...")
        self._hid_name: str = ""

    def hidName(self) -> str:
        """Return the captured HID key name (e.g. 'Keypad 1', 'A')."""
        return self._hid_name

    def setHidName(self, name: str) -> None:
        """Set the key name programmatically (e.g. from device read)."""
        self._hid_name = name
        self.setText(name)

    def clear(self) -> None:
        self._hid_name = ""
        super().clear()

    def isEmpty(self) -> bool:
        return not self._hid_name

    # Qt reports a generic Key_Shift/Control/Alt/Meta value for both sides.
    # X11/XKB usually exposes evdev + 8 here, while native Wayland backends may
    # expose the evdev code itself.  Only consult these maps for an actual Qt
    # modifier key, so overlapping ordinary-key scan codes cannot be mistaken
    # for modifiers.
    _RIGHT_MOD_SCANCODES = {
        62: "Right Shift",   # X11 keycode for Right Shift
        105: "Right Ctrl",   # X11 keycode for Right Ctrl
        108: "Right Alt",    # X11 keycode for Right Alt
        134: "Right GUI",    # X11 keycode for Right Super
        54: "Right Shift",   # Linux evdev KEY_RIGHTSHIFT
        97: "Right Ctrl",    # Linux evdev KEY_RIGHTCTRL
        100: "Right Alt",    # Linux evdev KEY_RIGHTALT
        126: "Right GUI",    # Linux evdev KEY_RIGHTMETA
    }
    _RIGHT_MOD_NATIVE_KEYS = {
        0xFFE2: "Right Shift",  # XK_Shift_R
        0xFFE4: "Right Ctrl",   # XK_Control_R
        0xFFEA: "Right Alt",    # XK_Alt_R
        0xFFEC: "Right GUI",    # XK_Super_R
    }

    @classmethod
    def modifier_name_for_event(cls, event: QtGui.QKeyEvent) -> str | None:
        """Return a side-aware modifier name for a Qt key event."""
        key = event.key()
        altgr_key = getattr(QtCore.Qt.Key, "Key_AltGr", None)
        modifier_defaults = {
            QtCore.Qt.Key.Key_Shift: "Left Shift",
            QtCore.Qt.Key.Key_Control: "Left Ctrl",
            QtCore.Qt.Key.Key_Alt: "Left Alt",
            QtCore.Qt.Key.Key_Meta: "Left GUI",
        }
        if altgr_key is not None:
            modifier_defaults[altgr_key] = "Right Alt"
        if key not in modifier_defaults:
            return None

        native_name = cls._RIGHT_MOD_NATIVE_KEYS.get(event.nativeVirtualKey())
        scan_name = cls._RIGHT_MOD_SCANCODES.get(event.nativeScanCode())
        if altgr_key is not None and key == altgr_key:
            expected_family = "Alt"
        else:
            expected_family = {
                QtCore.Qt.Key.Key_Shift: "Shift",
                QtCore.Qt.Key.Key_Control: "Ctrl",
                QtCore.Qt.Key.Key_Alt: "Alt",
                QtCore.Qt.Key.Key_Meta: "GUI",
            }[key]
        for candidate in (native_name, scan_name):
            if candidate and expected_family in candidate:
                return candidate
        return modifier_defaults[key]

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()

        # Check for right-side modifiers via native scan/virtual-key metadata.
        modifier_name = self.modifier_name_for_event(event)
        if modifier_name:
            name = modifier_name
        elif bool(mods & QtCore.Qt.KeyboardModifier.KeypadModifier) and key in self._KEYPAD_MAP:
            name = self._KEYPAD_MAP[key]
        else:
            name = self._QT_TO_HID.get(key, "")

        if name:
            self._hid_name = name
            self.setText(name)
            self.keyChanged.emit()


class BatteryQueryThread(QtCore.QThread):
    """Run the short status exchange without blocking the Qt event loop."""

    completed = QtCore.pyqtSignal(object, str)

    def __init__(self, path: bytes | str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self) -> None:
        device = vp.VenusDevice(self.path)
        status = None
        error = ""
        try:
            device.open()
            status = device.query_status()
        except Exception as exc:
            error = str(exc)
        finally:
            try:
                device.close()
            except Exception:
                pass
        self.completed.emit(status, error)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Venus Pro Config")
        self.resize(1400, 850)
        
        # Set Application Icon
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))
        
        # Identity for Taskbar
        app = QtWidgets.QApplication.instance()
        if app:
            app.setDesktopFileName("com.github.es00bac.venusprolinux")

        # Store device path instead of keeping device open (prevents blocking mouse input)
        self.device_path: bytes | str | None = None
        self.device_infos: list[vp.DeviceInfo] = []
        self.device_type: str = 'venus_pro'  # 'venus_pro' or 'holtek'
        self.holtek_profile: int = 0  # 0-4, selected hardware profile for Holtek device
        self.holtek_dpi_colors: list[int] = []
        self.active_button_profiles: dict = vp.BUTTON_PROFILES
        self.custom_profiles: dict[str, tuple[int, int, int]] = {}
        self.button_assignments: dict[str, dict] = {} # Stored button settings from device
        self._battery_thread: BatteryQueryThread | None = None
        self._quitting = False
        self._tray_notice_shown = False
        self._shutdown_restore_done = False
        self._last_battery_led_level: int | None = None
        self._last_battery_status: tuple[int, bool] | None = None
        self._battery_led_restore: dict[str, int] | None = None
        self.battery_led_enabled = False
        self._config_errors: list[str] = []
        
        # Load macro names from config EARLY (before UI build)
        self.config_dir = Path.home() / ".config" / "venus_pro_linux"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.macro_config_file = self.config_dir / "macros.json"
        self.settings_file = self.config_dir / "settings.json"
        self.macro_names: dict[int, str] = {}
        self._load_macro_names()
        self._load_app_settings()


        root = QtWidgets.QWidget()
        self.setCentralWidget(root)

        main_layout = QtWidgets.QHBoxLayout(root)

        left_panel = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_panel, stretch=3)

        right_panel = QtWidgets.QVBoxLayout()
        main_layout.addLayout(right_panel, stretch=2)

        left_panel.addWidget(self._build_connection_group())
        left_panel.addWidget(self._build_tabs(), stretch=1)

        right_panel.addWidget(self._build_mouse_image())
        right_panel.addWidget(self._build_log(), stretch=1)
        
        self.custom_profiles = {}  # key -> (code_hi, code_lo, apply_offset)
        self.current_edit_key = None
        self._populating_editor = False
        self.button_assignments = {}
        
        # Staging & Transaction
        self.staging_manager = StagingManager()
        # Note: device/protocol passed later when needed, or we refactor TransactionController to take them at exec time?
        # Current TransactionController takes them at init. 
        # But device path changes. So we might need to instantiate controller on demand or update it.
        # Let's instantiate controller on demand in _commit_changes for now.
        
        self._initialize_default_assignments()
        self._setup_tray()

        for message in self._config_errors:
            self._log(message)
        self._config_errors.clear()

        self._log("Init: Refreshing and connecting...")
        
        # The initial read runs before main() shows this window.  It must not
        # create a modal message box, otherwise opening the parent from the
        # tray exposes a completely disabled-looking interface.
        self._refresh_and_connect(silent=True)
        
        # Keyboard shortcuts for Undo/Redo
        undo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self._on_undo)
        redo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Redo, self)
        redo_shortcut.activated.connect(self._on_redo)
        if app:
            app.aboutToQuit.connect(self._on_app_quit)


    def _build_connection_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Device Status")
        layout = QtWidgets.QHBoxLayout(group)

        self.status_label = QtWidgets.QLabel("Searching...")
        layout.addWidget(self.status_label)
        
        self.refresh_button = QtWidgets.QPushButton("⟳ Reconnect/Refresh")
        layout.addWidget(self.refresh_button)
        
        self.read_button = QtWidgets.QPushButton("📥 Read Settings")
        layout.addWidget(self.read_button)
        
        self.export_button = QtWidgets.QPushButton("💾 Export Profile")
        layout.addWidget(self.export_button)
        
        self.import_button = QtWidgets.QPushButton("📂 Import Profile")
        layout.addWidget(self.import_button)
        
        # Holtek profile selector (only visible when Holtek device connected)
        self.profile_label = QtWidgets.QLabel("Profile:")
        self.profile_label.setVisible(False)
        layout.addWidget(self.profile_label)

        self.profile_combo = QtWidgets.QComboBox()
        for i in range(5):
            self.profile_combo.addItem(f"Profile {i + 1}", i)
        self.profile_combo.setVisible(False)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        layout.addWidget(self.profile_combo)

        # Reclaim button (for busy devices)
        self.reclaim_button = QtWidgets.QPushButton("⚡ Reclaim Device")
        self.reclaim_button.setToolTip("Attempts to reclaim the device from Wine/VM by re-attaching host drivers.")
        self.reclaim_button.clicked.connect(self._reclaim_device)
        layout.addWidget(self.reclaim_button)

        # Hidden combo for logic, but not needed for user interaction mostly
        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.setVisible(False)

        self.refresh_button.clicked.connect(
            lambda _checked=False: self._refresh_and_connect(silent=False))
        self.read_button.clicked.connect(
            lambda _checked=False: self._read_settings(silent=False))
        self.export_button.clicked.connect(self._export_profile)
        self.import_button.clicked.connect(self._import_profile)
        
        # Factory Reset button
        self.reset_button = QtWidgets.QPushButton("⚠️ Factory Reset")
        self.reset_button.setStyleSheet(
            "QPushButton { background-color: #cc4444; color: white; "
            "font-weight: bold; padding: 8px; }"
            "QPushButton:disabled { background-color: palette(mid); "
            "color: palette(disabled-text); }")
        self.reset_button.clicked.connect(self._factory_reset)
        layout.addWidget(self.reset_button)

        # Remove old connect/disconnect/reset buttons from here

        return group


    def _build_tabs(self) -> QtWidgets.QTabWidget:
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._build_buttons_tab(), "Buttons")
        tabs.addTab(self._build_macros_tab(), "Macros")
        tabs.addTab(self._build_rgb_tab(), "RGB")
        tabs.addTab(self._build_polling_tab(), "Polling")
        tabs.addTab(self._build_dpi_tab(), "DPI")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        self.tabs = tabs
        return tabs

    def _build_buttons_tab(self) -> QtWidgets.QWidget:
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # --- Left: Button List ---
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_table = QtWidgets.QTableWidget()
        self.btn_table.setColumnCount(2)
        self.btn_table.setHorizontalHeaderLabels(["Button", "Current Assignment"])
        self.btn_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.btn_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.btn_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.btn_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.btn_table.verticalHeader().setVisible(False)
        
        # Populate rows
        # Sort by button number (Side 1-12, then others)
        self.sorted_btn_keys = sorted(vp.BUTTON_PROFILES.keys(), key=lambda k: int(k.split()[1]))
        self.btn_table.setRowCount(len(self.sorted_btn_keys))
        
        for i, key in enumerate(self.sorted_btn_keys):
            profile = vp.BUTTON_PROFILES[key]
            item_name = QtWidgets.QTableWidgetItem(profile.label)
            item_name.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            item_name.setFlags(item_name.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.btn_table.setItem(i, 0, item_name)
            
            item_assign = QtWidgets.QTableWidgetItem("Unknown (Read to update)")
            item_assign.setFlags(item_assign.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.btn_table.setItem(i, 1, item_assign)
            
        self.btn_table.itemSelectionChanged.connect(self._on_btn_table_select)
        left_layout.addWidget(self.btn_table)
        
        # --- Binding Feedback Panel ---
        feedback_group = QtWidgets.QGroupBox("Binding Preview")
        feedback_group.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 10px; }")
        feedback_layout = QtWidgets.QHBoxLayout(feedback_group)
        feedback_layout.setContentsMargins(10, 5, 10, 5)
        
        self.feedback_button_label = QtWidgets.QLabel("Button: -")
        self.feedback_button_label.setStyleSheet("font-size: 12px;")
        self.feedback_action_label = QtWidgets.QLabel("Action: -")
        self.feedback_action_label.setStyleSheet("font-size: 12px; color: #00D4AA;")
        
        feedback_layout.addWidget(self.feedback_button_label)
        feedback_layout.addWidget(QtWidgets.QLabel("→"))
        feedback_layout.addWidget(self.feedback_action_label)
        feedback_layout.addStretch()
        
        left_layout.addWidget(feedback_group)
        
        # --- Right: Editor ---
        right_widget = QtWidgets.QWidget()
        self.editor_layout = QtWidgets.QVBoxLayout(right_widget)
        self.editor_layout.setContentsMargins(10, 0, 0, 0)
        
        # Reverse map for key names
        # Preserve first mapping to avoid macro-only "Shift" (0x20) overriding "3".
        self.HID_USAGE_TO_NAME = {}
        for key_name, code in vp.HID_KEY_USAGE.items():
            if code not in self.HID_USAGE_TO_NAME:
                self.HID_USAGE_TO_NAME[code] = key_name
        
        self.editor_label = QtWidgets.QLabel("Select a button to edit")

        self.editor_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.editor_layout.addWidget(self.editor_label)
        
        self.action_select = QtWidgets.QComboBox()
        self.action_select.addItems([
            "Keyboard Key", "Left Click", "Right Click", "Middle Click", 
            "Forward", "Back", "Macro",
            "Fire Key", "Triple Click", "Media Key", "RGB Toggle", 
            "Polling Rate Toggle", "DPI Control", "Disabled"
        ])
        self.editor_layout.addWidget(QtWidgets.QLabel("Action:"))
        self.editor_layout.addWidget(self.action_select)
        
        # -- Editor Groups (same as before) --
        # 1. Keyboard
        self.key_group = QtWidgets.QWidget()
        key_group_layout = QtWidgets.QVBoxLayout(self.key_group)
        key_group_layout.setContentsMargins(0, 0, 0, 0)
        self.key_select = KeyCaptureEdit()
        self.special_key_combo = QtWidgets.QComboBox()
        self.special_key_combo.addItem("Select special key...", None)
        self.special_key_names = [
            "F13", "F14", "F15", "F16", "F17", "F18", "F19", "F20", "F21", "F22", "F23", "F24",
            "PrintScreen", "ScrollLock", "Pause", "Insert", "Home", "PageUp", "Delete", "End", "PageDown",
            "NumLock", "Menu",
            "Left Shift", "Left Ctrl", "Left Alt", "Left GUI",
            "Right Shift", "Right Ctrl", "Right Alt", "Right GUI",
            "Keypad /", "Keypad *", "Keypad -", "Keypad +", "Keypad Enter", "Keypad .",
            "Keypad 0", "Keypad 1", "Keypad 2", "Keypad 3", "Keypad 4",
            "Keypad 5", "Keypad 6", "Keypad 7", "Keypad 8", "Keypad 9",
        ]
        for key_name in self.special_key_names:
            if key_name in vp.HID_KEY_USAGE:
                self.special_key_combo.addItem(key_name, key_name)
        self.special_key_combo.currentIndexChanged.connect(self._on_special_key_select)
        self.key_select.keyChanged.connect(self._clear_special_key_selection)
        self.modifier_label = QtWidgets.QLabel("Modifiers:")
        self.mod_ctrl = QtWidgets.QCheckBox("Ctrl")
        self.mod_shift = QtWidgets.QCheckBox("Shift")
        self.mod_alt = QtWidgets.QCheckBox("Alt")
        self.mod_win = QtWidgets.QCheckBox("Win")
        mod_layout = QtWidgets.QHBoxLayout()
        mod_layout.addWidget(self.mod_ctrl); mod_layout.addWidget(self.mod_shift)
        mod_layout.addWidget(self.mod_alt); mod_layout.addWidget(self.mod_win)
        mod_layout.addStretch()
        key_group_layout.addWidget(QtWidgets.QLabel("Key:"))
        key_group_layout.addWidget(self.key_select)
        key_group_layout.addWidget(QtWidgets.QLabel("Special Keys:"))
        key_group_layout.addWidget(self.special_key_combo)
        key_group_layout.addWidget(self.modifier_label)
        key_group_layout.addLayout(mod_layout)
        
        # 2. Macro
        self.macro_group = QtWidgets.QWidget()
        macro_layout = QtWidgets.QFormLayout(self.macro_group)
        self.macro_index_spin = QtWidgets.QSpinBox()
        self.macro_index_spin.setRange(1, 16)
        macro_layout.addRow("Macro Index:", self.macro_index_spin)
        
        # Macro Repeat Mode
        self.macro_repeat_combo = QtWidgets.QComboBox()
        self.macro_repeat_combo.addItem("Run Once", vp.MACRO_REPEAT_ONCE)
        self.macro_repeat_combo.addItem("Repeat Count", 0x02) # Sentinel for count
        self.macro_repeat_combo.addItem("Repeat While Held", vp.MACRO_REPEAT_HOLD)
        self.macro_repeat_combo.addItem("Loop Until Toggle", vp.MACRO_REPEAT_TOGGLE)
        macro_layout.addRow("Repeat Mode:", self.macro_repeat_combo)
        
        self.macro_repeat_count = QtWidgets.QSpinBox()
        self.macro_repeat_count.setRange(1, 253)
        self.macro_repeat_count.setVisible(False)
        macro_layout.addRow("Repeat Count:", self.macro_repeat_count)
        
        self.macro_repeat_combo.currentIndexChanged.connect(
            lambda: self.macro_repeat_count.setVisible(self.macro_repeat_combo.currentData() == 0x02)
        )
        self.macro_repeat_count.valueChanged.connect(self._auto_stage_binding)

        # Macro Recall
        self.load_macro_btn = QtWidgets.QPushButton("Load from Slot")
        self.load_macro_btn.clicked.connect(self._load_macro_from_slot)
        macro_layout.addRow("Recall:", self.load_macro_btn)
        
        # 3. Special
        self.special_group = QtWidgets.QWidget()
        special_layout = QtWidgets.QHBoxLayout(self.special_group)
        self.special_delay_spin = QtWidgets.QSpinBox()
        self.special_delay_spin.setRange(0, 255); self.special_delay_spin.setValue(40); self.special_delay_spin.setSuffix(" ms")
        self.special_repeat_spin = QtWidgets.QSpinBox()
        self.special_repeat_spin.setRange(0, 255); self.special_repeat_spin.setValue(3)
        self.special_delay_label = QtWidgets.QLabel("Delay:")
        special_layout.addWidget(self.special_delay_label); special_layout.addWidget(self.special_delay_spin)
        special_layout.addWidget(QtWidgets.QLabel("Repeats:")); special_layout.addWidget(self.special_repeat_spin)

        # 4. Media
        self.media_group = QtWidgets.QWidget()
        media_layout = QtWidgets.QHBoxLayout(self.media_group)
        self.media_select = QtWidgets.QComboBox()
        for key in sorted(vp.MEDIA_KEY_CODES.keys()):
            self.media_select.addItem(key, vp.MEDIA_KEY_CODES[key])
        media_layout.addWidget(QtWidgets.QLabel("Media Function:")); media_layout.addWidget(self.media_select)

        # 5. DPI Control Group
        self.dpi_group = QtWidgets.QWidget()
        dpi_layout = QtWidgets.QHBoxLayout(self.dpi_group)
        self.dpi_action_select = QtWidgets.QComboBox()
        self.dpi_action_select.addItem("DPI Loop", 0x01) # D1=01
        self.dpi_action_select.addItem("DPI +", 0x02)    # D1=02
        self.dpi_action_select.addItem("DPI -", 0x03)    # D1=03
        dpi_layout.addWidget(QtWidgets.QLabel("DPI Function:"))
        dpi_layout.addWidget(self.dpi_action_select)
        
        # Add groups
        self.editor_layout.addWidget(self.key_group)
        self.editor_layout.addWidget(self.macro_group)
        self.editor_layout.addWidget(self.special_group)
        self.editor_layout.addWidget(self.media_group)
        self.editor_layout.addWidget(self.dpi_group)
        
        self.apply_button = QtWidgets.QPushButton("Stage Binding")
        self.apply_button.setStyleSheet("font-weight: bold; padding: 5px;")
        self.apply_button.setToolTip("Queue this change. You must click 'Apply All Changes' to write to device.")
        self.apply_button.clicked.connect(self._apply_button_binding)
        self.editor_layout.addWidget(self.apply_button)

        # Batch Actions
        batch_group = QtWidgets.QGroupBox("Batch Actions")
        batch_layout = QtWidgets.QHBoxLayout(batch_group)
        
        self.apply_all_button = QtWidgets.QPushButton("Apply All Changes")
        self.apply_all_button.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-weight: bold; padding: 5px; }"
            "QPushButton:disabled { background-color: palette(mid); "
            "color: palette(disabled-text); }")
        self.apply_all_button.setToolTip("Write all staged changes to the device memory.")
        self.apply_all_button.clicked.connect(self._commit_staged_changes)
        self.apply_all_button.setEnabled(False) # Default disabled
        
        self.discard_all_button = QtWidgets.QPushButton("Discard All")
        self.discard_all_button.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; "
            "font-weight: bold; padding: 5px; }"
            "QPushButton:disabled { background-color: palette(mid); "
            "color: palette(disabled-text); }")
        self.discard_all_button.setToolTip("Clear all pending changes and revert to current device state.")
        self.discard_all_button.clicked.connect(self._discard_staged_changes)
        self.discard_all_button.setEnabled(False)
        
        batch_layout.addWidget(self.apply_all_button)
        batch_layout.addWidget(self.discard_all_button)
        self.editor_layout.addWidget(batch_group)

        # Advanced / Custom Offsets (Restored for logic compatibility)
        self.advanced_group = QtWidgets.QGroupBox("Advanced / Custom Offsets")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        adv_layout = QtWidgets.QFormLayout(self.advanced_group)
        self.code_hi_spin = QtWidgets.QSpinBox(); self.code_hi_spin.setRange(0, 255); self.code_hi_spin.setDisplayIntegerBase(16); self.code_hi_spin.setPrefix("0x")
        self.code_lo_spin = QtWidgets.QSpinBox(); self.code_lo_spin.setRange(0, 255); self.code_lo_spin.setDisplayIntegerBase(16); self.code_lo_spin.setPrefix("0x")
        self.apply_offset_spin = QtWidgets.QSpinBox(); self.apply_offset_spin.setRange(0, 255); self.apply_offset_spin.setDisplayIntegerBase(16); self.apply_offset_spin.setPrefix("0x")
        adv_layout.addRow("Code Hi:", self.code_hi_spin)
        adv_layout.addRow("Code Lo:", self.code_lo_spin)
        adv_layout.addRow("Apply Offset:", self.apply_offset_spin)
        self.editor_layout.addWidget(self.advanced_group)
        
        self.editor_layout.addStretch()


        # Connects
        self.action_select.currentTextChanged.connect(self._update_bind_ui)

        # Auto-stage on any editor change
        self.action_select.currentTextChanged.connect(self._auto_stage_binding)
        self.key_select.keyChanged.connect(self._auto_stage_binding)
        self.special_key_combo.currentIndexChanged.connect(self._auto_stage_binding)
        self.mod_ctrl.stateChanged.connect(self._auto_stage_binding)
        self.mod_shift.stateChanged.connect(self._auto_stage_binding)
        self.mod_alt.stateChanged.connect(self._auto_stage_binding)
        self.mod_win.stateChanged.connect(self._auto_stage_binding)
        self.macro_index_spin.valueChanged.connect(self._auto_stage_binding)
        self.macro_repeat_combo.currentIndexChanged.connect(self._auto_stage_binding)
        self.media_select.currentIndexChanged.connect(self._auto_stage_binding)
        self.dpi_action_select.currentIndexChanged.connect(self._auto_stage_binding)
        self.special_delay_spin.valueChanged.connect(self._auto_stage_binding)
        self.special_repeat_spin.valueChanged.connect(self._auto_stage_binding)

        # All supported controls have fixed protocol offsets. Keep the old
        # raw-offset widgets available to the implementation, but do not show
        # a non-functional custom-offset editor in the normal interface.
        self.advanced_group.setVisible(False)
        self._update_bind_ui(self.action_select.currentText())
        self.right_panel_enabled(False)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        return splitter

    def _on_btn_table_select(self) -> None:
        """Handle button selection in the table."""
        rows = self.btn_table.selectionModel().selectedRows()
        if not rows:
            self.right_panel_enabled(False)
            self.current_edit_key = None
            return
            
        row = rows[0].row()
        key = self.btn_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
        label = self.btn_table.item(row, 0).text()
        
        self.editor_label.setText(f"Editing: {label}")
        self.current_edit_key = key # Store for apply
        self.right_panel_enabled(True)
        
        # Update Advanced / Custom Offsets UI
        if key in self.active_button_profiles:
            p = self.active_button_profiles[key]
            self.code_hi_spin.blockSignals(True)
            self.code_lo_spin.blockSignals(True)
            self.apply_offset_spin.blockSignals(True)

            if self.device_type == 'holtek':
                # Holtek uses index-based addressing, show index in offset
                self.code_hi_spin.setValue(0)
                self.code_lo_spin.setValue(0)
                self.apply_offset_spin.setValue(p.index)
            else:
                self.code_hi_spin.setValue(p.code_hi or 0)
                self.code_lo_spin.setValue(p.code_lo or 0)
                self.apply_offset_spin.setValue(p.apply_offset or 0)

            self.code_hi_spin.blockSignals(False)
            self.code_lo_spin.blockSignals(False)
            self.apply_offset_spin.blockSignals(False)

            self.code_hi_spin.setEnabled(False)
            self.code_lo_spin.setEnabled(False)
            self.apply_offset_spin.setEnabled(False)
        else:
            custom = self.custom_profiles.get(key)
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
        
        # Populate editor from current assignment
        self._update_ui_from_assignment(key)
        
        # Update Binding Preview Panel
        self.feedback_button_label.setText(f"Button: {label}")
        effective = self.staging_manager.get_effective_state(key)
        if effective:
            action_desc = self._get_binding_description(effective.get("action", ""), effective.get("params", {}))
            self.feedback_action_label.setText(f"Action: {action_desc}")
        else:
            self.feedback_action_label.setText("Action: Not configured")


    def right_panel_enabled(self, enabled: bool) -> None:
        for widget in (
                self.action_select, self.key_group, self.macro_group,
                self.special_group, self.media_group, self.dpi_group,
                self.apply_button):
            widget.setEnabled(enabled)
        
    def _update_ui_from_assignment(self, button_key: str) -> None:
        """Update editor UI from effective assignment (staged if pending, else base)."""
        self._populating_editor = True
        try:
            self._update_ui_from_assignment_inner(button_key)
        finally:
            self._populating_editor = False

    def _update_ui_from_assignment_inner(self, button_key: str) -> None:
        assign = self.staging_manager.get_effective_state(button_key)
        if assign is None:
            if button_key not in self.button_assignments:
                return
            assign = self.button_assignments[button_key]
        action = assign["action"]
        params = assign["params"]
        
        self.action_select.blockSignals(True)
        for item_index in reversed(range(self.action_select.count())):
            if (self.action_select.itemData(item_index)
                    == "__preserve_unknown__"):
                self.action_select.removeItem(item_index)
        idx = self.action_select.findText(action)
        if idx >= 0:
            self.action_select.setCurrentIndex(idx)
        else:
            self.action_select.addItem(
                f"Unsupported: {action} (choose a replacement)",
                "__preserve_unknown__")
            self.action_select.setCurrentIndex(self.action_select.count() - 1)
        
        self._update_bind_ui(self.action_select.currentText())
        self.action_select.blockSignals(False)
        
        if action == "Keyboard Key":
            hid_key = params.get("key", 0)
            mod = params.get("mod", 0)
            
            key_name = self.HID_USAGE_TO_NAME.get(hid_key, "")
            if key_name:
                if key_name in self.special_key_names:
                    self.special_key_combo.blockSignals(True)
                    idx = self.special_key_combo.findData(key_name)
                    if idx >= 0:
                        self.special_key_combo.setCurrentIndex(idx)
                    self.special_key_combo.blockSignals(False)
                    self.key_select.clear()
                else:
                    self.special_key_combo.blockSignals(True)
                    self.special_key_combo.setCurrentIndex(0)
                    self.special_key_combo.blockSignals(False)
                    self.key_select.setHidName(key_name)
            else:
                self.key_select.clear()
            
            self.mod_ctrl.setChecked(bool(mod & vp.MODIFIER_CTRL))
            self.mod_shift.setChecked(bool(mod & vp.MODIFIER_SHIFT))
            self.mod_alt.setChecked(bool(mod & vp.MODIFIER_ALT))
            self.mod_win.setChecked(bool(mod & vp.MODIFIER_WIN))
        elif action == "Macro":
            self.macro_index_spin.setValue(params.get("index", 1))
            # Set repeat mode
            mode_data = params.get("mode", vp.MACRO_REPEAT_ONCE)
            idx = self.macro_repeat_combo.findData(mode_data)
            if idx >= 0: 
                self.macro_repeat_combo.setCurrentIndex(idx)
            else:
                # If not found, it must be a custom count (1-FD)
                idx_count = self.macro_repeat_combo.findData(0x02)
                if idx_count >= 0: self.macro_repeat_combo.setCurrentIndex(idx_count)
            
            self.macro_repeat_count.setValue(params.get("mode", 1) if isinstance(params.get("mode", 1), int) else 1)
        elif action == "Media Key":
            index = self.media_select.findData(params.get("code", 0))
            if index >= 0:
                self.media_select.setCurrentIndex(index)
        elif action == "DPI Control":
            index = self.dpi_action_select.findData(params.get("func", 1))
            if index >= 0:
                self.dpi_action_select.setCurrentIndex(index)
        elif action in ("Fire Key", "Triple Click"):
            self.special_delay_spin.setValue(params.get("delay", 40))
            self.special_repeat_spin.setValue(params.get("repeat", 3))

    def _update_bind_ui(self, action: str) -> None:
        """Show/hide UI elements based on selected action."""
        self.key_group.setVisible(action == "Keyboard Key")
        self.macro_group.setVisible(action == "Macro")
        self.special_group.setVisible(action in ["Fire Key", "Triple Click"])
        self.media_group.setVisible(action == "Media Key")
        self.dpi_group.setVisible(action == "DPI Control")
        
        # Enable/disable repeat count based on repeat mode
        if action == "Macro":
            mode = self.macro_repeat_combo.currentData()
            self.macro_repeat_count.setVisible(mode == 0x02)
        else:
            self.macro_repeat_count.setVisible(False)

    def _on_special_key_select(self) -> None:
        if self.special_key_combo.currentData():
            self.key_select.clear()

    def _clear_special_key_selection(self) -> None:
        if self.special_key_combo.currentIndex() != 0:
            self.special_key_combo.setCurrentIndex(0)

    def _load_macro_names(self) -> None:
        """Load macro names from local JSON config."""
        if self.macro_config_file.exists():
            try:
                import json
                with open(self.macro_config_file, 'r') as f:
                    data = json.load(f)
                    # Convert keys to int
                    self.macro_names = {int(k): v for k, v in data.items()}
            except Exception as e:
                self._config_errors.append(f"Config: Failed to load macro names: {e}")
        
        # Ensure defaults for missing slots
        for i in range(1, 17):
            if i not in self.macro_names:
                self.macro_names[i] = f"Macro {i}"

    def _save_macro_names(self) -> None:
        """Save macro names to local JSON config."""
        try:
            import json
            with open(self.macro_config_file, 'w') as f:
                json.dump(self.macro_names, f, indent=2)
        except Exception as e:
            self._log(f"Config: Failed to save macro names: {e}")

    def _load_app_settings(self) -> None:
        """Load persistent background-controller preferences."""
        if not self.settings_file.exists():
            return
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("settings root must be an object")
            enabled = bool(data.get("battery_led_enabled", False))
            restore = data.get("battery_led_restore")
            parsed_restore = None
            if isinstance(restore, dict):
                parsed_restore = {
                    "r": max(0, min(255, int(restore.get("r", 255)))),
                    "g": max(0, min(255, int(restore.get("g", 0)))),
                    "b": max(0, min(255, int(restore.get("b", 255)))),
                    "mode": max(0, min(3, int(
                        restore.get("mode", vp.RGB_MODE_STEADY)))),
                    "brightness": max(0, min(100, int(
                        restore.get("brightness", 100)))),
                    "speed": max(vp.RGB_EFFECT_SPEED_MIN,
                                 min(vp.RGB_EFFECT_SPEED_MAX, int(
                                     restore.get(
                                         "speed",
                                         vp.RGB_EFFECT_SPEED_DEFAULT)))),
                }
            self.battery_led_enabled = enabled
            self._battery_led_restore = parsed_restore
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._config_errors.append(f"Config: Failed to load settings: {exc}")

    def _save_app_settings(self) -> None:
        """Persist the battery LED preference and its restore lighting."""
        payload = {
            "battery_led_enabled": self.battery_led_enabled,
            "battery_led_restore": self._battery_led_restore,
        }
        temporary = self.settings_file.with_suffix(".json.tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.settings_file)
        except OSError as exc:
            self._log(f"Config: Failed to save settings: {exc}")

    def _build_macros_tab(self) -> QtWidgets.QWidget:
        """Build the slot-oriented macro editor and text/timing tools."""
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        # Device slots remain visible while the editor changes.  Selecting a
        # slot is local and instant; loading hardware is an explicit action.
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        slot_label = QtWidgets.QLabel("Macro slots")
        slot_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_layout.addWidget(slot_label)
        self.macro_list = QtWidgets.QListWidget()
        self.macro_list.setAlternatingRowColors(True)
        self.macro_list.itemSelectionChanged.connect(self._select_macro_slot)
        self.macro_list.itemDoubleClicked.connect(
            self._load_macro_from_slot_selection)
        left_layout.addWidget(self.macro_list)
        slot_hint = QtWidgets.QLabel(
            "Select a target; double-click to load it from the mouse.")
        slot_hint.setWordWrap(True)
        slot_hint.setStyleSheet("color: palette(mid);")
        left_layout.addWidget(slot_hint)

        self._refresh_macro_list()
        splitter.addWidget(left_widget)

        right_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(right_widget)
        layout.setContentsMargins(10, 0, 0, 0)

        header_layout = QtWidgets.QGridLayout()
        header_layout.addWidget(QtWidgets.QLabel("Slot:"), 0, 0)
        self.macro_bind_index_spin = QtWidgets.QSpinBox()
        self.macro_bind_index_spin.setRange(1, 16)
        self.macro_bind_index_spin.setValue(1)
        self.macro_bind_index_spin.valueChanged.connect(
            self._macro_slot_spin_changed)
        header_layout.addWidget(self.macro_bind_index_spin, 0, 1)
        header_layout.addWidget(QtWidgets.QLabel("Name:"), 0, 2)
        self.macro_name_edit = QtWidgets.QLineEdit("Macro 1")
        self.macro_name_edit.setMaxLength(15)
        self.macro_name_edit.setToolTip(
            "The mouse stores up to 15 UTF-16 code units in a macro name.")
        header_layout.addWidget(self.macro_name_edit, 0, 3, 1, 3)
        self.load_slot_button = QtWidgets.QPushButton("Load from Mouse")
        self.load_slot_button.clicked.connect(self._load_macro_from_slot_on_tab)
        header_layout.addWidget(self.load_slot_button, 0, 6)
        self.save_macro_button = QtWidgets.QPushButton("Save to Mouse")
        self.save_macro_button.setStyleSheet(
            "font-weight: bold; padding: 6px; background-color: #397d43;")
        self.save_macro_button.clicked.connect(self._save_current_macro)
        header_layout.addWidget(self.save_macro_button, 0, 7)
        header_layout.setColumnStretch(3, 1)
        layout.addLayout(header_layout)

        toolbar = QtWidgets.QHBoxLayout()
        self.record_button = QtWidgets.QPushButton("🔴 Record")
        self.record_button.setCheckable(True)
        self.record_button.setStyleSheet(
            "QPushButton:checked { background-color: #b3261e; color: white; }")
        self.record_button.toggled.connect(self._toggle_recording)
        self.stop_record_button = QtWidgets.QPushButton("⏹ Stop")
        self.stop_record_button.setEnabled(False)
        self.stop_record_button.clicked.connect(self._stop_recording)
        self.move_up_button = QtWidgets.QPushButton("▲")
        self.move_up_button.setToolTip("Move selected event up (Alt+Up)")
        self.move_up_button.clicked.connect(self._move_event_up)
        self.move_down_button = QtWidgets.QPushButton("▼")
        self.move_down_button.setToolTip("Move selected event down (Alt+Down)")
        self.move_down_button.clicked.connect(self._move_event_down)
        self.duplicate_event_button = QtWidgets.QPushButton("Duplicate")
        self.duplicate_event_button.clicked.connect(self._duplicate_selected_event)
        self.delete_events_button = QtWidgets.QPushButton("Delete Selected")
        self.delete_events_button.clicked.connect(self._delete_selected_events)
        self.clear_events_button = QtWidgets.QPushButton("Clear All")
        self.clear_events_button.clicked.connect(self._clear_macro_events)

        for widget in (
                self.record_button, self.stop_record_button,
                self.move_up_button, self.move_down_button,
                self.duplicate_event_button, self.delete_events_button,
                self.clear_events_button):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._recording = False
        self._last_key_time: float = 0.0

        self.macro_event_table = QtWidgets.QTableWidget()
        self.macro_event_table.setColumnCount(5)
        self.macro_event_table.setHorizontalHeaderLabels(
            ["#", "Event", "Action", "Delay after", ""])
        header = self.macro_event_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.macro_event_table.setColumnWidth(0, 35)
        self.macro_event_table.setColumnWidth(2, 75)
        self.macro_event_table.setColumnWidth(3, 105)
        self.macro_event_table.setColumnWidth(4, 38)
        self.macro_event_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.macro_event_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.macro_event_table.setAlternatingRowColors(True)
        self.macro_event_table.verticalHeader().setVisible(False)
        self.macro_event_table.setMinimumHeight(230)
        layout.addWidget(self.macro_event_table, stretch=3)

        self.macro_capacity_bar = QtWidgets.QProgressBar()
        self.macro_capacity_bar.setRange(0, vp.MACRO_MAX_EVENTS)
        self.macro_capacity_bar.setValue(0)
        self.macro_capacity_bar.setFormat(
            f"%v / {vp.MACRO_MAX_EVENTS} hardware events")
        layout.addWidget(self.macro_capacity_bar)

        builder_tabs = QtWidgets.QTabWidget()
        self.macro_builder_tabs = builder_tabs

        text_builder = QtWidgets.QWidget()
        text_layout = QtWidgets.QGridLayout(text_builder)
        self.quick_text_edit = QtWidgets.QPlainTextEdit()
        self.quick_text_edit.setPlaceholderText(
            "Type text to convert into hardware key presses (US keyboard layout)…")
        self.quick_text_edit.setMaximumHeight(72)
        self.quick_text_edit.textChanged.connect(
            self._update_text_macro_requirements)
        text_layout.addWidget(self.quick_text_edit, 0, 0, 1, 8)

        text_layout.addWidget(QtWidgets.QLabel("Timing:"), 1, 0)
        self.text_timing_mode = QtWidgets.QComboBox()
        self.text_timing_mode.addItem("Fixed", "fixed")
        self.text_timing_mode.addItem("Random range", "random")
        self.text_timing_mode.currentIndexChanged.connect(
            self._sync_text_timing_controls)
        text_layout.addWidget(self.text_timing_mode, 1, 1)

        text_layout.addWidget(QtWidgets.QLabel("Key held:"), 1, 2)
        self.text_hold_spin = QtWidgets.QSpinBox()
        self.text_hold_spin.setRange(vp.MACRO_MIN_DELAY_MS, 0xFFFF)
        self.text_hold_spin.setValue(35)
        self.text_hold_spin.setSuffix(" ms")
        self.text_hold_spin.valueChanged.connect(
            self._update_text_macro_requirements)
        text_layout.addWidget(self.text_hold_spin, 1, 3)

        self.text_fixed_delay_label = QtWidgets.QLabel("Between keys:")
        text_layout.addWidget(self.text_fixed_delay_label, 1, 4)
        self.text_fixed_delay_spin = QtWidgets.QSpinBox()
        self.text_fixed_delay_spin.setRange(vp.MACRO_MIN_DELAY_MS, 0xFFFF)
        self.text_fixed_delay_spin.setValue(90)
        self.text_fixed_delay_spin.setSuffix(" ms")
        self.text_fixed_delay_spin.valueChanged.connect(
            self._update_text_macro_requirements)
        text_layout.addWidget(self.text_fixed_delay_spin, 1, 5)

        self.text_random_range_widget = QtWidgets.QWidget()
        random_layout = QtWidgets.QHBoxLayout(self.text_random_range_widget)
        random_layout.setContentsMargins(0, 0, 0, 0)
        random_layout.addWidget(QtWidgets.QLabel("Between:"))
        self.text_random_min_spin = QtWidgets.QSpinBox()
        self.text_random_min_spin.setRange(vp.MACRO_MIN_DELAY_MS, 0xFFFF)
        self.text_random_min_spin.setValue(70)
        self.text_random_min_spin.setSuffix(" ms")
        self.text_random_min_spin.valueChanged.connect(
            self._update_text_macro_requirements)
        random_layout.addWidget(self.text_random_min_spin)
        random_layout.addWidget(QtWidgets.QLabel("to"))
        self.text_random_max_spin = QtWidgets.QSpinBox()
        self.text_random_max_spin.setRange(vp.MACRO_MIN_DELAY_MS, 0xFFFF)
        self.text_random_max_spin.setValue(160)
        self.text_random_max_spin.setSuffix(" ms")
        self.text_random_max_spin.valueChanged.connect(
            self._update_text_macro_requirements)
        random_layout.addWidget(self.text_random_max_spin)
        text_layout.addWidget(self.text_random_range_widget, 1, 4, 1, 2)

        text_layout.addWidget(QtWidgets.QLabel("Extra after spaces:"), 2, 0)
        self.text_word_pause_spin = QtWidgets.QSpinBox()
        self.text_word_pause_spin.setRange(0, 0xFFFF)
        self.text_word_pause_spin.setValue(60)
        self.text_word_pause_spin.setSuffix(" ms")
        self.text_word_pause_spin.valueChanged.connect(
            self._update_text_macro_requirements)
        text_layout.addWidget(self.text_word_pause_spin, 2, 1)
        text_layout.addWidget(QtWidgets.QLabel("Output:"), 2, 2)
        self.text_output_mode = QtWidgets.QComboBox()
        self.text_output_mode.addItem("Replace current events", "replace")
        self.text_output_mode.addItem("Append to current events", "append")
        self.text_output_mode.currentIndexChanged.connect(
            self._update_text_macro_requirements)
        text_layout.addWidget(self.text_output_mode, 2, 3, 1, 2)

        self.gen_text_btn = QtWidgets.QPushButton("Generate Text Events")
        self.gen_text_btn.setStyleSheet("font-weight: bold;")
        self.gen_text_btn.clicked.connect(self._generate_text_macro)
        text_layout.addWidget(self.gen_text_btn, 2, 5, 1, 3)
        self.text_builder_status = QtWidgets.QLabel()
        self.text_builder_status.setWordWrap(True)
        text_layout.addWidget(self.text_builder_status, 3, 0, 1, 8)
        builder_tabs.addTab(text_builder, "Text Builder")

        manual_builder = QtWidgets.QWidget()
        add_layout = QtWidgets.QGridLayout(manual_builder)
        add_layout.addWidget(QtWidgets.QLabel("Event:"), 0, 0)
        self.add_key_combo = QtWidgets.QComboBox()
        self.add_key_combo.addItem("Mouse: Left Button", ("mouse", 0x01))
        self.add_key_combo.addItem("Mouse: Right Button", ("mouse", 0x02))
        self.add_key_combo.addItem("Mouse: Middle Button", ("mouse", 0x04))
        self.add_key_combo.addItem("Mouse: Back Button", ("mouse", 0x08))
        self.add_key_combo.addItem("Mouse: Forward Button", ("mouse", 0x10))
        for modifier_name, modifier_code in vp.MACRO_MODIFIER_CODES.items():
            self.add_key_combo.addItem(
                f"Modifier: {modifier_name}",
                ("modifier", modifier_code),
            )
        self.add_key_combo.insertSeparator(self.add_key_combo.count())
        manual_keys = sorted(
            ((name, code) for code, name in self.HID_USAGE_TO_NAME.items()
             if code < 0xE0 and name != "Shift"),
            key=lambda item: (len(item[0]) > 1, item[0]),
        )
        for key_name, keycode in manual_keys:
            self.add_key_combo.addItem(key_name, ("keyboard", keycode))
        add_layout.addWidget(self.add_key_combo, 0, 1, 1, 3)

        add_layout.addWidget(QtWidgets.QLabel("Action:"), 0, 4)
        self.add_action_combo = QtWidgets.QComboBox()
        self.add_action_combo.addItem("Tap (press + release)", "tap")
        self.add_action_combo.addItem("Press only", "press")
        self.add_action_combo.addItem("Release only", "release")
        self.add_action_combo.currentIndexChanged.connect(
            self._sync_manual_event_controls)
        add_layout.addWidget(self.add_action_combo, 0, 5)

        self.add_hold_label = QtWidgets.QLabel("Held:")
        add_layout.addWidget(self.add_hold_label, 1, 0)
        self.add_hold_spin = QtWidgets.QSpinBox()
        self.add_hold_spin.setRange(vp.MACRO_MIN_DELAY_MS, 0xFFFF)
        self.add_hold_spin.setValue(35)
        self.add_hold_spin.setSuffix(" ms")
        add_layout.addWidget(self.add_hold_spin, 1, 1)
        add_layout.addWidget(QtWidgets.QLabel("Delay after:"), 1, 2)
        self.add_delay_spin = QtWidgets.QSpinBox()
        self.add_delay_spin.setRange(0, 0xFFFF)
        self.add_delay_spin.setValue(90)
        self.add_delay_spin.setSuffix(" ms")
        add_layout.addWidget(self.add_delay_spin, 1, 3)

        self.add_event_button = QtWidgets.QPushButton("Add Event")
        self.add_event_button.setStyleSheet("font-weight: bold;")
        self.add_event_button.clicked.connect(self._add_manual_event)
        add_layout.addWidget(self.add_event_button, 1, 4, 1, 2)

        add_layout.addWidget(QtWidgets.QLabel("Set selected delays:"), 2, 0)
        self.selected_delay_spin = QtWidgets.QSpinBox()
        self.selected_delay_spin.setRange(0, 0xFFFF)
        self.selected_delay_spin.setValue(90)
        self.selected_delay_spin.setSuffix(" ms")
        add_layout.addWidget(self.selected_delay_spin, 2, 1)
        self.apply_selected_delay_button = QtWidgets.QPushButton("Apply")
        self.apply_selected_delay_button.clicked.connect(
            self._apply_delay_to_selected)
        add_layout.addWidget(self.apply_selected_delay_button, 2, 2)
        manual_hint = QtWidgets.QLabel(
            "A delay belongs to the event before it. Tap adds a matched press/release pair.")
        manual_hint.setWordWrap(True)
        manual_hint.setStyleSheet("color: palette(mid);")
        add_layout.addWidget(manual_hint, 2, 3, 1, 3)
        builder_tabs.addTab(manual_builder, "Manual Events")

        builder_tabs.setMaximumHeight(225)
        layout.addWidget(builder_tabs, stretch=1)

        summary_layout = QtWidgets.QHBoxLayout()
        self.macro_preview_label = QtWidgets.QLabel('Output: "" · 0 ms total')
        self.macro_preview_label.setStyleSheet("font-family: monospace; padding: 4px;")
        self.macro_preview_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_layout.addWidget(self.macro_preview_label, stretch=1)
        layout.addLayout(summary_layout)

        bind_group = QtWidgets.QGroupBox("Bind saved slot to a mouse button")
        bind_layout = QtWidgets.QGridLayout(bind_group)
        bind_layout.addWidget(QtWidgets.QLabel("Bind to Button:"), 0, 0)
        self.macro_button_select = QtWidgets.QComboBox()
        for key, profile in vp.BUTTON_PROFILES.items():
            self.macro_button_select.addItem(profile.label, key)
        bind_layout.addWidget(self.macro_button_select, 0, 1)
        bind_layout.addWidget(QtWidgets.QLabel("Repeat:"), 0, 2)
        self.macro_tab_repeat_combo = QtWidgets.QComboBox()
        self.macro_tab_repeat_combo.addItem("Run Once", vp.MACRO_REPEAT_ONCE)
        self.macro_tab_repeat_combo.addItem("Repeat While Held", vp.MACRO_REPEAT_HOLD)
        self.macro_tab_repeat_combo.addItem("Toggle Loop", vp.MACRO_REPEAT_TOGGLE)
        self.macro_tab_repeat_combo.addItem("Repeat Count", vp.MACRO_REPEAT_COUNT)
        bind_layout.addWidget(self.macro_tab_repeat_combo, 0, 3)

        bind_layout.addWidget(QtWidgets.QLabel("Count:"), 0, 4)
        self.macro_tab_repeat_count_spin = QtWidgets.QSpinBox()
        self.macro_tab_repeat_count_spin.setRange(1, 253)
        self.macro_tab_repeat_count_spin.setValue(1)
        self.macro_tab_repeat_count_spin.setEnabled(False)
        bind_layout.addWidget(self.macro_tab_repeat_count_spin, 0, 5)
        self.macro_tab_repeat_combo.currentIndexChanged.connect(
            lambda: self.macro_tab_repeat_count_spin.setEnabled(self.macro_tab_repeat_combo.currentData() == vp.MACRO_REPEAT_COUNT)
        )
        self.bind_macro_button = QtWidgets.QPushButton("Bind Slot")
        self.bind_macro_button.clicked.connect(self._bind_macro_to_button)
        bind_layout.addWidget(self.bind_macro_button, 0, 6)
        bind_layout.setColumnStretch(1, 1)

        layout.addWidget(bind_group)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([210, 850])

        QtGui.QShortcut(QtGui.QKeySequence("Delete"), self.macro_event_table).activated.connect(
            self._delete_selected_events)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+D"), self.macro_event_table).activated.connect(
            self._duplicate_selected_event)
        QtGui.QShortcut(QtGui.QKeySequence("Alt+Up"), self.macro_event_table).activated.connect(
            self._move_event_up)
        QtGui.QShortcut(QtGui.QKeySequence("Alt+Down"), self.macro_event_table).activated.connect(
            self._move_event_down)

        self._sync_text_timing_controls()
        self._sync_manual_event_controls()
        self._update_text_macro_requirements()
        self._update_macro_preview()
        self.macro_list.setCurrentRow(0)

        return splitter

    def _refresh_macro_list(self) -> None:
        """Refresh the macro list widget."""
        selected = (self.macro_bind_index_spin.value()
                    if hasattr(self, "macro_bind_index_spin") else 1)
        self.macro_list.clear()
        for i in range(1, 17):
            name = self.macro_names.get(i, f"Macro {i}")
            item = QtWidgets.QListWidgetItem(f"{i}: {name}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, i)
            self.macro_list.addItem(item)
        if self.macro_list.count():
            self.macro_list.setCurrentRow(max(0, min(15, selected - 1)))

    def _select_macro_slot(
            self, item: QtWidgets.QListWidgetItem | None = None) -> None:
        """Select a local slot without performing surprise hardware I/O."""
        item = item or self.macro_list.currentItem()
        if item is None or not hasattr(self, "macro_bind_index_spin"):
            return
        index = int(item.data(QtCore.Qt.ItemDataRole.UserRole))
        self.macro_bind_index_spin.blockSignals(True)
        self.macro_bind_index_spin.setValue(index)
        self.macro_bind_index_spin.blockSignals(False)
        self.macro_name_edit.setText(
            self.macro_names.get(index, f"Macro {index}"))

    def _macro_slot_spin_changed(self, index: int) -> None:
        """Keep the macro editor's slot list and name synchronized."""
        if hasattr(self, "macro_list") and self.macro_list.count() >= index:
            self.macro_list.blockSignals(True)
            self.macro_list.setCurrentRow(index - 1)
            self.macro_list.blockSignals(False)
        self.macro_name_edit.setText(
            self.macro_names.get(index, f"Macro {index}"))

    def _load_macro_from_slot_selection(self, item: QtWidgets.QListWidgetItem) -> None:
        """Load a double-clicked macro slot from hardware."""
        self._select_macro_slot(item)
        index = int(item.data(QtCore.Qt.ItemDataRole.UserRole))
        self._load_macro_from_slot(index)

    def _save_current_macro(self) -> None:
        """Save current macro: Check Name -> Upload -> Save Config."""
        name = self.macro_name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid Name", "Macro name cannot be empty.")
            return
        if len(name.encode("utf-16-le")) > 30:
            QtWidgets.QMessageBox.warning(
                self, "Name Too Long",
                "A hardware macro name can contain at most 15 UTF-16 code "
                "units. Shorten the name before saving.")
            return

        index = self.macro_bind_index_spin.value() # Use the target slot
        
        # Unique Name Check
        for i, existing_name in self.macro_names.items():
            if i != index and existing_name.lower() == name.lower():
                 QtWidgets.QMessageBox.warning(self, "Duplicate Name", f"Macro name '{name}' is already used by Slot {i}.")
                 return
        
        # Upload to Device
        if self._upload_macro():  # Uses macro_bind_index_spin.
            self.macro_names[index] = name
            self._save_macro_names()
            self._refresh_macro_list()
            self._log(f"Macro '{name}' saved to slot {index}")

    def _toggle_recording(self, checked: bool) -> None:
        """Start or stop macro recording."""
        if checked:
            if self.macro_event_table.rowCount() >= vp.MACRO_MAX_EVENTS:
                self.record_button.blockSignals(True)
                self.record_button.setChecked(False)
                self.record_button.blockSignals(False)
                self._set_macro_builder_status(
                    "The hardware slot is already full.", error=True)
                return
            self._recording = True
            self._last_key_time = 0.0
            self.record_button.setText("🔴 Recording...")
            self.stop_record_button.setEnabled(True)
            # Install event filter to capture key events
            QtWidgets.QApplication.instance().installEventFilter(self)
            self._log("Recording started - press keys to record macro events")
        else:
            self._stop_recording()

    def _stop_recording(self) -> None:
        """Stop macro recording."""
        if self._recording and self.macro_event_table.rowCount():
            delay_widget = self.macro_event_table.cellWidget(
                self.macro_event_table.rowCount() - 1, 3)
            if delay_widget:
                delay_widget.setValue(vp.MACRO_MIN_DELAY_MS)
        self._recording = False
        self.record_button.blockSignals(True)
        self.record_button.setChecked(False)
        self.record_button.blockSignals(False)
        self.record_button.setText("🔴 Record")
        self.stop_record_button.setEnabled(False)
        QtWidgets.QApplication.instance().removeEventFilter(self)
        self._update_macro_preview()
        self._log("Recording stopped")

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Capture key events during recording."""
        if self._recording:
            if event.type() == QtCore.QEvent.Type.KeyPress or event.type() == QtCore.QEvent.Type.KeyRelease:
                key_event = event
                if key_event.isAutoRepeat():
                    return False  # Ignore auto-repeat

                key_text = key_event.text().upper()
                qt_key = key_event.key()

                modifier = self._qt_key_to_macro_modifier(key_event)
                if modifier is not None:
                    modifier_name, keycode = modifier
                    key_name = f"Modifier: {modifier_name}"
                    is_modifier = True
                    event_type = "modifier"
                else:
                    # Map the non-modifier Qt key to a keyboard HID usage.
                    key_name = self._qt_key_to_name(qt_key, key_text)
                    if not key_name or key_name not in vp.HID_KEY_USAGE:
                        self._set_macro_builder_status(
                            f"Recording skipped unsupported key 0x{qt_key:X}.",
                            error=True,
                        )
                        return True
                    keycode = vp.HID_KEY_USAGE[key_name]
                    is_modifier = False
                    event_type = "keyboard"

                if key_name:
                    current_time = time.time() * 1000  # ms
                    if (self._last_key_time > 0 and
                            self.macro_event_table.rowCount()):
                        # Each hardware delay belongs to the event before it.
                        previous_delay = min(
                            0xFFFF,
                            max(vp.MACRO_MIN_DELAY_MS,
                                int(current_time - self._last_key_time)),
                        )
                        delay_widget = self.macro_event_table.cellWidget(
                            self.macro_event_table.rowCount() - 1, 3)
                        if delay_widget:
                            delay_widget.setValue(previous_delay)

                    is_down = event.type() == QtCore.QEvent.Type.KeyPress
                    added = self._add_event_to_table(
                        key_name, is_down, vp.MACRO_MIN_DELAY_MS,
                        is_modifier=is_modifier,
                        event_type=event_type,
                        keycode=keycode,
                    )
                    if not added:
                        self._stop_recording()
                        self._set_macro_builder_status(
                            "Recording stopped: the 69-event slot is full.",
                            error=True,
                        )
                        return True
                    self._last_key_time = current_time
                    return True  # Consume the event

        return super().eventFilter(obj, event)

    def _qt_key_to_name(self, qt_key: int, key_text: str) -> str | None:
        """Convert Qt key code to HID key name."""
        # Handle letter keys
        if len(key_text) == 1 and key_text.isalpha():
            return key_text.upper()
        # Handle number keys
        if len(key_text) == 1 and key_text.isdigit():
            return key_text
        return KeyCaptureEdit._QT_TO_HID.get(qt_key)

    def _qt_key_to_macro_modifier(
            self, key_event: QtGui.QKeyEvent) -> tuple[str, int] | None:
        """Map a Qt modifier event to the vendor's stored-macro code."""
        modifier_name = KeyCaptureEdit.modifier_name_for_event(key_event)
        if modifier_name is None:
            return None
        # The vendor converter collapses left/right GUI keys to one byte.
        if modifier_name in ("Left GUI", "Right GUI"):
            modifier_name = "GUI"
        keycode = vp.MACRO_MODIFIER_CODES.get(modifier_name)
        if keycode is None:
            return None
        return modifier_name, keycode

    def _set_macro_builder_status(self, message: str,
                                  error: bool = False) -> None:
        if hasattr(self, "text_builder_status"):
            self.text_builder_status.setText(message)
            self.text_builder_status.setStyleSheet(
                "color: #e57373;" if error else "color: palette(mid);")
        if error:
            self._log(f"Macro editor: {message}")

    def _can_add_macro_events(self, count: int) -> bool:
        return (self.macro_event_table.rowCount() + count
                <= vp.MACRO_MAX_EVENTS)

    def _sync_text_timing_controls(self) -> None:
        """Show only the timing controls relevant to the chosen mode."""
        random_timing = self.text_timing_mode.currentData() == "random"
        self.text_fixed_delay_label.setVisible(not random_timing)
        self.text_fixed_delay_spin.setVisible(not random_timing)
        self.text_random_range_widget.setVisible(random_timing)
        self._update_text_macro_requirements()

    def _sync_manual_event_controls(self) -> None:
        """A hold duration is meaningful only for a complete tap."""
        is_tap = self.add_action_combo.currentData() == "tap"
        self.add_hold_label.setEnabled(is_tap)
        self.add_hold_spin.setEnabled(is_tap)
        self.add_event_button.setText(
            "Add Tap" if is_tap else "Add Event")

    def _text_macro_timing(self) -> tuple[int, int]:
        if self.text_timing_mode.currentData() == "random":
            return (self.text_random_min_spin.value(),
                    self.text_random_max_spin.value())
        fixed = self.text_fixed_delay_spin.value()
        return fixed, fixed

    def _update_text_macro_requirements(self) -> None:
        """Validate text conversion and show its exact slot cost."""
        if not hasattr(self, "gen_text_btn"):
            return
        text = self.quick_text_edit.toPlainText()
        required, unsupported = vp.text_macro_requirements(text)
        existing = self.macro_event_table.rowCount()
        append = self.text_output_mode.currentData() == "append"
        total = existing + required if append else required
        minimum, maximum = self._text_macro_timing()

        error = ""
        if not text:
            message = (
                f"US keyboard layout · {vp.MACRO_MAX_EVENTS - existing} "
                "hardware events available in this slot")
        elif unsupported:
            display = ", ".join(repr(character) for character in unsupported)
            error = f"Unsupported character(s): {display}"
            message = error
        elif minimum > maximum:
            error = "The random minimum cannot exceed the maximum."
            message = error
        elif maximum + self.text_word_pause_spin.value() > 0xFFFF:
            error = "The inter-key delay plus word pause exceeds 65,535 ms."
            message = error
        elif total > vp.MACRO_MAX_EVENTS:
            error = (
                f"Needs {total} events after generation; the hardware slot "
                f"holds {vp.MACRO_MAX_EVENTS}.")
            message = error
        else:
            verb = "append" if append else "replace"
            message = (
                f"{len(text)} character(s) → {required} events · "
                f"{vp.MACRO_MAX_EVENTS - total} free after {verb}")

        self.gen_text_btn.setEnabled(bool(text) and not error)
        self.text_builder_status.setText(message)
        self.text_builder_status.setStyleSheet(
            "color: #e57373;" if error else "color: palette(mid);")

    def _add_event_to_table(self, key_name: str, is_down: bool, delay: int,
                            is_modifier: bool = False,
                            event_type: str = "keyboard",
                            keycode: int | None = None,
                            row: int | None = None,
                            update_preview: bool = True) -> bool:
        """Add one event without allowing a write past the hardware slot."""
        if not self._can_add_macro_events(1):
            self._set_macro_builder_status(
                f"The slot is full ({vp.MACRO_MAX_EVENTS} events).",
                error=True)
            return False
        if row is None:
            row = self.macro_event_table.rowCount()
        row = max(0, min(row, self.macro_event_table.rowCount()))
        self.macro_event_table.insertRow(row)

        # Row number
        num_item = QtWidgets.QTableWidgetItem(str(row + 1))
        num_item.setFlags(num_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.macro_event_table.setItem(row, 0, num_item)

        # Key name (store is_modifier flag)
        key_item = QtWidgets.QTableWidgetItem(key_name)
        key_item.setFlags(key_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        key_item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, is_modifier)  # Store modifier flag
        key_item.setData(QtCore.Qt.ItemDataRole.UserRole + 2,
                         "modifier" if is_modifier else event_type)
        key_item.setData(QtCore.Qt.ItemDataRole.UserRole + 3, keycode)
        self.macro_event_table.setItem(row, 1, key_item)

        # Action
        action_item = QtWidgets.QTableWidgetItem("Press" if is_down else "Release")
        action_item.setFlags(action_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        action_item.setData(QtCore.Qt.ItemDataRole.UserRole, is_down)
        self.macro_event_table.setItem(row, 2, action_item)

        # Delay (editable)
        delay_spin = QtWidgets.QSpinBox()
        delay_spin.setRange(0, 0xFFFF)
        delay_spin.setValue(delay)
        delay_spin.setSuffix(" ms")
        delay_spin.valueChanged.connect(self._update_macro_preview)
        self.macro_event_table.setCellWidget(row, 3, delay_spin)

        # Delete button
        delete_btn = QtWidgets.QPushButton("✕")
        delete_btn.setMaximumWidth(30)
        delete_btn.clicked.connect(lambda: self._delete_event_row(row))
        self.macro_event_table.setCellWidget(row, 4, delete_btn)

        self._renumber_rows()
        if update_preview:
            self._update_macro_preview()
        return True

    def _delete_event_row(self, row: int) -> None:
        """Delete a row from the event table."""
        # Find the current row of the delete button that was clicked
        sender = self.sender()
        for i in range(self.macro_event_table.rowCount()):
            if self.macro_event_table.cellWidget(i, 4) == sender:
                self.macro_event_table.removeRow(i)
                break
        self._renumber_rows()
        self._update_macro_preview()

    def _renumber_rows(self) -> None:
        """Renumber all rows in the event table."""
        for i in range(self.macro_event_table.rowCount()):
            item = self.macro_event_table.item(i, 0)
            if item:
                item.setText(str(i + 1))

    def _clear_macro_events(self) -> None:
        """Clear all events from the table."""
        self.macro_event_table.setRowCount(0)
        self._update_macro_preview()

    def _selected_macro_rows(self) -> list[int]:
        return sorted({index.row() for index in
                       self.macro_event_table.selectionModel().selectedRows()})

    def _delete_selected_events(self) -> None:
        rows = self._selected_macro_rows()
        if not rows and self.macro_event_table.currentRow() >= 0:
            rows = [self.macro_event_table.currentRow()]
        for row in reversed(rows):
            self.macro_event_table.removeRow(row)
        self._renumber_rows()
        self._update_macro_preview()

    def _duplicate_selected_event(self) -> None:
        row = self.macro_event_table.currentRow()
        if row < 0:
            return
        if not self._can_add_macro_events(1):
            self._set_macro_builder_status(
                "Cannot duplicate: the hardware slot is full.", error=True)
            return
        data = self._get_row_data(row)
        self._add_event_to_table(
            data[0], bool(data[1]), int(data[2]), bool(data[3]),
            str(data[4]), data[5], row=row + 1)
        self.macro_event_table.selectRow(row + 1)

    def _apply_delay_to_selected(self) -> None:
        rows = self._selected_macro_rows()
        if not rows and self.macro_event_table.currentRow() >= 0:
            rows = [self.macro_event_table.currentRow()]
        for row in rows:
            delay_widget = self.macro_event_table.cellWidget(row, 3)
            if delay_widget:
                delay_widget.setValue(self.selected_delay_spin.value())
        self._update_macro_preview()

    def _move_event_up(self) -> None:
        """Move the selected event up in the list."""
        row = self.macro_event_table.currentRow()
        if row > 0:
            self._swap_rows(row, row - 1)
            self.macro_event_table.selectRow(row - 1)

    def _move_event_down(self) -> None:
        """Move the selected event down in the list."""
        row = self.macro_event_table.currentRow()
        if row >= 0 and row < self.macro_event_table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self.macro_event_table.selectRow(row + 1)

    def _swap_rows(self, row1: int, row2: int) -> None:
        """Swap two rows in the event table."""
        # Get data from both rows
        data1 = self._get_row_data(row1)
        data2 = self._get_row_data(row2)

        # Set data in swapped positions
        self._set_row_data(row1, data2)
        self._set_row_data(row2, data1)
        self._renumber_rows()
        self._update_macro_preview()

    def _get_row_data(self, row: int) -> tuple:
        """Get data from a row."""
        key_item = self.macro_event_table.item(row, 1)
        key = key_item.text()
        is_modifier = bool(key_item.data(QtCore.Qt.ItemDataRole.UserRole + 1))
        event_type = key_item.data(QtCore.Qt.ItemDataRole.UserRole + 2) or "keyboard"
        keycode = key_item.data(QtCore.Qt.ItemDataRole.UserRole + 3)
        action_item = self.macro_event_table.item(row, 2)
        is_down = action_item.data(QtCore.Qt.ItemDataRole.UserRole)
        delay_widget = self.macro_event_table.cellWidget(row, 3)
        delay = delay_widget.value() if delay_widget else 0
        return (key, is_down, delay, is_modifier, event_type, keycode)

    def _set_row_data(self, row: int, data: tuple) -> None:
        """Set data in a row."""
        key, is_down, delay, is_modifier, event_type, keycode = data
        key_item = self.macro_event_table.item(row, 1)
        key_item.setText(key)
        key_item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, is_modifier)
        key_item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, event_type)
        key_item.setData(QtCore.Qt.ItemDataRole.UserRole + 3, keycode)
        action_item = self.macro_event_table.item(row, 2)
        action_item.setText("Press" if is_down else "Release")
        action_item.setData(QtCore.Qt.ItemDataRole.UserRole, is_down)
        delay_widget = self.macro_event_table.cellWidget(row, 3)
        if delay_widget:
            delay_widget.setValue(delay)

    def _add_manual_event(self) -> None:
        """Add a tap or a single press/release event from the builder."""
        key_name = self.add_key_combo.currentText()
        event_data = self.add_key_combo.currentData()
        if not event_data:
            return
        event_type, keycode = event_data
        action = self.add_action_combo.currentData()
        is_modifier = event_type == "modifier"
        needed = 2 if action == "tap" else 1
        if not self._can_add_macro_events(needed):
            self._set_macro_builder_status(
                f"This action needs {needed} event(s), but only "
                f"{vp.MACRO_MAX_EVENTS - self.macro_event_table.rowCount()} "
                "remain in the slot.", error=True)
            return

        if action == "tap":
            self._add_event_to_table(
                key_name, True, self.add_hold_spin.value(), is_modifier,
                event_type, keycode, update_preview=False)
            self._add_event_to_table(
                key_name, False, self.add_delay_spin.value(), is_modifier,
                event_type, keycode, update_preview=False)
        else:
            self._add_event_to_table(
                key_name, action == "press", self.add_delay_spin.value(),
                is_modifier, event_type, keycode, update_preview=False)
        self._update_macro_preview()

    def _update_macro_preview(self) -> None:
        """Update output, duration, capacity, and unmatched-state feedback."""
        events = self._get_macro_events_from_table()
        total_delay = sum(event.delay_ms for event in events)
        output: list[str] = []
        pressed: set[tuple[str, int]] = set()
        active_modifiers: set[int] = set()

        for event in events:
            event_type = "modifier" if event.is_modifier else event.event_type
            identity = (event_type, event.keycode)
            if event.is_down:
                pressed.add(identity)
            else:
                pressed.discard(identity)

            if event_type == "modifier":
                if event.is_down:
                    active_modifiers.add(event.keycode)
                else:
                    active_modifiers.discard(event.keycode)
            elif event_type == "mouse" and event.is_down:
                mouse_names = {
                    0x01: "Left click", 0x02: "Right click",
                    0x04: "Middle click", 0x08: "Back click",
                    0x10: "Forward click",
                }
                output.append(f"[{mouse_names.get(event.keycode, 'Mouse click')}]")
            elif event_type == "keyboard" and event.is_down:
                non_text_modifiers = active_modifiers.intersection(
                    vp.MACRO_NON_TEXT_MODIFIER_CODES)
                if non_text_modifiers:
                    modifier_labels = "+".join(
                        vp.MACRO_MODIFIER_NAMES.get(code, f"0x{code:02X}")
                        for code in sorted(active_modifiers)
                    )
                    name = self.HID_USAGE_TO_NAME.get(
                        event.keycode, f"0x{event.keycode:02X}")
                    output.append(f"[{modifier_labels}+{name}]")
                else:
                    shift_active = bool(
                        active_modifiers.intersection(
                            vp.MACRO_SHIFT_CODES))
                    character = vp.ASCII_FROM_HID.get(
                        (event.keycode, shift_active))
                    if character is not None:
                        output.append(character)
                    else:
                        name = self.HID_USAGE_TO_NAME.get(
                            event.keycode, f"0x{event.keycode:02X}")
                        output.append(f"[{name}]")

        rendered = json.dumps("".join(output), ensure_ascii=False)
        warning = f" · ⚠ {len(pressed)} still pressed" if pressed else ""
        self.macro_preview_label.setText(
            f"Output: {rendered} · {total_delay:,} ms total{warning}")
        count = self.macro_event_table.rowCount()
        self.macro_capacity_bar.setValue(count)
        self.macro_capacity_bar.setFormat(
            f"{count} / {vp.MACRO_MAX_EVENTS} hardware events · "
            f"{vp.MACRO_MAX_EVENTS - count} free")
        self._update_text_macro_requirements()

    def _get_macro_events_from_table(self) -> list:
        """Extract macro events from the table."""
        events = []
        for row in range(self.macro_event_table.rowCount()):
            key_item = self.macro_event_table.item(row, 1)
            action_item = self.macro_event_table.item(row, 2)
            delay_widget = self.macro_event_table.cellWidget(row, 3)

            if not key_item or not action_item:
                continue

            key_name = key_item.text()
            is_down = bool(action_item.data(QtCore.Qt.ItemDataRole.UserRole))
            is_modifier = bool(
                key_item.data(QtCore.Qt.ItemDataRole.UserRole + 1))
            event_type = key_item.data(QtCore.Qt.ItemDataRole.UserRole + 2) or (
                "modifier" if is_modifier else "keyboard")
            stored_keycode = key_item.data(QtCore.Qt.ItemDataRole.UserRole + 3)
            delay = delay_widget.value() if delay_widget else 0

            if event_type == "mouse" and stored_keycode is not None:
                events.append(vp.MacroEvent.mouse(int(stored_keycode), is_down, delay))
            elif key_name in vp.HID_KEY_USAGE or stored_keycode is not None:
                keycode = (int(stored_keycode) if stored_keycode is not None
                           else vp.HID_KEY_USAGE[key_name])
                events.append(vp.MacroEvent(
                    keycode=keycode,
                    is_down=is_down,
                    delay_ms=delay,
                    is_modifier=is_modifier,
                    event_type=event_type,
                ))
        return events

    def _build_rgb_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # --- Quick Pick Grid ---
        quick_pick_group = QtWidgets.QGroupBox("Quick Pick Colors")
        grid_layout = QtWidgets.QGridLayout(quick_pick_group)
        grid_layout.setSpacing(4)
        
        row, col = 0, 0
        for r, g, b in vp.RGB_QUICK_PICKS:
            color = QtGui.QColor(r, g, b)
            btn = QtWidgets.QPushButton()
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #555;")
            btn.setToolTip(f"RGB: {r}, {g}, {b}")
            
            # Connect using closure to capture current color
            btn.clicked.connect(lambda _, c=color: self._set_custom_color(c))
            
            grid_layout.addWidget(btn, row, col)
            col += 1
            if col >= 9:
                col = 0
                row += 1
        
        layout.addWidget(quick_pick_group)

        # Custom controls in a form
        form_widget = QtWidgets.QWidget()
        form_layout = QtWidgets.QFormLayout(form_widget)

        # Color picker
        self.rgb_color_button = QtWidgets.QPushButton("Pick Custom Color")
        self.rgb_color_button.setStyleSheet("background-color: #FF00FF; color: white; font-weight: bold;")
        self.rgb_color_button.clicked.connect(self._pick_rgb_color)
        self.rgb_current_color = QtGui.QColor(255, 0, 255)  # Default magenta
        
        # Mode selector
        self.rgb_mode = QtWidgets.QComboBox()
        self.rgb_mode.addItem("Off", vp.RGB_MODE_OFF)
        self.rgb_mode.addItem("Steady", vp.RGB_MODE_STEADY)
        self.rgb_mode.addItem("Breathing", vp.RGB_MODE_BREATHING)
        self.rgb_mode.addItem("Neon", vp.RGB_MODE_NEON)
        self.rgb_mode.setCurrentIndex(1)  # Default to Steady
        self.rgb_mode.setToolTip("Select the lighting effect mode.")
        
        # Brightness slider
        self.rgb_brightness = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.rgb_brightness.setRange(0, 100)
        self.rgb_brightness.setValue(100)
        self.rgb_brightness.setToolTip("Adjust the overall brightness of the LED.")
        self.rgb_brightness_label = QtWidgets.QLabel("100%")
        self.rgb_brightness.valueChanged.connect(
            self._update_rgb_brightness_label
        )
        
        brightness_layout = QtWidgets.QHBoxLayout()
        brightness_layout.addWidget(self.rgb_brightness, stretch=1)
        brightness_layout.addWidget(self.rgb_brightness_label)

        self.rgb_speed_label = QtWidgets.QLabel("Effect speed (raw):")
        self.rgb_speed = QtWidgets.QSpinBox()
        self.rgb_speed.setRange(
            vp.RGB_EFFECT_SPEED_MIN, vp.RGB_EFFECT_SPEED_MAX)
        self.rgb_speed.setValue(vp.RGB_EFFECT_SPEED_DEFAULT)
        self.rgb_speed.setToolTip(
            "Areson animation speed: 1 is fastest and 5 is slowest. "
            "Holtek exposes a raw per-profile speed byte.")
        self.rgb_speed_label.setVisible(False)
        self.rgb_speed.setVisible(False)
        self.rgb_mode.currentIndexChanged.connect(
            self._update_rgb_effect_controls)

        apply_custom_button = QtWidgets.QPushButton("Apply Lighting")
        apply_custom_button.setStyleSheet("font-weight: bold; padding: 8px; background-color: #444;")
        apply_custom_button.clicked.connect(self._apply_rgb_custom)

        self.battery_led_checkbox = QtWidgets.QCheckBox(
            "Use mouse LED as a battery gauge while this app is running")
        self.battery_led_checkbox.setChecked(self.battery_led_enabled)
        self.battery_led_checkbox.setToolTip(
            "Uses a low 10% steady-light setting and updates only when the mouse "
            "reports a different 10% battery step. The absolute raw minimum is "
            "not used because it suppresses mixed red/green colors on this LED. "
            "Green is full, yellow is half, and red is empty. The wireless "
            "firmware may still switch its RGB off after inactivity; this mode "
            "does not repeatedly rewrite the mouse's EEPROM as a keepalive.")
        self.battery_led_checkbox.toggled.connect(self._set_battery_led_enabled)
        gradient_label = QtWidgets.QLabel(
            '<span style="color:#00ff00">● full</span> → '
            '<span style="color:#80ff00">●</span> → '
            '<span style="color:#ffff00">● half</span> → '
            '<span style="color:#ff8000">●</span> → '
            '<span style="color:#ff0000">● empty</span>')

        form_layout.addRow("Color:", self.rgb_color_button)
        form_layout.addRow("Mode:", self.rgb_mode)
        self.rgb_brightness_form_label = QtWidgets.QLabel("Brightness:")
        form_layout.addRow(self.rgb_brightness_form_label, brightness_layout)
        form_layout.addRow(self.rgb_speed_label, self.rgb_speed)
        form_layout.addRow("", apply_custom_button)
        form_layout.addRow("Battery LED:", self.battery_led_checkbox)
        form_layout.addRow("", gradient_label)

        if self._battery_led_restore:
            self._apply_rgb_restore_to_widgets(self._battery_led_restore)
        
        layout.addWidget(form_widget)
        layout.addStretch()
        
        return widget

    def _update_rgb_brightness_label(self, value: int) -> None:
        suffix = " raw" if self.device_type == "holtek" else "%"
        self.rgb_brightness_label.setText(f"{value}{suffix}")

    def _set_custom_color(self, color: QtGui.QColor) -> None:
        """Set the current color from a preset."""
        self.rgb_current_color = color
        self.rgb_color_button.setStyleSheet(
            f"background-color: {color.name()}; color: {'white' if color.lightness() < 128 else 'black'}; font-weight: bold;"
        )
        # Optionally auto-apply?
        # self._apply_rgb_custom()

    def _capture_rgb_restore(self) -> dict[str, int]:
        return {
            "r": self.rgb_current_color.red(),
            "g": self.rgb_current_color.green(),
            "b": self.rgb_current_color.blue(),
            "mode": int(self.rgb_mode.currentData() or vp.RGB_MODE_OFF),
            "brightness": self.rgb_brightness.value(),
            "speed": self.rgb_speed.value(),
        }

    def _apply_rgb_restore_to_widgets(self, settings: dict[str, int]) -> None:
        color = QtGui.QColor(settings["r"], settings["g"], settings["b"])
        self._set_custom_color(color)
        mode_index = self.rgb_mode.findData(settings["mode"])
        if mode_index >= 0:
            self.rgb_mode.setCurrentIndex(mode_index)
        self.rgb_brightness.setValue(settings["brightness"])
        self.rgb_speed.setValue(settings.get(
            "speed", vp.RGB_EFFECT_SPEED_DEFAULT))

    def _update_rgb_effect_controls(self) -> None:
        is_holtek = self.device_type == "holtek"
        animated = self.rgb_mode.currentData() in (
            vp.RGB_MODE_BREATHING, vp.RGB_MODE_NEON)
        self.rgb_speed_label.setVisible(is_holtek or animated)
        self.rgb_speed.setVisible(is_holtek or animated)
        self.rgb_speed_label.setText(
            "Effect speed (raw):" if is_holtek else
            "Effect speed (1 fast–5 slow):")


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

        self.dpi_header = QtWidgets.QLabel(
            "DPI slots (presets are captured values; custom conversion is approximate and sensor-dependent)")
        self.dpi_header.setWordWrap(True)
        layout.addWidget(self.dpi_header)

        self.dpi_profile_controls = QtWidgets.QWidget()
        profile_controls = QtWidgets.QHBoxLayout(self.dpi_profile_controls)
        profile_controls.setContentsMargins(0, 0, 0, 0)
        self.dpi_stage_count_label = QtWidgets.QLabel("Enabled stages:")
        profile_controls.addWidget(self.dpi_stage_count_label)
        self.dpi_stage_count_spin = QtWidgets.QSpinBox()
        self.dpi_stage_count_spin.setRange(1, 10)
        self.dpi_stage_count_spin.setValue(5)
        self.dpi_stage_count_spin.valueChanged.connect(
            self._update_dpi_row_visibility)
        profile_controls.addWidget(self.dpi_stage_count_spin)
        profile_controls.addSpacing(16)
        self.dpi_active_stage_label = QtWidgets.QLabel("Current stage:")
        profile_controls.addWidget(self.dpi_active_stage_label)
        self.dpi_active_stage_spin = QtWidgets.QSpinBox()
        self.dpi_active_stage_spin.setRange(1, 5)
        self.dpi_active_stage_spin.setValue(1)
        profile_controls.addWidget(self.dpi_active_stage_spin)
        profile_controls.addStretch()
        layout.addWidget(self.dpi_profile_controls)

        self.dpi_rows: list[tuple[
            QtWidgets.QComboBox,
            QtWidgets.QSpinBox,
            QtWidgets.QSpinBox,
            QtWidgets.QSpinBox,
        ]] = []
        self.dpi_row_widgets: list[QtWidgets.QWidget] = []
        self.dpi_raw_labels: list[QtWidgets.QLabel] = []
        self.dpi_check_labels: list[QtWidgets.QLabel] = []
        for slot in range(10):
            row_widget = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            label = QtWidgets.QLabel(f"Slot {slot + 1}")
            label.setMinimumWidth(60)

            combo = QtWidgets.QComboBox()
            combo.addItem("Custom", None)
            for dpi in sorted(vp.DPI_PRESETS.keys()):
                combo.addItem(f"{dpi} DPI", dpi)
            combo.currentIndexChanged.connect(self._sync_dpi_presets)

            dpi_spin = QtWidgets.QSpinBox()
            dpi_spin.setRange(100, 20000)
            dpi_spin.setSingleStep(100)
            dpi_spin.valueChanged.connect(lambda _=None, row_index=slot: self._on_dpi_spin_changed(row_index))

            value_spin = QtWidgets.QSpinBox()
            value_spin.setRange(0, 255)
            value_spin.valueChanged.connect(lambda _=None, row_index=slot: self._on_dpi_value_changed(row_index))
            tweak_spin = QtWidgets.QSpinBox()
            tweak_spin.setRange(0, 255)
            tweak_spin.setReadOnly(True)
            tweak_spin.setButtonSymbols(
                QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
            tweak_spin.setToolTip(
                "Derived record checksum byte; updated from the raw value.")

            raw_label = QtWidgets.QLabel("Raw value")
            check_label = QtWidgets.QLabel("Check")

            row.addWidget(label)
            row.addWidget(combo)
            row.addWidget(QtWidgets.QLabel("DPI"))
            row.addWidget(dpi_spin)
            row.addWidget(raw_label)
            row.addWidget(value_spin)
            row.addWidget(check_label)
            row.addWidget(tweak_spin)
            layout.addWidget(row_widget)

            self.dpi_rows.append((combo, dpi_spin, value_spin, tweak_spin))
            self.dpi_row_widgets.append(row_widget)
            self.dpi_raw_labels.append(raw_label)
            self.dpi_check_labels.append(check_label)

        apply_button = QtWidgets.QPushButton("Apply DPI Slots")
        apply_button.clicked.connect(self._apply_dpi)
        layout.addWidget(apply_button)
        layout.addStretch(1)

        self._sync_dpi_presets()
        self._update_dpi_row_visibility()
        return widget

    def _dpi_stage_count(self) -> int:
        """Return the number of rows the selected protocol can safely write."""
        return self.dpi_stage_count_spin.value()

    def _update_dpi_row_visibility(self) -> None:
        if not hasattr(self, "dpi_row_widgets"):
            return
        count = self._dpi_stage_count()
        self.dpi_active_stage_spin.setMaximum(max(1, count))
        for index, row_widget in enumerate(self.dpi_row_widgets):
            row_widget.setVisible(index < count)

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


    def _store_custom_profile(self) -> None:
        button_key = self.current_edit_key
        if button_key is None:
            return
        # If it's a standard profile, we shouldn't be here (locked fields), but check anyway
        if button_key in self.active_button_profiles:
            if self.device_type == 'holtek':
                return  # Holtek profiles are always standard
            profile = self.active_button_profiles[button_key]
            if profile.code_hi is not None:
                return

        self.custom_profiles[button_key] = (
            self.code_hi_spin.value(),
            self.code_lo_spin.value(),
            self.apply_offset_spin.value(),
        )

    def _resolve_profile(self, button_key: str, use_fallback: bool) -> tuple[int, int, int]:
        # Holtek uses a different profile structure (index-based)
        if self.device_type == 'holtek':
            profile = self.active_button_profiles.get(button_key)
            if profile is not None:
                return 0, 0, profile.index
            raise ValueError(f"Unknown Holtek button: {button_key}")

        profile = vp.BUTTON_PROFILES[button_key]
        if profile.code_hi is not None and profile.code_lo is not None and profile.apply_offset is not None:
            return profile.code_hi, profile.code_lo, profile.apply_offset
        if button_key in self.custom_profiles:
            return self.custom_profiles[button_key]
        if use_fallback and button_key == self.current_edit_key:
            code_hi = self.code_hi_spin.value()
            code_lo = self.code_lo_spin.value()
            apply_offset = self.apply_offset_spin.value()
            self.custom_profiles[button_key] = (code_hi, code_lo, apply_offset)
            return code_hi, code_lo, apply_offset
        raise ValueError("Unknown button profile. Fill code/offset values in the Buttons tab first.")


    def _log(self, text: str) -> None:
        self.log_area.appendPlainText(text)

    def _battery_icon(self, percent: int | None, cable_connected: bool = False) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(64, 64)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        outline = QtGui.QColor("#e6e6e6")
        if percent is None:
            fill = QtGui.QColor("#777777")
        else:
            fill = QtGui.QColor(*vp.battery_gradient_rgb(percent))

        pen = QtGui.QPen(outline, 4)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        body = QtCore.QRectF(6, 14, 46, 36)
        painter.drawRoundedRect(body, 5, 5)
        painter.fillRect(QtCore.QRectF(53, 24, 6, 16), outline)

        if percent is not None:
            inner_width = 38 * max(0, min(100, percent)) / 100
            painter.fillRect(QtCore.QRectF(10, 18, inner_width, 28), fill)
        else:
            painter.setPen(outline)
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(25)
            painter.setFont(font)
            painter.drawText(body, QtCore.Qt.AlignmentFlag.AlignCenter, "?")

        if cable_connected:
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 3))
            painter.drawLine(32, 10, 25, 30)
            painter.drawLine(25, 30, 34, 30)
            painter.drawLine(34, 30, 27, 52)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _setup_tray(self) -> None:
        """Create one desktop-neutral Qt status icon and refresh timer."""
        self.tray_icon: QtWidgets.QSystemTrayIcon | None = None
        self.battery_timer = QtCore.QTimer(self)
        self.battery_timer.setInterval(60_000)
        self.battery_timer.timeout.connect(self._request_battery_refresh)
        self.battery_timer.start()
        self.battery_led_tray_action: QtGui.QAction | None = None

        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            self._log("Tray: This desktop session does not expose a system tray.")
            self._sync_battery_led_controls()
            return

        self.tray_icon = QtWidgets.QSystemTrayIcon(self._battery_icon(None), self)
        self.tray_icon.setToolTip("Venus mouse — battery unavailable")
        menu = QtWidgets.QMenu(self)
        show_action = menu.addAction("Show Venus Pro Config")
        show_action.triggered.connect(self._show_from_tray)
        refresh_action = menu.addAction("Refresh Battery")
        refresh_action.triggered.connect(self._request_battery_refresh)
        self.battery_led_tray_action = menu.addAction(
            "Battery-color mouse LED (low brightness)")
        self.battery_led_tray_action.setCheckable(True)
        self.battery_led_tray_action.triggered.connect(
            self._set_battery_led_enabled)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit_from_tray)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()
        self._sync_battery_led_controls()

        app = QtWidgets.QApplication.instance()
        if app:
            app.setQuitOnLastWindowClosed(False)

    def _sync_battery_led_controls(self) -> None:
        supported = self.device_type == "venus_pro"
        if hasattr(self, "battery_led_checkbox"):
            self.battery_led_checkbox.blockSignals(True)
            self.battery_led_checkbox.setChecked(self.battery_led_enabled)
            self.battery_led_checkbox.setEnabled(supported)
            self.battery_led_checkbox.blockSignals(False)
        if self.battery_led_tray_action:
            self.battery_led_tray_action.blockSignals(True)
            self.battery_led_tray_action.setChecked(self.battery_led_enabled)
            self.battery_led_tray_action.setEnabled(supported)
            self.battery_led_tray_action.blockSignals(False)

    def _set_battery_led_enabled(self, enabled: bool,
                                 restore: bool = True) -> None:
        """Toggle the background battery-color controller."""
        enabled = bool(enabled)
        if enabled and self.device_type != "venus_pro":
            self._sync_battery_led_controls()
            return
        if enabled == self.battery_led_enabled:
            self._sync_battery_led_controls()
            return

        was_enabled = self.battery_led_enabled
        if enabled:
            self._battery_led_restore = self._capture_rgb_restore()
            self.battery_led_enabled = True
            self._last_battery_led_level = None
            self._log(
                "Battery LED: enabled (low brightness; updates on battery-step changes)")
        else:
            self.battery_led_enabled = False
            self._last_battery_led_level = None
            self._log("Battery LED: disabled")

        self._save_app_settings()
        self._sync_battery_led_controls()
        if enabled:
            self._request_battery_refresh()
        elif was_enabled and restore:
            self._restore_battery_led(quiet=False)

    def _restore_battery_led(self, quiet: bool) -> bool:
        """Restore lighting captured when battery mode was enabled."""
        settings = self._battery_led_restore
        self._last_battery_led_level = None
        if not settings:
            return True
        if hasattr(self, "rgb_mode"):
            self._apply_rgb_restore_to_widgets(settings)
        if self.device_type != "venus_pro" or self.device_path is None:
            return True
        packets = vp.build_rgb_packets(
            settings["r"], settings["g"], settings["b"],
            settings["mode"], settings["brightness"],
            settings.get("speed", vp.RGB_EFFECT_SPEED_DEFAULT))
        return self._send_reports(
            [vp.build_simple(vp.CMD_READY), *packets],
            "Battery LED restore", quiet=quiet)

    def _on_app_quit(self) -> None:
        if self._shutdown_restore_done:
            return
        self._shutdown_restore_done = True
        self._quitting = True
        self.battery_timer.stop()
        if self._battery_thread and self._battery_thread.isRunning():
            # open() may wait one second for the shared HID lock before the
            # status exchange uses its own 500 ms timeout.
            self._battery_thread.wait(2000)
        if self.battery_led_enabled:
            self._restore_battery_led(quiet=True)
        if self.tray_icon:
            self.tray_icon.hide()

    def _apply_battery_led_status(self, status: vp.BatteryStatus) -> None:
        if (not self.battery_led_enabled or self._quitting or
                status.level == self._last_battery_led_level):
            return
        r, g, b = vp.battery_gradient_rgb(status.percent)
        success = self._send_reports(
            [vp.build_simple(vp.CMD_READY),
             vp.build_battery_indicator_rgb(status.percent)],
            f"Battery LED {status.percent}% ({r},{g},{b})",
            quiet=True)
        if success:
            self._last_battery_led_level = status.level
            self._log(
                f"Battery LED: {status.percent}% -> RGB({r}, {g}, {b}) at "
                f"{vp.BATTERY_LED_BRIGHTNESS}% brightness")

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason) -> None:
        if reason in (QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
                      QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_from_tray()

    def _quit_from_tray(self) -> None:
        self._quitting = True
        self.battery_timer.stop()
        if self.tray_icon:
            self.tray_icon.hide()
        app = QtWidgets.QApplication.instance()
        if app:
            app.quit()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.tray_icon and self.tray_icon.isVisible() and not self._quitting:
            event.ignore()
            self.hide()
            if not self._tray_notice_shown:
                self.tray_icon.showMessage(
                    "Venus Pro Config",
                    "Battery monitoring is still running. Use the tray menu to quit.",
                    QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                    3500,
                )
                self._tray_notice_shown = True
            return
        super().closeEvent(event)

    def _request_battery_refresh(self) -> None:
        if not self.tray_icon and not self.battery_led_enabled:
            return
        if self.device_type != "venus_pro" or self.device_path is None:
            if self.tray_icon:
                self.tray_icon.setIcon(self._battery_icon(None))
                self.tray_icon.setToolTip("Venus mouse — battery unavailable")
            return
        if self._battery_thread and self._battery_thread.isRunning():
            return
        self._battery_thread = BatteryQueryThread(self.device_path, self)
        self._battery_thread.completed.connect(self._battery_query_finished)
        thread = self._battery_thread
        thread.finished.connect(
            lambda finished_thread=thread:
                self._battery_thread_finished(finished_thread))
        self._battery_thread.start()

    def _battery_query_finished(self, status: object, error: str) -> None:
        if isinstance(status, vp.BatteryStatus):
            connection = "USB cable" if status.cable_connected else "wireless"
            current = (status.level, status.cable_connected)
            if current != self._last_battery_status:
                self._log(f"Battery: {status.percent}% ({connection})")
                self._last_battery_status = current
            if self.tray_icon:
                suffix = "; battery LED on" if self.battery_led_enabled else ""
                self.tray_icon.setIcon(
                    self._battery_icon(status.percent, status.cable_connected))
                self.tray_icon.setToolTip(
                    f"Venus Pro — {status.percent}% ({connection}{suffix})")
            self._apply_battery_led_status(status)
        else:
            if self.tray_icon:
                self.tray_icon.setIcon(self._battery_icon(None))
                self.tray_icon.setToolTip(
                    "Venus Pro — disconnected or inaccessible")
            if error:
                self._log(f"Battery refresh: {error}")

    def _battery_thread_finished(self, thread: BatteryQueryThread) -> None:
        """Release a worker only after QThread confirms run() has returned."""
        if self._battery_thread is thread:
            self._battery_thread = None
        thread.deleteLater()

    def _refresh_devices(self) -> None:
        self.device_infos = vp.list_devices()
        self.device_combo.clear()

        if not vp.HIDAPI_AVAILABLE:
            self.status_label.setText("Status: python-hidapi is not installed")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.device_combo.addItem("Install python-hidapi")
            self.device_path = None
            return

        if not self.device_infos:
            self.status_label.setText("Status: No device found")
            self.status_label.setStyleSheet("")
            self.device_combo.addItem("No supported vendor HID interface found")
            self.device_path = None
            return

        for info in self.device_infos:
            access = " — inaccessible" if info.access_error else ""
            label = (f"{info.product} (0x{info.vendor_id:04x}:0x{info.product_id:04x}, "
                     f"interface {info.interface_number}){access}")
            self.device_combo.addItem(label, info)

        chosen = next((item for item in self.device_infos if not item.access_error),
                      self.device_infos[0])
        self.device_path = chosen.path
        if chosen.access_error:
            self.status_label.setText("Status: Mouse detected, but access failed")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            self._log(f"Detection: {chosen.access_error}")
        else:
            self.status_label.setStyleSheet("")
            self.status_label.setText("Status: Ready")

    def _connect_device(self) -> None:
        """Legacy function - now just stores device path."""
        if not self.device_infos:
            QtWidgets.QMessageBox.warning(self, "No device", "No supported devices detected.")
            return
        info = self.device_combo.currentData()
        if info is None:
            QtWidgets.QMessageBox.warning(self, "No device", "Pick a device entry first.")
            return
        self.device_path = info.path
        self.status_label.setText(f"Ready: {info.product}")
        self._log(f"Device selected: {info.product} ({info.display_path})")

    def _disconnect_device(self) -> None:
        """Legacy function - just clears device path."""
        self.device_path = None
        self.status_label.setText("Disconnected")
        self._log("Device cleared")

    def _refresh_and_connect(self, silent: bool = False) -> None:
        """Refresh devices and store path for transient connections."""
        self._log("Connect: Refreshing device list...")
        self._refresh_devices()
        if self.device_infos:
            info = next((item for item in self.device_infos if not item.access_error),
                        self.device_infos[0])
            self.device_path = info.path

            # Detect device type and swap profiles
            new_type = dd.detect_device_type(info)
            if new_type != self.device_type:
                self._log(f"Connect: Device type changed: {self.device_type} -> {new_type}")
            self.device_type = new_type
            self.active_button_profiles = dd.get_button_profiles(self.device_type)
            self._last_battery_led_level = None
            self._last_battery_status = None
            self._sync_battery_led_controls()
            self._rebuild_button_table()

            device_name = vp.DEVICE_NAMES.get((info.vendor_id, info.product_id), info.product)
            self.status_label.setText(f"Ready: {device_name}")
            self.setWindowTitle(f"Venus Pro Config — {device_name}")
            self._log(f"Connect: Found {device_name} ({self.device_type}) at {info.display_path}")
            if info.selection_note:
                self._log(f"Connect: {info.selection_note}")

            # Show/hide profile selector for Holtek
            is_holtek = self.device_type == 'holtek'
            self.profile_label.setVisible(is_holtek)
            self.profile_combo.setVisible(is_holtek)

            # Guard macro tab for Holtek
            self._update_macro_tab_availability()

            QtWidgets.QApplication.processEvents()

            if info.access_error:
                self.status_label.setText(f"Detected: {device_name} — access denied")
                self._log(f"Connect: {info.access_error}")
            else:
                # Auto-read settings on startup
                self._log("Connect: Triggering auto-read settings...")
                if is_holtek:
                    self._read_settings_holtek(
                        silent=silent, use_active_profile=True)
                else:
                    self._read_settings(silent=silent)
                self._request_battery_refresh()
        else:
            self._log("Connect: No devices found.")
            self.status_label.setText("No device found")
            self._request_battery_refresh()

    def _auto_connect(self) -> None:
        """Legacy function - handled by _refresh_and_connect now."""
        pass

    def _rebuild_button_table(self) -> None:
        """Clear and repopulate button table from active_button_profiles."""
        profiles = self.active_button_profiles
        self.sorted_btn_keys = sorted(profiles.keys(), key=lambda k: int(k.split()[1]))
        self._log(f"Rebuild table: {len(self.sorted_btn_keys)} buttons, keys={self.sorted_btn_keys[:3]}...")
        self.btn_table.clearContents()
        self.btn_table.setRowCount(len(self.sorted_btn_keys))

        for i, key in enumerate(self.sorted_btn_keys):
            profile = profiles[key]
            label = profile.label
            item_name = QtWidgets.QTableWidgetItem(label)
            item_name.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            item_name.setFlags(item_name.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.btn_table.setItem(i, 0, item_name)

            item_assign = QtWidgets.QTableWidgetItem("Unknown (Read to update)")
            item_assign.setFlags(item_assign.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.btn_table.setItem(i, 1, item_assign)

        # Also update the macro tab's button selector if it exists
        if hasattr(self, 'macro_button_select'):
            self.macro_button_select.clear()
            for key in self.sorted_btn_keys:
                profile = profiles[key]
                self.macro_button_select.addItem(profile.label, key)

    def _update_macro_tab_availability(self) -> None:
        """Synchronize every protocol-specific control after detection."""
        self._sync_device_specific_ui()

    def _sync_device_specific_ui(self) -> None:
        """Expose only controls that the selected controller implements."""
        is_holtek = self.device_type == "holtek"

        actions = (
            [
                "Keyboard Key", "Left Click", "Right Click", "Middle Click",
                "Forward", "Back", "DPI Control", "Fire Key",
                "Profile Switch", "Disabled",
            ] if is_holtek else [
                "Keyboard Key", "Left Click", "Right Click", "Middle Click",
                "Forward", "Back", "Macro", "Fire Key", "Triple Click",
                "Media Key", "RGB Toggle", "Polling Rate Toggle",
                "DPI Control", "Disabled",
            ]
        )
        current_action = self.action_select.currentText()
        self.action_select.blockSignals(True)
        self.action_select.clear()
        self.action_select.addItems(actions)
        selected = self.action_select.findText(current_action)
        self.action_select.setCurrentIndex(
            selected if selected >= 0 else self.action_select.findText("Disabled"))
        self.action_select.blockSignals(False)
        self._update_bind_ui(self.action_select.currentText())

        modifier_tooltip = (
            "The Holtek button record stores one HID key and has no modifier "
            "field." if is_holtek else "Combine modifiers with the selected key.")
        for checkbox in (self.mod_ctrl, self.mod_shift, self.mod_alt, self.mod_win):
            checkbox.blockSignals(True)
            if is_holtek:
                checkbox.setChecked(False)
            checkbox.setEnabled(not is_holtek)
            checkbox.setToolTip(modifier_tooltip)
            checkbox.blockSignals(False)
        self.modifier_label.setEnabled(not is_holtek)
        self.modifier_label.setToolTip(modifier_tooltip)

        self.special_delay_label.setVisible(not is_holtek)
        self.special_delay_spin.setVisible(not is_holtek)

        current_dpi_action = self.dpi_action_select.currentData()
        self.dpi_action_select.blockSignals(True)
        self.dpi_action_select.clear()
        if not is_holtek:
            self.dpi_action_select.addItem("DPI Loop", 0x01)
        self.dpi_action_select.addItem("DPI +", 0x02)
        self.dpi_action_select.addItem("DPI -", 0x03)
        dpi_action_index = self.dpi_action_select.findData(current_dpi_action)
        self.dpi_action_select.setCurrentIndex(
            dpi_action_index if dpi_action_index >= 0 else 0)
        self.dpi_action_select.blockSignals(False)

        for index in range(self.tabs.count()):
            title = self.tabs.tabText(index)
            if title == "Macros":
                self.tabs.setTabEnabled(index, not is_holtek)
                self.tabs.setTabToolTip(
                    index,
                    "The Holtek controller has no confirmed hardware macro "
                    "format." if is_holtek else "")
            elif title == "Advanced":
                self.tabs.setTabEnabled(index, not is_holtek)
                self.tabs.setTabToolTip(
                    index,
                    "Raw reports on this tab use the 17-byte Areson format."
                    if is_holtek else "")

        for button in (self.export_button, self.import_button, self.reset_button):
            button.setEnabled(not is_holtek)
        self.export_button.setToolTip(
            "Full profile export is currently Areson-only." if is_holtek else "")
        self.import_button.setToolTip(
            "Full profile import is currently Areson-only." if is_holtek else "")
        self.reset_button.setToolTip(
            "The Holtek factory-reset sequence is not confirmed." if is_holtek else "")

        self.rgb_speed.setRange(
            0 if is_holtek else vp.RGB_EFFECT_SPEED_MIN,
            0xFF if is_holtek else vp.RGB_EFFECT_SPEED_MAX)
        self.rgb_brightness.setMaximum(0xFF if is_holtek else 100)
        self.rgb_brightness_form_label.setText(
            "Brightness (raw):" if is_holtek else "Brightness:")
        self._update_rgb_brightness_label(self.rgb_brightness.value())
        self._update_rgb_effect_controls()

        self.dpi_profile_controls.setVisible(True)
        self.dpi_stage_count_spin.setMaximum(10 if is_holtek else 5)
        self.dpi_active_stage_label.setVisible(is_holtek)
        self.dpi_active_stage_spin.setVisible(is_holtek)
        self.dpi_header.setText(
            "Per-profile DPI stages (Holtek stores 1–10 stages at 200-DPI "
            "increments)." if is_holtek else
            "DPI slots (presets are captured values; custom conversion is "
            "approximate and sensor-dependent)")
        preset_values = (sorted(hp.DPI_PRESETS) if is_holtek
                         else sorted(vp.DPI_PRESETS))
        for combo, dpi_spin, value_spin, tweak_spin in self.dpi_rows:
            current_dpi = dpi_spin.value()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Custom", None)
            for dpi in preset_values:
                combo.addItem(f"{dpi} DPI", dpi)
            preset_index = combo.findData(current_dpi)
            combo.setCurrentIndex(preset_index if preset_index >= 0 else 0)
            combo.blockSignals(False)
            dpi_spin.setRange(200 if is_holtek else 100,
                              28000 if is_holtek else 20000)
            dpi_spin.setSingleStep(200 if is_holtek else 100)
            value_spin.setVisible(not is_holtek)
            tweak_spin.setVisible(not is_holtek)
        for label in self.dpi_raw_labels + self.dpi_check_labels:
            label.setVisible(not is_holtek)
        self._update_dpi_row_visibility()

    def _require_device(self, auto_mode: bool = False) -> bool:
        """Check if a device path is available for transient connections."""
        if self.device_path is None:
            # Try to refresh and find devices
            self._refresh_devices()
            
        if self.device_path is None:
            if not auto_mode:
                QtWidgets.QMessageBox.warning(self, "No device", "No device found. Please connect your mouse.")
            return False
        return True


    def _send_reports(self, reports: list[bytes], label: str,
                      quiet: bool = False) -> bool:
        """Send reports using a transient device connection."""
        if quiet and self.device_path is None:
            return False
        if not quiet and not self._require_device():
            return False

        device = None
        try:
            # Open device transiently using factory
            device = dd.create_device(self.device_type, self.device_path)
            device.open()
            
            for report in reports:
                if device.send_reliable(report):
                    self._log(f"{label}: {report.hex()}")
                else:
                    self._log(f"TIMEOUT: {report.hex()}")
                    raise RuntimeError(
                        getattr(device, "last_error", "") or
                        f"Device timed out on command {report[1]:02X}")
            return True
        except Exception as exc:
            self._log(f"{label}: {exc}")
            if not quiet:
                QtWidgets.QMessageBox.critical(self, "Send failed", str(exc))
            return False
        finally:
            # Always close the device
            if device:
                device.close()


    def _sync_all_buttons(self) -> None:
        """Stage the cached assignments and use the normal transaction path."""
        for key, assignment in self.button_assignments.items():
            self.staging_manager.stage_change(
                key, assignment["action"], assignment.get("params", {}))
        self._update_staged_visuals()
        self._commit_staged_changes()


    def _auto_stage_binding(self) -> None:
        """Auto-stage the current binding silently (no validation warnings)."""
        if self._populating_editor:
            return
        self._apply_button_binding(silent=True)

    def _apply_button_binding(self, silent: bool = False) -> None:
        if not self.current_edit_key:
            return
        if self.action_select.currentData() == "__preserve_unknown__":
            return

        action = self.action_select.currentText()
        params = {}

        # VALIDATION & PARAMS
        if action == "Macro":
            mode = self.macro_repeat_combo.currentData()
            count = self.macro_repeat_count.value() if mode == 0x02 else mode
            params = {
                "index": self.macro_index_spin.value(),
                "mode": count
            }
        elif action == "Keyboard Key":
            special_key = self.special_key_combo.currentData()
            if special_key:
                key_name = special_key
            else:
                if self.key_select.isEmpty():
                    if not silent:
                        QtWidgets.QMessageBox.warning(self, "Invalid", "Please press a key combination or choose a special key.")
                    return
                key_name = self.key_select.hidName()

            if not key_name:
                if not silent:
                    QtWidgets.QMessageBox.warning(self, "Invalid", "Please press a key combination or choose a special key.")
                return
            
            hid_key = vp.HID_KEY_USAGE.get(key_name, 0) or vp.HID_KEY_USAGE.get(key_name.upper(), 0)
            
            modifier = 0
            if self.mod_ctrl.isChecked(): modifier |= vp.MODIFIER_CTRL
            if self.mod_shift.isChecked(): modifier |= vp.MODIFIER_SHIFT
            if self.mod_alt.isChecked(): modifier |= vp.MODIFIER_ALT
            if self.mod_win.isChecked(): modifier |= vp.MODIFIER_WIN
            
            params = {"key": hid_key, "mod": modifier}

        elif action in ["Left Click", "Right Click", "Middle Click", "Forward", "Back"]:
            pass 
             
        elif action == "DPI Control":
            params = {"func": self.dpi_action_select.currentData()}
             
        elif action in ["Fire Key", "Triple Click"]:
            params = {"delay": self.special_delay_spin.value(), "repeat": self.special_repeat_spin.value()}
             
        elif action == "Disabled":
            pass
             
        elif action == "Media Key":
            code = self.media_select.currentData()
            params = {"code": code}
             
        elif action == "Polling Rate Toggle":
            pass
             
        elif action == "RGB Toggle":
            pass

        # STAGE CHANGE (skip if nothing actually changed)
        effective = self.staging_manager.get_effective_state(self.current_edit_key)
        if effective is None or effective.get("action") != action or effective.get("params") != params:
            self.staging_manager.stage_change(self.current_edit_key, action, params)

        # UPDATE UI
        self._update_staged_visuals()
        
    def _get_binding_description(self, action: str, params: dict) -> str:
        """Get a descriptive string for a button binding."""
        if action == "Keyboard Key":
            hid_key = params.get("key", 0)
            modifier = params.get("mod", 0)
            key_name = self.HID_USAGE_TO_NAME.get(hid_key, f"0x{hid_key:02X}")
            
            # Use Qt names for display if available
            qt_name_map = {
                "Enter": "Return", "Escape": "Esc", "Delete": "Del", "Insert": "Ins",
                "PageUp": "PgUp", "PageDown": "PgDown", "Space": "Space"
            }
            display_key = qt_name_map.get(key_name, key_name)
            
            mods = []
            if modifier & vp.MODIFIER_CTRL: mods.append("Ctrl")
            if modifier & vp.MODIFIER_SHIFT: mods.append("Shift")
            if modifier & vp.MODIFIER_ALT: mods.append("Alt")
            if modifier & vp.MODIFIER_WIN: mods.append("Win")
            
            if mods:
                return f"Key: {display_key} ({'+'.join(mods)})"
            return f"Key: {display_key}"

        elif action == "Macro":
            index = params.get("index", 1)
            # Mode is once/hold/toggle, or a raw repeat count (1..253).
            mode_val = params.get("mode", 1)
            
            mode_str = "Custom"
            if mode_val == vp.MACRO_REPEAT_ONCE: mode_str = "Once"
            elif mode_val == vp.MACRO_REPEAT_HOLD: mode_str = "Hold"
            elif mode_val == vp.MACRO_REPEAT_TOGGLE: mode_str = "Toggle"
            else: mode_str = f"x{mode_val}"
            
            return f"Macro {index} ({mode_str})"

        elif action == "DPI Control":
            func = params.get("func", 1)
            func_map = {1: "Loop", 2: "Up", 3: "Down"}
            return f"DPI {func_map.get(func, 'Unknown')}"
            
        elif action == "Disabled":
            return "Disabled"
            
        elif action == "Media Key":
            code = params.get("code", 0)
            # Reverse lookup media key
            name = "Unknown"
            for k, v in vp.MEDIA_KEY_CODES.items():
                if v == code:
                    name = k
                    break
            return f"Media: {name}"
            
        elif action in ["Fire Key", "Triple Click"]:
            repeat = params.get("repeat", 3)
            if self.device_type == "holtek":
                return f"{action} (x{repeat})"
            delay = params.get("delay", 40)
            return f"{action} ({delay}ms, x{repeat})"

        # Default fallback for simple actions (Left Click, etc.)
        return action

    def _on_undo(self) -> None:
        """Handle Ctrl+Z: Undo last staging operation."""
        if self.staging_manager.undo():
            self._log("Undo: Reverted last staged change.")
            self._update_staged_visuals()
            self._refresh_current_binding_editor()
        else:
            self._log("Undo: Nothing to undo.")

    def _on_redo(self) -> None:
        """Handle Ctrl+Shift+Z: Redo last undone operation."""
        if self.staging_manager.redo():
            self._log("Redo: Re-applied staging change.")
            self._update_staged_visuals()
            self._refresh_current_binding_editor()
        else:
            self._log("Redo: Nothing to redo.")

    def _refresh_current_binding_editor(self) -> None:
        """Refresh the selected editor and preview from effective state."""
        if not self.current_edit_key:
            return
        self._update_ui_from_assignment(self.current_edit_key)
        effective = self.staging_manager.get_effective_state(
            self.current_edit_key)
        if effective:
            description = self._get_binding_description(
                effective.get("action", ""), effective.get("params", {}))
            self.feedback_action_label.setText(f"Action: {description}")

    def _update_staged_visuals(self) -> None:
        """Update button list to show staged vs committed state."""
        staged = self.staging_manager.get_staged_changes()
        has_changes = len(staged) > 0
        
        self.apply_all_button.setEnabled(has_changes)
        self.discard_all_button.setEnabled(has_changes)
        
        for row in range(self.btn_table.rowCount()):
             key = self.btn_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
             item_assign = self.btn_table.item(row, 1)
             
             if key in staged:
                 entry = staged[key]
                 desc = self._get_binding_description(entry["action"], entry["params"])
                 item_assign.setText(f"{desc} *")
                 # Orange/Yellow for staged
                 item_assign.setForeground(QtGui.QBrush(QtGui.QColor("#FFA500"))) 
                 # Bold font for emphasis
                 font = item_assign.font()
                 font.setBold(True)
                 item_assign.setFont(font)
                 
             elif key in self.button_assignments:
                 entry = self.button_assignments[key]
                 desc = self._get_binding_description(entry["action"], entry["params"])
                 item_assign.setText(desc)
                 # Standard white/gray for committed
                 item_assign.setForeground(QtGui.QBrush(
                     self.palette().color(QtGui.QPalette.ColorRole.Text)))
                 font = item_assign.font()
                 font.setBold(False)
                 item_assign.setFont(font)
             else:
                 item_assign.setText("Unknown")
                 item_assign.setForeground(QtGui.QBrush(QtGui.QColor("gray")))

    def _commit_staged_changes(self) -> None:
        """Commit all staged changes to the device using TransactionController."""
        if not self._require_device():
            return
            
        if not self.staging_manager.has_changes():
            return

        class PacketBuilder:
            def __init__(self, parent):
                self.parent = parent
                
            def build_packets(self, key, action, params):
                return self.parent._build_packets_for_key(key, action, params)

        device = None
        progress = None
        success = False
        failure: Exception | None = None
        try:
            device = dd.create_device(self.device_type, self.device_path)
            device.open()

            # Holtek: enter write mode before sending packets
            if self.device_type == 'holtek':
                device.enter_write_mode()
            elif not device.begin_write():
                raise RuntimeError(device.last_error or "Mouse did not enter ready state")

            builder = PacketBuilder(self)
            controller = TransactionController(device, builder, logger=self._log)

            # Progress dialog
            progress = QtWidgets.QProgressDialog(
                "Applying changes...", None, 0, 0, self)
            progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            progress.show()

            success = controller.execute_transaction(self.staging_manager)

            # Holtek: commit button writes and reset device to reload
            if self.device_type == 'holtek' and success:
                progress.setLabelText("Restarting device, please wait...")
                progress.setCancelButton(None)
                QtWidgets.QApplication.processEvents()
                device.commit_writes(categories=0x02)  # Button category + reset
                # Device handle is dead after reset — close may fail, that's OK
                try:
                    device.close()
                except Exception:
                    pass
                device = None
                self._holtek_reconnect()
        except Exception as exc:
            failure = exc
        finally:
            if device:
                try:
                    device.close()
                except Exception:
                    pass
            if progress:
                progress.close()

        if failure is not None:
            QtWidgets.QMessageBox.critical(self, "Error", str(failure))
        elif success:
            self.button_assignments = deepcopy(self.staging_manager.base_state)
            self._update_staged_visuals()
            self._refresh_current_binding_editor()
            QtWidgets.QMessageBox.information(
                self, "Success", "All changes applied successfully.")
        else:
            QtWidgets.QMessageBox.critical(
                self, "Partial Write Possible",
                "A write failed. Earlier acknowledged changes may already be "
                "stored on the device; read settings again before retrying.")

    def _discard_staged_changes(self) -> None:
        """Discard all staged changes."""
        self.staging_manager.clear_stage()
        self._update_staged_visuals()
        self._refresh_current_binding_editor()

    def _build_packets_for_key(self, key: str, action: str, params: dict) -> list[bytes]:
        """Helper to build packets for a single key binding."""
        # Holtek: use holtek_protocol's packet builder
        if self.device_type == 'holtek':
            btn_profile = self.active_button_profiles.get(key)
            if btn_profile is None:
                raise ValueError(f"Unknown button: {key}")
            return hp.build_write_packets(btn_profile.index, action, params,
                                          profile=self.holtek_profile)

        reports = []
        code_hi, code_lo, apply_offset = self._resolve_profile(key, use_fallback=True)

        if action == "Keyboard Key":
            reports.extend(vp.build_key_binding(
                code_hi, code_lo, params.get("key", 0), params.get("mod", 0)))
            reports.append(vp.build_keyboard_bind(apply_offset))
        elif action == "Media Key":
            reports.extend(vp.build_consumer_binding(
                code_hi, code_lo, params.get("code", 0)))
            reports.append(vp.build_keyboard_bind(apply_offset))
        elif action == "Disabled":
            reports.append(vp.build_disabled(apply_offset))
        elif action in ["Left Click", "Right Click", "Middle Click", "Forward", "Back"]:
            val_map = {"Left Click": 0x01, "Right Click": 0x02,
                       "Middle Click": 0x04, "Back": 0x08, "Forward": 0x10}
            reports.append(vp.build_mouse_param(apply_offset, val_map[action]))
        elif action == "DPI Control":
            reports.append(vp.build_dpi_control(apply_offset, params.get("func", 1)))
        elif action in ["Fire Key", "Triple Click"]:
            reports.append(vp.build_special_binding(
                apply_offset, params.get("delay", 40), params.get("repeat", 3)))
        elif action == "Polling Rate Toggle":
            reports.append(vp.build_poll_rate_toggle(apply_offset))
        elif action == "RGB Toggle":
            reports.append(vp.build_rgb_toggle(apply_offset))
        elif action == "Macro":
            reports.append(vp.build_macro_bind(
                apply_offset, params.get("index", 1) - 1,
                params.get("mode", vp.MACRO_REPEAT_ONCE)))
        else:
            raise ValueError(f"Unsupported button action: {action}")
                 
        return reports


    def _upload_macro(self) -> bool:
        """Collect current macro and upload to device."""
        if not self._require_device():
            return False
        if self.device_type == "holtek":
            QtWidgets.QMessageBox.information(
                self, "Not Supported",
                "Hardware macros use the Areson protocol and are not "
                "available on the Holtek Venus MMO.")
            return False
        
        macro_index = self.macro_bind_index_spin.value() - 1  # 0-indexed internally
        if macro_index < 0 or macro_index > 15:
            QtWidgets.QMessageBox.warning(self, "Invalid", "Macro Index must be 1-16.")
            return False
        try:
            # 1. Collect events from table
            if self.macro_event_table.rowCount():
                final_delay = self.macro_event_table.cellWidget(
                    self.macro_event_table.rowCount() - 1, 3)
                if final_delay:
                    final_delay.setValue(vp.MACRO_MIN_DELAY_MS)
            raw_events = self._get_macro_events_from_table()
            if not raw_events:
                QtWidgets.QMessageBox.warning(self, "Error", "No valid events to upload.")
                return False

            # Preserve the editor's explicit press/release stream.  Rebuilding
            # it from key-down rows destroyed mouse events and intentionally
            # overlapping key sequences.
            events = list(raw_events)

            if not events:
                QtWidgets.QMessageBox.warning(self, "Error", "No valid events to upload.")
                return False

            if len(events) > vp.MACRO_MAX_EVENTS:
                QtWidgets.QMessageBox.warning(
                    self, "Too Many Events",
                    f"A hardware macro slot holds at most {vp.MACRO_MAX_EVENTS} events.")
                return False
            
            # 2. Build macro data buffer
            macro_name = self.macro_name_edit.text() or "Macro"
            full_macro = vp.build_macro_image(macro_name, events)
            
            # Get slot address
            page, offset = vp.get_macro_slot_info(macro_index)
            
            self._log(f"Uploading Macro {macro_index+1} ({macro_name}) to Page 0x{page:02X} Offset 0x{offset:02X}...")
            
            # Build reports
            reports = [vp.build_simple(vp.CMD_READY)]
            
            # Split into 10-byte chunks
            addr = (page << 8) | offset
            for i in range(0, len(full_macro), 10):
                chunk = full_macro[i:i+10]
                chunk_addr = addr + i
                chunk_page = (chunk_addr >> 8) & 0xFF
                chunk_off = chunk_addr & 0xFF
                reports.append(vp.build_macro_chunk(chunk_off, chunk, chunk_page))
            
            success = self._send_reports(
                    reports,
                    f"Macro {macro_index+1} Upload ({len(full_macro)} bytes)")
            if success:
                QtWidgets.QMessageBox.information(
                    self, "Success", f"Macro {macro_index+1} uploaded successfully!")
            return success

        except Exception as e:
            self._log(f"Macro Upload Error: {e}")
            QtWidgets.QMessageBox.critical(self, "Upload Error", str(e))
            return False

    def _bind_macro_to_button(self) -> None:
        """Rebind an already-uploaded macro to a different button using Sync logic."""
        if not self._require_device():
            return
            
        button_key = self.macro_button_select.currentData()
        macro_index = self.macro_bind_index_spin.value()
        repeat_mode = self.macro_tab_repeat_combo.currentData()
        repeat_count = self.macro_tab_repeat_count_spin.value()
        effective_repeat = repeat_count if repeat_mode == vp.MACRO_REPEAT_COUNT else repeat_mode
        
        self.staging_manager.stage_change(
            button_key, "Macro",
            {"index": macro_index, "mode": effective_repeat})
        self._update_staged_visuals()
        self._log(
            f"Binding macro slot {macro_index} to {button_key} "
            f"(repeat 0x{effective_repeat:02X})")
        self._commit_staged_changes()


    def _apply_rgb_custom(self) -> None:
        if not self._require_device():
            return
        r = self.rgb_current_color.red()
        g = self.rgb_current_color.green()
        b = self.rgb_current_color.blue()
        mode = self.rgb_mode.currentData()
        brightness = self.rgb_brightness.value()

        if self.device_type == 'holtek':
            return self._apply_rgb_holtek(
                r, g, b, mode, brightness, self.rgb_speed.value())

        if self.battery_led_enabled:
            self._set_battery_led_enabled(False, restore=False)

        rgb_packets = vp.build_rgb_packets(
            r, g, b, mode, brightness, self.rgb_speed.value())
        reports = [vp.build_simple(vp.CMD_READY), *rgb_packets]

        mode_name = self.rgb_mode.currentText()
        self._send_reports(reports, f"RGB Custom: #{r:02x}{g:02x}{b:02x} {mode_name} {brightness}%")


    def _apply_polling_rate(self) -> None:
        rate = self.polling_select.currentData()

        if self.device_type == 'holtek':
            return self._apply_polling_holtek(rate)

        payload = vp.POLLING_RATE_PAYLOADS[rate]
        reports = [vp.build_simple(vp.CMD_READY), vp.build_report(vp.CMD_WRITE, payload)]
        self._send_reports(reports, f"Polling {rate} Hz")

    def _sync_dpi_presets(self) -> None:
        for combo, dpi_spin, value_spin, tweak_spin in self.dpi_rows:
            dpi_value = combo.currentData()
            if dpi_value is None:
                continue
            dpi_spin.blockSignals(True)
            value_spin.blockSignals(True)
            tweak_spin.blockSignals(True)
            dpi_spin.setValue(dpi_value)
            if self.device_type == "holtek":
                raw_value = hp.dpi_to_raw(dpi_value)
            else:
                raw_value = vp.DPI_PRESETS[dpi_value]["value"]
            value_spin.setValue(raw_value)
            tweak_spin.setValue(vp.dpi_value_to_tweak(raw_value))
            dpi_spin.blockSignals(False)
            value_spin.blockSignals(False)
            tweak_spin.blockSignals(False)

    def _apply_dpi(self) -> None:
        if self.device_type == 'holtek':
            return self._apply_dpi_holtek()

        reports = [vp.build_simple(vp.CMD_READY)]
        reports.append(vp.build_dpi_stage_count(self._dpi_stage_count()))
        for slot, (_, _, value_spin, tweak_spin) in enumerate(
                self.dpi_rows[:self._dpi_stage_count()]):
            value = value_spin.value()
            tweak = vp.dpi_value_to_tweak(value)
            tweak_spin.setValue(tweak)
            reports.append(vp.build_dpi(slot, value, tweak))
        self._send_reports(reports, "DPI slots")

    def _on_dpi_spin_changed(self, row_index: int) -> None:
        if row_index >= len(self.dpi_rows):
            return
        combo, dpi_spin, value_spin, tweak_spin = self.dpi_rows[row_index]
        dpi_value = dpi_spin.value()
        if self.device_type == "holtek":
            dpi_value = max(200, min(28000,
                            int(round(dpi_value / 200)) * 200))
            if dpi_spin.value() != dpi_value:
                dpi_spin.blockSignals(True)
                dpi_spin.setValue(dpi_value)
                dpi_spin.blockSignals(False)
            value = hp.dpi_to_raw(dpi_value)
        else:
            value = vp.dpi_to_value(dpi_value)
        tweak = vp.dpi_value_to_tweak(value)

        combo.blockSignals(True)
        idx = combo.findData(dpi_value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

        value_spin.blockSignals(True)
        tweak_spin.blockSignals(True)
        value_spin.setValue(value)
        tweak_spin.setValue(tweak)
        value_spin.blockSignals(False)
        tweak_spin.blockSignals(False)

    def _on_dpi_value_changed(self, row_index: int) -> None:
        if row_index >= len(self.dpi_rows):
            return
        combo, dpi_spin, value_spin, tweak_spin = self.dpi_rows[row_index]
        value = value_spin.value()
        tweak = vp.dpi_value_to_tweak(value)
        dpi_value = vp.value_to_dpi(value)

        combo.blockSignals(True)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

        dpi_spin.blockSignals(True)
        tweak_spin.blockSignals(True)
        dpi_spin.setValue(dpi_value)
        tweak_spin.setValue(tweak)
        dpi_spin.blockSignals(False)
        tweak_spin.blockSignals(False)

    def _on_profile_changed(self, index: int) -> None:
        """Handle profile selector change — re-read settings for the new profile."""
        if index < 0:
            return
        self.holtek_profile = self.profile_combo.currentData()
        if self.holtek_profile is None:
            self.holtek_profile = 0
        self._log(f"Profile switched to {self.holtek_profile + 1}")

        # Discard any staged changes (they belong to the previous profile)
        if self.staging_manager.has_changes():
            self.staging_manager.clear_stage()
            self._update_staged_visuals()

        # Re-read settings from device for the newly selected profile
        if self.device_path and self.device_type == 'holtek':
            self._read_settings_holtek(silent=True)

    def _holtek_reconnect(self) -> None:
        """Wait for Holtek device to reconnect after reset and update path.

        Uses processEvents during the wait so the GUI stays responsive and
        does not interfere with USB re-enumeration.
        """
        self._log("  Waiting for device to reconnect...")
        # Initial wait — device needs time to fully disconnect before re-enumerating
        deadline = time.time() + 2.0
        while time.time() < deadline:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.1)

        # Poll for reconnection
        deadline = time.time() + 8.0
        while time.time() < deadline:
            new_path = hp.find_device_path()
            if new_path:
                self.device_path = new_path
                self._log(f"  Device reconnected: {new_path}")
                return
            QtWidgets.QApplication.processEvents()
            time.sleep(0.3)

        self._log("  Warning: device did not reconnect within timeout")

    def _apply_rgb_holtek(self, r: int, g: int, b: int, mode: int,
                          brightness: int, speed: int) -> None:
        """Apply RGB settings on Holtek device."""
        if not self._require_device():
            return
        device = None
        progress = QtWidgets.QProgressDialog("Applying lighting...", None, 0, 0, self)
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.show()
        QtWidgets.QApplication.processEvents()
        try:
            device = hp.HoltekDevice(self.device_path)
            device.open()
            device.enter_write_mode()
            profile = self.holtek_profile
            packets = hp.build_led_packets(
                r, g, b, mode, brightness, speed, profile=profile)
            for pkt in packets:
                device.send_feature(pkt)
                time.sleep(0.008)
            # Commit LED and reset device to reload settings from flash
            progress.setLabelText("Restarting device, please wait...")
            QtWidgets.QApplication.processEvents()
            device.commit_writes(categories=0x08)
            # Device handle is dead after reset — close may fail
            try:
                device.close()
            except Exception:
                pass
            device = None
            mode_name = self.rgb_mode.currentText()
            self._log(
                f"Holtek RGB (profile {profile + 1}): "
                f"#{r:02x}{g:02x}{b:02x} {mode_name} "
                f"brightness={brightness} speed={speed}")
            # Wait for device to reconnect after reset
            self._holtek_reconnect()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "RGB failed", str(exc))
        finally:
            progress.close()
            if device:
                device.close()

    def _apply_polling_holtek(self, rate: int) -> None:
        """Apply polling rate on Holtek device using F5 command."""
        if not self._require_device():
            return
        device = None
        try:
            device = hp.HoltekDevice(self.device_path)
            device.open()
            device.set_polling_rate(rate)
            self._log(f"Holtek Polling: {rate} Hz")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Polling rate failed", str(exc))
        finally:
            if device:
                device.close()

    def _apply_dpi_holtek(self) -> None:
        """Apply DPI settings on Holtek device."""
        if not self._require_device():
            return
        device = None
        progress = QtWidgets.QProgressDialog("Applying DPI...", None, 0, 0, self)
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.show()
        QtWidgets.QApplication.processEvents()
        try:
            device = hp.HoltekDevice(self.device_path)
            device.open()
            device.enter_write_mode()
            # Collect DPI values from the UI (dpi_spin = actual DPI in CPI)
            dpi_values = []
            for _, dpi_spin, _, _ in self.dpi_rows[:self._dpi_stage_count()]:
                dpi_values.append(dpi_spin.value())
            # Write DPI to the selected profile only
            profile = self.holtek_profile
            packets = hp.build_dpi_packets(
                dpi_values,
                profile=profile,
                current_stage=self.dpi_active_stage_spin.value() - 1,
                color_indices=self.holtek_dpi_colors,
            )
            for pkt in packets:
                device.send_feature(pkt)
                time.sleep(0.008)
            # Commit DPI and reset device to reload settings from flash
            progress.setLabelText("Restarting device, please wait...")
            QtWidgets.QApplication.processEvents()
            device.commit_writes(categories=0x04)
            # Device handle is dead after reset — close may fail
            try:
                device.close()
            except Exception:
                pass
            device = None
            self._log(f"Holtek DPI (profile {profile + 1}): {dpi_values}")
            # Wait for device to reconnect after reset
            self._holtek_reconnect()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "DPI failed", str(exc))
        finally:
            progress.close()
            if device:
                device.close()

    def _send_built_report(self) -> None:
        if not self._require_device():
            return
        if self.device_type == "holtek":
            QtWidgets.QMessageBox.warning(
                self, "Wrong Protocol",
                "Built reports on this tab use the 17-byte Areson format and "
                "cannot be sent to a Holtek device.")
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
        if self.device_type == "holtek":
            QtWidgets.QMessageBox.warning(
                self, "Wrong Protocol",
                "Raw reports on this tab use the 17-byte Areson format and "
                "cannot be sent to a Holtek device.")
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

        if self.device_type == 'holtek':
            QtWidgets.QMessageBox.information(self, "Not Supported",
                "Factory reset is not yet supported for the Holtek Venus MMO.\n"
                "Please use the Windows software for factory reset.")
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Reset",
            "Are you sure you want to reset the device to factory defaults?\nThis will clear all custom button mappings, macros, and RGB settings.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            if self._send_reports(
                    [vp.build_simple(vp.CMD_FACTORY_RESET)], "Factory reset"):
                QtWidgets.QMessageBox.information(
                    self, "Reset Complete", "Factory reset command acknowledged.")

    def _reclaim_device(self) -> None:
        """Attempt to reclaim all Venus devices from other processes."""
        self._log("USB: Attempting to reclaim Venus devices from other processes...")
        found = False
        for vid, pid in sorted(vp.SUPPORTED_DEVICE_IDS):
            if vp.reclaim_device(vid, pid):
                self._log(f"USB: Reclaim attempt sent to {vid:04X}:{pid:04X}")
                found = True
        
        if found:
            self._log("USB: Reclaim sequence complete. Refreshing...")
            time.sleep(1.0)
            self._refresh_and_connect()
        else:
            self._log("USB: No devices found to reclaim.")
            QtWidgets.QMessageBox.information(self, "Device Reclaim", "No Venus Pro devices found on the USB bus.")

    def _read_settings(self, silent: bool = False) -> None:
        if not self._require_device(auto_mode=silent):
            return

        if self.device_type == 'holtek':
            return self._read_settings_holtek(silent=silent)

        self._log("--- Reading from Device ---")
        device = None
        try:
            # Open device transiently for reading
            device = vp.VenusDevice(self.device_path)
            device.open()
            
            # Retry loop for initial handshake
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if not device.start_session():
                        raise vp.ProtocolError("startup challenge was rejected")
                    break # Success
                except Exception as e:
                    if attempt < max_retries - 1:
                        self._log(f"Read handshake failed (Attempt {attempt+1}): {e}. Retrying...")
                        time.sleep(0.5)
                        # Re-open might be needed?
                        device.close()
                        time.sleep(0.1)
                        device.open()
                    else:
                        raise e
            
            # The vendor utility reads the 0x0000..0x009f configuration block.
            page0 = bytearray()
            for offset in range(0, 0xA0, 10):
                chunk = device.read_flash(0, offset, 10)
                page0.extend(chunk)
            
            # Page 1 contains keyboard mappings (Part 1)
            page1 = bytearray()
            for offset in range(0, 256, 10):
                length = min(10, 256 - offset)
                chunk = device.read_flash(1, offset, length)
                page1.extend(chunk)

            # Page 2 contains keyboard mappings (Part 2)
            page2 = bytearray()
            for offset in range(0, 256, 10):
                length = min(10, 256 - offset)
                chunk = device.read_flash(2, offset, length)
                page2.extend(chunk)


            self._log("Flash pages 0 and 1 read complete.")

            # 1. DPI Levels
            stage_count = page0[0x02]
            if 1 <= stage_count <= 5:
                self.dpi_stage_count_spin.setValue(stage_count)
                self._update_dpi_row_visibility()
                self._log(f"  Enabled DPI stages: {stage_count}")
            dpi_offsets = [0x0C, 0x10, 0x14, 0x18, 0x1C]
            for i, offset in enumerate(dpi_offsets):
                val = page0[offset]
                closest_dpi = 1000
                min_diff = 999
                for dpi, info in vp.DPI_PRESETS.items():
                    if abs(info["value"] - val) < min_diff:
                        min_diff = abs(info["value"] - val)
                        closest_dpi = dpi
                
                if i < len(self.dpi_rows):
                    combo, dpi_spin, value_spin, tweak_spin = self.dpi_rows[i]
                    combo.blockSignals(True)
                    # Do not label an arbitrary raw value as a factory preset.
                    exact_preset = vp.DPI_PRESETS.get(closest_dpi, {}).get("value") == val
                    if exact_preset:
                        for idx in range(combo.count()):
                            if combo.itemData(idx) == closest_dpi:
                                combo.setCurrentIndex(idx)
                                break
                    else:
                        combo.setCurrentIndex(0)  # Custom
                    
                    dpi_spin.blockSignals(True)
                    value_spin.blockSignals(True)
                    tweak_spin.blockSignals(True)
                    dpi_spin.setValue(vp.value_to_dpi(val))
                    value_spin.setValue(val)
                    tweak_spin.setValue(page0[offset + 3])
                    dpi_spin.blockSignals(False)
                    value_spin.blockSignals(False)
                    tweak_spin.blockSignals(False)

                    combo.blockSignals(False)

            # 2. Polling Rate
            poll_code = page0[0x00]
            rate = vp.POLLING_CODE_TO_RATE.get(poll_code)
            
            # Find the rate in the combo box
            for i in range(self.polling_select.count()):
                if rate is not None and self.polling_select.itemData(i) == rate:
                    self.polling_select.setCurrentIndex(i)
                    self._log(f"  Polling Rate: {rate}Hz")
                    break

            # 3. RGB Settings
            rgb_r = page0[0x54]
            rgb_g = page0[0x55]
            rgb_b = page0[0x56]
            rgb_mode_raw = page0[0x58]
            rgb_mode = vp.rgb_mode_from_hardware(rgb_mode_raw)
            brightness_b1 = page0[0x5A]
            brightness = (100 if brightness_b1 == 0xFF else
                          0 if brightness_b1 <= 1 else
                          min(100, round(brightness_b1 / 3)))

            # While battery mode owns the hardware LED, retain the saved
            # manual lighting in the controls so disabling can restore it.
            if self.battery_led_enabled and self._battery_led_restore:
                self._apply_rgb_restore_to_widgets(self._battery_led_restore)
            else:
                self._set_custom_color(QtGui.QColor(rgb_r, rgb_g, rgb_b))
                mode_index = self.rgb_mode.findData(rgb_mode)
                if mode_index >= 0:
                    self.rgb_mode.setCurrentIndex(mode_index)
                self.rgb_brightness.setValue(brightness)
                self.rgb_speed.setValue(max(
                    vp.RGB_EFFECT_SPEED_MIN,
                    min(vp.RGB_EFFECT_SPEED_MAX, page0[0x5C])))
            self._log(
                f"  RGB: ({rgb_r},{rgb_g},{rgb_b}), "
                f"Mode: 0x{rgb_mode_raw:02X}, Brightness: {brightness}%")

            # 4. Button Bindings
            self._log("  Parsing Button bindings...")
            for button_key, profile in vp.BUTTON_PROFILES.items():
                offset = profile.apply_offset
                btype = page0[offset]
                d1 = page0[offset + 1]
                d2 = page0[offset + 2]
                
                action = "Disabled"
                params = {}
                
                self._log(f"DEBUG: Parsing {button_key} (Offset 0x{offset:02X}) -> Type 0x{btype:02X}, D1 0x{d1:02X}, D2 0x{d2:02X}")

                if btype == vp.BUTTON_TYPE_MOUSE:
                    action = {
                        0x01: "Left Click", 0x02: "Right Click",
                        0x04: "Middle Click", 0x08: "Back", 0x10: "Forward",
                    }.get(d1, f"Mouse Button (0x{d1:02X})")
                elif btype == vp.BUTTON_TYPE_KEYBOARD:
                    definition_page = page1 if profile.code_hi == 0x01 else page2
                    block = bytes(definition_page[profile.code_lo:profile.code_lo + 0x20])
                    count = block[0] if block else 0
                    needed = 1 + count * 3 + 1
                    if count == 0 or needed > len(block):
                        action = "Invalid Key Definition"
                    else:
                        if sum(block[:needed]) & 0xFF != 0x55:
                            self._log(f"  Warning: {button_key} key definition checksum is invalid")
                        modifiers = 0
                        keycode = None
                        consumer_usage = None
                        for event_index in range(count):
                            start = 1 + event_index * 3
                            status, code_lo, code_hi = block[start:start + 3]
                            if status == 0x80:
                                modifiers |= code_lo
                            elif status == 0x81 and keycode is None:
                                keycode = code_lo
                            elif status == 0x82 and consumer_usage is None:
                                consumer_usage = code_lo | (code_hi << 8)
                        if consumer_usage is not None:
                            action = "Media Key"
                            params = {"code": consumer_usage}
                        elif keycode is not None:
                            action = "Keyboard Key"
                            params = {"key": keycode, "mod": modifiers}
                        else:
                            action = "Unknown Key Definition"
                elif btype == vp.BUTTON_TYPE_DPI_LEGACY:
                    action = "DPI Control"
                    params = {"func": d1}
                elif btype == vp.BUTTON_TYPE_MACRO:
                    action = "Macro"
                    macro_index = d1
                    params["index"] = macro_index + 1
                    self._log(f"  DEBUG: Macro Index {macro_index+1}")
                    
                    # D2 is repeat mode/count
                    params["mode"] = d2
                    if d2 >= 0x01 and d2 <= 0xFD: # Repeat Count
                        params["count"] = d2
                    else:
                        params["count"] = 1 # Default for other modes
                    
                    params["name"] = self.macro_names.get(
                        macro_index + 1, f"Macro {macro_index + 1}")
                elif btype == vp.BUTTON_TYPE_SPECIAL:
                    action = "Triple Click" if d1 == 50 else "Fire Key"
                    params["delay"] = d1
                    params["repeat"] = d2
                elif btype == vp.BUTTON_TYPE_POLL_RATE:
                    action = "Polling Rate Toggle"
                elif btype == vp.BUTTON_TYPE_RGB_TOGGLE:
                    action = "RGB Toggle"

                self.button_assignments[button_key] = {"action": action, "params": params}
                self._log(f"  DEBUG: Resolved Action: {action} {params}")

            self._log("Button bindings parsed.")
            
            # Load base state into staging manager
            self.staging_manager.load_base_state(self.button_assignments)
            self._update_staged_visuals()
            self._refresh_current_binding_editor()
            
            # No trailing commit needed after reads - device auto-exits read mode
            # Sending 0x04/0x03 here would RE-ENTER config mode and break button inputs!
            
            self._log("--- Done Reading ---")
            self.status_label.setText("Status: Ready — configuration read")
            self.status_label.setStyleSheet("")
            if not silent:
                QtWidgets.QMessageBox.information(
                    self, "Read Success",
                    "Configuration successfully read from device.")

        except Exception as e:
            self._log(f"Error reading configuration: {e}")
            self.status_label.setText("Status: Read failed — see log")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            if not silent:
                QtWidgets.QMessageBox.critical(self, "Read Error", str(e))
        finally:
            # Always close the device
            if device:
                device.close()

    def _read_settings_holtek(self, silent: bool = False,
                              use_active_profile: bool = False) -> None:
        """Read settings from Holtek Venus MMO device.

        Args:
            silent: If True, suppress the success message box (used during profile switch).
            use_active_profile: Select and read the profile currently active on
                the mouse. Used once during device connection.
        """
        profile = self.holtek_profile
        profile_description = "active profile" if use_active_profile else f"Profile {profile + 1}"
        self._log(f"--- Reading from Holtek Device ({profile_description}) ---")
        device = None
        try:
            device = hp.HoltekDevice(self.device_path)
            device.open()

            config = hp.read_all_config(
                device, profile=None if use_active_profile else profile)
            if use_active_profile:
                profile = max(0, min(4, int(config.get("active_profile", 0))))
                self.holtek_profile = profile
                self.profile_combo.blockSignals(True)
                self.profile_combo.setCurrentIndex(profile)
                self.profile_combo.blockSignals(False)
            buttons = config['buttons']

            self._log(f"  Read {len(buttons)} button entries from device")

            # Parse button assignments into GUI format
            self.button_assignments = {}
            for btn_info in buttons:
                idx = btn_info['index']
                btn_key = f"Button {idx + 1}"
                if btn_key not in self.active_button_profiles:
                    continue

                action, params = hp.button_action_to_gui(
                    btn_info['type'], btn_info['code'],
                    type_hi=btn_info.get('type_hi', 0))
                self.button_assignments[btn_key] = {"action": action, "params": params}
                self._log(f"  {btn_key}: {action} {params}")

            # Fill missing buttons with Disabled
            for btn_key in self.active_button_profiles:
                if btn_key not in self.button_assignments:
                    self.button_assignments[btn_key] = {"action": "Disabled", "params": {}}

            # Load base state into staging manager
            self.staging_manager.load_base_state(self.button_assignments)
            self._update_staged_visuals()
            self._refresh_current_binding_editor()

            # Update DPI spinboxes from per-profile values
            dpi_stages = config.get('dpi_stages', [])
            if dpi_stages:
                self._log(f"  DPI stages: {dpi_stages}")
                self.dpi_stage_count_spin.blockSignals(True)
                self.dpi_stage_count_spin.setValue(len(dpi_stages))
                self.dpi_stage_count_spin.blockSignals(False)
                self.dpi_active_stage_spin.setValue(
                    max(1, min(len(dpi_stages),
                               int(config.get('dpi_stage_current', 0)) + 1)))
                self.holtek_dpi_colors = list(
                    config.get('dpi_colors', []))
                for i, dpi_val in enumerate(dpi_stages):
                    if i < len(self.dpi_rows):
                        _, dpi_spin, value_spin, tweak_spin = self.dpi_rows[i]
                        dpi_spin.blockSignals(True)
                        dpi_spin.setValue(dpi_val)
                        dpi_spin.blockSignals(False)
                self._update_dpi_row_visibility()

            # Reflect the entire per-profile LED record. Applying without an
            # intentional edit must not silently replace mode, brightness, or speed.
            led = config.get('led', {})
            if led:
                r, g, b = led.get('r', 0), led.get('g', 0), led.get('b', 0)
                mode = led.get('mode', 3)
                brightness = led.get('brightness', 5)
                speed = led.get('speed', 1)
                self._log(f"  LED: #{r:02x}{g:02x}{b:02x} mode={mode} brightness={brightness} speed={speed}")
                self.rgb_current_color = QtGui.QColor(r, g, b)
                if hasattr(self, 'rgb_color_button'):
                    color = self.rgb_current_color
                    self.rgb_color_button.setStyleSheet(
                        f"background-color: {color.name()}; "
                        f"color: {'white' if color.lightness() < 128 else 'black'}; "
                        f"font-weight: bold;")
                mode_index = self.rgb_mode.findData(mode)
                if mode_index >= 0:
                    self.rgb_mode.setCurrentIndex(mode_index)
                self.rgb_brightness.setValue(brightness)
                self.rgb_speed.setValue(speed)

            # Log raw data for debugging
            dpi_raw = config.get('dpi_raw', b'')
            if dpi_raw:
                self._log(f"  DPI raw: {dpi_raw.hex()}")
            led_raw = config.get('led_raw', b'')
            if led_raw:
                self._log(f"  LED raw: {led_raw.hex()}")

            self._log(f"--- Done Reading Holtek (Profile {profile + 1}) ---")
            if not silent:
                QtWidgets.QMessageBox.information(self, "Read Success", "Holtek configuration successfully read from device.")

        except Exception as e:
            self._log(f"Error reading Holtek configuration: {e}")
            self.status_label.setText("Status: Read failed — see log")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            if not silent:
                QtWidgets.QMessageBox.critical(self, "Read Error", str(e))
        finally:
            if device:
                device.close()

    def _export_profile(self) -> None:
        """Dump device memory to a file."""
        if not self._require_device():
            return
        if self.device_type == 'holtek':
            QtWidgets.QMessageBox.information(self, "Not Supported",
                "Profile export is not yet supported for the Holtek Venus MMO.")
            return
            
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Profile", "profile.bin", "Binary Files (*.bin)")
        if not fname:
            return
            
        progress = QtWidgets.QProgressDialog("Exporting profile...", "Cancel", 0, 256, self)
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.show()
        
        device = None
        cancelled = False
        try:
            # Open device transiently
            device = vp.VenusDevice(self.device_path)
            device.open()
            if not device.start_session():
                raise vp.ProtocolError("startup challenge was rejected")
            
            with open(fname, "wb") as f:
                for page in range(256):
                    if progress.wasCanceled():
                        cancelled = True
                        break
                    progress.setValue(page)
                    
                    # Read page (256 bytes)
                    page_data = bytearray()
                    for offset in range(0, 256, 10):
                        length = min(10, 256 - offset)
                        chunk = device.read_flash(page, offset, length)
                        page_data.extend(chunk)
                    f.write(page_data)
            if cancelled:
                self._log(f"Profile export canceled; partial dump remains at {fname}")
                QtWidgets.QMessageBox.information(
                    self, "Export Canceled", f"A partial dump remains at {fname}")
            else:
                progress.setValue(256)
                self._log(f"Profile exported to {fname}")
                QtWidgets.QMessageBox.information(
                    self, "Export Successful", f"Profile saved to {fname}")
        except Exception as e:
            self._log(f"Export failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Export Failed", str(e))
        finally:
            if device:
                device.close()
            progress.close()

    def _import_profile(self) -> None:
        """Load profile from file and write to device."""
        if not self._require_device():
            return
        if self.device_type == 'holtek':
            QtWidgets.QMessageBox.information(self, "Not Supported",
                "Profile import is not yet supported for the Holtek Venus MMO.")
            return
            
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Profile", "", "Binary Files (*.bin)")
        if not fname:
            return
            
        try:
            data = Path(fname).read_bytes()
            if len(data) != 65536: # 256 * 256
                QtWidgets.QMessageBox.warning(self, "Invalid File", f"File size must be exactly 64KB (got {len(data)} bytes).")
                return
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Read Failed", str(e))
            return
            
        # Warning
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Import", 
            "This will overwrite ALL device settings (macros, bindings, etc) with the imported profile.\nContinue?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
            
        progress = QtWidgets.QProgressDialog("Importing profile (Writing Flash)...", "Cancel", 0, 256, self)
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.show()
        
        device = None
        imported = False
        cancelled = False
        try:
            # Open device transiently
            device = vp.VenusDevice(self.device_path)
            device.open()
            if not device.start_session():
                raise vp.ProtocolError("startup challenge was rejected")
            if not device.begin_write():
                raise RuntimeError(device.last_error or "Mouse did not enter ready state")
            
            for page in range(256):
                if progress.wasCanceled():
                    cancelled = True
                    break
                progress.setValue(page)
                
                # Extract page data
                page_start = page * 256
                page_data = data[page_start : page_start + 256]
                
                # Write in 10-byte chunks (protocol limit)
                for offset in range(0, 256, 10):
                    if progress.wasCanceled():
                        cancelled = True
                        break
                    chunk = page_data[offset : offset + 10]
                    packet = vp.build_flash_write(page, offset, chunk)
                    if not device.send_reliable(packet):
                        raise RuntimeError(
                            device.last_error or
                            f"Write failed at 0x{page:02x}{offset:02x}")
                if cancelled:
                    break

            if cancelled:
                self._log("Profile import canceled; the device contains a partial write")
                QtWidgets.QMessageBox.warning(
                    self, "Import Canceled",
                    "Import stopped after a partial write. Re-import a complete profile before relying on the device configuration.")
            else:
                imported = True
                progress.setValue(256)
                self._log(f"Profile imported from {fname}")
                QtWidgets.QMessageBox.information(
                    self, "Import Successful", "Profile successfully written to device.")
            
        except Exception as e:
            self._log(f"Import failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Import Failed", str(e))
        finally:
            if device:
                device.close()
            progress.close()
        
        # Reload settings only after a complete import (and after closing HID).
        if imported:
            self._read_settings()

    def _initialize_default_assignments(self) -> None:
        """Initialize assignments with Disabled for all known buttons."""
        for button_key in self.active_button_profiles.keys():
            self.button_assignments[button_key] = {"action": "Disabled", "params": {}}
            
    def _update_all_ui_from_assignments(self) -> None:
        """Refresh the button table and other UI."""
        for row in range(self.btn_table.rowCount()):
            key = self.btn_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
            if key in self.button_assignments:
                assign = self.button_assignments[key]
                action = assign["action"]
                desc = self._get_binding_description(action, assign.get("params", {}))
                
                self.btn_table.item(row, 1).setText(desc)
                # Reset color
                self.btn_table.item(row, 1).setForeground(QtGui.QBrush(
                    self.palette().color(QtGui.QPalette.ColorRole.Text)))


    def _load_macro_from_slot_on_tab(self) -> None:
        """Load macro from slot using the Macros tab's slot index spinner."""
        if not self._require_device():
            return
        slot_index = self.macro_bind_index_spin.value()
        self._load_macro_from_slot(slot_index)

    def _load_macro_from_slot(self, slot_index: int | None = None) -> None:
        """Read macro from selected slot and populate table."""
        if not self._require_device():
            return
            
        if slot_index is None:
            slot_index = self.macro_index_spin.value()

        self.macro_bind_index_spin.blockSignals(True)
        self.macro_bind_index_spin.setValue(slot_index)
        self.macro_bind_index_spin.blockSignals(False)
        self.macro_list.blockSignals(True)
        self.macro_list.setCurrentRow(slot_index - 1)
        self.macro_list.blockSignals(False)
            
        start_page, start_offset = vp.get_macro_slot_info(slot_index - 1)
        
        self._log(f"Reading macro slot {slot_index} (Page 0x{start_page:02X}, Offset 0x{start_offset:02X})")
        
        data = bytearray()
        device = None
        try:
            # Open device transiently
            device = vp.VenusDevice(self.device_path)
            device.open()
            if not device.start_session():
                raise vp.ProtocolError("startup challenge was rejected")

            # Read exactly one 0x180-byte slot from its absolute address.
            slot_address = (start_page << 8) | start_offset
            for relative in range(0, vp.MACRO_SLOT_SIZE, vp.MAX_DATA_LEN):
                address = slot_address + relative
                length = min(vp.MAX_DATA_LEN,
                             vp.MACRO_SLOT_SIZE - relative)
                data.extend(device.read_flash(
                    (address >> 8) & 0xFF, address & 0xFF, length))
            raw_macro = bytes(data)
                
            # Parse Name
            name_length = raw_macro[0]
            self._log(f"  Name length: {name_length} bytes")
            if 0 < name_length <= 30 and name_length % 2 == 0:
                try:
                    name = raw_macro[1:1 + name_length].decode('utf-16le')
                    self.macro_name_edit.setText(name)
                    self.macro_names[slot_index] = name
                    self._save_macro_names()
                    self._refresh_macro_list()
                except UnicodeDecodeError:
                    self.macro_name_edit.setText(f"Macro {slot_index}")
            else:
                self.macro_name_edit.setText(f"Macro {slot_index}")
                
            # Parse Events
            self.macro_event_table.setRowCount(0)
            event_offset = 0x20
            event_count = raw_macro[0x1F]
            if event_count > vp.MACRO_MAX_EVENTS:
                raise vp.ProtocolError(
                    f"macro slot reports impossible event count {event_count}")
            events_end = event_offset + event_count * 5
            expected_checksum = vp.calculate_terminator_checksum(
                raw_macro, event_count)
            if raw_macro[events_end] != expected_checksum:
                self._log(
                    f"  Warning: macro checksum is invalid "
                    f"(stored {raw_macro[events_end]:02x}, expected {expected_checksum:02x})")
            mouse_names = {
                0x01: "Mouse: Left Button",
                0x02: "Mouse: Right Button",
                0x04: "Mouse: Middle Button",
                0x08: "Mouse: Back Button",
                0x10: "Mouse: Forward Button",
            }

            for _ in range(event_count):
                if event_offset + 5 > vp.MACRO_SLOT_SIZE:
                    break
                    
                b0 = raw_macro[event_offset]
                b1 = raw_macro[event_offset+1]
                
                if b0 not in (0x81, 0x41, 0x80, 0x40, 0x84, 0x44):
                    break
                    
                keycode = b1
                delay = (raw_macro[event_offset+3] << 8) | raw_macro[event_offset+4]
                is_down = bool(b0 & 0x80)
                is_modifier = (b0 == 0x80 or b0 == 0x40)
                is_mouse = (b0 & 0x07) == 0x04

                if is_mouse:
                    key_name = mouse_names.get(keycode, f"Mouse: Button 0x{keycode:02X}")
                    self._add_event_to_table(key_name, is_down, delay,
                                             event_type="mouse", keycode=keycode,
                                             update_preview=False)
                else:
                    if is_modifier:
                        modifier_name = vp.MACRO_MODIFIER_NAMES.get(keycode)
                        key_name = (
                            f"Modifier: {modifier_name}" if modifier_name
                            else f"Modifier 0x{keycode:02X}")
                    else:
                        key_name = self.HID_USAGE_TO_NAME.get(
                            keycode, f"Key 0x{keycode:02X}")
                    self._add_event_to_table(key_name, is_down, delay, is_modifier,
                                             event_type="modifier" if is_modifier else "keyboard",
                                             keycode=keycode,
                                             update_preview=False)
                
                event_offset += 5
                
            self._update_macro_preview()
            self._log(f"Loaded macro slot {slot_index}")
            
        except Exception as e:
            self._log(f"Failed to load macro: {e}")
            QtWidgets.QMessageBox.critical(self, "Load Error", str(e))
        finally:
            if device:
                device.close()


    def _generate_text_macro(self) -> None:
        """Generate a validated fixed- or random-timing text macro."""
        text = self.quick_text_edit.toPlainText()
        if not text:
            return

        minimum, maximum = self._text_macro_timing()
        try:
            events = vp.build_text_macro_events(
                text,
                key_hold_ms=self.text_hold_spin.value(),
                delay_min_ms=minimum,
                delay_max_ms=maximum,
                extra_word_pause_ms=self.text_word_pause_spin.value(),
            )
        except ValueError as exc:
            self._set_macro_builder_status(str(exc), error=True)
            return

        append = self.text_output_mode.currentData() == "append"
        existing = self.macro_event_table.rowCount() if append else 0
        if existing + len(events) > vp.MACRO_MAX_EVENTS:
            self._set_macro_builder_status(
                f"Generation would need {existing + len(events)} events; "
                f"the slot holds {vp.MACRO_MAX_EVENTS}.", error=True)
            return
        if not append:
            self.macro_event_table.setRowCount(0)

        for event in events:
            event_type = "modifier" if event.is_modifier else event.event_type
            if event_type == "modifier":
                modifier_name = vp.MACRO_MODIFIER_NAMES.get(event.keycode)
                key_name = (
                    f"Modifier: {modifier_name}" if modifier_name
                    else f"Modifier 0x{event.keycode:02X}")
            else:
                key_name = self.HID_USAGE_TO_NAME.get(
                    event.keycode, f"Key 0x{event.keycode:02X}")
            self._add_event_to_table(
                key_name, event.is_down, event.delay_ms,
                event.is_modifier, event_type, event.keycode,
                update_preview=False)
        self._update_macro_preview()
        mode = "Appended" if append else "Generated"
        self._log(f"{mode} {len(events)} macro events from {len(text)} characters")


def main() -> None:

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
