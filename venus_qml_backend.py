"""QindaTK front end: the backend object the QML scene binds to.

``VenusBackend`` adapts :class:`venus_session.VenusSession` for QML: grouped
read-only maps (``device``, ``editor``, ``macro``, ``lighting``, ``dpi``...),
list models for the button table, macro slots, macro events, DPI rows and
the log, and slots for every user action.  Device errors surface through the
``message(kind, title, text)`` signal, which the QML shows in a
``Tk.MessageDialog``.  Key capture (bindings and macro recording) is an
application-wide event filter, exactly like the widgets window's.
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6 import QtCore, QtGui

import holtek_protocol as hp
import venus_keys
import venus_protocol as vp
import venus_session as vs
from venus_macro_draft import HID_USAGE_TO_NAME, MacroDraft, manual_event_choices
from venus_qml_models import DictListModel

HERE = Path(__file__).resolve().parent
LOG_LIMIT = 2000
BATTERY_INTERVAL_MS = 60_000
DPI_ROWS = 10


def battery_icon(percent: int | None, cable_connected: bool = False) -> QtGui.QIcon:
    """The tray icon: a battery outline filled with the gradient colour."""
    pixmap = QtGui.QPixmap(64, 64)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    outline = QtGui.QColor("#e6e6e6")
    fill = (QtGui.QColor("#777777") if percent is None
            else QtGui.QColor(*vp.battery_gradient_rgb(percent)))
    painter.setPen(QtGui.QPen(outline, 4))
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


class BatteryQueryThread(QtCore.QThread):
    """Run the short status exchange without blocking the QML event loop."""

    completed = QtCore.pyqtSignal(object, str)

    def __init__(self, path: bytes | str, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.path = path

    def run(self) -> None:
        status, error = None, ""
        try:
            status = vs.VenusSession.query_battery(self.path)
        except Exception as exc:
            error = str(exc)
        self.completed.emit(status, error)


class VenusBackend(QtCore.QObject):
    deviceChanged = QtCore.pyqtSignal()
    optionsChanged = QtCore.pyqtSignal()
    stagingChanged = QtCore.pyqtSignal()
    editorChanged = QtCore.pyqtSignal()
    macroChanged = QtCore.pyqtSignal()
    lightingChanged = QtCore.pyqtSignal()
    pollingChanged = QtCore.pyqtSignal()
    dpiChanged = QtCore.pyqtSignal()
    batteryChanged = QtCore.pyqtSignal()
    busyChanged = QtCore.pyqtSignal()
    captureChanged = QtCore.pyqtSignal()
    message = QtCore.pyqtSignal(str, str, str)
    showRequested = QtCore.pyqtSignal()
    trayNotice = QtCore.pyqtSignal(str, str)

    def __init__(self, session: vs.VenusSession, parent: QtCore.QObject | None = None, *,
                 theme_preset: str = "", density: str = "") -> None:
        super().__init__(parent)
        self.session = session
        self.session.log = self._log
        self.session.idle = self._idle
        self.draft = MacroDraft()
        self._theme_preset = theme_preset
        self._density = density
        self._tray_visible = lambda: False
        self._quitting = False
        self._shutdown_done = False
        self._busy = False
        self._busy_text = ""
        self._cancel = False
        self._capture = ""
        self._recording_last_time = 0.0
        self._battery_thread: BatteryQueryThread | None = None
        self._last_battery_status: tuple[int, bool] | None = None
        self._battery = {"text": "Battery: unknown", "percent": -1, "cable": False, "known": False}

        self.buttons_model = DictListModel(["key", "label", "description", "staged", "action"], self)
        self.macro_slots_model = DictListModel(["slot", "name", "label"], self)
        self.macro_events_model = DictListModel(
            ["row", "keyName", "actionText", "isDown", "delay", "kind", "selected"], self)
        self.dpi_model = DictListModel(
            ["slot", "label", "presetIndex", "dpi", "raw", "tweak", "inUse"], self)
        self.log_model = DictListModel(["text"], self)

        self._current_key = ""
        self._editor: dict = {}
        self._pending: dict = {}
        self._staging_state: dict = {}
        self._macro_slot = 1
        self._macro_name = session.macro_names.get(1, "Macro 1")
        self._macro_selection: list[int] = []
        self._macro_current = -1
        self._recording = False
        self._builder_status = ""
        self._builder_error = False
        self._rgb = vs.RgbState()
        self._polling = 1000
        self._dpi_stages = [vs.DpiStage(1000, vp.DPI_PRESETS[1000]["value"],
                                        vp.DPI_PRESETS[1000]["tweak"], True)
                            for _ in range(DPI_ROWS)]
        self._dpi_stage_count = 5
        self._dpi_active_stage = 0

        self.battery_timer = QtCore.QTimer(self)
        self.battery_timer.setInterval(BATTERY_INTERVAL_MS)
        self.battery_timer.timeout.connect(self.refreshBattery)
        self.battery_timer.start()

        for line in session.config_errors:
            self._log(line)
        session.config_errors.clear()
        if session.battery_led_restore:
            self._rgb = vs.RgbState.from_dict(session.battery_led_restore)
        self._refresh_all()
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            app.aboutToQuit.connect(self.shutdown)

    # -- models (constant QObject properties so QML can bind to them) --------
    @QtCore.pyqtProperty(QtCore.QObject, constant=True)
    def buttonsModel(self) -> QtCore.QObject:  # noqa: N802
        return self.buttons_model

    @QtCore.pyqtProperty(QtCore.QObject, constant=True)
    def macroSlotsModel(self) -> QtCore.QObject:  # noqa: N802
        return self.macro_slots_model

    @QtCore.pyqtProperty(QtCore.QObject, constant=True)
    def macroEventsModel(self) -> QtCore.QObject:  # noqa: N802
        return self.macro_events_model

    @QtCore.pyqtProperty(QtCore.QObject, constant=True)
    def dpiModel(self) -> QtCore.QObject:  # noqa: N802
        return self.dpi_model

    @QtCore.pyqtProperty(QtCore.QObject, constant=True)
    def logModel(self) -> QtCore.QObject:  # noqa: N802
        return self.log_model

    # ------------------------------------------------------------------ util
    def set_tray_probe(self, probe) -> None:
        """``probe()`` tells whether a tray icon is currently shown."""
        self._tray_visible = probe

    def _log(self, text: str) -> None:
        for line in str(text).splitlines() or [""]:
            self.log_model.insert_row(self.log_model.count, {"text": line})
        while self.log_model.count > LOG_LIMIT:
            self.log_model.remove_row(0)

    @QtCore.pyqtSlot()
    def clearLog(self) -> None:  # noqa: N802
        self.log_model.clear()

    def _idle(self) -> None:
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.processEvents()

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._busy, self._busy_text = busy, text
        self.busyChanged.emit()
        self._idle()

    def _progress(self, text: str) -> None:
        self._busy_text = text
        self.busyChanged.emit()
        self._idle()

    def _run(self, label: str, operation, *, done: str = "", title: str = "") -> bool:
        """Run a device operation with the busy indicator and error dialog."""
        self._set_busy(True, label)
        try:
            operation()
        except vs.SessionError as exc:
            self.message.emit("error", title or f"{label} failed", str(exc))
            return False
        finally:
            self._set_busy(False)
        if done:
            self.message.emit("info", title or label, done)
        return True

    def _refresh_all(self) -> None:
        self._rebuild_options()
        self._rebuild_device()
        self._rebuild_buttons()
        self._rebuild_macro_slots()
        self._rebuild_macro_events()
        self._rebuild_dpi_rows()
        self._load_editor()
        self.lightingChanged.emit()
        self.pollingChanged.emit()
        self.dpiChanged.emit()
        self.batteryChanged.emit()

    # ---------------------------------------------------------------- device
    def _rebuild_device(self) -> None:
        self.deviceChanged.emit()

    @QtCore.pyqtProperty("QVariantMap", notify=deviceChanged)
    def device(self) -> dict:
        session = self.session
        info = session.device_info
        access_error = info.access_error if info else ""
        connected = session.demo or (session.device_path is not None and not access_error)
        if session.demo:
            status, level = f"Demo: {session.device_name}", "ok"
        elif not vp.HIDAPI_AVAILABLE:
            status, level = "python-hidapi is not installed", "warn"
        elif info is None:
            status, level = "No device found", "muted"
        elif access_error:
            status, level = f"Detected: {session.device_name} — access denied", "warn"
        else:
            status, level = f"Ready: {session.device_name}", "ok"
        return {
            "name": session.device_name, "type": session.device_type,
            "isHoltek": session.is_holtek, "connected": connected,
            "status": status, "statusLevel": level,
            "path": info.display_path if info else "",
            "holtekProfile": session.holtek_profile, "demo": session.demo,
            "accessError": access_error,
        }

    @QtCore.pyqtProperty(str, notify=deviceChanged)
    def windowTitle(self) -> str:  # noqa: N802 - QML-facing
        name = self.session.device_name
        return f"Venus Pro Config — {name}" if name else "Venus Pro Config"

    @QtCore.pyqtProperty(QtCore.QUrl, constant=True)
    def mouseImage(self) -> QtCore.QUrl:  # noqa: N802
        path = HERE / "mouseimg.png"
        return QtCore.QUrl.fromLocalFile(str(path)) if path.exists() else QtCore.QUrl()

    @QtCore.pyqtProperty(str, constant=True)
    def themePreset(self) -> str:  # noqa: N802
        return self._theme_preset

    @QtCore.pyqtProperty(str, constant=True)
    def densityMode(self) -> str:  # noqa: N802
        return self._density

    def _rebuild_options(self) -> None:
        self.optionsChanged.emit()

    @QtCore.pyqtProperty("QVariantMap", notify=optionsChanged)
    def options(self) -> dict:
        session = self.session
        holtek = session.is_holtek
        return {
            "actions": session.actions,
            "specialKeys": vs.SPECIAL_KEY_NAMES,
            "mediaKeys": [{"name": name, "code": code}
                          for name, code in sorted(vp.MEDIA_KEY_CODES.items())],
            "dpiFunctions": [{"name": name, "value": value} for name, value in session.dpi_functions],
            "macroModes": [{"name": name, "value": value} for name, value in vs.MACRO_REPEAT_MODES],
            "rgbModes": [{"name": name, "value": value} for name, value in vs.RGB_MODES],
            "pollingRates": vs.POLLING_RATES,
            "quickPicks": [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in vp.RGB_QUICK_PICKS],
            "manualChoices": [{"label": label, "kind": kind, "code": code}
                              for label, kind, code in manual_event_choices()],
            "buttonChoices": [{"key": key, "label": session.button_label(key)}
                              for key in session.button_keys],
            "modifiersEnabled": not holtek,
            "macrosEnabled": not holtek,
            "advancedEnabled": not holtek,
            "profilesEnabled": not holtek,
            "resetEnabled": not holtek,
            "specialDelayVisible": not holtek,
            "holtekProfiles": [f"Profile {index + 1}" for index in range(5)],
            "batteryGradient": [
                {"label": label, "color": "#%02x%02x%02x" % vp.battery_gradient_rgb(percent)}
                for label, percent in (("full", 100), ("", 75), ("half", 50), ("", 25), ("empty", 0))],
            "batteryGradient": [
                {"color": "#%02x%02x%02x" % vp.battery_gradient_rgb(percent), "label": label}
                for percent, label in ((100, "full"), (75, ""), (50, "half"), (25, ""), (0, "empty"))],
        }

    @QtCore.pyqtSlot(bool)
    def connectDevice(self, silent: bool) -> None:  # noqa: N802
        """Refresh the device list, detect the controller and auto-read."""
        self._set_busy(True, "Connecting...")
        try:
            result = self.session.connect(read=True)
        finally:
            self._set_busy(False)
        self._last_battery_status = None
        self._rebuild_options()
        if result.read is not None:
            self._apply_config(result.read)
        else:
            self._rebuild_buttons()
            self._load_editor()
        self._rebuild_device()
        self.lightingChanged.emit()
        if result.read_error and not silent:
            self.message.emit("error", "Read Error", result.read_error)
        elif result.access_error and not silent:
            self.message.emit("warning", "Access denied", result.access_error)
        self.refreshBattery()

    @QtCore.pyqtSlot()
    def refresh(self) -> None:
        self.connectDevice(False)

    @QtCore.pyqtSlot(str)
    def loadDemo(self, kind: str) -> None:  # noqa: N802
        """Illustrative state for screenshots and tests; never touches a mouse."""
        config = self.session.load_demo(kind or "venus_pro")
        self._rebuild_options()
        self._apply_config(config)
        self._rebuild_device()
        self.selectButton("Button 5" if kind == "holtek" else "Button 1")
        if kind != "holtek":
            self.draft.clear()
            self.draft.generate_text("Hello, Venus!", key_hold_ms=35, delay_min_ms=70,
                                     delay_max_ms=160, extra_word_pause_ms=80, append=False,
                                     rng=__import__("random").Random(7))
            self.draft.add_tap("Mouse: Left Button", "mouse", 0x01, 35, 120)
            self._macro_name = "Chat greeting"
            self._rebuild_macro_events()
            self._set_builder_status("Generated a text macro with randomized inter-key delays.")
        self.lightingChanged.emit()
        self.batteryChanged.emit()

    def _apply_config(self, config: vs.DeviceConfig) -> None:
        if config.polling_rate:
            self._polling = config.polling_rate
        if config.rgb is not None:
            if self.session.battery_led_enabled and self.session.battery_led_restore:
                self._rgb = vs.RgbState.from_dict(self.session.battery_led_restore)
            else:
                self._rgb = config.rgb
        if config.dpi_stage_count:
            self._dpi_stage_count = config.dpi_stage_count
        for index, stage in enumerate(config.dpi_stages[:DPI_ROWS]):
            self._dpi_stages[index] = stage
        self._dpi_active_stage = config.dpi_active_stage
        self._rebuild_buttons()
        self._rebuild_dpi_rows()
        self._load_editor()
        self.lightingChanged.emit()
        self.pollingChanged.emit()
        self.dpiChanged.emit()

    @QtCore.pyqtSlot()
    def readSettings(self) -> None:  # noqa: N802
        holder: dict = {}

        def operation():
            holder["config"] = (self.session.read_settings_holtek()
                                if self.session.is_holtek else self.session.read_settings())

        if self._run("Reading settings", operation, title="Read Error"):
            self._apply_config(holder["config"])
            self._rebuild_device()
            self.message.emit("info", "Read Success",
                              "Configuration successfully read from device.")

    @QtCore.pyqtSlot(int)
    def setHoltekProfile(self, profile: int) -> None:  # noqa: N802
        if profile == self.session.holtek_profile:
            return
        holder: dict = {}

        def operation():
            holder["config"] = self.session.select_holtek_profile(profile)

        self._run("Reading profile", operation, title="Read Error")
        self._rebuild_staging()
        if holder.get("config") is not None:
            self._apply_config(holder["config"])
        else:
            self._rebuild_buttons()
            self._load_editor()
        self._rebuild_device()

    @QtCore.pyqtSlot()
    def reclaim(self) -> None:
        if self.session.reclaim():
            self.connectDevice(False)
        else:
            self.message.emit("info", "Device Reclaim",
                              "No Venus Pro devices found on the USB bus.")

    @QtCore.pyqtSlot()
    def factoryReset(self) -> None:  # noqa: N802
        """Called after the QML confirmation dialog was accepted."""
        self._run("Factory reset", self.session.factory_reset,
                  done="Factory reset command acknowledged.", title="Reset")

    # --------------------------------------------------------------- buttons
    def _rebuild_buttons(self) -> None:
        session = self.session
        staged = session.staging.get_staged_changes()
        rows = []
        for key in session.button_keys:
            entry = staged.get(key) or session.button_assignments.get(key)
            description = (session.describe(entry["action"], entry.get("params", {}))
                           if entry else "Unknown (Read to update)")
            rows.append({"key": key, "label": session.button_label(key),
                         "description": description, "staged": key in staged,
                         "action": entry["action"] if entry else ""})
        self.buttons_model.set_rows(rows)
        if self._current_key not in session.active_button_profiles:
            self._current_key = ""
        self._rebuild_staging()

    def _rebuild_staging(self) -> None:
        staging = self.session.staging
        self._staging_state = {
            "hasChanges": staging.has_changes(),
            "count": len(staging.get_staged_changes()),
            "canUndo": staging.can_undo(), "canRedo": staging.can_redo(),
        }
        self.stagingChanged.emit()

    @QtCore.pyqtProperty("QVariantMap", notify=stagingChanged)
    def staging(self) -> dict:
        return dict(self._staging_state)

    @QtCore.pyqtProperty("QVariantMap", notify=editorChanged)
    def editor(self) -> dict:
        return dict(self._editor)

    def _load_editor(self) -> None:
        key = self._current_key
        session = self.session
        editor = {"key": key, "label": session.button_label(key) if key else "",
                  "description": "Not configured", "action": "Disabled",
                  "unsupported": False, "keyName": "", "specialKey": "",
                  "modCtrl": False, "modShift": False, "modAlt": False, "modWin": False,
                  "macroIndex": 1, "macroMode": vp.MACRO_REPEAT_ONCE, "macroCount": 1,
                  "mediaCode": vp.MEDIA_KEY_CODES["PlayPause"], "dpiFunc": session.dpi_functions[0][1],
                  "delay": 40, "repeat": 3}
        entry = session.effective_binding(key) if key else None
        if entry:
            action, params = entry["action"], entry.get("params", {})
            editor["action"] = action
            editor["description"] = session.describe(action, params)
            editor["unsupported"] = action not in session.actions
            if action == "Keyboard Key":
                name = HID_USAGE_TO_NAME.get(params.get("key", 0), "")
                if name in vs.SPECIAL_KEY_NAMES:
                    editor["specialKey"] = name
                else:
                    editor["keyName"] = name
                mod = params.get("mod", 0)
                editor.update(modCtrl=bool(mod & vp.MODIFIER_CTRL),
                              modShift=bool(mod & vp.MODIFIER_SHIFT),
                              modAlt=bool(mod & vp.MODIFIER_ALT),
                              modWin=bool(mod & vp.MODIFIER_WIN))
            elif action == "Macro":
                mode = params.get("mode", vp.MACRO_REPEAT_ONCE)
                known = {value for _, value in vs.MACRO_REPEAT_MODES}
                editor["macroIndex"] = params.get("index", 1)
                editor["macroMode"] = mode if mode in known else vp.MACRO_REPEAT_COUNT
                editor["macroCount"] = mode if isinstance(mode, int) and 1 <= mode <= 253 else 1
            elif action == "Media Key":
                editor["mediaCode"] = params.get("code", editor["mediaCode"])
            elif action == "DPI Control":
                editor["dpiFunc"] = params.get("func", editor["dpiFunc"])
            elif action in ("Fire Key", "Triple Click"):
                editor["delay"] = params.get("delay", 40)
                editor["repeat"] = params.get("repeat", 3)
        self._editor = editor
        self.editorChanged.emit()

    @QtCore.pyqtSlot(str)
    def selectButton(self, key: str) -> None:  # noqa: N802
        self._current_key = key if key in self.session.active_button_profiles else ""
        self._pending = {}
        self._load_editor()

    @QtCore.pyqtSlot(str, "QVariantMap")
    def stageBinding(self, action: str, values: dict) -> None:  # noqa: N802
        """Stage the editor's current values for the selected button.

        ``values`` holds the editor controls: keyName/specialKey/mod* for a
        keyboard key, macroIndex/macroMode/macroCount, mediaCode, dpiFunc,
        delay/repeat.  Missing keys fall back to the current editor state.
        """
        key = self._current_key
        if not key or action not in self.session.actions:
            return
        # The controls are authoritative while a binding is half-entered (a
        # modifier ticked before its key), so keep what they sent.
        self._pending.update(values or {})
        state = dict(self._editor)
        state.update(self._pending)
        params: dict = {}
        if action == "Keyboard Key":
            key_name = state.get("specialKey") or state.get("keyName") or ""
            if not key_name:
                return
            hid_key = (vp.HID_KEY_USAGE.get(key_name, 0)
                       or vp.HID_KEY_USAGE.get(key_name.upper(), 0))
            modifier = 0
            if not self.session.is_holtek:
                if state.get("modCtrl"):
                    modifier |= vp.MODIFIER_CTRL
                if state.get("modShift"):
                    modifier |= vp.MODIFIER_SHIFT
                if state.get("modAlt"):
                    modifier |= vp.MODIFIER_ALT
                if state.get("modWin"):
                    modifier |= vp.MODIFIER_WIN
            params = {"key": hid_key, "mod": modifier}
        elif action == "Macro":
            mode = int(state.get("macroMode", vp.MACRO_REPEAT_ONCE))
            count = int(state.get("macroCount", 1))
            params = {"index": int(state.get("macroIndex", 1)),
                      "mode": count if mode == vp.MACRO_REPEAT_COUNT else mode}
        elif action == "Media Key":
            params = {"code": int(state.get("mediaCode", 0))}
        elif action == "DPI Control":
            params = {"func": int(state.get("dpiFunc", 1))}
        elif action in ("Fire Key", "Triple Click"):
            params = {"delay": int(state.get("delay", 40)), "repeat": int(state.get("repeat", 3))}
        self.session.stage_binding(key, action, params)
        self._rebuild_buttons()
        self._load_editor()

    @QtCore.pyqtSlot()
    def commitStaged(self) -> None:  # noqa: N802
        if not self.session.staging.has_changes():
            return
        self._set_busy(True, "Applying changes...")
        try:
            result = self.session.commit_staged(self._progress)
        except vs.SessionError as exc:
            result = vs.CommitResult(False, str(exc))
        finally:
            self._set_busy(False)
        self._rebuild_buttons()
        self._load_editor()
        self._rebuild_device()
        if result.ok:
            self.message.emit("info", "Success", "All changes applied successfully.")
        elif result.partial:
            self.message.emit("error", "Partial Write Possible", result.error)
        else:
            self.message.emit("error", "Error", result.error)

    @QtCore.pyqtSlot()
    def discardStaged(self) -> None:  # noqa: N802
        self.session.discard_staged()
        self._rebuild_buttons()
        self._load_editor()

    @QtCore.pyqtSlot()
    def undo(self) -> None:
        if self.session.staging.undo():
            self._log("Undo: Reverted last staged change.")
        else:
            self._log("Undo: Nothing to undo.")
        self._rebuild_buttons()
        self._load_editor()

    @QtCore.pyqtSlot()
    def redo(self) -> None:
        if self.session.staging.redo():
            self._log("Redo: Re-applied staging change.")
        else:
            self._log("Redo: Nothing to redo.")
        self._rebuild_buttons()
        self._load_editor()

    # ----------------------------------------------------------- key capture
    @QtCore.pyqtProperty(str, notify=captureChanged)
    def captureMode(self) -> str:  # noqa: N802
        return self._capture

    @QtCore.pyqtSlot()
    def beginKeyCapture(self) -> None:  # noqa: N802
        if self._capture != "binding":
            self._capture = "binding"
            self.captureChanged.emit()

    @QtCore.pyqtSlot()
    def endKeyCapture(self) -> None:  # noqa: N802
        if self._capture == "binding":
            self._capture = ""
            self.captureChanged.emit()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if not self._capture:
            return False
        kind = event.type()
        if kind == QtCore.QEvent.Type.ShortcutOverride:
            # Accepting the override keeps menu shortcuts (Ctrl+Z, F5...) from
            # firing while a key is being captured; the KeyPress follows.
            event.accept()
            return True
        if kind not in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            return False
        if event.isAutoRepeat():
            return True
        if self._capture == "binding":
            if kind == QtCore.QEvent.Type.KeyPress:
                name = venus_keys.hid_name_for_event(event)
                if name:
                    self.stageBinding("Keyboard Key", {"keyName": name, "specialKey": ""})
                    self.editorChanged.emit()
            return True
        return self._record_key_event(event, kind == QtCore.QEvent.Type.KeyPress)

    # ---------------------------------------------------------------- macros
    def _rebuild_macro_slots(self) -> None:
        names = self.session.macro_names
        self.macro_slots_model.set_rows([
            {"slot": slot, "name": names.get(slot, f"Macro {slot}"),
             "label": f"{slot}: {names.get(slot, f'Macro {slot}')}"}
            for slot in range(1, vs.MACRO_SLOT_COUNT + 1)])
        self.macroChanged.emit()

    def _rebuild_macro_events(self) -> None:
        rows = []
        for index, event in enumerate(self.draft.events):
            rows.append({"row": index, "keyName": event.key_name,
                         "actionText": "Press" if event.is_down else "Release",
                         "isDown": event.is_down, "delay": event.delay_ms,
                         "kind": event.kind, "selected": index in self._macro_selection})
        self.macro_events_model.set_rows(rows)
        self._macro_selection = [row for row in self._macro_selection if row < len(rows)]
        if self._macro_current >= len(rows):
            self._macro_current = len(rows) - 1
        self.macroChanged.emit()

    def _renumber_macro_rows(self) -> None:
        self.macro_events_model.update_all(lambda data: {"row": data["row"]})
        for index in range(self.macro_events_model.count):
            self.macro_events_model.update_row(index, row=index,
                                             selected=index in self._macro_selection)
        self.macroChanged.emit()

    @QtCore.pyqtProperty("QVariantMap", notify=macroChanged)
    def macro(self) -> dict:
        preview = self.draft.preview()
        return {
            "slot": self._macro_slot, "name": self._macro_name,
            "count": len(self.draft), "capacity": self.draft.capacity,
            "free": self.draft.free, "preview": preview.summary,
            "output": preview.output, "totalMs": preview.total_ms,
            "pressed": preview.pressed, "recording": self._recording,
            "builderStatus": self._builder_status, "builderError": self._builder_error,
            "selection": list(self._macro_selection), "currentRow": self._macro_current,
        }

    def _set_builder_status(self, text: str, error: bool = False) -> None:
        self._builder_status, self._builder_error = text, error
        if error:
            self._log(f"Macro editor: {text}")
        self.macroChanged.emit()

    @QtCore.pyqtSlot(int)
    def selectMacroSlot(self, slot: int) -> None:  # noqa: N802
        """Choose the save target; no device I/O."""
        slot = max(1, min(vs.MACRO_SLOT_COUNT, int(slot)))
        self._macro_slot = slot
        self._macro_name = self.session.macro_names.get(slot, f"Macro {slot}")
        self.macroChanged.emit()

    @QtCore.pyqtSlot(str)
    def setMacroName(self, name: str) -> None:  # noqa: N802
        self._macro_name = name[:15]
        self.macroChanged.emit()

    @QtCore.pyqtSlot()
    def loadMacroFromMouse(self) -> None:  # noqa: N802
        holder: dict = {}

        def operation():
            self.stopRecording()
            holder["name"] = self.session.load_macro_slot(self._macro_slot, self.draft)

        if self._run("Loading macro", operation, title="Load Error"):
            self._macro_name = holder["name"]
            self._macro_selection = []
            self._macro_current = -1
            self._rebuild_macro_slots()
            self._rebuild_macro_events()
            self._set_builder_status(f"Loaded slot {self._macro_slot} from the mouse.")

    @QtCore.pyqtSlot()
    def saveMacroToMouse(self) -> None:  # noqa: N802
        slot, name = self._macro_slot, self._macro_name.strip()

        def operation():
            self.stopRecording()
            self.session.save_macro(slot, name, self.draft)

        if self._run("Saving macro", operation, title="Save Error"):
            self._rebuild_macro_slots()
            self._rebuild_macro_events()
            self.message.emit("info", "Success", f"Macro {slot} uploaded successfully!")

    @QtCore.pyqtSlot(str, int, int)
    def bindSlotToButton(self, button_key: str, mode: int, count: int) -> None:  # noqa: N802
        if button_key not in self.session.active_button_profiles:
            return
        self._set_busy(True, "Binding macro...")
        try:
            result = self.session.bind_macro(button_key, self._macro_slot, mode, count)
        except vs.SessionError as exc:
            result = vs.CommitResult(False, str(exc))
        finally:
            self._set_busy(False)
        self._rebuild_buttons()
        self._load_editor()
        if result.ok:
            self.message.emit("info", "Success", "All changes applied successfully.")
        else:
            self.message.emit("error", "Bind failed", result.error)

    # -- event list editing
    @QtCore.pyqtSlot(int, bool, bool)
    def selectEvent(self, row: int, extend: bool, span: bool) -> None:  # noqa: N802
        if not 0 <= row < len(self.draft.events):
            return
        if span and self._macro_current >= 0:
            low, high = sorted((self._macro_current, row))
            selection = set(self._macro_selection) if extend else set()
            selection.update(range(low, high + 1))
        elif extend:
            selection = set(self._macro_selection)
            selection.symmetric_difference_update({row})
        else:
            selection = {row}
        self._macro_selection = sorted(selection)
        self._macro_current = row
        for index in range(self.macro_events_model.count):
            self.macro_events_model.update_row(index, selected=index in selection)
        self.macroChanged.emit()

    def _target_rows(self) -> list[int]:
        rows = list(self._macro_selection)
        if not rows and self._macro_current >= 0:
            rows = [self._macro_current]
        return rows

    @QtCore.pyqtSlot(int, int)
    def setEventDelay(self, row: int, delay: int) -> None:  # noqa: N802
        if self.draft.set_delay(row, delay):
            self.macro_events_model.update_row(row, delay=self.draft.events[row].delay_ms)
            self.macroChanged.emit()

    @QtCore.pyqtSlot(int)
    def applyDelayToSelected(self, delay: int) -> None:  # noqa: N802
        for row in self._target_rows():
            self.setEventDelay(row, delay)

    @QtCore.pyqtSlot(int)
    def deleteEvent(self, row: int) -> None:  # noqa: N802
        if self.draft.delete([row]):
            self._macro_selection = [r for r in self._macro_selection if r != row]
            self._rebuild_macro_events()

    @QtCore.pyqtSlot()
    def deleteSelectedEvents(self) -> None:  # noqa: N802
        rows = self._target_rows()
        if rows:
            self.draft.delete(rows)
            self._macro_selection = []
            self._macro_current = -1
            self._rebuild_macro_events()

    @QtCore.pyqtSlot()
    def duplicateEvent(self) -> None:  # noqa: N802
        if self._macro_current < 0:
            return
        new_row = self.draft.duplicate(self._macro_current)
        if new_row is None:
            self._set_builder_status("Cannot duplicate: the hardware slot is full.", True)
            return
        self._macro_selection = [new_row]
        self._macro_current = new_row
        self._rebuild_macro_events()

    @QtCore.pyqtSlot(int)
    def moveEvent(self, delta: int) -> None:  # noqa: N802
        if self._macro_current < 0:
            return
        target = self.draft.move(self._macro_current, delta)
        if target is None:
            return
        self._macro_selection = [target]
        self._macro_current = target
        self._rebuild_macro_events()

    @QtCore.pyqtSlot()
    def clearEvents(self) -> None:  # noqa: N802
        self.stopRecording()
        self.draft.clear()
        self._macro_selection = []
        self._macro_current = -1
        self._rebuild_macro_events()

    # -- builders
    @QtCore.pyqtSlot(str, int, int, int, bool, result=str)
    def textStatus(self, text: str, delay_min: int, delay_max: int,  # noqa: N802
                   word_pause: int, append: bool) -> str:
        message, error = self.draft.text_status(text, delay_min, delay_max, word_pause, append)
        self._builder_status, self._builder_error = message, bool(error)
        self.macroChanged.emit()
        return error

    @QtCore.pyqtSlot(str, int, int, int, int, bool)
    def generateText(self, text: str, hold: int, delay_min: int, delay_max: int,  # noqa: N802
                     word_pause: int, append: bool) -> None:
        if not text:
            return
        try:
            count = self.draft.generate_text(
                text, key_hold_ms=hold, delay_min_ms=delay_min, delay_max_ms=delay_max,
                extra_word_pause_ms=word_pause, append=append)
        except ValueError as exc:
            self._set_builder_status(str(exc), True)
            return
        self._macro_selection = []
        self._macro_current = -1
        self._rebuild_macro_events()
        self._log(f"{'Appended' if append else 'Generated'} {count} macro events "
                  f"from {len(text)} characters")
        self._set_builder_status(f"{'Appended' if append else 'Generated'} {count} events.")

    @QtCore.pyqtSlot(int, str, int, int)
    def addManualEvent(self, choice: int, action: str, hold: int, delay: int) -> None:  # noqa: N802
        choices = manual_event_choices()
        if not 0 <= choice < len(choices):
            return
        label, kind, code = choices[choice]
        needed = 2 if action == "tap" else 1
        if not self.draft.can_add(needed):
            self._set_builder_status(
                f"This action needs {needed} event(s), but only {self.draft.free} "
                "remain in the slot.", True)
            return
        if action == "tap":
            self.draft.add_tap(label, kind, code, hold, delay)
        else:
            self.draft.add_single(label, kind, code, action == "press", delay)
        self._rebuild_macro_events()

    # -- recording
    @QtCore.pyqtSlot()
    def toggleRecording(self) -> None:  # noqa: N802
        if self._recording:
            self.stopRecording()
            return
        if not self.draft.can_add(1):
            self._set_builder_status("The hardware slot is already full.", True)
            return
        self._recording = True
        self._recording_last_time = 0.0
        self._capture = "recording"
        self.captureChanged.emit()
        self.macroChanged.emit()
        self._log("Recording started - press keys to record macro events")

    @QtCore.pyqtSlot()
    def stopRecording(self) -> None:  # noqa: N802
        if not self._recording:
            return
        self._recording = False
        if self._capture == "recording":
            self._capture = ""
            self.captureChanged.emit()
        self.draft.normalize_final_delay()
        self._rebuild_macro_events()
        self._log("Recording stopped")

    def _record_key_event(self, event: QtGui.QKeyEvent, is_down: bool) -> bool:
        modifier = venus_keys.macro_modifier_for_event(event)
        if modifier is not None:
            modifier_name, keycode = modifier
            key_name, kind = f"Modifier: {modifier_name}", "modifier"
        else:
            key_name = venus_keys.qt_key_to_name(event.key(), event.text().upper())
            if not key_name or key_name not in vp.HID_KEY_USAGE:
                self._set_builder_status(
                    f"Recording skipped unsupported key 0x{event.key():X}.", True)
                return True
            keycode, kind = vp.HID_KEY_USAGE[key_name], "keyboard"
        now = time.time() * 1000
        if self._recording_last_time > 0 and self.draft.events:
            previous = min(0xFFFF, max(vp.MACRO_MIN_DELAY_MS,
                                       int(now - self._recording_last_time)))
            self.draft.set_delay(len(self.draft.events) - 1, previous)
            self.macro_events_model.update_row(len(self.draft.events) - 1, delay=previous)
        if not self.draft.add_single(key_name, kind, keycode, is_down, vp.MACRO_MIN_DELAY_MS):
            self.stopRecording()
            self._set_builder_status("Recording stopped: the 69-event slot is full.", True)
            return True
        index = len(self.draft.events) - 1
        self.macro_events_model.insert_row(index, {
            "row": index, "keyName": key_name, "actionText": "Press" if is_down else "Release",
            "isDown": is_down, "delay": vp.MACRO_MIN_DELAY_MS, "kind": kind, "selected": False})
        self._recording_last_time = now
        self.macroChanged.emit()
        return True

    # -------------------------------------------------------------- lighting
    @QtCore.pyqtProperty("QVariantMap", notify=lightingChanged)
    def lighting(self) -> dict:
        holtek = self.session.is_holtek
        rgb = self._rgb
        animated = rgb.mode in (vp.RGB_MODE_BREATHING, vp.RGB_MODE_NEON)
        mode_name = next((name for name, value in vs.RGB_MODES if value == rgb.mode), "Steady")
        return {
            "r": rgb.r, "g": rgb.g, "b": rgb.b, "hex": f"#{rgb.r:02x}{rgb.g:02x}{rgb.b:02x}",
            "mode": rgb.mode, "modeName": mode_name,
            "brightness": rgb.brightness, "brightnessMax": 0xFF if holtek else 100,
            "brightnessSuffix": " raw" if holtek else "%",
            "brightnessLabel": "Brightness (raw)" if holtek else "Brightness",
            "speed": rgb.speed,
            "speedMin": 0 if holtek else vp.RGB_EFFECT_SPEED_MIN,
            "speedMax": 0xFF if holtek else vp.RGB_EFFECT_SPEED_MAX,
            "showSpeed": holtek or animated,
            "speedLabel": "Effect speed (raw)" if holtek else "Effect speed (1 fast – 5 slow)",
            "batteryLedEnabled": self.session.battery_led_enabled,
            "batteryLedSupported": self.session.battery_led_supported,
        }

    @QtCore.pyqtSlot(QtGui.QColor)
    def setRgbColor(self, color: QtGui.QColor) -> None:  # noqa: N802
        self._rgb = vs.RgbState(color.red(), color.green(), color.blue(),
                                self._rgb.mode, self._rgb.brightness, self._rgb.speed)
        self.lightingChanged.emit()

    @QtCore.pyqtSlot(int)
    def setRgbMode(self, mode: int) -> None:  # noqa: N802
        self._rgb.mode = int(mode)
        self.lightingChanged.emit()

    @QtCore.pyqtSlot(int)
    def setRgbBrightness(self, value: int) -> None:  # noqa: N802
        self._rgb.brightness = int(value)
        self.lightingChanged.emit()

    @QtCore.pyqtSlot(int)
    def setRgbSpeed(self, value: int) -> None:  # noqa: N802
        self._rgb.speed = int(value)
        self.lightingChanged.emit()

    @QtCore.pyqtSlot()
    def applyLighting(self) -> None:  # noqa: N802
        state = vs.RgbState(**self._rgb.to_dict())
        mode_name = self.lighting["modeName"]

        def operation():
            self.session.apply_rgb(state, mode_name, self._progress)

        self._run("Applying lighting", operation, title="RGB failed")
        self._rebuild_device()
        self.lightingChanged.emit()

    @QtCore.pyqtSlot(bool)
    def setBatteryLedEnabled(self, enabled: bool) -> None:  # noqa: N802
        try:
            restored = self.session.set_battery_led_enabled(enabled, self._rgb)
        except vs.SessionError as exc:
            self.message.emit("error", "Battery LED", str(exc))
            restored = None
        if restored is not None:
            self._rgb = restored
        self.lightingChanged.emit()
        if enabled and self.session.battery_led_enabled:
            self.refreshBattery()

    # --------------------------------------------------------------- polling
    @QtCore.pyqtProperty(int, notify=pollingChanged)
    def polling(self) -> int:
        return self._polling

    @QtCore.pyqtSlot(int)
    def setPollingRate(self, rate: int) -> None:  # noqa: N802
        if rate in vs.POLLING_RATES:
            self._polling = int(rate)
            self.pollingChanged.emit()

    @QtCore.pyqtSlot()
    def applyPolling(self) -> None:  # noqa: N802
        rate = self._polling
        self._run(f"Polling {rate} Hz", lambda: self.session.apply_polling(rate),
                  title="Polling rate failed")

    # ------------------------------------------------------------------- DPI
    def _dpi_presets(self) -> list[int]:
        return sorted(hp.DPI_PRESETS if self.session.is_holtek else vp.DPI_PRESETS)

    def _rebuild_dpi_rows(self) -> None:
        presets = self._dpi_presets()
        rows = []
        for index, stage in enumerate(self._dpi_stages):
            preset_index = presets.index(stage.dpi) + 1 if stage.preset and stage.dpi in presets else 0
            rows.append({"slot": index, "label": f"Slot {index + 1}", "presetIndex": preset_index,
                         "dpi": stage.dpi, "raw": stage.raw, "tweak": stage.tweak,
                         "inUse": index < self._dpi_stage_count})
        self.dpi_model.set_rows(rows)
        self.dpiChanged.emit()

    @QtCore.pyqtProperty("QVariantMap", notify=dpiChanged)
    def dpi(self) -> dict:
        holtek = self.session.is_holtek
        return {
            "stageCount": self._dpi_stage_count, "stageMax": 10 if holtek else 5,
            "activeStage": self._dpi_active_stage + 1, "showActive": holtek,
            "showRaw": not holtek,
            "header": ("Per-profile DPI stages (Holtek stores 1–10 stages at 200-DPI increments)."
                       if holtek else
                       "DPI slots (presets are captured values; custom conversion is "
                       "approximate and sensor-dependent)."),
            "min": 200 if holtek else 100, "max": 28000 if holtek else 20000,
            "step": 200 if holtek else 100,
            "presets": self._dpi_presets(),
            "presetLabels": ["Custom"] + [f"{dpi} DPI" for dpi in self._dpi_presets()],
        }

    @QtCore.pyqtSlot(int)
    def setDpiStageCount(self, count: int) -> None:  # noqa: N802
        maximum = 10 if self.session.is_holtek else 5
        self._dpi_stage_count = max(1, min(maximum, int(count)))
        self._dpi_active_stage = min(self._dpi_active_stage, self._dpi_stage_count - 1)
        for index in range(DPI_ROWS):
            self.dpi_model.update_row(index, inUse=index < self._dpi_stage_count)
        self.dpiChanged.emit()

    @QtCore.pyqtSlot(int)
    def setDpiActiveStage(self, stage: int) -> None:  # noqa: N802
        self._dpi_active_stage = max(0, min(self._dpi_stage_count - 1, int(stage) - 1))
        self.dpiChanged.emit()

    def _store_stage(self, row: int, stage: vs.DpiStage) -> None:
        self._dpi_stages[row] = stage
        presets = self._dpi_presets()
        preset_index = presets.index(stage.dpi) + 1 if stage.preset and stage.dpi in presets else 0
        self.dpi_model.update_row(row, presetIndex=preset_index, dpi=stage.dpi,
                                 raw=stage.raw, tweak=stage.tweak)
        self.dpiChanged.emit()

    @QtCore.pyqtSlot(int, int)
    def setDpiPreset(self, row: int, preset_index: int) -> None:  # noqa: N802
        presets = self._dpi_presets()
        if not 0 <= row < DPI_ROWS or not 1 <= preset_index <= len(presets):
            return
        dpi = presets[preset_index - 1]
        raw = hp.dpi_to_raw(dpi) if self.session.is_holtek else vp.DPI_PRESETS[dpi]["value"]
        self._store_stage(row, vs.DpiStage(dpi, raw, vp.dpi_value_to_tweak(raw), True))

    @QtCore.pyqtSlot(int, int)
    def setDpiValue(self, row: int, dpi: int) -> None:  # noqa: N802
        if not 0 <= row < DPI_ROWS:
            return
        if self.session.is_holtek:
            dpi = max(200, min(28000, int(round(dpi / 200)) * 200))
            raw = hp.dpi_to_raw(dpi)
            preset = dpi in hp.DPI_PRESETS
        else:
            dpi = max(100, min(20000, int(dpi)))
            raw = vp.dpi_to_value(dpi)
            preset = dpi in vp.DPI_PRESETS and vp.DPI_PRESETS[dpi]["value"] == raw
        self._store_stage(row, vs.DpiStage(dpi, raw, vp.dpi_value_to_tweak(raw), preset))

    @QtCore.pyqtSlot(int, int)
    def setDpiRaw(self, row: int, raw: int) -> None:  # noqa: N802
        if not 0 <= row < DPI_ROWS or self.session.is_holtek:
            return
        raw = max(0, min(255, int(raw)))
        self._store_stage(row, vs.DpiStage(vp.value_to_dpi(raw), raw,
                                           vp.dpi_value_to_tweak(raw), False))

    @QtCore.pyqtSlot()
    def applyDpi(self) -> None:  # noqa: N802
        stages = [vs.DpiStage(**vars(stage)) for stage in self._dpi_stages]
        count, active = self._dpi_stage_count, self._dpi_active_stage

        def operation():
            self.session.apply_dpi(stages, count, active, self._progress)

        self._run("Applying DPI", operation, title="DPI failed")
        self._rebuild_device()

    # -------------------------------------------------------------- advanced
    @QtCore.pyqtSlot(str, str)
    def sendBuiltReport(self, command_hex: str, payload_hex: str) -> None:  # noqa: N802
        self._run("Advanced built", lambda: self.session.send_built_report(command_hex, payload_hex),
                  title="Send failed")

    @QtCore.pyqtSlot(str)
    def sendRawReport(self, raw_hex: str) -> None:  # noqa: N802
        self._run("Advanced raw", lambda: self.session.send_raw_report(raw_hex),
                  title="Send failed")

    # -------------------------------------------------------------- profiles
    @QtCore.pyqtSlot()
    def cancelBusy(self) -> None:  # noqa: N802
        self._cancel = True

    def _page_progress(self, verb: str):
        self._cancel = False

        def progress(page: int) -> bool:
            if page % 8 == 0:
                self._progress(f"{verb} page {page + 1}/256...")
            return not self._cancel
        return progress

    @QtCore.pyqtSlot(QtCore.QUrl)
    def exportProfile(self, url: QtCore.QUrl) -> None:  # noqa: N802
        path = Path(url.toLocalFile() if url.isLocalFile() else url.toString())
        if not path.name:
            return
        holder: dict = {}

        def operation():
            holder["done"] = self.session.export_profile(path, self._page_progress("Exporting"))

        if self._run("Exporting profile", operation, title="Export Failed"):
            if holder.get("done"):
                self.message.emit("info", "Export Successful", f"Profile saved to {path}")
            else:
                self.message.emit("info", "Export Canceled", f"A partial dump remains at {path}")

    @QtCore.pyqtSlot(QtCore.QUrl)
    def importProfile(self, url: QtCore.QUrl) -> None:  # noqa: N802
        """Called after the QML confirmation dialog was accepted."""
        path = Path(url.toLocalFile() if url.isLocalFile() else url.toString())
        if not path.name:
            return
        holder: dict = {}

        def operation():
            holder["done"] = self.session.import_profile(path, self._page_progress("Importing"))

        if self._run("Importing profile", operation, title="Import Failed"):
            if holder.get("done"):
                self.message.emit("info", "Import Successful",
                                  "Profile successfully written to device.")
                self.readSettings()
            else:
                self.message.emit("warning", "Import Canceled",
                                  "Import stopped after a partial write. Re-import a complete "
                                  "profile before relying on the device configuration.")

    # --------------------------------------------------------------- battery
    @QtCore.pyqtProperty("QVariantMap", notify=batteryChanged)
    def battery(self) -> dict:
        return dict(self._battery)

    @QtCore.pyqtSlot()
    def refreshBattery(self) -> None:  # noqa: N802
        session = self.session
        if session.demo or not session.battery_led_supported or session.device_path is None:
            self._battery = {"text": "Battery: unavailable", "percent": -1,
                             "cable": False, "known": False}
            self.batteryChanged.emit()
            return
        if self._battery_thread and self._battery_thread.isRunning():
            return
        thread = BatteryQueryThread(session.device_path, self)
        thread.completed.connect(self._battery_query_finished)
        thread.finished.connect(lambda finished=thread: self._battery_thread_finished(finished))
        self._battery_thread = thread
        thread.start()

    def _battery_query_finished(self, status: object, error: str) -> None:
        if isinstance(status, vp.BatteryStatus):
            connection = "USB cable" if status.cable_connected else "wireless"
            current = (status.level, status.cable_connected)
            if current != self._last_battery_status:
                self._log(f"Battery: {status.percent}% ({connection})")
                self._last_battery_status = current
            suffix = "; battery LED on" if self.session.battery_led_enabled else ""
            self._battery = {"text": f"Battery {status.percent}% ({connection}{suffix})",
                             "percent": status.percent, "cable": status.cable_connected,
                             "known": True}
            self.batteryChanged.emit()
            if self.session.battery_led_enabled and not self._quitting:
                self.session.apply_battery_led_status(status)
        else:
            self._battery = {"text": "Battery: disconnected or inaccessible", "percent": -1,
                             "cable": False, "known": False}
            self.batteryChanged.emit()
            if error:
                self._log(f"Battery refresh: {error}")

    def _battery_thread_finished(self, thread: BatteryQueryThread) -> None:
        if self._battery_thread is thread:
            self._battery_thread = None
        thread.deleteLater()

    # ------------------------------------------------------------- lifecycle
    @QtCore.pyqtProperty(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @QtCore.pyqtProperty(str, notify=busyChanged)
    def busyText(self) -> str:  # noqa: N802
        return self._busy_text

    @QtCore.pyqtSlot(result=bool)
    def closeToTray(self) -> bool:  # noqa: N802
        """True when the window should hide instead of closing."""
        if self._quitting or not self._tray_visible():
            return False
        self.trayNotice.emit("Venus Pro Config",
                             "Battery monitoring is still running. Use the tray menu to quit.")
        return True

    @QtCore.pyqtSlot()
    def quit(self) -> None:
        self._quitting = True
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.quit()

    @QtCore.pyqtSlot()
    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._quitting = True
        self.battery_timer.stop()
        if self._battery_thread and self._battery_thread.isRunning():
            self._battery_thread.wait(2000)
        if self.session.battery_led_enabled:
            self.session.restore_battery_led(quiet=True)
