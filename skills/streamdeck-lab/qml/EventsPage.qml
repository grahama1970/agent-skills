import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// EventsPage -- browse and inspect the event catalog for dynamic page mutations.

Item {
    id: root

    required property QtObject deckBridge
    property var events: []
    property int selectedIndex: -1
    property var selectedEvent: selectedIndex >= 0 && selectedIndex < events.length ? events[selectedIndex] : null

    Component.onCompleted: reloadEvents()

    function reloadEvents() {
        try {
            events = JSON.parse(deckBridge.eventCatalogJson || "[]")
        } catch(e) {
            events = []
        }
    }

    function filteredEvents() {
        var ctx = contextFilterCombo.currentText
        var tier = tierFilterCombo.currentText
        var result = []
        for (var i = 0; i < events.length; i++) {
            var ev = events[i]
            if (ctx !== "all" && (ev.context || "") !== ctx) continue
            if (tier !== "all" && (ev.alert_tier || "") !== tier) continue
            result.push(ev)
        }
        return result
    }

    function countByContext(ctx) {
        var c = 0
        for (var i = 0; i < events.length; i++) {
            if (events[i].context === ctx) c++
        }
        return c
    }

    function countByTier(tier) {
        var c = 0
        for (var i = 0; i < events.length; i++) {
            if ((events[i].alert_tier || "") === tier) c++
        }
        return c
    }

    Connections {
        target: deckBridge
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
                text: "Event Catalog"
                font.pixelSize: EmbryStyle.text.lg
                font.weight: Font.Bold
                color: EmbryStyle.colors.textPrimary
            }

            Rectangle {
                width: evTotalText.implicitWidth + EmbryStyle.layout.space3
                height: EmbryStyle.layout.badgeHeight
                radius: EmbryStyle.layout.badgeRadius
                color: EmbryStyle.colors.statusInfoBg
                Text { id: evTotalText; anchors.centerIn: parent; text: events.length + " events"; font.pixelSize: 9; font.weight: Font.Bold; color: EmbryStyle.colors.accent }
            }

            Item { Layout.fillWidth: true }

            // Filters
            Text { text: "Context:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }
            EmbryComboBox {
                id: contextFilterCombo
                model: ["all", "sentinel_hud", "compliance_dashboard", "f36_plant_floor"]
                implicitWidth: 180
                Accessible.name: "Context filter"
            }

            Text { text: "Tier:"; font.pixelSize: EmbryStyle.text.sm; color: EmbryStyle.colors.textSecondary }
            EmbryComboBox {
                id: tierFilterCombo
                model: ["all", "critical", "warning", "advisory"]
                implicitWidth: 120
                Accessible.name: "Alert tier filter"
            }
        }

        // -- Summary cards --
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space2

            Repeater {
                model: [
                    { label: "sentinel_hud", ctx: "sentinel_hud", color: EmbryStyle.colors.accent },
                    { label: "compliance", ctx: "compliance_review", color: EmbryStyle.colors.accentGreen },
                    { label: "f36_plant", ctx: "f36_plant_floor", color: EmbryStyle.colors.accentAmber }
                ]
                Rectangle {
                    Layout.fillWidth: true
                    height: 36; radius: EmbryStyle.layout.radiusSm
                    color: EmbryStyle.colors.bgElevated; border.width: 1; border.color: EmbryStyle.colors.border
                    RowLayout {
                        anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2; spacing: EmbryStyle.layout.space2
                        Text { text: modelData.label; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: modelData.color }
                        Item { Layout.fillWidth: true }
                        Text { text: countByContext(modelData.ctx) + ""; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.Bold; color: EmbryStyle.colors.textPrimary }
                    }
                }
            }

            Repeater {
                model: [
                    { label: "CRIT", tier: "critical", color: EmbryStyle.colors.statusCritical },
                    { label: "WARN", tier: "warning", color: EmbryStyle.colors.statusWarning },
                    { label: "ADV", tier: "advisory", color: EmbryStyle.colors.statusInfo }
                ]
                Rectangle {
                    Layout.fillWidth: true
                    height: 36; radius: EmbryStyle.layout.radiusSm
                    color: EmbryStyle.colors.bgElevated; border.width: 1; border.color: EmbryStyle.colors.border
                    RowLayout {
                        anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2; spacing: EmbryStyle.layout.space2
                        Text { text: modelData.label; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: modelData.color }
                        Item { Layout.fillWidth: true }
                        Text { text: countByTier(modelData.tier) + ""; font.pixelSize: EmbryStyle.text.sm; font.weight: Font.Bold; color: EmbryStyle.colors.textPrimary }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

        // -- Events Table + Detail --
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: EmbryStyle.layout.space4

            // Table
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
                    spacing: EmbryStyle.layout.space1

                    // Header row
                    RowLayout {
                        Layout.fillWidth: true; spacing: 0
                        Text { Layout.fillWidth: true; text: "Event Name"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 100; text: "Context"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 80; text: "Action"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 40; text: "Pos"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 60; text: "Tier"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 40; text: "Flash"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                        Text { Layout.preferredWidth: 40; text: "ACK"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                    ListView {
                        id: eventsListView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: filteredEvents()
                        spacing: 1

                        delegate: Rectangle {
                            width: eventsListView.width
                            height: 28
                            radius: EmbryStyle.layout.radiusSm
                            color: selectedIndex === index ? EmbryStyle.colors.selectBg : evRowMa.containsMouse ? EmbryStyle.colors.bgHover : "transparent"

                            RowLayout {
                                anchors.fill: parent; spacing: 0
                                Text { Layout.fillWidth: true; text: modelData.name || ""; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textPrimary; elide: Text.ElideRight }
                                Text { Layout.preferredWidth: 100; text: modelData.context || ""; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.textMuted; elide: Text.ElideRight }
                                Text { Layout.preferredWidth: 80; text: modelData.action || ""; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.accent; elide: Text.ElideRight }
                                Text { Layout.preferredWidth: 40; text: modelData.position !== undefined ? modelData.position + "" : "--"; font.pixelSize: EmbryStyle.text.xs; font.family: EmbryStyle.text.monoFamily; color: EmbryStyle.colors.textSecondary }
                                Rectangle {
                                    Layout.preferredWidth: 50; height: 16; radius: 4
                                    color: {
                                        var t = modelData.alert_tier || ""
                                        if (t === "critical") return EmbryStyle.colors.statusCriticalBg
                                        if (t === "warning") return EmbryStyle.colors.statusWarningBg
                                        return EmbryStyle.colors.statusInfoBg
                                    }
                                    Text { anchors.centerIn: parent; text: (modelData.alert_tier || "").toUpperCase(); font.pixelSize: 7; font.weight: Font.Bold; color: { var t = modelData.alert_tier || ""; if (t === "critical") return EmbryStyle.colors.statusCritical; if (t === "warning") return EmbryStyle.colors.statusWarning; return EmbryStyle.colors.statusInfo } }
                                }
                                Text { Layout.preferredWidth: 40; text: modelData.flash ? EmbryStyle.icons.flash : ""; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.accentAmber; horizontalAlignment: Text.AlignHCenter }
                                Text { Layout.preferredWidth: 40; text: modelData.requires_ack ? EmbryStyle.icons.checkmark : ""; font.pixelSize: EmbryStyle.text.xs; color: EmbryStyle.colors.accentRed; horizontalAlignment: Text.AlignHCenter }
                            }

                            MouseArea {
                                id: evRowMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: selectedIndex = index
                            }
                            Accessible.name: (modelData.name || "event") + " row"; Accessible.role: Accessible.ListItem
                        }
                    }
                }
            }

            // Event detail
            Rectangle {
                Layout.preferredWidth: 280
                Layout.fillHeight: true
                radius: EmbryStyle.layout.radiusMd
                color: EmbryStyle.colors.bgElevated
                border.width: 1
                border.color: EmbryStyle.colors.border

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: EmbryStyle.layout.space3
                    spacing: EmbryStyle.layout.space2
                    visible: selectedEvent !== null

                    Text {
                        text: "Event Detail"
                        font.pixelSize: EmbryStyle.text.base
                        font.weight: Font.DemiBold
                        color: EmbryStyle.colors.textSecondary
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                    Text {
                        text: selectedEvent ? (selectedEvent.name || "") : ""
                        font.pixelSize: EmbryStyle.text.sm
                        font.weight: Font.Bold
                        color: EmbryStyle.colors.textPrimary
                    }

                    Text {
                        text: selectedEvent ? (selectedEvent.description || "") : ""
                        font.pixelSize: EmbryStyle.text.sm
                        color: EmbryStyle.colors.textSecondary
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: EmbryStyle.colors.separator }

                    // JSON display
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        TextArea {
                            readOnly: true
                            text: selectedEvent ? JSON.stringify(selectedEvent, null, 2) : ""
                            font.pixelSize: EmbryStyle.text.xs
                            font.family: EmbryStyle.text.monoFamily
                            color: EmbryStyle.colors.textSecondary
                            wrapMode: Text.WrapAnywhere
                            background: Rectangle { color: "transparent" }

                            Accessible.name: "Event JSON detail"
                            Accessible.role: Accessible.StaticText
                        }
                    }
                }

                // Empty state
                Text {
                    anchors.centerIn: parent
                    visible: selectedEvent === null
                    text: "Select an event"
                    font.pixelSize: EmbryStyle.text.base
                    color: EmbryStyle.colors.textMuted
                }
            }
        }
    }
}
