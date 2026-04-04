import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    // ── Properties ──────────────────────────────────────────
    property var bridge: null
    property var diagnosis: bridge ? JSON.parse(bridge.diagnosisJson) : null
    property var summary: diagnosis ? diagnosis.summary : null

    // ── Layout ──────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // ── Summary Cards Row ────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            // Pass/Warn/Fail counts
            Repeater {
                model: [
                    { label: "PASS", value: summary ? summary.pass : 0, color: EmbryStyle.colors.statusOk },
                    { label: "WARN", value: summary ? summary.warn : 0, color: EmbryStyle.colors.statusWarning },
                    { label: "FAIL", value: summary ? summary.fail : 0, color: EmbryStyle.colors.statusCritical },
                    { label: "TOTAL", value: summary ? summary.total : 0, color: EmbryStyle.colors.textSecondary },
                ]

                Rectangle {
                    required property var modelData

                    Layout.fillWidth: true
                    Layout.preferredHeight: 80

                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 4

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: modelData.value
                            font.pixelSize: EmbryStyle.text.xxl
                            font.weight: Font.Bold
                            color: modelData.color
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: modelData.label
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.SemiBold
                            color: EmbryStyle.colors.textMuted
                            font.letterSpacing: 1
                        }
                    }

                    Accessible.name: modelData.label + " count: " + modelData.value
                    Accessible.role: Accessible.StaticText
                }
            }

            // Satisfaction gauge
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 80

                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1
                border.color: EmbryStyle.colors.border

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 4

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: summary ? (summary.satisfied_rate * 100).toFixed(0) + "%" : "—"
                        font.pixelSize: EmbryStyle.text.xxl
                        font.weight: Font.Bold
                        color: {
                            if (!summary) return EmbryStyle.colors.textMuted;
                            if (summary.satisfied_rate >= 0.80) return EmbryStyle.colors.statusOk;
                            if (summary.satisfied_rate >= 0.60) return EmbryStyle.colors.statusWarning;
                            return EmbryStyle.colors.statusCritical;
                        }
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "SATISFIED"
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: Font.SemiBold
                        color: EmbryStyle.colors.textMuted
                        font.letterSpacing: 1
                    }
                }

                Accessible.name: "Satisfaction rate: " + (summary ? (summary.satisfied_rate * 100).toFixed(0) + " percent" : "unknown")
                Accessible.role: Accessible.StaticText
            }
        }

        // ── Grade Distribution Bar ───────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 28

            radius: EmbryStyle.layout.radiusSm
            color: EmbryStyle.colors.bgElevated
            clip: true

            Row {
                anchors.fill: parent

                Repeater {
                    model: {
                        if (!summary || !summary.grades) return [];
                        var total = summary.total || 1;
                        var items = [];
                        var grades = ["A", "B", "C", "F"];
                        var colors = [EmbryStyle.colors.statusOk, EmbryStyle.colors.accentGreen,
                                      EmbryStyle.colors.statusWarning, EmbryStyle.colors.statusCritical];
                        for (var i = 0; i < grades.length; i++) {
                            var count = summary.grades[grades[i]] || 0;
                            if (count > 0) {
                                items.push({ grade: grades[i], count: count, ratio: count / total, color: colors[i] });
                            }
                        }
                        return items;
                    }

                    Rectangle {
                        required property var modelData

                        width: parent.width * modelData.ratio
                        height: parent.height
                        color: modelData.color
                        opacity: 0.7

                        Text {
                            anchors.centerIn: parent
                            text: modelData.grade + " (" + modelData.count + ")"
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.SemiBold
                            color: EmbryStyle.colors.bg
                            visible: parent.width > 40
                        }
                    }
                }
            }

            Accessible.name: "Grade distribution bar"
            Accessible.role: Accessible.ProgressBar
        }

        // ── Systemic Issues Table ────────────────────────────
        Text {
            text: "Systemic Issues"
            font.pixelSize: EmbryStyle.text.base
            font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        ListView {
            id: issuesList

            Layout.fillWidth: true
            Layout.fillHeight: true

            clip: true
            model: diagnosis ? diagnosis.systemic_issues : []
            spacing: 2

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: issuesList.width
                height: issueRow.implicitHeight + EmbryStyle.layout.space3

                radius: EmbryStyle.layout.radiusSm
                color: index % 2 === 0 ? EmbryStyle.colors.bgElevated : "transparent"

                RowLayout {
                    id: issueRow

                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space2
                    spacing: EmbryStyle.layout.space3

                    // Severity badge
                    Rectangle {
                        Layout.preferredWidth: 60
                        Layout.preferredHeight: EmbryStyle.layout.badgeHeight

                        radius: EmbryStyle.layout.badgeRadius
                        color: {
                            var sev = modelData.severity || "low";
                            if (sev === "critical") return EmbryStyle.colors.statusCriticalBg;
                            if (sev === "high") return EmbryStyle.colors.statusWarningBg;
                            if (sev === "medium") return EmbryStyle.colors.statusInfoBg;
                            return EmbryStyle.colors.badge;
                        }

                        Text {
                            anchors.centerIn: parent
                            text: (modelData.severity || "low").toUpperCase()
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.Bold
                            color: {
                                var sev = modelData.severity || "low";
                                if (sev === "critical") return EmbryStyle.colors.statusCritical;
                                if (sev === "high") return EmbryStyle.colors.statusWarning;
                                if (sev === "medium") return EmbryStyle.colors.statusInfo;
                                return EmbryStyle.colors.textMuted;
                            }
                        }
                    }

                    // Issue name
                    Text {
                        Layout.preferredWidth: 180
                        text: modelData.issue || ""
                        font.pixelSize: EmbryStyle.text.sm
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textPrimary
                        elide: Text.ElideRight
                    }

                    // Count
                    Text {
                        Layout.preferredWidth: 40
                        text: "×" + (modelData.count || 0)
                        font.pixelSize: EmbryStyle.text.sm
                        font.weight: Font.SemiBold
                        color: EmbryStyle.colors.textSecondary
                        horizontalAlignment: Text.AlignRight
                    }

                    // Fix suggestion
                    Text {
                        Layout.fillWidth: true
                        text: modelData.fix || ""
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textMuted
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                    }
                }

                Accessible.name: (modelData.severity || "low") + " issue: " + (modelData.issue || "") + ", count " + (modelData.count || 0)
                Accessible.role: Accessible.ListItem
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                text: "No systemic issues detected"
                font.pixelSize: EmbryStyle.text.base
                color: EmbryStyle.colors.textMuted
                visible: issuesList.count === 0
            }
        }

        // ── Action Row ───────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            EmbryButton {
                text: "Refresh Diagnosis"
                variant: "primary"
                icon.name: "view-refresh"

                onClicked: if (bridge) bridge.refresh()

                Accessible.name: "Refresh diagnosis"
                Accessible.role: Accessible.Button
                Accessible.description: "Re-run diagnosis on latest session data"
            }

            Text {
                text: diagnosis ? "Rerun candidates: " + (diagnosis.rerun_candidates || []).length : ""
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textMuted
            }

            Item { Layout.fillWidth: true }

            Text {
                text: summary ? "Avg composite: " + summary.avg_composite.toFixed(3) : ""
                font.pixelSize: EmbryStyle.text.sm
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textSecondary
            }
        }
    }
}
