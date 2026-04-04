import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// EnsemblePage -- combine multiple models into an ensemble.
// Add models with weight sliders, pick a strategy, test and compare.

Item {
    id: ensemblePage

    property var ensembleModels: []  // [{path: "", weight: 0.5}, ...]
    property var ensembleResult: {
        try { return JSON.parse(classifierBridge.ensembleResultJson || "{}") }
        catch (e) { return {} }
    }

    function addModel(path) {
        var m = ensembleModels.slice()
        m.push({ path: path, weight: 0.5 })
        ensembleModels = m
    }

    function removeModel(idx) {
        var m = ensembleModels.slice()
        m.splice(idx, 1)
        ensembleModels = m
    }

    function updateWeight(idx, w) {
        var m = ensembleModels.slice()
        m[idx] = { path: m[idx].path, weight: w }
        ensembleModels = m
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Header -------------------------------------------------------
        Text {
            text: "Ensemble Builder"
            font.pixelSize: EmbryStyle.text.base
            font.weight: EmbryStyle.text.weightSemibold
            color: EmbryStyle.colors.textPrimary
        }

        // -- Add Model Row ------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            EmbryTextField {
                id: newModelField

                Layout.fillWidth: true
                placeholderText: "/path/to/model.pt"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "New model path"

                Keys.onReturnPressed: {
                    if (newModelField.text.length > 0) {
                        addModel(newModelField.text)
                        newModelField.text = ""
                    }
                }
            }

            EmbryButton {
                id: addModelBtn

                text: "Add Model"
                enabled: newModelField.text.length > 0

                Accessible.name: "Add model to ensemble"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: addModelBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput
                    border.width: 1
                    border.color: EmbryStyle.colors.accent
                    radius: EmbryStyle.layout.radiusSm
                }
                contentItem: Text {
                    text: addModelBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.accent
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: {
                    addModel(newModelField.text)
                    newModelField.text = ""
                }
            }
        }

        // -- Model List with Weight Sliders -------------------------------
        ListView {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(200, ensembleModels.length * 44 + 4)
            clip: true
            model: ensembleModels
            spacing: 2

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: ListView.view ? ListView.view.width : 0
                height: 40
                radius: EmbryStyle.layout.radiusSm
                color: EmbryStyle.colors.bgInput

                Accessible.name: (modelData.path || "model") + " weight " + (modelData.weight || 0).toFixed(2)
                Accessible.role: Accessible.ListItem

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: EmbryStyle.layout.space2
                    anchors.rightMargin: EmbryStyle.layout.space2
                    spacing: EmbryStyle.layout.space2

                    Text {
                        Layout.fillWidth: true
                        text: modelData.path || ""
                        font.pixelSize: EmbryStyle.text.xs
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textPrimary
                        elide: Text.ElideMiddle
                    }

                    Text {
                        text: "W:"
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textMuted
                    }

                    Slider {
                        id: weightSlider

                        Layout.preferredWidth: 120
                        from: 0.0; to: 1.0
                        stepSize: 0.05
                        value: modelData.weight || 0.5

                        Accessible.name: "Weight for " + (modelData.path || "model")
                        Accessible.role: Accessible.Slider

                        onMoved: updateWeight(index, value)
                    }

                    Text {
                        Layout.preferredWidth: 36
                        text: (modelData.weight || 0).toFixed(2)
                        font.pixelSize: EmbryStyle.text.xs
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.accent
                        horizontalAlignment: Text.AlignRight
                    }

                    // Remove button
                    Rectangle {
                        width: 22; height: 22
                        radius: EmbryStyle.layout.radiusSm
                        color: rmMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"

                        Accessible.name: "Remove model"
                        Accessible.role: Accessible.Button

                        Text {
                            anchors.centerIn: parent
                            text: EmbryStyle.icons.remove
                            font.pixelSize: EmbryStyle.text.sm
                            color: EmbryStyle.colors.accentRed
                        }

                        MouseArea {
                            id: rmMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: removeModel(index)
                        }
                    }
                }
            }
        }

        // -- Strategy + Run -----------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Strategy"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }

            EmbryComboBox {
                id: strategyCombo

                Layout.preferredWidth: 160
                model: ["voting", "averaging", "stacking"]

                Accessible.name: "Ensemble strategy"
            }

            EmbryButton {
                id: testEnsembleBtn

                text: "Test Ensemble"
                enabled: ensembleModels.length >= 2

                Accessible.name: "Test ensemble"
                Accessible.role: Accessible.Button

                background: Rectangle {
                    color: testEnsembleBtn.enabled
                        ? (testEnsembleBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput)
                        : EmbryStyle.colors.bgPressed
                    border.width: 1
                    border.color: EmbryStyle.colors.accentGreen
                    radius: EmbryStyle.layout.radiusSm
                }
                contentItem: Text {
                    text: testEnsembleBtn.text
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightSemibold
                    color: testEnsembleBtn.enabled
                        ? EmbryStyle.colors.accentGreen : EmbryStyle.colors.textDisabled
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: {
                    classifierBridge.runEnsemble(
                        JSON.stringify(ensembleModels),
                        strategyCombo.currentText
                    )
                }
            }

            Item { Layout.fillWidth: true }
        }

        // -- Ensemble Result ----------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border
            visible: typeof ensembleResult.ensemble_accuracy !== "undefined"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                Text {
                    text: "Ensemble Results"
                    font.pixelSize: EmbryStyle.text.base
                    font.weight: EmbryStyle.text.weightSemibold
                    color: EmbryStyle.colors.textPrimary
                }

                // Ensemble accuracy
                RowLayout {
                    spacing: EmbryStyle.layout.space3

                    Text { text: "Ensemble Accuracy:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }
                    Text {
                        text: parseFloat(ensembleResult.ensemble_accuracy || 0).toFixed(4)
                        font.pixelSize: EmbryStyle.text.lg
                        font.weight: EmbryStyle.text.weightBold
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.accentGreen
                    }
                }

                // Individual model comparison
                Text {
                    text: "vs Individual Models:"
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.textMuted
                    visible: (ensembleResult.individual || []).length > 0
                }

                Repeater {
                    model: ensembleResult.individual || []

                    RowLayout {
                        spacing: EmbryStyle.layout.space2

                        Text {
                            Layout.fillWidth: true
                            text: modelData.path || modelData.model || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textSecondary
                            elide: Text.ElideMiddle
                        }
                        Text {
                            text: parseFloat(modelData.accuracy || 0).toFixed(4)
                            font.pixelSize: EmbryStyle.text.sm
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textMuted
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
