import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Dashboard page — EmbryParticles + state test buttons + training status badges.
// Tab content for the Dashboard tab in VoiceLabApp.

Item {
    id: root

    required property var guiBridge
    property bool reduceMotion: false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // State test buttons row
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Text {
                text: "State"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            Repeater {
                model: ["idle", "listening", "thinking", "synthesizing", "speaking"]

                Rectangle {
                    width: stateText.implicitWidth + 12
                    height: 22
                    radius: EmbryStyle.layout.badgeRadius
                    color: guiBridge.embryState === modelData
                        ? EmbryStyle.colors.selectBg
                        : stateBtnMa.containsMouse
                            ? EmbryStyle.colors.badgeHover
                            : "transparent"
                    border.width: guiBridge.embryState === modelData ? 1 : 0
                    border.color: EmbryStyle.colors.accent

                    Accessible.name: "Set state to " + modelData
                    Accessible.role: Accessible.Button

                    Text {
                        id: stateText
                        anchors.centerIn: parent
                        text: modelData
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightMedium
                        font.capitalization: Font.AllUppercase
                        color: guiBridge.embryState === modelData
                            ? EmbryStyle.colors.accent
                            : EmbryStyle.colors.textMuted
                    }

                    MouseArea {
                        id: stateBtnMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: guiBridge.setEmbryState(modelData)
                    }
                }
            }

            Item { Layout.fillWidth: true }
        }

        // Main content: particles centered
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Item { Layout.fillWidth: true }

            ColumnLayout {
                Layout.alignment: Qt.AlignVCenter
                spacing: EmbryStyle.layout.space3

                EmbryParticles {
                    id: embryParticles
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 300
                    Layout.preferredHeight: 300
                    embryState: guiBridge.embryState
                    particleDataJson: guiBridge.particleDataJson
                    starsJson: guiBridge.starsJson
                    ringJson: guiBridge.ringJson
                    fontJson: guiBridge.fontJson
                    stateConfigsJson: guiBridge.stateConfigsJson
                    ringConfigsJson: guiBridge.ringConfigsJson
                    stateColorsJson: guiBridge.stateColorsJson
                    reduceMotion: root.reduceMotion
                }

                // State badge spacing
                Item { height: 30 }
            }

            Item { Layout.fillWidth: true }
        }

        // Training status badges row
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Text {
                text: "Training Status"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            Rectangle {
                width: kokoroLabel.implicitWidth + EmbryStyle.layout.badgePadding * 2
                height: EmbryStyle.layout.badgeHeight
                radius: EmbryStyle.layout.badgeRadius
                color: EmbryStyle.colors.badge

                Text {
                    id: kokoroLabel
                    anchors.centerIn: parent
                    text: "KOKORO  OK"
                    font.pixelSize: EmbryStyle.text.xs
                    font.weight: EmbryStyle.text.weightMedium
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.statusOk
                }
            }

            Rectangle {
                width: voiceLabel.implicitWidth + EmbryStyle.layout.badgePadding * 2
                height: EmbryStyle.layout.badgeHeight
                radius: EmbryStyle.layout.badgeRadius
                color: EmbryStyle.colors.badge

                Text {
                    id: voiceLabel
                    anchors.centerIn: parent
                    text: "VOICE DAEMON  OK"
                    font.pixelSize: EmbryStyle.text.xs
                    font.weight: EmbryStyle.text.weightMedium
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.statusOk
                }
            }

            Rectangle {
                width: rvcLabel.implicitWidth + EmbryStyle.layout.badgePadding * 2
                height: EmbryStyle.layout.badgeHeight
                radius: EmbryStyle.layout.badgeRadius
                color: EmbryStyle.colors.badge

                Text {
                    id: rvcLabel
                    anchors.centerIn: parent
                    text: "RVC  READY"
                    font.pixelSize: EmbryStyle.text.xs
                    font.weight: EmbryStyle.text.weightMedium
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.accent
                }
            }

            Item { Layout.fillWidth: true }
        }
    }
}
