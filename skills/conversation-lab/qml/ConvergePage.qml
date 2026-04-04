import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    // ── Properties ──────────────────────────────────────────
    property var bridge: null
    property var convergenceState: bridge ? JSON.parse(bridge.convergenceStateJson) : null
    property var cycles: convergenceState ? convergenceState.cycles : []
    property real targetRate: 0.80

    // ── Layout ──────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // ── Header with Status ───────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Convergence"
                font.pixelSize: EmbryStyle.text.lg
                font.weight: Font.SemiBold
                color: EmbryStyle.colors.textPrimary
            }

            // Status badge
            Rectangle {
                Layout.preferredHeight: EmbryStyle.layout.badgeHeight
                Layout.preferredWidth: convStatusText.implicitWidth + EmbryStyle.layout.space4

                radius: EmbryStyle.layout.badgeRadius
                color: {
                    var st = convergenceState ? convergenceState.status : "idle";
                    if (st === "converged") return EmbryStyle.colors.statusOkBg;
                    if (st === "running") return EmbryStyle.colors.statusInfoBg;
                    if (st === "plateau") return EmbryStyle.colors.statusWarningBg;
                    return EmbryStyle.colors.badge;
                }

                Text {
                    id: convStatusText

                    anchors.centerIn: parent
                    text: convergenceState ? convergenceState.status.toUpperCase() : "IDLE"
                    font.pixelSize: EmbryStyle.text.xs
                    font.weight: Font.Bold
                    color: {
                        var st = convergenceState ? convergenceState.status : "idle";
                        if (st === "converged") return EmbryStyle.colors.statusOk;
                        if (st === "running") return EmbryStyle.colors.statusInfo;
                        if (st === "plateau") return EmbryStyle.colors.statusWarning;
                        return EmbryStyle.colors.textMuted;
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Text {
                text: convergenceState ? "Run: " + convergenceState.run_id : ""
                font.pixelSize: EmbryStyle.text.xs
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textGhost
            }
        }

        // ── Convergence Chart ────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 240

            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            Canvas {
                id: convergenceCanvas

                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space4

                onPaint: {
                    var ctx = getContext("2d");
                    ctx.clearRect(0, 0, width, height);

                    if (cycles.length === 0) {
                        ctx.fillStyle = EmbryStyle.colors.textMuted.toString();
                        ctx.font = EmbryStyle.text.base + "px " + EmbryStyle.text.fontFamily;
                        ctx.textAlign = "center";
                        ctx.fillText("No convergence data", width / 2, height / 2);
                        return;
                    }

                    var padL = 50, padR = 20, padT = 20, padB = 40;
                    var chartW = width - padL - padR;
                    var chartH = height - padT - padB;

                    // Target line
                    var targetY = padT + chartH * (1 - targetRate);
                    ctx.strokeStyle = Qt.rgba(0, 1, 0.53, 0.3).toString();
                    ctx.lineWidth = 1;
                    ctx.setLineDash([6, 4]);
                    ctx.beginPath();
                    ctx.moveTo(padL, targetY);
                    ctx.lineTo(padL + chartW, targetY);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // Target label
                    ctx.fillStyle = Qt.rgba(0, 1, 0.53, 0.5).toString();
                    ctx.font = "10px " + EmbryStyle.text.monoFamily;
                    ctx.textAlign = "left";
                    ctx.fillText("target " + (targetRate * 100) + "%", padL + 4, targetY - 4);

                    // Y-axis labels
                    ctx.fillStyle = EmbryStyle.colors.textMuted.toString();
                    ctx.textAlign = "right";
                    for (var y = 0; y <= 100; y += 20) {
                        var yPos = padT + chartH * (1 - y / 100);
                        ctx.fillText(y + "%", padL - 8, yPos + 4);

                        // Grid line
                        ctx.strokeStyle = EmbryStyle.colors.separator.toString();
                        ctx.lineWidth = 0.5;
                        ctx.beginPath();
                        ctx.moveTo(padL, yPos);
                        ctx.lineTo(padL + chartW, yPos);
                        ctx.stroke();
                    }

                    // Draw satisfaction rate line
                    var maxCycles = Math.max(cycles.length, 5);
                    ctx.strokeStyle = EmbryStyle.colors.accentGreen.toString();
                    ctx.lineWidth = 2.5;
                    ctx.beginPath();
                    for (var i = 0; i < cycles.length; i++) {
                        var x = padL + (i / (maxCycles - 1)) * chartW;
                        var cy = padT + chartH * (1 - cycles[i].satisfied_rate);
                        if (i === 0) ctx.moveTo(x, cy);
                        else ctx.lineTo(x, cy);
                    }
                    ctx.stroke();

                    // Draw composite line
                    ctx.strokeStyle = EmbryStyle.colors.accent.toString();
                    ctx.lineWidth = 1.5;
                    ctx.setLineDash([4, 3]);
                    ctx.beginPath();
                    for (var j = 0; j < cycles.length; j++) {
                        var x2 = padL + (j / (maxCycles - 1)) * chartW;
                        var cy2 = padT + chartH * (1 - cycles[j].avg_composite);
                        if (j === 0) ctx.moveTo(x2, cy2);
                        else ctx.lineTo(x2, cy2);
                    }
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // Data points
                    for (var k = 0; k < cycles.length; k++) {
                        var px = padL + (k / (maxCycles - 1)) * chartW;
                        var py = padT + chartH * (1 - cycles[k].satisfied_rate);

                        ctx.fillStyle = EmbryStyle.colors.accentGreen.toString();
                        ctx.beginPath();
                        ctx.arc(px, py, 4, 0, 2 * Math.PI);
                        ctx.fill();

                        // X label
                        ctx.fillStyle = EmbryStyle.colors.textMuted.toString();
                        ctx.textAlign = "center";
                        ctx.font = "10px " + EmbryStyle.text.monoFamily;
                        ctx.fillText("C" + cycles[k].cycle, px, padT + chartH + 16);
                    }

                    // Legend
                    ctx.font = "10px " + EmbryStyle.text.fontFamily;
                    ctx.textAlign = "left";
                    var legendX = padL + chartW - 140;
                    ctx.fillStyle = EmbryStyle.colors.accentGreen.toString();
                    ctx.fillRect(legendX, padT + 2, 12, 2.5);
                    ctx.fillText("Satisfied %", legendX + 16, padT + 7);

                    ctx.fillStyle = EmbryStyle.colors.accent.toString();
                    ctx.fillRect(legendX, padT + 16, 12, 1.5);
                    ctx.fillText("Avg Composite", legendX + 16, padT + 21);
                }
            }

            // Repaint when data changes
            Connections {
                target: root
                function onCyclesChanged() { convergenceCanvas.requestPaint(); }
            }

            Accessible.name: "Convergence chart showing satisfaction rate and composite score across cycles"
            Accessible.role: Accessible.Chart
        }

        // ── Cycle Details Table ──────────────────────────────
        ListView {
            id: cyclesList

            Layout.fillWidth: true
            Layout.fillHeight: true

            clip: true
            model: cycles
            spacing: 2

            header: Rectangle {
                width: cyclesList.width
                height: 28
                color: EmbryStyle.colors.bgElevated
                radius: EmbryStyle.layout.radiusSm

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: EmbryStyle.layout.space2
                    anchors.rightMargin: EmbryStyle.layout.space2

                    Text { Layout.preferredWidth: 60; text: "Cycle"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.preferredWidth: 100; text: "Satisfied Rate"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.preferredWidth: 100; text: "Avg Composite"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.preferredWidth: 80; text: "Rerun"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.preferredWidth: 80; text: "Improved"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.fillWidth: true; text: "Regressed"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignHCenter }
                }
            }

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: cyclesList.width
                height: 30
                color: index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.02) : "transparent"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: EmbryStyle.layout.space2
                    anchors.rightMargin: EmbryStyle.layout.space2

                    Text { Layout.preferredWidth: 60; text: "C" + modelData.cycle; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold; color: EmbryStyle.colors.textPrimary }
                    Text { Layout.preferredWidth: 100; text: (modelData.satisfied_rate * 100).toFixed(1) + "%"; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: modelData.satisfied_rate >= targetRate ? EmbryStyle.colors.statusOk : EmbryStyle.colors.textSecondary }
                    Text { Layout.preferredWidth: 100; text: modelData.avg_composite.toFixed(3); font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                    Text { Layout.preferredWidth: 80; text: modelData.sessions_rerun; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.preferredWidth: 80; text: modelData.improved || 0; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.statusOk; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.fillWidth: true; text: modelData.regressed || 0; font.pixelSize: EmbryStyle.text.sm; color: (modelData.regressed || 0) > 0 ? EmbryStyle.colors.statusCritical : EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignHCenter }
                }

                Accessible.name: "Cycle " + modelData.cycle + ": " + (modelData.satisfied_rate * 100).toFixed(1) + "% satisfied"
                Accessible.role: Accessible.ListItem
            }
        }

        // ── Controls Row ─────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            EmbryButton {
                text: "Start Convergence"
                variant: "primary"
                enabled: bridge !== null && (!convergenceState || convergenceState.status !== "running")
                onClicked: if (bridge) bridge.startConvergence()

                Accessible.name: "Start convergence loop"
                Accessible.role: Accessible.Button
                Accessible.description: "Begin re-running unsatisfied sessions"
            }

            EmbryButton {
                text: "Dry Run"
                enabled: bridge !== null
                onClicked: if (bridge) bridge.startConvergenceDryRun()

                Accessible.name: "Dry run convergence"
                Accessible.role: Accessible.Button
                Accessible.description: "Diagnose without re-running sessions"
            }

            Item { Layout.fillWidth: true }

            Text {
                text: convergenceState ? "LLM calls: ~" + (convergenceState.total_llm_calls || 0) : ""
                font.pixelSize: EmbryStyle.text.xs
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textGhost
            }
        }
    }
}
