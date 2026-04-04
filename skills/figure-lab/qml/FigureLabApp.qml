import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// FigureLabApp -- tabbed window for D3 visualization composition & quality.
// Groups: Composition (Composer, Gallery) | Quality (Evaluate, Promote)
// Bridge: figureBridge (FigureLabBridge)

ApplicationWindow {
    id: appWindow

    width: 1060
    height: 700
    minimumWidth: 860
    minimumHeight: 540
    visible: true
    title: "Figure Lab"
    color: EmbryStyle.colors.bg

    property int activeTab: 0
    property int compositionCount: 0
    property bool promoteReady: false

    // Tab definitions (matches tab-registry.json)
    readonly property var tabDefs: [
        { id: "composer", label: "Composer",  group: "composition", groupColor: EmbryStyle.colors.accentGreen, shortcut: "1" },
        { id: "gallery",  label: "Gallery",   group: "composition", groupColor: EmbryStyle.colors.accentGreen, shortcut: "2" },
        { id: "evaluate", label: "Evaluate",  group: "quality",     groupColor: EmbryStyle.colors.accent, shortcut: "3" },
        { id: "promote",  label: "Promote",   group: "quality",     groupColor: EmbryStyle.colors.accent, shortcut: "4" }
    ]

    Component.onCompleted: figureBridge.refresh()

    // Parse catalog status for header badges
    Connections {
        target: figureBridge
        function onCatalogStatusJsonChanged() {
            try {
                var s = JSON.parse(figureBridge.catalogStatusJson)
                compositionCount = s.total || 0
                promoteReady = (s.pending || 0) > 0
            } catch (e) {}
        }
    }

    // Shortcuts
    Shortcut { sequence: "1"; onActivated: activeTab = 0 }
    Shortcut { sequence: "2"; onActivated: activeTab = 1 }
    Shortcut { sequence: "3"; onActivated: activeTab = 2 }
    Shortcut { sequence: "4"; onActivated: activeTab = 3 }
    Shortcut { sequence: "Ctrl+R"; onActivated: figureBridge.refresh() }
    Shortcut { sequence: "Ctrl+="; onActivated: EmbryStyle.scaleUp() }
    Shortcut { sequence: "Ctrl+-"; onActivated: EmbryStyle.scaleDown() }
    Shortcut { sequence: "Ctrl+0"; onActivated: EmbryStyle.scaleReset() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // -- Header Bar -------------------------------------------------------
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
                    width: 22; height: 22
                    radius: 6
                    color: EmbryStyle.colors.accentRed

                    Text {
                        anchors.centerIn: parent
                        text: "e"
                        font.pixelSize: EmbryStyle.text.sm
                        font.weight: Font.Bold
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textPrimary
                    }
                }

                Text {
                    text: "Figure Lab"
                    font.pixelSize: EmbryStyle.text.lg
                    font.weight: Font.Bold
                    color: EmbryStyle.colors.textPrimary
                }

                // Composition count badge
                Rectangle {
                    width: countLabel.implicitWidth + EmbryStyle.layout.space3 * 2
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.statusOkBg

                    Text {
                        id: countLabel
                        anchors.centerIn: parent
                        text: compositionCount + " figs"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        color: EmbryStyle.colors.accentGreen
                    }
                }

                // Promote status badge
                Rectangle {
                    visible: promoteReady
                    width: promoteLabel.implicitWidth + EmbryStyle.layout.space3 * 2
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.statusWarningBg

                    Text {
                        id: promoteLabel
                        anchors.centerIn: parent
                        text: "pending"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        color: EmbryStyle.colors.accentAmber
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

        // -- Grouped Tab Bar --------------------------------------------------
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
                        property int groupCount: 2
                        property string groupLabel: index === 0 ? "Composition" : "Quality"
                        property color groupColor: index === 0 ? EmbryStyle.colors.accentGreen : EmbryStyle.colors.accent

                        Text {
                            text: groupLabel + " " + EmbryStyle.icons.chevronRight
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.Medium
                            color: groupColor
                            opacity: 0.7
                        }

                        Repeater {
                            model: groupCount

                            Rectangle {
                                property int tabIdx: groupOffset + index

                                width: tabBtnText.implicitWidth + EmbryStyle.layout.space4
                                height: 28
                                radius: EmbryStyle.layout.radiusSm
                                color: activeTab === tabIdx
                                    ? EmbryStyle.colors.selectBg
                                    : tabBtnMa.containsMouse ? EmbryStyle.colors.badgeHover : "transparent"
                                border.width: activeTab === tabIdx || activeFocus ? 1 : 0
                                border.color: activeFocus ? EmbryStyle.colors.selectBorder : parent.groupColor

                                Accessible.name: "[" + tabDefs[tabIdx].shortcut + "] " + tabDefs[tabIdx].label
                                Accessible.role: Accessible.PageTab

                                Text {
                                    id: tabBtnText
                                    anchors.centerIn: parent
                                    text: "[" + tabDefs[tabIdx].shortcut + "] " + tabDefs[tabIdx].label
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.weight: activeTab === tabIdx ? Font.SemiBold : Font.Normal
                                    color: activeTab === tabIdx ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textMuted
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

        // -- Tab Content (StackLayout) ----------------------------------------
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: activeTab

            ComposerPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            GalleryPage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            EvaluatePage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            PromotePage { opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
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
        target: figureBridge
        function onErrorOccurred(msg) {
            errorText.text = msg
            errorToast.visible = true
            errorTimer.restart()
        }
    }
}
