import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// DeployPage -- model deployment and rollback management.

Item {
    id: root

    property var deployHistory: _parseHistory()

    function _parseHistory() {
        try {
            return JSON.parse(regressorBridge.deployHistoryJson || "[]")
        } catch (e) {
            return []
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // -- Deploy Controls --
        Text {
            text: "Deploy Model"
            font.pixelSize: EmbryStyle.text.lg
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        // Model path input
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Text {
                text: "Model Path"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            Rectangle {
                Layout.fillWidth: true
                height: 32
                radius: EmbryStyle.layout.radiusSm
                color: EmbryStyle.colors.bgInput
                border.width: 1
                border.color: modelPathInput.activeFocus
                    ? EmbryStyle.colors.borderFocused
                    : EmbryStyle.colors.borderInput

                TextInput {
                    id: modelPathInput
                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space2
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: EmbryStyle.text.sm
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.textPrimary
                    clip: true
                    selectByMouse: true

                    Accessible.name: "Model file path"
                    Accessible.role: Accessible.EditableText
                }
            }
        }

        // Task name input
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Text {
                text: "Target Task"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            Rectangle {
                Layout.fillWidth: true
                height: 32
                radius: EmbryStyle.layout.radiusSm
                color: EmbryStyle.colors.bgInput
                border.width: 1
                border.color: taskInput.activeFocus
                    ? EmbryStyle.colors.borderFocused
                    : EmbryStyle.colors.borderInput

                TextInput {
                    id: taskInput
                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space2
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: EmbryStyle.text.sm
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.textPrimary
                    clip: true
                    selectByMouse: true

                    Accessible.name: "Target task name"
                    Accessible.role: Accessible.EditableText
                }
            }

            // Deploy button
            Rectangle {
                width: deployBtnText.implicitWidth + EmbryStyle.layout.space4 * 2
                height: 32
                radius: EmbryStyle.layout.radiusSm
                color: deployBtnMa.containsMouse
                    ? EmbryStyle.colors.bgPressed
                    : EmbryStyle.colors.bgInput
                border.width: 1
                border.color: EmbryStyle.colors.accentGreen

                Accessible.name: "Deploy to discovery.py"
                Accessible.role: Accessible.Button

                Text {
                    id: deployBtnText
                    anchors.centerIn: parent
                    text: "Deploy to discovery.py"
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightSemibold
                    color: EmbryStyle.colors.accentGreen
                }

                MouseArea {
                    id: deployBtnMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (modelPathInput.text && taskInput.text) {
                            regressorBridge.deploy(modelPathInput.text, taskInput.text)
                        }
                    }
                    Accessible.name: "Deploy model"
                    Accessible.role: Accessible.Button
                }
            }
        }

        // -- Deployment History --
        Text {
            text: "Deployment History"
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

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space2
                spacing: 0

                // Header
                Row {
                    Layout.fillWidth: true
                    spacing: 1

                    Repeater {
                        model: ["Task", "Model Type", "Deployed At", "Path", ""]
                        Text {
                            width: {
                                var colWidths = [0.2, 0.15, 0.2, 0.35, 0.1]
                                return (root.width - EmbryStyle.layout.space4 * 2 - EmbryStyle.layout.space2 * 2) * colWidths[index]
                            }
                            height: 26
                            horizontalAlignment: Text.AlignLeft
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: EmbryStyle.layout.space2
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

                // History list
                ListView {
                    id: historyList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: deployHistory
                    spacing: 1

                    delegate: Rectangle {
                        width: historyList.width
                        height: 32
                        radius: EmbryStyle.layout.radiusSm
                        color: histRowMa.containsMouse
                            ? EmbryStyle.colors.bgHover
                            : "transparent"

                        Accessible.name: "Deployment: " + (modelData.task || "") + " - " + (modelData.model_type || "")
                        Accessible.role: Accessible.ListItem

                        Row {
                            anchors.fill: parent
                            spacing: 1

                            Text {
                                width: parent.width * 0.2
                                height: parent.height
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: EmbryStyle.layout.space2
                                text: modelData.task || ""
                                font.pixelSize: EmbryStyle.text.xs
                                font.weight: EmbryStyle.text.weightSemibold
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textPrimary
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width * 0.15
                                height: parent.height
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: EmbryStyle.layout.space2
                                text: modelData.model_type || ""
                                font.pixelSize: EmbryStyle.text.xs
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textSecondary
                            }

                            Text {
                                width: parent.width * 0.2
                                height: parent.height
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: EmbryStyle.layout.space2
                                text: modelData.deployed_at || ""
                                font.pixelSize: EmbryStyle.text.xs
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textMuted
                            }

                            Text {
                                width: parent.width * 0.35
                                height: parent.height
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: EmbryStyle.layout.space2
                                text: modelData.path || ""
                                font.pixelSize: EmbryStyle.text.xs
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textMuted
                                elide: Text.ElideMiddle
                            }

                            // Rollback button
                            Rectangle {
                                width: parent.width * 0.1
                                height: parent.height - 6
                                anchors.verticalCenter: parent.verticalCenter
                                radius: EmbryStyle.layout.radiusSm
                                color: rollbackMa.containsMouse
                                    ? EmbryStyle.colors.statusCriticalBg
                                    : "transparent"

                                Accessible.name: "Rollback " + (modelData.task || "")
                                Accessible.role: Accessible.Button

                                Text {
                                    anchors.centerIn: parent
                                    text: "Rollback"
                                    font.pixelSize: EmbryStyle.text.xs
                                    font.weight: EmbryStyle.text.weightMedium
                                    color: rollbackMa.containsMouse
                                        ? EmbryStyle.colors.accentRed
                                        : EmbryStyle.colors.textMuted
                                }

                                MouseArea {
                                    id: rollbackMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: regressorBridge.rollback(modelData.task || "")
                                    Accessible.name: "Rollback deployment"
                                    Accessible.role: Accessible.Button
                                }
                            }
                        }

                        MouseArea {
                            id: histRowMa
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                        }
                    }
                }

                // Empty state
                Text {
                    visible: deployHistory.length === 0
                    Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
                    text: "No deployments yet"
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.textMuted
                }
            }
        }
    }
}
