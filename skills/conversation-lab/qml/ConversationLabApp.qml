import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: root

    width: EmbryStyle.layout.windowWidth
    height: EmbryStyle.layout.windowHeight
    minimumWidth: 780
    minimumHeight: 480
    visible: true
    title: "Conversation Lab"
    color: EmbryStyle.colors.bg

    // ── Properties ──────────────────────────────────────────
    property int activeTab: 0
    property var tabRegistry: bridge ? JSON.parse(bridge.tabRegistryJson) : {"groups": []}

    // ── Header ──────────────────────────────────────────────
    header: ToolBar {
        id: headerBar

        height: 48
        background: Rectangle {
            color: EmbryStyle.colors.bgElevated
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: EmbryStyle.colors.separator
            }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: EmbryStyle.layout.space4
            anchors.rightMargin: EmbryStyle.layout.space4
            spacing: EmbryStyle.layout.space3

            // Embry logo placeholder
            Rectangle {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28

                radius: 6
                color: EmbryStyle.colors.accentGreen
                opacity: 0.9

                Text {
                    anchors.centerIn: parent
                    text: "e"
                    font.pixelSize: 16
                    font.weight: Font.Bold
                    color: EmbryStyle.colors.bg
                }
            }

            Text {
                text: "Conversation Lab"
                font.pixelSize: EmbryStyle.text.lg
                font.weight: Font.SemiBold
                color: EmbryStyle.colors.textPrimary
            }

            Item { Layout.fillWidth: true }

            // Status badge
            Rectangle {
                Layout.preferredHeight: EmbryStyle.layout.badgeHeight
                Layout.preferredWidth: statusLabel.implicitWidth + EmbryStyle.layout.space4

                radius: EmbryStyle.layout.badgeRadius
                color: bridge && bridge.convergenceStatus === "converged"
                       ? EmbryStyle.colors.statusOkBg
                       : bridge && bridge.convergenceStatus === "running"
                         ? EmbryStyle.colors.statusInfoBg
                         : EmbryStyle.colors.badge

                Text {
                    id: statusLabel

                    anchors.centerIn: parent
                    text: bridge ? bridge.convergenceStatus.toUpperCase() : "IDLE"
                    font.pixelSize: EmbryStyle.text.xs
                    font.weight: Font.SemiBold
                    color: bridge && bridge.convergenceStatus === "converged"
                           ? EmbryStyle.colors.statusOk
                           : bridge && bridge.convergenceStatus === "running"
                             ? EmbryStyle.colors.statusInfo
                             : EmbryStyle.colors.textMuted
                }

                Accessible.name: "Convergence status"
                Accessible.role: Accessible.StaticText
                Accessible.description: "Current convergence status: " + (bridge ? bridge.convergenceStatus : "idle")
            }
        }
    }

    // ── Tab Bar ──────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Grouped tab bar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36

            color: EmbryStyle.colors.bg

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space4
                anchors.rightMargin: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space6

                Repeater {
                    model: tabRegistry.groups || []

                    RowLayout {
                        required property var modelData
                        required property int index

                        spacing: EmbryStyle.layout.space1

                        // Group label
                        Text {
                            text: modelData.label
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.SemiBold
                            color: modelData.color
                            opacity: 0.7

                            Layout.rightMargin: 2
                        }

                        Text {
                            text: "▸"
                            font.pixelSize: EmbryStyle.text.xs
                            color: EmbryStyle.colors.textGhost

                            Layout.rightMargin: 2
                        }

                        // Tab buttons within group
                        Repeater {
                            model: modelData.tabs || []

                            Rectangle {
                                required property var modelData
                                required property int index

                                // Compute global tab index
                                property int globalIndex: {
                                    var idx = 0;
                                    var groups = tabRegistry.groups || [];
                                    for (var g = 0; g < groups.length; g++) {
                                        if (g === parent.parent.index) {
                                            return idx + index;
                                        }
                                        idx += (groups[g].tabs || []).length;
                                    }
                                    return idx + index;
                                }
                                property bool isActive: root.activeTab === globalIndex
                                property bool isHovered: tabMa.containsMouse

                                Layout.preferredWidth: tabText.implicitWidth + EmbryStyle.layout.space4
                                Layout.preferredHeight: 28

                                radius: EmbryStyle.layout.radiusSm
                                color: isActive ? EmbryStyle.colors.selectBg
                                     : isHovered ? EmbryStyle.colors.badgeHover
                                     : "transparent"
                                border.width: isActive || activeFocus ? 1 : 0
                                border.color: activeFocus ? EmbryStyle.colors.selectBorder : parent.parent.modelData.color

                                Text {
                                    id: tabText

                                    anchors.centerIn: parent
                                    text: "[" + modelData.shortcut + "] " + modelData.label
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.weight: isActive ? Font.SemiBold : Font.Normal
                                    color: isActive ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textSecondary
                                }

                                MouseArea {
                                    id: tabMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.activeTab = globalIndex
                                }

                                Accessible.name: modelData.label + " tab"
                                Accessible.role: Accessible.PageTab
                                Accessible.description: "Switch to " + modelData.label + " tab. Shortcut: " + modelData.shortcut
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }
            }

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: EmbryStyle.colors.separator
            }
        }

        // ── Tab Content ──────────────────────────────────────
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true

            currentIndex: root.activeTab

            DiagnosePage {
                id: diagnosePage
                bridge: root.bridge
                opacity: StackLayout.isCurrentItem ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } }
            }

            SessionsPage {
                id: sessionsPage
                bridge: root.bridge
                opacity: StackLayout.isCurrentItem ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } }
            }

            ConvergePage {
                id: convergePage
                bridge: root.bridge
                opacity: StackLayout.isCurrentItem ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } }
            }

            PromotePage {
                id: promotePage
                bridge: root.bridge
                opacity: StackLayout.isCurrentItem ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } }
            }
        }
    }

    // ── Keyboard Shortcuts ──────────────────────────────────
    Shortcut { sequence: "1"; onActivated: root.activeTab = 0 }
    Shortcut { sequence: "2"; onActivated: root.activeTab = 1 }
    Shortcut { sequence: "3"; onActivated: root.activeTab = 2 }
    Shortcut { sequence: "4"; onActivated: root.activeTab = 3 }
    Shortcut { sequence: "Ctrl+R"; onActivated: if (bridge) bridge.refresh() }
    Shortcut { sequence: "Ctrl+="; onActivated: EmbryStyle.scaleUp() }
    Shortcut { sequence: "Ctrl+-"; onActivated: EmbryStyle.scaleDown() }
    Shortcut { sequence: "Ctrl+0"; onActivated: EmbryStyle.scaleReset() }

    // ── Bridge reference ─────────────────────────────────────
    property var bridge: null

    Component.onCompleted: {
        if (typeof convBridge !== "undefined") {
            root.bridge = convBridge;
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
        target: convBridge
        function onErrorOccurred(msg) {
            errorText.text = msg
            errorToast.visible = true
            errorTimer.restart()
        }
    }
}
