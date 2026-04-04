import QtQuick
import QtQuick.Controls
import "."

// EmbryTextField — themed TextField matching EmbryStyle design tokens.
// Drop-in replacement: same API as TextField.
TextField {
    id: control

    color: !enabled ? EmbryStyle.colors.textDisabled
         : EmbryStyle.colors.textPrimary
    placeholderTextColor: EmbryStyle.colors.textPlaceholder
    font.pixelSize: EmbryStyle.text.sm
    selectionColor: EmbryStyle.colors.selectBg
    selectedTextColor: EmbryStyle.colors.textPrimary

    background: Rectangle {
        implicitWidth: 140
        implicitHeight: 32
        radius: EmbryStyle.layout.radiusSm
        color: !control.enabled ? EmbryStyle.colors.bgElevated
             : control.activeFocus ? EmbryStyle.colors.bgInput
             : EmbryStyle.colors.bgInput
        border.width: 1
        border.color: control.activeFocus ? EmbryStyle.colors.borderFocused
                    : control.hovered     ? EmbryStyle.colors.textMuted
                    : EmbryStyle.colors.borderInput
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }

    Accessible.role: Accessible.EditableText
}
