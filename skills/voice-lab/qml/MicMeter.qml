import QtQuick
import QtQuick.Controls
import "."

// Horizontal mic level meter — real-time PipeWire input
// Full-width bar with animated fill and peak indicator

Item {
    id: root

    required property real level  // 0.0–1.0 from bridge.micLevel
    property bool reduceMotion: false

    implicitHeight: 28
    implicitWidth: 400

    Accessible.name: "Microphone level meter"
    Accessible.role: Accessible.ProgressBar

    Rectangle {
        id: track
        anchors.fill: parent
        radius: EmbryStyle.layout.radiusSm
        color: EmbryStyle.colors.bgInput

        // Border
        border.width: 1
        border.color: EmbryStyle.colors.border

        // Label
        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: EmbryStyle.layout.space2
            text: "MIC"
            font.pixelSize: EmbryStyle.text.xs
            font.weight: EmbryStyle.text.weightMedium
            color: EmbryStyle.colors.textMuted
            z: 2
        }

        // Fill bar
        Rectangle {
            id: fill
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: parent.width * Math.min(1.0, root.level)
            radius: EmbryStyle.layout.radiusSm
            color: root.level > 0.85 ? EmbryStyle.colors.statusCritical
                 : root.level > 0.6  ? EmbryStyle.colors.statusWarning
                 :                      EmbryStyle.colors.accentGreen
            opacity: 0.7

            Behavior on width {
                enabled: !root.reduceMotion
                NumberAnimation { duration: 33 }  // ~30fps smoothing
            }

            Behavior on color {
                enabled: !root.reduceMotion
                ColorAnimation { duration: EmbryStyle.anim.fast }
            }
        }

        // dB readout
        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            anchors.rightMargin: EmbryStyle.layout.space2
            text: root.level > 0.001
                ? (20 * Math.log(root.level) / Math.LN10).toFixed(1) + " dB"
                : "-∞ dB"
            font.pixelSize: EmbryStyle.text.xs
            font.family: EmbryStyle.text.monoFamily
            color: EmbryStyle.colors.textSecondary
            z: 2
        }
    }

    // Focus indicator
    Rectangle {
        anchors.fill: parent
        anchors.margins: -EmbryStyle.layout.focusRingWidth
        radius: EmbryStyle.layout.radiusSm + EmbryStyle.layout.focusRingWidth
        color: "transparent"
        border.width: root.activeFocus ? EmbryStyle.layout.focusRingWidth : 0
        border.color: EmbryStyle.colors.accent
    }
}
