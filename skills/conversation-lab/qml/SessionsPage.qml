import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root

    // ── Properties ──────────────────────────────────────────
    property var bridge: null
    property var sessions: bridge ? JSON.parse(bridge.sessionsJson) : []
    property string filterGrade: ""
    property string filterDifficulty: ""

    property var filteredSessions: {
        var result = sessions;
        if (filterGrade) {
            result = result.filter(function(s) {
                return (s.grade || "") === filterGrade;
            });
        }
        if (filterDifficulty) {
            result = result.filter(function(s) {
                return (s.difficulty || "") === filterDifficulty;
            });
        }
        return result;
    }

    // ── Layout ──────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: EmbryStyle.layout.space4
        spacing: EmbryStyle.layout.space3

        // ── Filter Row ───────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: EmbryStyle.layout.space3

            Text {
                text: "Sessions (" + filteredSessions.length + ")"
                font.pixelSize: EmbryStyle.text.base
                font.weight: Font.SemiBold
                color: EmbryStyle.colors.textPrimary
            }

            Item { Layout.fillWidth: true }

            // Grade filter
            Text {
                text: "Grade:"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textMuted
            }

            EmbryComboBox {
                id: gradeFilter

                Layout.preferredWidth: 80
                model: ["All", "A", "B", "C", "F"]
                onCurrentTextChanged: root.filterGrade = currentText === "All" ? "" : currentText

                Accessible.name: "Filter by grade"
            }

            // Difficulty filter
            Text {
                text: "Difficulty:"
                font.pixelSize: EmbryStyle.text.sm
                color: EmbryStyle.colors.textMuted
            }

            EmbryComboBox {
                id: difficultyFilter

                Layout.preferredWidth: 100
                model: ["All", "easy", "medium", "hard"]
                onCurrentTextChanged: root.filterDifficulty = currentText === "All" ? "" : currentText

                Accessible.name: "Filter by difficulty"
            }
        }

        // ── Column Headers ───────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 28

            color: EmbryStyle.colors.bgElevated
            radius: EmbryStyle.layout.radiusSm

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: EmbryStyle.layout.space2
                anchors.rightMargin: EmbryStyle.layout.space2
                spacing: EmbryStyle.layout.space2

                Text { Layout.preferredWidth: 100; text: "Persona"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                Text { Layout.preferredWidth: 60; text: "Difficulty"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                Text { Layout.preferredWidth: 40; text: "Grade"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignHCenter }
                Text { Layout.preferredWidth: 60; text: "Composite"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignRight }
                Text { Layout.preferredWidth: 70; text: "Resolution"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                Text { Layout.preferredWidth: 40; text: "Turns"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignHCenter }
                Text { Layout.preferredWidth: 40; text: "QRAs"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignHCenter }
                Text { Layout.fillWidth: true; text: "Issues"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted }
                Text { Layout.preferredWidth: 50; text: "Rerun?"; font.pixelSize: EmbryStyle.text.xs; font.weight: Font.Bold; color: EmbryStyle.colors.textMuted; horizontalAlignment: Text.AlignHCenter }
            }
        }

        // ── Session List ─────────────────────────────────────
        ListView {
            id: sessionsList

            Layout.fillWidth: true
            Layout.fillHeight: true

            clip: true
            model: filteredSessions
            spacing: 1

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: sessionsList.width
                height: 32

                radius: 2
                color: index % 2 === 0 ? EmbryStyle.colors.bgElevated : "transparent"

                property string grade: modelData.grade || "?"
                property color gradeColor: {
                    if (grade === "A") return EmbryStyle.colors.statusOk;
                    if (grade === "B") return EmbryStyle.colors.accentGreen;
                    if (grade === "C") return EmbryStyle.colors.statusWarning;
                    if (grade === "F") return EmbryStyle.colors.statusCritical;
                    return EmbryStyle.colors.textMuted;
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: EmbryStyle.layout.space2
                    anchors.rightMargin: EmbryStyle.layout.space2
                    spacing: EmbryStyle.layout.space2

                    // Persona
                    Text {
                        Layout.preferredWidth: 100
                        text: modelData.persona || "—"
                        font.pixelSize: EmbryStyle.text.sm
                        color: EmbryStyle.colors.textPrimary
                        elide: Text.ElideRight
                    }

                    // Difficulty
                    Text {
                        Layout.preferredWidth: 60
                        text: modelData.difficulty || "—"
                        font.pixelSize: EmbryStyle.text.xs
                        color: EmbryStyle.colors.textMuted
                    }

                    // Grade badge
                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 22

                        radius: EmbryStyle.layout.badgeRadius
                        color: Qt.rgba(gradeColor.r, gradeColor.g, gradeColor.b, 0.15)

                        Text {
                            anchors.centerIn: parent
                            text: grade
                            font.pixelSize: EmbryStyle.text.sm
                            font.weight: Font.Bold
                            color: gradeColor
                        }
                    }

                    // Composite score
                    Text {
                        Layout.preferredWidth: 60
                        text: modelData.composite !== undefined ? modelData.composite.toFixed(3) : "—"
                        font.pixelSize: EmbryStyle.text.sm
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textSecondary
                        horizontalAlignment: Text.AlignRight
                    }

                    // Resolution
                    Text {
                        Layout.preferredWidth: 70
                        text: modelData.resolution || "—"
                        font.pixelSize: EmbryStyle.text.xs
                        color: modelData.resolution === "full" ? EmbryStyle.colors.statusOk
                             : modelData.resolution === "partial" ? EmbryStyle.colors.statusWarning
                             : EmbryStyle.colors.textMuted
                    }

                    // Turns
                    Text {
                        Layout.preferredWidth: 40
                        text: modelData.turns !== undefined ? modelData.turns : "—"
                        font.pixelSize: EmbryStyle.text.sm
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textSecondary
                        horizontalAlignment: Text.AlignHCenter
                    }

                    // QRAs cited
                    Text {
                        Layout.preferredWidth: 40
                        text: modelData.qras_cited !== undefined ? modelData.qras_cited : "—"
                        font.pixelSize: EmbryStyle.text.sm
                        font.family: EmbryStyle.text.monoFamily
                        color: modelData.qras_cited === 0 ? EmbryStyle.colors.statusCritical : EmbryStyle.colors.textSecondary
                        horizontalAlignment: Text.AlignHCenter
                    }

                    // Issues
                    Text {
                        Layout.fillWidth: true
                        text: (modelData.issues || []).join(", ")
                        font.pixelSize: EmbryStyle.text.xs
                        font.family: EmbryStyle.text.monoFamily
                        color: EmbryStyle.colors.textMuted
                        elide: Text.ElideRight
                    }

                    // Rerun eligible
                    Rectangle {
                        Layout.preferredWidth: 50
                        Layout.preferredHeight: 18

                        visible: modelData.rerun_eligible || false
                        radius: 9
                        color: EmbryStyle.colors.statusWarningBg

                        Text {
                            anchors.centerIn: parent
                            text: "RERUN"
                            font.pixelSize: 9
                            font.weight: Font.Bold
                            color: EmbryStyle.colors.statusWarning
                        }
                    }
                }

                Accessible.name: (modelData.persona || "Unknown") + " session, grade " + grade + ", composite " + (modelData.composite || 0).toFixed(3)
                Accessible.role: Accessible.ListItem
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                text: "No sessions loaded"
                font.pixelSize: EmbryStyle.text.base
                color: EmbryStyle.colors.textMuted
                visible: sessionsList.count === 0
            }
        }
    }
}
