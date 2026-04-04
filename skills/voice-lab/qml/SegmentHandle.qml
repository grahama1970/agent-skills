import QtQuick
import QtQuick.Controls
import "."

/**
 * Draggable vertical line for segment boundary editing.
 * Place via Repeater over segmentModel.
 *
 * Properties:
 *   segmentIndex: int  - row in segmentModel
 *   isEnd: bool        - false=start boundary, true=end boundary
 *   boundaryMs: int    - current boundary in ms
 *   totalDuration: real - total audio duration in seconds
 *   waveformWidth: real - parent waveform width in pixels
 *
 * Signals:
 *   boundaryMoved(int segmentIndex, bool isEnd, int newMs)
 */
Item {
    id: handle

    property int segmentIndex: 0
    property bool isEnd: false
    property int boundaryMs: 0
    property real totalDuration: 1.0
    property real waveformWidth: 1.0

    signal boundaryMoved(int segmentIndex, bool isEnd, int newMs)

    // Position from ms
    x: totalDuration > 0 ? (boundaryMs / 1000.0 / totalDuration) * waveformWidth - width / 2 : 0
    width: 12  // Wide hit area
    height: parent ? parent.height : 0

    // Visible line (thin, centered in hit area)
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        width: 2
        height: parent.height
        color: dragArea.drag.active
            ? HorusStyle.colors.accent  // Blue when dragging
            : HorusStyle.colors.textSubtle  // rgba(255,255,255,0.33)

        Behavior on color { ColorAnimation { duration: 150 } }
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
        drag.maximumX: handle.waveformWidth - handle.width

        onReleased: {
            if (handle.totalDuration > 0 && handle.waveformWidth > 0) {
                let centerX = handle.x + handle.width / 2
                let fraction = centerX / handle.waveformWidth
                let newMs = Math.round(fraction * handle.totalDuration * 1000)
                newMs = Math.max(0, Math.min(newMs, Math.round(handle.totalDuration * 1000)))
                handle.boundaryMoved(handle.segmentIndex, handle.isEnd, newMs)
            }
        }
    }

    // Small triangle indicator at top
    Canvas {
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        width: 8; height: 6

        onPaint: {
            let ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.fillStyle = dragArea.containsMouse
                ? HorusStyle.colors.accent
                : HorusStyle.colors.textSubtle
            ctx.beginPath()
            ctx.moveTo(0, 0)
            ctx.lineTo(width, 0)
            ctx.lineTo(width / 2, height)
            ctx.closePath()
            ctx.fill()
        }
    }
}
