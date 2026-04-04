import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1200
    height: 700
    minimumWidth: 900
    minimumHeight: 500
    title: "Evidence Case Viewer"
    visible: true
    color: "#141414"

    // ── NVIS Colors (MIL-STD-3009) ─────────────────────
    readonly property color nvisRed: "#e74c3c"
    readonly property color nvisAmber: "#e67e22"
    readonly property color nvisYellow: "#f39c12"
    readonly property color nvisGreen: "#2ecc71"

    // ── EmbryStyle tokens ──────────────────────────────
    readonly property color bgElevated: "#1e1e1e"
    readonly property color bgInput: "#242424"
    readonly property color accent: "#4a9eff"
    readonly property color textPrimary: "#ffffff"
    readonly property color textSecondary: "#e0e0e0"
    readonly property color textMuted: "#88ffffff"
    readonly property color textSubtle: "#55ffffff"
    readonly property color border: "#22ffffff"
    readonly property color separator: "#15ffffff"
    readonly property int panelRadius: 10
    readonly property int panelMargin: 12

    // Use system monospace font (JetBrains Mono if installed, else fallback)
    readonly property string monoFamily: "JetBrains Mono,Fira Code,monospace"

    // ── Top bar: question input ────────────────────────
    header: ToolBar {
        background: Rectangle { color: bgElevated; border.width: 0 }
        height: 56
        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 8

            TextField {
                id: questionInput
                Layout.fillWidth: true
                placeholderText: "Enter question to evaluate..."
                color: textPrimary
                placeholderTextColor: textSubtle
                font.pixelSize: 14
                background: Rectangle {
                    color: bgInput
                    radius: 8
                    border.color: questionInput.activeFocus ? accent : border
                    border.width: 1
                }
                onAccepted: runBtn.clicked()
            }

            Button {
                id: runBtn
                text: evidenceBridge.running ? "Running..." : "Evaluate"
                enabled: !evidenceBridge.running && questionInput.text.length > 0
                font.pixelSize: 13
                font.weight: Font.DemiBold
                contentItem: Text {
                    text: runBtn.text
                    color: runBtn.enabled ? textPrimary : textMuted
                    font: runBtn.font
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: runBtn.enabled ? (runBtn.pressed ? "#3578cc" : accent) : "#333333"
                    radius: 8
                    implicitWidth: 100
                    implicitHeight: 36
                }
                onClicked: evidenceBridge.runPipeline(questionInput.text)
            }
        }
    }

    // ── Main content: 2-column layout ──────────────────
    RowLayout {
        anchors.fill: parent
        anchors.margins: panelMargin
        spacing: panelMargin

        // Left column: Gates + Sentence Markup
        ColumnLayout {
            Layout.preferredWidth: 380
            Layout.fillHeight: true
            spacing: panelMargin

            // Sentence Markup Panel
            Panel {
                Layout.fillWidth: true
                Layout.preferredHeight: 160
                panelTitle: "Sentence Markup"

                Flow {
                    id: markupFlow
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 4

                    Repeater {
                        model: evidenceBridge.annotations
                        delegate: Rectangle {
                            width: termLabel.implicitWidth + 12
                            height: 26
                            radius: 4
                            color: {
                                var level = modelData.level
                                if (level === "RED") return Qt.rgba(nvisRed.r, nvisRed.g, nvisRed.b, 0.2)
                                if (level === "AMBER") return Qt.rgba(nvisAmber.r, nvisAmber.g, nvisAmber.b, 0.2)
                                if (level === "YELLOW") return Qt.rgba(nvisYellow.r, nvisYellow.g, nvisYellow.b, 0.15)
                                if (level === "GREEN") return Qt.rgba(nvisGreen.r, nvisGreen.g, nvisGreen.b, 0.15)
                                return "#333333"
                            }
                            border.color: {
                                var level = modelData.level
                                if (level === "RED") return nvisRed
                                if (level === "AMBER") return nvisAmber
                                if (level === "YELLOW") return nvisYellow
                                if (level === "GREEN") return nvisGreen
                                return border
                            }
                            border.width: 1

                            Text {
                                id: termLabel
                                anchors.centerIn: parent
                                text: modelData.term
                                color: {
                                    var level = modelData.level
                                    if (level === "RED") return nvisRed
                                    if (level === "AMBER") return nvisAmber
                                    if (level === "YELLOW") return nvisYellow
                                    if (level === "GREEN") return nvisGreen
                                    return textPrimary
                                }
                                font.pixelSize: 12
                                font.weight: Font.Medium
                            }

                            ToolTip.visible: mouseArea.containsMouse
                            ToolTip.text: modelData.label || ""
                            ToolTip.delay: 300

                            MouseArea {
                                id: mouseArea
                                anchors.fill: parent
                                hoverEnabled: true
                            }
                        }
                    }

                    // Empty state
                    Text {
                        visible: evidenceBridge.annotations.length === 0
                        text: evidenceBridge.running ? "Extracting entities..." : "No annotations yet"
                        color: textSubtle
                        font.pixelSize: 12
                        font.italic: true
                    }
                }
            }

            // Gates Panel
            Panel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                panelTitle: "Pipeline Gates"

                ListView {
                    id: gatesList
                    anchors.fill: parent
                    anchors.margins: 4
                    model: evidenceBridge.gates
                    spacing: 4
                    clip: true

                    delegate: Rectangle {
                        width: gatesList.width
                        height: 48
                        radius: 6
                        color: bgInput

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 8

                            // Status indicator
                            Rectangle {
                                width: 10; height: 10; radius: 5
                                color: {
                                    var s = modelData.status
                                    if (s === "running") return nvisYellow
                                    if (s === "passed") return nvisGreen
                                    if (s === "failed") return nvisRed
                                    return textSubtle
                                }

                                SequentialAnimation on opacity {
                                    running: modelData.status === "running"
                                    loops: Animation.Infinite
                                    NumberAnimation { to: 0.3; duration: 400 }
                                    NumberAnimation { to: 1.0; duration: 400 }
                                }
                            }

                            // Gate info
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Text {
                                    text: modelData.label || modelData.id
                                    color: textPrimary
                                    font.pixelSize: 13
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: modelData.reason || (modelData.status === "running" ? "Evaluating..." : "")
                                    color: textMuted
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            // Pass/Fail badge
                            Rectangle {
                                visible: modelData.status !== "running"
                                width: passLabel.implicitWidth + 12
                                height: 20
                                radius: 4
                                color: modelData.status === "passed"
                                    ? Qt.rgba(nvisGreen.r, nvisGreen.g, nvisGreen.b, 0.2)
                                    : Qt.rgba(nvisRed.r, nvisRed.g, nvisRed.b, 0.2)

                                Text {
                                    id: passLabel
                                    anchors.centerIn: parent
                                    text: modelData.status === "passed" ? "PASS" : "FAIL"
                                    color: modelData.status === "passed" ? nvisGreen : nvisRed
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                }
                            }
                        }
                    }

                    // Empty state
                    Text {
                        visible: evidenceBridge.gates.length === 0
                        anchors.centerIn: parent
                        text: "No gates fired yet"
                        color: textSubtle
                        font.pixelSize: 12
                        font.italic: true
                    }
                }
            }
        }

        // Right column: Evidence + Verdict
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: panelMargin

            // QRA Evidence Panel
            Panel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                panelTitle: "Evidence QRAs"

                ListView {
                    id: qraList
                    anchors.fill: parent
                    anchors.margins: 4
                    model: evidenceBridge.qras
                    spacing: 3
                    clip: true

                    delegate: Rectangle {
                        width: qraList.width
                        height: 40
                        radius: 4
                        color: bgInput

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 6
                            spacing: 6

                            // Control ID badge
                            Rectangle {
                                width: cidText.implicitWidth + 10
                                height: 20
                                radius: 4
                                color: Qt.rgba(accent.r, accent.g, accent.b, 0.15)

                                Text {
                                    id: cidText
                                    anchors.centerIn: parent
                                    text: modelData.control_id || "?"
                                    color: accent
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.question || ""
                                color: textSecondary
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }

                            Text {
                                text: (modelData.score || 0).toFixed(3)
                                color: textMuted
                                font.pixelSize: 10
                            }
                        }
                    }

                    Text {
                        visible: evidenceBridge.qras.length === 0
                        anchors.centerIn: parent
                        text: evidenceBridge.running ? "Searching /memory..." : "No QRAs yet"
                        color: textSubtle
                        font.pixelSize: 12
                        font.italic: true
                    }
                }
            }

            // Verdict Panel
            Panel {
                Layout.fillWidth: true
                Layout.preferredHeight: verdictContent.implicitHeight + 40
                Layout.minimumHeight: 80
                panelTitle: "Verdict"

                ColumnLayout {
                    id: verdictContent
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8

                    RowLayout {
                        spacing: 12
                        visible: evidenceBridge.verdict !== ""

                        // Verdict badge
                        Rectangle {
                            width: verdictText.implicitWidth + 20
                            height: 32
                            radius: 6
                            color: {
                                var v = evidenceBridge.verdict
                                if (v === "satisfied") return Qt.rgba(nvisGreen.r, nvisGreen.g, nvisGreen.b, 0.2)
                                if (v === "not_satisfied") return Qt.rgba(nvisRed.r, nvisRed.g, nvisRed.b, 0.2)
                                return Qt.rgba(nvisYellow.r, nvisYellow.g, nvisYellow.b, 0.15)
                            }

                            Text {
                                id: verdictText
                                anchors.centerIn: parent
                                text: evidenceBridge.verdict.toUpperCase()
                                color: {
                                    var v = evidenceBridge.verdict
                                    if (v === "satisfied") return nvisGreen
                                    if (v === "not_satisfied") return nvisRed
                                    return nvisYellow
                                }
                                font.pixelSize: 14
                                font.weight: Font.Bold
                            }
                        }

                        // Grade
                        Text {
                            visible: evidenceBridge.grade !== ""
                            text: "Grade: " + evidenceBridge.grade
                            color: textPrimary
                            font.pixelSize: 16
                            font.weight: Font.Bold
                        }
                    }

                    // Reason
                    Text {
                        visible: evidenceBridge.reason !== ""
                        text: evidenceBridge.reason
                        color: textSecondary
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    // Empty state
                    Text {
                        visible: evidenceBridge.verdict === ""
                        text: evidenceBridge.running ? "Pipeline running..." : "Enter a question and click Evaluate"
                        color: textSubtle
                        font.pixelSize: 12
                        font.italic: true
                    }
                }
            }
        }

        // Right column: Agent Chat Well
        ColumnLayout {
            Layout.preferredWidth: 320
            Layout.fillHeight: true
            spacing: 0

            // Chat panel
            Panel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                panelTitle: evidenceBridge.agentConnected ? "AGENT CHAT" : "AGENT CHAT (offline)"

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Chat messages scroll area
                    ListView {
                        id: chatList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.margins: 4
                        model: evidenceBridge.chatHistory
                        spacing: 6
                        clip: true

                        delegate: Rectangle {
                            width: chatList.width - 8
                            x: 4
                            height: msgText.implicitHeight + 16
                            radius: 8
                            color: modelData.role === "user"
                                ? Qt.rgba(accent.r, accent.g, accent.b, 0.12)
                                : bgInput

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 2

                                // Role label
                                Text {
                                    text: modelData.role === "user" ? "You" : "Agent"
                                    color: modelData.role === "user" ? accent : nvisGreen
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    font.capitalization: Font.AllUppercase
                                }

                                // Message text
                                Text {
                                    id: msgText
                                    text: modelData.text || ""
                                    color: textSecondary
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        // Auto-scroll to bottom on new messages
                        onCountChanged: {
                            Qt.callLater(function() {
                                chatList.positionViewAtEnd()
                            })
                        }

                        // Empty state
                        Text {
                            visible: evidenceBridge.chatHistory.length === 0
                            anchors.centerIn: parent
                            text: evidenceBridge.agentConnected
                                ? "Talk to the agent about this evidence case"
                                : "Start subagent on :8620 to enable chat"
                            color: textSubtle
                            font.pixelSize: 12
                            font.italic: true
                            horizontalAlignment: Text.AlignHCenter
                            width: parent.width - 24
                            wrapMode: Text.WordWrap
                        }
                    }

                    // Separator
                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: separator
                    }

                    // Chat input row
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.margins: 6
                        spacing: 6

                        TextField {
                            id: chatInput
                            Layout.fillWidth: true
                            placeholderText: "Override a gate, reject an entity..."
                            color: textPrimary
                            placeholderTextColor: textSubtle
                            font.pixelSize: 12
                            background: Rectangle {
                                color: bgInput
                                radius: 6
                                border.color: chatInput.activeFocus ? accent : border
                                border.width: 1
                            }
                            onAccepted: sendBtn.clicked()
                        }

                        Button {
                            id: sendBtn
                            text: "Send"
                            enabled: chatInput.text.length > 0
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            contentItem: Text {
                                text: sendBtn.text
                                color: sendBtn.enabled ? textPrimary : textMuted
                                font: sendBtn.font
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            background: Rectangle {
                                color: sendBtn.enabled ? (sendBtn.pressed ? "#3578cc" : accent) : "#333333"
                                radius: 6
                                implicitWidth: 52
                                implicitHeight: 30
                            }
                            onClicked: {
                                evidenceBridge.sendChat(chatInput.text)
                                chatInput.text = ""
                            }
                        }
                    }
                }
            }
        }
    }

    // ── Reusable Panel component ───────────────────────
    component Panel: Rectangle {
        property string panelTitle: ""
        default property alias contentChildren: panelContent.data

        color: bgElevated
        radius: panelRadius
        border.color: border
        border.width: 1

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // Title bar
            Rectangle {
                Layout.fillWidth: true
                height: 28
                color: "transparent"

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: panelTitle
                    color: textMuted
                    font.pixelSize: 11
                    font.weight: Font.Medium
                    font.capitalization: Font.AllUppercase
                    font.letterSpacing: 1.2
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: separator
            }

            Item {
                id: panelContent
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }
    }
}
