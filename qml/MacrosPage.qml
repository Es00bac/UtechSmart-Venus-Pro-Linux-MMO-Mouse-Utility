// SPDX-License-Identifier: MIT
import QtQuick
import QindaTK as Tk

// Macros tab: device slots, the event editor, the text and manual builders,
// and slot-to-button binding.
Item {
    id: page
    readonly property var macro: venusBackend.macro
    readonly property var options: venusBackend.options
    property int builderPage: 0
    property bool randomTiming: false
    property bool appendOutput: false
    property int bindMode: 1

    function refreshTextStatus() {
        const min = page.randomTiming ? randomMin.value : fixedDelay.value
        const max = page.randomTiming ? randomMax.value : fixedDelay.value
        venusBackend.textStatus(textInput.text, min, max, wordPause.value, page.appendOutput)
    }
    Component.onCompleted: refreshTextStatus()

    Tk.Flex {
        anchors.fill: parent
        direction: Tk.Flex.Row
        gap: Tk.Theme.space.md
        padding: Tk.Theme.space.md

        Tk.Panel {
            objectName: "macroSlots"
            title: "Macro slots"
            iconName: "list-ordered"
            grip: false
            collapsible: false
            Tk.Flex.basis: 210
            Tk.Flex.shrink: 0
            Tk.Scroll {
                Tk.Flex {
                    direction: Tk.Flex.Column
                    gap: Tk.Theme.space.xs
                    Repeater {
                        model: venusBackend.macroSlotsModel
                        Tk.ListRow {
                            required property var model
                            text: model.label
                            selected: model.slot === page.macro.slot
                            onClicked: venusBackend.selectMacroSlot(model.slot)
                            onDoubleClicked: { venusBackend.selectMacroSlot(model.slot); venusBackend.loadMacroFromMouse() }
                        }
                    }
                    Tk.Caption {
                        text: "Select a target; double-click to load it from the mouse."
                        wrapMode: Text.Wrap
                        padding: Tk.Theme.space.sm
                    }
                }
            }
        }

        Tk.Flex {
            direction: Tk.Flex.Column
            gap: Tk.Theme.space.sm
            Tk.Flex.grow: 1
            Tk.Flex.basis: 0
            Tk.Flex.minWidth: 420
            enabled: page.options.macrosEnabled

            Tk.Notice {
                visible: !page.options.macrosEnabled
                variant: "warning"
                text: "The Holtek controller has no confirmed hardware macro format; the editor is disabled for this mouse."
            }

            // ---- slot header ----
            Tk.Flex {
                direction: Tk.Flex.Row
                align: Tk.Flex.Center
                gap: Tk.Theme.space.sm
                Tk.Caption { text: "Slot" }
                Tk.NumberField {
                    objectName: "slotField"
                    value: page.macro.slot; from: 1; to: 16
                    implicitWidth: 64
                    onValueModified: function(v) { venusBackend.selectMacroSlot(v) }
                }
                Tk.Caption { text: "Name" }
                Tk.TextField {
                    id: macroNameField
                    objectName: "macroName"
                    text: page.macro.name
                    maximumLength: 15
                    tooltip: "The mouse stores up to 15 UTF-16 code units in a macro name."
                    Tk.Flex.grow: 1
                    Tk.Flex.basis: 0
                    Tk.Flex.minWidth: 100
                    onEditingFinished: venusBackend.setMacroName(text)
                }
                Tk.Button { text: "Load from Mouse"; iconName: "download"; onClicked: venusBackend.loadMacroFromMouse() }
                Tk.Button { text: "Save to Mouse"; iconName: "save"; variant: "accent"; onClicked: { venusBackend.setMacroName(macroNameField.text); venusBackend.saveMacroToMouse() } }
            }

            // ---- editing tools ----
            Tk.Flex {
                direction: Tk.Flex.Row
                align: Tk.Flex.Center
                gap: Tk.Theme.space.xs
                Tk.Button {
                    objectName: "recordButton"
                    text: page.macro.recording ? "Recording…" : "Record"
                    iconName: "circle"
                    variant: page.macro.recording ? "danger" : "default"
                    tooltip: "Record keyboard presses and releases with their timing"
                    onClicked: venusBackend.toggleRecording()
                }
                Tk.Button { text: "Stop"; iconName: "square"; enabled: page.macro.recording; onClicked: venusBackend.stopRecording() }
                Tk.ToolSeparator {}
                Tk.IconButton { iconName: "chevron-up"; tooltip: "Move selected event up"; ghost: false; onClicked: venusBackend.moveEvent(-1) }
                Tk.IconButton { iconName: "chevron-down"; tooltip: "Move selected event down"; ghost: false; onClicked: venusBackend.moveEvent(1) }
                Tk.Button { text: "Duplicate"; iconName: "copy"; onClicked: venusBackend.duplicateEvent() }
                Tk.Button { text: "Delete Selected"; iconName: "trash-2"; onClicked: venusBackend.deleteSelectedEvents() }
                Tk.Button { text: "Clear All"; iconName: "eraser"; variant: "ghost"; onClicked: venusBackend.clearEvents() }
            }

            // ---- event table ----
            Tk.Box {
                objectName: "eventTable"
                color: Tk.Theme.color.panelAlt
                borderWidth: 1
                radius: Tk.Theme.radius.sm
                Tk.Flex.grow: 1
                Tk.Flex.basis: 0
                Tk.Flex.minHeight: 140
                Tk.Flex {
                    direction: Tk.Flex.Column
                    Tk.Flex {
                        direction: Tk.Flex.Row
                        align: Tk.Flex.Center
                        gap: Tk.Theme.space.sm
                        paddingLeft: Tk.Theme.space.sm
                        paddingRight: Tk.Theme.space.xs
                        paddingTop: Tk.Theme.space.xs
                        paddingBottom: Tk.Theme.space.xs
                        Tk.Flex.shrink: 0
                        Tk.Overline { title: "#"; Tk.Flex.basis: 28; Tk.Flex.shrink: 0 }
                        Tk.Overline { title: "Event"; Tk.Flex.grow: 1; Tk.Flex.basis: 0 }
                        Tk.Overline { title: "Action"; Tk.Flex.basis: 56; Tk.Flex.shrink: 0 }
                        Tk.Overline { title: "Delay after"; Tk.Flex.basis: 96; Tk.Flex.shrink: 0 }
                        Tk.Spacer { size: Tk.Theme.size.controlSm }
                    }
                    Tk.Divider { Tk.Flex.shrink: 0 }
                    Tk.Scroll {
                        Tk.Flex.grow: 1
                        Tk.Flex.basis: 0
                        Tk.Flex.minHeight: 0
                        Tk.Flex {
                            direction: Tk.Flex.Column
                            Repeater {
                                model: venusBackend.macroEventsModel
                                MacroEventRow {}
                            }
                            Tk.EmptyState {
                                visible: page.macro.count === 0
                                iconName: "keyboard"
                                title: "No events"
                                text: "Record keys, generate text, or add events by hand."
                            }
                        }
                    }
                }
            }

            Tk.Flex {
                direction: Tk.Flex.Row
                align: Tk.Flex.Center
                gap: Tk.Theme.space.sm
                Tk.ProgressBar {
                    objectName: "capacityBar"
                    value: page.macro.count; from: 0; to: page.macro.capacity
                    Tk.Flex.grow: 1
                    Tk.Flex.basis: 0
                }
                Tk.Caption { text: page.macro.count + " / " + page.macro.capacity + " hardware events · " + page.macro.free + " free"; Tk.Flex.shrink: 0 }
            }

            // ---- builders ----
            Tk.TabStrip {
                model: ["Text Builder", "Manual Events"]
                currentIndex: page.builderPage
                onTabActivated: function(i) { page.builderPage = i }
            }

            Tk.Flex {
                direction: Tk.Flex.Column
                gap: Tk.Theme.space.sm
                visible: page.builderPage === 0
                Tk.TextArea {
                    id: textInput
                    objectName: "textInput"
                    placeholderText: "Type text to convert into hardware key presses (US keyboard layout)…"
                    rows: 2
                    onTextChanged: page.refreshTextStatus()
                }
                Tk.Flex {
                    direction: Tk.Flex.Row
                    wrap: Tk.Flex.Wrap
                    align: Tk.Flex.Center
                    gap: Tk.Theme.space.sm
                    Tk.Caption { text: "Timing" }
                    Tk.Segmented {
                        model: ["Fixed", "Random range"]
                        currentIndex: page.randomTiming ? 1 : 0
                        onActivated: function(i) { page.randomTiming = i === 1; page.refreshTextStatus() }
                    }
                    Tk.Caption { text: "Key held" }
                    Tk.NumberField { id: keyHold; value: 35; from: 3; to: 65535; suffix: " ms"; implicitWidth: 80 }
                    Tk.Caption { text: "Between keys"; visible: !page.randomTiming }
                    Tk.NumberField { id: fixedDelay; visible: !page.randomTiming; value: 90; from: 3; to: 65535; suffix: " ms"; implicitWidth: 80; onValueModified: page.refreshTextStatus() }
                    Tk.Caption { text: "Between"; visible: page.randomTiming }
                    Tk.NumberField { id: randomMin; visible: page.randomTiming; value: 70; from: 3; to: 65535; suffix: " ms"; implicitWidth: 80; onValueModified: page.refreshTextStatus() }
                    Tk.Caption { text: "to"; visible: page.randomTiming }
                    Tk.NumberField { id: randomMax; visible: page.randomTiming; value: 160; from: 3; to: 65535; suffix: " ms"; implicitWidth: 80; onValueModified: page.refreshTextStatus() }
                    Tk.Caption { text: "Extra after spaces" }
                    Tk.NumberField { id: wordPause; value: 60; from: 0; to: 65535; suffix: " ms"; implicitWidth: 80; onValueModified: page.refreshTextStatus() }
                    Tk.Caption { text: "Output" }
                    Tk.ComboBox {
                        model: ["Replace current events", "Append to current events"]
                        currentIndex: page.appendOutput ? 1 : 0
                        implicitWidth: 180
                        onActivated: function(i) { page.appendOutput = i === 1; page.refreshTextStatus() }
                    }
                    Tk.Button {
                        objectName: "generateButton"
                        text: "Generate Text Events"; iconName: "sparkles"; variant: "accent"
                        enabled: textInput.text.length > 0 && !page.macro.builderError
                        onClicked: {
                            const min = page.randomTiming ? randomMin.value : fixedDelay.value
                            const max = page.randomTiming ? randomMax.value : fixedDelay.value
                            venusBackend.generateText(textInput.text, keyHold.value, min, max, wordPause.value, page.appendOutput)
                        }
                    }
                }
            }

            Tk.Flex {
                direction: Tk.Flex.Column
                gap: Tk.Theme.space.sm
                visible: page.builderPage === 1
                Tk.Flex {
                    direction: Tk.Flex.Row
                    wrap: Tk.Flex.Wrap
                    align: Tk.Flex.Center
                    gap: Tk.Theme.space.sm
                    Tk.Caption { text: "Event" }
                    Tk.ComboBox { id: manualChoice; model: page.options.manualChoices; textRole: "label"; implicitWidth: 190; currentIndex: 0 }
                    Tk.Caption { text: "Action" }
                    Tk.ComboBox { id: manualAction; model: ["Tap (press + release)", "Press only", "Release only"]; implicitWidth: 160; currentIndex: 0 }
                    Tk.Caption { text: "Held"; enabled: manualAction.currentIndex === 0 }
                    Tk.NumberField { id: manualHold; value: 35; from: 3; to: 65535; suffix: " ms"; implicitWidth: 80; enabled: manualAction.currentIndex === 0 }
                    Tk.Caption { text: "Delay after" }
                    Tk.NumberField { id: manualDelay; value: 90; from: 0; to: 65535; suffix: " ms"; implicitWidth: 80 }
                    Tk.Button {
                        text: manualAction.currentIndex === 0 ? "Add Tap" : "Add Event"
                        iconName: "plus"; variant: "accent"
                        onClicked: venusBackend.addManualEvent(manualChoice.currentIndex,
                                                               ["tap", "press", "release"][manualAction.currentIndex],
                                                               manualHold.value, manualDelay.value)
                    }
                }
                Tk.Flex {
                    direction: Tk.Flex.Row
                    wrap: Tk.Flex.Wrap
                    align: Tk.Flex.Center
                    gap: Tk.Theme.space.sm
                    Tk.Caption { text: "Set selected delays" }
                    Tk.NumberField { id: selectedDelay; value: 90; from: 0; to: 65535; suffix: " ms"; implicitWidth: 80 }
                    Tk.Button { text: "Apply"; onClicked: venusBackend.applyDelayToSelected(selectedDelay.value) }
                    Tk.Caption { text: "A delay belongs to the event before it. Tap adds a matched press/release pair. Ctrl-click and Shift-click select several rows." }
                }
            }

            Tk.Caption {
                objectName: "builderStatus"
                text: page.macro.builderStatus
                color: page.macro.builderError ? Tk.Theme.color.danger : Tk.Theme.color.textMuted
                wrapMode: Text.Wrap
            }
            Tk.Mono { objectName: "macroPreview"; text: page.macro.preview; selectable: true }

            // ---- bind ----
            Tk.Box {
                color: Tk.Theme.color.panelAlt
                borderWidth: 1
                radius: Tk.Theme.radius.sm
                padding: Tk.Theme.space.sm
                Tk.Flex {
                    direction: Tk.Flex.Row
                    wrap: Tk.Flex.Wrap
                    align: Tk.Flex.Center
                    gap: Tk.Theme.space.sm
                    Tk.Overline { title: "Bind saved slot" }
                    Tk.Caption { text: "to button" }
                    Tk.ComboBox { id: bindButton; model: page.options.buttonChoices; textRole: "label"; implicitWidth: 170; currentIndex: 0 }
                    Tk.Caption { text: "Repeat" }
                    Tk.ComboBox {
                        id: bindModeCombo
                        model: page.options.macroModes
                        textRole: "name"
                        implicitWidth: 150
                        currentIndex: 0
                        onActivated: function(i) { page.bindMode = page.options.macroModes[i].value }
                    }
                    Tk.Caption { text: "Count" }
                    Tk.NumberField { id: bindCount; value: 1; from: 1; to: 253; implicitWidth: 64; enabled: page.bindMode === 2 }
                    Tk.Button {
                        text: "Bind Slot " + page.macro.slot; iconName: "link"; variant: "accent"
                        enabled: bindButton.currentIndex >= 0
                        onClicked: venusBackend.bindSlotToButton(page.options.buttonChoices[bindButton.currentIndex].key, page.bindMode, bindCount.value)
                    }
                }
            }
        }
    }
}
