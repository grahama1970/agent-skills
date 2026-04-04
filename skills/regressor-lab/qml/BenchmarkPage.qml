import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// BenchmarkPage -- multi-architecture comparison with scatter plot.

Item {
    id: root

    property var benchData: _parseBench()
    property int selectedModelIdx: 0

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

        // -- Architecture Checklist --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Architectures"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            Repeater {
                id: archRepeater
                model: ["linear", "ridge", "lasso", "gbr", "rf", "xgb"]

                Rectangle {
                    width: archRow.implicitWidth + EmbryStyle.layout.space3
                    height: 28
                    radius: EmbryStyle.layout.radiusSm
                    color: EmbryStyle.colors.bgInput

                    property bool selected: true

                    Row {
                        id: archRow
                        anchors.centerIn: parent
                        spacing: EmbryStyle.layout.space1

                        CheckBox {
                            id: archCheck
                            checked: selected
                            width: 18
                            height: 18
                            onToggled: selected = checked

                            Accessible.name: "Toggle " + (modelData || "") + " architecture"
                            Accessible.role: Accessible.CheckBox
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: (modelData || "").toUpperCase()
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightMedium
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textPrimary
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // Run Benchmark button
            Rectangle {
                width: runBtnText.implicitWidth + EmbryStyle.layout.space4 * 2
                height: 32
                radius: EmbryStyle.layout.radiusSm
                color: runBtnMa.containsMouse
                    ? EmbryStyle.colors.bgPressed
                    : EmbryStyle.colors.bgInput
                border.width: 1
                border.color: EmbryStyle.colors.accentGreen

                Accessible.name: "Run benchmark"
                Accessible.role: Accessible.Button

                Text {
                    id: runBtnText
                    anchors.centerIn: parent
                    text: "Run Benchmark"
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightSemibold
                    color: EmbryStyle.colors.accentGreen
                }

                MouseArea {
                    id: runBtnMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        var archs = []
                        for (var i = 0; i < archRepeater.count; i++) {
                            var item = archRepeater.itemAt(i)
                            if (item && item.selected) {
                                archs.push(archRepeater.model[i])
                            }
                        }
                        regressorBridge.runBenchmark(JSON.stringify(archs))
                    }
                    Accessible.name: "Run benchmark"
                    Accessible.role: Accessible.Button
                }
            }
        }

        // -- Results Table --
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 200
            radius: EmbryStyle.layout.radiusSm
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space2
                spacing: 0

                // Header row
                Row {
                    Layout.fillWidth: true
                    spacing: 1

                    Repeater {
                        model: ["Model", "RMSE", "R\u00B2", "MAPE", "MAE", "Train Time"]
                        Text {
                            width: (root.width - EmbryStyle.layout.space4 * 2 - EmbryStyle.layout.space2 * 2) / 6
                            height: 26
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            text: modelData || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightSemibold
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.accent
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: EmbryStyle.colors.separator
                }

                // Data rows
                ListView {
                    id: resultsTable
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: benchData.results || []
                    spacing: 1

                    delegate: Rectangle {
                        width: resultsTable.width
                        height: 28
                        radius: EmbryStyle.layout.radiusSm
                        color: {
                            if (index === _winnerIdx()) return EmbryStyle.colors.statusOkBg
                            if (index === selectedModelIdx) return EmbryStyle.colors.selectBg
                            return rowMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"
                        }
                        border.width: index === _winnerIdx() ? 1 : 0
                        border.color: EmbryStyle.colors.accentGreen

                        Accessible.name: (modelData.model || "") + " results"
                        Accessible.role: Accessible.ListItem

                        Row {
                            anchors.fill: parent
                            spacing: 1

                            Repeater {
                                model: [
                                    { val: (parent.parent.ListView.view.model[index] || {}).model || "", isName: true },
                                    { val: _fmt((parent.parent.ListView.view.model[index] || {}).rmse) },
                                    { val: _fmt((parent.parent.ListView.view.model[index] || {}).r2) },
                                    { val: _fmt((parent.parent.ListView.view.model[index] || {}).mape) },
                                    { val: _fmt((parent.parent.ListView.view.model[index] || {}).mae) },
                                    { val: (parent.parent.ListView.view.model[index] || {}).train_time || "" }
                                ]

                                Text {
                                    width: resultsTable.width / 6
                                    height: 28
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    text: modelData.val || ""
                                    font.pixelSize: EmbryStyle.text.xs
                                    font.family: EmbryStyle.text.monoFamily
                                    font.weight: modelData.isName
                                        ? EmbryStyle.text.weightSemibold
                                        : EmbryStyle.text.weightNormal
                                    color: modelData.isName
                                        ? EmbryStyle.colors.textPrimary
                                        : EmbryStyle.colors.textSecondary
                                }
                            }
                        }

                        MouseArea {
                            id: rowMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: selectedModelIdx = index
                        }
                    }
                }
            }
        }

        // -- Winner Highlight --
        Rectangle {
            Layout.fillWidth: true
            height: 28
            radius: EmbryStyle.layout.radiusSm
            color: EmbryStyle.colors.statusOkBg
            border.width: 1
            border.color: EmbryStyle.colors.accentGreen
            visible: (benchData.results || []).length > 0

            Accessible.name: "Winner: " + _winnerName()
            Accessible.role: Accessible.StaticText

            Text {
                anchors.centerIn: parent
                text: "Winner: " + _winnerName() + "  (lowest RMSE)"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightSemibold
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.accentGreen
            }
        }

        // -- Scatter Plot: Predicted vs Actual --
        Text {
            text: "Predicted vs Actual" + (_selectedModelName() ? " (" + _selectedModelName() + ")" : "")
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
                id: scatterCanvas
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space4

                onPaint: {
                    var ctx = getContext("2d")
                    var w = width
                    var h = height
                    ctx.clearRect(0, 0, w, h)

                    var results = benchData.results || []
                    var sel = results[selectedModelIdx] || {}
                    var pts = sel.scatter || []

                    // Grid
                    ctx.strokeStyle = EmbryStyle.colors.separator
                    ctx.lineWidth = 0.5
                    for (var gx = 0; gx <= 4; gx++) {
                        var xp = gx * w / 4
                        ctx.beginPath(); ctx.moveTo(xp, 0); ctx.lineTo(xp, h); ctx.stroke()
                    }
                    for (var gy = 0; gy <= 4; gy++) {
                        var yp = gy * h / 4
                        ctx.beginPath(); ctx.moveTo(0, yp); ctx.lineTo(w, yp); ctx.stroke()
                    }

                    if (pts.length === 0) {
                        ctx.fillStyle = EmbryStyle.colors.textMuted
                        ctx.font = EmbryStyle.text.sm + "px " + EmbryStyle.text.fontFamily
                        ctx.textAlign = "center"
                        ctx.fillText("No scatter data available", w / 2, h / 2)
                        return
                    }

                    // Compute bounds
                    var minV = Infinity, maxV = -Infinity
                    for (var i = 0; i < pts.length; i++) {
                        var a = pts[i].actual; var p = pts[i].predicted
                        if (a < minV) minV = a; if (a > maxV) maxV = a
                        if (p < minV) minV = p; if (p > maxV) maxV = p
                    }
                    var range = maxV - minV || 1

                    // Diagonal (perfect prediction)
                    ctx.strokeStyle = EmbryStyle.colors.accentGreen
                    ctx.lineWidth = 1
                    ctx.setLineDash([4, 4])
                    ctx.beginPath(); ctx.moveTo(0, h); ctx.lineTo(w, 0); ctx.stroke()
                    ctx.setLineDash([])

                    // Data points
                    ctx.fillStyle = EmbryStyle.colors.accent
                    for (var j = 0; j < pts.length; j++) {
                        var px = ((pts[j].actual - minV) / range) * w
                        var py = h - ((pts[j].predicted - minV) / range) * h
                        ctx.beginPath()
                        ctx.arc(px, py, 3, 0, Math.PI * 2)
                        ctx.fill()
                    }

                    // Axis labels
                    ctx.fillStyle = EmbryStyle.colors.textMuted
                    ctx.font = EmbryStyle.text.xs + "px " + EmbryStyle.text.fontFamily
                    ctx.textAlign = "center"
                    ctx.fillText("Actual", w / 2, h - 2)
                    ctx.save()
                    ctx.translate(10, h / 2)
                    ctx.rotate(-Math.PI / 2)
                    ctx.fillText("Predicted", 0, 0)
                    ctx.restore()

                    // Legend
                    ctx.fillStyle = EmbryStyle.colors.accent
                    ctx.fillRect(w - 80, 8, 8, 8)
                    ctx.fillStyle = EmbryStyle.colors.textMuted
                    ctx.textAlign = "left"
                    ctx.fillText("Points", w - 68, 16)
                }

                Connections {
                    target: root
                    function onBenchDataChanged() { scatterCanvas.requestPaint() }
                    function onSelectedModelIdxChanged() { scatterCanvas.requestPaint() }
                }
            }
        }
    }

    function _winnerIdx() {
        var results = benchData.results || []
        if (results.length === 0) return -1
        var best = 0
        for (var i = 1; i < results.length; i++) {
            if ((results[i].rmse || Infinity) < (results[best].rmse || Infinity)) best = i
        }
        return best
    }

    function _winnerName() {
        var idx = _winnerIdx()
        if (idx < 0) return "--"
        return (benchData.results[idx] || {}).model || "--"
    }

    function _selectedModelName() {
        var results = benchData.results || []
        return (results[selectedModelIdx] || {}).model || ""
    }

    function _fmt(val) {
        if (val === undefined || val === null) return "--"
        return Number(val).toFixed(4)
    }
}
