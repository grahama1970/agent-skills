import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var trainState: bridge ? JSON.parse(bridge.trainStateJson) : {}
    property var datasets: trainState.datasets || []
    property var recentTrains: trainState.recent_trains || []
    property int selectedDataset: -1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        Text {
            text: "Training Pipeline"
            font.pixelSize: EmbryStyle.text.lg; font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        // -- Dataset Table --
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 220
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                spacing: 0

                Text {
                    text: "Training Datasets (" + datasets.length + ")"
                    font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold
                    color: EmbryStyle.colors.textPrimary
                    Layout.bottomMargin: 4
                }

                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: 24
                    color: Qt.rgba(1, 1, 1, 0.03); radius: EmbryStyle.layout.radiusSm
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
                        Text { Layout.preferredWidth: 180; text: "Task"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 80; text: "Labels"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 120; text: "Last Harvest"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.fillWidth: true; text: "Path"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    }
                }

                ListView {
                    id: datasetList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; model: datasets; spacing: 1

                    delegate: Rectangle {
                        required property var modelData; required property int index
                        width: datasetList.width; height: 28
                        color: index === selectedDataset ? EmbryStyle.colors.selectBg
                             : index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
                            Text { Layout.preferredWidth: 180; text: modelData.task || ""; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                            Text { Layout.preferredWidth: 80; text: "" + (modelData.label_count || 0); font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                            Text { Layout.preferredWidth: 120; text: modelData.last_harvest || "-"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textMuted }
                            Text { Layout.fillWidth: true; text: modelData.path || ""; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textGhost; elide: Text.ElideMiddle }
                        }

                        MouseArea { anchors.fill: parent; onClicked: selectedDataset = index }
                        Accessible.name: (modelData.task || "") + " dataset"; Accessible.role: Accessible.ListItem
                    }
                }
            }
        }

        // -- Train Actions --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            Text { text: "Task:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
            EmbryTextField {
                id: taskField
                Layout.preferredWidth: 200
                placeholderText: "task name"
                text: selectedDataset >= 0 && selectedDataset < datasets.length ? datasets[selectedDataset].task : ""
                Accessible.name: "Task name input"
            }

            EmbryButton {
                text: "Train GPT"; variant: "primary"; onClicked: if (bridge) bridge.train(taskField.text, "gpt")
                Accessible.name: "Train GPT model"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Train Classifier"; onClicked: if (bridge) bridge.train(taskField.text, "classifier")
                Accessible.name: "Train classifier"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Train Regressor"; onClicked: if (bridge) bridge.train(taskField.text, "regressor")
                Accessible.name: "Train regressor"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Harvest Labels"; onClicked: if (bridge) bridge.harvest(taskField.text)
                Accessible.name: "Harvest training labels"; Accessible.role: Accessible.Button
            }
        }

        // -- Recent Training History --
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                spacing: 0

                Text {
                    text: "Recent Training Runs"
                    font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold
                    color: EmbryStyle.colors.textPrimary
                    Layout.bottomMargin: 4
                }

                ListView {
                    id: trainHistory
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; model: recentTrains; spacing: 1

                    delegate: Rectangle {
                        required property var modelData; required property int index
                        width: trainHistory.width; height: 30
                        color: index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                            Text { Layout.preferredWidth: 160; text: modelData.task || ""; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                            Text { Layout.preferredWidth: 80; text: modelData.model_type || ""; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textMuted }

                            Rectangle {
                                Layout.preferredWidth: 50; Layout.preferredHeight: 18; radius: 4
                                color: modelData.success ? EmbryStyle.colors.statusOkBg : EmbryStyle.colors.statusCriticalBg
                                Text { anchors.centerIn: parent; text: modelData.success ? "OK" : "FAIL"; font.pixelSize: 8; font.weight: Font.Bold; color: modelData.success ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusCritical }
                            }

                            Text { Layout.preferredWidth: 80; text: modelData.elapsed_seconds ? modelData.elapsed_seconds.toFixed(1) + "s" : "-"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textMuted }
                            Text { Layout.fillWidth: true; text: modelData.error || JSON.stringify(modelData.metrics || {}); font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: modelData.error ? EmbryStyle.colors.statusCritical : EmbryStyle.colors.textGhost; elide: Text.ElideRight }
                        }

                        Accessible.name: (modelData.task || "") + " " + (modelData.model_type || "") + " " + (modelData.success ? "success" : "failed"); Accessible.role: Accessible.ListItem
                    }

                    Text {
                        anchors.centerIn: parent; text: "No recent training runs"
                        font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                        visible: trainHistory.count === 0
                    }
                }
            }
        }
    }
}
