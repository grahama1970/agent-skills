import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// ProfilerPage -- Latency and memory profiling for individual models.

Item {
    id: root

    property var registry: appWindow.registry
    property var allModels: {
        var c = (registry && registry.candidate_models) || []
        var a = (registry && registry.api_models) || []
        return c.concat(a)
    }
    property var profileResult: null
    property var latencyBuckets: []

    Connections {
        target: gptBridge
        function onProfileResultJsonChanged() {
            try {
                var r = JSON.parse(gptBridge.profileResultJson)
                root.profileResult = r
                root.latencyBuckets = r.latency_histogram || []
                latencyCanvas.requestPaint()
            } catch (_) {
                root.profileResult = null
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        Text {
            text: "Model Profiler"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        // -- Model selector + Run button --
        RowLayout {
            spacing: EmbryStyle.layout.space3

            Text { text: "Model:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }

            EmbryComboBox {
                id: modelSelector
                Layout.preferredWidth: 300
                model: {
                    var names = []
                    for (var i = 0; i < root.allModels.length; i++) {
                        names.push(root.allModels[i].name || "")
                    }
                    return names
                }
                Accessible.name: "Model selector"
            }

            EmbryButton {
                text: "Run Profile"
                variant: "primary"
                enabled: modelSelector.currentText.length > 0
                onClicked: gptBridge.runProfile(modelSelector.currentText)
                Accessible.name: "Run profile button"
                Accessible.role: Accessible.Button
            }
        }

        // -- Profile Results Summary --
        Rectangle {
            Layout.fillWidth: true
            height: 80
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border
            visible: root.profileResult !== null

            RowLayout {
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space8

                // Tokens/sec
                ColumnLayout {
                    spacing: EmbryStyle.layout.space1
                    Text { text: "Tokens/sec"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }
                    Text {
                        text: root.profileResult ? (root.profileResult.tokens_per_sec || 0).toFixed(1) : "0"
                        font.pixelSize: EmbryStyle.text.xl
                        font.weight: EmbryStyle.text.weightBold
                        color: EmbryStyle.colors.accentGreen
                    }
                }

                // TTFT
                ColumnLayout {
                    spacing: EmbryStyle.layout.space1
                    Text { text: "Time to First Token"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }
                    Text {
                        text: root.profileResult ? (root.profileResult.ttft_ms || 0).toFixed(0) + "ms" : "0ms"
                        font.pixelSize: EmbryStyle.text.xl
                        font.weight: EmbryStyle.text.weightBold
                        color: EmbryStyle.colors.accent
                    }
                }

                // Memory Peak
                ColumnLayout {
                    spacing: EmbryStyle.layout.space1
                    Text { text: "Memory Peak"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }
                    Text {
                        text: root.profileResult ? (root.profileResult.memory_peak_mb || 0).toFixed(0) + " MB" : "0 MB"
                        font.pixelSize: EmbryStyle.text.xl
                        font.weight: EmbryStyle.text.weightBold
                        color: EmbryStyle.colors.accentYellow
                    }
                }
            }
        }

        // -- Latency Histogram (Canvas bar chart) --
        Text {
            text: "Latency Distribution"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textSecondary
            visible: root.latencyBuckets.length > 0
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 180
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border
            visible: root.latencyBuckets.length > 0

            Canvas {
                id: latencyCanvas
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space3

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    if (root.latencyBuckets.length === 0) return

                    var maxVal = 0
                    for (var i = 0; i < root.latencyBuckets.length; i++) {
                        if ((root.latencyBuckets[i].count || 0) > maxVal)
                            maxVal = root.latencyBuckets[i].count
                    }
                    if (maxVal === 0) maxVal = 1

                    var barW = (width - 20) / root.latencyBuckets.length
                    var barGap = 2

                    for (var j = 0; j < root.latencyBuckets.length; j++) {
                        var bucket = root.latencyBuckets[j]
                        var h = ((bucket.count || 0) / maxVal) * (height - 30)
                        var x = 10 + j * barW
                        var y = height - 20 - h

                        ctx.fillStyle = EmbryStyle.colors.accent
                        ctx.fillRect(x + barGap / 2, y, barW - barGap, h)

                        // Label
                        ctx.fillStyle = "#888888"
                        ctx.font = "9px Inter"
                        ctx.textAlign = "center"
                        ctx.fillText((bucket.ms || "").toString(), x + barW / 2, height - 5)
                    }
                }
            }
        }

        // -- Memory Timeline --
        Text {
            text: "Memory Timeline"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textSecondary
            visible: root.profileResult !== null && (root.profileResult.memory_timeline || []).length > 0
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border
            visible: root.profileResult !== null && (root.profileResult.memory_timeline || []).length > 0

            ListView {
                id: memTimeline
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space2
                clip: true
                model: root.profileResult ? (root.profileResult.memory_timeline || []) : []

                delegate: RowLayout {
                    width: memTimeline.width
                    spacing: EmbryStyle.layout.space2

                    Accessible.name: "Memory at " + (modelData.time_s || 0) + " seconds"
                    Accessible.role: Accessible.ListItem

                    Text {
                        Layout.preferredWidth: 60
                        text: (modelData.time_s || 0).toFixed(1) + "s"
                        font.pixelSize: EmbryStyle.text.xs
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textMuted
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 8
                        radius: 4
                        color: EmbryStyle.colors.bgInput

                        Rectangle {
                            width: parent.width * Math.min(1, (modelData.mb || 0) / (root.profileResult.memory_peak_mb || 1))
                            height: parent.height
                            radius: 4
                            color: EmbryStyle.colors.accentYellow
                        }
                    }

                    Text {
                        Layout.preferredWidth: 60
                        text: (modelData.mb || 0).toFixed(0) + " MB"
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textSecondary
                        horizontalAlignment: Text.AlignRight
                    }
                }
            }
        }

        // Placeholder
        Text {
            visible: root.profileResult === null
            Layout.fillWidth: true
            Layout.fillHeight: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: "Select a model and click Run Profile."
            font.pixelSize: EmbryStyle.text.base
            color: EmbryStyle.colors.textSubtle
        }
    }
}
