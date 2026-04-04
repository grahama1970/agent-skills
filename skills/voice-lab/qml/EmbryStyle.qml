pragma Singleton
import QtQuick

// Embry Design System — ported from embry-design-system.css
// Usage: import "." ; then reference EmbryStyle.colors.bg, etc.
// Scale: Ctrl+= / Ctrl+- in any lab app (persisted via QML Settings)
QtObject {
    id: _root

    // ── Global Scale Factor ────────────────────────────────
    property real scaleFactor: 1.0
    function scaleUp()   { scaleFactor = Math.min(scaleFactor + 0.1, 2.5) }
    function scaleDown() { scaleFactor = Math.max(scaleFactor - 0.1, 0.8) }
    function scaleReset(){ scaleFactor = 1.0 }
    function _s(base)    { return Math.round(base * _root.scaleFactor) }

    // ── Color Palette (NVIS-compliant per MIL-STD-3009) ──────
    readonly property QtObject colors: QtObject {
        readonly property color transparent:     "transparent"

        // Backgrounds — NVIS: ultra-dark to preserve night vision
        readonly property color bg:              "#080a0c"
        readonly property color bgOverlay:       "#e6080a0c"   // rgba(8,10,12,0.9)
        readonly property color bgElevated:      "#121416"
        readonly property color bgInput:         "#181a1c"
        readonly property color bgHover:         "#1a1c1e"
        readonly property color bgPressed:       "#282a2c"

        // Selection / highlight
        readonly property color selectBg:        "#18c8c8c8"   // ~9% dimmed white
        readonly property color selectHoverBg:   "#0cc8c8c8"   // ~5% dimmed white
        readonly property color selectBorder:    "#44aaff"      // NVIS blue
        readonly property color selectGlow:      "#44aaff"      // NVIS blue

        // Accent colors — NVIS palette
        readonly property color accent:          "#44aaff"      // NVIS blue (C_BLUE)
        readonly property color accentGreen:     "#00ff88"      // NVIS green (C_GREEN)
        readonly property color accentYellow:    "#ffe600"      // NVIS yellow (C_YELLOW)
        readonly property color accentRed:       "#ff4444"      // NVIS red (C_RED)
        readonly property color accentAmber:     "#ffaa00"      // NVIS amber (C_AMBER)

        // Accent backgrounds — dimmed for NVIS
        readonly property color accentGreenBg:   "#2600ff88"    // ~15% accentGreen
        readonly property color accentRedBg:     "#26ff4444"    // ~15% accentRed
        readonly property color accentBlueBg:    "#2644aaff"    // ~15% accent (blue)

        // Semantic status — aligned to NVIS
        readonly property color statusOk:        "#00ff88"      // NVIS green
        readonly property color statusWarning:   "#ffaa00"      // NVIS amber
        readonly property color statusCritical:  "#ff4444"      // NVIS red
        readonly property color statusInfo:      "#44aaff"      // NVIS blue
        readonly property color statusNodata:    "#505050"      // NVIS dim (C_DIM)

        // Status backgrounds — dimmed for NVIS
        readonly property color statusOkBg:      "#2600ff88"    // ~15% statusOk
        readonly property color statusInfoBg:    "#2644aaff"    // ~15% statusInfo
        readonly property color statusWarningBg: "#26ffaa00"    // ~15% statusWarning
        readonly property color statusCriticalBg:"#26ff4444"    // ~15% statusCritical

        // Status chart accents
        readonly property color statusOkLine:    "#4d00ff88"    // ~30% statusOk
        readonly property color statusOkText:    "#8000ff88"    // ~50% statusOk

        // Text — NVIS: dimmed white, never pure white
        readonly property color textPrimary:     "#c8c8c8"      // NVIS white (C_WHITE)
        readonly property color textSecondary:   "#b0b0b0"
        readonly property color textMuted:       "#88c8c8c8"    // ~53% NVIS white
        readonly property color textSubtle:      "#55c8c8c8"    // ~33% NVIS white
        readonly property color textGhost:       "#44c8c8c8"    // ~27% NVIS white
        readonly property color textPlaceholder: "#99c8c8c8"    // ~60% NVIS white
        readonly property color textDisabled:    "#33c8c8c8"    // ~20% NVIS white

        // Borders & separators
        readonly property color border:          "#22c8c8c8"    // ~13% NVIS white
        readonly property color borderFocused:   "#44aaff"      // NVIS blue
        readonly property color borderInput:     "#1e2022"
        readonly property color separator:       "#15c8c8c8"    // ~8% NVIS white
        readonly property color separatorStrong: "#1ac8c8c8"    // ~10% NVIS white

        // Subtle row highlights
        readonly property color rowAlt:          "#05c8c8c8"    // ~2% NVIS white

        // Badge / chip backgrounds
        readonly property color badge:           "#18c8c8c8"    // ~9% NVIS white
        readonly property color badgeSubtle:     "#12c8c8c8"    // ~7% NVIS white
        readonly property color badgeHover:      "#22c8c8c8"
    }

    // ── Typography ──────────────────────────────────────────
    readonly property QtObject text: QtObject {
        readonly property string fontFamily:     "Inter"
        readonly property string monoFamily:     "JetBrains Mono"

        property int xs:                Math.round(10 * _root.scaleFactor)
        property int sm:                Math.round(11 * _root.scaleFactor)
        property int base:              Math.round(14 * _root.scaleFactor)
        property int lg:                Math.round(20 * _root.scaleFactor)
        property int xl:                Math.round(24 * _root.scaleFactor)
        property int xxl:               Math.round(32 * _root.scaleFactor)

        readonly property int weightNormal:      400
        readonly property int weightMedium:      500
        readonly property int weightSemibold:    600
        readonly property int weightBold:        700
    }

    // ── Spacing & Layout ────────────────────────────────────
    readonly property QtObject layout: QtObject {
        property int space1:            Math.round(4  * _root.scaleFactor)
        property int space2:            Math.round(8  * _root.scaleFactor)
        property int space3:            Math.round(12 * _root.scaleFactor)
        property int space4:            Math.round(16 * _root.scaleFactor)
        property int space6:            Math.round(24 * _root.scaleFactor)
        property int space8:            Math.round(32 * _root.scaleFactor)

        property int radiusSm:          Math.round(4  * _root.scaleFactor)
        property int radiusMd:          Math.round(8  * _root.scaleFactor)
        property int radiusLg:          Math.round(12 * _root.scaleFactor)
        property int radiusXl:          Math.round(16 * _root.scaleFactor)

        property int windowWidth:       Math.round(1200 * _root.scaleFactor)
        property int windowHeight:      Math.round(700 * _root.scaleFactor)
        readonly property real windowRadius:     14

        property int badgeHeight:       Math.round(22 * _root.scaleFactor)
        property int badgePadding:      Math.round(6  * _root.scaleFactor)
        property int badgeRadius:       Math.round(4  * _root.scaleFactor)

        readonly property real focusRingWidth:   2
    }

    // ── Animation Timing (ms) ───────────────────────────────
    readonly property QtObject anim: QtObject {
        readonly property int instant:           80
        readonly property int fast:              100
        readonly property int snap:              120
        readonly property int pulse:             400
        readonly property int breathe:           600
        readonly property int gentle:            1000
    }

    // ── Icon Constants ───────────────────────────────────────
    readonly property QtObject icons: QtObject {
        readonly property string remove:        "\u2715"   // ✕
        readonly property string chevronRight:  "\u25B8"   // ▸
        readonly property string checkmark:     "\u2713"   // ✓
        readonly property string star:          "\u2605"   // ★
        readonly property string forbidden:     "\u26D4"   // ⛔
        readonly property string flash:         "\u26A1"   // ⚡
        readonly property string arrowRight:    "\u2192"   // →
        readonly property string arrowDown:     "\u2B07"   // ⬇
        readonly property string prevPage:      "\u25C0"   // ◀
        readonly property string nextPage:      "\u25B6"   // ▶
        readonly property string undo:          "\u21A9"   // ↩
        readonly property string redo:          "\u21AA"   // ↪
    }

    // ── Shadow & Effects ────────────────────────────────────
    readonly property QtObject shadow: QtObject {
        readonly property real panelBlur:        40.0
        readonly property real panelOpacity:     0.55
        readonly property real panelYOffset:     20
        readonly property real glowBlur:         16.0
        readonly property real glowOpacity:      0.5
    }
}
