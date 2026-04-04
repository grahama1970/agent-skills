import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var shadowStatus: bridge ? JSON.parse(bridge.shadowStatusJson) : []
    property int selectedTask: -1

    property string avgAgreement: {
        var sum = 0; var n = 0;
        for (var i = 0; i < shadowStatus.length; i++) { sum += (shadowStatus[i].agreement_rate || 0); n++; }
        return n > 0 ? (sum / n * 100).toFixed(1) + "%" : "-";
    }
    property int readyToPromote: shadowStatus.filter(function(s) { return (s.agreement_rate || 0) >= 0.90 && (s.sample_count || 0) >= 50; }).length
    property int needRetrain: shadowStatus.filter(function(s) { return (s.agreement_rate || 0) < 0.70 && (s.sample_count || 0) >= 50; }).length

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        Text {
            text: "Shadow Mode Status"
            font.pixelSize: EmbryStyle.text.lg; font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        // -- Summary Row --
        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3

            Repeater {
                model: [
                    { label: "Tasks Tracked", val: shadowStatus.length },
                    { label: "Avg Agreement", val: avgAgreement },
                    { label: "Ready to Promote", val: readyToPromote },
                    { label: "Need Retrain", val: needRetrain },
                ]

                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true; Layout.preferredHeight: 64
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1; border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.centerIn: parent; spacing: 4
                        Text { Layout.alignment: Qt.AlignHCenter; text: "" + modelData.val; font.pixelSize: EmbryStyle.text.lg; font.weight: Font.Bold; color: EmbryStyle.colors.textPrimary }
                        Text { Layout.alignment: Qt.AlignHCenter; text: modelData.label; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.SemiBold; color: EmbryStyle.colors.textMuted }
                    }
                }
            }
        }

        // -- Shadow Table --
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1; border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                spacing: 0

                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: 28
                    color: Qt.rgba(1, 1, 1, 0.03); radius: EmbryStyle.layout.radiusSm

                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
                        Text { Layout.preferredWidth: 200; text: "Task"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 100; text: "Agreement"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 80; text: "Samples"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 100; text: "Model Type"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.fillWidth: true; text: "Recommendation"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    }
                }

                ListView {
                    id: shadowList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; model: shadowStatus; spacing: 1

                    delegate: Rectangle {
                        required property var modelData; required property int index
                        width: shadowList.width; height: 34
                        radius: EmbryStyle.layout.radiusSm
                        color: index === selectedTask ? EmbryStyle.colors.selectBg
                             : index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                        property real agreement: modelData.agreement_rate || 0
                        property int samples: modelData.sample_count || 0

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8

                            Text { Layout.preferredWidth: 200; text: modelData.task || ""; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }

                            // Agreement with color bar
                            RowLayout {
                                Layout.preferredWidth: 100; spacing: 4

                                Rectangle {
                                    Layout.preferredWidth: 40; Layout.preferredHeight: 6; radius: 3
                                    color: Qt.rgba(1, 1, 1, 0.08)
                                    Rectangle {
                                        width: parent.width * Math.min(1, agreement); height: parent.height; radius: 3
                                        color: agreement >= 0.90 ? EmbryStyle.colors.statusOk
                                             : agreement >= 0.70 ? EmbryStyle.colors.statusWarning
                                             : EmbryStyle.colors.statusCritical
                                    }
                                }
                                Text {
                                    text: (agreement * 100).toFixed(1) + "%"
                                    font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                                    color: agreement >= 0.90 ? EmbryStyle.colors.statusOk
                                         : agreement >= 0.70 ? EmbryStyle.colors.statusWarning
                                         : EmbryStyle.colors.statusCritical
                                }
                            }

                            Text { Layout.preferredWidth: 80; text: "" + samples; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                            Text { Layout.preferredWidth: 100; text: modelData.model_type || "-"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textMuted }

                            // Recommendation badge
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 20; Layout.maximumWidth: recText.implicitWidth + 12
                                radius: 4
                                color: {
                                    if (samples < 50) return EmbryStyle.colors.badge;
                                    if (agreement >= 0.90) return EmbryStyle.colors.statusOkBg;
                                    if (agreement >= 0.80) return EmbryStyle.colors.statusInfoBg;
                                    if (agreement >= 0.70) return EmbryStyle.colors.statusWarningBg;
                                    return EmbryStyle.colors.statusCriticalBg;
                                }
                                Text {
                                    id: recText; anchors.centerIn: parent
                                    text: {
                                        if (samples < 50) return "NEED DATA";
                                        if (agreement >= 0.90) return "PROMOTE";
                                        if (agreement >= 0.80) return "PLATEAU";
                                        if (agreement >= 0.70) return "RETRAIN";
                                        return "LOW AGREE";
                                    }
                                    font.pixelSize: 8; font.weight: Font.Bold
                                    color: {
                                        if (samples < 50) return EmbryStyle.colors.textMuted;
                                        if (agreement >= 0.90) return EmbryStyle.colors.statusOk;
                                        if (agreement >= 0.80) return EmbryStyle.colors.statusInfo;
                                        if (agreement >= 0.70) return EmbryStyle.colors.statusWarning;
                                        return EmbryStyle.colors.statusCritical;
                                    }
                                }
                            }
                        }

                        MouseArea { anchors.fill: parent; onClicked: selectedTask = index }
                        Accessible.name: (modelData.task || "") + " agreement " + (agreement * 100).toFixed(0) + " percent"; Accessible.role: Accessible.ListItem
                    }

                    Text {
                        anchors.centerIn: parent; text: "No shadow data — run ./run.sh status"
                        font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                        visible: shadowList.count === 0
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true; spacing: EmbryStyle.layout.space3
            EmbryButton { text: "Refresh"; onClicked: if (bridge) bridge.refresh(); Accessible.name: "Refresh shadow status"; Accessible.role: Accessible.Button }
            Item { Layout.fillWidth: true }
        }
    }
}
