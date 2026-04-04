import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import QtWebEngine
import VoiceLab 1.0
import "."

// Editor page — tab content for the Record tab in VoiceLabApp.
// Converted from ApplicationWindow to Item for embedding in tabbed layout.
// Shortcuts are managed by VoiceLabApp when this tab is active.

Item {
    id: root

    required property var editorBridge
    property int selectedSegment: -1
    property string currentPhase: editorBridge.phase
    property bool loopEnabled: false

    function formatTime(seconds) {
        let m = Math.floor(seconds / 60)
        let s = Math.floor(seconds % 60)
        return "%1:%2".arg(m).arg(String(s).padStart(2, '0'))
    }

    // Reference audio playback
    MediaPlayer {
        id: refPlayer
        source: editorBridge.refAudioPath ? Qt.resolvedUrl("file://" + editorBridge.refAudioPath) : ""
        audioOutput: AudioOutput { id: audioOut }
        onPlaybackStateChanged: {
            if (refPlayer.playbackState === MediaPlayer.PlayingState) {
                ytPreview.ytSeek(refPlayer.position / 1000.0)
                ytPreview.ytPlay()
            } else {
                ytPreview.ytPause()
            }
        }
    }

    // Expose refPlayer so VoiceLabApp can wire shortcuts
    property alias player: refPlayer

    // Bridge signal connections
    Connections {
        target: editorBridge
        function onPlaybackRequested() {
            if (editorBridge.inPointMs >= 0) {
                refPlayer.position = editorBridge.inPointMs
            }
            refPlayer.play()
        }
        function onRecordingError(msg) {
            errorLabel.text = msg
            errorLabel.visible = true
            errorHideTimer.restart()
        }
        function onCountdownFinished() {
            editorBridge.setPhase("record")
            editorBridge.recordAndPlay()
        }
        function onRecordingStopped() {
            editorBridge.setPhase("review")
        }
        function onInPointMsChanged() {
            if (editorBridge.inPointMs >= 0 && editorBridge.outPointMs >= 0) {
                root.loopEnabled = true
            }
        }
        function onOutPointMsChanged() {
            if (editorBridge.inPointMs >= 0 && editorBridge.outPointMs >= 0) {
                root.loopEnabled = true
            }
        }
    }

    Timer {
        id: errorHideTimer
        interval: 8000
        onTriggered: errorLabel.visible = false
    }

    // Out-point boundary enforcement
    Timer {
        id: outPointStopTimer
        interval: 50
        repeat: true
        running: editorBridge.outPointMs > 0 && (editorBridge.isRecording || refPlayer.playbackState === MediaPlayer.PlayingState)

        property real lastSeekTime: 0

        onTriggered: {
            if (refPlayer.position >= editorBridge.outPointMs) {
                let now = Date.now()
                if (now - lastSeekTime < 500) return
                lastSeekTime = now

                if (editorBridge.isRecording && root.loopEnabled && editorBridge.inPointMs >= 0) {
                    editorBridge.cycleTake()
                    refPlayer.position = editorBridge.inPointMs
                    ytPreview.ytSeek(editorBridge.inPointMs / 1000.0)
                } else if (editorBridge.isRecording) {
                    editorBridge.stopRecording()
                    refPlayer.pause()
                } else if (root.loopEnabled && editorBridge.inPointMs >= 0) {
                    refPlayer.position = editorBridge.inPointMs
                    ytPreview.ytSeek(editorBridge.inPointMs / 1000.0)
                } else {
                    refPlayer.pause()
                }
            }
        }
    }

    function seekToSegment(idx) {
        if (idx < 0 || idx >= editorBridge.segmentModel.rowCount()) return
        let startMs = editorBridge.getSegmentStartMs(idx)
        if (startMs >= 0 && refPlayer.duration > 0) {
            refPlayer.position = startMs
        }
    }

    function playSegment(idx) {
        if (idx < 0 || idx >= editorBridge.segmentModel.rowCount()) return
        let startMs = editorBridge.getSegmentStartMs(idx)
        let endMs = editorBridge.getSegmentEndMs(idx)
        if (startMs >= 0) {
            refPlayer.position = startMs
            refPlayer.play()
            segmentStopTimer.endMs = endMs
            segmentStopTimer.start()
        }
    }

    Timer {
        id: segmentStopTimer
        property int endMs: 0
        interval: 50
        repeat: true
        onTriggered: {
            if (refPlayer.position >= endMs) {
                refPlayer.pause()
                stop()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // Top Bar (extracted component)
        EditorTopBar {
            Layout.fillWidth: true
            editorBridge: root.editorBridge
            refPlayer: root.player
        }

        // Preview Row: Video + VU Meter
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 180
            spacing: 8

            // Video preview
            Rectangle {
                id: videoPreview
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: HorusStyle.colors.bgElevated
                radius: 10
                clip: true

                WebEngineView {
                    id: ytPreview
                    anchors.centerIn: parent
                    width: parent.width - 2
                    height: Math.min(parent.height - 2, (parent.width - 2) * 9 / 16)
                    visible: editorBridge.videoSourceType === "youtube" && editorBridge.videoSource !== ""
                    audioMuted: currentPhase === "record"
                    settings.playbackRequiresUserGesture: false
                    settings.javascriptEnabled: true
                    settings.localContentCanAccessRemoteUrls: true

                    Component.onCompleted: {
                        if (editorBridge.videoSourceType === "youtube" && editorBridge.videoSource)
                            loadYouTube(editorBridge.videoSource)
                    }

                    Connections {
                        target: root.editorBridge
                        function onVideoSourceChanged() {
                            if (root.editorBridge.videoSourceType === "youtube" && root.editorBridge.videoSource)
                                ytPreview.loadYouTube(root.editorBridge.videoSource)
                        }
                    }

                    function loadYouTube(embedUrl) {
                        let vid = embedUrl
                        if (vid.indexOf("/embed/") >= 0) {
                            vid = vid.split("/embed/")[1]
                            if (vid.indexOf("?") >= 0) vid = vid.split("?")[0]
                        }
                        let html = '<!DOCTYPE html><html><head><meta charset="utf-8">' +
                            '<style>*{margin:0;padding:0;overflow:hidden;background:transparent}' +
                            'html,body{width:100%;height:100%;background:transparent}' +
                            'iframe{position:absolute;top:0;left:0;width:100%;height:100%;border:0}</style></head>' +
                            '<body><iframe id="ytplayer" src="https://www.youtube-nocookie.com/embed/' + vid +
                            '?rel=0&modestbranding=1&enablejsapi=1" ' +
                            'allow="accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture" ' +
                            'allowfullscreen></iframe></body></html>'
                        loadHtml(html, "https://www.youtube-nocookie.com")
                    }

                    function ytPlay() {
                        runJavaScript("try{document.getElementById('ytplayer').contentWindow.postMessage(JSON.stringify({event:'command',func:'playVideo',args:''}),'*')}catch(e){}")
                    }
                    function ytPause() {
                        runJavaScript("try{document.getElementById('ytplayer').contentWindow.postMessage(JSON.stringify({event:'command',func:'pauseVideo',args:''}),'*')}catch(e){}")
                    }
                    function ytSeek(seconds) {
                        runJavaScript("try{document.getElementById('ytplayer').contentWindow.postMessage(JSON.stringify({event:'command',func:'seekTo',args:[" + seconds + ",true]}),'*')}catch(e){}")
                    }
                }

                // Empty state
                Label {
                    anchors.centerIn: parent
                    visible: editorBridge.videoSource === ""
                    text: "No video loaded"
                    font.family: "Inter"
                    font.pixelSize: 13
                    color: HorusStyle.colors.textGhost
                }

                // MUTED badge during recording
                Rectangle {
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.margins: 6
                    visible: currentPhase === "record" && editorBridge.videoSource !== ""
                    width: mutedLabel.implicitWidth + 10
                    height: 18
                    radius: 4
                    color: Qt.rgba(1, 0.27, 0.17, 0.8)
                    z: 1

                    Label {
                        id: mutedLabel
                        anchors.centerIn: parent
                        text: "MUTED"
                        font.family: "JetBrains Mono"
                        font.pixelSize: 8
                        font.bold: true
                        color: HorusStyle.colors.textPrimary
                    }
                }
            }

            // VU Meter
            Rectangle {
                Layout.preferredWidth: 40
                Layout.fillHeight: true
                color: HorusStyle.colors.bgElevated
                radius: 10

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 6
                    spacing: 4

                    Label {
                        text: "MIC"
                        font.family: "JetBrains Mono"
                        font.pixelSize: 9
                        color: HorusStyle.colors.textSubtle
                        Layout.alignment: Qt.AlignHCenter
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: HorusStyle.colors.bgInput
                        radius: 4

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: parent.height * editorBridge.micLevel
                            radius: 4
                            color: editorBridge.micLevel > 0.8
                                ? HorusStyle.colors.accentRed
                                : editorBridge.micLevel > 0.5
                                    ? HorusStyle.colors.accentYellow
                                    : HorusStyle.colors.accentGreen

                            Behavior on height {
                                NumberAnimation { duration: 50 }
                            }
                        }
                    }

                    Label {
                        text: (editorBridge.micLevel * 100).toFixed(0) + "%"
                        font.family: "JetBrains Mono"
                        font.pixelSize: 9
                        color: HorusStyle.colors.textGhost
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }
        }

        // 2-Track Timeline
        Timeline {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 160
            editorBridge: root.editorBridge
            refPlayer: root.player
            selectedSegment: root.selectedSegment
            onSegmentClicked: (idx) => { root.selectedSegment = idx }
        }

        // Transport Controls (extracted component)
        TransportControls {
            Layout.fillWidth: true
            editorBridge: root.editorBridge
            refPlayer: root.player
            loopEnabled: root.loopEnabled
            onLoopToggled: (enabled) => {
                root.loopEnabled = enabled
                if (!enabled) {
                    editorBridge.clearIOPoints()
                    editorBridge.setPhase("browse")
                } else {
                    editorBridge.setPhase("set_io")
                }
            }
        }

        // Recording Error Banner
        Label {
            id: errorLabel
            visible: false
            Layout.fillWidth: true
            text: ""
            font.family: "Inter"
            font.pixelSize: 12
            color: HorusStyle.colors.accentRed
            horizontalAlignment: Text.AlignHCenter
            padding: 6
            background: Rectangle {
                color: Qt.rgba(1, 0.27, 0.17, 0.1)
                radius: 8
                border.color: HorusStyle.colors.accentRed
                border.width: 1
            }
        }
    }

    // Countdown Overlay
    Rectangle {
        id: countdownOverlay
        anchors.fill: parent
        z: 100
        visible: editorBridge.countdownValue >= 0
        color: Qt.rgba(0, 0, 0, 0.85)

        Label {
            id: countdownLabel
            anchors.centerIn: parent
            text: editorBridge.countdownValue > 0 ? editorBridge.countdownValue : "GO!"
            font.family: "Inter"
            font.pixelSize: 120
            font.bold: true
            color: editorBridge.countdownValue > 0
                ? HorusStyle.colors.textPrimary
                : HorusStyle.colors.accentGreen

            transform: Scale {
                id: countdownScale
                origin.x: countdownLabel.width / 2
                origin.y: countdownLabel.height / 2
                xScale: 1.0
                yScale: 1.0
            }

            Connections {
                target: root.editorBridge
                function onCountdownValueChanged() {
                    if (root.editorBridge.countdownValue >= 0) {
                        countdownScaleAnim.restart()
                    }
                }
            }

            SequentialAnimation {
                id: countdownScaleAnim
                PropertyAction { target: countdownScale; property: "xScale"; value: 1.5 }
                PropertyAction { target: countdownScale; property: "yScale"; value: 1.5 }
                ParallelAnimation {
                    NumberAnimation { target: countdownScale; property: "xScale"; to: 1.0; duration: 300; easing.type: Easing.OutBack }
                    NumberAnimation { target: countdownScale; property: "yScale"; to: 1.0; duration: 300; easing.type: Easing.OutBack }
                }
            }
        }

        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: countdownLabel.bottom
            anchors.topMargin: 20
            text: "Get ready to record..."
            font.family: "Inter"
            font.pixelSize: 18
            color: HorusStyle.colors.textMuted
            visible: editorBridge.countdownValue > 0
        }
    }
}
