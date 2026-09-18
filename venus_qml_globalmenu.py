"""Global-menu hosting monitor for the QindaTK interface.

Qt exports the window's ``Qt.labs.platform`` menu bar as a
``com.canonical.dbusmenu`` endpoint (``/MenuBar/<n>`` on this process's bus
connection) and announces it per window; the QindaQt shell shows it in the
panel's global-menu applet.  Publication alone does not prove the panel
renders it (ADR-0077), so the in-window menu bar is hidden only while the
registrar acknowledges hosting of our exact service and path through
``IsMenuHosted`` / ``MenuHostedChanged``.  A registrar that vanishes, or a
layout without a global-menu applet, brings the local bar back.
"""

from __future__ import annotations

import re

from PyQt6 import QtCore

try:
    from PyQt6 import QtDBus
except ImportError:  # pragma: no cover - pyqt6 without dbus
    QtDBus = None

REGISTRAR = "com.canonical.AppMenu.Registrar"
REGISTRAR_PATH = "/com/canonical/AppMenu/Registrar"
MENUBAR_ROOT = "/MenuBar"


class GlobalMenuHostMonitor(QtCore.QObject):
    hostedChanged = QtCore.pyqtSignal()

    def __init__(self, enabled: bool = True, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._hosted = False
        self._paths: list[str] = []
        self._attempts = 0
        self._bus = None
        self._enabled = bool(enabled and QtDBus is not None)
        self._poll = QtCore.QTimer(self)
        self._poll.setInterval(750)
        self._poll.timeout.connect(self._query)
        if not self._enabled:
            return
        self._bus = QtDBus.QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            self._enabled = False
            return
        self._bus.connect(REGISTRAR, REGISTRAR_PATH, REGISTRAR, "MenuHostedChanged",
                          self._hosted_changed)
        self._watcher = QtDBus.QDBusServiceWatcher(
            REGISTRAR, self._bus, QtDBus.QDBusServiceWatcher.WatchModeFlag.WatchForOwnerChange,
            self)
        self._watcher.serviceOwnerChanged.connect(self._registrar_owner_changed)
        self.start()

    @QtCore.pyqtProperty(bool, notify=hostedChanged)
    def hosted(self) -> bool:
        return self._hosted

    @QtCore.pyqtProperty(bool, constant=True)
    def enabled(self) -> bool:
        return self._enabled

    @QtCore.pyqtProperty(str, notify=hostedChanged)
    def endpoint(self) -> str:
        """``service path`` of the hosted endpoint, for diagnostics."""
        return f"{self._service()} {self._paths[0]}" if self._paths else ""

    @QtCore.pyqtSlot()
    def start(self) -> None:
        """(Re)discover our exported menu bars and ask whether they are hosted."""
        if not self._enabled:
            return
        self._attempts = 0
        self._poll.start()

    def _service(self) -> str:
        return self._bus.baseService() if self._bus is not None else ""

    def _set_hosted(self, hosted: bool) -> None:
        if hosted != self._hosted:
            self._hosted = hosted
            self.hostedChanged.emit()

    def _exported_paths(self) -> list[str]:
        call = QtDBus.QDBusMessage.createMethodCall(
            self._service(), MENUBAR_ROOT, "org.freedesktop.DBus.Introspectable", "Introspect")
        reply = self._bus.call(call, QtDBus.QDBus.CallMode.Block, 500)
        if reply.type() != QtDBus.QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
            return []
        return [f"{MENUBAR_ROOT}/{name}" for name in
                re.findall(r'<node name="([^"]+)"', str(reply.arguments()[0]))]

    def _is_hosted(self, path: str) -> bool:
        call = QtDBus.QDBusMessage.createMethodCall(
            REGISTRAR, REGISTRAR_PATH, REGISTRAR, "IsMenuHosted")
        call.setArguments([self._service(), QtDBus.QDBusObjectPath(path)])
        reply = self._bus.call(call, QtDBus.QDBus.CallMode.Block, 500)
        return (reply.type() == QtDBus.QDBusMessage.MessageType.ReplyMessage
                and bool(reply.arguments() and reply.arguments()[0]))

    def _query(self) -> None:
        self._attempts += 1
        self._paths = self._exported_paths()
        hosted = any(self._is_hosted(path) for path in self._paths)
        self._set_hosted(hosted)
        # The shell acknowledges shortly after the window is shown and
        # focused; keep asking for a while, then rely on the signal.
        if hosted or self._attempts >= 12:
            self._poll.stop()

    @QtCore.pyqtSlot(str, QtDBus.QDBusObjectPath if QtDBus else object, bool)
    def _hosted_changed(self, service: str, path, hosted: bool) -> None:
        if service != self._service():
            return
        path_text = path.path() if hasattr(path, "path") else str(path)
        if hosted:
            if path_text not in self._paths:
                self._paths.append(path_text)
            self._set_hosted(True)
        elif path_text in self._paths:
            self._set_hosted(any(self._is_hosted(p) for p in self._paths))

    def _registrar_owner_changed(self, name: str, old_owner: str, new_owner: str) -> None:
        if not new_owner:
            self._set_hosted(False)
            self._poll.stop()
        else:
            self.start()
