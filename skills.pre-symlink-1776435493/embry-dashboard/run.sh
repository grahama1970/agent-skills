#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# /embry-dashboard — Skill wrapper for the Embry Dashboard (Tauri app)
#
# Commands:
#   gui         Launch the Tauri app
#   navigate    Navigate to a specific tab (D-Bus signal + /tmp/embry_view)
#   screenshot  Capture window for /review-design
#   help        Show usage

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
TAURI_APP_DIR="${PROJECT_ROOT}/apps/embry-ui"

CMD="${1:-help}"
shift || true

case "$CMD" in
    gui)
        # Launch Tauri app — dev mode if source available, else built binary
        if [[ -f "${TAURI_APP_DIR}/package.json" ]]; then
            if [[ -f "${TAURI_APP_DIR}/src-tauri/target/release/embry-ui" ]]; then
                echo "Launching Embry Dashboard (release binary)..."
                exec "${TAURI_APP_DIR}/src-tauri/target/release/embry-ui" "$@"
            else
                echo "Launching Embry Dashboard (dev mode)..."
                cd "$TAURI_APP_DIR"
                exec npm run tauri dev "$@"
            fi
        else
            echo "ERROR: Tauri app not found at ${TAURI_APP_DIR}"
            echo "Expected: apps/embry-ui/ with package.json"
            exit 1
        fi
        ;;

    navigate)
        # Navigate to a specific tab: ./run.sh navigate threats/matrix
        TARGET="${1:-}"
        if [[ -z "$TARGET" ]]; then
            echo "Usage: ./run.sh navigate <group/tab>"
            echo ""
            echo "Examples:"
            echo "  ./run.sh navigate threats/matrix"
            echo "  ./run.sh navigate compliance/lemma"
            echo "  ./run.sh navigate analytics/overview"
            exit 1
        fi

        # Write to /tmp/embry_view (Tauri app reads on next check)
        echo "$TARGET" > /tmp/embry_view
        echo "View set: $TARGET"

        # Send D-Bus NavigateTab signal
        if command -v busctl &>/dev/null; then
            busctl --user emit \
                /org/embry/State \
                org.embry.State \
                NavigateTab s "$TARGET" 2>/dev/null && \
                echo "D-Bus NavigateTab signal sent" || \
                echo "WARN: D-Bus signal failed (state daemon may not be running)"
        else
            echo "WARN: busctl not found, D-Bus signal skipped"
        fi
        ;;

    screenshot)
        # Capture dashboard window for /review-design
        OUTPUT="${1:-/tmp/embry_screenshot.png}"

        # Find window by title
        WID=$(xdotool search --name "Embry" 2>/dev/null | head -1) || true

        if [[ -z "$WID" ]]; then
            echo "ERROR: No Embry window found. Launch with: ./run.sh gui"
            exit 1
        fi

        # Capture via ImageMagick import
        if command -v import &>/dev/null; then
            import -window "$WID" "$OUTPUT"
            echo "Screenshot saved: $OUTPUT"
        elif command -v grim &>/dev/null; then
            # Wayland fallback
            grim -g "$(xdotool getwindowgeometry --shell "$WID" | awk -F= '/POSITION/{p=$2} /WIDTH/{w=$2} /HEIGHT/{h=$2} END{print p","w"x"h}')" "$OUTPUT"
            echo "Screenshot saved: $OUTPUT"
        else
            echo "ERROR: Neither 'import' (ImageMagick) nor 'grim' found"
            exit 1
        fi
        ;;

    help|--help|-h)
        echo "embry-dashboard: Skill wrapper for Embry Dashboard (Tauri app)"
        echo ""
        echo "Commands:"
        echo "  gui                Launch the Embry Dashboard"
        echo "  navigate <path>    Navigate to tab (e.g. threats/matrix)"
        echo "  screenshot [path]  Capture window (default: /tmp/embry_screenshot.png)"
        echo "  help               Show this help"
        echo ""
        echo "Examples:"
        echo "  ./run.sh gui"
        echo "  ./run.sh navigate compliance/lemma"
        echo "  ./run.sh screenshot /tmp/review.png"
        ;;

    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
