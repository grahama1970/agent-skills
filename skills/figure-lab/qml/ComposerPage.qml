import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// ComposerPage -- compose D3 visualizations: pick type, provide data, render.

Item {
    id: root

    property var recentModel: []

    Connections {
        target: figureBridge
        function onComposeStatusChanged() {
            try {
                var r = JSON.parse(figureBridge.composeStatus)
                if (r.status === "ok" && r.output_path) {
                    previewPath = r.output_path
                    refreshRecent()
                }
            } catch (e) {}
        }
    }

    property string previewPath: ""

    function refreshRecent() {
        try {
            var gallery = JSON.parse(figureBridge.galleryJson)
            recentModel = (gallery || []).slice(0, 10)
        } catch (e) {
            recentModel = []
        }
    }

    Component.onCompleted: {
        figureBridge.loadGallery("", 0.0, false)
        refreshRecent()
    }

    readonly property var vizTypes: ["bar", "line", "scatter", "heatmap", "pie", "treemap", "sankey", "radar"]

    RowLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Left: Controls ---------------------------------------------------
        ColumnLayout {
            Layout.preferredWidth: 340
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space3

            // Viz type selector
            Text {
                text: "Viz Type"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: Font.Medium
                color: EmbryStyle.colors.textSecondary
            }

            EmbryComboBox {
                id: vizTypeCombo
                Layout.fillWidth: true
                model: vizTypes
                currentIndex: 0

                Accessible.name: "Visualization type"
            }

            // Data input
            Text {
                text: "Data Source"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: Font.Medium
                color: EmbryStyle.colors.textSecondary
            }

            EmbryTextField {
                id: dataPathField
                Layout.fillWidth: true
                placeholderText: "JSON file path (or leave blank for inline)"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Data file path"
            }

            Text {
                text: "Inline JSON Data"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: Font.Medium
                color: EmbryStyle.colors.textSecondary
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: 120

                TextArea {
                    id: inlineDataArea
                    placeholderText: '[{"label": "A", "value": 10}, ...]'
                    font.pixelSize: EmbryStyle.text.sm
                    font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.textPrimary
                    wrapMode: TextArea.Wrap
                    background: Rectangle {
                        color: EmbryStyle.colors.bgInput
                        border.width: 1
                        border.color: inlineDataArea.activeFocus ? EmbryStyle.colors.borderFocused : EmbryStyle.colors.borderInput
                        radius: EmbryStyle.layout.radiusSm
                    }

                    Accessible.name: "Inline JSON data"
                    Accessible.role: Accessible.EditableText
                }
            }

            // Title and description
            EmbryTextField {
                id: titleField
                Layout.fillWidth: true
                placeholderText: "Title"

                Accessible.name: "Composition title"
            }

            EmbryTextField {
                id: descField
                Layout.fillWidth: true
                placeholderText: "Description"

                Accessible.name: "Composition description"
            }

            EmbryTextField {
                id: outputPathField
                Layout.fillWidth: true
                placeholderText: "Output path (optional)"
                font.family: EmbryStyle.text.monoFamily

                Accessible.name: "Output path"
            }

            // Buttons
            RowLayout {
                Layout.fillWidth: true
                spacing: EmbryStyle.layout.space2

                EmbryButton {
                    id: composeBtn
                    text: "Compose"
                    variant: "primary"
                    Layout.fillWidth: true

                    Accessible.name: "Compose visualization"
                    Accessible.role: Accessible.Button

                    onClicked: {
                        var dataArg = dataPathField.text || inlineDataArea.text
                        figureBridge.compose(
                            vizTypeCombo.currentText,
                            dataArg,
                            titleField.text,
                            descField.text,
                            outputPathField.text
                        )
                    }
                }

                EmbryButton {
                    id: dryRunBtn
                    text: "Dry Run"

                    Accessible.name: "Dry run composition"
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
                        font.weight: Font.Medium
                        color: EmbryStyle.colors.textSecondary
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: {
                        // Dry run just validates without writing output
                        figureBridge.compose(
                            vizTypeCombo.currentText,
                            dataPathField.text || inlineDataArea.text,
                            titleField.text,
                            descField.text,
                            ""
                        )
                    }
                }
            }

            // Recent compositions list
            Text {
                text: "Recent (last 10)"
                font.pixelSize: EmbryStyle.text.sm
                font.weight: Font.Medium
                color: EmbryStyle.colors.textMuted
                topPadding: EmbryStyle.layout.space2
            }

            ListView {
                id: recentList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: recentModel
                spacing: 2

                delegate: Rectangle {
                    width: recentList.width
                    height: 28
                    radius: EmbryStyle.layout.radiusSm
                    color: recentMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"

                    Accessible.name: (modelData.viz_type || "unknown") + ": " + (modelData.name || "composition") + " score " + (modelData.overall_score || 0).toFixed(2)
                    Accessible.role: Accessible.ListItem

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: EmbryStyle.layout.space2
                        anchors.rightMargin: EmbryStyle.layout.space2
                        spacing: EmbryStyle.layout.space2

                        // Viz type badge
                        Rectangle {
                            width: typeBadge.implicitWidth + 8
                            height: 18
                            radius: 4
                            color: EmbryStyle.colors.statusOkBg

                            Text {
                                id: typeBadge
                                anchors.centerIn: parent
                                text: (modelData.viz_type || "?")
                                font.pixelSize: 8
                                font.weight: Font.Bold
                                color: EmbryStyle.colors.accentGreen
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.name || ""
                            font.pixelSize: EmbryStyle.text.sm
                            color: EmbryStyle.colors.textPrimary
                            elide: Text.ElideRight
                        }

                        Text {
                            text: (modelData.overall_score || 0).toFixed(2)
                            font.pixelSize: EmbryStyle.text.xs
                            font.family: EmbryStyle.text.monoFamily
                            color: (modelData.overall_score || 0) >= 0.85
                                ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusWarning
                        }
                    }

                    MouseArea {
                        id: recentMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: previewPath = modelData.output_path || ""
                        Accessible.name: "Preview " + (modelData.viz_type || "figure")
                        Accessible.role: Accessible.Button
                    }
                }
            }
        }

        // -- Right: Preview ---------------------------------------------------
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
                    text: "Preview"
                    font.pixelSize: EmbryStyle.text.base
                    font.weight: Font.Medium
                    color: EmbryStyle.colors.textSecondary
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    // Show image if PNG, otherwise show path text
                    Image {
                        id: previewImage
                        anchors.fill: parent
                        visible: previewPath.endsWith(".png") || previewPath.endsWith(".svg")
                        source: previewPath ? "file://" + previewPath : ""
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                    }

                    ColumnLayout {
                        anchors.centerIn: parent
                        visible: !previewImage.visible
                        spacing: EmbryStyle.layout.space2

                        Text {
                            text: previewPath || "No composition selected"
                            font.pixelSize: EmbryStyle.text.sm
                            font.family: EmbryStyle.text.monoFamily
                            color: previewPath ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textMuted
                            wrapMode: Text.WrapAnywhere
                            Layout.maximumWidth: 400
                        }

                        EmbryButton {
                            id: openBrowserBtn
                            visible: previewPath.endsWith(".html")
                            text: "Open in Browser"

                            Accessible.name: "Open HTML in browser"
                            Accessible.role: Accessible.Button

                            background: Rectangle {
                                color: openBrowserBtn.hovered ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgInput
                                border.width: 1
                                border.color: EmbryStyle.colors.accent
                                radius: EmbryStyle.layout.radiusSm
                            }

                            contentItem: Text {
                                text: openBrowserBtn.text
                                font.pixelSize: EmbryStyle.text.sm
                                font.weight: Font.Medium
                                color: EmbryStyle.colors.accent
                                horizontalAlignment: Text.AlignHCenter
                            }

                            onClicked: Qt.openUrlExternally("file://" + previewPath)
                        }
                    }
                }
            }
        }
    }
}
