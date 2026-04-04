import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// PromotePage -- promote verified figures and manage lab-verified status.

Item {
    id: root

    property var promoteData: ({ pending: [], promoted: [], stats: {} })
    property int selectedPendingIdx: -1
    property int selectedPromotedIdx: -1

    Connections {
        target: figureBridge
        function onPromoteListJsonChanged() {
            try {
                promoteData = JSON.parse(figureBridge.promoteListJson) || { pending: [], promoted: [], stats: {} }
            } catch (e) {
                promoteData = { pending: [], promoted: [], stats: {} }
            }
        }
    }

    Component.onCompleted: figureBridge.refresh()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // -- Stats Row --------------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Repeater {
                model: [
                    { label: "Total",    key: "total",    color: EmbryStyle.colors.textPrimary },
                    { label: "Promoted", key: "promoted", color: EmbryStyle.colors.statusOk },
                    { label: "Pending",  key: "pending",  color: EmbryStyle.colors.statusWarning },
                    { label: "Failing",  key: "failing",  color: EmbryStyle.colors.statusCritical }
                ]

                Rectangle {
                    width: 120
                    height: 56
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: modelData.label
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.Medium
                            color: EmbryStyle.colors.textMuted
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: String((promoteData.stats || {})[modelData.key] || 0)
                            font.pixelSize: EmbryStyle.text.xl
                            font.weight: Font.Bold
                            font.family: EmbryStyle.text.monoFamily
                            color: modelData.color
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // Bulk promote button
            EmbryButton {
                id: bulkPromoteBtn
                text: "Promote All Passing"

                Accessible.name: "Promote all passing compositions"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: bulkPromoteBtn.hovered ? Qt.darker(EmbryStyle.colors.accentGreen, 1.3) : EmbryStyle.colors.accentGreen
                    radius: EmbryStyle.layout.radiusSm
                }

                contentItem: Text {
                    text: bulkPromoteBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: Font.Bold
                    color: EmbryStyle.colors.bg
                    horizontalAlignment: Text.AlignHCenter
                    leftPadding: EmbryStyle.layout.space3
                    rightPadding: EmbryStyle.layout.space3
                }

                onClicked: {
                    var pending = promoteData.pending || []
                    for (var i = 0; i < pending.length; i++) {
                        figureBridge.promote(pending[i].name || "")
                    }
                    figureBridge.refresh()
                }
            }
        }

        // -- Two-column lists -------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space3

            // Pending list
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: EmbryStyle.layout.space2

                RowLayout {
                    spacing: EmbryStyle.layout.space2

                    Text {
                        text: "Pending"
                        font.pixelSize: EmbryStyle.text.base
                        font.weight: Font.Bold
                        color: EmbryStyle.colors.statusWarning
                    }

                    Rectangle {
                        width: pendCountLabel.implicitWidth + 8
                        height: 18
                        radius: 4
                        color: EmbryStyle.colors.statusWarningBg

                        Text {
                            id: pendCountLabel
                            anchors.centerIn: parent
                            text: String((promoteData.pending || []).length)
                            font.pixelSize: 8
                            font.weight: Font.Bold
                            color: EmbryStyle.colors.statusWarning
                        }
                    }

                    Item { Layout.fillWidth: true }

                    EmbryButton {
                        id: promoteSelBtn
                        text: "Promote Selected"
                        enabled: selectedPendingIdx >= 0

                        Accessible.name: "Promote selected pending composition"
                        Accessible.role: Accessible.Button

                        background: Rectangle {
                            color: promoteSelBtn.enabled
                                ? (promoteSelBtn.hovered ? Qt.darker(EmbryStyle.colors.accentGreen, 1.3) : EmbryStyle.colors.accentGreen)
                                : EmbryStyle.colors.bgInput
                            radius: EmbryStyle.layout.radiusSm
                        }

                        contentItem: Text {
                            text: promoteSelBtn.text
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.Bold
                            color: promoteSelBtn.enabled ? EmbryStyle.colors.bg : EmbryStyle.colors.textMuted
                            horizontalAlignment: Text.AlignHCenter
                            leftPadding: EmbryStyle.layout.space2
                            rightPadding: EmbryStyle.layout.space2
                        }

                        onClicked: {
                            var pending = promoteData.pending || []
                            if (selectedPendingIdx >= 0 && selectedPendingIdx < pending.length) {
                                figureBridge.promote(pending[selectedPendingIdx].name || "")
                                selectedPendingIdx = -1
                                figureBridge.refresh()
                            }
                        }
                    }
                }

                ListView {
                    id: pendingList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: promoteData.pending || []
                    spacing: 2

                    delegate: Rectangle {
                        width: pendingList.width
                        height: 36
                        radius: EmbryStyle.layout.radiusSm
                        color: selectedPendingIdx === index
                            ? EmbryStyle.colors.selectBg
                            : pendMa.containsMouse ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgElevated

                        Accessible.name: (modelData.name || "") + " pending"
                        Accessible.role: Accessible.ListItem

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: EmbryStyle.layout.space2
                            anchors.rightMargin: EmbryStyle.layout.space2
                            spacing: EmbryStyle.layout.space2

                            Rectangle {
                                width: vtBadge.implicitWidth + 8
                                height: 18
                                radius: 4
                                color: EmbryStyle.colors.statusOkBg

                                Text {
                                    id: vtBadge
                                    anchors.centerIn: parent
                                    text: modelData.viz_type || "?"
                                    font.pixelSize: 8
                                    font.weight: Font.Bold
                                    color: EmbryStyle.colors.accentGreen
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.name || ""
                                font.pixelSize: EmbryStyle.text.sm
                                color: EmbryStyle.colors.textPrimary
                                elide: Text.ElideRight
                            }

                            Text {
                                text: (modelData.overall_score || 0).toFixed(2)
                                font.pixelSize: EmbryStyle.text.xs
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.statusWarning
                            }
                        }

                        MouseArea {
                            id: pendMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: selectedPendingIdx = index
                            Accessible.name: "Select pending figure"
                            Accessible.role: Accessible.ListItem
                        }
                    }
                }
            }

            // Vertical separator
            Rectangle {
                Layout.fillHeight: true
                width: 1
                color: EmbryStyle.colors.separator
            }

            // Promoted list
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: EmbryStyle.layout.space2

                RowLayout {
                    spacing: EmbryStyle.layout.space2

                    Text {
                        text: "Promoted"
                        font.pixelSize: EmbryStyle.text.base
                        font.weight: Font.Bold
                        color: EmbryStyle.colors.statusOk
                    }

                    Rectangle {
                        width: promCountLabel.implicitWidth + 8
                        height: 18
                        radius: 4
                        color: EmbryStyle.colors.statusOkBg

                        Text {
                            id: promCountLabel
                            anchors.centerIn: parent
                            text: String((promoteData.promoted || []).length)
                            font.pixelSize: 8
                            font.weight: Font.Bold
                            color: EmbryStyle.colors.statusOk
                        }
                    }

                    Item { Layout.fillWidth: true }

                    EmbryButton {
                        id: demoteSelBtn
                        text: "Demote Selected"
                        enabled: selectedPromotedIdx >= 0

                        Accessible.name: "Demote selected promoted composition"
                        Accessible.role: Accessible.Button

                        background: Rectangle {
                            color: demoteSelBtn.hovered ? EmbryStyle.colors.statusCriticalBg : EmbryStyle.colors.bgInput
                            border.width: 1
                            border.color: demoteSelBtn.enabled ? EmbryStyle.colors.statusCritical : EmbryStyle.colors.border
                            radius: EmbryStyle.layout.radiusSm
                        }

                        contentItem: Text {
                            text: demoteSelBtn.text
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.Medium
                            color: demoteSelBtn.enabled ? EmbryStyle.colors.statusCritical : EmbryStyle.colors.textMuted
                            horizontalAlignment: Text.AlignHCenter
                            leftPadding: EmbryStyle.layout.space2
                            rightPadding: EmbryStyle.layout.space2
                        }

                        onClicked: {
                            var promoted = promoteData.promoted || []
                            if (selectedPromotedIdx >= 0 && selectedPromotedIdx < promoted.length) {
                                figureBridge.demote(promoted[selectedPromotedIdx].name || "")
                                selectedPromotedIdx = -1
                                figureBridge.refresh()
                            }
                        }
                    }
                }

                ListView {
                    id: promotedList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: promoteData.promoted || []
                    spacing: 2

                    delegate: Rectangle {
                        width: promotedList.width
                        height: 36
                        radius: EmbryStyle.layout.radiusSm
                        color: selectedPromotedIdx === index
                            ? EmbryStyle.colors.selectBg
                            : promItemMa.containsMouse ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgElevated

                        Accessible.name: (modelData.name || "") + " promoted"
                        Accessible.role: Accessible.ListItem

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: EmbryStyle.layout.space2
                            anchors.rightMargin: EmbryStyle.layout.space2
                            spacing: EmbryStyle.layout.space2

                            Rectangle {
                                width: pvtBadge.implicitWidth + 8
                                height: 18
                                radius: 4
                                color: EmbryStyle.colors.statusOkBg

                                Text {
                                    id: pvtBadge
                                    anchors.centerIn: parent
                                    text: modelData.viz_type || "?"
                                    font.pixelSize: 8
                                    font.weight: Font.Bold
                                    color: EmbryStyle.colors.accentGreen
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.name || ""
                                font.pixelSize: EmbryStyle.text.sm
                                color: EmbryStyle.colors.textPrimary
                                elide: Text.ElideRight
                            }

                            // Lab-verified badge
                            Rectangle {
                                width: verBadge.implicitWidth + 8
                                height: 18
                                radius: 4
                                color: EmbryStyle.colors.statusInfoBg

                                Text {
                                    id: verBadge
                                    anchors.centerIn: parent
                                    text: "lab-verified"
                                    font.pixelSize: 8
                                    font.weight: Font.Bold
                                    color: EmbryStyle.colors.accent
                                }
                            }

                            Text {
                                text: (modelData.overall_score || 0).toFixed(2)
                                font.pixelSize: EmbryStyle.text.xs
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.statusOk
                            }
                        }

                        MouseArea {
                            id: promItemMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: selectedPromotedIdx = index
                            Accessible.name: "Select promoted figure"
                            Accessible.role: Accessible.ListItem
                        }
                    }
                }
            }
        }
    }
}
