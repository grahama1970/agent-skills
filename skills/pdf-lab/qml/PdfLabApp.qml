import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: root

    width: 1024
    height: 680
    minimumWidth: 860
    minimumHeight: 540
    visible: true
    title: "PDF Lab"
    color: EmbryStyle.colors.bg

    property int activeTab: 0
    property var tabRegistry: pdfBridge ? JSON.parse(pdfBridge.tabRegistryJson) : {"groups": []}

    // ── Header ──────────────────────────────────────────────
    header: ToolBar {
        height: 48
        background: Rectangle {
            color: EmbryStyle.colors.bgElevated
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: EmbryStyle.colors.separator }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: EmbryStyle.layout.space4
            anchors.rightMargin: EmbryStyle.layout.space4
            spacing: EmbryStyle.layout.space3

            Rectangle {
                Layout.preferredWidth: 28; Layout.preferredHeight: 28
                radius: 6; color: EmbryStyle.colors.accentRed; opacity: 0.9
                Text { anchors.centerIn: parent; text: "e"; font.pixelSize: 16; font.weight: Font.Bold; color: EmbryStyle.colors.bg }
            }

            Text {
                text: "PDF Lab"
                font.pixelSize: EmbryStyle.text.lg; font.weight: Font.SemiBold
                color: EmbryStyle.colors.textPrimary
            }

            Item { Layout.fillWidth: true }

            // Current PDF name
            Text {
                text: pdfBridge ? pdfBridge.currentPdfName : "No PDF loaded"
                font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textMuted
                elide: Text.ElideMiddle
                Layout.maximumWidth: 300
            }

            // Tune status badge
            Rectangle {
                Layout.preferredHeight: EmbryStyle.layout.badgeHeight
                Layout.preferredWidth: tuneStatusText.implicitWidth + EmbryStyle.layout.space4
                radius: EmbryStyle.layout.badgeRadius
                color: {
                    var st = pdfBridge ? pdfBridge.tuneStatus : "idle";
                    if (st === "converged") return EmbryStyle.colors.statusOkBg;
                    if (st === "running") return EmbryStyle.colors.statusInfoBg;
                    return EmbryStyle.colors.badge;
                }
                Text {
                    id: tuneStatusText
                    anchors.centerIn: parent
                    text: pdfBridge ? pdfBridge.tuneStatus.toUpperCase() : "IDLE"
                    font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold
                    color: {
                        var st = pdfBridge ? pdfBridge.tuneStatus : "idle";
                        if (st === "converged") return EmbryStyle.colors.statusOk;
                        if (st === "running") return EmbryStyle.colors.statusInfo;
                        return EmbryStyle.colors.textMuted;
                    }
                }
                Accessible.name: "Tune status"; Accessible.role: Accessible.StaticText
            }
        }
    }

    // ── Tab Bar ──────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 36
            color: EmbryStyle.colors.bg

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space4
                anchors.rightMargin: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space6

                Repeater {
                    model: tabRegistry.groups || []
                    RowLayout {
                        required property var modelData; required property int index
                        spacing: EmbryStyle.layout.space1

                        Text { text: modelData.label; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.SemiBold; color: modelData.color; opacity: 0.7; Layout.rightMargin: 2 }
                        Text { text: "▸"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textGhost; Layout.rightMargin: 2 }

                        Repeater {
                            model: modelData.tabs || []
                            Rectangle {
                                required property var modelData; required property int index
                                property int globalIndex: {
                                    var idx = 0; var groups = tabRegistry.groups || [];
                                    for (var g = 0; g < groups.length; g++) {
                                        if (g === parent.parent.index) return idx + index;
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
                                    id: tabText; anchors.centerIn: parent
                                    text: "[" + modelData.shortcut + "] " + modelData.label
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.weight: isActive ? Font.SemiBold : Font.Normal
                                    color: isActive ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textSecondary
                                }
                                MouseArea { id: tabMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.activeTab = globalIndex }
                                Accessible.name: modelData.label + " tab"; Accessible.role: Accessible.PageTab
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: EmbryStyle.colors.separator }
        }

        // ── Tab Content ──────────────────────────────────────
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: root.activeTab

            TunePage { bridge: pdfBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            AnnotatePage { bridge: pdfBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            ParametersPage { bridge: pdfBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            QuestionsPage { bridge: pdfBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            HistoryPage { bridge: pdfBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
        }
    }

    // ── Shortcuts ────────────────────────────────────────────
    Shortcut { sequence: "1"; onActivated: root.activeTab = 0 }
    Shortcut { sequence: "2"; onActivated: root.activeTab = 1 }
    Shortcut { sequence: "3"; onActivated: root.activeTab = 2 }
    Shortcut { sequence: "4"; onActivated: root.activeTab = 3 }
    Shortcut { sequence: "5"; onActivated: root.activeTab = 4 }
    Shortcut { sequence: "Ctrl+R"; onActivated: if (pdfBridge) pdfBridge.refresh() }
    Shortcut { sequence: "Ctrl+="; onActivated: EmbryStyle.scaleUp() }
    Shortcut { sequence: "Ctrl+-"; onActivated: EmbryStyle.scaleDown() }
    Shortcut { sequence: "Ctrl+0"; onActivated: EmbryStyle.scaleReset() }

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
        target: pdfBridge
        function onErrorOccurred(msg) {
            errorText.text = msg
            errorToast.visible = true
            errorTimer.restart()
        }
    }
}
