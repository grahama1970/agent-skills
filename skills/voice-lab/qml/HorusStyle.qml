pragma Singleton
import QtQuick

// HorusStyle — alias layer forwarding to EmbryStyle.
// Editor sub-components reference HorusStyle.colors.*, HorusStyle.anim.*, etc.
// Rather than mass-renaming 100+ references, this forwards everything.
// Extra properties that EmbryStyle lacks are kept here for backward compat.
QtObject {

    // Forward colors, anim, shadow directly from EmbryStyle
    readonly property QtObject colors: EmbryStyle.colors
    readonly property QtObject anim: EmbryStyle.anim
    readonly property QtObject shadow: EmbryStyle.shadow

    // ── Typography (HorusStyle-specific naming) ───────────────
    // Editor sub-components reference these; EmbryStyle uses different names.
    readonly property QtObject text: QtObject {
        // Search bar
        readonly property int searchSize:        20
        readonly property int searchWeight:      Font.Normal

        // Section headers
        readonly property int sectionSize:       11
        readonly property int sectionWeight:     Font.Medium

        // Result items
        readonly property int resultTitleSize:   14
        readonly property int resultTitleWeight: Font.DemiBold
        readonly property int resultDescSize:    13
        readonly property int resultDescWeight:  Font.Normal
        readonly property int resultTypeSize:    12

        // Body / chat
        readonly property int bodySize:          14

        // Badges & labels
        readonly property int badgeSize:         11
        readonly property int badgeWeight:       Font.Medium
        readonly property int hintSize:          12
        readonly property int shortcutSize:      10

        // Empty state
        readonly property int emptySize:         14

        // Icons (emoji fallback sizes)
        readonly property int iconLarge:         24
        readonly property int iconMedium:        20
        readonly property int iconSmall:         14
        readonly property int iconMicro:         12
    }

    // ── Spacing & Layout (HorusStyle-specific naming) ─────────
    readonly property QtObject layout: QtObject {
        // Window
        readonly property int windowWidth:       680
        readonly property int windowHeight:      460
        readonly property real windowRadius:     14

        // Panel margins
        readonly property int panelMargin:       16
        readonly property int panelMarginSmall:  12

        // Search bar
        readonly property int searchBarHeight:   52
        readonly property int searchTopPadding:  8

        // Result items
        readonly property int resultHeight:      44
        readonly property int resultIconWidth:   28
        readonly property int resultTitleMax:    280
        readonly property int resultPadding:     10
        readonly property int resultSpacing:     10

        // Skill cards
        readonly property int skillCardHeight:   56

        // Bottom action bar
        readonly property int actionBarHeight:   32

        // Audio recording bar
        readonly property int recordingBarHeight: 28

        // Badge dimensions
        readonly property int badgeHeight:       22
        readonly property int badgePadding:      6
        readonly property int badgeRadius:       4
        readonly property int shortcutHeight:    18
        readonly property int shortcutRadius:    3

        // General
        readonly property int separatorHeight:   1
        readonly property real statusDotSize:    6
    }
}
