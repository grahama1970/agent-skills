import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// EvaluatePage -- score compositions across 5 quality dimensions with radar chart.

Item {
    id: root

    property var evalResult: null
    property bool hasResult: evalResult !== null

    readonly property var dimensions: [
        { key: "readability",    label: "Readability",    weight: 0.25 },
        { key: "data_accuracy",  label: "Data Accuracy",  weight: 0.30 },
        { key: "visual_density", label: "Visual Density", weight: 0.15 },
        { key: "color_harmony",  label: "Color Harmony",  weight: 0.20 },
        { key: "title_clarity",  label: "Title Clarity",  weight: 0.10 }
    ]

    readonly property real passThreshold: 0.85

    Connections {
        target: figureBridge
        function onEvaluateResultJsonChanged() {
            try {
                evalResult = JSON.parse(figureBridge.evaluateResultJson)
                radarCanvas.requestPaint()
            } catch (e) {
                evalResult = null
            }
        }
    }

    function scoreFor(key) {
        if (!evalResult || !evalResult.scores) return 0
        return evalResult.scores[key] || 0
    }

    function overallScore() {
        if (!evalResult) return 0
        return evalResult.overall_score || 0
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // Composition path input
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Text {
                text: "Composition:"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: Font.Medium
                color: EmbryStyle.colors.textSecondary
            }

            EmbryTextField {
                id: evalPathField
                Layout.fillWidth: true
                placeholderText: "Path to composition HTML/PNG"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Composition path for evaluation"
            }

            EmbryButton {
                id: evalBtn
                text: "Evaluate"

                Accessible.name: "Run evaluation"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: evalBtn.hovered ? Qt.darker(EmbryStyle.colors.accent, 1.3) : EmbryStyle.colors.accent
                    radius: EmbryStyle.layout.radiusSm
                }

                contentItem: Text {
                    text: evalBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: Font.Bold
                    color: EmbryStyle.colors.bg
                    horizontalAlignment: Text.AlignHCenter
                    leftPadding: EmbryStyle.layout.space3
                    rightPadding: EmbryStyle.layout.space3
                }

                onClicked: figureBridge.evaluate(evalPathField.text)
            }

            EmbryButton {
                id: evalAllBtn
                text: "Evaluate All"

                Accessible.name: "Evaluate all compositions"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: evalAllBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput
                    border.width: 1
                    border.color: EmbryStyle.colors.border
                    radius: EmbryStyle.layout.radiusSm
                }

                contentItem: Text {
                    text: evalAllBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: Font.Medium
                    color: EmbryStyle.colors.textSecondary
                    horizontalAlignment: Text.AlignHCenter
                    leftPadding: EmbryStyle.layout.space3
                    rightPadding: EmbryStyle.layout.space3
                }

                onClicked: figureBridge.evaluateAll()
            }
        }

        // -- Score Cards + Radar ----------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space4

            // Score dimension cards
            ColumnLayout {
                Layout.preferredWidth: 400
                Layout.fillHeight: true
                spacing: EmbryStyle.layout.space2

                Repeater {
                    model: dimensions

                    Rectangle {
                        Layout.fillWidth: true
                        height: 64
                        radius: EmbryStyle.layout.radiusMd
                        color: EmbryStyle.colors.bgElevated
                        border.width: 1
                        border.color: EmbryStyle.colors.border

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: EmbryStyle.layout.space2
                            spacing: 2

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: EmbryStyle.layout.space2

                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.label
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.weight: Font.Medium
                                    color: EmbryStyle.colors.textPrimary
                                }

                                Text {
                                    text: scoreFor(modelData.key).toFixed(2)
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.family: EmbryStyle.text.monoFamily
                                    font.weight: Font.Bold
                                    color: scoreFor(modelData.key) >= 0.85
                                        ? EmbryStyle.colors.statusOk
                                        : scoreFor(modelData.key) >= 0.6
                                            ? EmbryStyle.colors.statusWarning
                                            : EmbryStyle.colors.statusCritical
                                }

                                // Weight label
                                Rectangle {
                                    width: weightText.implicitWidth + 8
                                    height: 16
                                    radius: 4
                                    color: EmbryStyle.colors.statusInfoBg

                                    Text {
                                        id: weightText
                                        anchors.centerIn: parent
                                        text: "w:" + modelData.weight.toFixed(2)
                                        font.pixelSize: 8
                                        font.weight: Font.Bold
                                        font.family: EmbryStyle.text.monoFamily
                                        color: EmbryStyle.colors.accent
                                    }
                                }

                                Text {
                                    text: "=" + (scoreFor(modelData.key) * modelData.weight).toFixed(3)
                                    font.pixelSize: EmbryStyle.text.xs
                                    font.family: EmbryStyle.text.monoFamily
                                    color: EmbryStyle.colors.textMuted
                                }
                            }

                            // Gauge bar
                            Rectangle {
                                Layout.fillWidth: true
                                height: 8
                                radius: 4
                                color: EmbryStyle.colors.bgInput

                                Rectangle {
                                    width: parent.width * Math.min(1.0, scoreFor(modelData.key))
                                    height: parent.height
                                    radius: 4
                                    color: scoreFor(modelData.key) >= 0.85
                                        ? EmbryStyle.colors.statusOk
                                        : scoreFor(modelData.key) >= 0.6
                                            ? EmbryStyle.colors.statusWarning
                                            : EmbryStyle.colors.statusCritical

                                    Behavior on width {
                                        NumberAnimation { duration: EmbryStyle.anim.pulse }
                                    }
                                }
                            }
                        }
                    }
                }

                // Overall score gauge
                Rectangle {
                    Layout.fillWidth: true
                    height: 80
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 2
                    border.color: overallScore() >= passThreshold
                        ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusWarning

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: EmbryStyle.layout.space3
                        spacing: EmbryStyle.layout.space3

                        ColumnLayout {
                            spacing: 2

                            Text {
                                text: "OVERALL"
                                font.pixelSize: EmbryStyle.text.xs
                                font.weight: Font.Bold
                                color: EmbryStyle.colors.textMuted
                            }

                            Text {
                                text: overallScore().toFixed(3)
                                font.pixelSize: EmbryStyle.text.xxl
                                font.weight: Font.Bold
                                font.family: EmbryStyle.text.monoFamily
                                color: overallScore() >= passThreshold
                                    ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusWarning
                            }
                        }

                        // Large gauge bar
                        Rectangle {
                            Layout.fillWidth: true
                            height: 16
                            radius: 8
                            color: EmbryStyle.colors.bgInput

                            Rectangle {
                                width: parent.width * Math.min(1.0, overallScore())
                                height: parent.height
                                radius: 8
                                color: overallScore() >= passThreshold
                                    ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusWarning

                                Behavior on width {
                                    NumberAnimation { duration: EmbryStyle.anim.pulse }
                                }
                            }

                            // Threshold marker
                            Rectangle {
                                x: parent.width * passThreshold - 1
                                width: 2
                                height: parent.height
                                color: EmbryStyle.colors.textPrimary
                                opacity: 0.6
                            }
                        }

                        // Pass/fail badge
                        Rectangle {
                            width: pfLabel.implicitWidth + EmbryStyle.layout.space3 * 2
                            height: EmbryStyle.layout.badgeHeight
                            radius: EmbryStyle.layout.badgeRadius
                            color: overallScore() >= passThreshold
                                ? EmbryStyle.colors.statusOkBg : EmbryStyle.colors.statusCriticalBg

                            Text {
                                id: pfLabel
                                anchors.centerIn: parent
                                text: overallScore() >= passThreshold ? "PASS" : "FAIL"
                                font.pixelSize: 9
                                font.weight: Font.Bold
                                color: overallScore() >= passThreshold
                                    ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusCritical
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }

            // -- Radar Chart --------------------------------------------------
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1
                border.color: EmbryStyle.colors.border

                Canvas {
                    id: radarCanvas
                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space4

                    onPaint: {
                        var ctx = getContext("2d")
                        var w = width
                        var h = height
                        var cx = w / 2
                        var cy = h / 2
                        var r = Math.min(cx, cy) - 30
                        var n = 5
                        var angleStep = (2 * Math.PI) / n

                        ctx.clearRect(0, 0, w, h)

                        // Draw grid rings (3 levels)
                        for (var level = 1; level <= 3; level++) {
                            var lr = r * (level / 3)
                            ctx.beginPath()
                            ctx.strokeStyle = Qt.rgba(0.78, 0.78, 0.78, 0.12)
                            ctx.lineWidth = 1
                            for (var i = 0; i <= n; i++) {
                                var a = -Math.PI / 2 + i * angleStep
                                var px = cx + lr * Math.cos(a)
                                var py = cy + lr * Math.sin(a)
                                if (i === 0) ctx.moveTo(px, py)
                                else ctx.lineTo(px, py)
                            }
                            ctx.closePath()
                            ctx.stroke()
                        }

                        // Draw axes
                        for (var j = 0; j < n; j++) {
                            var aa = -Math.PI / 2 + j * angleStep
                            ctx.beginPath()
                            ctx.strokeStyle = Qt.rgba(0.78, 0.78, 0.78, 0.2)
                            ctx.lineWidth = 1
                            ctx.moveTo(cx, cy)
                            ctx.lineTo(cx + r * Math.cos(aa), cy + r * Math.sin(aa))
                            ctx.stroke()

                            // Axis labels
                            var lx = cx + (r + 18) * Math.cos(aa)
                            var ly = cy + (r + 18) * Math.sin(aa)
                            ctx.fillStyle = Qt.rgba(0.78, 0.78, 0.78, 0.7)
                            ctx.font = "9px 'Inter'"
                            ctx.textAlign = "center"
                            ctx.textBaseline = "middle"
                            ctx.fillText(dimensions[j].label, lx, ly)
                        }

                        // Draw data polygon
                        if (hasResult) {
                            ctx.beginPath()
                            ctx.strokeStyle = EmbryStyle.colors.accent
                            ctx.lineWidth = 2
                            ctx.fillStyle = Qt.rgba(0.27, 0.67, 1.0, 0.2)

                            for (var k = 0; k <= n; k++) {
                                var idx = k % n
                                var score = scoreFor(dimensions[idx].key)
                                var da = -Math.PI / 2 + idx * angleStep
                                var dx = cx + r * score * Math.cos(da)
                                var dy = cy + r * score * Math.sin(da)
                                if (k === 0) ctx.moveTo(dx, dy)
                                else ctx.lineTo(dx, dy)
                            }
                            ctx.closePath()
                            ctx.fill()
                            ctx.stroke()

                            // Draw score dots
                            for (var m = 0; m < n; m++) {
                                var ds = scoreFor(dimensions[m].key)
                                var dotA = -Math.PI / 2 + m * angleStep
                                var dotX = cx + r * ds * Math.cos(dotA)
                                var dotY = cy + r * ds * Math.sin(dotA)
                                ctx.beginPath()
                                ctx.arc(dotX, dotY, 4, 0, 2 * Math.PI)
                                ctx.fillStyle = EmbryStyle.colors.accent
                                ctx.fill()
                            }
                        }
                    }
                }
            }
        }
    }
}
