import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// GalleryPage -- browse, filter, and manage all compositions in the gallery.

Item {
    id: root

    property var galleryItems: []
    property int selectedIndex: -1
    property var selectedItem: selectedIndex >= 0 && selectedIndex < galleryItems.length
        ? galleryItems[selectedIndex] : null

    Connections {
        target: figureBridge
        function onGalleryJsonChanged() {
            try {
                galleryItems = JSON.parse(figureBridge.galleryJson) || []
            } catch (e) {
                galleryItems = []
            }
            if (selectedIndex >= galleryItems.length) selectedIndex = -1
        }
    }

    Component.onCompleted: figureBridge.loadGallery("", 0.0, false)

    readonly property var vizTypes: ["", "bar", "line", "scatter", "heatmap", "pie", "treemap", "sankey", "radar"]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // -- Filter Row -------------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Type:"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }

            EmbryComboBox {
                id: filterTypeCombo
                model: vizTypes
                currentIndex: 0
                implicitWidth: 120

                Accessible.name: "Filter by viz type"

                onCurrentTextChanged: applyFilter()
            }

            Text {
                text: "Min Score:"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textSecondary
            }

            Slider {
                id: scoreSlider
                from: 0.0
                to: 1.0
                value: 0.0
                stepSize: 0.05
                implicitWidth: 140

                Accessible.name: "Minimum score threshold"
                Accessible.role: Accessible.Slider

                onValueChanged: applyFilter()
            }

            Text {
                text: scoreSlider.value.toFixed(2)
                font.pixelSize: EmbryStyle.text.xs
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textPrimary
            }

            CheckBox {
                id: promotedOnlyCheck
                text: "Promoted Only"

                Accessible.name: "Show promoted only"
                Accessible.role: Accessible.CheckBox

                contentItem: Text {
                    leftPadding: promotedOnlyCheck.indicator.width + 4
                    text: promotedOnlyCheck.text
                    font.pixelSize: EmbryStyle.text.sm
                    color: EmbryStyle.colors.textSecondary
                    verticalAlignment: Text.AlignVCenter
                }

                onCheckedChanged: applyFilter()
            }

            Item { Layout.fillWidth: true }

            Text {
                text: galleryItems.length + " items"
                font.pixelSize: EmbryStyle.text.xs
                font.family: EmbryStyle.text.monoFamily
                color: EmbryStyle.colors.textMuted
            }
        }

        // -- Main Content: Grid + Detail Panel --------------------------------
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space3

            // Grid view
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true

                GridView {
                    id: galleryGrid
                    clip: true
                    cellWidth: Math.floor((root.width - 340 - EmbryStyle.layout.space4 * 3) / 3)
                    cellHeight: 180
                    model: galleryItems.length

                    delegate: Rectangle {
                        id: card

                        property var item: galleryItems[index] || {}

                        width: galleryGrid.cellWidth - EmbryStyle.layout.space2
                        height: galleryGrid.cellHeight - EmbryStyle.layout.space2
                        radius: EmbryStyle.layout.radiusMd
                        color: selectedIndex === index
                            ? EmbryStyle.colors.selectBg : cardMa.containsMouse
                                ? EmbryStyle.colors.bgHover : EmbryStyle.colors.bgElevated
                        border.width: selectedIndex === index ? 1 : 0
                        border.color: EmbryStyle.colors.selectBorder

                        Accessible.name: (item.name || "Composition") + " card"
                        Accessible.role: Accessible.ListItem

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: EmbryStyle.layout.space2
                            spacing: EmbryStyle.layout.space1

                            // Thumbnail placeholder
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 80
                                radius: EmbryStyle.layout.radiusSm
                                color: EmbryStyle.colors.bgInput

                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 2
                                    source: (item.output_path || "").endsWith(".png")
                                        ? "file://" + (item.output_path || "") : ""
                                    visible: source !== ""
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                }

                                Text {
                                    anchors.centerIn: parent
                                    visible: !(item.output_path || "").endsWith(".png")
                                    text: (item.viz_type || "?").toUpperCase()
                                    font.pixelSize: EmbryStyle.text.lg
                                    font.weight: Font.Bold
                                    color: EmbryStyle.colors.textGhost
                                }
                            }

                            // Viz type badge + promoted badge row
                            RowLayout {
                                spacing: EmbryStyle.layout.space1

                                Rectangle {
                                    width: vizBadge.implicitWidth + 8
                                    height: 18
                                    radius: 4
                                    color: EmbryStyle.colors.statusOkBg

                                    Text {
                                        id: vizBadge
                                        anchors.centerIn: parent
                                        text: item.viz_type || "?"
                                        font.pixelSize: 8
                                        font.weight: Font.Bold
                                        color: EmbryStyle.colors.accentGreen
                                    }
                                }

                                Rectangle {
                                    visible: item.promoted || false
                                    width: promBadge.implicitWidth + 8
                                    height: 18
                                    radius: 4
                                    color: EmbryStyle.colors.statusInfoBg

                                    Text {
                                        id: promBadge
                                        anchors.centerIn: parent
                                        text: "promoted"
                                        font.pixelSize: 8
                                        font.weight: Font.Bold
                                        color: EmbryStyle.colors.accent
                                    }
                                }

                                Item { Layout.fillWidth: true }
                            }

                            // Name
                            Text {
                                Layout.fillWidth: true
                                text: item.name || ""
                                font.pixelSize: EmbryStyle.text.sm
                                font.weight: Font.Medium
                                color: EmbryStyle.colors.textPrimary
                                elide: Text.ElideRight
                                maximumLineCount: 1
                            }

                            // Score gauge
                            RowLayout {
                                spacing: EmbryStyle.layout.space1

                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 6
                                    radius: 3
                                    color: EmbryStyle.colors.bgInput

                                    Rectangle {
                                        width: parent.width * Math.min(1.0, item.overall_score || 0)
                                        height: parent.height
                                        radius: 3
                                        color: (item.overall_score || 0) >= 0.85
                                            ? EmbryStyle.colors.statusOk
                                            : (item.overall_score || 0) >= 0.6
                                                ? EmbryStyle.colors.statusWarning
                                                : EmbryStyle.colors.statusCritical
                                    }
                                }

                                Text {
                                    text: (item.overall_score || 0).toFixed(2)
                                    font.pixelSize: EmbryStyle.text.xs
                                    font.family: EmbryStyle.text.monoFamily
                                    color: EmbryStyle.colors.textSecondary
                                }
                            }
                        }

                        MouseArea {
                            id: cardMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: selectedIndex = index
                            Accessible.name: "View " + (modelData.viz_type || "figure") + " details"
                            Accessible.role: Accessible.Button
                        }
                    }
                }
            }

            // -- Detail Panel -------------------------------------------------
            Rectangle {
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1
                border.color: EmbryStyle.colors.border
                visible: selectedItem !== null

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space3
                    spacing: EmbryStyle.layout.space2

                    Text {
                        text: (selectedItem && selectedItem.name) || ""
                        font.pixelSize: EmbryStyle.text.base
                        font.weight: Font.Bold
                        color: EmbryStyle.colors.textPrimary
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }

                    Text {
                        text: (selectedItem && selectedItem.description) || "No description"
                        font.pixelSize: EmbryStyle.text.sm
                        color: EmbryStyle.colors.textMuted
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                    // Scores breakdown
                    Repeater {
                        model: selectedItem ? Object.keys(selectedItem.scores || {}) : []

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: EmbryStyle.layout.space2

                            Text {
                                Layout.fillWidth: true
                                text: modelData || ""
                                font.pixelSize: EmbryStyle.text.sm
                                color: EmbryStyle.colors.textSecondary
                            }

                            Text {
                                text: selectedItem ? ((selectedItem.scores || {})[modelData] || 0).toFixed(2) : ""
                                font.pixelSize: EmbryStyle.text.sm
                                font.family: EmbryStyle.text.monoFamily
                                color: EmbryStyle.colors.textPrimary
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                    Text {
                        text: "Overall: " + ((selectedItem && selectedItem.overall_score) || 0).toFixed(3)
                        font.pixelSize: EmbryStyle.text.base
                        font.weight: Font.Bold
                        color: ((selectedItem && selectedItem.overall_score) || 0) >= 0.85
                            ? EmbryStyle.colors.statusOk : EmbryStyle.colors.statusWarning
                    }

                    Text {
                        text: "Path: " + ((selectedItem && selectedItem.output_path) || "")
                        font.pixelSize: EmbryStyle.text.xs
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textMuted
                        wrapMode: Text.WrapAnywhere
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "Created: " + ((selectedItem && selectedItem.created_at) || "")
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textMuted
                    }

                    Item { Layout.fillHeight: true }

                    // Action buttons
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: EmbryStyle.layout.space2

                        EmbryButton {
                            id: promoteSelBtn
                            text: "Promote"
                            Layout.fillWidth: true
                            enabled: selectedItem && !(selectedItem.promoted)

                            Accessible.name: "Promote selected composition"
                            Accessible.role: Accessible.Button

                            background: Rectangle {
                                color: promoteSelBtn.enabled
                                    ? (promoteSelBtn.hovered ? Qt.darker(EmbryStyle.colors.accentGreen, 1.3) : EmbryStyle.colors.accentGreen)
                                    : EmbryStyle.colors.bgInput
                                radius: EmbryStyle.layout.radiusSm
                            }

                            contentItem: Text {
                                text: promoteSelBtn.text
                                font.pixelSize: EmbryStyle.text.sm
                                font.weight: Font.Bold
                                color: promoteSelBtn.enabled ? EmbryStyle.colors.bg : EmbryStyle.colors.textMuted
                                horizontalAlignment: Text.AlignHCenter
                            }

                            onClicked: {
                                if (selectedItem) figureBridge.promote(selectedItem.name)
                            }
                        }

                        EmbryButton {
                            id: deleteSelBtn
                            text: "Delete"
                            Layout.fillWidth: true

                            Accessible.name: "Delete selected composition"
                            Accessible.role: Accessible.Button

                            background: Rectangle {
                                color: deleteSelBtn.hovered ? EmbryStyle.colors.statusCriticalBg : EmbryStyle.colors.bgInput
                                border.width: 1
                                border.color: EmbryStyle.colors.statusCritical
                                radius: EmbryStyle.layout.radiusSm
                            }

                            contentItem: Text {
                                text: deleteSelBtn.text
                                font.pixelSize: EmbryStyle.text.sm
                                font.weight: Font.Medium
                                color: EmbryStyle.colors.statusCritical
                                horizontalAlignment: Text.AlignHCenter
                            }

                            onClicked: {
                                if (selectedItem) figureBridge.demote(selectedItem.name)
                            }
                        }
                    }
                }
            }
        }
    }

    function applyFilter() {
        figureBridge.loadGallery(
            filterTypeCombo.currentText,
            scoreSlider.value,
            promotedOnlyCheck.checked
        )
    }
}
