#!/usr/bin/env bash
# Blind adversarial tests for sidebar explorer overhaul (09_TASKS)
# The coding agent NEVER sees this file — only pass/fail output.
set -euo pipefail

WEZTERM_DIR="/home/graham/workspace/experiments/wezterm"
PI_MONO_DIR="/home/graham/workspace/experiments/pi-mono/packages/wezterm"
PASS=0
FAIL=0
RESULTS=()

check() {
    local id="$1" desc="$2"
    shift 2
    if "$@" >/dev/null 2>&1; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

check_grep() {
    local id="$1" desc="$2" pattern="$3" file="$4"
    if grep -qE "$pattern" "$file" 2>/dev/null; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

check_not_grep() {
    local id="$1" desc="$2" pattern="$3" file="$4"
    if ! grep -qE "$pattern" "$file" 2>/dev/null; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Sidebar Explorer Blind Tests ==="

# --- Task 1: Branding ---
check_grep "T1.1" "status-bar.lua uses pi symbol" \
    "π-term" "$PI_MONO_DIR/lua/embry/status-bar.lua"

check_grep "T1.2" "fancy_tab_bar.rs has pi-term branding" \
    "\\\\u\{03C0\}|π-term" "$WEZTERM_DIR/wezterm-gui/src/termwindow/render/fancy_tab_bar.rs"

check_grep "T1.3" "fancy_tab_bar.rs skips default LeftStatus" \
    "Skip.*default.*left.status|LeftStatus.*=>.*\{" "$WEZTERM_DIR/wezterm-gui/src/termwindow/render/fancy_tab_bar.rs"

check_not_grep "T1.4" "status-bar.lua does not use old pi-term text" \
    '"[ ]*pi-term[ ]*"' "$PI_MONO_DIR/lua/embry/status-bar.lua"

# --- Task 2: Project root detection ---
check_grep "T2.1" "sidebar_state.rs has find_project_root function" \
    "fn find_project_root|pub fn find_project_root" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T2.2" "sidebar_state.rs checks .git marker" \
    '\.git|"\.git"' "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T2.3" "sidebar_state.rs checks Cargo.toml marker" \
    'Cargo\.toml|"Cargo.toml"' "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T2.4" "sidebar_state.rs checks package.json marker" \
    'package\.json|"package.json"' "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T2.5" "sidebar_state.rs has test_find_project_root test" \
    "test_find_project_root" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

# --- Task 3: Fuzzy search/filter ---
check_grep "T3.1" "sidebar_state.rs has filter_text field" \
    "filter_text" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T3.2" "sidebar_state.rs has set_filter method" \
    "fn set_filter|pub fn set_filter" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T3.3" "sidebar_state.rs has filtered_entries method" \
    "fn filtered_entries|pub fn filtered_entries" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T3.4" "sidebar.rs renders filter_text in search bar (not static Search...)" \
    "filter_text|self\.sidebar_tree.*filter" "$WEZTERM_DIR/wezterm-gui/src/termwindow/render/sidebar.rs"

check_grep "T3.5" "mod.rs has SidebarKeyInput or SidebarSearchClear notification" \
    "SidebarKeyInput|SidebarSearchClear|SidebarFilter" "$WEZTERM_DIR/wezterm-gui/src/termwindow/mod.rs"

check_grep "T3.6" "sidebar_state.rs has test_filter_entries test" \
    "test_filter" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

# --- Task 4: Keyboard navigation ---
check_grep "T4.1" "sidebar_state.rs has selected_index field" \
    "selected_index" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T4.2" "sidebar_state.rs has move_selection method" \
    "fn move_selection|pub fn move_selection" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T4.3" "sidebar_state.rs has open_selected method" \
    "fn open_selected|pub fn open_selected" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T4.4" "keybindings.lua has LEADER+e sidebar focus toggle" \
    'LEADER.*e|sidebar.*focus|toggle.*sidebar' "$PI_MONO_DIR/lua/embry/keybindings.lua"

check_grep "T4.5" "sidebar_state.rs has test_keyboard_navigation test" \
    "test_keyboard|test_move_selection|test_navigation" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

# --- Task 5: Lazy directory loading ---
check_not_grep "T5.1" "sidebar_state.rs no longer has 500 entry cap" \
    "500|MAX_ENTRIES.*500" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T5.2" "sidebar_state.rs has shallow/lazy read method" \
    "read_dir_shallow|read_children|lazy.*load|fn read_dir\b" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_not_grep "T5.3" "sidebar_state.rs does not call read_dir_recursive for init" \
    "read_dir_recursive" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

check_grep "T5.4" "sidebar_state.rs has test for lazy loading" \
    "test_lazy|test_shallow|test_read_dir" "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

# --- Task 6: File type color coding ---
check_grep "T6.1" "sidebar.rs has file_color or extension-based color function" \
    "fn file_color|fn extension_color|fn color_for|match.*extension|\.rs.*=>|\.lua.*=>" \
    "$WEZTERM_DIR/wezterm-gui/src/termwindow/render/sidebar.rs"

check_grep "T6.2" "sidebar.rs has Dracula-inspired color values" \
    "ffb86c|8be9fd|50fa7b|f1fa8c|bd93f9|ff79c6" \
    "$WEZTERM_DIR/wezterm-gui/src/termwindow/render/sidebar.rs"

# --- Task 6b: File viewer pane ---
check_grep "T6b.1" "mouseevent.rs or mod.rs handles SidebarFile double-click" \
    "double.*click|SidebarFile.*open|file_open|SidebarFileOpen" \
    "$WEZTERM_DIR/wezterm-gui/src/termwindow/mouseevent.rs"

check_grep "T6b.2" "File extension classification exists (code vs rich content)" \
    '\.rs|\.py|\.lua|\.md|\.html|\.pdf|\.png|\.svg' \
    "$WEZTERM_DIR/wezterm-gui/src/termwindow/mouseevent.rs"

# --- Task 9b: Panel toggle ---
check_grep "T9b.1" "keybindings.lua has LEADER+0 pure terminal mode" \
    'LEADER.*0|pure.*terminal|collapse.*all|hide.*all.*panel' \
    "$PI_MONO_DIR/lua/embry/keybindings.lua"

# --- Rust compilation check ---
check "COMPILE" "Config crate compiles and passes tests" \
    bash -c "cd $WEZTERM_DIR && cargo test -p config --quiet 2>&1"

# --- Interaction test check ---
check "E2E" "ops-pi-term sidebar tests pass" \
    bash -c "test -f /home/graham/.pi/skills/ops-pi-term/tests/pi-term-interaction-tests.sh"

# --- Best practices: Rust ---
check_not_grep "BP.1" "sidebar_state.rs has no unwrap() in non-test code" \
    '\.unwrap\(\)' <(sed '/^#\[cfg(test)\]/,/^}/d' "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs" 2>/dev/null || cat "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs")

check_not_grep "BP.2" "sidebar.rs has no println! or dbg!" \
    'println!|dbg!' "$WEZTERM_DIR/wezterm-gui/src/termwindow/render/sidebar.rs"

check_not_grep "BP.3" "sidebar_state.rs has no println! or dbg!" \
    'println!|dbg!' "$WEZTERM_DIR/wezterm-gui/src/termwindow/sidebar_state.rs"

# === Report ===
echo ""
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  Blind tests: $PASS pass, $FAIL fail ($(( PASS + FAIL )) total)"
echo ""

# Exit with failure count
[[ $FAIL -eq 0 ]]
