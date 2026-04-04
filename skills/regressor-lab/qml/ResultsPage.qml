import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// ResultsPage -- detailed model results with residuals histogram and feature importance.

Item {
    id: root

    property var benchData: _parseBench()
    property int selectedIdx: 0
    property var selectedModel: (benchData.results || [])[selectedIdx] || {}

    function _parseBench() {
        try {
            return JSON.parse(regressorBridge.benchmarkResultJson || "{}")
        } catch (e) {
            return {}
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // -- Model Selector --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Text {
                text: "Model"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            EmbryComboBox {
                id: modelCombo
                Layout.preferredWidth: 200
                model: _modelNames()
                currentIndex: selectedIdx
                onCurrentIndexChanged: selectedIdx = currentIndex

                Accessible.name: "Select model to view results"
            }

            Item { Layout.fillWidth: true }
        }

        // -- Metrics Cards --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Repeater {
                model: [
                    { label: "RMSE", value: selectedModel.rmse, color: EmbryStyle.colors.accentRed, good: false },
                    { label: "R\u00B2", value: selectedModel.r2, color: EmbryStyle.colors.accentGreen, good: true },
                    { label: "MAPE", value: selectedModel.mape, color: EmbryStyle.colors.accentAmber, good: false },
                    { label: "MAE", value: selectedModel.mae, color: EmbryStyle.colors.accent, good: false }
                ]

                Rectangle {
                    Layout.fillWidth: true
                    height: 72
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    Accessible.name: (modelData.label || "") + ": " + _fmtMetric(modelData.value)
                    Accessible.role: Accessible.StaticText

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: _fmtMetric(modelData.value)
                            font.pixelSize: EmbryStyle.text.xl
                            font.weight: EmbryStyle.text.weightBold
                            font.family: EmbryStyle.text.monoFamily
                            color: _metricColor(modelData)
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: modelData.label || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightMedium
                            color: EmbryStyle.colors.textMuted
                        }
                    }
                }
            }
        }

        // -- Residuals Histogram --
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space3

            // Residuals
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: EmbryStyle.layout.space1

                Text {
                    text: "Residuals Distribution"
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightMedium
                    color: EmbryStyle.colors.textMuted
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    Canvas {
                        id: residualsCanvas
                        anchors.fill: parent
                        anchors.margins: EmbryStyle.layout.space4

                        onPaint: {
                            var ctx = getContext("2d")
                            var w = width; var h = height
                            ctx.clearRect(0, 0, w, h)

                            var bins = selectedModel.residual_bins || []
                            if (bins.length === 0) {
                                ctx.fillStyle = EmbryStyle.colors.textMuted
                                ctx.font = EmbryStyle.text.sm + "px " + EmbryStyle.text.fontFamily
                                ctx.textAlign = "center"
                                ctx.fillText("No residual data", w / 2, h / 2)
                                return
                            }

                            var maxBin = 0
                            for (var i = 0; i < bins.length; i++) {
                                if ((bins[i].count || 0) > maxBin) maxBin = bins[i].count
                            }
                            if (maxBin === 0) maxBin = 1

                            var barW = (w - 20) / bins.length - 2
                            var chartH = h - 30

                            // Grid lines
                            ctx.strokeStyle = EmbryStyle.colors.separator
                            ctx.lineWidth = 0.5
                            for (var g = 0; g <= 4; g++) {
                                var gy = chartH * (1 - g / 4)
                                ctx.beginPath(); ctx.moveTo(20, gy); ctx.lineTo(w, gy); ctx.stroke()
                            }

                            // Bars
                            for (var b = 0; b < bins.length; b++) {
                                var barH = (bins[b].count / maxBin) * chartH
                                var bx = 20 + b * (barW + 2)
                                var by = chartH - barH

                                ctx.fillStyle = EmbryStyle.colors.accent
                                ctx.fillRect(bx, by, barW, barH)

                                // Label
                                if (bins.length <= 20) {
                                    ctx.fillStyle = EmbryStyle.colors.textGhost
                                    ctx.font = (EmbryStyle.text.xs - 2) + "px " + EmbryStyle.text.monoFamily
                                    ctx.textAlign = "center"
                                    ctx.fillText(
                                        _fmtShort(bins[b].edge),
                                        bx + barW / 2, chartH + 12
                                    )
                                }
                            }

                            // Axis label
                            ctx.fillStyle = EmbryStyle.colors.textMuted
                            ctx.font = EmbryStyle.text.xs + "px " + EmbryStyle.text.fontFamily
                            ctx.textAlign = "center"
                            ctx.fillText("Prediction Error", w / 2, h - 2)
                        }

                        Connections {
                            target: root
                            function onSelectedModelChanged() { residualsCanvas.requestPaint() }
                        }
                    }
                }
            }

            // Feature Importance
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: EmbryStyle.layout.space1

                Text {
                    text: "Feature Importance"
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightMedium
                    color: EmbryStyle.colors.textMuted
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    Canvas {
                        id: importanceCanvas
                        anchors.fill: parent
                        anchors.margins: EmbryStyle.layout.space4

                        onPaint: {
                            var ctx = getContext("2d")
                            var w = width; var h = height
                            ctx.clearRect(0, 0, w, h)

                            var feats = selectedModel.feature_importance || []
                            if (feats.length === 0) {
                                ctx.fillStyle = EmbryStyle.colors.textMuted
                                ctx.font = EmbryStyle.text.sm + "px " + EmbryStyle.text.fontFamily
                                ctx.textAlign = "center"
                                ctx.fillText("N/A (linear model)", w / 2, h / 2)
                                return
                            }

                            var maxImp = 0
                            for (var i = 0; i < feats.length; i++) {
                                if ((feats[i].importance || 0) > maxImp) maxImp = feats[i].importance
                            }
                            if (maxImp === 0) maxImp = 1

                            var barH = Math.min(22, (h - 20) / feats.length - 4)
                            var labelW = 80

                            for (var f = 0; f < feats.length; f++) {
                                var fy = f * (barH + 4) + 10
                                var bw = ((feats[f].importance || 0) / maxImp) * (w - labelW - 10)

                                // Label
                                ctx.fillStyle = EmbryStyle.colors.textSecondary
                                ctx.font = (EmbryStyle.text.xs - 1) + "px " + EmbryStyle.text.monoFamily
                                ctx.textAlign = "right"
                                ctx.fillText(
                                    (feats[f].name || "").substring(0, 12),
                                    labelW - 4, fy + barH * 0.75
                                )

                                // Bar
                                ctx.fillStyle = EmbryStyle.colors.accentGreen
                                ctx.fillRect(labelW, fy, bw, barH)

                                // Value
                                ctx.fillStyle = EmbryStyle.colors.textMuted
                                ctx.textAlign = "left"
                                ctx.fillText(
                                    Number(feats[f].importance || 0).toFixed(3),
                                    labelW + bw + 4, fy + barH * 0.75
                                )
                            }
                        }

                        Connections {
                            target: root
                            function onSelectedModelChanged() { importanceCanvas.requestPaint() }
                        }
                    }
                }
            }
        }
    }

    function _modelNames() {
        var results = benchData.results || []
        var names = []
        for (var i = 0; i < results.length; i++) {
            names.push(results[i].model || "model_" + i)
        }
        return names
    }

    function _fmtMetric(val) {
        if (val === undefined || val === null) return "--"
        return Number(val).toFixed(4)
    }

    function _fmtShort(val) {
        if (val === undefined || val === null) return ""
        return Number(val).toFixed(2)
    }

    function _metricColor(data) {
        if (data.value === undefined || data.value === null) return EmbryStyle.colors.textMuted
        if (data.good) {
            return Number(data.value) > 0.9 ? EmbryStyle.colors.accentGreen
                 : Number(data.value) > 0.7 ? EmbryStyle.colors.accentYellow
                 : EmbryStyle.colors.accentRed
        }
        return data.color || EmbryStyle.colors.textPrimary
    }
}
