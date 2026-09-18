// SPDX-License-Identifier: MIT
import QtQuick
import QtQuick.Dialogs as Dialogs
import QtQuick.Templates as T
import QindaTK as Tk

// Venus Pro Config, QindaTK interface. The Python side (venus_qml.py)
// exposes `venusBackend`; everything visual lives here and in the pages.
Tk.AppWindow {
    id: window
    width: 1280
    height: 820
    minimumWidth: 900
    minimumHeight: 600
    title: venusBackend.windowTitle

    property int currentPage: 0
    property url pendingImport
    // The in-window menu bar is one of two hosts for the same menu; the
    // other is GlobalMenuMirror (the panel). It stays visible until the
    // QindaQt shell acknowledges that it hosts our menu (ADR-0077), or
    // whenever the user insists on it.
    property bool menuInWindow: false
    property bool logVisible: true
    readonly property bool menuHosted: globalMenuHost.hosted
    readonly property string themePreset: Tk.Theme.preset
    readonly property string densityName: Tk.Density.modeName
    readonly property bool desktopThemeReady: desktopTheme.status === Loader.Ready
    readonly property bool canUseProfiles: device.connected && options.profilesEnabled
    readonly property bool canReset: device.connected && options.resetEnabled

    function readSettings() { if (window.device.connected) venusBackend.readSettings() }
    function exportProfile() { if (window.canUseProfiles) exportDialog.open() }
    function importProfile() { if (window.canUseProfiles) importDialog.open() }
    function factoryReset() { if (window.canReset) resetDialog.open() }
    function applyTheme(preset) { desktopTheme.active = false; Tk.Theme.applyPreset(preset) }
    function applyDesktopTheme() { desktopTheme.active = false; desktopTheme.active = true }
    function applyDensity(mode) { Tk.Density.modeName = mode }
    function openHelp(page) { Qt.openUrlExternally("https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility/blob/main/" + page) }
    function showAbout() { aboutDialog.open() }
    readonly property var device: venusBackend.device
    readonly property var options: venusBackend.options
    readonly property var staging: venusBackend.staging
    readonly property var pages: [
        { "text": "Buttons", "iconName": "mouse-pointer-2" },
        { "text": "Macros", "iconName": "keyboard" },
        { "text": "Lighting", "iconName": "palette" },
        { "text": "DPI", "iconName": "gauge" },
        { "text": "Polling", "iconName": "activity" },
        { "text": "Advanced", "iconName": "terminal" }
    ]

    Component.onCompleted: {
        if (venusBackend.themePreset.length > 0) Tk.Theme.applyPreset(venusBackend.themePreset)
        if (venusBackend.densityMode.length > 0) Tk.Density.modeName = venusBackend.densityMode
    }
    onClosing: function(close) {
        if (venusBackend.closeToTray()) { close.accepted = false; window.hide() }
    }

    Connections {
        target: venusBackend
        function onMessage(kind, title, text) {
            messageDialog.variant = kind === "error" ? "danger" : kind
            messageDialog.title = title
            messageDialog.text = text
            messageDialog.open()
        }
    }

    // ---- keyboard shortcuts (menu items only display them) ----
    Shortcut { sequences: [StandardKey.Undo]; onActivated: venusBackend.undo() }
    Shortcut { sequences: [StandardKey.Redo]; onActivated: venusBackend.redo() }
    Shortcut { sequence: "Ctrl+R"; onActivated: window.readSettings() }
    Shortcut { sequence: "F5"; onActivated: venusBackend.refresh() }
    Shortcut { sequence: "Ctrl+Return"; onActivated: if (window.staging.hasChanges) venusBackend.commitStaged() }
    Shortcut { sequences: [StandardKey.Quit]; onActivated: venusBackend.quit() }

    menuBar: Tk.MenuBar {
        objectName: "menuBar"
        visible: window.menuInWindow || !window.menuHosted
        Tk.Menu {
            title: "&File"
            Tk.MenuItem { text: "Read Settings"; shortcut: "Ctrl+R"; iconName: "download"; enabled: window.device.connected; onTriggered: window.readSettings() }
            Tk.MenuSeparator {}
            Tk.MenuItem { text: "Export Profile…"; iconName: "save"; enabled: window.canUseProfiles; onTriggered: window.exportProfile() }
            Tk.MenuItem { text: "Import Profile…"; iconName: "folder-open"; enabled: window.canUseProfiles; onTriggered: window.importProfile() }
            Tk.MenuSeparator {}
            Tk.MenuItem { text: "Quit"; shortcut: "Ctrl+Q"; onTriggered: venusBackend.quit() }
        }
        Tk.Menu {
            title: "&Edit"
            Tk.MenuItem { text: "Undo staged change"; shortcut: "Ctrl+Z"; iconName: "undo-2"; enabled: window.staging.canUndo; onTriggered: venusBackend.undo() }
            Tk.MenuItem { text: "Redo staged change"; shortcut: "Ctrl+Shift+Z"; iconName: "redo-2"; enabled: window.staging.canRedo; onTriggered: venusBackend.redo() }
            Tk.MenuSeparator {}
            Tk.MenuItem { text: "Apply All Changes"; shortcut: "Ctrl+Return"; iconName: "check"; enabled: window.staging.hasChanges; onTriggered: venusBackend.commitStaged() }
            Tk.MenuItem { text: "Discard Staged Changes"; iconName: "rotate-ccw"; enabled: window.staging.hasChanges; onTriggered: venusBackend.discardStaged() }
        }
        Tk.Menu {
            id: deviceMenu
            title: "&Device"
            Tk.MenuItem { text: "Reconnect / Refresh"; shortcut: "F5"; iconName: "refresh-cw"; onTriggered: venusBackend.refresh() }
            Tk.MenuItem { text: "Reclaim Device"; iconName: "zap"; onTriggered: venusBackend.reclaim() }
            Tk.MenuSeparator {}
            Tk.Menu {
                title: "Holtek Profile"
                enabled: window.device.isHoltek
                Repeater {
                    model: window.options.holtekProfiles
                    Tk.MenuItem {
                        required property int index
                        required property string modelData
                        text: modelData
                        checkable: true; radio: true
                        checked: window.device.holtekProfile === index
                        onTriggered: venusBackend.setHoltekProfile(index)
                    }
                }
            }
            Tk.MenuSeparator {}
            Tk.MenuItem { text: "Factory Reset…"; iconName: "triangle-alert"; danger: true; enabled: window.canReset; onTriggered: window.factoryReset() }
        }
        Tk.Menu {
            title: "&View"
            Tk.Menu {
                title: "Theme"
                Tk.MenuItem { text: "Sloom dark"; checkable: true; radio: true; checked: window.themePreset === "sloom-dark"; onTriggered: window.applyTheme("sloom-dark") }
                Tk.MenuItem { text: "Sloom light"; checkable: true; radio: true; checked: window.themePreset === "sloom-light"; onTriggered: window.applyTheme("sloom-light") }
                Tk.MenuItem { text: "Graphite"; checkable: true; radio: true; checked: window.themePreset === "graphite"; onTriggered: window.applyTheme("graphite") }
                Tk.MenuItem { text: "QindaQt desktop"; checkable: true; radio: true; checked: window.themePreset === "qindaqt"; enabled: window.desktopThemeReady; onTriggered: window.applyDesktopTheme() }
            }
            Tk.Menu {
                title: "Density"
                Tk.MenuItem { text: "Compact"; checkable: true; radio: true; checked: window.densityName === "compact"; onTriggered: window.applyDensity("compact") }
                Tk.MenuItem { text: "Comfortable"; checkable: true; radio: true; checked: window.densityName === "comfortable"; onTriggered: window.applyDensity("comfortable") }
                Tk.MenuItem { text: "Touch"; checkable: true; radio: true; checked: window.densityName === "touch"; onTriggered: window.applyDensity("touch") }
            }
            Tk.MenuSeparator {}
            Tk.MenuItem { text: "Menu In Window"; checkable: true; checked: window.menuInWindow; onTriggered: window.menuInWindow = !window.menuInWindow }
            Tk.MenuItem { text: "Show Toolbar"; checkable: true; checked: window.toolBarsVisible; onTriggered: window.toolBarsVisible = !window.toolBarsVisible }
            Tk.MenuItem { text: "Show Status Bar"; checkable: true; checked: window.statusBarVisible; onTriggered: window.statusBarVisible = !window.statusBarVisible }
            Tk.MenuItem { text: "Show Log"; checkable: true; checked: window.logVisible; onTriggered: window.logVisible = !window.logVisible }
        }
        Tk.Menu {
            title: "&Help"
            Tk.MenuItem { text: "Protocol notes"; iconName: "book-open"; onTriggered: window.openHelp("PROTOCOL.md") }
            Tk.MenuItem { text: "Macro editor guide"; iconName: "book-open"; onTriggered: window.openHelp("docs/MACRO_EDITOR.md") }
            Tk.MenuSeparator {}
            Tk.MenuItem { text: "About Venus Pro Config"; iconName: "info"; onTriggered: window.showAbout() }
        }
    }

    toolBars: [
        Tk.ToolBar {
            objectName: "deviceBar"
            wrap: true
            Tk.Icon {
                name: "mouse-pointer-2"
                size: Tk.Theme.size.iconLg
                color: window.device.statusLevel === "ok" ? Tk.Theme.color.success
                     : window.device.statusLevel === "warn" ? Tk.Theme.color.warning : Tk.Theme.color.textMuted
            }
            Tk.Label {
                objectName: "deviceStatus"
                text: window.device.status
                Tk.Flex.shrink: 0
            }
            Tk.Badge {
                visible: window.device.connected
                text: window.device.isHoltek ? "Holtek" : "Areson"
                variant: "accent"
            }
            Tk.ToolSeparator {}
            Tk.Button { text: "Reconnect"; iconName: "refresh-cw"; tooltip: "Refresh the device list and re-read settings (F5)"; onClicked: venusBackend.refresh() }
            Tk.Button { text: "Read Settings"; iconName: "download"; enabled: window.device.connected; tooltip: "Read the configuration from the mouse (Ctrl+R)"; onClicked: venusBackend.readSettings() }
            Tk.Button { text: "Export"; iconName: "save"; enabled: window.canUseProfiles; onClicked: window.exportProfile() }
            Tk.Button { text: "Import"; iconName: "folder-open"; enabled: window.canUseProfiles; onClicked: window.importProfile() }
            Tk.Caption { text: "Profile"; visible: window.device.isHoltek }
            Tk.ComboBox {
                objectName: "holtekProfile"
                visible: window.device.isHoltek
                model: window.options.holtekProfiles
                currentIndex: window.device.holtekProfile
                implicitWidth: 100
                onActivated: function(i) { venusBackend.setHoltekProfile(i) }
            }
            Tk.Spacer {}
            Tk.Spinner { running: venusBackend.busy; visible: venusBackend.busy }
            Tk.Caption { text: venusBackend.busyText; visible: venusBackend.busy }
            Tk.Button { text: "Cancel"; small: true; variant: "ghost"; visible: venusBackend.busy; onClicked: venusBackend.cancelBusy() }
            Tk.Button {
                objectName: "applyAll"
                text: window.staging.hasChanges ? "Apply " + window.staging.count + " Change" + (window.staging.count === 1 ? "" : "s") : "Apply All Changes"
                iconName: "check"; variant: "accent"
                enabled: window.staging.hasChanges && window.device.connected
                tooltip: "Write all staged changes to the device memory"
                onClicked: venusBackend.commitStaged()
            }
            Tk.Button { text: "Discard"; iconName: "rotate-ccw"; variant: "ghost"; enabled: window.staging.hasChanges; onClicked: venusBackend.discardStaged() }
            Tk.Button {
                text: "Factory Reset"; iconName: "triangle-alert"; variant: "danger"
                enabled: window.canReset
                tooltip: window.options.resetEnabled ? "Restore Areson defaults (also wipes custom macros)" : "The Holtek factory-reset sequence is not confirmed."
                onClicked: window.factoryReset()
            }
        }
    ]

    statusBar: Tk.StatusBar {
        objectName: "statusBar"
        Tk.StatusField { iconName: "mouse-pointer-2"; text: window.device.status; muted: false }
        Tk.StatusField { iconName: "list"; text: window.staging.hasChanges ? window.staging.count + " staged change" + (window.staging.count === 1 ? "" : "s") : "No staged changes" }
        Tk.Spacer {}
        Tk.StatusField { iconName: "zap"; text: venusBackend.battery.text; muted: !venusBackend.battery.known; visible: !window.device.isHoltek }
        Tk.StatusField { iconName: "panel-top"; text: "Menu in panel"; visible: window.menuHosted; tooltip: "The QindaQt shell hosts this window's menu in its global menu applet" }
        Tk.StatusField { text: window.device.path; visible: window.device.path.length > 0 }
    }

    Tk.Splitter {
        objectName: "mainSplit"
        Item {
            objectName: "mainColumn"
            T.SplitView.fillWidth: true
            T.SplitView.minimumWidth: 640
            Tk.Flex {
                anchors.fill: parent
                direction: Tk.Flex.Column
                Tk.Box {
                    color: Tk.Theme.color.surface
                    borderBottom: 1
                    borderColor: Tk.Theme.color.divider
                    paddingLeft: Tk.Theme.space.md
                    paddingRight: Tk.Theme.space.md
                    Tk.Flex.shrink: 0
                    Tk.TabStrip {
                        objectName: "pageTabs"
                        model: window.pages
                        currentIndex: window.currentPage
                        onTabActivated: function(i) { window.currentPage = i }
                    }
                }
                Item {
                    id: pageHost
                    objectName: "pageHost"
                    Tk.Flex.grow: 1
                    Tk.Flex.basis: 0
                    Tk.Flex.minHeight: 0
                    Loader {
                        id: desktopTheme
                        visible: false
                        active: venusBackend.themePreset.length === 0
                        source: "DesktopThemeBridge.qml"
                    }
                    ButtonsPage { objectName: "buttonsPage"; anchors.fill: parent; visible: window.currentPage === 0; onShowMacros: window.currentPage = 1 }
                    MacrosPage { objectName: "macrosPage"; anchors.fill: parent; visible: window.currentPage === 1 }
                    LightingPage { objectName: "lightingPage"; anchors.fill: parent; visible: window.currentPage === 2 }
                    DpiPage { objectName: "dpiPage"; anchors.fill: parent; visible: window.currentPage === 3 }
                    PollingPage { objectName: "pollingPage"; anchors.fill: parent; visible: window.currentPage === 4 }
                    AdvancedPage { objectName: "advancedPage"; anchors.fill: parent; visible: window.currentPage === 5 }
                }
            }
        }
        SidePanel {
            id: sidePanel
            objectName: "sidePanel"
            showLog: window.logVisible
            T.SplitView.preferredWidth: 380
            T.SplitView.minimumWidth: 260
        }
    }

    // The same menu, exported to the QindaQt panel's global menu.
    GlobalMenuMirror { host: window }

    // ---- dialogs ----
    Tk.MessageDialog {
        id: messageDialog
        objectName: "messageDialog"
        primaryText: "OK"
        secondaryText: ""
    }
    Tk.MessageDialog {
        id: resetDialog
        title: "Confirm Reset"
        variant: "danger"
        text: "Reset the device to factory defaults? This clears all custom button mappings, macros, and RGB settings."
        primaryText: "Reset"
        destructive: true
        onAccepted: venusBackend.factoryReset()
    }
    Tk.MessageDialog {
        id: importConfirm
        title: "Confirm Import"
        variant: "warning"
        text: "This will overwrite ALL device settings (macros, bindings, etc.) with the imported profile. Continue?"
        primaryText: "Import"
        destructive: true
        onAccepted: venusBackend.importProfile(window.pendingImport)
    }
    Tk.MessageDialog {
        id: aboutDialog
        title: "Venus Pro Config"
        variant: "info"
        text: "Reverse-engineered configuration utility for the UtechSmart Venus Pro MMO mouse (Areson 25a7:fa07/fa08 and Holtek 04d9:fc55). " +
              "QindaTK interface on QindaTK " + Tk.Theme.name + ". MIT licence."
        primaryText: "OK"
        secondaryText: ""
    }
    Dialogs.FileDialog {
        id: exportDialog
        title: "Save Profile"
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: ["Binary Files (*.bin)"]
        defaultSuffix: "bin"
        onAccepted: venusBackend.exportProfile(selectedFile)
    }
    Dialogs.FileDialog {
        id: importDialog
        title: "Open Profile"
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: ["Binary Files (*.bin)"]
        onAccepted: { window.pendingImport = selectedFile; importConfirm.open() }
    }
}
