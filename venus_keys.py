"""Qt key-event to HID-name mapping shared by both front ends.

The Qt Widgets interface (``venus_gui.KeyCaptureEdit``) and the QindaTK
interface (``venus_qml_backend``) both need to turn a ``QKeyEvent`` into the
key names used by ``venus_protocol.HID_KEY_USAGE`` and
``venus_protocol.MACRO_MODIFIER_CODES``.  Keeping the tables here means a
numpad or right-side-modifier fix lands in both interfaces at once.

Only :mod:`PyQt6.QtCore` and :mod:`PyQt6.QtGui` are imported; nothing here
needs QtWidgets or QtQuick.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui

import venus_protocol as vp

Key = QtCore.Qt.Key

# Qt.Key -> HID_KEY_USAGE name (regular keys).
QT_TO_HID: dict[QtCore.Qt.Key, str] = {
    **{getattr(Key, f"Key_{chr(c)}"): chr(c)
       for c in range(ord("A"), ord("Z") + 1)},
    Key.Key_1: "1", Key.Key_2: "2", Key.Key_3: "3", Key.Key_4: "4",
    Key.Key_5: "5", Key.Key_6: "6", Key.Key_7: "7", Key.Key_8: "8",
    Key.Key_9: "9", Key.Key_0: "0",
    Key.Key_F1: "F1", Key.Key_F2: "F2", Key.Key_F3: "F3", Key.Key_F4: "F4",
    Key.Key_F5: "F5", Key.Key_F6: "F6", Key.Key_F7: "F7", Key.Key_F8: "F8",
    Key.Key_F9: "F9", Key.Key_F10: "F10", Key.Key_F11: "F11",
    Key.Key_F12: "F12", Key.Key_F13: "F13", Key.Key_F14: "F14",
    Key.Key_F15: "F15", Key.Key_F16: "F16", Key.Key_F17: "F17",
    Key.Key_F18: "F18", Key.Key_F19: "F19", Key.Key_F20: "F20",
    Key.Key_F21: "F21", Key.Key_F22: "F22", Key.Key_F23: "F23",
    Key.Key_F24: "F24",
    Key.Key_Return: "Enter", Key.Key_Escape: "Escape",
    Key.Key_Backspace: "Backspace", Key.Key_Tab: "Tab",
    Key.Key_Space: "Space",
    Key.Key_Minus: "-", Key.Key_Equal: "=",
    Key.Key_BracketLeft: "[", Key.Key_BracketRight: "]",
    Key.Key_Backslash: "\\", Key.Key_Semicolon: ";",
    Key.Key_Apostrophe: "'", Key.Key_QuoteLeft: "`",
    Key.Key_Comma: ",", Key.Key_Period: ".",
    Key.Key_Slash: "/", Key.Key_CapsLock: "CapsLock",
    Key.Key_Insert: "Insert", Key.Key_Home: "Home",
    Key.Key_PageUp: "PageUp", Key.Key_Delete: "Delete",
    Key.Key_End: "End", Key.Key_PageDown: "PageDown",
    Key.Key_Right: "Right", Key.Key_Left: "Left",
    Key.Key_Down: "Down", Key.Key_Up: "Up",
    Key.Key_Print: "PrintScreen",
    Key.Key_ScrollLock: "ScrollLock",
    Key.Key_Pause: "Pause", Key.Key_Menu: "Menu",
    Key.Key_NumLock: "NumLock",
    # Modifier keys (standalone binding)
    Key.Key_Shift: "Left Shift", Key.Key_Control: "Left Ctrl",
    Key.Key_Alt: "Left Alt", Key.Key_Meta: "Left GUI",
}

# When KeypadModifier is active, these keys become "Keypad X".
KEYPAD_MAP: dict[QtCore.Qt.Key, str] = {
    Key.Key_0: "Keypad 0", Key.Key_1: "Keypad 1", Key.Key_2: "Keypad 2",
    Key.Key_3: "Keypad 3", Key.Key_4: "Keypad 4", Key.Key_5: "Keypad 5",
    Key.Key_6: "Keypad 6", Key.Key_7: "Keypad 7", Key.Key_8: "Keypad 8",
    Key.Key_9: "Keypad 9",
    Key.Key_Slash: "Keypad /", Key.Key_Asterisk: "Keypad *",
    Key.Key_Minus: "Keypad -", Key.Key_Plus: "Keypad +",
    Key.Key_Enter: "Keypad Enter", Key.Key_Period: "Keypad .",
}

# Qt reports a generic Key_Shift/Control/Alt/Meta value for both sides.
# X11/XKB usually exposes evdev + 8 here, while native Wayland backends may
# expose the evdev code itself.  Only consult these maps for an actual Qt
# modifier key, so overlapping ordinary-key scan codes cannot be mistaken
# for modifiers.
RIGHT_MOD_SCANCODES: dict[int, str] = {
    62: "Right Shift",   # X11 keycode for Right Shift
    105: "Right Ctrl",   # X11 keycode for Right Ctrl
    108: "Right Alt",    # X11 keycode for Right Alt
    134: "Right GUI",    # X11 keycode for Right Super
    54: "Right Shift",   # Linux evdev KEY_RIGHTSHIFT
    97: "Right Ctrl",    # Linux evdev KEY_RIGHTCTRL
    100: "Right Alt",    # Linux evdev KEY_RIGHTALT
    126: "Right GUI",    # Linux evdev KEY_RIGHTMETA
}
RIGHT_MOD_NATIVE_KEYS: dict[int, str] = {
    0xFFE2: "Right Shift",  # XK_Shift_R
    0xFFE4: "Right Ctrl",   # XK_Control_R
    0xFFEA: "Right Alt",    # XK_Alt_R
    0xFFEC: "Right GUI",    # XK_Super_R
}

_MODIFIER_DEFAULTS: dict[QtCore.Qt.Key, str] = {
    Key.Key_Shift: "Left Shift",
    Key.Key_Control: "Left Ctrl",
    Key.Key_Alt: "Left Alt",
    Key.Key_Meta: "Left GUI",
}
_MODIFIER_FAMILIES: dict[QtCore.Qt.Key, str] = {
    Key.Key_Shift: "Shift",
    Key.Key_Control: "Ctrl",
    Key.Key_Alt: "Alt",
    Key.Key_Meta: "GUI",
}
_ALTGR_KEY = getattr(Key, "Key_AltGr", None)


def modifier_name_for_event(event: QtGui.QKeyEvent) -> str | None:
    """Return a side-aware modifier name for a Qt key event, else ``None``."""
    key = event.key()
    defaults = dict(_MODIFIER_DEFAULTS)
    if _ALTGR_KEY is not None:
        defaults[_ALTGR_KEY] = "Right Alt"
    if key not in defaults:
        return None

    native_name = RIGHT_MOD_NATIVE_KEYS.get(event.nativeVirtualKey())
    scan_name = RIGHT_MOD_SCANCODES.get(event.nativeScanCode())
    if _ALTGR_KEY is not None and key == _ALTGR_KEY:
        expected_family = "Alt"
    else:
        expected_family = _MODIFIER_FAMILIES[key]
    for candidate in (native_name, scan_name):
        if candidate and expected_family in candidate:
            return candidate
    return defaults[key]


def hid_name_for_event(event: QtGui.QKeyEvent) -> str:
    """Return the HID_KEY_USAGE name a key press binds to, or ``""``."""
    modifier_name = modifier_name_for_event(event)
    if modifier_name:
        return modifier_name
    key = event.key()
    keypad = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.KeypadModifier)
    if keypad and key in KEYPAD_MAP:
        return KEYPAD_MAP[key]
    return QT_TO_HID.get(key, "")


def qt_key_to_name(qt_key: int, key_text: str) -> str | None:
    """Convert a Qt key code (and its text) to a HID key name for recording."""
    if len(key_text) == 1 and key_text.isalpha():
        return key_text.upper()
    if len(key_text) == 1 and key_text.isdigit():
        return key_text
    return QT_TO_HID.get(qt_key)


def macro_modifier_for_event(event: QtGui.QKeyEvent) -> tuple[str, int] | None:
    """Map a Qt modifier event to the vendor's stored-macro (name, code)."""
    modifier_name = modifier_name_for_event(event)
    if modifier_name is None:
        return None
    # The vendor converter collapses left/right GUI keys to one byte.
    if modifier_name in ("Left GUI", "Right GUI"):
        modifier_name = "GUI"
    keycode = vp.MACRO_MODIFIER_CODES.get(modifier_name)
    if keycode is None:
        return None
    return modifier_name, keycode
