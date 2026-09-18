"""Headless checks for the QindaTK interface (qml/ on top of venus_qml_backend).

Runs offscreen with the software renderer; no mouse is needed because the
backend is put into demo mode.  Skips cleanly where PyQt6's QtQuick or the
QindaTK QML module is not installed.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

try:
    from PyQt6 import QtCore, QtGui, QtQml, QtQuick  # noqa: F401
    try:  # a QApplication serves the widgets suites too when they share a process
        from PyQt6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover - pyqt6 without widgets
        QApplication = QtGui.QGuiApplication

    import venus_protocol as vp
    import venus_session as vs
    from venus_qml_backend import VenusBackend
    from venus_qml_globalmenu import GlobalMenuHostMonitor
except ImportError:  # pragma: no cover - minimal test hosts
    QtCore = None


def _qindatk_available() -> bool:
    if QtCore is None:
        return False
    # A QQmlEngine needs an application; the import path list comes from Qt.
    app = QApplication.instance() or QApplication([])  # noqa: F841 - keeps Qt alive
    engine = QtQml.QQmlEngine()
    paths = list(engine.importPathList())
    del engine
    for path in paths:
        if (Path(path) / "QindaTK" / "qmldir").exists():
            return True
    return False


@unittest.skipIf(QtCore is None, "PyQt6 QtQuick is not installed")
@unittest.skipUnless(_qindatk_available(), "the QindaTK QML module is not installed")
class QindaTkInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.session = vs.VenusSession(config_dir=Path(self.temp.name))
        self.backend = VenusBackend(self.session)
        self.backend.loadDemo("venus_pro")
        self.engine = QtQml.QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty("venusBackend", self.backend)
        self.menu_host = GlobalMenuHostMonitor(enabled=False)
        self.engine.rootContext().setContextProperty("globalMenuHost", self.menu_host)
        self.engine.load(QtCore.QUrl.fromLocalFile(str(REPO / "qml" / "Main.qml")))
        self.assertTrue(self.engine.rootObjects(), "qml/Main.qml failed to load")
        self.window = self.engine.rootObjects()[0]
        self.window.setWidth(1280)
        self.window.setHeight(820)
        self.spin()

    def tearDown(self):
        self.backend.shutdown()
        self.app.removeEventFilter(self.backend)
        del self.engine
        self.spin()
        self.temp.cleanup()

    def spin(self, times: int = 4):
        for _ in range(times):
            self.app.processEvents()

    def find(self, name: str):
        item = self.window.findChild(QtCore.QObject, name)
        self.assertIsNotNone(item, name)
        return item

    @staticmethod
    def items(root):
        """Every visual descendant (Repeater delegates are not QObject children)."""
        for child in root.childItems():
            yield child
            yield from QindaTkInterfaceTests.items(child)

    def test_window_renders_every_page(self):
        self.assertEqual(self.window.title(), "Venus Pro Config — Venus Pro (Wireless)")
        tabs = self.find("pageTabs")
        self.assertEqual(tabs.property("count"), 6)
        for page in range(6):
            self.window.setProperty("currentPage", page)
            self.spin()
            image = self.window.grabWindow()
            self.assertFalse(image.isNull())
        self.assertEqual(self.find("deviceStatus").property("text"), "Demo: Venus Pro (Wireless)")

    def test_button_rows_follow_the_model_and_staging(self):
        rows = [item for item in self.items(self.find("buttonList"))
                if item.metaObject().className().startswith("ListRow")]
        self.assertEqual(len(rows), 16)
        self.assertEqual(rows[0].property("text"), "Side Button 1")
        self.assertEqual(rows[0].property("height"), 22)
        self.assertEqual(rows[1].property("y"), rows[0].property("y") + 22)

        self.backend.selectButton("Button 3")
        self.backend.stageBinding("Right Click", {})
        self.spin()
        self.assertTrue(self.backend.staging["hasChanges"])
        self.assertTrue(self.find("applyAll").property("text").startswith("Apply 1 Change"))
        self.assertEqual(self.find("bindingPreview").property("text"), "Right Click")
        self.backend.undo()
        self.spin()
        self.assertFalse(self.backend.staging["hasChanges"])
        self.assertEqual(self.find("bindingPreview").property("text"), "Left Click")

    def test_key_capture_stages_a_keyboard_binding(self):
        self.backend.selectButton("Button 8")
        self.backend.stageBinding("Keyboard Key", {"keyName": "A"})
        self.backend.beginKeyCapture()
        press = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_F7,
                                QtCore.Qt.KeyboardModifier.NoModifier)
        self.assertTrue(self.app.sendEvent(self.window, press))
        self.backend.endKeyCapture()
        binding = self.session.staging.get_effective_state("Button 8")
        self.assertEqual(binding, {"action": "Keyboard Key",
                                   "params": {"key": vp.HID_KEY_USAGE["F7"], "mod": 0}})
        self.assertEqual(self.backend.editor["keyName"], "F7")
        self.assertEqual(self.backend.captureMode, "")

    def test_macro_editor_rows_and_recording(self):
        self.window.setProperty("currentPage", 1)
        self.spin()
        self.assertEqual(self.backend.macro["name"], "Chat greeting")
        table = self.find("eventTable")
        fields = [item for item in self.items(table) if item.objectName() == "delayField"]
        self.assertEqual(len(fields), self.backend.macro["count"])

        self.backend.clearEvents()
        self.backend.toggleRecording()
        self.assertTrue(self.backend.macro["recording"])
        for kind in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            event = QtGui.QKeyEvent(kind, QtCore.Qt.Key.Key_C, QtCore.Qt.KeyboardModifier.NoModifier, "c")
            self.app.sendEvent(self.window, event)
        self.backend.stopRecording()
        events = self.backend.draft.to_macro_events()
        self.assertEqual([(e.keycode, e.is_down) for e in events],
                         [(vp.HID_KEY_USAGE["C"], True), (vp.HID_KEY_USAGE["C"], False)])
        self.assertEqual(events[-1].delay_ms, vp.MACRO_MIN_DELAY_MS)
        self.assertIn('Output: "c"', self.backend.macro["preview"])

    def test_dpi_rows_edit_in_place(self):
        self.window.setProperty("currentPage", 3)
        self.spin()
        self.backend.setDpiValue(1, 3000)
        row = self.backend.dpiModel.get(1)
        self.assertEqual(row["dpi"], 3000)
        self.assertEqual(row["raw"], vp.dpi_to_value(3000))
        self.assertEqual(row["presetIndex"], 0)
        self.backend.setDpiStageCount(3)
        self.assertFalse(self.backend.dpiModel.get(4)["inUse"])

    def test_device_errors_reach_the_message_dialog(self):
        dialog = self.find("messageDialog")
        self.backend.applyLighting()   # demo mode refuses hardware access
        self.spin()
        self.assertTrue(dialog.property("visible"))
        self.assertIn("Demo mode", dialog.property("text"))

    def test_local_menu_bar_follows_global_menu_hosting(self):
        bar = self.find("menuBar")
        self.assertTrue(bar.property("visible"))
        self.menu_host._set_hosted(True)
        self.spin()
        self.assertFalse(bar.property("visible"))
        self.window.setProperty("menuInWindow", True)
        self.spin()
        self.assertTrue(bar.property("visible"))

    def test_holtek_demo_hides_areson_only_controls(self):
        self.backend.loadDemo("holtek")
        self.spin()
        self.assertTrue(self.backend.device["isHoltek"])
        self.assertFalse(self.backend.options["macrosEnabled"])
        self.assertTrue(self.find("holtekProfile").property("visible"))
        self.assertEqual(self.backend.dpi["stageMax"], 10)
        self.assertNotIn("Macro", self.backend.options["actions"])


if __name__ == "__main__":
    unittest.main()
