import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// EvaluatePage -- load a trained model, run on test data, display
// confusion matrix and per-class metrics.

Item {
    id: evalPage

    property var evalResult: {
        try { return JSON.parse(classifierBridge.evaluateResultJson || "{}") }
        catch (e) { return {} }
    }
    property var confMatrix: evalResult.confusion_matrix || []
    property var classNames: evalResult.class_names || []
    property var perClass: evalResult.per_class || []
    property real overallAcc: parseFloat(evalResult.accuracy || 0)
    property real overallF1: parseFloat(evalResult.macro_f1 || 0)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Model + Data Inputs ------------------------------------------
        Text {
            text: "Model Evaluation"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: EmbryStyle.layout.space2
            rowSpacing: EmbryStyle.layout.space2

            Text {
                text: "Model Path"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }
            EmbryTextField {
                id: modelPathField

                Layout.fillWidth: true
                placeholderText: "/path/to/model.pt"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Model file path"
            }
            EmbryButton {
                id: loadBtn

                text: "Load"
                enabled: modelPathField.text.length > 0

                Accessible.name: "Load model"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: loadBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput
                    border.width: 1
                    border.color: EmbryStyle.colors.accent
                    radius: EmbryStyle.layout.radiusSm
                }
                contentItem: Text {
                    text: loadBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.accent
                    horizontalAlignment: Text.AlignHCenter
                }
            }

            Text {
                text: "Test Data"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }
            EmbryTextField {
                id: testPathField

                Layout.fillWidth: true
                placeholderText: "/path/to/test_data/"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Test data path"
            }
            EmbryButton {
                id: evalBtn

                text: "Evaluate"
                enabled: modelPathField.text.length > 0
                    && testPathField.text.length > 0

                Accessible.name: "Run evaluation"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: evalBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput
                    border.width: 1
                    border.color: EmbryStyle.colors.accentGreen
                    radius: EmbryStyle.layout.radiusSm
                }
                contentItem: Text {
                    text: evalBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightSemibold
                    color: EmbryStyle.colors.accentGreen
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: classifierBridge.evaluate(
                    modelPathField.text, testPathField.text
                )
            }
        }

        // -- Summary Cards ------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3
            visible: perClass.length > 0

            Repeater {
                model: [
                    { label: "Accuracy", value: overallAcc.toFixed(4), clr: EmbryStyle.colors.accentGreen },
                    { label: "Macro F1", value: overallF1.toFixed(4), clr: EmbryStyle.colors.accent },
                ]

                Rectangle {
                    Layout.preferredWidth: 140
                    height: 56
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: (modelData.label || "")
                            font.pixelSize: EmbryStyle.text.xs
                            color: EmbryStyle.colors.textMuted
                        }
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: (modelData.value || "0")
                            font.pixelSize: EmbryStyle.text.lg
                            font.weight: EmbryStyle.text.weightBold
                            font.family: EmbryStyle.text.monoFamily
                            color: modelData.clr || EmbryStyle.colors.textPrimary
                        }
                    }
                }
            }
        }

        // -- Confusion Matrix ---------------------------------------------
        Text {
            text: "Confusion Matrix"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
            visible: confMatrix.length > 0
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(300, (confMatrix.length + 1) * 34)
            clip: true
            visible: confMatrix.length > 0

            GridLayout {
                columns: confMatrix.length + 1
                columnSpacing: 2
                rowSpacing: 2

                // Header: empty corner + class names
                Rectangle { width: 80; height: 28; color: "transparent" }
                Repeater {
                    model: classNames
                    Rectangle {
                        width: 56; height: 28
                        color: EmbryStyle.colors.bgElevated
                        radius: 2
                        Text {
                            anchors.centerIn: parent
                            text: modelData || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightSemibold
                            color: EmbryStyle.colors.textMuted
                            elide: Text.ElideRight
                        }
                    }
                }

                // Matrix rows
                Repeater {
                    model: confMatrix.length

                    // Row container -- row label + cells
                    Repeater {
                        property int rowIdx: index
                        model: confMatrix.length + 1

                        Rectangle {
                            property int colIdx: index - 1
                            property bool isLabel: index === 0
                            property bool isDiag: !isLabel && (colIdx === rowIdx)
                            property real cellVal: (!isLabel && confMatrix[rowIdx])
                                ? (confMatrix[rowIdx][colIdx] || 0) : 0
                            property real maxVal: {
                                if (isLabel) return 1
                                var mx = 1
                                for (var r = 0; r < confMatrix.length; r++)
                                    for (var c = 0; c < confMatrix[r].length; c++)
                                        if (confMatrix[r][c] > mx) mx = confMatrix[r][c]
                                return mx
                            }

                            width: isLabel ? 80 : 56
                            height: 28
                            radius: 2
                            color: isLabel
                                ? EmbryStyle.colors.bgElevated
                                : isDiag
                                    ? Qt.rgba(0, 1, 0.533, 0.1 + 0.3 * (cellVal / maxVal))
                                    : cellVal > 0
                                        ? Qt.rgba(1, 0.267, 0.267, 0.05 + 0.2 * (cellVal / maxVal))
                                        : EmbryStyle.colors.bgInput

                            Text {
                                anchors.centerIn: parent
                                text: isLabel
                                    ? (classNames[rowIdx] || "")
                                    : String(Math.round(cellVal))
                                font.pixelSize: EmbryStyle.text.xs
                                font.family: isLabel ? EmbryStyle.text.fontFamily : EmbryStyle.text.monoFamily
                                font.weight: isDiag ? EmbryStyle.text.weightBold : EmbryStyle.text.weightNormal
                                color: isLabel
                                    ? EmbryStyle.colors.textMuted
                                    : isDiag
                                        ? EmbryStyle.colors.accentGreen
                                        : EmbryStyle.colors.textSecondary
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }

        // -- Per-Class Metrics --------------------------------------------
        Text {
            text: "Per-Class Metrics"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
            visible: perClass.length > 0
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: perClass
            spacing: 2
            visible: perClass.length > 0

            header: Rectangle {
                width: ListView.view ? ListView.view.width : 0
                height: 26
                color: EmbryStyle.colors.bgElevated

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: EmbryStyle.layout.space2
                    anchors.rightMargin: EmbryStyle.layout.space2

                    Text { Layout.fillWidth: true; text: "Class"; font.pixelSize: EmbryStyle.text.xs; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textMuted }
                    Text { Layout.preferredWidth: 70; text: "Precision"; font.pixelSize: EmbryStyle.text.xs; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignRight }
                    Text { Layout.preferredWidth: 70; text: "Recall"; font.pixelSize: EmbryStyle.text.xs; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignRight }
                    Text { Layout.preferredWidth: 70; text: "F1"; font.pixelSize: EmbryStyle.text.xs; font.weight: EmbryStyle.text.weightSemibold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignRight }
                }
            }

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: ListView.view ? ListView.view.width : 0
                height: 28
                color: EmbryStyle.colors.bgInput
                radius: 2

                Accessible.name: (modelData.name || "class") + " precision " + parseFloat(modelData.precision || 0).toFixed(4) + " f1 " + parseFloat(modelData.f1 || 0).toFixed(4)
                Accessible.role: Accessible.ListItem

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: EmbryStyle.layout.space2
                    anchors.rightMargin: EmbryStyle.layout.space2

                    Text { Layout.fillWidth: true; text: modelData.name || ""; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                    Text { Layout.preferredWidth: 70; text: parseFloat(modelData.precision || 0).toFixed(4); font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary; horizontalAlignment: Text.AlignRight }
                    Text { Layout.preferredWidth: 70; text: parseFloat(modelData.recall || 0).toFixed(4); font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary; horizontalAlignment: Text.AlignRight }
                    Text { Layout.preferredWidth: 70; text: parseFloat(modelData.f1 || 0).toFixed(4); font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary; horizontalAlignment: Text.AlignRight }
                }
            }
        }
    }
}
