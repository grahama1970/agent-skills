"""Embry Textual theme — CLI Developer surface mapping of canonical tokens.

Maps Embry design system tokens (from distance.css / embry-design-system.css)
to Textual CSS. This is the FIRST Embry-themed Textual TUI, establishing
the pattern for all future CLI skills.

Design compliance:
  P1: Every color maps to a semantic token. No decorative color.
  P2: Color never the sole differentiator. Paired with [PASS]/[WARN]/[FAIL] text.
  P5: All elements keyboard-completable.
  P6: No blinking or animation.
"""

# Canonical Embry token values (from distance.css + embry-design-system.css)
EMBRY_BG = "#141414"
EMBRY_SURFACE = "#171717"
EMBRY_ELEVATED = "#262626"
EMBRY_TEXT_PRIMARY = "#ffffff"
EMBRY_TEXT_SECONDARY = "#e0e0e0"
EMBRY_TEXT_MUTED = "#808080"  # rgba(255,255,255,0.53) approximated for ANSI
EMBRY_ACCENT = "#4a9eff"
EMBRY_STATUS_OK = "#22c55e"
EMBRY_STATUS_WARNING = "#eab308"
EMBRY_STATUS_CRITICAL = "#ef4444"
EMBRY_STATUS_INFO = "#3b82f6"
EMBRY_BORDER = "#333333"  # rgba(255,255,255,0.13) approximated

EMBRY_TCSS = """
Screen {
    background: #141414;
}

/* Surface hierarchy */
.card {
    background: #171717;
    border: solid #333333;
    padding: 1;
}
.elevated {
    background: #262626;
    border: solid #333333;
    padding: 1;
}

/* Status badge colors — P2: always paired with [PASS]/[WARN]/[FAIL] text */
.status-pass {
    color: #22c55e;
}
.status-warn {
    color: #eab308;
}
.status-fail {
    color: #ef4444;
}
.status-info {
    color: #3b82f6;
}

/* Accent for selection/focus */
.selected {
    background: #1a3a5c;
    border: solid #4a9eff;
}

/* Text hierarchy */
.text-primary {
    color: #ffffff;
}
.text-secondary {
    color: #e0e0e0;
}
.text-muted {
    color: #808080;
}

/* Header bar */
.header-bar {
    background: #4a9eff;
    color: #ffffff;
    text-style: bold;
    padding: 0 2;
    height: 1;
}

/* Footer hint bar */
.hint-bar {
    background: #171717;
    color: #808080;
    height: 1;
    padding: 0 1;
}

/* Chat panel */
.chat-panel {
    background: #171717;
    border-left: solid #333333;
    padding: 1;
}

.chat-input {
    background: #262626;
    color: #ffffff;
    border: solid #333333;
}

.chat-input:focus {
    border: solid #4a9eff;
}

/* Assessment detail lines */
.assess-pass {
    color: #22c55e;
}
.assess-warn {
    color: #eab308;
}
.assess-fail {
    color: #ef4444;
}
"""
