import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import "."

// Transport controls bar: play/pause, record, loop toggle, scrub slider, time display.
// Extracted from Editor.qml — requires editorBridge and refPlayer from parent scope.

Rectangle {
    id: transport

    required property var editorBridge
    required property var refPlayer
    required property bool loopEnabled

    signal loopToggled(bool enabled)

    implicitHeight: 50
    color: HorusStyle.colors.bgElevated
    radius: 12

    function formatTime(seconds) {
        let m = Math.floor(seconds / 60)
        let s = Math.floor(seconds % 60)
        return "%1:%2".arg(m).arg(String(s).padStart(2, '0'))
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        // Play/Pause
        Button {
            id: playBtn
            implicitWidth: 40; implicitHeight: 40
            onClicked: refPlayer.playbackState === MediaPlayer.PlayingState ? refPlayer.pause() : refPlayer.play()
            background: Rectangle {
                color: playBtn.hovered ? HorusStyle.colors.bgHover : "transparent"
                radius: 8
            }
            contentItem: Icon {
                source: refPlayer.playbackState === MediaPlayer.PlayingState ? "icons/pause.svg" : "icons/play.svg"
                size: 20
            }
            ToolTip.visible: hovered
            ToolTip.text: "Play / Pause (Space)"
        }

        // Record
        Button {
            id: recBtn
            implicitWidth: 40; implicitHeight: 40
            onClicked: {
                if (editorBridge.isRecording) {
                    editorBridge.stopRecording()
                    refPlayer.pause()
                } else {
                    editorBridge.setPhase("record")
                    editorBridge.startCountdown()
                }
            }
            background: Rectangle {
                color: editorBridge.isRecording ? Qt.rgba(1, 0, 0, 0.2) : (recBtn.hovered ? HorusStyle.colors.bgHover : "transparent")
                radius: 8
                border.color: editorBridge.isRecording ? HorusStyle.colors.accentRed : "transparent"
                border.width: editorBridge.isRecording ? 1 : 0
            }
            contentItem: Icon {
                source: "icons/record.svg"
                size: 20
                opacity: editorBridge.isRecording ? 1.0 : 0.53
            }
            ToolTip.visible: hovered
            ToolTip.text: "Record (R)"
        }

        // Loop toggle
        Button {
            id: loopBtn
            implicitWidth: 40; implicitHeight: 40
            checkable: true
            checked: transport.loopEnabled
            onToggled: {
                transport.loopToggled(checked)
            }
            background: Rectangle {
                color: loopBtn.checked
                    ? Qt.rgba(0.29, 0.62, 1.0, 0.2)
                    : (loopBtn.hovered ? HorusStyle.colors.bgHover : "transparent")
                radius: 8
                border.color: loopBtn.checked ? HorusStyle.colors.accent : "transparent"
                border.width: loopBtn.checked ? 1 : 0
            }
            contentItem: Label {
                text: "\u21BB"
                font.pixelSize: 22
                color: loopBtn.checked ? HorusStyle.colors.accent : HorusStyle.colors.textSubtle
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            ToolTip.visible: hovered
            ToolTip.text: "Loop region (I/O to set points)"
        }

        // Scrub slider
        Slider {
            id: scrubSlider
            Layout.fillWidth: true
            from: 0
            to: refPlayer.duration > 0 ? refPlayer.duration : 1
            value: refPlayer.position
            live: true

            property bool userDragging: pressed

            onMoved: {
                if (userDragging) {
                    refPlayer.position = value
                }
            }

            Connections {
                target: transport.refPlayer
                function onPositionChanged() {
                    if (!scrubSlider.userDragging) {
                        scrubSlider.value = transport.refPlayer.position
                    }
                }
            }

            background: Rectangle {
                x: scrubSlider.leftPadding
                y: scrubSlider.topPadding + scrubSlider.availableHeight / 2 - height / 2
                width: scrubSlider.availableWidth
                height: 6
                radius: 3
                color: HorusStyle.colors.bgInput

                // Progress fill
                Rectangle {
                    width: scrubSlider.visualPosition * parent.width
                    height: parent.height
                    radius: 3
                    color: HorusStyle.colors.accent
                    opacity: 0.6
                }

                // Loop region highlight on scrub bar
                Rectangle {
                    visible: transport.loopEnabled && transport.editorBridge.inPointMs >= 0 && transport.editorBridge.outPointMs >= 0 && transport.refPlayer.duration > 0
                    x: visible ? (transport.editorBridge.inPointMs / transport.refPlayer.duration) * parent.width : 0
                    width: visible ? ((transport.editorBridge.outPointMs - transport.editorBridge.inPointMs) / transport.refPlayer.duration) * parent.width : 0
                    height: parent.height
                    radius: 3
                    color: Qt.rgba(0.29, 0.62, 1.0, 0.3)
                }
            }

            handle: Rectangle {
                x: scrubSlider.leftPadding + scrubSlider.visualPosition * (scrubSlider.availableWidth - width)
                y: scrubSlider.topPadding + scrubSlider.availableHeight / 2 - height / 2
                width: 14; height: 14
                radius: 7
                color: scrubSlider.pressed ? HorusStyle.colors.textPrimary : HorusStyle.colors.accent
                border.color: HorusStyle.colors.accent
                border.width: 2
            }
        }

        // Time display
        Label {
            text: formatTime(refPlayer.position / 1000) + " / " + formatTime(refPlayer.duration / 1000)
            font.family: "JetBrains Mono"
            font.pixelSize: 13
            color: HorusStyle.colors.textMuted
            Layout.minimumWidth: 90
            horizontalAlignment: Text.AlignRight
        }
    }
}
