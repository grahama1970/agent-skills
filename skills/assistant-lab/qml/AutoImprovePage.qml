import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var diagnoseResult: bridge ? JSON.parse(bridge.diagnoseResultJson) : {}
    property var metricsLog: bridge ? JSON.parse(bridge.metricsLogJson) : []

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        Text {
            text: "Auto-Improve Loop"
            font.pixelSize: EmbryStyle.text.lg; font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        // -- Diagnose Card --
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: diagCol.implicitHeight + EmbryStyle.layout.space4
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border
            visible: diagnoseResult.task !== undefined

            ColumnLayout {
                id: diagCol
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                RowLayout {
                    spacing: EmbryStyle.layout.space2
                    Text { text: "Diagnosis:"; font.pixelSize: EmbryStyle.text.base; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary }
                    Text { text: diagnoseResult.task || ""; font.pixelSize: EmbryStyle.text.base; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.accent }
                }

                // Capability flags
                GridLayout {
                    Layout.fillWidth: true
                    columns: 4; columnSpacing: EmbryStyle.layout.space4; rowSpacing: 4

                    Repeater {
                        model: [
                            { label: "GPT Model", key: "has_gpt" },
                            { label: "Classifier", key: "has_classifier" },
                            { label: "Regressor", key: "has_regressor" },
                            { label: "Shadow Data", key: "shadow" },
                        ]

                        RowLayout {
                            required property var modelData
                            spacing: 4

                            Rectangle {
                                width: 10; height: 10; radius: 5
                                color: {
                                    var val = diagnoseResult[modelData.key];
                                    if (val === true) return EmbryStyle.colors.statusOk;
                                    if (val === false) return EmbryStyle.colors.statusCritical;
                                    if (typeof val === "object" && val !== null) return EmbryStyle.colors.statusOk;
                                    return EmbryStyle.colors.textGhost;
                                }
                            }
                            Text { text: modelData.label; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }
                        }
                    }
                }

                // Recommendations
                Flow {
                    Layout.fillWidth: true; spacing: EmbryStyle.layout.space1
                    visible: (diagnoseResult.recommendations || []).length > 0

                    Text { text: "Recommendations:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted; height: 24; verticalAlignment: Text.AlignVCenter }

                    Repeater {
                        model: diagnoseResult.recommendations || []
                        Rectangle {
                            required property var modelData
                            width: recText.implicitWidth + EmbryStyle.layout.space3; height: 24; radius: 12
                            color: EmbryStyle.colors.badge
                            Text { id: recText; anchors.centerIn: parent; text: modelData; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.accentAmber }
                        }
                    }
                }
            }
        }

        // -- Actions --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            Text { text: "Task:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
            EmbryTextField {
                id: improveTask
                Layout.preferredWidth: 200
                placeholderText: "task name"
                Accessible.name: "Task name for auto-improve"
            }

            EmbryButton {
                text: "Diagnose"; onClicked: if (bridge) bridge.diagnose(improveTask.text)
                Accessible.name: "Run task diagnosis"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Auto-Improve"; variant: "primary"; onClicked: if (bridge) bridge.autoImprove(improveTask.text)
                Accessible.name: "Run auto-improve for task"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Auto-Improve All"; onClicked: if (bridge) bridge.autoImproveAll()
                Accessible.name: "Run auto-improve for all tasks"; Accessible.role: Accessible.Button
            }
        }

        // -- Metrics Log --
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                spacing: 0

                Text {
                    text: "Action History (" + metricsLog.length + ")"
                    font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold
                    color: EmbryStyle.colors.textPrimary
                    Layout.bottomMargin: 4
                }

                ListView {
                    id: metricsList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; model: metricsLog; spacing: 1

                    delegate: Rectangle {
                        required property var modelData; required property int index
                        width: metricsList.width; height: 28
                        color: index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                            // Action badge
                            Rectangle {
                                Layout.preferredWidth: 100; Layout.preferredHeight: 18; radius: 4
                                color: {
                                    var a = modelData.action || "";
                                    if (a.indexOf("promote") >= 0) return EmbryStyle.colors.statusOkBg;
                                    if (a.indexOf("train") >= 0) return EmbryStyle.colors.statusInfoBg;
                                    return Qt.rgba(1, 1, 1, 0.08);
                                }
                                Text {
                                    anchors.centerIn: parent; text: (modelData.action || "").toUpperCase()
                                    font.pixelSize: 8; font.weight: Font.Bold
                                    color: {
                                        var a = modelData.action || "";
                                        if (a.indexOf("promote") >= 0) return EmbryStyle.colors.statusOk;
                                        if (a.indexOf("train") >= 0) return EmbryStyle.colors.accent;
                                        return EmbryStyle.colors.textMuted;
                                    }
                                }
                            }

                            Text { Layout.preferredWidth: 160; text: modelData.task || ""; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                            Text { Layout.preferredWidth: 80; text: modelData.size || ""; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textMuted }
                            Text { Layout.preferredWidth: 80; text: modelData.gpu || ""; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textMuted }
                            Text {
                                Layout.preferredWidth: 80
                                text: modelData.cost_est ? "$" + modelData.cost_est.toFixed(2) : ""
                                font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textSecondary
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.ts ? new Date(modelData.ts * 1000).toLocaleString() : ""
                                font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textGhost
                            }
                        }

                        Accessible.name: (modelData.action || "") + " " + (modelData.task || ""); Accessible.role: Accessible.ListItem
                    }

                    Text {
                        anchors.centerIn: parent; text: "No auto-improve actions yet"
                        font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                        visible: metricsList.count === 0
                    }
                }
            }
        }
    }
}
