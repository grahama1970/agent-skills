import QtQuick
import QtQuick.Controls
import "."

Button {
    id: control

    // Variant: "primary" (accentGreen), "secondary" (bgElevated), "danger" (accentRed)
    property string variant: "secondary"

    property color variantColor: variant === "primary" ? EmbryStyle.colors.accentGreen
                               : variant === "danger"  ? EmbryStyle.colors.accentRed
                               : EmbryStyle.colors.textSecondary

    property color variantBg: variant === "primary" ? EmbryStyle.colors.accentGreenBg
                            : variant === "danger"  ? EmbryStyle.colors.accentRedBg
                            : EmbryStyle.colors.bgElevated

    hoverEnabled: true

    contentItem: Text {
        text: control.text
        font.pixelSize: EmbryStyle.text.sm
        font.weight: Font.SemiBold
        color: !control.enabled ? EmbryStyle.colors.textGhost
             : control.pressed  ? variantColor
             : control.hovered  ? EmbryStyle.colors.textPrimary
             : variantColor
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        implicitWidth: 80
        implicitHeight: 32
        radius: EmbryStyle.layout.radiusSm
        color: !control.enabled ? EmbryStyle.colors.bgInput
             : control.pressed  ? EmbryStyle.colors.bgPressed
             : control.hovered  ? EmbryStyle.colors.bgHover
             : variantBg
        border.width: control.activeFocus || control.hovered ? 1 : 1
        border.color: !control.enabled ? EmbryStyle.colors.borderSubtle
                    : control.activeFocus ? EmbryStyle.colors.selectBorder
                    : control.hovered ? variantColor
                    : EmbryStyle.colors.border

        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }

    Accessible.role: Accessible.Button
}
