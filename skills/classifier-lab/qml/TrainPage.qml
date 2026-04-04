import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// TrainPage -- configure and launch classifier training jobs.
// Data source, backbone, hyperparameters, log output.

Item {
    id: trainPage

    property string selectedDataPath: ""
    property string selectedBackbone: backboneCombo.currentText

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Data Source --------------------------------------------------
        Text {
            text: "Data Source"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            EmbryComboBox {
                id: dataTypeCombo

                Layout.preferredWidth: 140
                model: ["JSONL File", "Image Dir", "Class Dir"]

                Accessible.name: "Data source type"
            }

            EmbryTextField {
                id: dataPathField

                Layout.fillWidth: true
                placeholderText: dataTypeCombo.currentIndex === 0
                    ? "/path/to/labels.jsonl"
                    : "/path/to/images/"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Data path"
            }
        }

        // -- Backbone Selector --------------------------------------------
        Text {
            text: "Backbone"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        EmbryComboBox {
            id: backboneCombo

            Layout.fillWidth: true
            model: [
                "efficientnet_b0",
                "efficientnet_b2",
                "resnet50",
                "convnextv2_nano",
                "mobilenetv3_small",
                "distilbert",
                "prajjwal1/bert-tiny",
                "tfidf_logreg",
                "tfidf_svm",
                "gradient_boosting",
                "random_forest",
            ]

            Accessible.name: "Model backbone"
        }

        // -- Training Parameters ------------------------------------------
        Text {
            text: "Parameters"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 6
            columnSpacing: EmbryStyle.layout.space2
            rowSpacing: EmbryStyle.layout.space2

            Text {
                text: "Epochs"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }
            SpinBox {
                id: epochsSpin

                value: 10
                from: 1; to: 500
                editable: true

                Accessible.name: "Epochs"
                Accessible.role: Accessible.SpinBox
            }

            Text {
                text: "Batch Size"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }
            SpinBox {
                id: batchSpin

                value: 32
                from: 1; to: 512
                stepSize: 8
                editable: true

                Accessible.name: "Batch size"
                Accessible.role: Accessible.SpinBox
            }

            Text {
                text: "Learning Rate"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }
            EmbryTextField {
                id: lrField

                Layout.preferredWidth: 100
                text: "0.001"
                validator: DoubleValidator { bottom: 0.0; top: 1.0; decimals: 6 }
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Learning rate"
            }
        }

        // -- Action Buttons -----------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            EmbryButton {
                id: trainBtn

                text: classifierBridge.trainingStatus === "training" ? "Training..." : "Start Train"
                enabled: classifierBridge.trainingStatus !== "training"
                    && dataPathField.text.length > 0

                Accessible.name: "Start training"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: trainBtn.enabled
                        ? (trainBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput)
                        : EmbryStyle.colors.bgPressed
                    border.width: 1
                    border.color: EmbryStyle.colors.accentGreen
                    radius: EmbryStyle.layout.radiusSm
                }
                contentItem: Text {
                    text: trainBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightSemibold
                    color: trainBtn.enabled ? EmbryStyle.colors.accentGreen : EmbryStyle.colors.textDisabled
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: classifierBridge.runTrain(
                    dataPathField.text,
                    backboneCombo.currentText,
                    epochsSpin.value,
                    batchSpin.value,
                    parseFloat(lrField.text)
                )
            }

            EmbryButton {
                id: dryRunBtn

                text: "Dry Run"
                enabled: classifierBridge.trainingStatus !== "training"
                    && dataPathField.text.length > 0

                Accessible.name: "Dry run training"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: dryRunBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput
                    border.width: 1
                    border.color: EmbryStyle.colors.border
                    radius: EmbryStyle.layout.radiusSm
                }
                contentItem: Text {
                    text: dryRunBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.textSecondary
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: classifierBridge.runTrain(
                    dataPathField.text,
                    backboneCombo.currentText,
                    1, batchSpin.value,
                    parseFloat(lrField.text)
                )
            }

            Item { Layout.fillWidth: true }
        }

        // -- Training Log -------------------------------------------------
        Text {
            text: "Training Log"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Accessible.name: "Training log output"
            Accessible.role: Accessible.StaticText

            TextArea {
                id: logArea

                readOnly: true
                Accessible.name: "Training log output"
                Accessible.role: Accessible.StaticText
                text: classifierBridge.trainLogText || ""
                font.pixelSize: EmbryStyle.text.xs
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textSecondary
                wrapMode: Text.WordWrap
                background: Rectangle {
                    color: EmbryStyle.colors.bgInput
                    radius: EmbryStyle.layout.radiusSm
                }

                onTextChanged: {
                    if (logArea.contentHeight > logArea.height) {
                        logArea.cursorPosition = logArea.length
                    }
                }
            }
        }
    }
}
