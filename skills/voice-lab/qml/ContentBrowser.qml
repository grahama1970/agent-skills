import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Slide-out content browser drawer (550px wide, full editor height).
// Three source tabs: YouTube, Movies, TV Shows.
// Emits contentSelected(url, sourceType, title) when user picks content.
Item {
    id: browser
    property bool isOpen: false

    signal contentSelected(string url, string sourceType, string title)

    // --- Scrim (click to close) ---
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.4)
        visible: browser.isOpen
        opacity: browser.isOpen ? 1.0 : 0.0

        Behavior on opacity {
            NumberAnimation { duration: 200 }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: browser.isOpen = false
        }
    }

    // --- Drawer panel ---
    Rectangle {
        id: drawer
        width: 550
        height: parent.height
        color: HorusStyle.colors.bg
        x: browser.isOpen ? 0 : -width

        Behavior on x {
            NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
        }

        // Right border
        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: HorusStyle.colors.border
        }

        ColumnLayout {
            id: drawerContent
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12

            // --- Header ---
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Label {
                    text: "Find Content"
                    font.family: "Inter"
                    font.pixelSize: 18
                    font.bold: true
                    color: HorusStyle.colors.textPrimary
                    Layout.fillWidth: true
                }

                Button {
                    implicitWidth: 32
                    implicitHeight: 32
                    onClicked: browser.isOpen = false
                    background: Rectangle {
                        color: parent.hovered ? HorusStyle.colors.bgHover : "transparent"
                        radius: 6
                    }
                    contentItem: Icon {
                        source: "icons/x.svg"
                        size: 16
                        opacity: 0.53
                    }
                }
            }

            // --- Search bar ---
            Rectangle {
                Layout.fillWidth: true
                height: HorusStyle.layout.searchBarHeight
                color: HorusStyle.colors.bgInput
                radius: 10
                border.color: searchField.activeFocus ? HorusStyle.colors.borderFocused : HorusStyle.colors.border
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 8

                    Icon {
                        source: "icons/search.svg"
                        size: 16
                        opacity: 0.27
                    }

                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        placeholderText: drawerContent.activeTab === 0 ? "Paste YouTube URL..." : "Search movies, shows..."
                        placeholderTextColor: HorusStyle.colors.textPlaceholder
                        color: HorusStyle.colors.textPrimary
                        font.family: "Inter"
                        font.pixelSize: 15
                        background: null
                        selectByMouse: true

                        onTextChanged: {
                            if (drawerContent.activeTab > 0) {
                                searchDebounce.restart()
                            }
                        }
                    }

                    // Loading spinner
                    BusyIndicator {
                        visible: contentProvider.isSearching
                        implicitWidth: 20
                        implicitHeight: 20
                    }
                }
            }

            // --- Tab bar ---
            property int activeTab: 0  // 0=YouTube, 1=Movies, 2=TV

            RowLayout {
                Layout.fillWidth: true
                spacing: 4

                Repeater {
                    model: [
                        { label: "YouTube", idx: 0 },
                        { label: "Movies", idx: 1 },
                        { label: "TV Shows", idx: 2 }
                    ]
                    Rectangle {
                        width: tabLabel.implicitWidth + 24
                        height: 32
                        radius: 8
                        color: drawerContent.activeTab === modelData.idx
                            ? HorusStyle.colors.accent
                            : HorusStyle.colors.bgInput

                        Label {
                            id: tabLabel
                            anchors.centerIn: parent
                            text: modelData.label
                            font.family: "Inter"
                            font.pixelSize: 13
                            font.bold: drawerContent.activeTab === modelData.idx
                            color: drawerContent.activeTab === modelData.idx
                                ? HorusStyle.colors.textOnAccent : HorusStyle.colors.textMuted
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                drawerContent.activeTab = modelData.idx
                                searchField.text = ""
                                tvDrilldown.visible = false
                                // Auto-load recent for Movies/TV when switching tabs
                                if (modelData.idx === 1) {
                                    contentProvider.search("", "Movie")
                                } else if (modelData.idx === 2) {
                                    contentProvider.search("", "Series")
                                }
                            }
                        }
                    }
                }
            }

            // --- Debounce timer for search ---
            Timer {
                id: searchDebounce
                interval: 300
                onTriggered: {
                    let q = searchField.text
                    if (drawerContent.activeTab === 1) {
                        contentProvider.search(q, "Movie")
                    } else if (drawerContent.activeTab === 2) {
                        tvDrilldown.visible = false
                        contentProvider.search(q, "Series")
                    }
                }
            }

            // --- YouTube tab content ---
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: drawerContent.activeTab === 0
                spacing: 12

                Label {
                    text: "Paste a YouTube embed or watch URL"
                    font.family: "Inter"
                    font.pixelSize: 13
                    color: HorusStyle.colors.textMuted
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    // The search field doubles as the URL field for YouTube tab
                    Button {
                        text: "Load"
                        enabled: {
                            let url = searchField.text.toLowerCase()
                            return url.indexOf("youtube.com") >= 0 || url.indexOf("youtu.be") >= 0
                        }
                        onClicked: {
                            let url = searchField.text.trim()
                            let vid = ""
                            // Extract video ID from any YouTube URL format
                            if (url.indexOf("/watch?v=") >= 0) {
                                vid = url.split("v=")[1]
                                if (vid.indexOf("&") >= 0) vid = vid.split("&")[0]
                            } else if (url.indexOf("youtu.be/") >= 0) {
                                vid = url.split("youtu.be/")[1]
                                if (vid.indexOf("?") >= 0) vid = vid.split("?")[0]
                                if (vid.indexOf("\\") >= 0) vid = vid.split("\\")[0]
                            } else if (url.indexOf("/embed/") >= 0) {
                                vid = url.split("/embed/")[1]
                                if (vid.indexOf("?") >= 0) vid = vid.split("?")[0]
                            }
                            // Build embed URL with enablejsapi for proper playback
                            if (vid) {
                                url = "https://www.youtube.com/embed/" + vid + "?enablejsapi=1&origin=null"
                            }
                            browser.contentSelected(url, "youtube", "YouTube")
                        }
                        background: Rectangle {
                            color: parent.enabled
                                ? (parent.hovered ? HorusStyle.colors.accent : Qt.darker(HorusStyle.colors.accent, 1.3))
                                : HorusStyle.colors.bgInput
                            radius: 8
                        }
                        contentItem: Text {
                            text: parent.text
                            font.family: "Inter"
                            font.pixelSize: 14
                            font.bold: true
                            color: parent.parent.enabled ? HorusStyle.colors.textOnAccent : HorusStyle.colors.textGhost
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        implicitWidth: 80
                        implicitHeight: 36
                    }
                }

                // Quick tip
                Label {
                    Layout.fillWidth: true
                    text: "Supports youtube.com/watch?v=... and youtu.be/... URLs.\nThey will be converted to embed format automatically."
                    font.family: "Inter"
                    font.pixelSize: 12
                    color: HorusStyle.colors.textGhost
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }
            }

            // --- Movies tab content ---
            ListView {
                id: movieList
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: drawerContent.activeTab === 1
                model: contentProvider.searchModel
                clip: true
                spacing: 2

                delegate: ContentResultCard {
                    width: movieList.width
                    title: model.title
                    year: model.year
                    runtime: model.runtime
                    genres: model.genres
                    thumbnailUrl: model.thumbnailUrl
                    seasonEpisode: ""
                    onSelected: {
                        browser.contentSelected(model.filePath, "local", model.title)
                    }
                }

                // Empty state
                Label {
                    anchors.centerIn: parent
                    visible: movieList.count === 0 && !contentProvider.isSearching
                    text: searchField.text ? "No movies found" : "Type to search movies"
                    font.family: "Inter"
                    font.pixelSize: 14
                    color: HorusStyle.colors.textGhost
                }
            }

            // --- TV tab content ---
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: drawerContent.activeTab === 2

                // Series list
                ListView {
                    id: seriesList
                    anchors.fill: parent
                    visible: !tvDrilldown.visible
                    model: contentProvider.searchModel
                    clip: true
                    spacing: 2

                    delegate: ContentResultCard {
                        width: seriesList.width
                        title: model.title
                        year: model.year
                        runtime: model.runtime
                        genres: model.genres
                        thumbnailUrl: model.thumbnailUrl
                        seasonEpisode: ""
                        onSelected: {
                            tvDrilldown.seriesTitle = model.title
                            contentProvider.loadEpisodes(model.jellyfinId)
                            tvDrilldown.visible = true
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        visible: seriesList.count === 0 && !contentProvider.isSearching
                        text: searchField.text ? "No shows found" : "Type to search TV shows"
                        font.family: "Inter"
                        font.pixelSize: 14
                        color: HorusStyle.colors.textGhost
                    }
                }

                // Episode drill-down
                ColumnLayout {
                    id: tvDrilldown
                    anchors.fill: parent
                    visible: false
                    spacing: 8

                    property string seriesTitle: ""

                    // Back button + series title
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            implicitWidth: 32
                            implicitHeight: 32
                            onClicked: tvDrilldown.visible = false
                            background: Rectangle {
                                color: parent.hovered ? HorusStyle.colors.bgHover : "transparent"
                                radius: 6
                            }
                            contentItem: Icon {
                                source: "icons/arrow-left.svg"
                                size: 18
                            }
                        }

                        Label {
                            text: tvDrilldown.seriesTitle
                            font.family: "Inter"
                            font.pixelSize: 16
                            font.bold: true
                            color: HorusStyle.colors.textPrimary
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    // Episode list grouped by season
                    ListView {
                        id: episodeList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: contentProvider.episodeModel
                        clip: true
                        spacing: 2

                        // Track current season for headers
                        property string lastSeason: ""

                        delegate: Column {
                            width: episodeList.width
                            spacing: 0

                            // Season header (shown when episode number is E01 or first item)
                            Rectangle {
                                width: parent.width
                                height: visible ? 32 : 0
                                visible: model.index === 0 || model.seasonEpisode.substring(4, 6) === "01"
                                color: "transparent"

                                Label {
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 4
                                    text: {
                                        let ep = model.seasonEpisode
                                        if (ep.length >= 3) {
                                            let num = parseInt(ep.substring(1, 3))
                                            return "Season " + num
                                        }
                                        return "Episodes"
                                    }
                                    font.family: "Inter"
                                    font.pixelSize: HorusStyle.text.sectionSize
                                    font.weight: HorusStyle.text.sectionWeight
                                    font.capitalization: Font.AllUppercase
                                    color: HorusStyle.colors.textSubtle
                                }
                            }

                            // Episode row
                            Rectangle {
                                width: parent.width
                                height: 44
                                color: epMouse.containsMouse ? HorusStyle.colors.bgHover : "transparent"
                                radius: 6

                                Behavior on color {
                                    ColorAnimation { duration: HorusStyle.anim.instant }
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    spacing: 10

                                    // Episode badge
                                    Rectangle {
                                        width: epBadge.implicitWidth + 10
                                        height: 20
                                        radius: 4
                                        color: HorusStyle.colors.badge

                                        Label {
                                            id: epBadge
                                            anchors.centerIn: parent
                                            text: model.seasonEpisode
                                            font.family: "JetBrains Mono"
                                            font.pixelSize: 10
                                            font.bold: true
                                            color: HorusStyle.colors.accent
                                        }
                                    }

                                    Label {
                                        text: model.title
                                        font.family: "Inter"
                                        font.pixelSize: 13
                                        color: HorusStyle.colors.textPrimary
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }

                                    Label {
                                        text: model.runtime
                                        font.family: "JetBrains Mono"
                                        font.pixelSize: 11
                                        color: HorusStyle.colors.textGhost
                                    }
                                }

                                MouseArea {
                                    id: epMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        let displayTitle = tvDrilldown.seriesTitle + " " + model.seasonEpisode + " - " + model.title
                                        browser.contentSelected(model.filePath, "local", displayTitle)
                                    }
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: episodeList.count === 0 && !contentProvider.isSearching
                            text: "Loading episodes..."
                            font.family: "Inter"
                            font.pixelSize: 14
                            color: HorusStyle.colors.textGhost
                        }
                    }
                }
            }
        }
    }
}
