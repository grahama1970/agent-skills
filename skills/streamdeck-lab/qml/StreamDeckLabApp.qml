import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// StreamDeckLabApp -- evaluate, generate, and manage Stream Deck layouts.
// Groups: Templates (Templates, Ground Truth) | Testing (Evaluate, Generator, Events)

ApplicationWindow {
    id: appWindow

    width: 1060
    height: 700
    minimumWidth: 860
    minimumHeight: 540
    visible: true
    title: "Stream Deck Lab"
    color: EmbryStyle.colors.bg

    property int activeTab: 0
    property var templateCount: deckBridge ? deckBridge.templatesJson : "[]"

    // Tab definitions (mirrors tab-registry.json)
    readonly property var tabDefs: [
        { id: "templates",    label: "Templates",    group: "templates", groupColor: EmbryStyle.colors.accentGreen, shortcut: "1" },
        { id: "ground-truth", label: "Ground Truth", group: "templates", groupColor: EmbryStyle.colors.accentGreen, shortcut: "2" },
        { id: "evaluate",     label: "Evaluate",     group: "testing",   groupColor: EmbryStyle.colors.accent, shortcut: "3" },
        { id: "generator",    label: "Generator",    group: "testing",   groupColor: EmbryStyle.colors.accent, shortcut: "4" },
        { id: "events",       label: "Events",       group: "testing",   groupColor: EmbryStyle.colors.accent, shortcut: "5" }
    ]

    Component.onCompleted: {
        if (deckBridge) deckBridge.refresh()
    }

    // Tab switching shortcuts
    Shortcut { sequence: "1"; onActivated: activeTab = 0 }
    Shortcut { sequence: "2"; onActivated: activeTab = 1 }
    Shortcut { sequence: "3"; onActivated: activeTab = 2 }
    Shortcut { sequence: "4"; onActivated: activeTab = 3 }
    Shortcut { sequence: "5"; onActivated: activeTab = 4 }
    Shortcut { sequence: "Ctrl+R"; onActivated: { if (deckBridge) deckBridge.refresh() } }
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

                    Accessible.name: "Embry logo"
                    Accessible.role: Accessible.StaticText
                }

                Text {
                    text: "Stream Deck Lab"
                    font.pixelSize: EmbryStyle.text.lg
                    font.weight: Font.Bold
                    color: EmbryStyle.colors.textPrimary
                }

                // Template count badge
                Rectangle {
                    width: tplCountText.implicitWidth + EmbryStyle.layout.space3
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.statusOkBg

                    Text {
                        id: tplCountText
                        anchors.centerIn: parent
                        text: {
                            try { return JSON.parse(templateCount).length + " templates" }
                            catch(e) { return "0 templates" }
                        }
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        color: EmbryStyle.colors.accentGreen
                    }

                    Accessible.name: "Template count"
                    Accessible.role: Accessible.StaticText
                }

                Item { Layout.fillWidth: true }

                // Eval status badge
                Rectangle {
                    width: evalStatusText.implicitWidth + EmbryStyle.layout.space3
                    height: EmbryStyle.layout.badgeHeight
                    radius: EmbryStyle.layout.badgeRadius
                    color: {
                        var s = deckBridge ? deckBridge.evalStatus : "idle"
                        if (s === "pass") return EmbryStyle.colors.statusOkBg
                        if (s === "fail") return EmbryStyle.colors.statusCriticalBg
                        if (s === "running") return EmbryStyle.colors.statusInfoBg
                        return EmbryStyle.colors.badge
                    }

                    Text {
                        id: evalStatusText
                        anchors.centerIn: parent
                        text: {
                            var s = deckBridge ? deckBridge.evalStatus : "idle"
                            return s.toUpperCase()
                        }
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        color: {
                            var s = deckBridge ? deckBridge.evalStatus : "idle"
                            if (s === "pass") return EmbryStyle.colors.statusOk
                            if (s === "fail") return EmbryStyle.colors.statusCritical
                            if (s === "running") return EmbryStyle.colors.statusInfo
                            return EmbryStyle.colors.textMuted
                        }
                    }

                    Accessible.name: "Evaluation status"
                    Accessible.role: Accessible.StaticText
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

                // Group: Templates
                RowLayout {
                    spacing: EmbryStyle.layout.space1
                    Text { text: "Templates " + EmbryStyle.icons.chevronRight; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Medium; color: EmbryStyle.colors.accentGreen; opacity: 0.7 }
                    Repeater {
                        model: 2
                        Rectangle {
                            property int tabIdx: index
                            width: tabLbl.implicitWidth + 16; height: 28
                            radius: EmbryStyle.layout.radiusSm
                            color: activeTab === tabIdx ? EmbryStyle.colors.selectBg : tabMa1.containsMouse ? EmbryStyle.colors.badgeHover : "transparent"
                            border.width: activeTab === tabIdx || activeFocus ? 1 : 0
                            border.color: activeFocus ? EmbryStyle.colors.selectBorder : EmbryStyle.colors.accentGreen
                            Text { id: tabLbl; anchors.centerIn: parent; text: "[" + tabDefs[tabIdx].shortcut + "] " + tabDefs[tabIdx].label; font.pixelSize: EmbryStyle.text.sm; font.weight: activeTab === tabIdx ? Font.SemiBold : Font.Normal; color: activeTab === tabIdx ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textMuted }
                            MouseArea { id: tabMa1; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: activeTab = tabIdx }
                            Accessible.name: tabDefs[tabIdx].label + " tab"; Accessible.role: Accessible.PageTab
                        }
                    }
                }

                // Group: Testing
                RowLayout {
                    spacing: EmbryStyle.layout.space1
                    Text { text: "Testing " + EmbryStyle.icons.chevronRight; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Medium; color: EmbryStyle.colors.accent; opacity: 0.7 }
                    Repeater {
                        model: 3
                        Rectangle {
                            property int tabIdx: index + 2
                            width: tabLbl2.implicitWidth + 16; height: 28
                            radius: EmbryStyle.layout.radiusSm
                            color: activeTab === tabIdx ? EmbryStyle.colors.selectBg : tabMa2.containsMouse ? EmbryStyle.colors.badgeHover : "transparent"
                            border.width: activeTab === tabIdx || activeFocus ? 1 : 0
                            border.color: activeFocus ? EmbryStyle.colors.selectBorder : EmbryStyle.colors.accent
                            Text { id: tabLbl2; anchors.centerIn: parent; text: "[" + tabDefs[tabIdx].shortcut + "] " + tabDefs[tabIdx].label; font.pixelSize: EmbryStyle.text.sm; font.weight: activeTab === tabIdx ? Font.SemiBold : Font.Normal; color: activeTab === tabIdx ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textMuted }
                            MouseArea { id: tabMa2; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: activeTab = tabIdx }
                            Accessible.name: tabDefs[tabIdx].label + " tab"; Accessible.role: Accessible.PageTab
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

            TemplatesPage { deckBridge: appWindow.deckBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            GroundTruthPage { deckBridge: appWindow.deckBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            EvaluatePage { deckBridge: appWindow.deckBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            GeneratorPage { deckBridge: appWindow.deckBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
            EventsPage { deckBridge: appWindow.deckBridge; opacity: StackLayout.isCurrentItem ? 1 : 0; Behavior on opacity { NumberAnimation { duration: EmbryStyle.anim.fast } } }
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
        target: deckBridge
        function onErrorOccurred(msg) {
            errorText.text = msg
            errorToast.visible = true
            errorTimer.restart()
        }
    }
}
