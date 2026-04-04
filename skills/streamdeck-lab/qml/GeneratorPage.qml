import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// GeneratorPage -- dynamic Stream Deck page generation with event mutations.

Item {
    id: root

    required property QtObject deckBridge
    property var generatedPage: null
    property var selectedEvents: ({})
    property var eventCatalog: []
    property bool showCritical: true
    property bool showWarning: true
    property bool showAdvisory: true

    Component.onCompleted: reloadEvents()

    function reloadEvents() {
        try {
            eventCatalog = JSON.parse(deckBridge.eventCatalogJson || "[]")
        } catch(e) {
            eventCatalog = []
        }
    }

    function parseGenerated() {
        try {
            generatedPage = JSON.parse(deckBridge.generatedPageJson || "null")
        } catch(e) {
            generatedPage = null
        }
    }

    function filteredEvents() {
        var ctx = contextCombo.currentText
        var result = []
        for (var i = 0; i < eventCatalog.length; i++) {
            var ev = eventCatalog[i]
            if (ev.context !== ctx) continue
            var tier = ev.alert_tier || ""
            if (tier === "critical" && !showCritical) continue
            if (tier === "warning" && !showWarning) continue
            if (tier === "advisory" && !showAdvisory) continue
            result.push(ev)
        }
        return result
    }

    function selectedEventNames() {
        var names = []
        for (var k in selectedEvents) {
            if (selectedEvents[k]) names.push(k)
        }
        return names
    }

    Connections {
        target: deckBridge
        function onGeneratedPageJsonChanged() { parseGenerated() }
        function onEventCatalogJsonChanged() { reloadEvents() }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // -- Header --
        RowLayout {
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Page Generator"
                font.pixelSize: EmbryStyle.text.lg
                font.weight: Font.Bold
                color: EmbryStyle.colors.textPrimary
            }

            Item { Layout.fillWidth: true }

            Text { text: "Context:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }

            EmbryComboBox {
                id: contextCombo
                model: ["sentinel_hud", "compliance_dashboard", "f36_plant_floor"]
                implicitWidth: 200
                onCurrentTextChanged: { selectedEvents = {} }
                Accessible.name: "Context picker"
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

        // -- Controls + Preview --
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space4

            // Left: Event selection + filters
            ColumnLayout {
                Layout.preferredWidth: 340
                Layout.fillHeight: true
                spacing: EmbryStyle.layout.space3

                // Alert tier filter
                Rectangle {
                    Layout.fillWidth: true
                    height: 36
                    radius: EmbryStyle.layout.radiusSm
                    color: EmbryStyle.colors.bgElevated
                    border.width: 1
                    border.color: EmbryStyle.colors.border

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: EmbryStyle.layout.space2
                        spacing: EmbryStyle.layout.space3

                        Text { text: "Tiers:"; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted }

                        CheckBox {
                            id: critCheck; checked: showCritical; text: "Critical"
                            onCheckedChanged: showCritical = checked
                            Accessible.name: "Filter critical events"; Accessible.role: Accessible.CheckBox
                        }
                        CheckBox {
                            id: warnCheck; checked: showWarning; text: "Warning"
                            onCheckedChanged: showWarning = checked
                            Accessible.name: "Filter warning events"; Accessible.role: Accessible.CheckBox
                        }
                        CheckBox {
                            id: advCheck; checked: showAdvisory; text: "Advisory"
                            onCheckedChanged: showAdvisory = checked
                            Accessible.name: "Filter advisory events"; Accessible.role: Accessible.CheckBox
                        }
                    }
                }

                // Event multiselect
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
                            text: "Events (" + selectedEventNames().length + " selected)"
                            font.pixelSize: EmbryStyle.text.sm
                            font.weight: Font.DemiBold
                            color: EmbryStyle.colors.textPrimary
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: EmbryStyle.layout.space2

                            Repeater {
                                model: filteredEvents()

                                Rectangle {
                                    property bool isSelected: selectedEvents[modelData.name] || false
                                    width: evBadgeText.implicitWidth + EmbryStyle.layout.space4
                                    height: 28
                                    radius: EmbryStyle.layout.badgeRadius
                                    color: isSelected ? EmbryStyle.colors.statusInfoBg : evBadgeMa.containsMouse ? EmbryStyle.colors.badgeHover : EmbryStyle.colors.badge
                                    border.width: isSelected ? 1 : 0
                                    border.color: EmbryStyle.colors.selectBorder

                                    Text {
                                        id: evBadgeText
                                        anchors.centerIn: parent
                                        text: (modelData.name || "")
                                        font.pixelSize: EmbryStyle.text.xs
                                        font.weight: Font.Bold
                                        color: {
                                            var tier = modelData.alert_tier || ""
                                            if (tier === "critical") return EmbryStyle.colors.statusCritical
                                            if (tier === "warning") return EmbryStyle.colors.statusWarning
                                            return EmbryStyle.colors.statusInfo
                                        }
                                    }

                                    MouseArea {
                                        id: evBadgeMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            var ev = Object.assign({}, selectedEvents)
                                            ev[modelData.name] = !ev[modelData.name]
                                            selectedEvents = ev
                                        }
                                    }

                                    Accessible.name: modelData.name + " event toggle"
                                    Accessible.role: Accessible.CheckBox
                                }
                            }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }

                // Action buttons
                RowLayout {
                    spacing: EmbryStyle.layout.space2

                    EmbryButton {
                        text: "Generate Page"
                        variant: "primary"
                        onClicked: deckBridge.generate(contextCombo.currentText, JSON.stringify(selectedEventNames()))
                        Accessible.name: "Generate page layout"; Accessible.role: Accessible.Button
                    }

                    EmbryButton {
                        text: "Mutate"
                        enabled: selectedEventNames().length === 1
                        onClicked: deckBridge.mutate(contextCombo.currentText, selectedEventNames()[0])
                        Accessible.name: "Apply single event mutation"; Accessible.role: Accessible.Button
                    }

                    Item { Layout.fillWidth: true }

                    EmbryButton {
                        text: "Push to Hardware"
                        enabled: generatedPage !== null
                        onClicked: deckBridge.pushToHardware()
                        Accessible.name: "Push generated page to Stream Deck hardware"; Accessible.role: Accessible.Button
                    }
                }
            }

            // Right: Preview
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

                    RowLayout {
                        Text {
                            text: "Preview"
                            font.pixelSize: EmbryStyle.text.base
                            font.weight: Font.DemiBold
                            color: EmbryStyle.colors.textSecondary
                        }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            visible: generatedPage !== null
                            width: mutCountText.implicitWidth + EmbryStyle.layout.space2
                            height: 18; radius: 4
                            color: EmbryStyle.colors.statusWarningBg
                            Text { id: mutCountText; anchors.centerIn: parent; text: generatedPage ? (generatedPage.mutations || []).length + " mutations" : ""; font.pixelSize: 8; font.weight: Font.Bold; color: EmbryStyle.colors.accentAmber }
                        }
                    }

                    // Button grid
                    GridLayout {
                        id: previewGrid
                        columns: 5
                        rowSpacing: EmbryStyle.layout.space2
                        columnSpacing: EmbryStyle.layout.space2
                        Layout.alignment: Qt.AlignHCenter
                        visible: generatedPage !== null

                        Repeater {
                            model: generatedPage ? (generatedPage.buttons || []) : []

                            Rectangle {
                                width: 72; height: 72
                                radius: 8
                                color: EmbryStyle.colors.bgInput
                                border.width: 1
                                border.color: {
                                    var tier = modelData._alert_tier || ""
                                    if (tier === "critical") return EmbryStyle.colors.statusCritical
                                    if (tier === "warning") return EmbryStyle.colors.statusWarning
                                    return EmbryStyle.colors.border
                                }

                                // Flash indicator for alerts
                                Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: "transparent"
                                    border.width: modelData._flash ? 2 : 0
                                    border.color: EmbryStyle.colors.statusCritical
                                    visible: modelData._flash || false

                                    SequentialAnimation on opacity {
                                        running: modelData._flash || false
                                        loops: Animation.Infinite
                                        NumberAnimation { to: 0.3; duration: 400 }
                                        NumberAnimation { to: 1.0; duration: 400 }
                                    }
                                }

                                ColumnLayout {
                                    anchors.centerIn: parent
                                    spacing: 2

                                    Text {
                                        Layout.alignment: Qt.AlignHCenter
                                        text: modelData.icon_text || modelData.icon || ""
                                        font.pixelSize: EmbryStyle.text.lg
                                        color: {
                                            var tier = modelData._alert_tier || ""
                                            if (tier === "critical") return EmbryStyle.colors.statusCritical
                                            if (tier === "warning") return EmbryStyle.colors.statusWarning
                                            return EmbryStyle.colors.accent
                                        }
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

                                Accessible.name: "Generated button " + index + ": " + (modelData.text || "empty")
                                Accessible.role: Accessible.Button
                            }
                        }
                    }

                    // Empty state
                    Text {
                        visible: generatedPage === null
                        text: "Select events and click Generate"
                        font.pixelSize: EmbryStyle.text.base
                        color: EmbryStyle.colors.textMuted
                        Layout.alignment: Qt.AlignHCenter
                    }

                    Item { Layout.fillHeight: true }
                }
            }
        }
    }
}
