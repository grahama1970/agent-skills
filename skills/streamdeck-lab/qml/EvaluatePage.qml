import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// EvaluatePage -- 5-tier weighted scoring for Stream Deck templates.

Item {
    id: root

    required property QtObject deckBridge
    property var evalResult: null
    property var allResults: []
    property string selectedTemplate: ""

    function parseResult() {
        try {
            evalResult = JSON.parse(deckBridge.evaluateResultJson || "null")
        } catch(e) {
            evalResult = null
        }
    }

    Connections {
        target: deckBridge
        function onEvaluateResultJsonChanged() { parseResult() }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // -- Header --
        RowLayout {
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Template Evaluation"
                font.pixelSize: EmbryStyle.text.lg
                font.weight: Font.Bold
                color: EmbryStyle.colors.textPrimary
            }

            Item { Layout.fillWidth: true }

            Text { text: "Template:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }

            EmbryComboBox {
                id: templateCombo
                model: {
                    try {
                        var tpls = JSON.parse(deckBridge.templatesJson || "[]")
                        return tpls.map(function(t) { return t.name || t.template || "" })
                    } catch(e) { return [] }
                }
                implicitWidth: 200
                onCurrentTextChanged: selectedTemplate = currentText
                Accessible.name: "Template selector"
            }

            EmbryButton {
                text: "Run Evaluate"
                variant: "primary"
                onClicked: deckBridge.evaluate(selectedTemplate)
                Accessible.name: "Run evaluation"; Accessible.role: Accessible.Button
            }

            EmbryButton {
                text: "Evaluate All"
                onClicked: deckBridge.evaluateAll()
                Accessible.name: "Evaluate all templates"; Accessible.role: Accessible.Button
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

        // -- Score Breakdown + Gauge --
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space4

            // Left: Score cards
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: EmbryStyle.layout.space2

                // Tier 1: Workflow Coverage (40%)
                ScoreCard {
                    tierName: "Workflow Coverage"
                    weight: "40%"
                    score: evalResult ? (evalResult.scores || {}).workflow_coverage || 0 : 0
                    detail: ""
                    accentColor: EmbryStyle.colors.accentGreen
                }

                // Tier 2: Icon Appropriateness (20%)
                ScoreCard {
                    tierName: "Icon Appropriateness"
                    weight: "20%"
                    score: evalResult ? (evalResult.scores || {}).icon_appropriateness || 0 : 0
                    detail: evalResult && evalResult.icons_missing > 0 ? evalResult.icons_missing + " missing icons" : ""
                    accentColor: EmbryStyle.colors.accent
                }

                // Tier 3: Navigation (15%)
                ScoreCard {
                    tierName: "Navigation"
                    weight: "15%"
                    score: evalResult ? (evalResult.scores || {}).navigation || 0 : 0
                    detail: evalResult ? "back=" + ((evalResult.scores || {}).navigation >= 0.5 ? "yes" : "no") : ""
                    accentColor: EmbryStyle.colors.accentAmber
                }

                // Tier 4: Layout Density (15%)
                ScoreCard {
                    tierName: "Layout Density"
                    weight: "15%"
                    score: evalResult ? (evalResult.scores || {}).layout_density || 0 : 0
                    detail: evalResult ? (evalResult.non_empty_buttons || 0) + " buttons (6-24 range)" : ""
                    accentColor: EmbryStyle.colors.accentAmber
                }

                // Tier 5: Palette Compliance (10%)
                ScoreCard {
                    tierName: "Palette Compliance"
                    weight: "10%"
                    score: evalResult ? (evalResult.scores || {}).palette_compliance || 0 : 0
                    detail: "NVIS color check, label length"
                    accentColor: EmbryStyle.colors.accent
                }

                Item { Layout.fillHeight: true }
            }

            // Right: Overall gauge
            Rectangle {
                Layout.preferredWidth: 200
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1
                border.color: EmbryStyle.colors.border

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: EmbryStyle.layout.space3

                    Text {
                        text: "Overall Score"
                        font.pixelSize: EmbryStyle.text.base
                        font.weight: Font.DemiBold
                        color: EmbryStyle.colors.textSecondary
                        Layout.alignment: Qt.AlignHCenter
                    }

                    // Gauge circle
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 120; height: 120
                        radius: 60
                        color: "transparent"
                        border.width: 6
                        border.color: {
                            var s = evalResult ? (evalResult.total_score || 0) : 0
                            if (s >= 0.85) return EmbryStyle.colors.statusOk
                            if (s >= 0.5) return EmbryStyle.colors.statusWarning
                            return EmbryStyle.colors.statusCritical
                        }

                        Text {
                            anchors.centerIn: parent
                            text: evalResult ? (evalResult.total_score * 100).toFixed(1) + "%" : "--"
                            font.pixelSize: EmbryStyle.text.xl
                            font.weight: Font.Bold
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textPrimary
                        }
                    }

                    // Pass/Fail badge
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: passFailText.implicitWidth + EmbryStyle.layout.space4
                        height: EmbryStyle.layout.badgeHeight + 4
                        radius: EmbryStyle.layout.badgeRadius
                        color: {
                            if (!evalResult) return EmbryStyle.colors.badge
                            return evalResult.pass ? EmbryStyle.colors.statusOkBg : EmbryStyle.colors.statusCriticalBg
                        }

                        Text {
                            id: passFailText
                            anchors.centerIn: parent
                            text: {
                                if (!evalResult) return "NO DATA"
                                return evalResult.pass ? "PASS (>= 0.85)" : "FAIL (< 0.85)"
                            }
                            font.pixelSize: 9
                            font.weight: Font.Bold
                            color: {
                                if (!evalResult) return EmbryStyle.colors.textMuted
                                return evalResult.pass ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusCritical
                            }
                        }
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "Pass threshold: 0.85"
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textMuted
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

        // -- Results Table --
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 160
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space1

                // Table header
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Repeater {
                        model: ["Template", "Overall", "Coverage", "Icons", "Nav", "Density", "Palette", "Result"]
                        Text {
                            Layout.fillWidth: index === 0
                            Layout.preferredWidth: index === 0 ? -1 : 65
                            text: modelData
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: Font.Bold
                            color: EmbryStyle.colors.textMuted
                        }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                ListView {
                    id: resultsTable
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: {
                        try {
                            var r = JSON.parse(deckBridge.evaluateResultJson || "null")
                            if (r && Array.isArray(r)) return r
                            if (r && r.template) return [r]
                            return []
                        } catch(e) { return [] }
                    }
                    spacing: 1

                    delegate: RowLayout {
                        width: resultsTable.width
                        spacing: 0
                        property var scores: modelData.scores || {}

                        Accessible.name: (modelData.template || "template") + " score " + ((modelData.total_score || 0) * 100).toFixed(1) + "% " + (modelData.pass ? "pass" : "fail")
                        Accessible.role: Accessible.ListItem

                        Text { Layout.fillWidth: true; text: modelData.template || ""; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                        Text { Layout.preferredWidth: 65; text: ((modelData.total_score || 0) * 100).toFixed(1) + "%"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textPrimary }
                        Text { Layout.preferredWidth: 65; text: ((scores.workflow_coverage || 0) * 100).toFixed(0) + "%"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 65; text: ((scores.icon_appropriateness || 0) * 100).toFixed(0) + "%"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 65; text: ((scores.navigation || 0) * 100).toFixed(0) + "%"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 65; text: ((scores.layout_density || 0) * 100).toFixed(0) + "%"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 65; text: ((scores.palette_compliance || 0) * 100).toFixed(0) + "%"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                        Rectangle {
                            Layout.preferredWidth: 50; height: 18; radius: 4
                            color: modelData.pass ? EmbryStyle.colors.statusOkBg : EmbryStyle.colors.statusCriticalBg
                            Text { anchors.centerIn: parent; text: modelData.pass ? "PASS" : "FAIL"; font.pixelSize: 8; font.weight: Font.Bold; color: modelData.pass ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusCritical }
                        }
                    }
                }
            }
        }
    }

    // -- ScoreCard component --
    component ScoreCard: Rectangle {
        property string tierName: ""
        property string weight: ""
        property real score: 0
        property string detail: ""
        property color accentColor: EmbryStyle.colors.accent

        Layout.fillWidth: true
        height: 52
        radius: EmbryStyle.layout.radiusSm
        color: EmbryStyle.colors.bgElevated
        border.width: 1
        border.color: EmbryStyle.colors.border

        RowLayout {
            anchors.fill: parent
            anchors.margins: EmbryStyle.layout.space2
            spacing: EmbryStyle.layout.space3

            ColumnLayout {
                spacing: 1
                Layout.preferredWidth: 160
                RowLayout {
                    spacing: EmbryStyle.layout.space2
                    Text { text: tierName; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.DemiBold; color: EmbryStyle.colors.textPrimary }
                    Rectangle {
                        width: weightLbl.implicitWidth + 6; height: 16; radius: 4
                        color: EmbryStyle.colors.badge
                        Text { id: weightLbl; anchors.centerIn: parent; text: weight; font.pixelSize: 8; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    }
                }
                Text { text: detail; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted; visible: detail !== "" }
            }

            // Score bar
            Rectangle {
                Layout.fillWidth: true
                height: 8
                radius: 4
                color: EmbryStyle.colors.bgInput

                Rectangle {
                    width: parent.width * Math.min(score, 1.0)
                    height: parent.height
                    radius: 4
                    color: accentColor

                    Behavior on width { NumberAnimation { duration: 300 } }
                }
            }

            Text {
                Layout.preferredWidth: 40
                text: (score * 100).toFixed(0) + "%"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: Font.Bold
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textPrimary
                horizontalAlignment: Text.AlignRight
            }
        }

        Accessible.name: tierName + " score " + (score * 100).toFixed(0) + " percent"
        Accessible.role: Accessible.ProgressBar
    }
}
