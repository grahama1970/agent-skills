import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// DataPage -- JSONL data loading, column selection, preview table.

Item {
    id: root

    property var dataInfo: _parseData()

    function _parseData() {
        try {
            return JSON.parse(regressorBridge.dataInfoJson || "{}")
        } catch (e) {
            return {}
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // -- File Path Input --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Text {
                text: "JSONL File"
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
                border.color: pathInput.activeFocus
                    ? EmbryStyle.colors.borderFocused
                    : EmbryStyle.colors.borderInput

                TextInput {
                    id: pathInput
                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space2
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: EmbryStyle.text.sm
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.textPrimary
                    clip: true
                    selectByMouse: true
                    text: dataInfo.path || ""

                    Accessible.name: "JSONL file path"
                    Accessible.role: Accessible.EditableText
                }
            }
        }

        // -- Target Column Selector --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Text {
                text: "Target Column"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: EmbryStyle.text.weightMedium
                color: EmbryStyle.colors.textMuted
            }

            EmbryComboBox {
                id: targetCombo
                Layout.preferredWidth: 200
                model: dataInfo.columns || []
                currentIndex: _targetIndex()

                Accessible.name: "Target column selector"

                function _targetIndex() {
                    var cols = dataInfo.columns || []
                    var target = dataInfo.target || ""
                    for (var i = 0; i < cols.length; i++) {
                        if (cols[i] === target) return i
                    }
                    return -1
                }
            }

            Item { Layout.fillWidth: true }

            // Load Data button
            Rectangle {
                width: loadBtnText.implicitWidth + EmbryStyle.layout.space4 * 2
                height: 32
                radius: EmbryStyle.layout.radiusSm
                color: loadBtnMa.containsMouse
                    ? EmbryStyle.colors.bgPressed
                    : EmbryStyle.colors.bgInput
                border.width: 1
                border.color: EmbryStyle.colors.accentGreen

                Accessible.name: "Load data"
                Accessible.role: Accessible.Button

                Text {
                    id: loadBtnText
                    anchors.centerIn: parent
                    text: "Load Data"
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: EmbryStyle.text.weightSemibold
                    color: EmbryStyle.colors.accentGreen
                }

                MouseArea {
                    id: loadBtnMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        var target = targetCombo.currentText || ""
                        regressorBridge.loadData(pathInput.text, target)
                    }
                    Accessible.name: "Load data"
                    Accessible.role: Accessible.Button
                }
            }
        }

        // -- Summary Cards --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Repeater {
                model: [
                    { label: "Samples", value: dataInfo.sample_count || 0, color: EmbryStyle.colors.accent },
                    { label: "Features", value: dataInfo.feature_count || 0, color: EmbryStyle.colors.accentGreen },
                    { label: "Target Range", value: _targetRange(), color: EmbryStyle.colors.accentYellow }
                ]

                Rectangle {
                    Layout.fillWidth: true
                    height: 60
                    radius: EmbryStyle.layout.radiusMd
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    Accessible.name: (modelData.label || "") + ": " + (modelData.value || "")
                    Accessible.role: Accessible.StaticText

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: String(modelData.value || "0")
                            font.pixelSize: EmbryStyle.text.lg
                            font.weight: EmbryStyle.text.weightBold
                            font.family: EmbryStyle.text.monoFamily
                            color: modelData.color || EmbryStyle.colors.textPrimary
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: modelData.label || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.weight: EmbryStyle.text.weightMedium
                            color: EmbryStyle.colors.textMuted
                        }
                    }
                }
            }
        }

        // -- Feature Columns List --
        Text {
            text: "Feature Columns"
            font.pixelSize: EmbryStyle.text.sm
            font.weight: EmbryStyle.text.weightMedium
            color: EmbryStyle.colors.textMuted
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 80
            radius: EmbryStyle.layout.radiusSm
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ListView {
                id: featureList
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space2
                clip: true
                orientation: ListView.Horizontal
                spacing: EmbryStyle.layout.space2
                model: dataInfo.features || []

                delegate: Rectangle {
                    width: featureCheckRow.implicitWidth + EmbryStyle.layout.space3
                    height: 28
                    radius: EmbryStyle.layout.radiusSm
                    color: EmbryStyle.colors.bgInput

                    Row {
                        id: featureCheckRow
                        anchors.centerIn: parent
                        spacing: EmbryStyle.layout.space1

                        CheckBox {
                            id: featureCheck
                            checked: true
                            width: 18
                            height: 18

                            Accessible.name: "Toggle feature " + (modelData || "")
                            Accessible.role: Accessible.CheckBox
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData || ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textPrimary
                        }
                    }
                }
            }
        }

        // -- Data Preview Table --
        Text {
            text: "Data Preview (first 10 rows)"
            font.pixelSize: EmbryStyle.text.sm
            font.weight: EmbryStyle.text.weightMedium
            color: EmbryStyle.colors.textMuted
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusSm
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ListView {
                id: previewTable
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space2
                clip: true
                model: dataInfo.preview || []
                spacing: 1

                header: Rectangle {
                    width: previewTable.width
                    height: 24
                    color: EmbryStyle.colors.bgInput

                    Row {
                        anchors.fill: parent
                        spacing: 1

                        Repeater {
                            model: dataInfo.columns || []
                            Text {
                                width: previewTable.width / Math.max((dataInfo.columns || []).length, 1)
                                height: 24
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                text: modelData || ""
                                font.pixelSize: EmbryStyle.text.xs
                                font.weight: EmbryStyle.text.weightSemibold
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.accent
                                elide: Text.ElideRight
                            }
                        }
                    }
                }

                delegate: Row {
                    width: previewTable.width
                    spacing: 1

                    Accessible.name: "Data row " + (index + 1)
                    Accessible.role: Accessible.ListItem

                    Repeater {
                        model: dataInfo.columns || []
                        Text {
                            width: previewTable.width / Math.max((dataInfo.columns || []).length, 1)
                            height: 20
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            text: {
                                var row = (previewTable.model || [])[index] || {}
                                return String(row[modelData] !== undefined ? row[modelData] : "")
                            }
                            font.pixelSize: EmbryStyle.text.xs
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textSecondary
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }

    function _targetRange() {
        var lo = dataInfo.target_min
        var hi = dataInfo.target_max
        if (lo === undefined || hi === undefined) return "--"
        return Number(lo).toFixed(2) + " - " + Number(hi).toFixed(2)
    }
}
