// SPDX-License-Identifier: MIT
import QtQuick
import QindaTK as Tk

// DPI tab: enabled stage count, per-stage preset/DPI/raw editing.
Item {
    id: page
    readonly property var dpiState: venusBackend.dpi

    Tk.Scroll {
        anchors.fill: parent
        padding: Tk.Theme.space.md
        Tk.Flex {
            direction: Tk.Flex.Column
            gap: Tk.Theme.space.md

            Tk.Label { text: page.dpiState.header; muted: true; wrapMode: Text.Wrap }

            Tk.Flex {
                direction: Tk.Flex.Row
                align: Tk.Flex.Center
                gap: Tk.Theme.space.md
                Tk.Caption { text: "Enabled stages" }
                Tk.NumberField {
                    objectName: "stageCount"
                    value: page.dpiState.stageCount; from: 1; to: page.dpiState.stageMax
                    implicitWidth: 64
                    onValueModified: function(v) { venusBackend.setDpiStageCount(v) }
                }
                Tk.Caption { text: "Current stage"; visible: page.dpiState.showActive }
                Tk.NumberField {
                    visible: page.dpiState.showActive
                    value: page.dpiState.activeStage; from: 1; to: page.dpiState.stageCount
                    implicitWidth: 64
                    onValueModified: function(v) { venusBackend.setDpiActiveStage(v) }
                }
            }

            Tk.Flex {
                direction: Tk.Flex.Row
                align: Tk.Flex.Center
                gap: Tk.Theme.space.sm
                Tk.Overline { title: "Slot"; Tk.Flex.basis: 56; Tk.Flex.shrink: 0 }
                Tk.Overline { title: "Preset"; Tk.Flex.basis: 130; Tk.Flex.shrink: 0 }
                Tk.Overline { title: "DPI"; Tk.Flex.basis: 130; Tk.Flex.shrink: 0 }
                Tk.Overline { title: "Raw value"; visible: page.dpiState.showRaw; Tk.Flex.basis: 100; Tk.Flex.shrink: 0 }
                Tk.Overline { title: "Check"; visible: page.dpiState.showRaw; Tk.Flex.basis: 60; Tk.Flex.shrink: 0 }
            }
            Tk.Divider {}

            Repeater {
                model: venusBackend.dpiModel
                Tk.Flex {
                    required property var model
                    direction: Tk.Flex.Row
                    align: Tk.Flex.Center
                    gap: Tk.Theme.space.sm
                    visible: model.inUse
                    Tk.Caption { text: parent.model.label; Tk.Flex.basis: 56; Tk.Flex.shrink: 0 }
                    Tk.ComboBox {
                        model: page.dpiState.presetLabels
                        currentIndex: parent.model.presetIndex
                        Tk.Flex.basis: 130; Tk.Flex.shrink: 0
                        onActivated: function(i) { venusBackend.setDpiPreset(parent.model.slot, i) }
                    }
                    Tk.NumberField {
                        value: parent.model.dpi
                        from: page.dpiState.min; to: page.dpiState.max; stepSize: page.dpiState.step
                        suffix: " DPI"
                        Tk.Flex.basis: 130; Tk.Flex.shrink: 0
                        onValueModified: function(v) { venusBackend.setDpiValue(parent.model.slot, v) }
                    }
                    Tk.NumberField {
                        visible: page.dpiState.showRaw
                        value: parent.model.raw; from: 0; to: 255
                        tooltip: "Raw sensor byte; presets are capture-backed, custom values are approximate."
                        Tk.Flex.basis: 100; Tk.Flex.shrink: 0
                        onValueModified: function(v) { venusBackend.setDpiRaw(parent.model.slot, v) }
                    }
                    Tk.Mono {
                        visible: page.dpiState.showRaw
                        text: "0x" + parent.model.tweak.toString(16).padStart(2, "0")
                        Tk.Flex.basis: 60; Tk.Flex.shrink: 0
                    }
                }
            }

            Tk.Flex {
                direction: Tk.Flex.Row
                Tk.Button { objectName: "applyDpi"; text: "Apply DPI Slots"; iconName: "gauge"; variant: "accent"; onClicked: venusBackend.applyDpi() }
            }
        }
    }
}
