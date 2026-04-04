import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// ReportsPage -- Generate and view benchmark reports.

Item {
    id: root

    property var reports: []
    property string previewContent: ""
    property int selectedReport: -1
    property string taskForReport: ""

    Connections {
        target: gptBridge
        function onReportListJsonChanged() {
            try {
                root.reports = JSON.parse(gptBridge.reportListJson)
            } catch (_) {
                root.reports = []
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        Text {
            text: "Reports"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        // -- Generate controls --
        RowLayout {
            spacing: EmbryStyle.layout.space3

            Text { text: "Task:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }

            EmbryTextField {
                id: reportTaskField
                Layout.preferredWidth: 200
                placeholderText: "Task name"
                text: root.taskForReport
                onTextChanged: root.taskForReport = text
                Accessible.name: "Report task name"
            }

            EmbryButton {
                text: "Generate Report"
                variant: "primary"
                enabled: root.taskForReport.length > 0
                onClicked: gptBridge.generateReport(root.taskForReport)
                Accessible.name: "Generate report button"
                Accessible.role: Accessible.Button
            }
        }

        // -- Split: Report list + Preview --
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space3

            // Report history list
            Rectangle {
                Layout.preferredWidth: 340
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1
                border.color: EmbryStyle.colors.border

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        height: 32
                        color: EmbryStyle.colors.bgInput

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: EmbryStyle.layout.space3
                            anchors.rightMargin: EmbryStyle.layout.space3
                            spacing: EmbryStyle.layout.space2

                            Text { Layout.preferredWidth: 90; text: "Date"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                            Text { Layout.preferredWidth: 80; text: "Task"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                            Text { Layout.preferredWidth: 60; text: "Models"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                            Text { Layout.fillWidth: true;    text: "Verdict"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                    ListView {
                        id: reportList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: root.reports

                        delegate: Rectangle {
                            width: reportList.width
                            height: 38
                            color: root.selectedReport === index
                                ? EmbryStyle.colors.selectBg
                                : reportRowMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"

                            Accessible.name: (modelData.task || "") + " report from " + (modelData.date || "")
                            Accessible.role: Accessible.ListItem

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: EmbryStyle.layout.space3
                                anchors.rightMargin: EmbryStyle.layout.space3
                                spacing: EmbryStyle.layout.space2

                                Text { Layout.preferredWidth: 90; text: modelData.date || ""; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textMuted }
                                Text { Layout.preferredWidth: 80; text: modelData.task || ""; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                                Text { Layout.preferredWidth: 60; text: String(modelData.model_count || 0); font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary; horizontalAlignment: Text.AlignHCenter }

                                // Verdict badge
                                Rectangle {
                                    Layout.fillWidth: true
                                    width: verdictBadgeText.implicitWidth + EmbryStyle.layout.space3
                                    height: 20
                                    radius: EmbryStyle.layout.badgeRadius
                                    color: (modelData.verdict || "") === "pass"
                                        ? EmbryStyle.colors.statusOkBg
                                        : EmbryStyle.colors.statusCriticalBg

                                    Text {
                                        id: verdictBadgeText
                                        anchors.centerIn: parent
                                        text: (modelData.verdict || "pending").toUpperCase()
                                        font.pixelSize: EmbryStyle.text.xs
                                        font.weight: EmbryStyle.text.weightBold
                                        color: (modelData.verdict || "") === "pass"
                                            ? EmbryStyle.colors.accentGreen
                                            : EmbryStyle.colors.accentRed
                                    }
                                }
                            }

                            MouseArea {
                                id: reportRowMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.selectedReport = index
                                    root.previewContent = modelData.content || "No content available."
                                }
                            }
                        }
                    }
                }
            }

            // Report preview
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1
                border.color: EmbryStyle.colors.border

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        height: 32
                        color: EmbryStyle.colors.bgInput

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: EmbryStyle.layout.space3
                            anchors.left: parent.left
                            text: "Report Preview"
                            font.pixelSize: EmbryStyle.text.sm
                            font.weight: EmbryStyle.text.weightSemibold
                            color: EmbryStyle.colors.textSecondary
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true

                        Accessible.name: "Report content preview"
                        Accessible.role: Accessible.Pane

                        Text {
                            width: parent.width - EmbryStyle.layout.space6
                            padding: EmbryStyle.layout.space3
                            text: root.previewContent || "Select a report to preview."
                            font.pixelSize: EmbryStyle.text.sm
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textPrimary
                            wrapMode: Text.Wrap
                        }
                    }
                }
            }
        }
    }
}
