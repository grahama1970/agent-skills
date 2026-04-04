import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// GptLabApp -- tabbed window for GPT model benchmarking and analysis.
// Groups: Models (Registry, Benchmark) | Analysis (Results, Profiler, Reports)
// Bridge: gptBridge (GptLabBridge)

ApplicationWindow {
    id: appWindow

    width: 1060
    height: 700
    minimumWidth: 860
    minimumHeight: 540
    visible: true
    title: "GPT Lab"
    color: EmbryStyle.colors.bg

    property int activeTab: 0
    property var registry: []

    Component.onCompleted: {
        gptBridge.refresh()
        try {
            registry = JSON.parse(gptBridge.registryJson)
        } catch (_) {
            registry = { candidate_models: [], api_models: [] }
        }
    }

    // Tab definitions (matches tab-registry.json)
    readonly property var tabDefs: [
        { id: "registry",  label: "Registry",  group: "models",   groupColor: EmbryStyle.colors.accentGreen, shortcut: "1" },
        { id: "benchmark", label: "Benchmark", group: "models",   groupColor: EmbryStyle.colors.accentGreen, shortcut: "2" },
        { id: "results",   label: "Results",   group: "analysis", groupColor: EmbryStyle.colors.accent,      shortcut: "3" },
        { id: "profiler",  label: "Profiler",  group: "analysis", groupColor: EmbryStyle.colors.accent,      shortcut: "4" },
        { id: "reports",   label: "Reports",   group: "analysis", groupColor: EmbryStyle.colors.accent,      shortcut: "5" }
    ]

    // Groups metadata
    readonly property var groupDefs: [
        { label: "Models",   color: EmbryStyle.colors.accentGreen, offset: 0, count: 2 },
        { label: "Analysis", color: EmbryStyle.colors.accent,      offset: 2, count: 3 }
    ]

    // Keyboard shortcuts
    Shortcut { sequence: "1"; onActivated: activeTab = 0 }
    Shortcut { sequence: "2"; onActivated: activeTab = 1 }
    Shortcut { sequence: "3"; onActivated: activeTab = 2 }
    Shortcut { sequence: "4"; onActivated: activeTab = 3 }
    Shortcut { sequence: "5"; onActivated: activeTab = 4 }
    Shortcut { sequence: "Ctrl+R"; onActivated: gptBridge.refresh() }
    Shortcut { sequence: "Ctrl+="; onActivated: EmbryStyle.scaleUp() }
    Shortcut { sequence: "Ctrl+-"; onActivated: EmbryStyle.scaleDown() }
    Shortcut { sequence: "Ctrl+0"; onActivated: EmbryStyle.scaleReset() }

    Connections {
        target: gptBridge
        function onRegistryJsonChanged() {
            try {
                appWindow.registry = JSON.parse(gptBridge.registryJson)
            } catch (_) {}
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // -- Header Bar --
        Rectangle {
            Layout.fillWidth: true
            height: 44
            color: EmbryStyle.colors.bgElevated

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space4
                anchors.rightMargin: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space3

                // Embry badge
                Rectangle {
                    width: 22
                    height: 22
                    radius: 6
                    color: EmbryStyle.colors.accentRedBg

                    Accessible.name: "Embry logo"
                    Accessible.role: Accessible.StaticText

                    Text {
                        anchors.centerIn: parent
                        text: "e"
                        font.pixelSize: EmbryStyle.text.base
                        font.weight: EmbryStyle.text.weightBold
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.accentRed
                    }
                }

                Text {
                    text: "GPT Lab"
                    font.pixelSize: EmbryStyle.text.lg
                    font.weight: EmbryStyle.text.weightBold
                    color: EmbryStyle.colors.textPrimary
                }

                // Model count badge
                Rectangle {
                    width: modelCountText.implicitWidth + EmbryStyle.layout.space4
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.statusOkBg

                    Accessible.name: "Model count"
                    Accessible.role: Accessible.StaticText

                    Text {
                        id: modelCountText
                        anchors.centerIn: parent
                        text: {
                            var r = appWindow.registry
                            var c = (r.candidate_models || []).length + (r.api_models || []).length
                            return c + " models"
                        }
                        font.pixelSize: EmbryStyle.text.sm
                        font.weight: EmbryStyle.text.weightBold
                        color: EmbryStyle.colors.accentGreen
                    }
                }

                Item { Layout.fillWidth: true }

                // Benchmark status badge
                Rectangle {
                    width: benchStatusText.implicitWidth + EmbryStyle.layout.space4
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: gptBridge.benchmarkStatus === "running"
                        ? EmbryStyle.colors.statusWarningBg
                        : EmbryStyle.colors.statusOkBg

                    Accessible.name: "Benchmark status"
                    Accessible.role: Accessible.StaticText

                    Text {
                        id: benchStatusText
                        anchors.centerIn: parent
                        text: gptBridge.benchmarkStatus || "idle"
                        font.pixelSize: EmbryStyle.text.sm
                        font.weight: EmbryStyle.text.weightBold
                        font.capitalization: Font.Capitalize
                        color: gptBridge.benchmarkStatus === "running"
                            ? EmbryStyle.colors.accentYellow
                            : EmbryStyle.colors.accentGreen
                    }
                }
            }

            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: EmbryStyle.colors.separator
            }
        }

        // -- Grouped Tab Bar --
        Rectangle {
            Layout.fillWidth: true
            height: 36
            color: EmbryStyle.colors.bg

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space4
                anchors.rightMargin: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space4

                Repeater {
                    model: groupDefs.length

                    RowLayout {
                        spacing: EmbryStyle.layout.space1
                        property var grp: groupDefs[index]

                        Text {
                            text: grp.label + " " + EmbryStyle.icons.chevronRight
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightMedium
                            color: grp.color
                            opacity: 0.7
                        }

                        Repeater {
                            model: grp.count
                            Rectangle {
                                property int tabIdx: grp.offset + index
                                width: tabLabel.implicitWidth + EmbryStyle.layout.space4
                                height: 28
                                radius: EmbryStyle.layout.radiusSm
                                color: activeTab === tabIdx
                                    ? EmbryStyle.colors.selectBg
                                    : tabMa.containsMouse ? EmbryStyle.colors.badgeHover : "transparent"
                                border.width: activeTab === tabIdx || activeFocus ? 1 : 0
                                border.color: activeFocus ? EmbryStyle.colors.selectBorder : grp.color

                                Accessible.name: tabDefs[tabIdx].label + " tab"
                                Accessible.role: Accessible.PageTab

                                Text {
                                    id: tabLabel
                                    anchors.centerIn: parent
                                    text: "[" + tabDefs[tabIdx].shortcut + "] " + tabDefs[tabIdx].label
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.weight: activeTab === tabIdx ? EmbryStyle.text.weightSemibold : EmbryStyle.text.weightNormal
                                    color: activeTab === tabIdx ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textMuted
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

            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: EmbryStyle.colors.separator
            }
        }

        // -- Tab Content --
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: activeTab

            RegistryPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            BenchmarkPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            ResultsPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            ProfilerPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            ReportsPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
        }
    }

    // Error toast
    Rectangle {
        id: errorToast
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: EmbryStyle.layout.space4
        width: errorText.implicitWidth + EmbryStyle.layout.space4 * 2
        height: errorText.implicitHeight + EmbryStyle.layout.space2 * 2
        radius: EmbryStyle.layout.radiusMd
        color: EmbryStyle.colors.statusCriticalBg
        border.color: EmbryStyle.colors.accentRed
        border.width: 1
        visible: false
        z: 100

        Text {
            id: errorText
            anchors.centerIn: parent
            color: EmbryStyle.colors.textPrimary
            font.pixelSize: EmbryStyle.text.sm
            font.family: EmbryStyle.text.monoFamily
        }

        Timer {
            id: errorTimer
            interval: 5000
            onTriggered: errorToast.visible = false
        }

        Accessible.name: "Error notification"
        Accessible.role: Accessible.AlertMessage
    }

    Connections {
        target: gptBridge
        function onErrorOccurred(msg) {
            errorText.text = msg
            errorToast.visible = true
            errorTimer.restart()
        }
    }
}
