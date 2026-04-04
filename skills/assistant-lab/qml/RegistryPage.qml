import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var registry: bridge ? JSON.parse(bridge.registryJson) : {}
    property string filterType: "all"
    property int selectedRow: -1

    property var allModels: {
        var items = [];
        var vals = registry.validators || {};
        for (var v in vals) items.push({task: v, type: "validator", data: vals[v]});
        var cls = registry.classifiers || {};
        for (var c in cls) items.push({task: c, type: "classifier", data: cls[c]});
        var regs = registry.regressors || {};
        for (var r in regs) items.push({task: r, type: "regressor", data: regs[r]});
        if (filterType !== "all") items = items.filter(function(i) { return i.type === filterType; });
        return items;
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Summary Cards --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            Repeater {
                model: [
                    { label: "Validators", count: Object.keys(registry.validators || {}).length, color: EmbryStyle.colors.accentGreen },
                    { label: "Classifiers", count: Object.keys(registry.classifiers || {}).length, color: EmbryStyle.colors.accent },
                    { label: "Regressors", count: Object.keys(registry.regressors || {}).length, color: EmbryStyle.colors.accentAmber },
                ]

                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true; Layout.preferredHeight: 64
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1; border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.centerIn: parent; spacing: 4
                        Text { Layout.alignment: Qt.AlignHCenter; text: "" + modelData.count; font.pixelSize: EmbryStyle.text.xl; font.weight: Font.Bold; color: modelData.color }
                        Text { Layout.alignment: Qt.AlignHCenter; text: modelData.label; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.SemiBold; color: EmbryStyle.colors.textMuted }
                    }
                    Accessible.name: modelData.label + " count " + modelData.count; Accessible.role: Accessible.StaticText
                }
            }

            // Shadow vs promoted
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 64
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1; border.color: EmbryStyle.colors.border

                property int shadowCount: {
                    var count = 0;
                    var all = root.allModels;
                    for (var i = 0; i < all.length; i++) if (all[i].data.shadow_mode) count++;
                    return count;
                }

                ColumnLayout {
                    anchors.centerIn: parent; spacing: 4
                    Text { Layout.alignment: Qt.AlignHCenter; text: parent.parent.shadowCount + " shadow"; font.pixelSize: EmbryStyle.text.base; font.weight: Font.Bold; color: EmbryStyle.colors.statusWarning }
                    Text { Layout.alignment: Qt.AlignHCenter; text: (root.allModels.length - parent.parent.shadowCount) + " promoted"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.statusOk }
                }
            }
        }

        // -- Filter + Table --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            Text { text: "Filter:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
            EmbryComboBox {
                Layout.preferredWidth: 140
                model: ["all", "validator", "classifier", "regressor"]
                onCurrentTextChanged: root.filterType = currentText
                Accessible.name: "Filter by model type"
            }

            Item { Layout.fillWidth: true }

            Text {
                text: allModels.length + " models"
                font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textGhost
            }
        }

        // -- Model Table --
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
                        Text { Layout.preferredWidth: 180; text: "Task"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 80; text: "Type"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 70; text: "Threshold"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 70; text: "CV Acc"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 70; text: "Samples"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 60; text: "Status"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.fillWidth: true; text: "Note"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    }
                }

                ListView {
                    id: modelList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; model: allModels; spacing: 1

                    delegate: Rectangle {
                        required property var modelData; required property int index
                        width: modelList.width; height: 32
                        radius: EmbryStyle.layout.radiusSm
                        color: index === selectedRow ? EmbryStyle.colors.selectBg
                             : index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                            Text { Layout.preferredWidth: 180; text: modelData.task; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }

                            // Type badge
                            Rectangle {
                                Layout.preferredWidth: 80; Layout.preferredHeight: 20; radius: 4
                                color: {
                                    if (modelData.type === "validator") return EmbryStyle.colors.statusOkBg;
                                    if (modelData.type === "classifier") return EmbryStyle.colors.statusInfoBg;
                                    return EmbryStyle.colors.statusWarningBg;
                                }
                                Text {
                                    anchors.centerIn: parent; text: modelData.type.toUpperCase()
                                    font.pixelSize: 9; font.weight: Font.Bold
                                    color: {
                                        if (modelData.type === "validator") return EmbryStyle.colors.accentGreen;
                                        if (modelData.type === "classifier") return EmbryStyle.colors.accent;
                                        return EmbryStyle.colors.accentAmber;
                                    }
                                }
                            }

                            Text { Layout.preferredWidth: 70; text: (modelData.data.confidence_threshold || 0).toFixed(2); font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                            Text { Layout.preferredWidth: 70; text: modelData.data.cv_accuracy ? modelData.data.cv_accuracy.toFixed(3) : "-"; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                            Text { Layout.preferredWidth: 70; text: modelData.data.training_samples ? "" + modelData.data.training_samples : "-"; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }

                            // Shadow/promoted badge
                            Rectangle {
                                Layout.preferredWidth: 60; Layout.preferredHeight: 18; radius: 4
                                color: modelData.data.shadow_mode ? EmbryStyle.colors.statusWarningBg : EmbryStyle.colors.statusOkBg
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.data.shadow_mode ? "SHADOW" : "LIVE"
                                    font.pixelSize: 8; font.weight: Font.Bold
                                    color: modelData.data.shadow_mode ? EmbryStyle.colors.statusWarning : EmbryStyle.colors.statusOk
                                }
                            }

                            Text { Layout.fillWidth: true; text: modelData.data.note || ""; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textGhost; elide: Text.ElideRight }
                        }

                        MouseArea { anchors.fill: parent; onClicked: selectedRow = index }
                        Accessible.name: modelData.task + " " + modelData.type; Accessible.role: Accessible.ListItem
                    }
                }
            }
        }

        // -- Action Row --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3
            EmbryButton { text: "Refresh"; onClicked: if (bridge) bridge.refresh(); Accessible.name: "Refresh registry"; Accessible.role: Accessible.Button }
            Item { Layout.fillWidth: true }
        }
    }
}
