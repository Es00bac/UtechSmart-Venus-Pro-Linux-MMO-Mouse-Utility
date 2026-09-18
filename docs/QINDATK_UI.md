# The QindaTK interface

Venus Pro Config ships two windows over one protocol layer:

| Interface | Entry point | Toolkit | Selected by |
| --- | --- | --- | --- |
| Qt Widgets (upstream) | `venus_gui.py` | PyQt6 QtWidgets | `venusprolinux --widgets`, or when the QindaTK files are absent |
| QindaTK | `venus_qml.py` + `qml/` | PyQt6 QtQuick + the [QindaTK](https://github.com/Es00bac/QindaQt) QML module | `venusprolinux` (default when installed), `venusprolinux --qindatk` |

Both send the same reports: the QindaTK window is a thin adapter over the
shared, Qt-free session layer, and the Widgets window keeps its own code but
uses the same protocol builders and (since this change) the same key tables.

## Modules

```
venus_protocol.py, holtek_protocol.py     wire format (unchanged)
device_driver.py, staging_manager.py,
transaction_controller.py                  device factory, staging, transaction (unchanged)
venus_keys.py          Qt key event -> HID name / macro modifier (shared by both windows)
venus_macro_draft.py   the macro being edited: capacity, preview, text builder, slot image parsing
venus_session.py       VenusSession: discovery, read/parse, commit, macros, lighting, DPI,
                       polling, reset, raw reports, export/import, battery LED, settings
venus_qml_models.py    DictListModel (QAbstractListModel over dicts, in-place edits)
venus_qml_backend.py   VenusBackend: the QObject the QML binds to (maps, models, slots, key capture)
venus_qml.py           entry point: argument parsing, tray icon, headless --grab/--dump
qml/Main.qml           Tk.AppWindow: menu bar, tool bar, tab strip, side panel, status bar, dialogs
qml/*Page.qml          Buttons, Macros, Lighting, DPI, Polling, Advanced
qml/SidePanel.qml      mouse picture and the log
qml/MacroEventRow.qml  one macro event row
qml/DesktopThemeBridge.qml  QindaTK.QindaQt bridge (loaded only where the QindaQt desktop is present)
```

## Running

```
python3 venus_qml.py                       # on a desktop, tray icon when available
python3 venus_qml.py --theme sloom-light --density comfortable
python3 venus_qml.py --demo --grab shot.png --size 1280x820 --page 1   # headless render
python3 venus_qml.py --demo holtek --dump                             # item tree, like qtk-preview
```

`--demo` loads an illustrative configuration and refuses every hardware
operation, which is how the tests and screenshots run without a mouse.
On the QindaQt desktop the window adopts the desktop theme through
`QindaTK.QindaQt`; elsewhere it uses the `sloom-dark` preset (View ▸ Theme
switches presets and density at run time).

## Behaviour parity with the Widgets window

- Bindings are staged as you edit (action, key capture, modifiers, macro
  slot/repeat, media, DPI function, repeat click) and written by *Apply All
  Changes*; Undo/Redo (Ctrl+Z / Ctrl+Shift+Z) walk the staging history.
- Key capture uses an application event filter, exactly like
  `KeyCaptureEdit`: numpad keys and right-side modifiers are distinguished,
  and menu shortcuts are suppressed while capturing or recording.
- Macro recording, the text builder (fixed or random timing, word pause,
  replace/append), manual events (tap / press / release, mouse buttons,
  hardware modifiers), reorder/duplicate/delete, per-row delays, the 69-event
  capacity bar, the output preview with the unreleased-input warning, slot
  load/save and slot-to-button binding.
- Lighting: 27 quick picks, hex field and colour dialog, Off/Steady/
  Breathing/Neon, brightness, effect speed (Areson 1–5, Holtek raw), and the
  battery-colour LED controller with tray integration and restore on quit.
- DPI: Areson 1–5 stages with raw value and derived check byte; Holtek 1–10
  stages at 200-DPI steps with the current stage and preserved colour indices.
- Polling 125–1000 Hz, Areson raw/built reports, factory reset with
  confirmation, profile export/import with progress and cancel.
- Holtek: profile selector, Areson-only tabs shown disabled with a notice.

## Tests

```
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_macro_draft tests.test_session tests.test_qml_ui
```

`test_session` parses a real flash dump from `dumps/` and asserts the packets
the session sends; `test_qml_ui` instantiates `qml/Main.qml` headlessly,
renders every page, and drives staging, key capture, recording and DPI
editing through the backend.
