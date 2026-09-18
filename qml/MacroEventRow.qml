// SPDX-License-Identifier: MIT
import QtQuick
import QindaTK as Tk

// One row of the macro event table: #, event, press/release, delay, delete.
Tk.Box {
    id: rowBox
    required property int index
    required property var model
    implicitHeight: Tk.Theme.size.control + Tk.Theme.space.xs
    color: model.selected ? Tk.Theme.color.selection
         : (tap.pressed ? Tk.Theme.color.pressed : (hover.hovered ? Tk.Theme.color.hover : "transparent"))
    radius: Tk.Theme.radius.xs
    Accessible.role: Accessible.ListItem
    Accessible.name: model.keyName + " " + model.actionText

    HoverHandler { id: hover }
    TapHandler {
        id: tap
        onTapped: venusBackend.selectEvent(rowBox.model.row,
                                           (tap.point.modifiers & Qt.ControlModifier) !== 0,
                                           (tap.point.modifiers & Qt.ShiftModifier) !== 0)
    }

    Tk.Flex {
        anchors.fill: parent
        direction: Tk.Flex.Row
        align: Tk.Flex.Center
        gap: Tk.Theme.space.sm
        paddingLeft: Tk.Theme.space.sm
        paddingRight: Tk.Theme.space.xs
        Tk.Mono { text: rowBox.model.row + 1; Tk.Flex.basis: 28; Tk.Flex.shrink: 0; horizontalAlignment: Text.AlignRight }
        Tk.Icon {
            name: rowBox.model.kind === "mouse" ? "mouse-pointer" : (rowBox.model.kind === "modifier" ? "command" : "keyboard")
            size: Tk.Theme.size.iconSm
            color: Tk.Theme.color.textMuted
            Tk.Flex.shrink: 0
        }
        Tk.Label { text: rowBox.model.keyName; Tk.Flex.grow: 1; Tk.Flex.basis: 0; Tk.Flex.minWidth: 60 }
        Tk.Badge {
            text: rowBox.model.actionText
            variant: rowBox.model.isDown ? "accent" : "default"
            Tk.Flex.basis: 56; Tk.Flex.shrink: 0
        }
        Tk.NumberField {
            objectName: "delayField"
            value: rowBox.model.delay
            from: 0; to: 65535
            suffix: " ms"
            small: true
            tooltip: "Delay after this event"
            Tk.Flex.basis: 96; Tk.Flex.shrink: 0
            onValueModified: function(v) { venusBackend.setEventDelay(rowBox.model.row, v) }
        }
        Tk.IconButton {
            iconName: "x"; small: true; tooltip: "Delete event"
            onClicked: venusBackend.deleteEvent(rowBox.model.row)
        }
    }
}
