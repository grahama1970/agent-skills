import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// TemplatesPage -- browse and preview Stream Deck layout templates.

Item {
    id: root

    required property QtObject deckBridge
    property var templates: []
    property int selectedIndex: -1
    property var selectedTemplate: selectedIndex >= 0 && selectedIndex < templates.length ? templates[selectedIndex] : null

    Component.onCompleted: reloadTemplates()

    function reloadTemplates() {
        try {
            templates = JSON.parse(deckBridge.templatesJson || "[]")
        } catch(e) {
            templates = []
        }
    }

    Connections {
        target: deckBridge
        function onTemplatesJsonChanged() { reloadTemplates() }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space4

        // -- Template List --
        Rectangle {
            Layout.preferredWidth: 320
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
                    text: "Templates (" + templates.length + ")"
                    font.pixelSize: EmbryStyle.text.base
                    font.weight: Font.DemiBold
                    color: EmbryStyle.colors.textPrimary
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                ListView {
                    id: templateList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: templates
                    spacing: EmbryStyle.layout.space1

                    delegate: Rectangle {
                        width: templateList.width
                        height: tplCol.implicitHeight + EmbryStyle.layout.space3
                        radius: EmbryStyle.layout.radiusSm
                        color: selectedIndex === index ? EmbryStyle.colors.selectBg : tplMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"
                        border.width: selectedIndex === index ? 1 : 0
                        border.color: EmbryStyle.colors.selectBorder

                        ColumnLayout {
                            id: tplCol
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: EmbryStyle.layout.space2
                            spacing: 2

                            Text {
                                text: (modelData.name || modelData.template || "unnamed")
                                font.pixelSize: EmbryStyle.text.sm
                                font.weight: Font.DemiBold
                                color: EmbryStyle.colors.textPrimary
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            RowLayout {
                                spacing: EmbryStyle.layout.space2

                                // Context badge
                                Rectangle {
                                    width: ctxText.implicitWidth + EmbryStyle.layout.space2
                                    height: 18
                                    radius: 4
                                    color: EmbryStyle.colors.statusInfoBg
                                    Text { id: ctxText; anchors.centerIn: parent; text: (modelData.context || "unknown"); font.pixelSize: 8; font.weight: Font.Bold; color: EmbryStyle.colors.accent }
                                }

                                // Button count
                                Text {
                                    text: (modelData.button_count || 0) + " btns"
                                    font.pixelSize: EmbryStyle.text.xs
                                    color: EmbryStyle.colors.textMuted
                                }

                                Item { Layout.fillWidth: true }

                                // Eval score
                                Text {
                                    text: modelData.last_score !== undefined ? (modelData.last_score * 100).toFixed(0) + "%" : "--"
                                    font.pixelSize: EmbryStyle.text.xs
                                    font.weight: Font.Bold
                                    font.family: EmbryStyle.text.monoFamily
                                    color: {
                                        var s = modelData.last_score || 0
                                        if (s >= 0.85) return EmbryStyle.colors.statusOk
                                        if (s >= 0.5) return EmbryStyle.colors.statusWarning
                                        return EmbryStyle.colors.statusCritical
                                    }
                                }
                            }
                        }

                        MouseArea {
                            id: tplMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: selectedIndex = index
                        }

                        Accessible.name: (modelData.name || "template") + " button"
                        Accessible.role: Accessible.ListItem
                    }
                }
            }
        }

        // -- Template Detail --
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: EmbryStyle.layout.radiusMd
            color: EmbryStyle.colors.bgElevated
            border.width: 1
            border.color: EmbryStyle.colors.border

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: EmbryStyle.layout.space4
                spacing: EmbryStyle.layout.space3
                visible: selectedTemplate !== null

                // Header
                RowLayout {
                    spacing: EmbryStyle.layout.space3

                    Text {
                        text: selectedTemplate ? (selectedTemplate.name || selectedTemplate.template || "") : ""
                        font.pixelSize: EmbryStyle.text.lg
                        font.weight: Font.Bold
                        color: EmbryStyle.colors.textPrimary
                    }

                    // Status badge
                    Rectangle {
                        width: statusLbl.implicitWidth + EmbryStyle.layout.space3
                        height: EmbryStyle.layout.badgeHeight
                        radius: EmbryStyle.layout.badgeRadius
                        color: {
                            var st = selectedTemplate ? (selectedTemplate.status || "unverified") : "unverified"
                            if (st === "verified") return EmbryStyle.colors.statusOkBg
                            if (st === "failing") return EmbryStyle.colors.statusCriticalBg
                            return EmbryStyle.colors.badge
                        }

                        Text {
                            id: statusLbl
                            anchors.centerIn: parent
                            text: selectedTemplate ? (selectedTemplate.status || "unverified").toUpperCase() : ""
                            font.pixelSize: 9
                            font.weight: Font.Bold
                            color: {
                                var st = selectedTemplate ? (selectedTemplate.status || "unverified") : "unverified"
                                if (st === "verified") return EmbryStyle.colors.statusOk
                                if (st === "failing") return EmbryStyle.colors.statusCritical
                                return EmbryStyle.colors.textMuted
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: selectedTemplate ? (selectedTemplate.deck_model || "15-key") : ""
                        font.pixelSize: EmbryStyle.text.xs
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textMuted
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                // Button grid preview
                Text {
                    text: "Button Layout"
                    font.pixelSize: EmbryStyle.text.sm
                    font.weight: Font.DemiBold
                    color: EmbryStyle.colors.textSecondary
                }

                GridLayout {
                    id: buttonGrid
                    columns: selectedTemplate && (selectedTemplate.deck_model || "") === "32-key" ? 8 : 5
                    rowSpacing: EmbryStyle.layout.space2
                    columnSpacing: EmbryStyle.layout.space2
                    Layout.fillWidth: true

                    Repeater {
                        model: selectedTemplate ? (selectedTemplate.buttons || []) : []

                        Rectangle {
                            width: 72; height: 72
                            radius: 8
                            color: EmbryStyle.colors.bgInput
                            border.width: 1
                            border.color: {
                                var tier = modelData._alert_tier || ""
                                if (tier === "critical") return EmbryStyle.colors.accentRed
                                if (tier === "warning") return EmbryStyle.colors.accentAmber
                                return EmbryStyle.colors.border
                            }

                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: 2

                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: modelData.icon_text || modelData.icon || ""
                                    font.pixelSize: EmbryStyle.text.lg
                                    color: EmbryStyle.colors.accent
                                    horizontalAlignment: Text.AlignHCenter
                                }

                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    Layout.maximumWidth: 66
                                    text: modelData.text || modelData.label || ""
                                    font.pixelSize: 8
                                    font.weight: Font.Bold
                                    color: EmbryStyle.colors.textPrimary
                                    horizontalAlignment: Text.AlignHCenter
                                    elide: Text.ElideRight
                                }
                            }

                            Accessible.name: "Button " + index + ": " + (modelData.text || "empty")
                            Accessible.role: Accessible.Button
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                visible: selectedTemplate === null
                text: templates.length === 0
                    ? "No templates available. Use the Generator tab to create one."
                    : "Select a template to preview"
                font.pixelSize: EmbryStyle.text.base
                color: EmbryStyle.colors.textMuted
            }
        }
    }
}
