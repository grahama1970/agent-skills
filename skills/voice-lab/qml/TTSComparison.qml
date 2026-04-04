import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import VoiceLab 1.0
import "."

// TTS A/B Comparison panel — synthesize same text with Kokoro vs Voice Daemon,
// compare waveforms side by side, play each independently

Item {
    id: root

    required property var guiBridge
    property bool reduceMotion: false

    implicitWidth: 400
    implicitHeight: 400

    Accessible.name: "TTS comparison panel"
    Accessible.role: Accessible.Pane

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // ── Header ───────────────────────────────────────────
        Text {
            text: "TTS A/B Comparison"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
            Layout.fillWidth: true
        }

        // ── Text Input ───────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: textInput.implicitHeight + EmbryStyle.layout.space4
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgInput
            border.width: textInput.activeFocus ? EmbryStyle.layout.focusRingWidth : 1
            border.color: textInput.activeFocus ? EmbryStyle.colors.accent : EmbryStyle.colors.borderInput

            TextEdit {
                id: textInput
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space2
                wrapMode: TextEdit.Wrap
                font.pixelSize: EmbryStyle.text.base
                color: EmbryStyle.colors.textPrimary
                selectionColor: EmbryStyle.colors.accent
                selectedTextColor: "#000000"
                text: "The quick brown fox jumps over the lazy dog."

                Accessible.name: "Text to synthesize"
                Accessible.role: Accessible.EditableText

                // Placeholder
                Text {
                    anchors.fill: parent
                    text: "Enter text to synthesize..."
                    font: textInput.font
                    color: EmbryStyle.colors.textPlaceholder
                    visible: textInput.text.length === 0
                }
            }
        }

        // ── Synthesize Button ────────────────────────────────
        Rectangle {
            id: synthButton
            Layout.fillWidth: true
            height: 36
            radius: EmbryStyle.layout.radiusMd
            color: synthMa.pressed ? EmbryStyle.colors.bgPressed
                 : synthMa.containsMouse ? EmbryStyle.colors.bgHover
                 : EmbryStyle.colors.accent
            opacity: guiBridge.ttsBusy ? 0.5 : 1.0

            Accessible.name: guiBridge.ttsBusy ? "Synthesizing" : "Synthesize both"
            Accessible.role: Accessible.Button

            Text {
                anchors.centerIn: parent
                text: guiBridge.ttsBusy ? "Synthesizing..." : "Synthesize Both"
                font.pixelSize: EmbryStyle.text.base
                font.weight: EmbryStyle.text.weightSemibold
                color: guiBridge.ttsBusy ? EmbryStyle.colors.textMuted : "#000000"
            }

            MouseArea {
                id: synthMa
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                enabled: !guiBridge.ttsBusy
                onClicked: guiBridge.synthesizeBoth(textInput.text)
            }

            // Focus indicator
            Rectangle {
                anchors.fill: parent
                anchors.margins: -EmbryStyle.layout.focusRingWidth
                radius: parent.radius + EmbryStyle.layout.focusRingWidth
                color: "transparent"
                border.width: synthButton.activeFocus ? EmbryStyle.layout.focusRingWidth : 0
                border.color: EmbryStyle.colors.accent
            }

            Behavior on color {
                enabled: !root.reduceMotion
                ColorAnimation { duration: EmbryStyle.anim.fast }
            }
        }

        // ── Waveform A: Kokoro ───────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space1

            RowLayout {
                Layout.fillWidth: true
                spacing: EmbryStyle.layout.space2

                Rectangle {
                    width: labelA.implicitWidth + EmbryStyle.layout.badgePadding * 2
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.badge

                    Text {
                        id: labelA
                        anchors.centerIn: parent
                        text: "A  KOKORO"
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightMedium
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.accent
                    }
                }

                Item { Layout.fillWidth: true }

                // Play A button
                Rectangle {
                    width: 60
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: playAMa.containsMouse ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgElevated
                    visible: guiBridge.ttsPathA !== ""

                    Accessible.name: "Play Kokoro audio"
                    Accessible.role: Accessible.Button

                    Text {
                        anchors.centerIn: parent
                        text: "Play"
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightMedium
                        color: EmbryStyle.colors.accentGreen
                    }

                    MouseArea {
                        id: playAMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: guiBridge.play(guiBridge.ttsPathA)
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusSm
                color: EmbryStyle.colors.bg
                border.width: 1
                border.color: EmbryStyle.colors.border
                clip: true

                WaveformPainter {
                    id: waveA
                    anchors.fill: parent
                    peaks: guiBridge.ttsPeaksA
                    waveColor: "#664a9eff"  // accent blue at 40%
                }

                // Empty state
                Text {
                    anchors.centerIn: parent
                    text: "No audio"
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.textGhost
                    visible: guiBridge.ttsPeaksA.length === 0
                }
            }
        }

        // ── Waveform B: Voice Daemon ─────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space1

            RowLayout {
                Layout.fillWidth: true
                spacing: EmbryStyle.layout.space2

                Rectangle {
                    width: labelB.implicitWidth + EmbryStyle.layout.badgePadding * 2
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.badge

                    Text {
                        id: labelB
                        anchors.centerIn: parent
                        text: "B  VOICE DAEMON"
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightMedium
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.accentGreen
                    }
                }

                Item { Layout.fillWidth: true }

                // Play B button
                Rectangle {
                    width: 60
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: playBMa.containsMouse ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgElevated
                    visible: guiBridge.ttsPathB !== ""

                    Accessible.name: "Play voice daemon audio"
                    Accessible.role: Accessible.Button

                    Text {
                        anchors.centerIn: parent
                        text: "Play"
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightMedium
                        color: EmbryStyle.colors.accentGreen
                    }

                    MouseArea {
                        id: playBMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: guiBridge.play(guiBridge.ttsPathB)
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusSm
                color: EmbryStyle.colors.bg
                border.width: 1
                border.color: EmbryStyle.colors.border
                clip: true

                WaveformPainter {
                    id: waveB
                    anchors.fill: parent
                    peaks: guiBridge.ttsPeaksB
                    waveColor: "#6600ff88"  // accent green at 40%
                }

                // Empty state
                Text {
                    anchors.centerIn: parent
                    text: "No audio"
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.textGhost
                    visible: guiBridge.ttsPeaksB.length === 0
                }
            }
        }
    }
}
