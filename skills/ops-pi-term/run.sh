#!/usr/bin/env bash
# ops-pi-term — Pi Term operations and interaction testing
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
TESTS_DIR="$SKILL_DIR/tests"
SCREENSHOT_DIR="$SKILL_DIR/screenshots/tests"
BASELINE_DIR="$SKILL_DIR/fixtures/baseline"
WEZTERM_DIR="${HOME}/workspace/experiments/pi-term"
PI_MONO_DIR="${HOME}/workspace/experiments/pi-mono/packages/wezterm"

# Task-monitor integration
TM_RUN="$SKILL_DIR/../task-monitor/run.sh"
_tm() {
    if [[ -f "$TM_RUN" ]]; then
        "$TM_RUN" "$@" 2>/dev/null || true
    fi
}

usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  test [--group NAME] [--list]   Run interaction tests (all or specific group)"
    echo "  health                         Health check (no UI interaction)"
    echo "  blind-test                     Run blind adversarial tests via /test-lab"
    echo "  visual-regression [--generate-baseline|--update-baseline]"
    echo "  design-review                  Feed screenshots to /review-design"
    echo "  build-check                    Verify Rust + Lua build status"
    echo ""
    exit 1
}

# === Health Check ===
cmd_health() {
    _tm start-session --project ops-pi-term
    local pass=0 fail=0

    echo "=== Pi Term Health Check ==="
    echo ""

    # 1. wezterm-gui process
    if pgrep -x wezterm-gui >/dev/null 2>&1; then
        echo "  [OK] wezterm-gui is running (PID: $(pgrep -x wezterm-gui | head -1))"
        pass=$((pass + 1))
    else
        echo "  [FAIL] wezterm-gui is NOT running"
        fail=$((fail + 1))
    fi

    # 2. X11 window
    local wid
    wid=$(xdotool search --class "org.wezfurlong.wezterm" 2>/dev/null | head -1 || true)
    if [[ -n "$wid" ]]; then
        echo "  [OK] X11 window found (ID: $wid)"
        pass=$((pass + 1))
    else
        echo "  [FAIL] No X11 window found"
        fail=$((fail + 1))
    fi

    # 3. Config tests
    if (cd "$WEZTERM_DIR" && cargo test -p config --quiet 2>/dev/null); then
        echo "  [OK] Config crate tests pass"
        pass=$((pass + 1))
    else
        echo "  [FAIL] Config crate tests failed"
        fail=$((fail + 1))
    fi

    # 4. pi-webview binary
    local webview_bin=""
    for p in \
        "$WEZTERM_DIR/pi-webview/target/release/pi-webview" \
        "$WEZTERM_DIR/pi-webview/target/debug/pi-webview" \
        "$(which pi-webview 2>/dev/null || true)"; do
        if [[ -x "$p" ]]; then
            webview_bin="$p"
            break
        fi
    done
    if [[ -n "$webview_bin" ]]; then
        echo "  [OK] pi-webview binary found: $webview_bin"
        pass=$((pass + 1))
    else
        echo "  [WARN] pi-webview not built (browser sidecar unavailable)"
    fi

    # 5. Lua modules
    local lua_dir="$PI_MONO_DIR/lua/embry"
    local expected_modules=(state status-bar tab-title keybindings signals notifications metadata palette session sidebar browser init)
    local missing=0
    for mod in "${expected_modules[@]}"; do
        if [[ ! -f "$lua_dir/$mod.lua" ]]; then
            echo "  [FAIL] Missing Lua module: $mod.lua"
            missing=$((missing + 1))
        fi
    done
    if [[ $missing -eq 0 ]]; then
        echo "  [OK] All ${#expected_modules[@]} Lua modules present"
        pass=$((pass + 1))
    else
        fail=$((fail + missing))
    fi

    # 6. signal-monitor.sh
    if [[ -f "$lua_dir/signal-monitor.sh" ]]; then
        echo "  [OK] signal-monitor.sh present"
        pass=$((pass + 1))
    else
        echo "  [FAIL] signal-monitor.sh missing"
        fail=$((fail + 1))
    fi

    # 7. D-Bus service
    if busctl --user status org.embry.Agent >/dev/null 2>&1; then
        echo "  [OK] Embry Agent D-Bus service running"
        pass=$((pass + 1))
    else
        echo "  [WARN] Embry Agent D-Bus service not running (agent features disabled)"
    fi

    # 8. Screenshot tools
    if command -v import >/dev/null 2>&1 && command -v xdotool >/dev/null 2>&1; then
        echo "  [OK] Screenshot tools available (import, xdotool)"
        pass=$((pass + 1))
    else
        echo "  [FAIL] Missing screenshot tools (need: imagemagick, xdotool)"
        fail=$((fail + 1))
    fi

    # 9. Session directory
    local session_dir="$HOME/.local/share/pi/term/sessions"
    if [[ -d "$session_dir" ]]; then
        local count
        count=$(ls "$session_dir"/*.json 2>/dev/null | wc -l || echo 0)
        echo "  [OK] Session directory exists ($count saved sessions)"
        pass=$((pass + 1))
    else
        echo "  [INFO] Session directory not created yet"
    fi

    echo ""
    echo "  Health: $pass pass, $fail fail"

    _tm add-accomplishment --text "Health check: $pass pass, $fail fail"
    _tm end-session --notes "Health check completed"

    [[ $fail -eq 0 ]]
}

# === Interaction Tests ===
cmd_test() {
    _tm start-session --project ops-pi-term

    # Delegate to the interaction test script
    chmod +x "$TESTS_DIR/pi-term-interaction-tests.sh"
    "$TESTS_DIR/pi-term-interaction-tests.sh" "$@"
    local rc=$?

    if [[ $rc -eq 0 ]]; then
        _tm add-accomplishment --text "Interaction tests: ALL PASS"
    else
        _tm add-accomplishment --text "Interaction tests: SOME FAILURES"
    fi
    _tm end-session --notes "Interaction tests completed (exit=$rc)"
    return $rc
}

# === Build Check ===
cmd_build_check() {
    _tm start-session --project ops-pi-term
    echo "=== Pi Term Build Check ==="

    local pass=0 fail=0

    # Config crate
    echo "  Checking config crate..."
    if (cd "$WEZTERM_DIR" && cargo check -p config 2>/dev/null); then
        echo "  [OK] cargo check -p config"
        pass=$((pass + 1))
    else
        echo "  [FAIL] cargo check -p config"
        fail=$((fail + 1))
    fi

    # Config tests
    echo "  Running config tests..."
    if (cd "$WEZTERM_DIR" && cargo test -p config 2>/dev/null); then
        echo "  [OK] cargo test -p config"
        pass=$((pass + 1))
    else
        echo "  [FAIL] cargo test -p config"
        fail=$((fail + 1))
    fi

    # TypeScript tools tests
    echo "  Running vitest..."
    if (cd "$PI_MONO_DIR" && npx vitest run --reporter=dot 2>/dev/null); then
        echo "  [OK] vitest tests pass"
        pass=$((pass + 1))
    else
        echo "  [WARN] vitest may need npm install first"
    fi

    echo ""
    echo "  Build check: $pass pass, $fail fail"

    _tm add-accomplishment --text "Build check: $pass pass, $fail fail"
    _tm end-session --notes "Build check completed"
    [[ $fail -eq 0 ]]
}

# === Visual Regression ===
cmd_visual_regression() {
    _tm start-session --project ops-pi-term

    mkdir -p "$BASELINE_DIR" "$SCREENSHOT_DIR"

    if [[ "${1:-}" == "--generate-baseline" || "${1:-}" == "--update-baseline" ]]; then
        echo "Generating baseline screenshots..."
        chmod +x "$TESTS_DIR/pi-term-interaction-tests.sh"
        "$TESTS_DIR/pi-term-interaction-tests.sh" --group visual_baseline || true

        # Copy latest screenshots as baseline
        local count=0
        for f in "$SCREENSHOT_DIR"/01_baseline_*.png; do
            if [[ -f "$f" ]]; then
                cp "$f" "$BASELINE_DIR/baseline.png"
                count=$((count + 1))
            fi
        done
        echo "  Baseline updated: $count screenshots"
        _tm add-accomplishment --text "Visual regression baseline updated"
    else
        # Compare against baseline
        if [[ ! -f "$BASELINE_DIR/baseline.png" ]]; then
            echo "No baseline found. Run: $0 visual-regression --generate-baseline"
            _tm end-session --notes "No baseline found"
            return 1
        fi

        # Take current screenshot
        local wid
        wid=$(xdotool search --class "org.wezfurlong.wezterm" 2>/dev/null | head -1 || true)
        if [[ -z "$wid" ]]; then
            echo "No WezTerm window found"
            _tm end-session --notes "No window for visual regression"
            return 1
        fi

        local current="$SCREENSHOT_DIR/regression_current_$(date +%s).png"
        import -window "$wid" "$current"

        if command -v compare >/dev/null 2>&1; then
            local diff_count
            diff_count=$(compare -metric AE "$BASELINE_DIR/baseline.png" "$current" /dev/null 2>&1 || echo "999999")
            echo "Pixel difference: $diff_count"

            if [[ "$diff_count" -lt 500 ]]; then
                echo "  [PASS] Visual regression: within threshold (<500 px diff)"
                _tm add-accomplishment --text "Visual regression PASS ($diff_count px diff)"
            else
                echo "  [FAIL] Visual regression: $diff_count pixels differ (threshold: 500)"
                # Generate diff image
                local diff_img="$SCREENSHOT_DIR/regression_diff_$(date +%s).png"
                compare "$BASELINE_DIR/baseline.png" "$current" "$diff_img" 2>/dev/null || true
                echo "  Diff image: $diff_img"
                _tm add-accomplishment --text "Visual regression FAIL ($diff_count px diff)"
            fi
        else
            echo "  [WARN] ImageMagick 'compare' not available, skipping pixel diff"
        fi
    fi

    _tm end-session --notes "Visual regression completed"
}

# === Design Review ===
cmd_design_review() {
    echo "Capturing current screenshots for design review..."

    local wid
    wid=$(xdotool search --class "org.wezfurlong.wezterm" 2>/dev/null | head -1 || true)
    if [[ -z "$wid" ]]; then
        echo "No WezTerm window found"
        return 1
    fi

    local ts=$(date +%s)
    local shots=()

    # Capture baseline
    local shot="$SCREENSHOT_DIR/design_review_${ts}.png"
    import -window "$wid" "$shot"
    shots+=("$shot")

    echo "Screenshots captured: ${#shots[@]} files in $SCREENSHOT_DIR/"
    echo ""
    echo "To run design review, use:"
    echo "  /review-design with gemini ${shots[*]} --context \"Pi Term sidebar + tab bar layout\""
}

# === Main ===
case "${1:-}" in
    test)       shift; cmd_test "$@" ;;
    health)     cmd_health ;;
    build-check) cmd_build_check ;;
    visual-regression) shift; cmd_visual_regression "$@" ;;
    design-review) cmd_design_review ;;
    blind-test)
        echo "Blind tests require /test-lab integration."
        echo "Use: /test-lab generate --domain pi-term --tasks local/docs/08_TASKS_sidebar.md"
        ;;
    *)          usage ;;
esac
