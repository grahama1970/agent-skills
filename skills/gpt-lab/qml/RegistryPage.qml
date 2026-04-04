import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// RegistryPage -- Model registry viewer and editor.
// Reads candidate_models and api_models from bridge.registryJson.

Item {
    id: root

    property var registry: appWindow.registry
    property var candidates: (registry && registry.candidate_models) || []
    property var apiModels: (registry && registry.api_models) || []
    property int selectedCandidate: -1

    // Add-model form state
    property string newName: ""
    property string newParams: ""
    property string newType: "base"
    property string newProvider: "hf"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Section: Candidate Models --
        Text {
            text: "Candidate Models"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: 200
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Table header
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: EmbryStyle.colors.bgInput

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: EmbryStyle.layout.space3
                        anchors.rightMargin: EmbryStyle.layout.space3
                        spacing: EmbryStyle.layout.space2

                        Text { Layout.preferredWidth: 280; text: "Name"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 80;  text: "Params (B)"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 100; text: "Type"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 100; text: "Provider"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Item { Layout.fillWidth: true }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                ListView {
                    id: candidateList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: candidates

                    delegate: Rectangle {
                        width: candidateList.width
                        height: 36
                        color: root.selectedCandidate === index
                            ? EmbryStyle.colors.selectBg
                            : rowMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"

                        Accessible.name: (modelData.name || "") + " model row"
                        Accessible.role: Accessible.ListItem

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: EmbryStyle.layout.space3
                            anchors.rightMargin: EmbryStyle.layout.space3
                            spacing: EmbryStyle.layout.space2

                            Text { Layout.preferredWidth: 280; text: modelData.name || ""; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                            Text { Layout.preferredWidth: 80;  text: String(modelData.params_b || ""); font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.accentGreen }
                            // Type badge
                            Rectangle {
                                Layout.preferredWidth: 100
                                width: typeBadgeText.implicitWidth + EmbryStyle.layout.space3
                                height: 20
                                radius: EmbryStyle.layout.badgeRadius
                                color: (modelData.type || "") === "finetuned" ? EmbryStyle.colors.statusInfoBg : EmbryStyle.colors.badge

                                Text {
                                    id: typeBadgeText
                                    anchors.centerIn: parent
                                    text: modelData.type || "base"
                                    font.pixelSize: EmbryStyle.text.xs
                                    font.weight: EmbryStyle.text.weightBold
                                    color: (modelData.type || "") === "finetuned" ? EmbryStyle.colors.accent : EmbryStyle.colors.textSecondary
                                }
                            }
                            Text { Layout.preferredWidth: 100; text: modelData.provider || ""; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
                            Item { Layout.fillWidth: true }
                        }

                        MouseArea {
                            id: rowMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.selectedCandidate = index
                        }
                    }
                }
            }
        }

        // -- Section: API Models --
        Text {
            text: "API Models"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        Rectangle {
            Layout.fillWidth: true
            height: Math.max(80, apiList.contentHeight + 36)
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: EmbryStyle.colors.bgInput

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: EmbryStyle.layout.space3
                        anchors.rightMargin: EmbryStyle.layout.space3
                        spacing: EmbryStyle.layout.space2

                        Text { Layout.preferredWidth: 200; text: "Name"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.preferredWidth: 100; text: "Provider"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                        Text { Layout.fillWidth: true; text: "Notes"; font.pixelSize: EmbryStyle.text.sm; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textSecondary }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                ListView {
                    id: apiList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: apiModels

                    delegate: Rectangle {
                        width: apiList.width
                        height: 32
                        color: "transparent"

                        Accessible.name: (modelData.name || "") + " API model"
                        Accessible.role: Accessible.ListItem

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: EmbryStyle.layout.space3
                            anchors.rightMargin: EmbryStyle.layout.space3
                            spacing: EmbryStyle.layout.space2

                            Text { Layout.preferredWidth: 200; text: modelData.name || ""; font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textPrimary }
                            Text { Layout.preferredWidth: 100; text: modelData.provider || ""; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textMuted }
                            Text { Layout.fillWidth: true; text: modelData.notes || ""; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSubtle; elide: Text.ElideRight }
                        }
                    }
                }
            }
        }

        // -- Add Model Form --
        Text {
            text: "Add Model"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            EmbryTextField {
                id: nameField
                Layout.preferredWidth: 240
                placeholderText: "Model name"
                text: root.newName
                onTextChanged: root.newName = text
                Accessible.name: "Model name input"
            }

            EmbryTextField {
                id: paramsField
                Layout.preferredWidth: 80
                placeholderText: "Params B"
                text: root.newParams
                onTextChanged: root.newParams = text
                Accessible.name: "Parameter count input"
            }

            EmbryComboBox {
                id: typeCombo
                Layout.preferredWidth: 110
                model: ["base", "finetuned"]
                onCurrentTextChanged: root.newType = currentText
                Accessible.name: "Model type selector"
            }

            EmbryTextField {
                id: providerField
                Layout.preferredWidth: 100
                placeholderText: "Provider"
                text: root.newProvider
                onTextChanged: root.newProvider = text
                Accessible.name: "Provider input"
            }

            EmbryButton {
                text: "Add"
                variant: "primary"
                enabled: root.newName.length > 0
                onClicked: {
                    gptBridge.addModel(root.newName, root.newParams, root.newType, root.newProvider)
                    root.newName = ""
                    root.newParams = ""
                }
                Accessible.name: "Add model button"
                Accessible.role: Accessible.Button
            }

            EmbryButton {
                text: "Remove Selected"
                variant: "danger"
                enabled: root.selectedCandidate >= 0
                onClicked: {
                    var m = candidates[root.selectedCandidate]
                    if (m) {
                        gptBridge.removeModel(m.name || "")
                        root.selectedCandidate = -1
                    }
                }
                Accessible.name: "Remove selected model button"
                Accessible.role: Accessible.Button
            }
        }
    }
}
