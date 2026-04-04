import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    // ── Properties ──────────────────────────────────────────
    property var bridge: null
    property var promoteState: bridge ? JSON.parse(bridge.promoteStateJson) : null

    // ── Layout ──────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // ── Header ───────────────────────────────────────────
        Text {
            text: "QRA Promotion Pipeline"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: Font.SemiBold
            color: EmbryStyle.colors.textPrimary
        }

        Text {
            text: "Harvest satisfactory turns → deduplicate → assess → promote to sparta_qra"
            font.pixelSize: EmbryStyle.text.sm
            color: EmbryStyle.colors.textMuted
        }

        // ── Pipeline Stage Cards ─────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Repeater {
                model: [
                    { stage: "HARVEST", key: "harvested", icon: "⬇", color: EmbryStyle.colors.accent },
                    { stage: "DEDUP", key: "deduplicated", icon: "⊘", color: EmbryStyle.colors.accentYellow },
                    { stage: "ASSESS", key: "assessed", icon: "✓", color: EmbryStyle.colors.accentAmber },
                    { stage: "PROMOTE", key: "promoted", icon: "★", color: EmbryStyle.colors.statusOk },
                ]

                Rectangle {
                    required property var modelData
                    required property int index

                    Layout.fillWidth: true
                    Layout.preferredHeight: 100

                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 6

                        // Icon
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: modelData.icon
                            font.pixelSize: EmbryStyle.text.xl
                            color: modelData.color
                        }

                        // Count
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: promoteState ? (promoteState[modelData.key] || 0) : "—"
                            font.pixelSize: EmbryStyle.text.xxl
                            font.weight: Font.Bold
                            color: EmbryStyle.colors.textPrimary
                        }

                        // Label
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: modelData.stage
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.SemiBold
                            color: EmbryStyle.colors.textMuted
                            font.letterSpacing: 1
                        }
                    }

                    // Arrow connector (except last)
                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: -14
                        anchors.verticalCenter: parent.verticalCenter
                        text: "→"
                        font.pixelSize: EmbryStyle.text.lg
                        color: EmbryStyle.colors.textGhost
                        visible: index < 3
                        z: 1
                    }

                    Accessible.name: modelData.stage + ": " + (promoteState ? (promoteState[modelData.key] || 0) : "unknown")
                    Accessible.role: Accessible.StaticText
                }
            }
        }

        // ── Additional Metrics ───────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: detailsColumn.implicitHeight + EmbryStyle.layout.space4

            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ColumnLayout {
                id: detailsColumn

                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                Text {
                    text: "Pipeline Details"
                    font.pixelSize: EmbryStyle.text.base
                    font.weight: Font.SemiBold
                    color: EmbryStyle.colors.textPrimary
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 4
                    rowSpacing: EmbryStyle.layout.space2
                    columnSpacing: EmbryStyle.layout.space4

                    Repeater {
                        model: [
                            { label: "Staged (pending review)", key: "staged" },
                            { label: "Rejected (quality gate)", key: "rejected" },
                            { label: "Failed (errors)", key: "failed" },
                            { label: "Lean4 verified", key: "lean4_verified" },
                            { label: "Lean4 failed", key: "lean4_failed" },
                            { label: "Total candidates", key: "total_candidates" },
                        ]

                        RowLayout {
                            required property var modelData

                            spacing: EmbryStyle.layout.space2

                            Text {
                                text: modelData.label + ":"
                                font.pixelSize: EmbryStyle.text.sm
                                color: EmbryStyle.colors.textMuted
                            }

                            Text {
                                text: promoteState ? (promoteState[modelData.key] || 0) : "—"
                                font.pixelSize: EmbryStyle.text.sm
                                font.weight: Font.SemiBold
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textPrimary
                            }
                        }
                    }
                }
            }
        }

        // Spacer
        Item { Layout.fillHeight: true }

        // ── Action Row ───────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            EmbryButton {
                text: "Run Nightly Promote"
                variant: "primary"
                onClicked: if (bridge) bridge.runPromoteNightly(false)

                Accessible.name: "Run nightly QRA promotion"
                Accessible.role: Accessible.Button
                Accessible.description: "Scan sessions and promote qualifying QRAs to sparta_qra"
            }

            EmbryButton {
                text: "Dry Run"
                onClicked: if (bridge) bridge.runPromoteNightly(true)

                Accessible.name: "Dry run promotion"
                Accessible.role: Accessible.Button
                Accessible.description: "Count candidates without promoting"
            }

            Item { Layout.fillWidth: true }

            Text {
                visible: promoteState !== null && promoteState.last_run
                text: promoteState ? "Last run: " + (promoteState.last_run || "") : ""
                font.pixelSize: EmbryStyle.text.xs
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textGhost
            }
        }
    }
}
