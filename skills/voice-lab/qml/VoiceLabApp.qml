import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import VoiceLab 1.0
import "."

// VoiceLabApp — unified tabbed window for all voice-lab surfaces.
// Groups: Voice (Record, TTS Compare) | System (Dashboard, RVC Sweep)
// Two bridges coexist: editorBridge (VoiceLabBridge) + guiBridge (VoiceLabGuiBridge)

ApplicationWindow {
    id: appWindow
    width: 1000
    height: 660
    minimumWidth: 800
    minimumHeight: 500
    visible: true
    title: "Voice Lab"
    color: EmbryStyle.colors.bg

    property int activeTab: 0  // 0=Record, 1=TTS Compare, 2=Dashboard, 3=RVC Sweep
    property bool reduceMotion: false

    // Set initial tab from --tab argument (set by app.py via context property)
    property string initialTab: typeof startTab !== "undefined" ? startTab : "dashboard"

    Component.onCompleted: {
        guiBridge.initialize()
        // Resolve initial tab
        let tabMap = {"record": 0, "tts-compare": 1, "dashboard": 2, "rvc-sweep": 3}
        if (initialTab in tabMap) {
            activeTab = tabMap[initialTab]
        }
    }

    // Tab definitions (matches tab-registry.json)
    readonly property var tabDefs: [
        { id: "record",      label: "Record",      group: "voice",  groupColor: "#00ff88", shortcut: "1" },
        { id: "tts-compare", label: "TTS Compare", group: "voice",  groupColor: "#00ff88", shortcut: "2" },
        { id: "dashboard",   label: "Dashboard",   group: "system", groupColor: "#4a9eff", shortcut: "3" },
        { id: "rvc-sweep",   label: "RVC Sweep",   group: "system", groupColor: "#4a9eff", shortcut: "4" },
    ]

    // Tab switching shortcuts
    Shortcut { sequence: "1"; onActivated: activeTab = 0 }
    Shortcut { sequence: "2"; onActivated: activeTab = 1 }
    Shortcut { sequence: "3"; onActivated: activeTab = 2 }
    Shortcut { sequence: "4"; onActivated: activeTab = 3 }

    // Editor-specific shortcuts (only active on Record tab)
    Shortcut {
        sequence: "Space"
        enabled: activeTab === 0
        onActivated: {
            var ed = editorPage
            if (ed.player.playbackState === 1 /* PlayingState */) {
                ed.player.pause()
            } else {
                ed.player.play()
            }
        }
    }
    Shortcut {
        sequence: "R"
        enabled: activeTab === 0
        onActivated: {
            if (editorBridge.isRecording) {
                editorBridge.stopRecording()
                editorPage.player.pause()
            } else {
                editorBridge.setPhase("record")
                editorBridge.startCountdown()
            }
        }
    }
    Shortcut { sequence: "Ctrl+S"; enabled: activeTab === 0; onActivated: editorBridge.saveAlignment("") }
    Shortcut { sequence: "Ctrl+="; onActivated: EmbryStyle.scaleUp() }
    Shortcut { sequence: "Ctrl+-"; onActivated: EmbryStyle.scaleDown() }
    Shortcut { sequence: "Ctrl+0"; onActivated: EmbryStyle.scaleReset() }
    Shortcut {
        sequence: "I"
        enabled: activeTab === 0
        onActivated: {
            if (editorPage.player.duration > 0) {
                editorBridge.setInPoint(editorPage.player.position)
                editorPage.loopEnabled = true
                editorBridge.setPhase("set_io")
            }
        }
    }
    Shortcut {
        sequence: "O"
        enabled: activeTab === 0
        onActivated: {
            if (editorPage.player.duration > 0) {
                editorBridge.setOutPoint(editorPage.player.position)
                editorPage.loopEnabled = true
                editorBridge.setPhase("set_io")
            }
        }
    }
    Shortcut {
        sequence: "Escape"
        enabled: activeTab === 0
        onActivated: {
            editorBridge.clearIOPoints()
            editorPage.loopEnabled = false
            editorBridge.setPhase("browse")
        }
    }
    Shortcut {
        sequence: "Left"
        enabled: activeTab === 0
        onActivated: {
            if (editorPage.selectedSegment > 0) editorPage.selectedSegment--
            editorPage.seekToSegment(editorPage.selectedSegment)
        }
    }
    Shortcut {
        sequence: "Right"
        enabled: activeTab === 0
        onActivated: {
            if (editorPage.selectedSegment < editorBridge.segmentModel.rowCount() - 1) editorPage.selectedSegment++
            editorPage.seekToSegment(editorPage.selectedSegment)
        }
    }
    Shortcut {
        sequence: "P"
        enabled: activeTab === 0
        onActivated: editorPage.playSegment(editorPage.selectedSegment)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Header Bar ─────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 44
            color: EmbryStyle.colors.bgElevated

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space4
                anchors.rightMargin: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space3

                // Embry logo
                Text {
                    text: "[e]"
                    font.pixelSize: EmbryStyle.text.base
                    font.weight: EmbryStyle.text.weightBold
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.accent
                }

                Text {
                    text: "Embry"
                    font.pixelSize: EmbryStyle.text.lg
                    font.weight: EmbryStyle.text.weightBold
                    color: EmbryStyle.colors.accent
                }

                Text {
                    text: "Voice Lab"
                    font.pixelSize: EmbryStyle.text.base
                    font.weight: EmbryStyle.text.weightNormal
                    color: EmbryStyle.colors.textMuted
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
                            text: guiBridge.persona
                            font.pixelSize: EmbryStyle.text.sm
                            font.weight: EmbryStyle.text.weightMedium
                            color: EmbryStyle.colors.textPrimary
                            font.capitalization: Font.Capitalize
                        }

                        Text {
                            text: "\u25BE"
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
                            model: guiBridge.personaList
                            MenuItem {
                                text: modelData
                                onTriggered: guiBridge.setPersona(modelData)
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

        // ── Grouped Tab Bar ────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 36
            color: EmbryStyle.colors.bg

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space4
                anchors.rightMargin: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space4

                // Render tab groups
                Repeater {
                    model: 2  // two groups

                    RowLayout {
                        spacing: EmbryStyle.layout.space1

                        property int groupOffset: index === 0 ? 0 : 2
                        property int groupCount: 2
                        property string groupLabel: index === 0 ? "Voice" : "System"
                        property string groupColor: index === 0 ? "#00ff88" : "#4a9eff"

                        // Group label
                        Text {
                            text: groupLabel + " " + EmbryStyle.icons.chevronRight
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightMedium
                            color: groupColor
                            opacity: 0.7
                        }

                        // Tabs within group
                        Repeater {
                            model: groupCount
                            Rectangle {
                                property int tabIdx: groupOffset + index
                                width: tabText.implicitWidth + 16
                                height: 26
                                radius: EmbryStyle.layout.radiusSm
                                color: activeTab === tabIdx
                                    ? EmbryStyle.colors.selectBg
                                    : tabMa.containsMouse
                                        ? EmbryStyle.colors.badgeHover
                                        : "transparent"
                                border.width: activeTab === tabIdx ? 1 : 0
                                border.color: parent.groupColor

                                Text {
                                    id: tabText
                                    anchors.centerIn: parent
                                    text: tabDefs[tabIdx].label
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.weight: activeTab === tabIdx ? EmbryStyle.text.weightSemibold : EmbryStyle.text.weightNormal
                                    color: activeTab === tabIdx ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textMuted
                                }

                                // Shortcut badge
                                Text {
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 2
                                    text: tabDefs[tabIdx].shortcut
                                    font.pixelSize: 8
                                    font.family: EmbryStyle.text.monoFamily
                                    color: EmbryStyle.colors.textGhost
                                    visible: activeTab !== tabIdx
                                }

                                MouseArea {
                                    id: tabMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: activeTab = tabIdx
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }
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

        // ── Tab Content (StackLayout) ──────────────────────────
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: activeTab

            // Tab 0: Record (Editor)
            Editor {
                id: editorPage
                editorBridge: appWindow.editorBridge
            }

            // Tab 1: TTS Compare
            TTSComparison {
                guiBridge: appWindow.guiBridge
                reduceMotion: appWindow.reduceMotion
            }

            // Tab 2: Dashboard
            DashboardPage {
                guiBridge: appWindow.guiBridge
                reduceMotion: appWindow.reduceMotion
            }

            // Tab 3: RVC Sweep
            RVCSweepStub {}
        }

        // ── MicMeter (shared, always visible) ──────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: EmbryStyle.colors.separator
        }

        MicMeter {
            Layout.fillWidth: true
            Layout.margins: EmbryStyle.layout.space3
            level: guiBridge.micLevel
            reduceMotion: appWindow.reduceMotion
        }
    }
}
