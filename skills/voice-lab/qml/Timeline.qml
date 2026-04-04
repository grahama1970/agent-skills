import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import VoiceLab 1.0
import "."

/**
 * 2-track NLE timeline with draggable I/O handles and playhead.
 *
 * Track 1 (top): Recording — green waveform (empty until recording)
 * Track 2 (bottom): Reference — blue waveform with segment handles
 *
 * Full-height overlays: dim regions, I/O region highlight, IOHandles, Playhead.
 */
Item {
    id: timeline

    required property var editorBridge
    property var refPlayer
    property int selectedSegment: -1

    signal segmentClicked(int idx)

    // Derived normalized positions (null-guarded)
    readonly property real ioInNorm: editorBridge && editorBridge.inPointMs >= 0 && editorBridge.audioDuration > 0
        ? (editorBridge.inPointMs / 1000.0) / editorBridge.audioDuration : -1.0
    readonly property real ioOutNorm: editorBridge && editorBridge.outPointMs >= 0 && editorBridge.audioDuration > 0
        ? (editorBridge.outPointMs / 1000.0) / editorBridge.audioDuration : -1.0
    readonly property real playheadNorm: refPlayer && refPlayer.duration > 0
        ? refPlayer.position / refPlayer.duration : 0.0

    // Track layout
    ColumnLayout {
        id: trackLayout
        anchors.fill: parent
        spacing: 0

        // Recording Track (top)
        Item {
            id: recTrack
            Layout.fillWidth: true
            Layout.preferredHeight: 100

            Rectangle {
                anchors.fill: parent
                color: HorusStyle.colors.bgElevated
            }

            Label {
                x: 8; y: 4; z: 6
                text: "Recording"
                font.family: "Inter"
                font.pixelSize: 11
                color: HorusStyle.colors.textGhost
            }

            WaveformPainter {
                id: recWaveform
                anchors.fill: parent
                peaks: editorBridge ? editorBridge.recPeaks : []
                waveColor: Qt.rgba(0.0, 1.0, 0.53, 0.4)
            }

            Label {
                anchors.centerIn: parent
                visible: !editorBridge || editorBridge.recPeaks.length === 0
                text: "Press R to record"
                font.family: "Inter"
                font.pixelSize: 14
                color: HorusStyle.colors.textGhost
                z: 1
            }

            Rectangle {
                anchors.fill: parent
                visible: editorBridge && editorBridge.isRecording
                color: "transparent"
                border.color: HorusStyle.colors.accentGreen
                border.width: 2
                z: 8

                SequentialAnimation on opacity {
                    running: editorBridge ? editorBridge.isRecording : false
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.3; duration: HorusStyle.anim.breathe }
                    NumberAnimation { to: 1.0; duration: HorusStyle.anim.breathe }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: HorusStyle.colors.separator
        }

        // Reference Track (bottom)
        Item {
            id: refTrack
            Layout.fillWidth: true
            Layout.preferredHeight: 100

            Rectangle {
                anchors.fill: parent
                color: HorusStyle.colors.bg
            }

            Label {
                x: 8; y: 4; z: 6
                text: "Reference"
                font.family: "Inter"
                font.pixelSize: 11
                color: HorusStyle.colors.textGhost
            }

            WaveformPainter {
                id: refWaveform
                anchors.fill: parent
                peaks: editorBridge ? editorBridge.refPeaks : []
                waveColor: Qt.rgba(0.29, 0.62, 1.0, 0.4)
            }

            // Segment handles (start)
            Repeater {
                model: editorBridge ? editorBridge.segmentModel : null
                SegmentHandle {
                    segmentIndex: model.index
                    isEnd: false
                    boundaryMs: model.startMs
                    totalDuration: editorBridge ? editorBridge.audioDuration : 1.0
                    waveformWidth: refWaveform.width
                    height: refWaveform.height
                    z: 10
                    onBoundaryMoved: (idx, end, ms) => {
                        editorBridge.updateSegmentBounds(idx, ms, editorBridge.getSegmentEndMs(idx))
                    }
                }
            }

            // Segment handles (end)
            Repeater {
                model: editorBridge ? editorBridge.segmentModel : null
                SegmentHandle {
                    segmentIndex: model.index
                    isEnd: true
                    boundaryMs: model.endMs
                    totalDuration: editorBridge ? editorBridge.audioDuration : 1.0
                    waveformWidth: refWaveform.width
                    height: refWaveform.height
                    z: 10
                    onBoundaryMoved: (idx, end, ms) => {
                        editorBridge.updateSegmentBounds(idx, editorBridge.getSegmentStartMs(idx), ms)
                    }
                }
            }

            // Segment index labels
            Repeater {
                model: editorBridge ? editorBridge.segmentModel : null
                Label {
                    x: editorBridge && editorBridge.audioDuration > 0
                        ? (model.startMs / 1000.0 / editorBridge.audioDuration) * refWaveform.width + 4
                        : 0
                    y: 2
                    text: model.segIndex
                    font.family: "JetBrains Mono"
                    font.pixelSize: 9
                    color: HorusStyle.colors.textGhost
                    z: 6
                }
            }

            // Selected segment highlight
            Rectangle {
                visible: selectedSegment >= 0 && editorBridge && editorBridge.audioDuration > 0
                x: visible ? (editorBridge.getSegmentStartMs(selectedSegment) / 1000.0 / editorBridge.audioDuration) * refWaveform.width : 0
                width: visible ? ((editorBridge.getSegmentEndMs(selectedSegment) - editorBridge.getSegmentStartMs(selectedSegment)) / 1000.0 / editorBridge.audioDuration) * refWaveform.width : 0
                height: refWaveform.height
                color: Qt.rgba(0.29, 0.62, 1.0, 0.08)
                border.color: HorusStyle.colors.accent
                border.width: 1
                radius: 2
            }
        }
    }

    // Full-height overlays (absolute positioned)

    // Dim-left (before in-point)
    Rectangle {
        visible: ioInNorm >= 0
        x: 0
        y: 0
        width: ioInNorm >= 0 ? ioInNorm * timeline.width : 0
        height: timeline.height
        color: Qt.rgba(0, 0, 0, 0.4)
        z: 5
    }

    // Dim-right (after out-point)
    Rectangle {
        visible: ioOutNorm >= 0
        x: ioOutNorm >= 0 ? ioOutNorm * timeline.width : timeline.width
        y: 0
        width: ioOutNorm >= 0 ? timeline.width - (ioOutNorm * timeline.width) : 0
        height: timeline.height
        color: Qt.rgba(0, 0, 0, 0.4)
        z: 5
    }

    // I/O region highlight (between handles)
    Rectangle {
        visible: ioInNorm >= 0 && ioOutNorm >= 0
        x: ioInNorm >= 0 ? ioInNorm * timeline.width : 0
        y: 0
        width: (ioInNorm >= 0 && ioOutNorm >= 0) ? (ioOutNorm - ioInNorm) * timeline.width : 0
        height: timeline.height
        color: Qt.rgba(0.29, 0.62, 1.0, 0.06)
        z: 4
    }

    // In-point handle
    IOHandle {
        id: inHandle
        isInPoint: true
        positionNormalized: ioInNorm
        timelineWidth: timeline.width
        height: timeline.height
        z: 20

        onPositionChanged: (norm) => {
            if (editorBridge && editorBridge.audioDuration > 0) {
                let ms = Math.round(norm * editorBridge.audioDuration * 1000)
                editorBridge.setInPoint(ms)
            }
        }
    }

    // Out-point handle
    IOHandle {
        id: outHandle
        isInPoint: false
        positionNormalized: ioOutNorm
        timelineWidth: timeline.width
        height: timeline.height
        z: 20

        onPositionChanged: (norm) => {
            if (editorBridge && editorBridge.audioDuration > 0) {
                let ms = Math.round(norm * editorBridge.audioDuration * 1000)
                editorBridge.setOutPoint(ms)
            }
        }
    }

    // Playhead
    Playhead {
        id: playheadItem
        positionNormalized: playheadNorm
        timelineWidth: timeline.width
        height: timeline.height
        z: 15

        onSeekRequested: (norm) => {
            if (refPlayer && refPlayer.duration > 0) {
                refPlayer.position = norm * refPlayer.duration
            }
        }
    }

    // Click-to-seek (below everything)
    MouseArea {
        anchors.fill: parent
        z: -1
        onClicked: (mouse) => {
            if (editorBridge && editorBridge.audioDuration > 0 && refPlayer && refPlayer.duration > 0) {
                let norm = mouse.x / width
                let ms = norm * editorBridge.audioDuration * 1000
                refPlayer.position = norm * refPlayer.duration
                timeline.segmentClicked(editorBridge.findSegmentAt(ms))
            }
        }
    }
}
