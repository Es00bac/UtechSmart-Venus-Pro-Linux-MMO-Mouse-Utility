// SPDX-License-Identifier: MIT
import QtQuick
import QtQuick.Templates as T
import QindaTK as Tk

// Right column: the mouse picture and the session log.
Item {
    id: side
    property bool showLog: true

    Tk.Flex {
        anchors.fill: parent
        direction: Tk.Flex.Column
        gap: Tk.Theme.space.md
        padding: Tk.Theme.space.md
        paddingLeft: 0

        Tk.Panel {
            objectName: "mousePanel"
            title: "Mouse"
            iconName: "mouse-pointer-2"
            grip: false
            collapsible: false
            Tk.Flex.shrink: 0
            Item {
                implicitHeight: 210
                implicitWidth: 200
                Image {
                    objectName: "mouseImage"
                    anchors.fill: parent
                    source: venusBackend.mouseImage
                    fillMode: Image.PreserveAspectFit
                    sourceSize.width: 640
                    asynchronous: true
                }
            }
        }

        Tk.Panel {
            objectName: "logPanel"
            title: "Log"
            iconName: "scroll-text"
            grip: false
            collapsible: false
            visible: side.showLog
            Tk.Flex.grow: 1
            Tk.Flex.basis: 0
            Tk.Flex.minHeight: 120
            actions: [
                Tk.IconButton { iconName: "trash-2"; tooltip: "Clear log"; small: true; onClicked: venusBackend.clearLog() }
            ]
            ListView {
                id: logView
                objectName: "logView"
                clip: true
                model: venusBackend.logModel
                spacing: 1
                delegate: Tk.Mono {
                    required property var model
                    text: model.text
                    width: ListView.view.width
                    wrapMode: Text.Wrap
                    elide: Text.ElideNone
                    font.pixelSize: Tk.Theme.font.caption
                }
                T.ScrollBar.vertical: Tk.ScrollBar {}
                onCountChanged: Qt.callLater(function() { logView.positionViewAtEnd() })
            }
        }
    }
}
