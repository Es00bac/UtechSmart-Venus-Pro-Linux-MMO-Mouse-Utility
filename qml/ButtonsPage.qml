// SPDX-License-Identifier: MIT
import QtQuick
import QindaTK as Tk

// Buttons tab: the button list with staged markers, and the binding editor.
Item {
    id: page
    readonly property var editor: venusBackend.editor
    readonly property var options: venusBackend.options
    readonly property var staging: venusBackend.staging
    signal showMacros()

    function stage(action, values) { venusBackend.stageBinding(action, values || {}) }
    function indexOf(list, value) {
        for (let i = 0; i < list.length; ++i) if (list[i] === value) return i
        return -1
    }
    function indexOfField(list, field, value) {
        for (let i = 0; i < list.length; ++i) if (list[i][field] === value) return i
        return -1
    }

    Tk.Flex {
        anchors.fill: parent
        direction: Tk.Flex.Row
        gap: Tk.Theme.space.md
        padding: Tk.Theme.space.md

        // ---- button list ----
        Tk.Panel {
            objectName: "buttonList"
            title: "Buttons"
            iconName: "mouse-pointer-2"
            grip: false
            collapsible: false
            Tk.Flex.basis: 320
            Tk.Flex.shrink: 0
            actions: [
                Tk.Badge {
                    text: page.staging.count + " staged"
                    variant: "warning"
                    visible: page.staging.hasChanges
                }
            ]
            Tk.Scroll {
                Tk.Flex {
                    direction: Tk.Flex.Column
                    Repeater {
                        model: venusBackend.buttonsModel
                        Tk.ListRow {
                            required property var model
                            text: model.label
                            selected: model.key === page.editor.key
                            active: model.staged
                            iconName: model.staged ? "circle-dot" : "circle"
                            onClicked: venusBackend.selectButton(model.key)
                            trailing: Tk.Caption {
                                text: model.description + (model.staged ? " *" : "")
                                color: model.staged ? Tk.Theme.color.warning : Tk.Theme.color.textMuted
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }

        // ---- editor ----
        Tk.Panel {
            objectName: "bindingEditor"
            title: page.editor.key ? "Editing: " + page.editor.label : "Select a button to edit"
            iconName: "sliders-horizontal"
            grip: false
            collapsible: false
            Tk.Flex.grow: 1
            Tk.Flex.basis: 0
            Tk.Flex.minWidth: 320
            Tk.Scroll {
                padding: Tk.Theme.space.sm
                Tk.Flex {
                    direction: Tk.Flex.Column
                    gap: Tk.Theme.space.md
                    enabled: page.editor.key.length > 0

                    Tk.EmptyState {
                        visible: page.editor.key.length === 0
                        iconName: "mouse-pointer"
                        title: "No button selected"
                        text: "Pick a button on the left. Changes are staged as you edit and written by Apply All Changes."
                    }

                    Tk.Notice {
                        visible: page.editor.unsupported
                        variant: "warning"
                        text: "Unsupported: " + page.editor.action + " — choose a replacement action."
                    }

                    Tk.PropertyGroup {
                        title: "Binding"
                        collapsible: false
                        visible: page.editor.key.length > 0
                        Tk.PropertyRow {
                            label: "Action"
                            Tk.ComboBox {
                                objectName: "actionCombo"
                                model: page.options.actions
                                currentIndex: page.indexOf(page.options.actions, page.editor.action)
                                onActivated: function(i) { page.stage(page.options.actions[i]) }
                            }
                        }
                        Tk.PropertyRow {
                            label: "Preview"
                            Tk.Label { objectName: "bindingPreview"; text: page.editor.description; accent: true }
                        }
                    }

                    Tk.PropertyGroup {
                        title: "Keyboard key"
                        collapsible: false
                        visible: page.editor.action === "Keyboard Key"
                        Tk.PropertyRow {
                            label: "Key"
                            hint: "Click the field, then press the key to bind (numpad and right-side modifiers are distinguished)."
                            Tk.TextField {
                                id: keyField
                                objectName: "keyCapture"
                                readOnly: true
                                mono: true
                                iconName: "keyboard"
                                text: page.editor.keyName
                                placeholderText: activeFocus ? "Press a key…" : "Click here, then press a key…"
                                onActiveFocusChanged: activeFocus ? venusBackend.beginKeyCapture() : venusBackend.endKeyCapture()
                            }
                        }
                        Tk.PropertyRow {
                            label: "Special key"
                            Tk.ComboBox {
                                objectName: "specialKeyCombo"
                                model: ["Select special key…"].concat(Array.from(page.options.specialKeys))
                                currentIndex: page.editor.specialKey.length ? page.indexOf(page.options.specialKeys, page.editor.specialKey) + 1 : 0
                                onActivated: function(i) {
                                    if (i === 0) return
                                    page.stage("Keyboard Key", { "specialKey": page.options.specialKeys[i - 1], "keyName": "" })
                                }
                            }
                        }
                        Tk.PropertyRow {
                            label: "Modifiers"
                            hint: page.options.modifiersEnabled ? "" : "The Holtek button record stores one HID key and has no modifier field."
                            Tk.Flex {
                                direction: Tk.Flex.Row
                                gap: Tk.Theme.space.lg
                                align: Tk.Flex.Center
                                enabled: page.options.modifiersEnabled
                                Tk.CheckBox { text: "Ctrl"; checked: page.editor.modCtrl; onToggled: page.stage("Keyboard Key", { "modCtrl": checked }) }
                                Tk.CheckBox { text: "Shift"; checked: page.editor.modShift; onToggled: page.stage("Keyboard Key", { "modShift": checked }) }
                                Tk.CheckBox { text: "Alt"; checked: page.editor.modAlt; onToggled: page.stage("Keyboard Key", { "modAlt": checked }) }
                                Tk.CheckBox { text: "Win"; checked: page.editor.modWin; onToggled: page.stage("Keyboard Key", { "modWin": checked }) }
                            }
                        }
                    }

                    Tk.PropertyGroup {
                        title: "Macro"
                        collapsible: false
                        visible: page.editor.action === "Macro"
                        Tk.PropertyRow {
                            label: "Macro slot"
                            Tk.NumberField {
                                value: page.editor.macroIndex; from: 1; to: 16
                                onValueModified: function(v) { page.stage("Macro", { "macroIndex": v }) }
                            }
                        }
                        Tk.PropertyRow {
                            label: "Repeat mode"
                            Tk.ComboBox {
                                model: page.options.macroModes
                                textRole: "name"
                                currentIndex: page.indexOfField(page.options.macroModes, "value", page.editor.macroMode)
                                onActivated: function(i) { page.stage("Macro", { "macroMode": page.options.macroModes[i].value }) }
                            }
                        }
                        Tk.PropertyRow {
                            label: "Repeat count"
                            visible: page.editor.macroMode === 2
                            Tk.NumberField {
                                value: page.editor.macroCount; from: 1; to: 253
                                onValueModified: function(v) { page.stage("Macro", { "macroCount": v }) }
                            }
                        }
                        Tk.PropertyRow {
                            label: "Recall"
                            Tk.Button {
                                text: "Load from slot"; iconName: "download"
                                tooltip: "Read this slot from the mouse into the macro editor"
                                onClicked: { venusBackend.selectMacroSlot(page.editor.macroIndex); page.showMacros(); venusBackend.loadMacroFromMouse() }
                            }
                        }
                    }

                    Tk.PropertyGroup {
                        title: "Repeated click"
                        collapsible: false
                        visible: page.editor.action === "Fire Key" || page.editor.action === "Triple Click"
                        Tk.PropertyRow {
                            label: "Delay"
                            visible: page.options.specialDelayVisible
                            Tk.NumberField {
                                value: page.editor.delay; from: 0; to: 255; suffix: " ms"
                                onValueModified: function(v) { page.stage(page.editor.action, { "delay": v }) }
                            }
                        }
                        Tk.PropertyRow {
                            label: "Repeats"
                            Tk.NumberField {
                                value: page.editor.repeat; from: 0; to: 255
                                onValueModified: function(v) { page.stage(page.editor.action, { "repeat": v }) }
                            }
                        }
                    }

                    Tk.PropertyGroup {
                        title: "Media key"
                        collapsible: false
                        visible: page.editor.action === "Media Key"
                        Tk.PropertyRow {
                            label: "Function"
                            Tk.ComboBox {
                                model: page.options.mediaKeys
                                textRole: "name"
                                currentIndex: page.indexOfField(page.options.mediaKeys, "code", page.editor.mediaCode)
                                onActivated: function(i) { page.stage("Media Key", { "mediaCode": page.options.mediaKeys[i].code }) }
                            }
                        }
                    }

                    Tk.PropertyGroup {
                        title: "DPI control"
                        collapsible: false
                        visible: page.editor.action === "DPI Control"
                        Tk.PropertyRow {
                            label: "Function"
                            Tk.ComboBox {
                                model: page.options.dpiFunctions
                                textRole: "name"
                                currentIndex: page.indexOfField(page.options.dpiFunctions, "value", page.editor.dpiFunc)
                                onActivated: function(i) { page.stage("DPI Control", { "dpiFunc": page.options.dpiFunctions[i].value }) }
                            }
                        }
                    }

                    Tk.Flex {
                        direction: Tk.Flex.Row
                        align: Tk.Flex.Center
                        gap: Tk.Theme.space.md
                        visible: page.editor.key.length > 0
                        Tk.Button {
                            objectName: "stageButton"
                            text: "Stage Binding"; iconName: "list-plus"
                            tooltip: "Queue this change; Apply All Changes writes it to the mouse"
                            onClicked: page.stage(page.editor.action)
                        }
                        Tk.Button {
                            text: "Apply All Changes"; iconName: "check"; variant: "accent"
                            enabled: page.staging.hasChanges
                            onClicked: venusBackend.commitStaged()
                        }
                        Tk.Button {
                            text: "Discard All"; iconName: "rotate-ccw"; variant: "ghost"
                            enabled: page.staging.hasChanges
                            onClicked: venusBackend.discardStaged()
                        }
                    }
                }
            }
        }
    }
}
