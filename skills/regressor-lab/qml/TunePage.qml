import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// TunePage -- hyperparameter tuning with model-specific sliders.

Item {
    id: root

    property var tuneResult: _parseTune()
    property string selectedModelType: modelTypeCombo.currentText || "xgb"

    function _parseTune() {
        try {
            return JSON.parse(regressorBridge.tuneResultJson || "{}")
        } catch (e) {
            return {}
        }
    }

    // Hyperparameter definitions per model type
    property var hpDefs: ({
        "xgb": [
            { key: "learning_rate", label: "Learning Rate", min: 0.01, max: 0.3, step: 0.01, defaultVal: 0.1 },
            { key: "max_depth", label: "Max Depth", min: 3, max: 12, step: 1, defaultVal: 6 },
            { key: "n_estimators", label: "N Estimators", min: 50, max: 500, step: 10, defaultVal: 100 }
        ],
        "rf": [
            { key: "n_estimators", label: "N Estimators", min: 50, max: 500, step: 10, defaultVal: 100 },
            { key: "max_depth", label: "Max Depth", min: 3, max: 30, step: 1, defaultVal: 10 },
            { key: "min_samples_split", label: "Min Samples Split", min: 2, max: 20, step: 1, defaultVal: 2 }
        ],
        "gbr": [
            { key: "learning_rate", label: "Learning Rate", min: 0.01, max: 0.3, step: 0.01, defaultVal: 0.1 },
            { key: "n_estimators", label: "N Estimators", min: 50, max: 500, step: 10, defaultVal: 100 },
            { key: "max_depth", label: "Max Depth", min: 3, max: 12, step: 1, defaultVal: 3 }
        ],
        "ridge": [
            { key: "alpha", label: "Alpha", min: 0.01, max: 100.0, step: 0.1, defaultVal: 1.0 }
        ],
        "lasso": [
            { key: "alpha", label: "Alpha", min: 0.001, max: 10.0, step: 0.01, defaultVal: 1.0 }
        ]
    })

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // -- Model Type + Strategy --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Model Type"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            EmbryComboBox {
                id: modelTypeCombo
                Layout.preferredWidth: 140
                model: ["xgb", "rf", "gbr", "ridge", "lasso"]

                Accessible.name: "Select model type for tuning"
            }

            Text {
                text: "Search Strategy"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            EmbryComboBox {
                id: strategyCombo
                Layout.preferredWidth: 140
                model: ["grid", "random", "bayesian"]

                Accessible.name: "Select search strategy"
            }

            Text {
                text: "Max Trials"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            SpinBox {
                id: maxTrialsSpin
                from: 5
                to: 500
                value: 50
                stepSize: 5

                Accessible.name: "Maximum number of trials"
                Accessible.role: Accessible.SpinBox

                background: Rectangle {
                    radius: EmbryStyle.layout.radiusSm
                    color: EmbryStyle.colors.bgInput
                    border.width: 1
                    border.color: maxTrialsSpin.activeFocus
                        ? EmbryStyle.colors.borderFocused
                        : EmbryStyle.colors.borderInput
                }

                contentItem: Text {
                    text: maxTrialsSpin.textFromValue(maxTrialsSpin.value, maxTrialsSpin.locale)
                    font.pixelSize: EmbryStyle.text.sm
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.textPrimary
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Item { Layout.fillWidth: true }
        }

        // -- Hyperparameter Sliders --
        Text {
            text: "Hyperparameters (" + selectedModelType.toUpperCase() + ")"
            font.pixelSize: EmbryStyle.text.sm
            font.weight: EmbryStyle.text.weightMedium
            color: EmbryStyle.colors.textMuted
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(120, sliderColumn.implicitHeight + EmbryStyle.layout.space4)
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ColumnLayout {
                id: sliderColumn
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                Repeater {
                    id: hpRepeater
                    model: hpDefs[selectedModelType] || []

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: EmbryStyle.layout.space2

                        property real hpValue: modelData.defaultVal || 0

                        Text {
                            Layout.preferredWidth: 140
                            text: modelData.label || ""
                            font.pixelSize: EmbryStyle.text.sm
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textSecondary
                            horizontalAlignment: Text.AlignRight

                            Accessible.name: (modelData.label || "") + " parameter"
                            Accessible.role: Accessible.StaticText
                        }

                        Slider {
                            id: hpSlider
                            Layout.fillWidth: true
                            from: modelData.min || 0
                            to: modelData.max || 1
                            stepSize: modelData.step || 0.01
                            value: modelData.defaultVal || 0
                            onValueChanged: parent.hpValue = value

                            Accessible.name: "Adjust " + (modelData.label || "")
                            Accessible.role: Accessible.Slider

                            background: Rectangle {
                                x: hpSlider.leftPadding
                                y: hpSlider.topPadding + hpSlider.availableHeight / 2 - height / 2
                                width: hpSlider.availableWidth
                                height: 4
                                radius: 2
                                color: EmbryStyle.colors.bgInput

                                Rectangle {
                                    width: hpSlider.visualPosition * parent.width
                                    height: parent.height
                                    radius: 2
                                    color: EmbryStyle.colors.accent
                                }
                            }

                            handle: Rectangle {
                                x: hpSlider.leftPadding + hpSlider.visualPosition * (hpSlider.availableWidth - width)
                                y: hpSlider.topPadding + hpSlider.availableHeight / 2 - height / 2
                                width: 14
                                height: 14
                                radius: 7
                                color: hpSlider.pressed
                                    ? EmbryStyle.colors.bgPressed
                                    : EmbryStyle.colors.bgInput
                                border.width: 2
                                border.color: EmbryStyle.colors.accent
                            }
                        }

                        Text {
                            Layout.preferredWidth: 60
                            text: Number(hpSlider.value).toFixed(modelData.step < 1 ? 2 : 0)
                            font.pixelSize: EmbryStyle.text.sm
                            font.weight: EmbryStyle.text.weightMedium
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.accent
                            horizontalAlignment: Text.AlignLeft
                        }
                    }
                }
            }
        }

        // -- Run Tune Button --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Item { Layout.fillWidth: true }

            Rectangle {
                width: tuneBtnText.implicitWidth + EmbryStyle.layout.space4 * 2
                height: 36
                radius: EmbryStyle.layout.radiusSm
                color: tuneBtnMa.containsMouse
                    ? EmbryStyle.colors.bgPressed
                    : EmbryStyle.colors.bgInput
                border.width: 1
                border.color: EmbryStyle.colors.accentGreen

                Accessible.name: "Run hyperparameter tuning"
                Accessible.role: Accessible.Button

                Text {
                    id: tuneBtnText
                    anchors.centerIn: parent
                    text: "Run Tune"
                    font.pixelSize: EmbryStyle.text.base
                    font.weight: EmbryStyle.text.weightSemibold
                    color: EmbryStyle.colors.accentGreen
                }

                MouseArea {
                    id: tuneBtnMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        var params = {}
                        var defs = hpDefs[selectedModelType] || []
                        for (var i = 0; i < hpRepeater.count; i++) {
                            var item = hpRepeater.itemAt(i)
                            if (item && defs[i]) {
                                params[defs[i].key] = item.hpValue
                            }
                        }
                        regressorBridge.runTune(
                            selectedModelType,
                            JSON.stringify(params),
                            strategyCombo.currentText,
                            maxTrialsSpin.value
                        )
                    }
                }
            }
        }

        // -- Best Params Display --
        Text {
            text: "Best Parameters"
            font.pixelSize: EmbryStyle.text.sm
            font.weight: EmbryStyle.text.weightMedium
            color: EmbryStyle.colors.textMuted
            visible: (tuneResult.best_params || null) !== null
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: tuneResult.best_score !== undefined
                ? EmbryStyle.colors.accentGreen
                : EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                // Score badge
                Rectangle {
                    visible: tuneResult.best_score !== undefined
                    Layout.alignment: Qt.AlignHCenter
                    width: scoreText.implicitWidth + EmbryStyle.layout.badgePadding * 2
                    height: EmbryStyle.layout.badgeHeight + 4
                    radius: EmbryStyle.layout.badgeRadius
                    color: EmbryStyle.colors.statusOkBg

                    Accessible.name: "Best score: " + _fmtScore()
                    Accessible.role: Accessible.StaticText

                    Text {
                        id: scoreText
                        anchors.centerIn: parent
                        text: "Best Score: " + _fmtScore()
                        font.pixelSize: EmbryStyle.text.base
                        font.weight: EmbryStyle.text.weightBold
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.accentGreen
                    }
                }

                // Params list
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: _paramsList()
                    spacing: 2

                    delegate: RowLayout {
                        width: parent ? parent.width : 0
                        spacing: EmbryStyle.layout.space2

                        Accessible.name: (modelData.key || "parameter") + ": " + String(modelData.value !== undefined ? modelData.value : "unknown")
                        Accessible.role: Accessible.ListItem

                        Text {
                            Layout.preferredWidth: 160
                            text: modelData.key || ""
                            font.pixelSize: EmbryStyle.text.sm
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textSecondary
                            horizontalAlignment: Text.AlignRight
                        }

                        Text {
                            text: String(modelData.value !== undefined ? modelData.value : "--")
                            font.pixelSize: EmbryStyle.text.sm
                            font.weight: EmbryStyle.text.weightSemibold
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.accent
                        }
                    }
                }

                // Empty state
                Text {
                    visible: _paramsList().length === 0
                    Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
                    text: "Run tuning to see best parameters"
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.textMuted
                }
            }
        }
    }

    function _fmtScore() {
        if (tuneResult.best_score === undefined) return "--"
        return Number(tuneResult.best_score).toFixed(4)
    }

    function _paramsList() {
        var bp = tuneResult.best_params || {}
        var list = []
        var keys = Object.keys(bp)
        for (var i = 0; i < keys.length; i++) {
            list.push({ key: keys[i], value: bp[keys[i]] })
        }
        return list
    }
}
