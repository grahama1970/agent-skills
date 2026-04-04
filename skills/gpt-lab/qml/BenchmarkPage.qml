import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// BenchmarkPage -- Configure and run task benchmarks across models.

Item {
    id: root

    property var registry: appWindow.registry
    property var allModels: {
        var c = (registry && registry.candidate_models) || []
        var a = (registry && registry.api_models) || []
        return c.concat(a)
    }
    property var selectedModels: ({})
    property var results: []
    property string taskName: ""

    Connections {
        target: gptBridge
        function onBenchmarkResultJsonChanged() {
            try {
                root.results = JSON.parse(gptBridge.benchmarkResultJson)
            } catch (_) {
                root.results = []
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Task Selector --
        Text {
            text: "Task Benchmark"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        RowLayout {
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Task:"
                font.pixelSize: EmbryStyle.text.base
                color: EmbryStyle.colors.textSecondary
            }

            EmbryTextField {
                id: taskField
                Layout.preferredWidth: 240
                placeholderText: "e.g. qra-validator"
                text: root.taskName
                onTextChanged: root.taskName = text
                Accessible.name: "Task name input"
            }
        }

        // -- Model Checklist --
        Text {
            text: "Select Models"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textSecondary
        }

        Rectangle {
            Layout.fillWidth: true
            height: Math.min(120, modelChecklist.contentHeight + 8)
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ListView {
                id: modelChecklist
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space1
                clip: true
                model: allModels

                delegate: CheckBox {
                    width: modelChecklist.width
                    text: modelData.name || ""
                    font.pixelSize: EmbryStyle.text.sm
                    checked: !!(root.selectedModels[modelData.name || ""])
                    onCheckedChanged: {
                        var copy = Object.assign({}, root.selectedModels)
                        if (checked) {
                            copy[modelData.name || ""] = true
                        } else {
                            delete copy[modelData.name || ""]
                        }
                        root.selectedModels = copy
                    }
                    Accessible.name: (modelData.name || "") + " checkbox"
                    Accessible.role: Accessible.CheckBox
                }
            }
        }

        // -- Benchmark Params --
        RowLayout {
            spacing: EmbryStyle.layout.space4

            Text { text: "Samples:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }
            SpinBox {
                id: sampleSpin
                from: 10
                to: 1000
                stepSize: 10
                value: 100
                Accessible.name: "Sample count"
                Accessible.role: Accessible.SpinBox
            }

            Text { text: "Temperature:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }
            EmbryTextField {
                id: tempField
                Layout.preferredWidth: 60
                text: "0.0"
                Accessible.name: "Temperature input"
            }
        }

        // -- Action Buttons --
        RowLayout {
            spacing: EmbryStyle.layout.space3

            EmbryButton {
                text: "Run Benchmark"
                variant: "primary"
                enabled: root.taskName.length > 0 && Object.keys(root.selectedModels).length > 0
                onClicked: {
                    var models = JSON.stringify(Object.keys(root.selectedModels))
                    gptBridge.runBenchmark(root.taskName, models, sampleSpin.value)
                }
                Accessible.name: "Run benchmark button"
                Accessible.role: Accessible.Button
            }

            EmbryButton {
                text: "Compare"
                enabled: Object.keys(root.selectedModels).length === 2
                onClicked: {
                    var names = Object.keys(root.selectedModels)
                    gptBridge.runCompare(root.taskName, names[0], names[1])
                }
                Accessible.name: "Compare two models button"
                Accessible.role: Accessible.Button
            }

            EmbryButton {
                text: "Find Minimum"
                enabled: root.taskName.length > 0
                onClicked: {
                    gptBridge.findMinimum(root.taskName, 0.85)
                }
                Accessible.name: "Find minimum viable model button"
                Accessible.role: Accessible.Button
            }
        }

        // -- Results Table --
        Text {
            text: "Results"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textSecondary
            visible: root.results.length > 0
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border
            visible: root.results.length > 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Header
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: EmbryStyle.colors.bgInput

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: EmbryStyle.layout.space3
                        anchors.rightMargin: EmbryStyle.layout.space3
                        spacing: EmbryStyle.layout.space2

                        Text { Layout.preferredWidth: 200; text: "Model"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 70;  text: "Accuracy"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 70;  text: "Agreement"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 70;  text: "Lat P50"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 70;  text: "Lat P99"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 70;  text: "Mem MB"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 80;  text: "Verdict"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                ListView {
                    id: resultsView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: root.results

                    delegate: Rectangle {
                        width: resultsView.width
                        height: 36
                        color: index % 2 === 0 ? "transparent" : EmbryStyle.colors.bgHover

                        Accessible.name: (modelData.model || "") + " result row"
                        Accessible.role: Accessible.ListItem

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: EmbryStyle.layout.space3
                            anchors.rightMargin: EmbryStyle.layout.space3
                            spacing: EmbryStyle.layout.space2

                            Text { Layout.preferredWidth: 200; text: modelData.model || ""; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                            Text { Layout.preferredWidth: 70;  text: ((modelData.accuracy || 0) * 100).toFixed(1) + "%"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.accentGreen }
                            Text { Layout.preferredWidth: 70;  text: ((modelData.agreement || 0) * 100).toFixed(1) + "%"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textPrimary }
                            Text { Layout.preferredWidth: 70;  text: (modelData.latency_p50 || 0).toFixed(0) + "ms"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textPrimary }
                            Text { Layout.preferredWidth: 70;  text: (modelData.latency_p99 || 0).toFixed(0) + "ms"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
                            Text { Layout.preferredWidth: 70;  text: (modelData.memory_mb || 0).toFixed(0); font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textPrimary }

                            // WORTH_IT verdict badge
                            Rectangle {
                                Layout.preferredWidth: 80
                                width: verdictText.implicitWidth + EmbryStyle.layout.space3
                                height: 20
                                radius: EmbryStyle.layout.badgeRadius
                                color: (modelData.worth_it || false)
                                    ? EmbryStyle.colors.statusOkBg
                                    : EmbryStyle.colors.statusCriticalBg

                                Text {
                                    id: verdictText
                                    anchors.centerIn: parent
                                    text: (modelData.worth_it || false) ? "WORTH IT" : "NOT WORTH"
                                    font.pixelSize: EmbryStyle.text.xs
                                    font.weight: EmbryStyle.text.weightBold
                                    color: (modelData.worth_it || false)
                                        ? EmbryStyle.colors.accentGreen
                                        : EmbryStyle.colors.accentRed
                                }
                            }
                        }
                    }
                }
            }
        }

        // Placeholder when no results
        Text {
            visible: root.results.length === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: "No benchmark results yet. Select models and run a benchmark."
            font.pixelSize: EmbryStyle.text.base
            color: EmbryStyle.colors.textSubtle
        }
    }
}
