import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// RVC Sweep results placeholder — future tab for sweep results, ranked params, presets.

Item {
    id: root

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        Text {
            text: "RVC Sweep"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        Text {
            text: "Parameter sweep results, ranked configurations, and presets will appear here."
            font.pixelSize: EmbryStyle.text.base
            color: EmbryStyle.colors.textMuted
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Text {
            text: "Run:  ./run.sh sweep --persona embry --track hawaiian_war_chant"
            font.pixelSize: EmbryStyle.text.sm
            font.family: EmbryStyle.text.monoFamily
            color: EmbryStyle.colors.textGhost
            Layout.fillWidth: true
        }

        Item { Layout.fillHeight: true }
    }
}
