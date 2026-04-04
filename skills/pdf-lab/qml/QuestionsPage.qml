import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var questions: bridge ? JSON.parse(bridge.questionsJson) : []
    property int selectedQuestion: -1
    property string filterSeverity: "all"

    property var filteredQuestions: {
        if (filterSeverity === "all") return questions;
        return questions.filter(function(q) { return q.reason === filterSeverity; });
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Header Row --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Deferred Questions (" + questions.length + ")"
                font.pixelSize: EmbryStyle.text.lg; font.weight: Font.SemiBold
                color: EmbryStyle.colors.textPrimary
            }

            Item { Layout.fillWidth: true }

            // Severity filter
            Text {
                text: "Filter:"
                font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted
            }

            EmbryComboBox {
                id: severityFilter
                Layout.preferredWidth: 160
                model: ["all", "stalled", "repeated_errors", "ambiguous_diagnosis"]
                onCurrentTextChanged: root.filterSeverity = currentText
                Accessible.name: "Filter by reason"
            }
        }

        // -- Question List --
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: EmbryStyle.layout.space3

            // Left: question list
            Rectangle {
                Layout.preferredWidth: 340; Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1; border.color: EmbryStyle.colors.border

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                    spacing: EmbryStyle.layout.space2

                    Text {
                        text: "Pending (" + filteredQuestions.length + ")"
                        font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold
                        color: EmbryStyle.colors.textPrimary
                    }

                    ListView {
                        id: questionList
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; model: filteredQuestions; spacing: 2

                        delegate: Rectangle {
                            required property var modelData; required property int index
                            width: questionList.width; height: 64
                            radius: EmbryStyle.layout.radiusSm
                            color: index === selectedQuestion ? EmbryStyle.colors.selectBg : "transparent"
                            border.width: index === selectedQuestion ? 1 : 0
                            border.color: EmbryStyle.colors.selectBorder

                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                                spacing: 2

                                RowLayout {
                                    spacing: 4

                                    // Severity badge
                                    Rectangle {
                                        width: reasonText.implicitWidth + 8; height: 18; radius: 4
                                        color: {
                                            if (modelData.reason === "stalled") return EmbryStyle.colors.statusWarningBg;
                                            if (modelData.reason === "repeated_errors") return EmbryStyle.colors.statusCriticalBg;
                                            return EmbryStyle.colors.statusInfoBg;
                                        }
                                        Text {
                                            id: reasonText; anchors.centerIn: parent
                                            text: modelData.reason || "unknown"
                                            font.pixelSize: 9; font.weight: Font.Bold
                                            color: {
                                                if (modelData.reason === "stalled") return EmbryStyle.colors.statusWarning;
                                                if (modelData.reason === "repeated_errors") return EmbryStyle.colors.statusCritical;
                                                return EmbryStyle.colors.statusInfo;
                                            }
                                        }
                                    }

                                    Text {
                                        text: "iter " + (modelData.iteration || 0) + "/" + (modelData.max_iterations || 0)
                                        font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                                        color: EmbryStyle.colors.textMuted
                                    }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.pdf_name || "unknown.pdf"
                                    font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold
                                    color: EmbryStyle.colors.textPrimary
                                    elide: Text.ElideMiddle
                                }

                                Text {
                                    text: "best delta: " + (modelData.best_delta || 0).toFixed(3)
                                    font.pixelSize: 9; font.family: EmbryStyle.text.monoFamily
                                    color: EmbryStyle.colors.textGhost
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: selectedQuestion = index
                            }

                            Accessible.name: (modelData.pdf_name || "unknown") + " deferred question"
                            Accessible.role: Accessible.ListItem
                        }

                        Text {
                            anchors.centerIn: parent
                            text: "No deferred questions"
                            font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                            visible: questionList.count === 0
                        }
                    }
                }
            }

            // Right: question detail
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1; border.color: EmbryStyle.colors.border

                property var selected: selectedQuestion >= 0 && selectedQuestion < filteredQuestions.length ? filteredQuestions[selectedQuestion] : null

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: EmbryStyle.layout.space3
                    spacing: EmbryStyle.layout.space3
                    visible: parent.selected !== null

                    // PDF name + delta
                    Text {
                        text: parent.parent.selected ? parent.parent.selected.pdf_name : ""
                        font.pixelSize: EmbryStyle.text.base; font.weight: Font.Bold
                        color: EmbryStyle.colors.textPrimary
                    }

                    // Delta summary
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 4; columnSpacing: EmbryStyle.layout.space4; rowSpacing: 4

                        Repeater {
                            model: {
                                var sel = root.selectedQuestion >= 0 && root.selectedQuestion < root.filteredQuestions.length ? root.filteredQuestions[root.selectedQuestion] : null;
                                if (!sel || !sel.delta_summary) return [];
                                var d = sel.delta_summary;
                                var items = [];
                                if (d.section_delta !== undefined) items.push({key: "sections", val: d.section_delta});
                                if (d.table_delta !== undefined) items.push({key: "tables", val: d.table_delta});
                                if (d.figure_delta !== undefined) items.push({key: "figures", val: d.figure_delta});
                                if (d.overall_delta !== undefined) items.push({key: "overall", val: d.overall_delta});
                                return items;
                            }

                            RowLayout {
                                required property var modelData
                                spacing: 4
                                Text { text: modelData.key + ":"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }
                                Text {
                                    text: modelData.val.toFixed(3)
                                    font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; font.weight: Font.SemiBold
                                    color: modelData.val >= 0.85 ? EmbryStyle.colors.statusOk : modelData.val >= 0.60 ? EmbryStyle.colors.statusWarning : EmbryStyle.colors.statusCritical
                                }
                            }
                        }
                    }

                    // Patterns
                    Flow {
                        Layout.fillWidth: true
                        spacing: EmbryStyle.layout.space1

                        Repeater {
                            model: {
                                var sel = root.selectedQuestion >= 0 && root.selectedQuestion < root.filteredQuestions.length ? root.filteredQuestions[root.selectedQuestion] : null;
                                return sel ? (sel.patterns || []) : [];
                            }
                            Rectangle {
                                required property var modelData
                                width: pText.implicitWidth + EmbryStyle.layout.space3; height: 22; radius: 11
                                color: EmbryStyle.colors.badge
                                Text {
                                    id: pText; anchors.centerIn: parent
                                    text: modelData
                                    font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                                    color: EmbryStyle.colors.accentAmber
                                }
                            }
                        }
                    }

                    // Diagnosis
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: diagText.implicitHeight + EmbryStyle.layout.space4
                        radius: EmbryStyle.layout.radiusSm
                        color: Qt.rgba(1, 1, 1, 0.03)

                        Text {
                            id: diagText
                            anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                            text: {
                                var sel = root.selectedQuestion >= 0 && root.selectedQuestion < root.filteredQuestions.length ? root.filteredQuestions[root.selectedQuestion] : null;
                                if (!sel || !sel.diagnosis_summary) return "";
                                var d = sel.diagnosis_summary;
                                return "Root cause: " + (d.root_cause || "unknown") + "\n" +
                                       "Patterns: " + (d.patterns || []).join(", ") + "\n" +
                                       "Failing steps: " + (d.failing_steps || []).join(", ");
                            }
                            font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textSecondary
                            wrapMode: Text.WordWrap
                        }
                    }

                    Item { Layout.fillHeight: true }
                }

                // Empty state
                Text {
                    anchors.centerIn: parent
                    text: "Select a question to view details"
                    font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                    visible: parent.selected === null
                }
            }
        }

        // -- Action Row --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            EmbryButton {
                text: "Review All"; variant: "primary"; onClicked: if (bridge) bridge.reviewQuestions()
                Accessible.name: "Launch interactive question review"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Refresh"; onClicked: if (bridge) bridge.refresh()
                Accessible.name: "Refresh deferred questions"; Accessible.role: Accessible.Button
            }

            Item { Layout.fillWidth: true }

            Text {
                text: questions.length + " deferred | " + filteredQuestions.length + " shown"
                font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textGhost
            }
        }
    }
}
