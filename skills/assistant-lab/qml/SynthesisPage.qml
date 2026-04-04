import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var synthResult: bridge ? JSON.parse(bridge.synthesisResultJson) : {}
    property var conversations: synthResult.conversations || []

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        Text {
            text: "Synthesis Evaluation"
            font.pixelSize: EmbryStyle.text.lg; font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        // -- Summary Row --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            // Synthesis rate gauge
            Rectangle {
                Layout.preferredWidth: 200; Layout.preferredHeight: 100
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1; border.color: synthResult.passing ? EmbryStyle.colors.statusOk : EmbryStyle.colors.border

                ColumnLayout {
                    anchors.centerIn: parent; spacing: 4

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: synthResult.synthesis_rate !== undefined ? (synthResult.synthesis_rate * 100).toFixed(1) + "%" : "-"
                        font.pixelSize: EmbryStyle.text.xxl; font.weight: Font.Bold
                        color: {
                            var rate = synthResult.synthesis_rate || 0;
                            if (rate >= (synthResult.min_synthesis_rate || 0.4)) return EmbryStyle.colors.statusOk;
                            if (rate >= 0.2) return EmbryStyle.colors.statusWarning;
                            return EmbryStyle.colors.statusCritical;
                        }
                    }
                    Text { Layout.alignment: Qt.AlignHCenter; text: "Synthesis Rate"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.SemiBold; color: EmbryStyle.colors.textMuted }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "threshold: " + ((synthResult.min_synthesis_rate || 0.4) * 100).toFixed(0) + "%"
                        font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textGhost
                    }
                }
                Accessible.name: "Synthesis rate gauge"; Accessible.role: Accessible.StaticText
            }

            // Info cards
            Repeater {
                model: [
                    { label: "Task", val: synthResult.task || "-" },
                    { label: "Persona", val: synthResult.persona || "-" },
                    { label: "Scope", val: synthResult.scope || "-" },
                    { label: "Conversations", val: "" + conversations.length },
                ]

                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true; Layout.preferredHeight: 100
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1; border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.centerIn: parent; spacing: 4
                        Text { Layout.alignment: Qt.AlignHCenter; text: modelData.val; font.pixelSize: EmbryStyle.text.base; font.weight: Font.Bold; color: EmbryStyle.colors.textPrimary }
                        Text { Layout.alignment: Qt.AlignHCenter; text: modelData.label; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.SemiBold; color: EmbryStyle.colors.textMuted }
                    }
                }
            }

            // Pass/Fail badge
            Rectangle {
                Layout.preferredWidth: 100; Layout.preferredHeight: 100
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 2; border.color: synthResult.passing ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusCritical

                Text {
                    anchors.centerIn: parent
                    text: synthResult.passing === true ? "PASS" : synthResult.passing === false ? "FAIL" : "-"
                    font.pixelSize: EmbryStyle.text.xl; font.weight: Font.Bold
                    color: synthResult.passing ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusCritical
                }
                Accessible.name: "Synthesis evaluation " + (synthResult.passing ? "passing" : "failing"); Accessible.role: Accessible.StaticText
            }
        }

        // -- Actions --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            Text { text: "Task:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
            EmbryTextField {
                id: synthTask
                Layout.preferredWidth: 200
                placeholderText: "task name"
                text: synthResult.task || ""
                Accessible.name: "Task for synthesis eval"
            }

            Text { text: "Count:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
            SpinBox {
                id: synthCount
                from: 5; to: 100; value: 20; stepSize: 5
                Accessible.name: "Number of synthesis conversations"; Accessible.role: Accessible.SpinBox
            }

            EmbryButton {
                text: "Run Synthesis Eval"
                variant: "primary"
                onClicked: if (bridge) bridge.runSynthesisEval(synthTask.text, synthCount.value)
                Accessible.name: "Run synthesis evaluation"; Accessible.role: Accessible.Button
            }
        }

        // -- Conversation Results --
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                spacing: 0

                Text {
                    text: "Conversation Results (" + conversations.length + ")"
                    font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold
                    color: EmbryStyle.colors.textPrimary
                    Layout.bottomMargin: 4
                }

                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: 24
                    color: Qt.rgba(1, 1, 1, 0.03); radius: EmbryStyle.layout.radiusSm
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
                        Text { Layout.preferredWidth: 40; text: "#"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 60; text: "QRAs"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 80; text: "Synthesis?"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.fillWidth: true; text: "Question"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    }
                }

                ListView {
                    id: convList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; model: conversations; spacing: 1

                    delegate: Rectangle {
                        required property var modelData; required property int index
                        width: convList.width; height: 28
                        color: index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                        property int qrasUsed: modelData.qras_used || 0

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                            Text { Layout.preferredWidth: 40; text: "" + (index + 1); font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary }
                            Text { Layout.preferredWidth: 60; text: "" + qrasUsed; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }

                            Rectangle {
                                Layout.preferredWidth: 80; Layout.preferredHeight: 18; radius: 4
                                color: qrasUsed > 0 ? EmbryStyle.colors.statusOkBg : EmbryStyle.colors.badge
                                Text {
                                    anchors.centerIn: parent
                                    text: qrasUsed > 0 ? "YES" : "NO"
                                    font.pixelSize: 8; font.weight: Font.Bold
                                    color: qrasUsed > 0 ? EmbryStyle.colors.statusOk : EmbryStyle.colors.textMuted
                                }
                            }

                            Text { Layout.fillWidth: true; text: modelData.question || ""; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textSecondary; elide: Text.ElideRight }
                        }

                        Accessible.name: "Conversation " + (index + 1) + " QRAs " + qrasUsed; Accessible.role: Accessible.ListItem
                    }

                    Text {
                        anchors.centerIn: parent; text: "Run synthesis eval to see results"
                        font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                        visible: convList.count === 0
                    }
                }
            }
        }

        // -- Errors --
        Text {
            visible: (synthResult.errors || []).length > 0
            text: "Errors: " + (synthResult.errors || []).length
            font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.statusCritical
        }
    }
}
