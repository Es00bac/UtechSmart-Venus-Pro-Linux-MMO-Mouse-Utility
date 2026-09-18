// SPDX-License-Identifier: MIT
import QtQuick
import QtQuick.Dialogs as Dialogs
import QindaTK as Tk

// Lighting tab: quick-pick colours, colour/mode/brightness/speed, and the
// battery-gauge controller.
Item {
    id: page
    readonly property var lighting: venusBackend.lighting
    readonly property var options: venusBackend.options
    function indexOfField(list, field, value) {
        for (let i = 0; i < list.length; ++i) if (list[i][field] === value) return i
        return -1
    }

    Dialogs.ColorDialog {
        id: colorDialog
        title: "Pick LED Color"
        selectedColor: page.lighting.hex
        onAccepted: venusBackend.setRgbColor(selectedColor)
    }

    Tk.Scroll {
        anchors.fill: parent
        padding: Tk.Theme.space.md
        Tk.Flex {
            direction: Tk.Flex.Column
            gap: Tk.Theme.space.lg

            Tk.PropertyGroup {
                title: "Quick pick colours"
                collapsible: false
                Tk.ColorSwatches {
                    objectName: "quickPicks"
                    colors: Array.from(page.options.quickPicks)
                    current: page.lighting.hex
                    columns: 9
                    customButton: true
                    onSelected: function(c) { venusBackend.setRgbColor(c) }
                    onCustomRequested: colorDialog.open()
                }
            }

            Tk.PropertyGroup {
                title: "Lighting"
                collapsible: false
                Tk.PropertyRow {
                    label: "Colour"
                    Tk.Flex {
                        direction: Tk.Flex.Row
                        align: Tk.Flex.Center
                        gap: Tk.Theme.space.sm
                        Tk.ColorField {
                            objectName: "colorField"
                            color: page.lighting.hex
                            implicitWidth: 140
                            onColorEdited: function(c) { venusBackend.setRgbColor(c) }
                            onPickRequested: colorDialog.open()
                        }
                        Tk.Button { text: "Pick custom colour…"; iconName: "pipette"; onClicked: colorDialog.open() }
                    }
                }
                Tk.PropertyRow {
                    label: "Mode"
                    Tk.Flex { direction: Tk.Flex.Row
                    Tk.ComboBox {
                        objectName: "modeCombo"
                        model: page.options.rgbModes
                        textRole: "name"
                        implicitWidth: 160
                        currentIndex: page.indexOfField(page.options.rgbModes, "value", page.lighting.mode)
                        onActivated: function(i) { venusBackend.setRgbMode(page.options.rgbModes[i].value) }
                    }
                    }
                }
                Tk.PropertyRow {
                    label: page.lighting.brightnessLabel
                    Tk.Flex { direction: Tk.Flex.Row; align: Tk.Flex.Center
                    Tk.Slider {
                        objectName: "brightnessSlider"
                        value: page.lighting.brightness
                        from: 0; to: page.lighting.brightnessMax; stepSize: 1
                        showValue: true
                        suffix: page.lighting.brightnessSuffix
                        implicitWidth: 320
                        onValueModified: function(v) { venusBackend.setRgbBrightness(Math.round(v)) }
                    }
                    }
                }
                Tk.PropertyRow {
                    label: page.lighting.speedLabel
                    visible: page.lighting.showSpeed
                    Tk.NumberField {
                        value: page.lighting.speed
                        from: page.lighting.speedMin; to: page.lighting.speedMax
                        implicitWidth: 80
                        tooltip: "Areson animation speed: 1 is fastest and 5 is slowest. Holtek exposes a raw per-profile speed byte."
                        onValueModified: function(v) { venusBackend.setRgbSpeed(v) }
                    }
                }
                Tk.PropertyRow {
                    label: ""
                    Tk.Flex { direction: Tk.Flex.Row
                    Tk.Button { objectName: "applyLighting"; text: "Apply Lighting"; iconName: "zap"; variant: "accent"; onClicked: venusBackend.applyLighting() }
                    }
                }
            }

            Tk.PropertyGroup {
                title: "Battery gauge"
                collapsible: false
                Tk.Switch {
                    objectName: "batteryLedSwitch"
                    text: "Use the mouse LED as a battery gauge while this app is running"
                    checked: page.lighting.batteryLedEnabled
                    enabled: page.lighting.batteryLedSupported
                    onToggled: venusBackend.setBatteryLedEnabled(checked)
                }
                Tk.Flex {
                    direction: Tk.Flex.Row
                    align: Tk.Flex.Center
                    gap: Tk.Theme.space.sm
                    Repeater {
                        model: page.options.batteryGradient
                        Tk.Flex {
                            required property var modelData
                            direction: Tk.Flex.Row
                            align: Tk.Flex.Center
                            gap: Tk.Theme.space.xs
                            Rectangle {
                                implicitWidth: Tk.Theme.size.iconSm; implicitHeight: Tk.Theme.size.iconSm
                                radius: Tk.Theme.radius.full
                                color: modelData.color       // battery gradient data, not chrome
                            }
                            Tk.Caption { text: modelData.label.length ? modelData.label : "→" }
                        }
                    }
                }
                Tk.Caption {
                    text: "Uses a low 10% steady-light setting and updates only when the mouse reports a different 10% battery step. " +
                          "Closing the window keeps the controller in the tray; quitting restores the lighting that was active when the mode was enabled. " +
                          "The wireless firmware may still switch its RGB off after inactivity; this mode does not rewrite the EEPROM as a keepalive."
                    wrapMode: Text.Wrap
                }
            }
        }
    }
}
