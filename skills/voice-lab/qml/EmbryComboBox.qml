import QtQuick
import QtQuick.Controls
import "."

// EmbryComboBox — themed ComboBox matching EmbryStyle design tokens.
// Drop-in replacement: same API as ComboBox.
ComboBox {
    id: control

    hoverEnabled: true
    font.pixelSize: EmbryStyle.text.sm

    indicator: Text {
        x: control.width - width - EmbryStyle.layout.space2
        y: (control.height - height) / 2
        text: "\u25BE"   // ▾ small down triangle
        font.pixelSize: EmbryStyle.text.sm
        color: control.hovered ? EmbryStyle.colors.textPrimary
             : EmbryStyle.colors.textMuted
        Behavior on color { ColorAnimation { duration: 120 } }
    }

    contentItem: Text {
        leftPadding: EmbryStyle.layout.space2
        rightPadding: EmbryStyle.layout.space4
        text: control.displayText
        font.pixelSize: EmbryStyle.text.sm
        color: !control.enabled ? EmbryStyle.colors.textDisabled
             : EmbryStyle.colors.textPrimary
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        implicitWidth: 140
        implicitHeight: 32
        radius: EmbryStyle.layout.radiusSm
        color: control.pressed  ? EmbryStyle.colors.bgPressed
             : control.hovered  ? EmbryStyle.colors.bgHover
             : EmbryStyle.colors.bgInput
        border.width: 1
        border.color: control.activeFocus ? EmbryStyle.colors.borderFocused
                    : control.hovered     ? EmbryStyle.colors.textMuted
                    : EmbryStyle.colors.borderInput
        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }

    popup: Popup {
        y: control.height + 2
        width: control.width
        implicitHeight: contentItem.implicitHeight + 2
        padding: 1

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }

        background: Rectangle {
            radius: EmbryStyle.layout.radiusSm
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border
        }
    }

    delegate: ItemDelegate {
        width: control.width
        height: 30

        contentItem: Text {
            text: control.textRole ? (Array.isArray(control.model) ? modelData : model[control.textRole]) : modelData
            font.pixelSize: EmbryStyle.text.sm
            color: highlighted ? EmbryStyle.colors.textPrimary
                 : EmbryStyle.colors.textSecondary
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        highlighted: control.highlightedIndex === index

        background: Rectangle {
            color: highlighted ? EmbryStyle.colors.selectBg
                 : hovered     ? EmbryStyle.colors.bgHover
                 : "transparent"
        }
    }

    Accessible.role: Accessible.ComboBox
}
