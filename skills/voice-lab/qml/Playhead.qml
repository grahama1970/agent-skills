import QtQuick
import QtQuick.Controls
import "."

/**
 * Draggable playhead with triangle grab indicator.
 *
 * Properties:
 *   positionNormalized: real - 0.0–1.0 position on timeline
 *   timelineWidth: real      - parent timeline width for drag constraints
 *
 * Signals:
 *   seekRequested(real normalizedPos) - emitted on drag release
 */
Item {
    id: playhead

    property real positionNormalized: 0.0
    property real timelineWidth: 1.0

    // Position from normalized value (ignored while dragging)
    x: !dragArea.drag.active
        ? positionNormalized * timelineWidth - width / 2
        : x
    width: 14
    height: parent ? parent.height : 0

    // Vertical line
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        width: 2
        height: parent.height
        color: HorusStyle.colors.accent
    }

    // Triangle grab handle at top
    Canvas {
        id: grabTriangle
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        width: 10; height: 8

        onPaint: {
            let ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.fillStyle = dragArea.containsMouse || dragArea.drag.active
                ? HorusStyle.colors.textPrimary
                : HorusStyle.colors.accent
            ctx.beginPath()
            ctx.moveTo(0, 0)
            ctx.lineTo(width, 0)
            ctx.lineTo(width / 2, height)
            ctx.closePath()
            ctx.fill()
        }

        // Repaint on hover/drag state change
        Connections {
            target: dragArea
            function onContainsMouseChanged() { grabTriangle.requestPaint() }
        }
    }

    // Drag area
    MouseArea {
        id: dragArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.SplitHCursor
        drag.target: playhead
        drag.axis: Drag.XAxis
        drag.minimumX: 0
        drag.maximumX: playhead.timelineWidth - playhead.width

        onReleased: {
            if (playhead.timelineWidth > 0) {
                let centerX = playhead.x + playhead.width / 2
                let norm = Math.max(0.0, Math.min(1.0, centerX / playhead.timelineWidth))
                playhead.seekRequested(norm)
            }
        }
    }

    signal seekRequested(real normalizedPos)
}
