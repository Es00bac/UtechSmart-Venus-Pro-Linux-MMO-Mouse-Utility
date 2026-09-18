// SPDX-License-Identifier: MIT
import QtQuick
import Qt.labs.platform as Platform

// The application menu as a platform menu bar. Qt exports it as a
// com.canonical.dbusmenu endpoint and announces it per window over the KDE
// appmenu Wayland protocol (the `qindaqt` platform theme creates the D-Bus
// menu bar while the desktop's registrar is on the bus), which is how the
// QindaQt panel's global menu shows it. Every item routes through the same
// window functions as the in-window Tk.MenuBar, so both are one menu.
Platform.MenuBar {
    id: mirror
    required property var host          // the Tk.AppWindow (Main.qml)
    window: mirror.host

    Platform.Menu {
        title: "&File"
        Platform.MenuItem { text: "Read Settings"; shortcut: "Ctrl+R"; enabled: mirror.host.device.connected; onTriggered: mirror.host.readSettings() }
        Platform.MenuSeparator {}
        Platform.MenuItem { text: "Export Profile…"; enabled: mirror.host.canUseProfiles; onTriggered: mirror.host.exportProfile() }
        Platform.MenuItem { text: "Import Profile…"; enabled: mirror.host.canUseProfiles; onTriggered: mirror.host.importProfile() }
        Platform.MenuSeparator {}
        Platform.MenuItem { text: "Quit"; shortcut: "Ctrl+Q"; role: Platform.MenuItem.QuitRole; onTriggered: venusBackend.quit() }
    }
    Platform.Menu {
        title: "&Edit"
        Platform.MenuItem { text: "Undo staged change"; shortcut: "Ctrl+Z"; enabled: mirror.host.staging.canUndo; onTriggered: venusBackend.undo() }
        Platform.MenuItem { text: "Redo staged change"; shortcut: "Ctrl+Shift+Z"; enabled: mirror.host.staging.canRedo; onTriggered: venusBackend.redo() }
        Platform.MenuSeparator {}
        Platform.MenuItem { text: "Apply All Changes"; shortcut: "Ctrl+Return"; enabled: mirror.host.staging.hasChanges; onTriggered: venusBackend.commitStaged() }
        Platform.MenuItem { text: "Discard Staged Changes"; enabled: mirror.host.staging.hasChanges; onTriggered: venusBackend.discardStaged() }
    }
    Platform.Menu {
        title: "&Device"
        Platform.MenuItem { text: "Reconnect / Refresh"; shortcut: "F5"; onTriggered: venusBackend.refresh() }
        Platform.MenuItem { text: "Reclaim Device"; onTriggered: venusBackend.reclaim() }
        Platform.MenuSeparator {}
        Platform.Menu {
            id: profileMenu
            title: "Holtek Profile"
            enabled: mirror.host.device.isHoltek
            Instantiator {
                model: mirror.host.options.holtekProfiles
                delegate: Platform.MenuItem {
                    required property int index
                    required property string modelData
                    text: modelData
                    checkable: true
                    checked: mirror.host.device.holtekProfile === index
                    onTriggered: venusBackend.setHoltekProfile(index)
                }
                onObjectAdded: function(index, object) { profileMenu.insertItem(index, object) }
                onObjectRemoved: function(index, object) { profileMenu.removeItem(object) }
            }
        }
        Platform.MenuSeparator {}
        Platform.MenuItem { text: "Factory Reset…"; enabled: mirror.host.canReset; onTriggered: mirror.host.factoryReset() }
    }
    Platform.Menu {
        title: "&View"
        Platform.Menu {
            title: "Theme"
            Platform.MenuItem { text: "Sloom dark"; checkable: true; checked: mirror.host.themePreset === "sloom-dark"; onTriggered: mirror.host.applyTheme("sloom-dark") }
            Platform.MenuItem { text: "Sloom light"; checkable: true; checked: mirror.host.themePreset === "sloom-light"; onTriggered: mirror.host.applyTheme("sloom-light") }
            Platform.MenuItem { text: "Graphite"; checkable: true; checked: mirror.host.themePreset === "graphite"; onTriggered: mirror.host.applyTheme("graphite") }
            Platform.MenuItem { text: "QindaQt desktop"; checkable: true; checked: mirror.host.themePreset === "qindaqt"; enabled: mirror.host.desktopThemeReady; onTriggered: mirror.host.applyDesktopTheme() }
        }
        Platform.Menu {
            title: "Density"
            Platform.MenuItem { text: "Compact"; checkable: true; checked: mirror.host.densityName === "compact"; onTriggered: mirror.host.applyDensity("compact") }
            Platform.MenuItem { text: "Comfortable"; checkable: true; checked: mirror.host.densityName === "comfortable"; onTriggered: mirror.host.applyDensity("comfortable") }
            Platform.MenuItem { text: "Touch"; checkable: true; checked: mirror.host.densityName === "touch"; onTriggered: mirror.host.applyDensity("touch") }
        }
        Platform.MenuSeparator {}
        Platform.MenuItem { text: "Menu In Window"; checkable: true; checked: mirror.host.menuInWindow; onTriggered: mirror.host.menuInWindow = !mirror.host.menuInWindow }
        Platform.MenuItem { text: "Show Toolbar"; checkable: true; checked: mirror.host.toolBarsVisible; onTriggered: mirror.host.toolBarsVisible = !mirror.host.toolBarsVisible }
        Platform.MenuItem { text: "Show Status Bar"; checkable: true; checked: mirror.host.statusBarVisible; onTriggered: mirror.host.statusBarVisible = !mirror.host.statusBarVisible }
        Platform.MenuItem { text: "Show Log"; checkable: true; checked: mirror.host.logVisible; onTriggered: mirror.host.logVisible = !mirror.host.logVisible }
    }
    Platform.Menu {
        title: "&Help"
        Platform.MenuItem { text: "Protocol notes"; onTriggered: mirror.host.openHelp("PROTOCOL.md") }
        Platform.MenuItem { text: "Macro editor guide"; onTriggered: mirror.host.openHelp("docs/MACRO_EDITOR.md") }
        Platform.MenuSeparator {}
        Platform.MenuItem { text: "About Venus Pro Config"; role: Platform.MenuItem.AboutRole; onTriggered: mirror.host.showAbout() }
    }
}
