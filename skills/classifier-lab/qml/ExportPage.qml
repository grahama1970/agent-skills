import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// ExportPage -- export trained models to ONNX, TorchScript, or joblib.
// Shows export status and list of previously exported models.

Item {
    id: exportPage

    property var exportList: {
        try { return JSON.parse(classifierBridge.exportListJson || "[]") }
        catch (e) { return [] }
    }
    property string exportStatus: ""

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Header -------------------------------------------------------
        Text {
            text: "Model Export"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        // -- Export Form --------------------------------------------------
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: EmbryStyle.layout.space3
            rowSpacing: EmbryStyle.layout.space2

            Text {
                text: "Source Model"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }
            EmbryTextField {
                id: srcModelField

                Layout.fillWidth: true
                placeholderText: "/path/to/model.pt"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Source model path"
            }

            Text {
                text: "Format"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }
            EmbryComboBox {
                id: formatCombo

                Layout.fillWidth: true
                model: ["ONNX", "TorchScript", "joblib"]

                Accessible.name: "Export format"
            }

            Text {
                text: "Output Path"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }
            EmbryTextField {
                id: outputPathField

                Layout.fillWidth: true
                placeholderText: "/path/to/exported_model.onnx"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Export output path"
            }
        }

        // -- Export Button + Status ---------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            EmbryButton {
                id: exportBtn

                text: "Export"
                enabled: srcModelField.text.length > 0
                    && outputPathField.text.length > 0

                Accessible.name: "Export model"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: exportBtn.enabled
                        ? (exportBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput)
                        : EmbryStyle.colors.bgPressed
                    border.width: 1
                    border.color: EmbryStyle.colors.accentGreen
                    radius: EmbryStyle.layout.radiusSm
                }
                contentItem: Text {
                    text: exportBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightSemibold
                    color: exportBtn.enabled
                        ? EmbryStyle.colors.accentGreen : EmbryStyle.colors.textDisabled
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: {
                    classifierBridge.exportModel(
                        srcModelField.text,
                        formatCombo.currentText,
                        outputPathField.text
                    )
                }
            }

            Text {
                text: exportStatus
                font.pixelSize: EmbryStyle.text.sm
                color: exportStatus.indexOf("Error") >= 0
                    ? EmbryStyle.colors.accentRed
                    : EmbryStyle.colors.accentGreen
                visible: exportStatus.length > 0
            }

            Item { Layout.fillWidth: true }
        }

        // -- Exported Models List -----------------------------------------
        Text {
            text: "Exported Models"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
            visible: exportList.length > 0
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: exportList
            spacing: 2
            visible: exportList.length > 0

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: ListView.view ? ListView.view.width : 0
                height: 36
                radius: EmbryStyle.layout.radiusSm
                color: EmbryStyle.colors.bgInput

                Accessible.name: (modelData.format || "unknown") + " export: " + (modelData.path || "no path")
                Accessible.role: Accessible.ListItem

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: EmbryStyle.layout.space2
                    anchors.rightMargin: EmbryStyle.layout.space2
                    spacing: EmbryStyle.layout.space2

                    // Format badge
                    Rectangle {
                        width: fmtText.implicitWidth + EmbryStyle.layout.space2 * 2
                        height: EmbryStyle.layout.badgeHeight
                        radius: EmbryStyle.layout.badgeRadius
                        color: EmbryStyle.colors.statusInfoBg

                        Text {
                            id: fmtText
                            anchors.centerIn: parent
                            text: modelData.format || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightSemibold
                            color: EmbryStyle.colors.accent
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: modelData.path || ""
                        font.pixelSize: EmbryStyle.text.xs
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textPrimary
                        elide: Text.ElideMiddle
                    }

                    Text {
                        text: modelData.size_mb
                            ? (parseFloat(modelData.size_mb).toFixed(1) + " MB")
                            : ""
                        font.pixelSize: EmbryStyle.text.xs
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textMuted
                    }

                    Text {
                        text: modelData.timestamp || ""
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textGhost
                    }
                }
            }
        }
    }

    // Listen for export completion
    Connections {
        target: classifierBridge
        function onExportListJsonChanged() {
            exportStatus = "Export complete"
        }
    }
}
