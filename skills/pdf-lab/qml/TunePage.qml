import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var tuneResult: bridge ? JSON.parse(bridge.tuneResultJson) : null
    property var delta: tuneResult ? tuneResult.delta_after : null
    property var deltaBefore: tuneResult ? tuneResult.delta_before : null
    property var trials: tuneResult ? tuneResult.trials : []
    property var diagnosis: tuneResult ? tuneResult.diagnosis : null

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // ── Delta Gauges Row ─────────────────────────────────
        Text {
            text: "Extraction Delta"
            font.pixelSize: EmbryStyle.text.base; font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Repeater {
                model: [
                    { label: "Sections", key: "section_delta" },
                    { label: "Tables", key: "table_delta" },
                    { label: "Figures", key: "figure_delta" },
                    { label: "Pages", key: "page_delta" },
                    { label: "Overall", key: "overall_delta" },
                ]

                Rectangle {
                    required property var modelData

                    Layout.fillWidth: true
                    Layout.preferredHeight: 90
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1; border.color: EmbryStyle.colors.border

                    property real beforeVal: deltaBefore ? (deltaBefore[modelData.key] || 0) : 0
                    property real afterVal: delta ? (delta[modelData.key] || 0) : 0
                    property real improvement: afterVal - beforeVal

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 4

                        // Before → After
                        RowLayout {
                            Layout.alignment: Qt.AlignHCenter
                            spacing: 4

                            Text {
                                text: beforeVal.toFixed(2)
                                font.pixelSize: EmbryStyle.text.sm
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textMuted
                                visible: deltaBefore !== null
                            }
                            Text {
                                text: "→"
                                font.pixelSize: EmbryStyle.text.xs
                                color: EmbryStyle.colors.textGhost
                                visible: deltaBefore !== null
                            }
                            Text {
                                text: afterVal.toFixed(2)
                                font.pixelSize: EmbryStyle.text.xl
                                font.weight: Font.Bold
                                color: {
                                    if (afterVal >= 0.90) return EmbryStyle.colors.statusOk;
                                    if (afterVal >= 0.70) return EmbryStyle.colors.statusWarning;
                                    return EmbryStyle.colors.statusCritical;
                                }
                            }
                        }

                        // Improvement indicator
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: improvement > 0 ? "+" + (improvement * 100).toFixed(1) + "%"
                                : improvement < 0 ? (improvement * 100).toFixed(1) + "%"
                                : "—"
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.SemiBold
                            color: improvement > 0 ? EmbryStyle.colors.statusOk
                                 : improvement < 0 ? EmbryStyle.colors.statusCritical
                                 : EmbryStyle.colors.textGhost
                            visible: deltaBefore !== null
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: modelData.label
                            font.pixelSize: EmbryStyle.text.xs; font.weight: Font.SemiBold
                            color: EmbryStyle.colors.textMuted; font.letterSpacing: 1
                        }
                    }

                    Accessible.name: modelData.label + " delta: " + afterVal.toFixed(2)
                    Accessible.role: Accessible.StaticText
                }
            }
        }

        // ── Diagnosis Section ────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: diagColumn.implicitHeight + EmbryStyle.layout.space4
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border

            ColumnLayout {
                id: diagColumn
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                Text {
                    text: "Diagnosis"
                    font.pixelSize: EmbryStyle.text.base; font.weight: Font.SemiBold
                    color: EmbryStyle.colors.textPrimary
                }

                RowLayout {
                    spacing: EmbryStyle.layout.space3

                    Text {
                        text: "Root cause:"
                        font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted
                    }
                    Text {
                        text: diagnosis ? (diagnosis.root_cause || "unknown") : "—"
                        font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                        font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary
                    }
                }

                // Patterns as tags
                Flow {
                    Layout.fillWidth: true
                    spacing: EmbryStyle.layout.space1

                    Text {
                        text: "Patterns:"
                        font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted
                        height: 24; verticalAlignment: Text.AlignVCenter
                    }

                    Repeater {
                        model: diagnosis ? (diagnosis.patterns || []) : []

                        Rectangle {
                            required property var modelData
                            width: patternText.implicitWidth + EmbryStyle.layout.space3
                            height: 24; radius: 12
                            color: EmbryStyle.colors.badge

                            Text {
                                id: patternText
                                anchors.centerIn: parent
                                text: modelData
                                font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.accentAmber
                            }
                        }
                    }
                }

                // Failing steps
                RowLayout {
                    spacing: EmbryStyle.layout.space3
                    visible: diagnosis && (diagnosis.failing_steps || []).length > 0

                    Text {
                        text: "Failing steps:"
                        font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted
                    }

                    Repeater {
                        model: diagnosis ? (diagnosis.failing_steps || []) : []
                        Rectangle {
                            required property var modelData
                            width: stepText.implicitWidth + 12; height: 22; radius: 4
                            color: EmbryStyle.colors.statusCriticalBg
                            Text { id: stepText; anchors.centerIn: parent; text: modelData; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.statusCritical }
                        }
                    }
                }
            }
        }

        // ── Trial Convergence ────────────────────────────────
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                Text {
                    text: "Convergence Trials (" + trials.length + ")"
                    font.pixelSize: EmbryStyle.text.base; font.weight: Font.SemiBold
                    color: EmbryStyle.colors.textPrimary
                }

                ListView {
                    id: trialsList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; model: trials; spacing: 2

                    delegate: Rectangle {
                        required property var modelData; required property int index
                        width: trialsList.width; height: 30
                        color: index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: EmbryStyle.layout.space2
                            spacing: EmbryStyle.layout.space3

                            Text { text: "#" + (modelData.iteration || index + 1); Layout.preferredWidth: 30; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary }
                            Text { text: "Δ " + ((modelData.delta && modelData.delta.overall_delta) || 0).toFixed(3); Layout.preferredWidth: 80; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                            Text { text: "font_threshold=" + ((modelData.params && modelData.params.font_threshold) || "—"); Layout.fillWidth: true; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textMuted; elide: Text.ElideRight }
                        }

                        Accessible.name: "Trial " + (index + 1) + " delta " + ((modelData.delta && modelData.delta.overall_delta) || 0).toFixed(3)
                        Accessible.role: Accessible.ListItem
                    }

                    Text {
                        anchors.centerIn: parent; text: "No trials yet — run tune to start"
                        font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                        visible: trialsList.count === 0
                    }
                }
            }
        }

        // ── Action Row ───────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            EmbryButton {
                text: "Run Tune"; variant: "primary"; onClicked: if (bridge) bridge.runTune(false, false)
                Accessible.name: "Run convergence tune"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Dry Run"; onClicked: if (bridge) bridge.runTune(true, false)
                Accessible.name: "Dry run tune"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Write Back"; enabled: tuneResult !== null && tuneResult.status === "converged"
                onClicked: if (bridge) bridge.runTune(false, true)
                Accessible.name: "Write fix to pipeline"; Accessible.role: Accessible.Button
            }

            Item { Layout.fillWidth: true }

            Text {
                text: tuneResult ? "Status: " + tuneResult.status + " | Iterations: " + tuneResult.iterations : ""
                font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textGhost
            }
        }
    }
}
