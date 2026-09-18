// SPDX-License-Identifier: MIT
import QtQuick
import QindaTK as Tk

// Polling tab: the USB report rate.
Item {
    id: page
    readonly property var options: venusBackend.options

    Tk.Flex {
        anchors.fill: parent
        direction: Tk.Flex.Column
        gap: Tk.Theme.space.md
        padding: Tk.Theme.space.md
        align: Tk.Flex.Start

        Tk.PropertyGroup {
            title: "USB polling rate"
            collapsible: false
            Tk.PropertyRow {
                label: "Polling rate"
                Tk.Flex { direction: Tk.Flex.Row
                Tk.Segmented {
                    objectName: "pollingSegments"
                    model: page.options.pollingRates.map(function(r) { return r + " Hz" })
                    currentIndex: page.options.pollingRates.indexOf(venusBackend.polling)
                    onActivated: function(i) { venusBackend.setPollingRate(page.options.pollingRates[i]) }
                }
                }
            }
            Tk.PropertyRow {
                label: ""
                Tk.Flex { direction: Tk.Flex.Row
                Tk.Button { objectName: "applyPolling"; text: "Apply Polling Rate"; iconName: "activity"; variant: "accent"; onClicked: venusBackend.applyPolling() }
                }
            }
        }
        Tk.Grid {
            columns: "auto 1fr"
            columnGap: Tk.Theme.space.md
            rowGap: Tk.Theme.space.xs
            Tk.Mono { text: "125 Hz" }  Tk.Caption { text: "lowest CPU usage" }
            Tk.Mono { text: "250 Hz" }  Tk.Caption { text: "" }
            Tk.Mono { text: "500 Hz" }  Tk.Caption { text: "" }
            Tk.Mono { text: "1000 Hz" } Tk.Caption { text: "best responsiveness for gaming" }
        }
    }
}
