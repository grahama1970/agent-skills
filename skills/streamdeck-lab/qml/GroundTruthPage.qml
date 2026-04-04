import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// GroundTruthPage -- edit and manage ground truth definitions for template evaluation.

Item {
    id: root

    required property QtObject deckBridge
    property string selectedContext: contextCombo.currentText
    property var groundTruth: ({})
    property var requiredWorkflows: []
    property var forbiddenItems: []

    Component.onCompleted: loadContext()

    function loadContext() {
        try {
            var allGt = JSON.parse(deckBridge.groundTruthJson || "[]")
            var match = null
            for (var i = 0; i < allGt.length; i++) {
                if ((allGt[i].context || "") === selectedContext) {
                    match = allGt[i]
                    break
                }
            }
            if (match) {
                groundTruth = match
                requiredWorkflows = match.required_workflows || []
                forbiddenItems = match.forbidden || []
            } else {
                groundTruth = {}
                requiredWorkflows = []
                forbiddenItems = []
            }
        } catch(e) {
            groundTruth = {}
            requiredWorkflows = []
            forbiddenItems = []
        }
    }

    Connections {
        target: deckBridge
        function onGroundTruthJsonChanged() { loadContext() }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Header --
        RowLayout {
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Ground Truth Editor"
                font.pixelSize: EmbryStyle.text.lg
                font.weight: Font.Bold
                color: EmbryStyle.colors.textPrimary
            }

            Item { Layout.fillWidth: true }

            // Context selector
            Text {
                text: "Context:"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }

            EmbryComboBox {
                id: contextCombo
                model: ["sentinel_hud", "compliance_dashboard", "f36_plant_floor"]
                implicitWidth: 200
                onCurrentTextChanged: loadContext()

                Accessible.name: "Context selector"
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

        // -- Content --
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space4

            // Left column: Required Workflows
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1
                border.color: EmbryStyle.colors.border

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space3
                    spacing: EmbryStyle.layout.space2

                    RowLayout {
                        Text {
                            text: "Required Workflows"
                            font.pixelSize: EmbryStyle.text.base
                            font.weight: Font.DemiBold
                            color: EmbryStyle.colors.textPrimary
                        }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            width: wfCountTxt.implicitWidth + EmbryStyle.layout.space2
                            height: 18; radius: 4
                            color: EmbryStyle.colors.statusOkBg
                            Text { id: wfCountTxt; anchors.centerIn: parent; text: requiredWorkflows.length + ""; font.pixelSize: 8; font.weight: Font.Bold; color: EmbryStyle.colors.accentGreen }
                        }
                    }

                    ListView {
                        id: workflowList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: requiredWorkflows
                        spacing: 2

                        delegate: Rectangle {
                            width: workflowList.width
                            height: 32
                            radius: EmbryStyle.layout.radiusSm
                            color: wfMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"

                            Accessible.name: (modelData || "workflow") + " required workflow"
                            Accessible.role: Accessible.ListItem

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: EmbryStyle.layout.space2
                                anchors.rightMargin: EmbryStyle.layout.space2

                                Text {
                                    text: modelData || ""
                                    font.pixelSize: EmbryStyle.text.sm
                                    font.family: EmbryStyle.text.monoFamily
                                    color: EmbryStyle.colors.textPrimary
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }

                                Text {
                                    text: EmbryStyle.icons.remove
                                    font.pixelSize: EmbryStyle.text.sm
                                    color: EmbryStyle.colors.accentRed
                                    visible: wfMa.containsMouse
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            var wf = requiredWorkflows.slice()
                                            wf.splice(index, 1)
                                            requiredWorkflows = wf
                                        }
                                    }
                                    Accessible.name: "Remove workflow"; Accessible.role: Accessible.Button
                                }
                            }

                            MouseArea { id: wfMa; anchors.fill: parent; hoverEnabled: true; z: -1 }
                        }
                    }

                    // Add workflow
                    RowLayout {
                        spacing: EmbryStyle.layout.space2
                        EmbryTextField {
                            id: newWorkflowField
                            Layout.fillWidth: true
                            placeholderText: "Add workflow..."
                            onAccepted: addWorkflowBtn.clicked()
                            Accessible.name: "New workflow name"
                        }
                        EmbryButton {
                            id: addWorkflowBtn
                            text: "Add"
                            onClicked: {
                                if (newWorkflowField.text.trim()) {
                                    var wf = requiredWorkflows.slice()
                                    wf.push(newWorkflowField.text.trim())
                                    requiredWorkflows = wf
                                    newWorkflowField.text = ""
                                }
                            }
                            Accessible.name: "Add workflow"; Accessible.role: Accessible.Button
                        }
                    }
                }
            }

            // Right column: Forbidden items + Palette + Button count
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: EmbryStyle.layout.space3

                // Forbidden items
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: EmbryStyle.layout.space3
                        spacing: EmbryStyle.layout.space2

                        Text {
                            text: "Forbidden Items"
                            font.pixelSize: EmbryStyle.text.base
                            font.weight: Font.DemiBold
                            color: EmbryStyle.colors.textPrimary
                        }

                        ListView {
                            id: forbiddenList
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            model: forbiddenItems
                            spacing: 2

                            delegate: Rectangle {
                                width: forbiddenList.width
                                height: 28
                                radius: EmbryStyle.layout.radiusSm
                                color: fbMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"

                                Accessible.name: (modelData || "item") + " forbidden item"
                                Accessible.role: Accessible.ListItem

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: EmbryStyle.layout.space2
                                    anchors.rightMargin: EmbryStyle.layout.space2

                                    Text { text: EmbryStyle.icons.forbidden; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.accentRed }
                                    Text { text: modelData || ""; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textPrimary; Layout.fillWidth: true; elide: Text.ElideRight }
                                    Text {
                                        text: EmbryStyle.icons.remove; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.accentRed; visible: fbMa.containsMouse
                                        MouseArea {
                                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: { var fb = forbiddenItems.slice(); fb.splice(index, 1); forbiddenItems = fb }
                                        }
                                        Accessible.name: "Remove forbidden item"; Accessible.role: Accessible.Button
                                    }
                                }
                                MouseArea { id: fbMa; anchors.fill: parent; hoverEnabled: true; z: -1 }
                            }
                        }

                        RowLayout {
                            spacing: EmbryStyle.layout.space2
                            EmbryTextField {
                                id: newForbiddenField; Layout.fillWidth: true; placeholderText: "Add forbidden..."
                                onAccepted: addForbiddenBtn.clicked()
                                Accessible.name: "New forbidden item"
                            }
                            EmbryButton {
                                id: addForbiddenBtn
                                text: "Add"
                                onClicked: {
                                    if (newForbiddenField.text.trim()) {
                                        var fb = forbiddenItems.slice()
                                        fb.push(newForbiddenField.text.trim())
                                        forbiddenItems = fb
                                        newForbiddenField.text = ""
                                    }
                                }
                                Accessible.name: "Add forbidden item"
                                Accessible.role: Accessible.Button
                            }
                        }
                    }
                }

                // Palette + Button count
                Rectangle {
                    Layout.fillWidth: true
                    height: 140
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: EmbryStyle.layout.space3
                        spacing: EmbryStyle.layout.space2

                        // NVIS compliance toggle
                        RowLayout {
                            spacing: EmbryStyle.layout.space3
                            Text { text: "Palette Requirements"; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.DemiBold; color: EmbryStyle.colors.textPrimary }
                            Item { Layout.fillWidth: true }
                            Switch {
                                id: nvisSwitch
                                checked: (groundTruth.palette || "") === "nvis"
                                Accessible.name: "NVIS compliance toggle"; Accessible.role: Accessible.CheckBox
                            }
                            Text { text: "NVIS"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: nvisSwitch.checked ? EmbryStyle.colors.accentGreen : EmbryStyle.colors.textMuted }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                        // Button count range
                        RowLayout {
                            spacing: EmbryStyle.layout.space3
                            Text { text: "Button count range:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }
                            Text { text: "Min:"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }
                            SpinBox {
                                id: minButtons; from: 1; to: 32; value: groundTruth.min_buttons || 6
                                Accessible.name: "Minimum button count"; Accessible.role: Accessible.SpinBox
                            }
                            Text { text: "Max:"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }
                            SpinBox {
                                id: maxButtons; from: 1; to: 32; value: groundTruth.max_buttons || 24
                                Accessible.name: "Maximum button count"; Accessible.role: Accessible.SpinBox
                            }
                        }
                    }
                }
            }
        }

        // -- Action Buttons --
        RowLayout {
            spacing: EmbryStyle.layout.space3

            EmbryButton {
                text: "Save Ground Truth"
                variant: "primary"
                onClicked: {
                    var data = {
                        context: selectedContext,
                        template: groundTruth.template || selectedContext,
                        required_workflows: requiredWorkflows,
                        forbidden: forbiddenItems,
                        palette: nvisSwitch.checked ? "nvis" : "standard",
                        min_buttons: minButtons.value,
                        max_buttons: maxButtons.value,
                        max_label_chars: 8
                    }
                    deckBridge.saveGroundTruth(selectedContext, JSON.stringify(data))
                }
                Accessible.name: "Save ground truth"; Accessible.role: Accessible.Button
            }

            EmbryButton {
                text: "Load From File"
                onClicked: deckBridge.loadGroundTruth(selectedContext)
                Accessible.name: "Load ground truth from file"; Accessible.role: Accessible.Button
            }

            Item { Layout.fillWidth: true }
        }
    }
}
