// SPDX-License-Identifier: MIT
import QtQuick
import QindaTK as Tk

// Advanced tab: hand-built and raw 17-byte Areson feature reports.
Item {
    id: page
    readonly property var options: venusBackend.options

    Tk.Flex {
        anchors.fill: parent
        direction: Tk.Flex.Column
        gap: Tk.Theme.space.md
        padding: Tk.Theme.space.md
        align: Tk.Flex.Stretch

        Tk.Notice {
            visible: !page.options.advancedEnabled
            variant: "warning"
            text: "Raw reports on this tab use the 17-byte Areson format and cannot be sent to a Holtek device."
        }
        Tk.Notice {
            visible: page.options.advancedEnabled
            variant: "danger"
            title: "Diagnostics"
            text: "Reports are written to the mouse as-is. EEPROM writes persist immediately; read the protocol notes before sending anything."
        }

        Tk.PropertyGroup {
            title: "Build a report"
            collapsible: false
            enabled: page.options.advancedEnabled
            Tk.PropertyRow {
                label: "Command (hex)"
                labelWidth: 170
                Tk.Flex { direction: Tk.Flex.Row; Tk.TextField { id: commandField; text: "07"; mono: true; implicitWidth: 80 } }
            }
            Tk.PropertyRow {
                label: "Payload (14 bytes hex)"
                labelWidth: 170
                Tk.TextField { id: payloadField; mono: true; placeholderText: "00 00 60 04 01 02 00 52 …" }
            }
            Tk.PropertyRow {
                label: ""
                Tk.Flex { direction: Tk.Flex.Row; Tk.Button { text: "Send Built Report"; iconName: "send"; onClicked: venusBackend.sendBuiltReport(commandField.text, payloadField.text) } }
            }
        }
        Tk.PropertyGroup {
            title: "Raw report"
            collapsible: false
            enabled: page.options.advancedEnabled
            Tk.PropertyRow {
                label: "Full report (17 bytes hex)"
                labelWidth: 170
                Tk.TextField { id: rawField; mono: true; placeholderText: "08 03 00 … checksum" }
            }
            Tk.PropertyRow {
                label: ""
                Tk.Flex { direction: Tk.Flex.Row; Tk.Button { text: "Send Raw Report"; iconName: "send"; onClicked: venusBackend.sendRawReport(rawField.text) } }
            }
        }
    }
}
