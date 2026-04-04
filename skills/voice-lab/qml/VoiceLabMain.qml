import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "."

// Voice Lab — KDE debug/testing utility for Embry voice system
// Two-column layout: EmbryParticles (left) + TTSComparison (right) + MicMeter (bottom)

Window {
    id: window
    width: EmbryStyle.layout.windowWidth
    height: EmbryStyle.layout.windowHeight
    minimumWidth: 700
    minimumHeight: 400
    visible: true
    title: "Voice Lab"
    color: EmbryStyle.colors.bg

    // Accessibility: reduce motion preference
    property bool reduceMotion: false

    Component.onCompleted: {
        bridge.initialize();
    }

    // ── State test buttons (debug row along top) ─────────────
    // Allows clicking through states without D-Bus

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 0
        spacing: 0

        // ── Title Bar ────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 44
            color: EmbryStyle.colors.bgElevated

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space4
                anchors.rightMargin: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space3

                // Embry logo text
                Text {
                    text: "Embry"
                    font.pixelSize: EmbryStyle.text.lg
                    font.weight: EmbryStyle.text.weightBold
                    color: EmbryStyle.colors.accent

                    Accessible.name: "Embry Voice Lab"
                    Accessible.role: Accessible.StaticText
                }

                Text {
                    text: "Voice Lab"
                    font.pixelSize: EmbryStyle.text.base
                    font.weight: EmbryStyle.text.weightNormal
                    color: EmbryStyle.colors.textMuted
                }

                // State test buttons
                Row {
                    spacing: EmbryStyle.layout.space1

                    Repeater {
                        model: ["idle", "listening", "thinking", "synthesizing", "speaking"]

                        Rectangle {
                            width: stateText.implicitWidth + 12
                            height: 22
                            radius: EmbryStyle.layout.badgeRadius
                            color: bridge.embryState === modelData
                                ? EmbryStyle.colors.selectBg
                                : stateBtnMa.containsMouse
                                    ? EmbryStyle.colors.badgeHover
                                    : "transparent"
                            border.width: bridge.embryState === modelData ? 1 : 0
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
                                color: bridge.embryState === modelData
                                    ? EmbryStyle.colors.accent
                                    : EmbryStyle.colors.textMuted
                            }

                            MouseArea {
                                id: stateBtnMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: bridge.setEmbryState(modelData)
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                // Persona dropdown
                Rectangle {
                    width: personaRow.implicitWidth + EmbryStyle.layout.space4
                    height: 28
                    radius: EmbryStyle.layout.radiusSm
                    color: personaDropMa.containsMouse ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput
                    border.width: 1
                    border.color: EmbryStyle.colors.borderInput

                    Accessible.name: "Select persona"
                    Accessible.role: Accessible.ComboBox

                    Row {
                        id: personaRow
                        anchors.centerIn: parent
                        spacing: EmbryStyle.layout.space1

                        Text {
                            text: bridge.persona
                            font.pixelSize: EmbryStyle.text.sm
                            font.weight: EmbryStyle.text.weightMedium
                            color: EmbryStyle.colors.textPrimary
                            font.capitalization: Font.Capitalize
                        }

                        Text {
                            text: "\u25BE"  // down triangle
                            font.pixelSize: EmbryStyle.text.xs
                            color: EmbryStyle.colors.textMuted
                        }
                    }

                    MouseArea {
                        id: personaDropMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: personaMenu.open()
                    }

                    Menu {
                        id: personaMenu
                        y: parent.height + 4

                        Repeater {
                            model: bridge.personaList
                            MenuItem {
                                text: modelData
                                onTriggered: bridge.setPersona(modelData)
                            }
                        }
                    }
                }
            }

            // Bottom separator
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: EmbryStyle.colors.separator
            }
        }

        // ── Main Content ─────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Left column: Embry Particles
            Rectangle {
                Layout.preferredWidth: 280
                Layout.fillHeight: true
                color: "transparent"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space4
                    spacing: EmbryStyle.layout.space3

                    Item { Layout.fillHeight: true }

                    EmbryParticles {
                        id: embryParticles
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 256
                        Layout.preferredHeight: 256
                        embryState: bridge.embryState
                        particleDataJson: bridge.particleDataJson
                        starsJson: bridge.starsJson
                        ringJson: bridge.ringJson
                        fontJson: bridge.fontJson
                        stateConfigsJson: bridge.stateConfigsJson
                        ringConfigsJson: bridge.ringConfigsJson
                        stateColorsJson: bridge.stateColorsJson
                        reduceMotion: window.reduceMotion
                    }

                    // Extra space for the state badge below the canvas
                    Item { height: 30 }

                    Item { Layout.fillHeight: true }
                }

                // Right separator
                Rectangle {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 1
                    color: EmbryStyle.colors.separator
                }
            }

            // Right column: TTS Comparison
            TTSComparison {
                Layout.fillWidth: true
                Layout.fillHeight: true
                reduceMotion: window.reduceMotion
            }
        }

        // ── Mic Meter (full width bottom) ────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: EmbryStyle.colors.separator
        }

        MicMeter {
            Layout.fillWidth: true
            Layout.margins: EmbryStyle.layout.space3
            level: bridge.micLevel
            reduceMotion: window.reduceMotion
        }
    }

    // ── Keyboard shortcuts ───────────────────────────────────
    Shortcut {
        sequence: "Escape"
        onActivated: window.close()
    }

    // Tab focus cycling handled by Qt's built-in tab order
}
