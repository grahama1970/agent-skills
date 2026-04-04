import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var tuneResult: bridge ? JSON.parse(bridge.tuneResultJson) : null
    property var trials: tuneResult ? (tuneResult.trials || []) : []
    property var winningParams: tuneResult ? tuneResult.winning_params : null

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        Text {
            text: "Parameter Search Space"
            font.pixelSize: EmbryStyle.text.lg; font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        // ── Winning Parameters Card ──────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: winParamsCol.implicitHeight + EmbryStyle.layout.space4
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: winningParams ? EmbryStyle.colors.statusOk : EmbryStyle.colors.border
            visible: winningParams !== null

            ColumnLayout {
                id: winParamsCol
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                RowLayout {
                    spacing: EmbryStyle.layout.space2
                    Text { text: "★"; font.pixelSize: EmbryStyle.text.lg; color: EmbryStyle.colors.statusOk }
                    Text { text: "Winning Parameters"; font.pixelSize: EmbryStyle.text.base; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 4; rowSpacing: 4; columnSpacing: EmbryStyle.layout.space4

                    Repeater {
                        model: {
                            if (!winningParams) return [];
                            var items = [];
                            var params = winningParams;
                            if (params.font_threshold !== undefined) items.push({key: "font_threshold", val: params.font_threshold});
                            if (params.short_section_merge_threshold !== undefined) items.push({key: "merge_threshold", val: params.short_section_merge_threshold});
                            if (params.min_table_lines !== undefined) items.push({key: "min_table_lines", val: params.min_table_lines});
                            if (params.preset) items.push({key: "preset", val: params.preset});
                            if (params.new_citation_pattern) items.push({key: "citation_pattern", val: params.new_citation_pattern});
                            var env = params.env || {};
                            for (var k in env) items.push({key: "env." + k, val: env[k]});
                            return items;
                        }

                        RowLayout {
                            required property var modelData
                            spacing: 4

                            Text { text: modelData.key + ":"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
                            Text { text: "" + modelData.val; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; font.weight: Font.SemiBold; color: EmbryStyle.colors.accentGreen }
                        }
                    }
                }
            }
        }

        // ── Trial Parameters Table ───────────────────────────
        Text {
            text: "Trial History (" + trials.length + " iterations)"
            font.pixelSize: EmbryStyle.text.base; font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        ListView {
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; model: trials; spacing: 2

            header: Rectangle {
                width: parent ? parent.width : 600; height: 28
                color: EmbryStyle.colors.bgElevated; radius: EmbryStyle.layout.radiusSm

                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                    Text { Layout.preferredWidth: 40; text: "#"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.preferredWidth: 80; text: "Delta"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.preferredWidth: 80; text: "Font Thr."; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.preferredWidth: 80; text: "Merge Thr."; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.preferredWidth: 80; text: "Min Lines"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.fillWidth: true; text: "Env Overrides"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                }
            }

            delegate: Rectangle {
                required property var modelData; required property int index
                width: parent ? parent.width : 600; height: 30
                color: index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                property var params: modelData.params || {}
                property real overallDelta: (modelData.delta && modelData.delta.overall_delta) || 0

                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                    Text { Layout.preferredWidth: 40; text: "" + (modelData.iteration || index + 1); font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary }
                    Text {
                        Layout.preferredWidth: 80; text: overallDelta.toFixed(3)
                        font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                        color: overallDelta >= 0.90 ? EmbryStyle.colors.statusOk : overallDelta >= 0.70 ? EmbryStyle.colors.statusWarning : EmbryStyle.colors.statusCritical
                    }
                    Text { Layout.preferredWidth: 80; text: params.font_threshold !== undefined ? params.font_threshold.toFixed(1) : "—"; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                    Text { Layout.preferredWidth: 80; text: params.short_section_merge_threshold !== undefined ? "" + params.short_section_merge_threshold : "—"; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                    Text { Layout.preferredWidth: 80; text: params.min_table_lines !== undefined ? "" + params.min_table_lines : "—"; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                    Text { Layout.fillWidth: true; text: JSON.stringify(params.env || {}); font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textGhost; elide: Text.ElideRight }
                }

                Accessible.name: "Trial " + (index + 1) + " delta " + overallDelta.toFixed(3)
                Accessible.role: Accessible.ListItem
            }
        }
    }
}
