#!/usr/bin/env python3
"""Venus Pro Config, QindaTK interface.

Launches the QML scene under ``qml/`` on top of the shared
:class:`venus_session.VenusSession`.  Besides the interactive window it offers
the headless options the QindaTK toolkit's own tooling uses, so a layout
claim can be checked on a machine without a display or a mouse::

    python3 venus_qml.py                       # the application
    python3 venus_qml.py --widgets             # start the Qt Widgets interface instead
    python3 venus_qml.py --demo --grab shot.png --size 1280x800
    python3 venus_qml.py --demo holtek --page 3 --dump
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QML_DIR = HERE / "qml"
APP_ID = "com.github.es00bac.venusprolinux"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Venus Pro Config (QindaTK interface)")
    parser.add_argument("--widgets", action="store_true",
                        help="run the Qt Widgets interface (venus_gui.py) instead")
    parser.add_argument("--demo", nargs="?", const="venus_pro", choices=("venus_pro", "holtek"),
                        help="illustrative configuration, no device access")
    parser.add_argument("--grab", metavar="PNG", help="render headlessly to PNG and exit")
    parser.add_argument("--dump", action="store_true",
                        help="print the item tree (headless) and exit")
    parser.add_argument("--size", default="1280x820", help="window size for --grab/--dump")
    parser.add_argument("--page", type=int, default=0, help="tab to show for --grab/--dump")
    parser.add_argument("--select", metavar="KEY", help="select a button (e.g. 'Button 3') for --grab")
    parser.add_argument("--theme", default="", help="QindaTK preset (sloom-dark, sloom-light, graphite)")
    parser.add_argument("--density", default="", help="compact, comfortable or touch")
    parser.add_argument("--no-tray", action="store_true", help="never create a tray icon")
    parser.add_argument("--exit-after", type=float, metavar="SECONDS",
                        help="quit after this many seconds and report the global-menu state (diagnostics)")
    parser.add_argument("--menu-in-window", action="store_true",
                        help="keep the menu bar inside the window even when the panel hosts it")
    parser.add_argument("--import-path", action="append", default=[],
                        help="extra QML import path (a QindaTK build tree)")
    return parser.parse_args(argv)


def dump_tree(item, depth: int = 0, out=sys.stdout) -> None:
    """``Type#objectName x,y WxH "text"`` per item, like qtk-preview --dump."""
    name = item.metaObject().className().split("_QMLTYPE")[0]
    object_name = item.objectName()
    label = f"{name}#{object_name}" if object_name else name
    text = item.property("text")
    text_part = f' "{text}"' if isinstance(text, str) and text else ""
    hidden = "" if item.isVisible() else " hidden"
    out.write(f"{'  ' * depth}{label}  {item.x():.0f},{item.y():.0f} "
              f"{item.width():.0f}x{item.height():.0f}{text_part}{hidden}\n")
    for child in item.childItems():
        dump_tree(child, depth + 1, out)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.widgets:
        sys.argv = [str(HERE / "venus_gui.py")]
        import venus_gui
        venus_gui.main()
        return 0

    headless = bool(args.grab or args.dump)
    if headless:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    from PyQt6 import QtCore, QtGui, QtQml, QtQuick  # noqa: F401 - QQuickWindow downcast

    try:
        from PyQt6 import QtWidgets
    except ImportError:  # pragma: no cover - pyqt6 built without widgets
        QtWidgets = None
    try:
        from PyQt6 import QtDBus
    except ImportError:  # pragma: no cover - pyqt6 built without dbus
        QtDBus = None

    import venus_session as vs
    from venus_qml_backend import VenusBackend, battery_icon
    from venus_qml_globalmenu import GlobalMenuHostMonitor

    app_class = QtWidgets.QApplication if QtWidgets is not None else QtGui.QGuiApplication
    app = app_class(sys.argv[:1])
    app.setApplicationName("venusprolinux")
    app.setApplicationDisplayName("Venus Pro Config")
    app.setOrganizationDomain("es00bac.github.com")
    app.setDesktopFileName(APP_ID)
    icon_path = HERE / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))

    session = vs.VenusSession()
    backend = VenusBackend(session, theme_preset=args.theme, density=args.density)
    if args.demo:
        backend.loadDemo(args.demo)
    else:
        backend.connectDevice(True)

    tray = None
    if (QtWidgets is not None and not args.no_tray and not headless
            and QtWidgets.QSystemTrayIcon.isSystemTrayAvailable()):
        tray = TrayController(backend, app, QtWidgets, battery_icon)
        backend.set_tray_probe(tray.is_visible)
        app.setQuitOnLastWindowClosed(False)
    else:
        backend._log("Tray: This desktop session does not expose a system tray."
                     if not headless and not args.no_tray else "Tray: disabled")

    engine = QtQml.QQmlApplicationEngine()
    for path in args.import_path:
        engine.addImportPath(path)
    engine.rootContext().setContextProperty("venusBackend", backend)
    # The QindaQt panel hosts the menu; the QML hides its own bar only once
    # the shell acknowledges that (nothing to acknowledge when headless).
    global_menu = GlobalMenuHostMonitor(enabled=not headless)
    engine.rootContext().setContextProperty("globalMenuHost", global_menu)
    engine.load(QtCore.QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    roots = engine.rootObjects()
    if not roots:
        print("venus_qml: failed to load qml/Main.qml", file=sys.stderr)
        return 1
    window = roots[0]
    if args.menu_in_window:
        window.setProperty("menuInWindow", True)
    backend.showRequested.connect(lambda: (window.show(), window.raise_(), window.requestActivate()))

    if headless:
        width, _, height = args.size.partition("x")
        window.setWidth(int(width or 1280))
        window.setHeight(int(height or 820))
        window.setProperty("currentPage", int(args.page))
        if args.select:
            backend.selectButton(args.select)
        for _ in range(6):
            app.processEvents()
        if args.dump:
            dump_tree(window.contentItem())
        if args.grab:
            image = window.grabWindow()
            if not image.save(args.grab, "PNG"):
                print(f"venus_qml: could not save {args.grab}", file=sys.stderr)
                return 1
            print(args.grab)
        backend.shutdown()
        del engine
        return 0

    if args.exit_after:
        print(f"global menu: service={QtDBus.QDBusConnection.sessionBus().baseService()}"
              if QtDBus is not None else "global menu: no QtDBus", flush=True)

        def report():
            print(f"global menu: enabled={global_menu.enabled} hosted={global_menu.hosted} "
                  f"endpoint='{global_menu.endpoint}' menuBarVisible="
                  f"{window.findChild(QtCore.QObject, 'menuBar').property('visible')}")
            app.quit()
        QtCore.QTimer.singleShot(int(args.exit_after * 1000), report)
    code = app.exec()
    del engine
    return code


class TrayController:
    """One desktop-neutral status icon with the battery gauge and quick actions."""

    def __init__(self, backend, app, QtWidgets, icon_factory) -> None:  # noqa: N803
        from PyQt6 import QtGui as _QtGui

        self.backend = backend
        self.icon_factory = icon_factory
        self.icon = QtWidgets.QSystemTrayIcon(icon_factory(None), app)
        self.icon.setToolTip("Venus mouse — battery unavailable")
        menu = QtWidgets.QMenu()
        menu.addAction("Show Venus Pro Config").triggered.connect(backend.showRequested.emit)
        menu.addAction("Refresh Battery").triggered.connect(backend.refreshBattery)
        self.led_action = _QtGui.QAction("Battery-color mouse LED (low brightness)", menu)
        self.led_action.setCheckable(True)
        self.led_action.triggered.connect(backend.setBatteryLedEnabled)
        menu.addAction(self.led_action)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(backend.quit)
        self.menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)
        backend.batteryChanged.connect(self._sync_battery)
        backend.lightingChanged.connect(self._sync_led)
        backend.trayNotice.connect(self._notice)
        self._notice_shown = False
        self._sync_led()
        self.icon.show()

    def is_visible(self) -> bool:
        return self.icon.isVisible()

    def _activated(self, reason) -> None:
        from PyQt6 import QtWidgets

        if reason in (QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
                      QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick):
            self.backend.showRequested.emit()

    def _sync_battery(self) -> None:
        battery = self.backend.battery
        if battery["known"]:
            self.icon.setIcon(self.icon_factory(battery["percent"], battery["cable"]))
            self.icon.setToolTip(f"Venus Pro — {battery['text']}")
        else:
            self.icon.setIcon(self.icon_factory(None))
            self.icon.setToolTip(f"Venus Pro — {battery['text']}")

    def _sync_led(self) -> None:
        lighting = self.backend.lighting
        self.led_action.blockSignals(True)
        self.led_action.setChecked(lighting["batteryLedEnabled"])
        self.led_action.setEnabled(lighting["batteryLedSupported"])
        self.led_action.blockSignals(False)

    def _notice(self, title: str, text: str) -> None:
        from PyQt6 import QtWidgets

        if self._notice_shown:
            return
        self._notice_shown = True
        self.icon.showMessage(title, text, QtWidgets.QSystemTrayIcon.MessageIcon.Information, 3500)


if __name__ == "__main__":
    raise SystemExit(main())
