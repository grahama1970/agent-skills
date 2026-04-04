import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// ResultsPage -- Detailed per-model results with head-to-head comparison.

Item {
    id: root

    property var results: []
    property var tasks: []
    property string selectedTask: ""
    property int compareA: -1
    property int compareB: -1

    Connections {
        target: gptBridge
        function onBenchmarkResultJsonChanged() {
            try {
                var all = JSON.parse(gptBridge.benchmarkResultJson)
                root.results = all
                // Extract unique tasks
                var taskSet = {}
                for (var i = 0; i < all.length; i++) {
                    taskSet[all[i].task || "unknown"] = true
                }
                root.tasks = Object.keys(taskSet)
                if (root.tasks.length > 0 && root.selectedTask === "") {
                    root.selectedTask = root.tasks[0]
                }
            } catch (_) {
                root.results = []
            }
        }
    }

    property var filtered: {
        if (!root.selectedTask) return root.results
        var out = []
        for (var i = 0; i < root.results.length; i++) {
            if ((root.results[i].task || "") === root.selectedTask) {
                out.push(root.results[i])
            }
        }
        return out
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Header --
        RowLayout {
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Detailed Results"
                font.pixelSize: EmbryStyle.text.lg
                font.weight: EmbryStyle.text.weightSemibold
                color: EmbryStyle.colors.textPrimary
            }

            Text { text: "Task:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }

            EmbryComboBox {
                id: taskFilter
                Layout.preferredWidth: 200
                model: root.tasks
                onCurrentTextChanged: root.selectedTask = currentText
                Accessible.name: "Task filter"
            }
        }

        // -- Model Cards Grid --
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Accessible.name: "Results cards"
            Accessible.role: Accessible.Pane

            Flow {
                id: cardFlow
                width: parent.width
                spacing: EmbryStyle.layout.space3

                Repeater {
                    model: root.filtered

                    Rectangle {
                        width: 260
                        height: 180
                        radius: EmbryStyle.layout.radiusMd
                        color: EmbryStyle.colors.bgElevated
                        border.width: (root.compareA === index || root.compareB === index) ? 2 : 1
                        border.color: (root.compareA === index || root.compareB === index)
                            ? EmbryStyle.colors.accent : EmbryStyle.colors.border

                        Accessible.name: (modelData.model || "") + " result card"
                        Accessible.role: Accessible.Pane

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: EmbryStyle.layout.space3
                            spacing: EmbryStyle.layout.space2

                            // Model name
                            Text {
                                text: modelData.model || ""
                                font.pixelSize: EmbryStyle.text.sm
                                font.weight: EmbryStyle.text.weightSemibold
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textPrimary
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }

                            // Accuracy gauge
                            Text { text: "Accuracy"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }
                            Rectangle {
                                Layout.fillWidth: true
                                height: 12
                                radius: 6
                                color: EmbryStyle.colors.bgInput

                                Rectangle {
                                    width: parent.width * Math.min(1, modelData.accuracy || 0)
                                    height: parent.height
                                    radius: 6
                                    color: (modelData.accuracy || 0) >= 0.85
                                        ? EmbryStyle.colors.accentGreen
                                        : (modelData.accuracy || 0) >= 0.7
                                            ? EmbryStyle.colors.accentYellow
                                            : EmbryStyle.colors.accentRed
                                }
                            }
                            Text {
                                text: ((modelData.accuracy || 0) * 100).toFixed(1) + "%"
                                font.pixelSize: EmbryStyle.text.xs
                                font.weight: EmbryStyle.text.weightBold
                                color: EmbryStyle.colors.accentGreen
                            }

                            // Latency bar
                            Text { text: "Latency P50"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }
                            Rectangle {
                                Layout.fillWidth: true
                                height: 8
                                radius: 4
                                color: EmbryStyle.colors.bgInput

                                Rectangle {
                                    width: parent.width * Math.min(1, (modelData.latency_p50 || 0) / 2000)
                                    height: parent.height
                                    radius: 4
                                    color: EmbryStyle.colors.accent
                                }
                            }
                            Text {
                                text: (modelData.latency_p50 || 0).toFixed(0) + "ms"
                                font.pixelSize: EmbryStyle.text.xs
                                color: EmbryStyle.colors.textSecondary
                            }

                            // Memory
                            Text {
                                text: "Memory: " + (modelData.memory_mb || 0).toFixed(0) + " MB"
                                font.pixelSize: EmbryStyle.text.xs
                                color: EmbryStyle.colors.textMuted
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.compareA < 0) {
                                    root.compareA = index
                                } else if (root.compareB < 0 && index !== root.compareA) {
                                    root.compareB = index
                                } else {
                                    root.compareA = index
                                    root.compareB = -1
                                }
                            }
                            Accessible.name: "Select " + (modelData.model || "model") + " for comparison"
                            Accessible.role: Accessible.Button
                        }
                    }
                }
            }
        }

        // -- Head-to-Head Comparison --
        Rectangle {
            Layout.fillWidth: true
            height: 100
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.accent
            visible: root.compareA >= 0 && root.compareB >= 0 && root.compareA < root.filtered.length && root.compareB < root.filtered.length

            Accessible.name: "Head-to-head comparison"
            Accessible.role: Accessible.Pane

            RowLayout {
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space4

                // Model A
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: EmbryStyle.layout.space1

                    Text {
                        text: root.compareA >= 0 && root.compareA < root.filtered.length ? (root.filtered[root.compareA].model || "") : ""
                        font.pixelSize: EmbryStyle.text.sm
                        font.weight: EmbryStyle.text.weightSemibold
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textPrimary
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    Text {
                        text: root.compareA >= 0 && root.compareA < root.filtered.length
                            ? "Acc: " + ((root.filtered[root.compareA].accuracy || 0) * 100).toFixed(1) + "%  Lat: " + (root.filtered[root.compareA].latency_p50 || 0).toFixed(0) + "ms"
                            : ""
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textSecondary
                    }
                }

                // VS / Winner badge
                ColumnLayout {
                    spacing: EmbryStyle.layout.space1

                    Text {
                        text: "VS"
                        font.pixelSize: EmbryStyle.text.lg
                        font.weight: EmbryStyle.text.weightBold
                        color: EmbryStyle.colors.accentYellow
                        horizontalAlignment: Text.AlignHCenter
                    }

                    Rectangle {
                        width: winnerText.implicitWidth + EmbryStyle.layout.space4
                        height: EmbryStyle.layout.badgeHeight
                        radius: EmbryStyle.layout.badgeRadius
                        color: EmbryStyle.colors.statusOkBg
                        visible: root.compareA >= 0 && root.compareB >= 0 && root.compareA < root.filtered.length && root.compareB < root.filtered.length

                        Text {
                            id: winnerText
                            anchors.centerIn: parent
                            text: {
                                if (root.compareA < 0 || root.compareB < 0 || root.compareA >= root.filtered.length || root.compareB >= root.filtered.length) return ""
                                var a = root.filtered[root.compareA]
                                var b = root.filtered[root.compareB]
                                var accA = a.accuracy || 0
                                var accB = b.accuracy || 0
                                var winner = accA >= accB ? (a.model || "") : (b.model || "")
                                var delta = Math.abs(accA - accB) * 100
                                return winner.split("/").pop() + " +" + delta.toFixed(1) + "%"
                            }
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightBold
                            color: EmbryStyle.colors.accentGreen
                        }
                    }
                }

                // Model B
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: EmbryStyle.layout.space1

                    Text {
                        text: root.compareB >= 0 && root.compareB < root.filtered.length ? (root.filtered[root.compareB].model || "") : ""
                        font.pixelSize: EmbryStyle.text.sm
                        font.weight: EmbryStyle.text.weightSemibold
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textPrimary
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    Text {
                        text: root.compareB >= 0 && root.compareB < root.filtered.length
                            ? "Acc: " + ((root.filtered[root.compareB].accuracy || 0) * 100).toFixed(1) + "%  Lat: " + (root.filtered[root.compareB].latency_p50 || 0).toFixed(0) + "ms"
                            : ""
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textSecondary
                    }
                }
            }
        }

        // Placeholder
        Text {
            visible: root.filtered.length === 0
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: "No results. Run benchmarks from the Benchmark tab first."
            font.pixelSize: EmbryStyle.text.base
            color: EmbryStyle.colors.textSubtle
        }
    }
}
