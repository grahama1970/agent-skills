import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// ClassifierLabApp -- tabbed window for classifier training, benchmarking,
// evaluation, ensemble creation, and model export.
// Groups: Training (Train, Benchmark) | Analysis (Evaluate, Ensemble, Export)

ApplicationWindow {
    id: appWindow

    width: 1060
    height: 700
    minimumWidth: 860
    minimumHeight: 540
    visible: true
    title: "Classifier Lab"
    color: EmbryStyle.colors.bg

    property int activeTab: 0
    property bool reduceMotion: false

    // Model count + training status from bridge
    property int modelCount: {
        try {
            var list = JSON.parse(classifierBridge.benchmarkResultJson || "[]")
            return list.length
        } catch (e) { return 0 }
    }
    property string trainStatus: classifierBridge.trainingStatus || "idle"

    readonly property var tabDefs: [
        { id: "train",     label: "Train",     group: "training",  groupColor: EmbryStyle.colors.accentGreen, shortcut: "1" },
        { id: "benchmark", label: "Benchmark", group: "training",  groupColor: EmbryStyle.colors.accentGreen, shortcut: "2" },
        { id: "evaluate",  label: "Evaluate",  group: "analysis",  groupColor: EmbryStyle.colors.accent, shortcut: "3" },
        { id: "ensemble",  label: "Ensemble",  group: "analysis",  groupColor: EmbryStyle.colors.accent, shortcut: "4" },
        { id: "export",    label: "Export",     group: "analysis",  groupColor: EmbryStyle.colors.accent, shortcut: "5" },
    ]

    Component.onCompleted: classifierBridge.refresh()

    // Tab switching shortcuts
    Shortcut { sequence: "1"; onActivated: activeTab = 0 }
    Shortcut { sequence: "2"; onActivated: activeTab = 1 }
    Shortcut { sequence: "3"; onActivated: activeTab = 2 }
    Shortcut { sequence: "4"; onActivated: activeTab = 3 }
    Shortcut { sequence: "5"; onActivated: activeTab = 4 }
    Shortcut { sequence: "Ctrl+R"; onActivated: classifierBridge.refresh() }
    Shortcut { sequence: "Ctrl+="; onActivated: EmbryStyle.scaleUp() }
    Shortcut { sequence: "Ctrl+-"; onActivated: EmbryStyle.scaleDown() }
    Shortcut { sequence: "Ctrl+0"; onActivated: EmbryStyle.scaleReset() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // -- Header Bar ---------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            height: 44
            color: EmbryStyle.colors.bgElevated

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space4
                anchors.rightMargin: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space3

                // Embry logo badge
                Rectangle {
                    width: 24; height: 24
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
                    text: "Classifier Lab"
                    font.pixelSize: EmbryStyle.text.lg
                    font.weight: EmbryStyle.text.weightBold
                    color: EmbryStyle.colors.textPrimary
                }

                // Model count badge
                Rectangle {
                    visible: modelCount > 0
                    width: modelBadgeText.implicitWidth + EmbryStyle.layout.space3 * 2
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.statusInfoBg

                    Text {
                        id: modelBadgeText
                        anchors.centerIn: parent
                        text: modelCount + " model" + (modelCount !== 1 ? "s" : "")
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightSemibold
                        color: EmbryStyle.colors.accent
                    }
                }

                Item { Layout.fillWidth: true }

                // Training status badge
                Rectangle {
                    width: statusText.implicitWidth + EmbryStyle.layout.space3 * 2
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: trainStatus === "training"
                        ? EmbryStyle.colors.statusOkBg
                        : trainStatus === "error"
                            ? EmbryStyle.colors.statusCriticalBg
                            : EmbryStyle.colors.badge

                    Accessible.name: "Training status: " + trainStatus
                    Accessible.role: Accessible.StaticText

                    Text {
                        id: statusText
                        anchors.centerIn: parent
                        text: trainStatus
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightBold
                        font.capitalization: Font.AllUppercase
                        color: trainStatus === "training"
                            ? EmbryStyle.colors.accentGreen
                            : trainStatus === "error"
                                ? EmbryStyle.colors.accentRed
                                : EmbryStyle.colors.textMuted
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

        // -- Grouped Tab Bar ----------------------------------------------
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
                    model: 2

                    RowLayout {
                        spacing: EmbryStyle.layout.space1

                        property int groupOffset: index === 0 ? 0 : 2
                        property int groupCount: index === 0 ? 2 : 3
                        property string groupLabel: index === 0 ? "Training" : "Analysis"
                        property color groupColor: index === 0 ? EmbryStyle.colors.accentGreen : EmbryStyle.colors.accent

                        Text {
                            text: groupLabel + " " + EmbryStyle.icons.chevronRight
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightMedium
                            color: groupColor
                            opacity: 0.7
                        }

                        Repeater {
                            model: groupCount

                            Rectangle {
                                property int tabIdx: groupOffset + index

                                width: tabLabel.implicitWidth + 16
                                height: 28
                                radius: EmbryStyle.layout.radiusSm
                                color: activeTab === tabIdx
                                    ? EmbryStyle.colors.selectBg
                                    : tabBtnMa.containsMouse
                                        ? EmbryStyle.colors.badgeHover
                                        : "transparent"
                                border.width: activeTab === tabIdx || activeFocus ? 1 : 0
                                border.color: activeFocus ? EmbryStyle.colors.selectBorder : parent.groupColor

                                Accessible.name: "[" + tabDefs[tabIdx].shortcut + "] " + tabDefs[tabIdx].label
                                Accessible.role: Accessible.PageTab

                                Text {
                                    id: tabLabel
                                    anchors.centerIn: parent
                                    text: "[" + tabDefs[tabIdx].shortcut + "] " + tabDefs[tabIdx].label
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.weight: activeTab === tabIdx
                                        ? EmbryStyle.text.weightSemibold
                                        : EmbryStyle.text.weightNormal
                                    color: activeTab === tabIdx
                                        ? EmbryStyle.colors.textPrimary
                                        : EmbryStyle.colors.textMuted
                                }

                                MouseArea {
                                    id: tabBtnMa
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

        // -- Tab Content (StackLayout) ------------------------------------
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: activeTab

            TrainPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            BenchmarkPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            EvaluatePage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            EnsemblePage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            ExportPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
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
        target: classifierBridge
        function onErrorOccurred(msg) {
            errorText.text = msg
            errorToast.visible = true
            errorTimer.restart()
        }
    }
}
