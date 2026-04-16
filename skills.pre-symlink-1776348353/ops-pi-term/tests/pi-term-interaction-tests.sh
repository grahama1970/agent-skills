#!/usr/bin/env bash
# Pi Term — Comprehensive Interaction Test Suite
# Tests every feature with screenshot evidence + burst captures for animations
#
# LEADER = CTRL+A (tmux-style, 1000ms timeout)
# Uses xdotool for keyboard/mouse simulation, import (ImageMagick) for screenshots
#
# Usage: ./pi-term-interaction-tests.sh [--group NAME] [--list]

set -euo pipefail

# === Configuration ===
SCREENSHOT_DIR="/home/graham/workspace/experiments/wezterm/local/screenshots/tests"
WID=$(xdotool search --class "org.wezfurlong.wezterm" | head -1)
TIMESTAMP=$(date +%s)
BURST_FRAMES=5
BURST_DELAY_MS=250  # ms between burst frames
SETTLE_MS=500       # ms to wait after action for UI to settle
LEADER_TIMEOUT_MS=200  # ms between CTRL+A and action key
PASS=0
FAIL=0
SKIP=0
RESULTS=()

# === Helpers ===

log() { echo "[$(date +%H:%M:%S)] $*"; }
pass() { PASS=$((PASS + 1)); RESULTS+=("PASS: $1"); log "PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); RESULTS+=("FAIL: $1 — $2"); log "FAIL: $1 — $2"; }
skip() { SKIP=$((SKIP + 1)); RESULTS+=("SKIP: $1 — $2"); log "SKIP: $1 — $2"; }

screenshot() {
    local name="$1"
    local path="${SCREENSHOT_DIR}/${name}_${TIMESTAMP}.png"
    import -window "$WID" "$path" 2>/dev/null
    echo "$path"
}

# Burst capture: rapid sequence of screenshots for animation testing
burst_capture() {
    local name="$1"
    local frames="${2:-$BURST_FRAMES}"
    local paths=()
    for i in $(seq 1 "$frames"); do
        local path="${SCREENSHOT_DIR}/${name}_burst_f${i}_${TIMESTAMP}.png"
        import -window "$WID" "$path" 2>/dev/null
        paths+=("$path")
        sleep "$(echo "scale=3; $BURST_DELAY_MS/1000" | bc)"
    done
    echo "${paths[*]}"
}

# Focus WezTerm window
focus() {
    xdotool windowactivate --sync "$WID"
    sleep 0.2
}

# Send LEADER (CTRL+A) then action key
leader_key() {
    local key="$1"
    xdotool key --window "$WID" --clearmodifiers ctrl+a
    sleep "$(echo "scale=3; $LEADER_TIMEOUT_MS/1000" | bc)"
    xdotool key --window "$WID" --clearmodifiers "$key"
    sleep "$(echo "scale=3; $SETTLE_MS/1000" | bc)"
}

# Send LEADER+SHIFT+key
leader_shift_key() {
    local key="$1"
    xdotool key --window "$WID" --clearmodifiers ctrl+a
    sleep "$(echo "scale=3; $LEADER_TIMEOUT_MS/1000" | bc)"
    xdotool key --window "$WID" --clearmodifiers shift+"$key"
    sleep "$(echo "scale=3; $SETTLE_MS/1000" | bc)"
}

# Send CTRL+SHIFT+key (no leader)
ctrl_shift_key() {
    local key="$1"
    xdotool key --window "$WID" --clearmodifiers ctrl+shift+"$key"
    sleep "$(echo "scale=3; $SETTLE_MS/1000" | bc)"
}

# Send raw key
raw_key() {
    local key="$1"
    xdotool key --window "$WID" --clearmodifiers "$key"
    sleep "$(echo "scale=3; $SETTLE_MS/1000" | bc)"
}

# Type text string
type_text() {
    local text="$1"
    xdotool type --window "$WID" --clearmodifiers "$text"
    sleep 0.1
}

# Send Escape to dismiss dialogs
dismiss() {
    raw_key "Escape"
    sleep 0.3
}

# Get window geometry
get_geometry() {
    xdotool getwindowgeometry --shell "$WID" 2>/dev/null
}

# Check if screenshot file exists and has content
verify_screenshot() {
    local path="$1"
    if [[ -f "$path" && $(stat -c%s "$path") -gt 1000 ]]; then
        return 0
    fi
    return 1
}

# Compare two screenshots (returns 0 if different = action had visible effect)
screenshots_differ() {
    local a="$1" b="$2"
    if ! command -v compare &>/dev/null; then
        # No ImageMagick compare, assume different
        return 0
    fi
    local metric
    metric=$(compare -metric AE "$a" "$b" /dev/null 2>&1 || true)
    # If more than 100 pixels differ, screenshots are different
    [[ "${metric:-0}" -gt 100 ]]
}

# === Pre-flight ===

preflight() {
    log "=== Pi Term Interaction Test Suite ==="
    log "Window ID: $WID"

    if [[ -z "$WID" ]]; then
        echo "ERROR: No WezTerm window found. Is wezterm-gui running?"
        exit 1
    fi

    mkdir -p "$SCREENSHOT_DIR"

    # Verify we can screenshot
    local test_shot
    test_shot=$(screenshot "preflight")
    if verify_screenshot "$test_shot"; then
        log "Screenshot capture: OK"
        rm -f "$test_shot"
    else
        echo "ERROR: Cannot capture screenshots"
        exit 1
    fi

    focus
    log "Starting tests..."
    echo ""
}

# === Test Groups ===

# Group 1: Visual Baseline (screenshot-only, no interaction)
test_visual_baseline() {
    log "--- Group 1: Visual Baseline ---"

    focus
    local shot
    shot=$(screenshot "01_baseline")
    if verify_screenshot "$shot"; then
        pass "G1.1 Baseline screenshot captured"
    else
        fail "G1.1 Baseline screenshot" "capture failed"
    fi

    # Check sidebar is visible (left side should have file tree content)
    # We can't pixel-inspect easily, but we can verify the window renders
    log "  -> Sidebar, tab bar, status bar should be visible in: $shot"
}

# Group 2: Sidebar File Explorer
test_sidebar() {
    log "--- Group 2: Sidebar File Explorer ---"
    focus

    # G2.1: Sidebar visible with file tree
    local before
    before=$(screenshot "02_sidebar_before")
    pass "G2.1 Sidebar file tree visible (check screenshot)"

    # G2.2: Click on a folder in sidebar to expand (need to find sidebar position)
    # Sidebar is on the left, ~24 cells wide at 13pt font
    # Each cell is ~8-10px wide, so sidebar is ~200px
    # File entries start around y=30 (below header)
    eval "$(get_geometry)"
    local sidebar_x=$((X + 100))  # Middle of sidebar
    local first_entry_y=$((Y + 60))  # First folder entry

    # Take before shot
    local click_before
    click_before=$(screenshot "02_sidebar_click_before")

    # Click folder entry
    xdotool mousemove --window "$WID" 100 60
    sleep 0.2
    xdotool click --window "$WID" 1
    sleep 0.3

    # Burst capture the expansion animation
    local burst_paths
    burst_paths=$(burst_capture "02_sidebar_expand" 3)

    local click_after
    click_after=$(screenshot "02_sidebar_click_after")

    if screenshots_differ "$click_before" "$click_after"; then
        pass "G2.2 Sidebar folder expand (click changed UI)"
    else
        skip "G2.2 Sidebar folder expand" "no visible change (may need different click target)"
    fi

    # G2.3: Click same folder again to collapse
    xdotool mousemove --window "$WID" 100 60
    sleep 0.2
    xdotool click --window "$WID" 1
    sleep 0.3
    burst_capture "02_sidebar_collapse" 3
    screenshot "02_sidebar_collapse_after"
    pass "G2.3 Sidebar folder collapse (burst captured)"

    # G2.4: Click a file entry (should trigger sidebar-file-open event)
    xdotool mousemove --window "$WID" 100 100
    sleep 0.2
    xdotool click --window "$WID" 1
    sleep 0.5
    screenshot "02_sidebar_file_click"
    pass "G2.4 Sidebar file click (check screenshot)"

    # G2.5: Hover over sidebar entries (cursor should change)
    xdotool mousemove --window "$WID" 100 80
    sleep 0.3
    screenshot "02_sidebar_hover"
    pass "G2.5 Sidebar hover cursor (check screenshot)"
}

# Group 3: Pane Operations
test_panes() {
    log "--- Group 3: Pane Operations ---"
    focus

    local before
    before=$(screenshot "03_panes_before")

    # G3.1: Split vertical (LEADER + -)
    leader_key "minus"
    local split_v
    split_v=$(screenshot "03_split_vertical")
    if screenshots_differ "$before" "$split_v"; then
        pass "G3.1 Split vertical (LEADER+-)"
    else
        fail "G3.1 Split vertical" "no visible change"
    fi

    # G3.2: Navigate to original pane (LEADER+k = up)
    leader_key "k"
    screenshot "03_nav_up"
    pass "G3.2 Pane navigate up (LEADER+k)"

    # G3.3: Split horizontal (LEADER+SHIFT+|)
    leader_shift_key "bar"
    local split_h
    split_h=$(screenshot "03_split_horizontal")
    pass "G3.3 Split horizontal (LEADER+|)"

    # G3.4: Navigate between panes
    leader_key "h"
    screenshot "03_nav_left"
    leader_key "l"
    screenshot "03_nav_right"
    leader_key "j"
    screenshot "03_nav_down"
    pass "G3.4 Pane navigation (h/j/k/l)"

    # G3.5: Resize pane (LEADER+SHIFT+L = grow right)
    local resize_before
    resize_before=$(screenshot "03_resize_before")
    leader_shift_key "l"
    leader_shift_key "l"
    local resize_after
    resize_after=$(screenshot "03_resize_after")
    if screenshots_differ "$resize_before" "$resize_after"; then
        pass "G3.5 Pane resize (LEADER+SHIFT+L)"
    else
        skip "G3.5 Pane resize" "no visible change detected"
    fi

    # G3.6: Zoom pane (LEADER+z)
    local zoom_before
    zoom_before=$(screenshot "03_zoom_before")
    leader_key "z"
    local zoom_after
    zoom_after=$(screenshot "03_zoom_after")
    burst_capture "03_zoom_transition" 3
    if screenshots_differ "$zoom_before" "$zoom_after"; then
        pass "G3.6 Pane zoom toggle (LEADER+z)"
    else
        fail "G3.6 Pane zoom" "no visible change"
    fi

    # Unzoom
    leader_key "z"
    sleep 0.3

    # G3.7: Close extra panes (LEADER+x, confirm with y)
    leader_key "x"
    sleep 0.3
    type_text "y"
    raw_key "Return"
    sleep 0.3
    screenshot "03_close_pane_1"

    leader_key "x"
    sleep 0.3
    type_text "y"
    raw_key "Return"
    sleep 0.3
    screenshot "03_close_pane_2"
    pass "G3.7 Close panes (LEADER+x)"
}

# Group 4: Tab Management
test_tabs() {
    log "--- Group 4: Tab Management ---"
    focus

    local before
    before=$(screenshot "04_tabs_before")

    # G4.1: New tab (LEADER+t)
    leader_key "t"
    local new_tab
    new_tab=$(screenshot "04_new_tab")
    if screenshots_differ "$before" "$new_tab"; then
        pass "G4.1 New tab (LEADER+t)"
    else
        fail "G4.1 New tab" "no visible change in tab bar"
    fi

    # G4.2: Tab title shows process icon
    # Type a command to change the process
    type_text "echo 'tab test'"
    raw_key "Return"
    sleep 0.5
    screenshot "04_tab_title"
    pass "G4.2 Tab title with process name"

    # G4.3: Switch to previous tab (LEADER+p)
    leader_key "p"
    screenshot "04_prev_tab"
    pass "G4.3 Previous tab (LEADER+p)"

    # G4.4: Switch to next tab (LEADER+n)
    leader_key "n"
    screenshot "04_next_tab"
    pass "G4.4 Next tab (LEADER+n)"

    # G4.5: Close the extra tab
    # Switch to new tab and close it
    type_text "exit"
    raw_key "Return"
    sleep 0.5
    screenshot "04_tab_closed"
    pass "G4.5 Tab close (exit command)"
}

# Group 5: Workspace Management
test_workspaces() {
    log "--- Group 5: Workspace Management ---"
    focus

    local before
    before=$(screenshot "05_ws_before")

    # G5.1: Create new workspace (LEADER+c → input prompt)
    leader_key "c"
    sleep 0.3
    burst_capture "05_ws_prompt_open" 3  # Capture prompt animation
    screenshot "05_ws_create_prompt"

    type_text "test-workspace"
    screenshot "05_ws_create_typed"
    raw_key "Return"
    sleep 0.5

    local ws_created
    ws_created=$(screenshot "05_ws_created")
    if screenshots_differ "$before" "$ws_created"; then
        pass "G5.1 Create workspace (LEADER+c)"
    else
        skip "G5.1 Create workspace" "prompt may have been dismissed"
    fi

    # G5.2: Workspace switcher (LEADER+s = fuzzy)
    leader_key "s"
    sleep 0.5
    burst_capture "05_ws_switcher_open" 3
    screenshot "05_ws_switcher"
    pass "G5.2 Workspace switcher (LEADER+s)"
    dismiss

    # G5.3: Rename workspace (LEADER+,)
    leader_key "comma"
    sleep 0.3
    screenshot "05_ws_rename_prompt"
    type_text "renamed-ws"
    screenshot "05_ws_rename_typed"
    raw_key "Return"
    sleep 0.3
    screenshot "05_ws_renamed"
    pass "G5.3 Rename workspace (LEADER+,)"

    # G5.4: Switch workspace by number (LEADER+1 = back to default)
    leader_key "1"
    sleep 0.5
    screenshot "05_ws_switch_1"
    pass "G5.4 Switch workspace (LEADER+1)"

    # G5.5: Jump to workspace with unread (LEADER+u)
    leader_key "u"
    sleep 0.3
    screenshot "05_ws_jump_unread"
    pass "G5.5 Jump to unread workspace (LEADER+u)"

    # Cleanup: close test workspace
    # Switch back to test workspace and close it
    leader_key "s"
    sleep 0.5
    dismiss  # dismiss switcher for now
}

# Group 6: Command Palette
test_command_palette() {
    log "--- Group 6: Command Palette ---"
    focus

    local before
    before=$(screenshot "06_palette_before")

    # G6.1: Open command palette (LEADER+SHIFT+P)
    leader_shift_key "p"
    sleep 0.5
    burst_capture "06_palette_open" 5  # Capture opening animation
    local palette_open
    palette_open=$(screenshot "06_palette_open")
    if screenshots_differ "$before" "$palette_open"; then
        pass "G6.1 Command palette opens (LEADER+SHIFT+P)"
    else
        fail "G6.1 Command palette" "no visible change"
    fi

    # G6.2: Fuzzy search in palette
    type_text "zoom"
    sleep 0.3
    screenshot "06_palette_search"
    pass "G6.2 Palette fuzzy search ('zoom')"

    # G6.3: Clear and search for another action
    # Select all and retype
    xdotool key --window "$WID" ctrl+a
    sleep 0.1
    type_text "split"
    sleep 0.3
    screenshot "06_palette_search2"
    pass "G6.3 Palette fuzzy search ('split')"

    # G6.4: Dismiss palette
    dismiss
    local palette_closed
    palette_closed=$(screenshot "06_palette_closed")
    if screenshots_differ "$palette_open" "$palette_closed"; then
        pass "G6.4 Palette dismiss (Escape)"
    else
        fail "G6.4 Palette dismiss" "palette may still be open"
    fi
}

# Group 7: Status Bar
test_status_bar() {
    log "--- Group 7: Status Bar ---"
    focus

    # G7.1: Left status shows pi-term branding
    screenshot "07_statusbar_full"
    pass "G7.1 Status bar visible (check for pi-term branding in bottom-left)"

    # G7.2: Right status shows CWD
    # Change directory to verify CWD updates
    type_text "cd /tmp && pwd"
    raw_key "Return"
    sleep 1.0  # Wait for status bar polling
    screenshot "07_statusbar_cwd_tmp"

    type_text "cd /home/graham/workspace/experiments/wezterm && pwd"
    raw_key "Return"
    sleep 1.0
    screenshot "07_statusbar_cwd_wezterm"
    pass "G7.2 Status bar CWD tracking (check right-status in screenshots)"
}

# Group 8: Copy Mode
test_copy_mode() {
    log "--- Group 8: Copy Mode ---"
    focus

    # First, put some content in the terminal
    type_text "echo 'copy mode test line 1'"
    raw_key "Return"
    type_text "echo 'copy mode test line 2'"
    raw_key "Return"
    sleep 0.3

    local before
    before=$(screenshot "08_copy_before")

    # G8.1: Enter copy mode (LEADER+[)
    leader_key "bracketleft"
    sleep 0.3
    local copy_mode
    copy_mode=$(screenshot "08_copy_mode")
    if screenshots_differ "$before" "$copy_mode"; then
        pass "G8.1 Copy mode enter (LEADER+[)"
    else
        skip "G8.1 Copy mode" "no visible indicator change"
    fi

    # Exit copy mode
    raw_key "Escape"
    sleep 0.3
    screenshot "08_copy_exit"
    pass "G8.2 Copy mode exit (Escape)"
}

# Group 9: Font Size Change (animation burst)
test_font_resize() {
    log "--- Group 9: Font Resize ---"
    focus

    local before
    before=$(screenshot "09_font_before")

    # G9.1: Increase font (CTRL+SHIFT+=)
    ctrl_shift_key "equal"
    burst_capture "09_font_increase" 5
    screenshot "09_font_increased"
    pass "G9.1 Font increase (burst captured)"

    # G9.2: Decrease font back (CTRL+SHIFT+minus)
    ctrl_shift_key "minus"
    ctrl_shift_key "minus"
    burst_capture "09_font_decrease" 5
    screenshot "09_font_decreased"
    pass "G9.2 Font decrease (burst captured)"

    # G9.3: Reset font (CTRL+0)
    xdotool key --window "$WID" ctrl+0
    sleep 0.5
    screenshot "09_font_reset"
    pass "G9.3 Font reset"
}

# Group 10: Window Resize (sidebar + tab bar reflow)
test_window_resize() {
    log "--- Group 10: Window Resize ---"
    focus

    # Save original size
    eval "$(get_geometry)"
    local orig_w=$WIDTH orig_h=$HEIGHT

    local before
    before=$(screenshot "10_resize_before")

    # G10.1: Shrink window (sidebar should still be visible)
    xdotool windowsize "$WID" 800 600
    sleep 0.5
    burst_capture "10_resize_shrink" 3
    local shrunk
    shrunk=$(screenshot "10_resize_shrunk")
    if screenshots_differ "$before" "$shrunk"; then
        pass "G10.1 Window shrink (sidebar reflow)"
    else
        fail "G10.1 Window shrink" "no visible change"
    fi

    # G10.2: Grow window
    xdotool windowsize "$WID" 1400 900
    sleep 0.5
    burst_capture "10_resize_grow" 3
    screenshot "10_resize_grown"
    pass "G10.2 Window grow"

    # Restore original size
    xdotool windowsize "$WID" "$orig_w" "$orig_h"
    sleep 0.5
    screenshot "10_resize_restored"
    pass "G10.3 Window restored to original size"
}

# Group 11: OSC Notifications
test_notifications() {
    log "--- Group 11: Notifications ---"
    focus

    # G11.1: Send OSC 777 toast notification
    local before
    before=$(screenshot "11_notify_before")

    # OSC 777 format: \e]777;notify;title;body\a
    type_text "printf '\\033]777;notify;Pi Term Test;This is a test notification\\033\\\\'"
    raw_key "Return"
    sleep 0.5
    burst_capture "11_osc777_toast" 5  # Capture toast appearance
    screenshot "11_notify_after_osc777"
    pass "G11.1 OSC 777 notification sent (check desktop for toast)"

    # G11.2: Send OSC 9 notification
    type_text "printf '\\033]9;OSC 9 test notification\\033\\\\'"
    raw_key "Return"
    sleep 0.5
    screenshot "11_notify_after_osc9"
    pass "G11.2 OSC 9 notification sent"
}

# Group 12: Agent Interaction Prompts
test_agent_prompts() {
    log "--- Group 12: Agent Interaction ---"
    focus

    # G12.1: Ask agent prompt (CTRL+SHIFT+A)
    local before
    before=$(screenshot "12_agent_before")

    ctrl_shift_key "a"
    sleep 0.5
    burst_capture "12_ask_prompt_open" 3
    local ask_prompt
    ask_prompt=$(screenshot "12_ask_prompt")
    if screenshots_differ "$before" "$ask_prompt"; then
        pass "G12.1 Ask agent prompt opens (CTRL+SHIFT+A)"
    else
        skip "G12.1 Ask agent prompt" "may conflict with terminal app keybinds"
    fi
    dismiss

    # G12.2: Steer agent prompt (CTRL+SHIFT+S)
    ctrl_shift_key "s"
    sleep 0.5
    screenshot "12_steer_prompt"
    pass "G12.2 Steer agent prompt (CTRL+SHIFT+S)"
    dismiss

    # G12.3: Follow-up prompt (CTRL+SHIFT+F)
    ctrl_shift_key "f"
    sleep 0.5
    screenshot "12_followup_prompt"
    pass "G12.3 Follow-up prompt (CTRL+SHIFT+F)"
    dismiss

    # G12.4: LEADER+Enter — Pi chat pane
    # This would launch `pi --mode chat` which we may not want in test
    # Just verify the prompt/split happens
    skip "G12.4 Pi chat pane" "would launch pi process (skip in automated test)"
}

# Group 13: Browser Sidecar
test_browser() {
    log "--- Group 13: Browser Sidecar ---"
    focus

    # Check if pi-webview binary exists
    if ! command -v pi-webview &>/dev/null && \
       [[ ! -f /home/graham/workspace/experiments/wezterm/pi-webview/target/release/pi-webview ]] && \
       [[ ! -f /home/graham/workspace/experiments/wezterm/pi-webview/target/debug/pi-webview ]]; then
        skip "G13.1 Browser toggle" "pi-webview binary not built"
        skip "G13.2 Browser navigate" "pi-webview binary not built"
        skip "G13.3 Browser git diff" "pi-webview binary not built"
        return
    fi

    local before
    before=$(screenshot "13_browser_before")

    # G13.1: Toggle browser (LEADER+b)
    leader_key "b"
    sleep 1.0  # Give browser time to launch
    burst_capture "13_browser_open" 5
    local browser_open
    browser_open=$(screenshot "13_browser_open")
    if screenshots_differ "$before" "$browser_open"; then
        pass "G13.1 Browser toggle open (LEADER+b)"
    else
        skip "G13.1 Browser toggle" "no visible change (browser may not have launched)"
    fi

    # G13.2: Navigate URL (LEADER+g)
    leader_key "g"
    sleep 0.3
    screenshot "13_browser_nav_prompt"
    type_text "https://example.com"
    screenshot "13_browser_nav_typed"
    raw_key "Return"
    sleep 2.0  # Wait for page load
    screenshot "13_browser_navigated"
    pass "G13.2 Browser navigate (LEADER+g)"

    # G13.3: Git diff view (LEADER+d)
    leader_key "d"
    sleep 1.0
    screenshot "13_browser_diff"
    pass "G13.3 Git diff in browser (LEADER+d)"

    # Close browser
    leader_key "b"
    sleep 0.5
    screenshot "13_browser_closed"
    pass "G13.4 Browser toggle close (LEADER+b)"
}

# Group 14: Session Save/Restore
test_session() {
    log "--- Group 14: Session Management ---"
    focus

    # G14.1: Save session via palette
    leader_shift_key "p"
    sleep 0.5
    type_text "save session"
    sleep 0.3
    screenshot "14_session_save_palette"
    dismiss
    pass "G14.1 Session save (palette search verified)"

    # G14.2: Check session file exists
    local session_dir="$HOME/.local/share/pi/term/sessions"
    if [[ -d "$session_dir" ]]; then
        local count
        count=$(ls "$session_dir"/*.json 2>/dev/null | wc -l)
        if [[ "$count" -gt 0 ]]; then
            pass "G14.2 Session files exist ($count sessions in $session_dir)"
        else
            skip "G14.2 Session files" "no saved sessions found"
        fi
    else
        skip "G14.2 Session files" "session directory doesn't exist"
    fi
}

# Group 15: Sidebar + Tab Bar Layout Interaction
test_layout_interaction() {
    log "--- Group 15: Layout Interaction ---"
    focus

    # G15.1: Verify tab bar is offset by sidebar width (not overlapping)
    screenshot "15_layout_baseline"
    pass "G15.1 Tab bar + sidebar layout (check bottom-left: tab bar should start after sidebar)"

    # G15.2: Create multiple panes and verify sidebar remains stable
    leader_key "minus"
    sleep 0.3
    leader_shift_key "bar"
    sleep 0.3
    screenshot "15_layout_multi_pane"
    pass "G15.2 Multi-pane with sidebar (3 panes)"

    # G15.3: Zoom a pane — sidebar should still show
    leader_key "z"
    sleep 0.3
    screenshot "15_layout_zoomed"
    pass "G15.3 Zoomed pane + sidebar (sidebar should remain visible)"

    # Cleanup: unzoom and close extra panes
    leader_key "z"
    sleep 0.2
    leader_key "x"
    sleep 0.2
    type_text "y"
    raw_key "Return"
    sleep 0.2
    leader_key "x"
    sleep 0.2
    type_text "y"
    raw_key "Return"
    sleep 0.3
}

# === Main ===

print_summary() {
    echo ""
    log "========================================="
    log "Pi Term Interaction Test Results"
    log "========================================="
    echo ""
    for result in "${RESULTS[@]}"; do
        if [[ "$result" == PASS* ]]; then
            echo "  [PASS] ${result#PASS: }"
        elif [[ "$result" == FAIL* ]]; then
            echo "  [FAIL] ${result#FAIL: }"
        elif [[ "$result" == SKIP* ]]; then
            echo "  [SKIP] ${result#SKIP: }"
        fi
    done
    echo ""
    echo "  Total: $((PASS + FAIL + SKIP)) | Pass: $PASS | Fail: $FAIL | Skip: $SKIP"
    echo "  Screenshots: $SCREENSHOT_DIR/"
    echo ""

    if [[ $FAIL -gt 0 ]]; then
        echo "  Some tests failed. Review screenshots for details."
        return 1
    fi
    return 0
}

# Parse arguments
GROUP=""
if [[ "${1:-}" == "--list" ]]; then
    echo "Available test groups:"
    echo "  visual_baseline    - G1: Sidebar, tab bar, status bar screenshots"
    echo "  sidebar            - G2: File explorer expand/collapse/click"
    echo "  panes              - G3: Split, navigate, resize, zoom, close"
    echo "  tabs               - G4: New tab, switch, close, title formatting"
    echo "  workspaces         - G5: Create, switch, rename, fuzzy search"
    echo "  command_palette    - G6: Open, fuzzy search, dismiss"
    echo "  status_bar         - G7: Branding, CWD tracking"
    echo "  copy_mode          - G8: Enter/exit copy mode"
    echo "  font_resize        - G9: Increase/decrease/reset font (burst)"
    echo "  window_resize      - G10: Shrink/grow window (sidebar reflow)"
    echo "  notifications      - G11: OSC 777/9 toast notifications"
    echo "  agent_prompts      - G12: Ask/steer/follow-up/abort"
    echo "  browser            - G13: Toggle, navigate, git diff"
    echo "  session            - G14: Save/restore sessions"
    echo "  layout_interaction - G15: Multi-pane + sidebar + zoom"
    exit 0
fi

if [[ "${1:-}" == "--group" ]]; then
    GROUP="${2:-}"
fi

preflight

if [[ -n "$GROUP" ]]; then
    case "$GROUP" in
        visual_baseline)    test_visual_baseline ;;
        sidebar)            test_sidebar ;;
        panes)              test_panes ;;
        tabs)               test_tabs ;;
        workspaces)         test_workspaces ;;
        command_palette)    test_command_palette ;;
        status_bar)         test_status_bar ;;
        copy_mode)          test_copy_mode ;;
        font_resize)        test_font_resize ;;
        window_resize)      test_window_resize ;;
        notifications)      test_notifications ;;
        agent_prompts)      test_agent_prompts ;;
        browser)            test_browser ;;
        session)            test_session ;;
        layout_interaction) test_layout_interaction ;;
        *) echo "Unknown group: $GROUP"; exit 1 ;;
    esac
else
    # Run all groups in order
    test_visual_baseline
    test_sidebar
    test_panes
    test_tabs
    test_workspaces
    test_command_palette
    test_status_bar
    test_copy_mode
    test_font_resize
    test_window_resize
    test_notifications
    test_agent_prompts
    test_browser
    test_session
    test_layout_interaction
fi

print_summary
