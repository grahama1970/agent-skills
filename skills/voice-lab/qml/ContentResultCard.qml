import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "."

// Result delegate: thumbnail + title + year/runtime/genres
// Used by ContentBrowser for movie and TV series search results.
Item {
    id: card
    width: parent ? parent.width : 200
    height: 72

    required property string title
    required property string year
    required property string runtime
    required property string genres
    required property string thumbnailUrl
    required property string seasonEpisode

    signal selected()

    Rectangle {
        anchors.fill: parent
        color: mouseArea.containsMouse ? HorusStyle.colors.bgHover : "transparent"
        radius: 8

        Behavior on color {
            ColorAnimation { duration: HorusStyle.anim.instant }
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 12

            // Thumbnail
            Rectangle {
                Layout.preferredWidth: 90
                Layout.preferredHeight: 56
                radius: 6
                color: HorusStyle.colors.bgInput
                clip: true

                Image {
                    id: thumb
                    anchors.fill: parent
                    source: card.thumbnailUrl
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    visible: status === Image.Ready
                }

                // Fallback icon when thumbnail fails or is loading
                Icon {
                    anchors.centerIn: parent
                    visible: thumb.status !== Image.Ready
                    source: card.seasonEpisode ? "icons/tv.svg" : "icons/film.svg"
                    size: 24
                    opacity: 0.27
                }

                // Season/episode badge overlay
                Rectangle {
                    visible: card.seasonEpisode !== ""
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.margins: 3
                    width: epLabel.implicitWidth + 8
                    height: 16
                    radius: 3
                    color: Qt.rgba(0, 0, 0, 0.7)

                    Label {
                        id: epLabel
                        anchors.centerIn: parent
                        text: card.seasonEpisode
                        font.family: "JetBrains Mono"
                        font.pixelSize: 9
                        font.bold: true
                        color: HorusStyle.colors.accent
                    }
                }
            }

            // Text column
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 2

                // Title
                Label {
                    Layout.fillWidth: true
                    text: card.title
                    font.family: "Inter"
                    font.pixelSize: HorusStyle.text.resultTitleSize
                    font.weight: HorusStyle.text.resultTitleWeight
                    color: HorusStyle.colors.textPrimary
                    elide: Text.ElideRight
                    maximumLineCount: 1
                }

                // Subtitle: year + runtime + genres
                Label {
                    Layout.fillWidth: true
                    text: {
                        let parts = []
                        if (card.year) parts.push(card.year)
                        if (card.runtime) parts.push(card.runtime)
                        if (card.genres) parts.push(card.genres)
                        return parts.join(" \u00B7 ")
                    }
                    font.family: "Inter"
                    font.pixelSize: HorusStyle.text.resultDescSize
                    color: HorusStyle.colors.textMuted
                    elide: Text.ElideRight
                    maximumLineCount: 1
                }
            }
        }

        MouseArea {
            id: mouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: card.selected()
        }
    }
}
