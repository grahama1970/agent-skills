import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// RegressorLabApp -- unified tabbed window for regression model development.
// Groups: Training (Data, Benchmark) | Analysis (Results, Tune, Deploy)
// Bridge: regressorBridge (RegressorLabBridge)

ApplicationWindow {
    id: appWindow

    property int activeTab: typeof startTabIndex !== "undefined" ? startTabIndex : 0
    property bool reduceMotion: false
    property var registryData: JSON.parse(regressorBridge.tabRegistryJson || "{}")
    property var tabDefs: _buildTabDefs()

    width: 1060
    height: 700
    minimumWidth: 860
    minimumHeight: 540
    visible: true
    title: "Regressor Lab"
    color: EmbryStyle.colors.bg

    function _buildTabDefs() {
        var defs = []
        var groups = registryData.groups || []
        for (var g = 0; g < groups.length; g++) {
            var grp = groups[g]
            var tabs = grp.tabs || []
            for (var t = 0; t < tabs.length; t++) {
                defs.push({
                    id: tabs[t].id,
                    label: tabs[t].label,
                    group: grp.id,
                    groupLabel: grp.label,
                    groupColor: grp.color,
                    shortcut: tabs[t].shortcut
                })
            }
        }
        return defs
    }

    Component.onCompleted: {
        regressorBridge.refresh()
    }

    // Tab switching shortcuts 1-5
    Shortcut { sequence: "1"; onActivated: activeTab = 0 }
    Shortcut { sequence: "2"; onActivated: activeTab = 1 }
    Shortcut { sequence: "3"; onActivated: activeTab = 2 }
    Shortcut { sequence: "4"; onActivated: activeTab = 3 }
    Shortcut { sequence: "5"; onActivated: activeTab = 4 }
    Shortcut { sequence: "Ctrl+R"; onActivated: regressorBridge.refresh() }
    Shortcut { sequence: "Ctrl+="; onActivated: EmbryStyle.scaleUp() }
    Shortcut { sequence: "Ctrl+-"; onActivated: EmbryStyle.scaleDown() }
    Shortcut { sequence: "Ctrl+0"; onActivated: EmbryStyle.scaleReset() }

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

                // Embry logo badge
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
                        font.pixelSize: EmbryStyle.text.sm
                        font.weight: EmbryStyle.text.weightBold
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.accentRed
                    }
                }

                Text {
                    text: "Regressor Lab"
                    font.pixelSize: EmbryStyle.text.lg
                    font.weight: EmbryStyle.text.weightBold
                    color: EmbryStyle.colors.textPrimary
                }

                // Model count badge
                Rectangle {
                    visible: _modelCount() > 0
                    width: modelCountText.implicitWidth + EmbryStyle.layout.badgePadding * 2
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.badge

                    Accessible.name: _modelCount() + " models"
                    Accessible.role: Accessible.StaticText

                    Text {
                        id: modelCountText
                        anchors.centerIn: parent
                        text: _modelCount() + " models"
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightMedium
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textSecondary
                    }
                }

                Item { Layout.fillWidth: true }

                // Training status badge
                Rectangle {
                    width: statusText.implicitWidth + EmbryStyle.layout.badgePadding * 2
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.badge

                    Accessible.name: "Training status: " + (regressorBridge.trainingStatus || "idle")
                    Accessible.role: Accessible.StaticText

                    Text {
                        id: statusText
                        anchors.centerIn: parent
                        text: (regressorBridge.trainingStatus || "IDLE").toUpperCase()
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightMedium
                        font.family: EmbryStyle.text.monoFamily
                        color: regressorBridge.trainingStatus === "training"
                            ? EmbryStyle.colors.accentYellow
                            : regressorBridge.trainingStatus === "complete"
                                ? EmbryStyle.colors.statusOk
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
                    model: registryData.groups || []

                    RowLayout {
                        spacing: EmbryStyle.layout.space1

                        property var grp: modelData
                        property int groupOffset: _groupOffset(index)

                        Text {
                            text: (grp.label || "") + " " + EmbryStyle.icons.chevronRight
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightMedium
                            color: grp.color || EmbryStyle.colors.textMuted
                            opacity: 0.7
                        }

                        Repeater {
                            model: grp.tabs || []

                            Rectangle {
                                property int tabIdx: groupOffset + index

                                width: tabLabel.implicitWidth + EmbryStyle.layout.space4
                                height: 28
                                radius: EmbryStyle.layout.radiusSm
                                color: activeTab === tabIdx
                                    ? EmbryStyle.colors.selectBg
                                    : tabMouseArea.containsMouse
                                        ? EmbryStyle.colors.badgeHover
                                        : "transparent"
                                border.width: activeTab === tabIdx || activeFocus ? 1 : 0
                                border.color: activeFocus ? EmbryStyle.colors.selectBorder : grp.color || EmbryStyle.colors.accent

                                Accessible.name: "[" + (modelData.shortcut || "") + "] " + (modelData.label || "")
                                Accessible.role: Accessible.PageTab

                                Text {
                                    id: tabLabel
                                    anchors.centerIn: parent
                                    text: "[" + (modelData.shortcut || "") + "] " + (modelData.label || "")
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.weight: activeTab === tabIdx
                                        ? EmbryStyle.text.weightSemibold
                                        : EmbryStyle.text.weightNormal
                                    color: activeTab === tabIdx
                                        ? EmbryStyle.colors.textPrimary
                                        : EmbryStyle.colors.textMuted
                                }

                                MouseArea {
                                    id: tabMouseArea
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

        // -- Tab Content (StackLayout) --
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: activeTab

            DataPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            BenchmarkPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            ResultsPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            TunePage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            DeployPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
        }
    }

    function _groupOffset(groupIndex) {
        var offset = 0
        var groups = registryData.groups || []
        for (var i = 0; i < groupIndex; i++) {
            offset += (groups[i].tabs || []).length
        }
        return offset
    }

    function _modelCount() {
        try {
            var data = JSON.parse(regressorBridge.benchmarkResultJson || "{}");
            var results = data.results || []
            return results.length
        } catch (e) {
            return 0
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
        target: regressorBridge
        function onErrorOccurred(msg) {
            errorText.text = msg
            errorToast.visible = true
            errorTimer.restart()
        }
    }
}
