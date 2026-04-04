import QtQuick
import QtQuick.Controls
import "."

/**
 * Draggable bracket handle for I/O point editing on the timeline.
 *
 * Properties:
 *   isInPoint: bool       - true = green "[" in-handle, false = red "]" out-handle
 *   positionNormalized: real - 0.0–1.0 position on timeline, -1 = not set
 *   timelineWidth: real   - parent timeline width for drag constraints
 *
 * Signals:
 *   positionChanged(real newNormalized) - emitted on drag release
 */
Item {
    id: handle

    property bool isInPoint: true
    property real positionNormalized: -1.0
    property real timelineWidth: 1.0

    signal positionChanged(real newNormalized)

    visible: positionNormalized >= 0.0

    // Position from normalized value (ignored while dragging)
    x: !dragArea.drag.active && positionNormalized >= 0
        ? positionNormalized * timelineWidth - width / 2
        : x
    width: 14
    height: parent ? parent.height : 0

    // Bracket line (vertical + top/bottom caps)
    Item {
        anchors.horizontalCenter: parent.horizontalCenter
        width: 8
        height: parent.height

        // Vertical line
        Rectangle {
            x: isInPoint ? 0 : parent.width - 2
            width: 2
            height: parent.height
            color: isInPoint ? HorusStyle.colors.accentGreen : HorusStyle.colors.accentRed
        }

        // Top cap
        Rectangle {
            x: isInPoint ? 0 : 0
            y: 0
            width: parent.width
            height: 2
            color: isInPoint ? HorusStyle.colors.accentGreen : HorusStyle.colors.accentRed
        }

        // Bottom cap
        Rectangle {
            x: isInPoint ? 0 : 0
            y: parent.height - 2
            width: parent.width
            height: 2
            color: isInPoint ? HorusStyle.colors.accentGreen : HorusStyle.colors.accentRed
        }
    }

    // Hover highlight
    Rectangle {
        anchors.fill: parent
        color: dragArea.containsMouse ? HorusStyle.colors.selectHoverBg : "transparent"
        radius: 2
    }

    // Drag area
    MouseArea {
        id: dragArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.SplitHCursor
        drag.target: handle
        drag.axis: Drag.XAxis
        drag.minimumX: 0
        drag.maximumX: handle.timelineWidth - handle.width

        onReleased: {
            if (handle.timelineWidth > 0) {
                let centerX = handle.x + handle.width / 2
                let norm = Math.max(0.0, Math.min(1.0, centerX / handle.timelineWidth))
                handle.positionChanged(norm)
            }
        }
    }
}
