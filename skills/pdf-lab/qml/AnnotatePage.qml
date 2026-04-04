import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    property var bridge: null
    property var screenshots: bridge ? JSON.parse(bridge.screenshotsJson) : []
    property int currentPage: 0
    property var bboxes: bridge ? JSON.parse(bridge.bboxesJson) : []
    property int selectedBbox: -1
    property string activeTool: "select"  // "select", "add_section", "add_table", "add_figure"

    // Undo/redo stack (from extractor/prototypes/tabbed BboxEditor pattern)
    property var undoStack: []   // [{kind: "add"|"delete", bbox: {...}, index: int}]
    property var redoStack: []

    function pushUndo(entry) {
        var stack = undoStack.slice();
        stack.push(entry);
        undoStack = stack;
        redoStack = [];
    }

    function undo() {
        if (undoStack.length === 0) return;
        var stack = undoStack.slice();
        var entry = stack.pop();
        undoStack = stack;
        var redo = redoStack.slice(); redo.push(entry); redoStack = redo;
        if (entry.kind === "add" && bridge) {
            bridge.deleteBbox(entry.index);
            selectedBbox = -1;
        } else if (entry.kind === "delete" && bridge) {
            bridge.addBbox(entry.bbox.page, entry.bbox.x, entry.bbox.y, entry.bbox.w, entry.bbox.h, entry.bbox.type);
        }
    }

    function redo() {
        if (redoStack.length === 0) return;
        var stack = redoStack.slice();
        var entry = stack.pop();
        redoStack = stack;
        var undo2 = undoStack.slice(); undo2.push(entry); undoStack = undo2;
        if (entry.kind === "add" && bridge) {
            bridge.addBbox(entry.bbox.page, entry.bbox.x, entry.bbox.y, entry.bbox.w, entry.bbox.h, entry.bbox.type);
        } else if (entry.kind === "delete" && bridge) {
            bridge.deleteBbox(entry.index);
            selectedBbox = -1;
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Toolbar ──────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 40
            color: EmbryStyle.colors.bgElevated

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space3
                anchors.rightMargin: EmbryStyle.layout.space3
                spacing: EmbryStyle.layout.space2

                // Tool buttons
                Repeater {
                    model: [
                        { tool: "select", label: "Select", icon: "↖" },
                        { tool: "add_section", label: "Section", icon: "§", color: EmbryStyle.colors.accentGreen },
                        { tool: "add_table", label: "Table", icon: "⊞", color: EmbryStyle.colors.accent },
                        { tool: "add_figure", label: "Figure", icon: "◱", color: EmbryStyle.colors.accentAmber },
                    ]

                    Rectangle {
                        required property var modelData

                        Layout.preferredWidth: toolLabel.implicitWidth + 28
                        Layout.preferredHeight: 28
                        radius: EmbryStyle.layout.radiusSm
                        color: activeTool === modelData.tool ? EmbryStyle.colors.selectBg : "transparent"
                        border.width: activeTool === modelData.tool ? 1 : 0
                        border.color: modelData.color || EmbryStyle.colors.textMuted

                        Row {
                            anchors.centerIn: parent; spacing: 4

                            Text {
                                text: modelData.icon
                                font.pixelSize: EmbryStyle.text.sm
                                color: modelData.color || EmbryStyle.colors.textPrimary
                            }
                            Text {
                                id: toolLabel
                                text: modelData.label
                                font.pixelSize: EmbryStyle.text.xs; font.weight: Font.SemiBold
                                color: activeTool === modelData.tool ? EmbryStyle.colors.textPrimary : EmbryStyle.colors.textSecondary
                            }
                        }

                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: root.activeTool = modelData.tool
                        }

                        Accessible.name: modelData.label + " tool"
                        Accessible.role: Accessible.Button
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 20; color: EmbryStyle.colors.separator }

                // Undo/Redo
                EmbryButton {
                    text: "↩"; flat: true; enabled: undoStack.length > 0
                    onClicked: root.undo()
                    Accessible.name: "Undo last annotation"; Accessible.role: Accessible.Button
                }
                EmbryButton {
                    text: "↪"; flat: true; enabled: redoStack.length > 0
                    onClicked: root.redo()
                    Accessible.name: "Redo annotation"; Accessible.role: Accessible.Button
                }

                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 20; color: EmbryStyle.colors.separator }

                // Page navigation
                EmbryButton {
                    text: "◀"; flat: true; enabled: currentPage > 0
                    onClicked: currentPage--
                    Accessible.name: "Previous page"; Accessible.role: Accessible.Button
                }

                Text {
                    text: "Page " + (currentPage + 1) + " / " + Math.max(screenshots.length, 1)
                    font.pixelSize: EmbryStyle.text.sm; font.family: EmbryStyle.text.monoFamily
                    color: EmbryStyle.colors.textSecondary
                }

                EmbryButton {
                    text: "▶"; flat: true; enabled: currentPage < screenshots.length - 1
                    onClicked: currentPage++
                    Accessible.name: "Next page"; Accessible.role: Accessible.Button
                }

                Item { Layout.fillWidth: true }

                // Delete selected bbox
                EmbryButton {
                    text: "Delete Region"
                    variant: "danger"
                    enabled: selectedBbox >= 0
                    onClicked: {
                        if (bridge && selectedBbox >= 0 && selectedBbox < bboxes.length) {
                            var deleted = bboxes[selectedBbox];
                            root.pushUndo({kind: "delete", bbox: deleted, index: selectedBbox});
                            bridge.deleteBbox(selectedBbox);
                            selectedBbox = -1;
                        }
                    }
                    Accessible.name: "Delete selected region"; Accessible.role: Accessible.Button
                }

                EmbryButton {
                    text: "Save Annotations"
                    variant: "primary"
                    onClicked: if (bridge) bridge.saveAnnotations()
                    Accessible.name: "Save bbox annotations"; Accessible.role: Accessible.Button
                }
            }

            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: EmbryStyle.colors.separator }
        }

        // ── Canvas Area ──────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 0

            // PDF page image with bbox overlay
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: EmbryStyle.colors.bg
                clip: true

                Flickable {
                    id: flickable
                    anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                    contentWidth: pageImage.width; contentHeight: pageImage.height
                    clip: true

                    Image {
                        id: pageImage

                        source: screenshots.length > currentPage ? ("file://" + screenshots[currentPage]) : ""
                        fillMode: Image.PreserveAspectFit
                        width: Math.min(sourceSize.width, flickable.width)
                        height: sourceSize.height > 0 ? width * (sourceSize.height / sourceSize.width) : flickable.height

                        // Bbox overlay canvas
                        Canvas {
                            id: bboxCanvas
                            anchors.fill: parent

                            property real startX: 0
                            property real startY: 0
                            property bool drawing: false

                            onPaint: {
                                var ctx = getContext("2d");
                                ctx.clearRect(0, 0, width, height);

                                // Draw existing bboxes
                                var pageBboxes = bboxes.filter(function(b) { return b.page === currentPage; });
                                for (var i = 0; i < pageBboxes.length; i++) {
                                    var b = pageBboxes[i];
                                    var bx = b.x * width;
                                    var by = b.y * height;
                                    var bw = b.w * width;
                                    var bh = b.h * height;

                                    var isSelected = (bboxes.indexOf(b) === selectedBbox);

                                    // Fill
                                    ctx.globalAlpha = isSelected ? 0.25 : 0.12;
                                    ctx.fillStyle = _typeColor(b.type);
                                    ctx.fillRect(bx, by, bw, bh);

                                    // Border
                                    ctx.globalAlpha = isSelected ? 1.0 : 0.6;
                                    ctx.strokeStyle = _typeColor(b.type);
                                    ctx.lineWidth = isSelected ? 2.5 : 1.5;
                                    ctx.setLineDash(isSelected ? [] : [4, 2]);
                                    ctx.strokeRect(bx, by, bw, bh);
                                    ctx.setLineDash([]);

                                    // Label
                                    ctx.globalAlpha = 0.9;
                                    ctx.font = "bold 11px " + EmbryStyle.text.monoFamily;
                                    ctx.fillStyle = _typeColor(b.type);
                                    ctx.fillText(b.type.toUpperCase(), bx + 3, by + 13);
                                }

                                // Draw in-progress bbox
                                if (drawing && activeTool !== "select") {
                                    ctx.globalAlpha = 0.3;
                                    ctx.fillStyle = _toolColor();
                                    ctx.fillRect(startX, startY, _mouseX - startX, _mouseY - startY);
                                    ctx.globalAlpha = 0.8;
                                    ctx.strokeStyle = _toolColor();
                                    ctx.lineWidth = 2;
                                    ctx.strokeRect(startX, startY, _mouseX - startX, _mouseY - startY);
                                }

                                ctx.globalAlpha = 1.0;
                            }

                            property real _mouseX: 0
                            property real _mouseY: 0

                            function _typeColor(type) {
                                if (type === "section") return EmbryStyle.colors.accentGreen.toString();
                                if (type === "table") return EmbryStyle.colors.accent.toString();
                                if (type === "figure") return EmbryStyle.colors.accentAmber.toString();
                                return EmbryStyle.colors.textMuted.toString();
                            }

                            function _toolColor() {
                                if (activeTool === "add_section") return EmbryStyle.colors.accentGreen.toString();
                                if (activeTool === "add_table") return EmbryStyle.colors.accent.toString();
                                if (activeTool === "add_figure") return EmbryStyle.colors.accentAmber.toString();
                                return EmbryStyle.colors.textMuted.toString();
                            }

                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: activeTool === "select" ? Qt.ArrowCursor : Qt.CrossCursor

                                onPressed: function(mouse) {
                                    if (activeTool === "select") {
                                        // Hit test existing bboxes
                                        var nx = mouse.x / bboxCanvas.width;
                                        var ny = mouse.y / bboxCanvas.height;
                                        var pageBboxes = bboxes.filter(function(b) { return b.page === currentPage; });
                                        selectedBbox = -1;
                                        for (var i = pageBboxes.length - 1; i >= 0; i--) {
                                            var b = pageBboxes[i];
                                            if (nx >= b.x && nx <= b.x + b.w && ny >= b.y && ny <= b.y + b.h) {
                                                selectedBbox = bboxes.indexOf(b);
                                                break;
                                            }
                                        }
                                        bboxCanvas.requestPaint();
                                    } else {
                                        bboxCanvas.startX = mouse.x;
                                        bboxCanvas.startY = mouse.y;
                                        bboxCanvas.drawing = true;
                                    }
                                }

                                onPositionChanged: function(mouse) {
                                    bboxCanvas._mouseX = mouse.x;
                                    bboxCanvas._mouseY = mouse.y;
                                    if (bboxCanvas.drawing) bboxCanvas.requestPaint();
                                }

                                onReleased: function(mouse) {
                                    if (bboxCanvas.drawing && activeTool !== "select") {
                                        var x1 = Math.min(bboxCanvas.startX, mouse.x) / bboxCanvas.width;
                                        var y1 = Math.min(bboxCanvas.startY, mouse.y) / bboxCanvas.height;
                                        var w = Math.abs(mouse.x - bboxCanvas.startX) / bboxCanvas.width;
                                        var h = Math.abs(mouse.y - bboxCanvas.startY) / bboxCanvas.height;

                                        // Minimum size threshold
                                        if (w > 0.01 && h > 0.01) {
                                            var type = activeTool.replace("add_", "");
                                            if (bridge) {
                                                var newBbox = {page: currentPage, x: x1, y: y1, w: w, h: h, type: type};
                                                bridge.addBbox(currentPage, x1, y1, w, h, type);
                                                root.pushUndo({kind: "add", bbox: newBbox, index: bboxes.length});
                                            }
                                        }
                                        bboxCanvas.drawing = false;
                                        bboxCanvas.requestPaint();
                                    }
                                }
                            }
                        }

                        // Repaint when bboxes or selection change
                        Connections {
                            target: root
                            function onBboxesChanged() { bboxCanvas.requestPaint(); }
                            function onSelectedBboxChanged() { bboxCanvas.requestPaint(); }
                            function onCurrentPageChanged() { bboxCanvas.requestPaint(); }
                        }
                    }

                    // Empty state
                    Text {
                        anchors.centerIn: parent
                        text: "Load a PDF or run diagnostics to capture page screenshots"
                        font.pixelSize: EmbryStyle.text.base; color: EmbryStyle.colors.textMuted
                        visible: screenshots.length === 0
                    }
                }

                Accessible.name: "PDF page with annotation overlay"
                Accessible.role: Accessible.Canvas
            }

            // ── Side Panel: Bbox List + Keyboard Shortcuts ─────
            // Keyboard shortcuts (from extractor/prototypes/tabbed BboxEditor)
            Shortcut { sequence: "Ctrl+Z"; onActivated: root.undo() }
            Shortcut { sequence: "Ctrl+Shift+Z"; onActivated: root.redo() }
            Shortcut { sequence: "Delete"; onActivated: { if (selectedBbox >= 0 && selectedBbox < bboxes.length) { var d = bboxes[selectedBbox]; root.pushUndo({kind: "delete", bbox: d, index: selectedBbox}); if (bridge) bridge.deleteBbox(selectedBbox); selectedBbox = -1; } } }
            Shortcut { sequence: "Escape"; onActivated: { root.activeTool = "select"; selectedBbox = -1; } }
            Shortcut { sequence: "S"; onActivated: root.activeTool = "add_section" }
            Shortcut { sequence: "T"; onActivated: root.activeTool = "add_table" }
            Shortcut { sequence: "F"; onActivated: root.activeTool = "add_figure" }
            Shortcut { sequence: "V"; onActivated: root.activeTool = "select" }

            Rectangle {
                Layout.preferredWidth: 200; Layout.fillHeight: true
                color: EmbryStyle.colors.bgElevated
                border.width: 1; border.color: EmbryStyle.colors.border

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: EmbryStyle.layout.space2
                    spacing: EmbryStyle.layout.space2

                    Text {
                        text: "Regions (" + bboxes.length + ")"
                        font.pixelSize: EmbryStyle.text.sm; font.weight: Font.SemiBold
                        color: EmbryStyle.colors.textPrimary
                    }

                    ListView {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; model: bboxes; spacing: 2

                        delegate: Rectangle {
                            required property var modelData; required property int index
                            width: parent ? parent.width : 180; height: 36
                            radius: EmbryStyle.layout.radiusSm
                            color: index === selectedBbox ? EmbryStyle.colors.selectBg : "transparent"
                            border.width: index === selectedBbox ? 1 : 0
                            border.color: EmbryStyle.colors.selectBorder

                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 4; spacing: 1

                                RowLayout {
                                    spacing: 4

                                    Rectangle {
                                        width: 8; height: 8; radius: 4
                                        color: {
                                            if (modelData.type === "section") return EmbryStyle.colors.accentGreen;
                                            if (modelData.type === "table") return EmbryStyle.colors.accent;
                                            if (modelData.type === "figure") return EmbryStyle.colors.accentAmber;
                                            return EmbryStyle.colors.textMuted;
                                        }
                                    }
                                    Text {
                                        text: modelData.type.toUpperCase()
                                        font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold
                                        color: EmbryStyle.colors.textPrimary
                                    }
                                    Text {
                                        text: "p" + (modelData.page + 1)
                                        font.pixelSize: EmbryStyle.text.xs
                                        color: EmbryStyle.colors.textMuted
                                    }
                                }

                                Text {
                                    text: modelData.x.toFixed(2) + "," + modelData.y.toFixed(2) + " " + modelData.w.toFixed(2) + "×" + modelData.h.toFixed(2)
                                    font.pixelSize: 9; font.family: EmbryStyle.text.monoFamily
                                    color: EmbryStyle.colors.textGhost
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    selectedBbox = index;
                                    if (modelData.page !== currentPage) currentPage = modelData.page;
                                }
                            }

                            Accessible.name: modelData.type + " region on page " + (modelData.page + 1)
                            Accessible.role: Accessible.ListItem
                        }
                    }
                }
            }
        }
    }
}
