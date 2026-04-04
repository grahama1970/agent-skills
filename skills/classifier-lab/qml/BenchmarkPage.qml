import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// BenchmarkPage -- compare multiple backbones on the same dataset.
// Multi-select checklist, results table with winner highlight.

Item {
    id: benchmarkPage

    property var results: {
        try { return JSON.parse(classifierBridge.benchmarkResultJson || "[]") }
        catch (e) { return [] }
    }
    property int winnerIdx: {
        if (results.length === 0) return -1
        var best = -1; var bestF1 = -1
        for (var i = 0; i < results.length; i++) {
            var f1 = parseFloat(results[i].macro_f1 || 0)
            if (f1 > bestF1) { bestF1 = f1; best = i }
        }
        return best
    }

    readonly property var availableBackbones: [
        "efficientnet_b0", "efficientnet_b2", "resnet50",
        "convnextv2_nano", "mobilenetv3_small", "distilbert",
        "prajjwal1/bert-tiny", "tfidf_logreg", "tfidf_svm",
        "gradient_boosting", "random_forest",
    ]

    // Track checked state per backbone
    property var checkedState: {
        var s = {}
        for (var i = 0; i < availableBackbones.length; i++) {
            s[availableBackbones[i]] = (i < 3)  // default: first 3 checked
        }
        return s
    }

    function getSelectedBackbones() {
        var sel = []
        for (var k in checkedState) {
            if (checkedState[k]) sel.push(k)
        }
        return sel
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Backbone Checklist -------------------------------------------
        Text {
            text: "Select Backbones"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        Flow {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Repeater {
                model: availableBackbones

                Rectangle {
                    width: cbRow.implicitWidth + EmbryStyle.layout.space3 * 2
                    height: 28
                    radius: EmbryStyle.layout.radiusSm
                    color: checkedState[modelData]
                        ? EmbryStyle.colors.selectBg
                        : EmbryStyle.colors.bgInput
                    border.width: 1
                    border.color: checkedState[modelData]
                        ? EmbryStyle.colors.accentGreen
                        : EmbryStyle.colors.borderInput

                    Row {
                        id: cbRow
                        anchors.centerIn: parent
                        spacing: EmbryStyle.layout.space1

                        CheckBox {
                            id: cb
                            checked: checkedState[modelData] || false
                            onCheckedChanged: {
                                var s = benchmarkPage.checkedState
                                s[modelData] = checked
                                benchmarkPage.checkedState = s
                            }

                            Accessible.name: "Select " + modelData
                            Accessible.role: Accessible.CheckBox
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textPrimary
                        }
                    }
                }
            }
        }

        // -- Run Button ---------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            EmbryButton {
                id: runBenchBtn

                text: classifierBridge.trainingStatus === "benchmarking"
                    ? "Running..." : "Run Benchmark"
                enabled: classifierBridge.trainingStatus !== "benchmarking"
                    && getSelectedBackbones().length > 0

                Accessible.name: "Run benchmark"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: runBenchBtn.enabled
                        ? (runBenchBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput)
                        : EmbryStyle.colors.bgPressed
                    border.width: 1
                    border.color: EmbryStyle.colors.accentGreen
                    radius: EmbryStyle.layout.radiusSm
                }
                contentItem: Text {
                    text: runBenchBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightSemibold
                    color: runBenchBtn.enabled
                        ? EmbryStyle.colors.accentGreen : EmbryStyle.colors.textDisabled
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: {
                    var sel = getSelectedBackbones()
                    classifierBridge.runBenchmark(JSON.stringify(sel))
                }
            }

            Text {
                text: classifierBridge.trainingStatus === "benchmarking"
                    ? "Benchmarking in progress..."
                    : results.length > 0
                        ? results.length + " result(s)"
                        : ""
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textMuted
            }

            Item { Layout.fillWidth: true }
        }

        // -- Results Table ------------------------------------------------
        Text {
            text: "Results"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
            visible: results.length > 0
        }

        // Table header
        Rectangle {
            Layout.fillWidth: true
            height: 30
            color: EmbryStyle.colors.bgElevated
            radius: EmbryStyle.layout.radiusSm
            visible: results.length > 0

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space2
                anchors.rightMargin: EmbryStyle.layout.space2
                spacing: 0

                Repeater {
                    model: ["Model", "Accuracy", "Macro F1", "Precision", "Recall", "Latency", "Size"]

                    Text {
                        Layout.fillWidth: index === 0
                        Layout.preferredWidth: index === 0 ? -1 : 80
                        text: modelData || ""
                        font.pixelSize: EmbryStyle.text.xs
                        font.weight: EmbryStyle.text.weightSemibold
                        color: EmbryStyle.colors.textMuted
                        horizontalAlignment: index === 0 ? Text.AlignLeft : Text.AlignRight
                    }
                }
            }
        }

        // Table rows
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: results
            spacing: 2

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: ListView.view ? ListView.view.width : 0
                height: 34
                radius: EmbryStyle.layout.radiusSm
                color: index === winnerIdx
                    ? EmbryStyle.colors.statusOkBg : EmbryStyle.colors.bgInput
                border.width: index === winnerIdx ? 1 : 0
                border.color: EmbryStyle.colors.accentGreen

                Accessible.name: (modelData.model || modelData.backbone || "model") + " accuracy " + parseFloat(modelData.accuracy || 0).toFixed(4) + (index === winnerIdx ? " winner" : "")
                Accessible.role: Accessible.ListItem

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: EmbryStyle.layout.space2
                    anchors.rightMargin: EmbryStyle.layout.space2
                    spacing: 0

                    Text {
                        Layout.fillWidth: true
                        text: (modelData.model || modelData.backbone || "") + (index === winnerIdx ? " " + EmbryStyle.icons.star : "")
                        font.pixelSize: EmbryStyle.text.sm
                        font.family: EmbryStyle.text.monoFamily
                        font.weight: index === winnerIdx
                            ? EmbryStyle.text.weightBold : EmbryStyle.text.weightNormal
                        color: index === winnerIdx
                            ? EmbryStyle.colors.accentGreen : EmbryStyle.colors.textPrimary
                        elide: Text.ElideRight
                    }

                    Repeater {
                        model: [
                            parseFloat(modelData.accuracy || 0).toFixed(4),
                            parseFloat(modelData.macro_f1 || 0).toFixed(4),
                            parseFloat(modelData.precision || 0).toFixed(4),
                            parseFloat(modelData.recall || 0).toFixed(4),
                            (modelData.latency_ms || "---") + "ms",
                            modelData.size_mb ? (parseFloat(modelData.size_mb).toFixed(1) + "MB") : "---",
                        ]

                        Text {
                            Layout.preferredWidth: 80
                            text: modelData || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textSecondary
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }
            }
        }
    }
}
