import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var history: bridge ? JSON.parse(bridge.historyJson) : []
    property int selectedEntry: -1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        Text {
            text: "Write-Back History (" + history.length + " commits)"
            font.pixelSize: EmbryStyle.text.lg; font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        // -- History Table --
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                spacing: 0

                // Header
                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: 28
                    color: Qt.rgba(1, 1, 1, 0.03); radius: EmbryStyle.layout.radiusSm

                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                        Text { Layout.preferredWidth: 80; text: "SHA"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 60; text: "Status"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 60; text: "Tier"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 120; text: "Branch"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 120; text: "Persona"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.fillWidth: true; text: "Description"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 80; text: "Delta"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    }
                }

                ListView {
                    id: historyList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; model: history; spacing: 1

                    delegate: Rectangle {
                        required property var modelData; required property int index
                        width: historyList.width; height: 36
                        radius: EmbryStyle.layout.radiusSm
                        color: index === selectedEntry ? EmbryStyle.colors.selectBg
                             : index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"
                        border.width: index === selectedEntry ? 1 : 0
                        border.color: EmbryStyle.colors.selectBorder

                        property var changes: modelData.changes || []

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                            // SHA
                            Text {
                                Layout.preferredWidth: 80
                                text: (modelData.commit_sha || "").substring(0, 7)
                                font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                                font.weight: Font.SemiBold; color: EmbryStyle.colors.accent
                            }

                            // Status badge
                            Rectangle {
                                Layout.preferredWidth: 60; Layout.preferredHeight: 20
                                radius: 4
                                color: {
                                    var st = modelData.status || "";
                                    if (st === "success") return EmbryStyle.colors.statusOkBg;
                                    if (st === "failed") return EmbryStyle.colors.statusCriticalBg;
                                    return Qt.rgba(1, 1, 1, 0.08);
                                }
                                Text {
                                    anchors.centerIn: parent
                                    text: (modelData.status || "unknown").toUpperCase()
                                    font.pixelSize: 9; font.weight: Font.Bold
                                    color: {
                                        var st = modelData.status || "";
                                        if (st === "success") return EmbryStyle.colors.statusOk;
                                        if (st === "failed") return EmbryStyle.colors.statusCritical;
                                        return EmbryStyle.colors.textMuted;
                                    }
                                }
                            }

                            // Tier
                            Text {
                                Layout.preferredWidth: 60
                                text: {
                                    var cs = modelData.changes || [];
                                    if (cs.length === 0) return "-";
                                    var tiers = cs.map(function(c) { return c.tier || 0; });
                                    return "T" + Math.min.apply(null, tiers);
                                }
                                font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textSecondary
                            }

                            // Branch
                            Text {
                                Layout.preferredWidth: 120
                                text: modelData.branch || ""
                                font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textMuted
                                elide: Text.ElideRight
                            }

                            // Persona
                            Text {
                                Layout.preferredWidth: 120
                                text: modelData.persona || ""
                                font.pixelSize: EmbryStyle.text.xs
                                color: EmbryStyle.colors.textSecondary
                                elide: Text.ElideRight
                            }

                            // Description
                            Text {
                                Layout.fillWidth: true
                                text: {
                                    var cs = modelData.changes || [];
                                    if (cs.length === 0) return modelData.description || "";
                                    return cs.map(function(c) { return c.description || ""; }).join("; ");
                                }
                                font.pixelSize: EmbryStyle.text.xs
                                color: EmbryStyle.colors.textSecondary
                                elide: Text.ElideRight
                            }

                            // Delta improvement
                            Text {
                                Layout.preferredWidth: 80
                                text: {
                                    var before = modelData.delta_before || 0;
                                    var after = modelData.delta_after || 0;
                                    var diff = after - before;
                                    if (diff > 0) return "+" + (diff * 100).toFixed(1) + "%";
                                    if (diff < 0) return (diff * 100).toFixed(1) + "%";
                                    return "-";
                                }
                                font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                                font.weight: Font.SemiBold
                                color: {
                                    var diff = (modelData.delta_after || 0) - (modelData.delta_before || 0);
                                    if (diff > 0) return EmbryStyle.colors.statusOk;
                                    if (diff < 0) return EmbryStyle.colors.statusCritical;
                                    return EmbryStyle.colors.textGhost;
                                }
                                horizontalAlignment: Text.AlignRight
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: selectedEntry = index
                        }

                        Accessible.name: "Commit " + (modelData.commit_sha || "").substring(0, 7) + " " + (modelData.status || "")
                        Accessible.role: Accessible.ListItem
                    }

                    Text {
                        anchors.centerIn: parent
                        text: "No write-back history yet"
                        font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                        visible: historyList.count === 0
                    }
                }
            }
        }

        // -- Detail Panel (selected entry) --
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: selectedEntry >= 0 ? detailCol.implicitHeight + EmbryStyle.layout.space4 : 0
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border
            visible: selectedEntry >= 0 && selectedEntry < history.length
            clip: true

            ColumnLayout {
                id: detailCol
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                Text {
                    text: "Code Changes"
                    font.pixelSize: EmbryStyle.text.base; font.weight: Font.SemiBold
                    color: EmbryStyle.colors.textPrimary
                }

                Repeater {
                    model: {
                        if (selectedEntry < 0 || selectedEntry >= history.length) return [];
                        return history[selectedEntry].changes || [];
                    }

                    RowLayout {
                        required property var modelData
                        spacing: EmbryStyle.layout.space2

                        Rectangle {
                            width: 24; height: 18; radius: 4
                            color: EmbryStyle.colors.statusInfoBg
                            Text { anchors.centerIn: parent; text: "T" + (modelData.tier || 0); font.pixelSize: 9; font.weight: Font.Bold; color: EmbryStyle.colors.accent }
                        }

                        Text {
                            text: modelData.file || ""
                            font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.accentGreen
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.description || ""
                            font.pixelSize: EmbryStyle.text.sm
                            color: EmbryStyle.colors.textSecondary
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        // -- Action Row --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            EmbryButton {
                text: "Rollback Selected"
                variant: "danger"
                enabled: selectedEntry >= 0 && selectedEntry < history.length
                onClicked: {
                    if (bridge && selectedEntry >= 0) {
                        var sha = history[selectedEntry].commit_sha || "";
                        if (sha) bridge.rollback(sha);
                    }
                }
                Accessible.name: "Rollback selected commit"; Accessible.role: Accessible.Button
            }
            EmbryButton {
                text: "Refresh"; onClicked: if (bridge) bridge.refresh()
                Accessible.name: "Refresh write-back history"; Accessible.role: Accessible.Button
            }

            Item { Layout.fillWidth: true }

            Text {
                text: {
                    var successes = history.filter(function(h) { return h.status === "success"; }).length;
                    return successes + " successful / " + history.length + " total";
                }
                font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textGhost
            }
        }
    }
}
