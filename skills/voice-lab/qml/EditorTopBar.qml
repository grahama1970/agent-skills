import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import "."

// Editor top bar: title, recording indicator, takes dropdown, save button.
// Extracted from Editor.qml — requires editorBridge and refPlayer from parent scope.

RowLayout {
    id: topBar

    required property var editorBridge
    required property var refPlayer

    height: 36
    spacing: 12

    function formatTime(seconds) {
        let m = Math.floor(seconds / 60)
        let s = Math.floor(seconds % 60)
        return "%1:%2".arg(m).arg(String(s).padStart(2, '0'))
    }

    Label {
        text: "Voice Lab"
        font.family: "Inter"
        font.pixelSize: 16
        font.bold: true
        color: HorusStyle.colors.textPrimary
    }

    Label {
        text: "\u00B7"
        font.pixelSize: 16
        color: HorusStyle.colors.textGhost
    }

    Label {
        text: editorBridge.videoTitle || "No track loaded"
        font.family: "Inter"
        font.pixelSize: 14
        color: HorusStyle.colors.textMuted
        elide: Text.ElideRight
        Layout.fillWidth: true
    }

    Label {
        visible: refPlayer.duration > 0
        text: topBar.formatTime(refPlayer.duration / 1000)
        font.family: "JetBrains Mono"
        font.pixelSize: 13
        color: HorusStyle.colors.textMuted
    }

    Item { Layout.fillWidth: true }

    // Recording indicator
    Rectangle {
        width: 10; height: 10; radius: 5
        color: editorBridge.isRecording ? HorusStyle.colors.accentGreen : HorusStyle.colors.textSubtle

        SequentialAnimation on opacity {
            running: editorBridge.isRecording
            loops: Animation.Infinite
            NumberAnimation { to: 0.3; duration: HorusStyle.anim.breathe }
            NumberAnimation { to: 1.0; duration: HorusStyle.anim.breathe }
        }
    }
    Label {
        text: editorBridge.isRecording ? "REC" : ""
        font.family: "JetBrains Mono"
        font.pixelSize: 11
        color: HorusStyle.colors.accentGreen
    }

    // Takes dropdown
    ComboBox {
        id: takesCombo
        visible: editorBridge.takeList.length > 0
        enabled: !editorBridge.isRecording
        model: editorBridge.takeList
        implicitWidth: 160

        Connections {
            target: topBar.editorBridge
            function onTakeListChanged() {
                if (topBar.editorBridge.takeList.length > 0)
                    takesCombo.currentIndex = topBar.editorBridge.takeList.length - 1
            }
        }

        onActivated: (index) => {
            if (!editorBridge.isRecording)
                editorBridge.loadTake(index)
        }

        background: Rectangle {
            color: takesCombo.hovered ? HorusStyle.colors.bgHover : HorusStyle.colors.bgElevated
            radius: 6
            border.color: HorusStyle.colors.border
            border.width: 1
            opacity: takesCombo.enabled ? 1.0 : 0.4
        }
        contentItem: Text {
            leftPadding: 8
            rightPadding: takesCombo.indicator.width + 8
            text: takesCombo.displayText
            font.family: "JetBrains Mono"
            font.pixelSize: 11
            color: HorusStyle.colors.textPrimary
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            opacity: takesCombo.enabled ? 1.0 : 0.4
        }
        indicator: Text {
            x: takesCombo.width - width - 8
            y: (takesCombo.height - height) / 2
            text: "\u25BE"  // down triangle
            font.pixelSize: 12
            color: HorusStyle.colors.textMuted
        }
        popup: Popup {
            y: takesCombo.height
            width: takesCombo.width
            implicitHeight: Math.min(contentItem.implicitHeight, 300)
            padding: 1

            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: takesCombo.popup.visible ? takesCombo.delegateModel : null
                currentIndex: takesCombo.highlightedIndex
            }

            background: Rectangle {
                color: HorusStyle.colors.bgElevated
                radius: 6
                border.color: HorusStyle.colors.border
                border.width: 1
            }
        }
        delegate: ItemDelegate {
            width: takesCombo.width
            contentItem: Text {
                text: modelData
                font.family: "JetBrains Mono"
                font.pixelSize: 11
                color: highlighted ? HorusStyle.colors.accent : HorusStyle.colors.textPrimary
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            highlighted: takesCombo.highlightedIndex === index
            background: Rectangle {
                color: highlighted ? Qt.rgba(0.29, 0.62, 1.0, 0.15) : "transparent"
            }
        }
    }

    Button {
        text: "Save"
        font.family: "Inter"
        font.pixelSize: 13
        onClicked: editorBridge.saveAlignment("")
        background: Rectangle {
            color: parent.hovered ? HorusStyle.colors.bgHover : HorusStyle.colors.bgElevated
            radius: 6
            border.color: HorusStyle.colors.border
            border.width: 1
        }
        contentItem: Text {
            text: parent.text
            color: HorusStyle.colors.textPrimary
            font: parent.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
}
