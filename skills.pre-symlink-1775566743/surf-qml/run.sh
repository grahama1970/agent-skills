#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# AT-SPI (gi/PyGObject) requires system python — it's an apt package, not pip-installable.
# Use system python3 directly instead of uv isolation.
PYTHON3="$(command -v python3)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Ensure AT-SPI accessibility is enabled for Qt
export QT_ACCESSIBILITY=1
export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1

# Check dependencies
check_deps() {
    if ! "$PYTHON3" -c "import gi; gi.require_version('Atspi', '2.0')" 2>/dev/null; then
        echo "ERROR: pyatspi/gi not available"
        echo "Install with: sudo apt install python3-gi gir1.2-atspi-2.0 at-spi2-core"
        exit 1
    fi
}

CMD="${1:-help}"
shift || true

case "$CMD" in
    list)
        check_deps
        "$PYTHON3" surf_qml.py list "$@"
        ;;

    find)
        check_deps
        "$PYTHON3" surf_qml.py find "$@"
        ;;

    focus)
        check_deps
        "$PYTHON3" surf_qml.py focus "$@"
        ;;

    read)
        check_deps
        "$PYTHON3" surf_qml.py read "$@"
        ;;

    props)
        check_deps
        "$PYTHON3" surf_qml.py props "$@"
        ;;

    click)
        check_deps
        "$PYTHON3" surf_qml.py click "$@"
        ;;

    type)
        check_deps
        "$PYTHON3" surf_qml.py type "$@"
        ;;

    key)
        check_deps
        "$PYTHON3" surf_qml.py key "$@"
        ;;

    snap|screenshot)
        check_deps
        "$PYTHON3" surf_qml.py snap "$@"
        ;;

    record)
        check_deps
        if ! command -v ffmpeg &>/dev/null; then
            echo "ERROR: ffmpeg not found (required for video recording)"
            echo "Install with: sudo apt install ffmpeg"
            exit 1
        fi
        "$PYTHON3" surf_qml.py record "$@"
        ;;

    test)
        check_deps
        "$PYTHON3" surf_qml.py test "$@"
        ;;

    sanity)
        echo "=== surf-qml Sanity Check ==="
        echo ""

        # Check AT-SPI daemon
        echo -n "AT-SPI daemon: "
        if busctl --user status org.a11y.Bus &>/dev/null; then
            echo "OK"
        else
            echo "FAILED - run: systemctl --user start at-spi-dbus-bus"
        fi

        # Check Python dependencies
        echo -n "Python gi/Atspi: "
        if "$PYTHON3" -c "import gi; gi.require_version('Atspi', '2.0'); from gi.repository import Atspi" 2>/dev/null; then
            echo "OK"
        else
            echo "FAILED - run: sudo apt install python3-gi gir1.2-atspi-2.0"
        fi

        # Check ImageMagick (screenshots)
        echo -n "ImageMagick (import): "
        if command -v import &>/dev/null; then
            echo "OK"
        else
            echo "FAILED - run: sudo apt install imagemagick"
        fi

        # Check ffmpeg (video recording)
        echo -n "ffmpeg: "
        if command -v ffmpeg &>/dev/null; then
            echo "OK"
        else
            echo "FAILED - run: sudo apt install ffmpeg"
        fi

        # Check xdotool (keyboard/mouse)
        echo -n "xdotool: "
        if command -v xdotool &>/dev/null; then
            echo "OK"
        else
            echo "FAILED - run: sudo apt install xdotool"
        fi

        # Check PyYAML (scenarios)
        echo -n "PyYAML: "
        if "$PYTHON3" -c "import yaml" 2>/dev/null; then
            echo "OK"
        else
            echo "OPTIONAL - run: pip install pyyaml (needed for YAML scenarios)"
        fi

        # List accessible apps
        echo ""
        echo "Accessible applications:"
        "$PYTHON3" -c "
import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi
desktop = Atspi.get_desktop(0)
for i in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(i)
    if app:
        name = app.get_name() or '(unnamed)'
        print(f'  - {name}')
" 2>/dev/null || echo "  (none found)"
        ;;

    help|*)
        cat <<'EOF'
surf-qml - QML/Qt Application Automation via AT-SPI

USAGE:
    ./run.sh <command> [options]

COMMANDS:
    list                List all accessible applications
    find <name>         Find window by name (partial match)
    focus <name>        Focus/activate window
    read                Read accessibility tree with element refs
    props <ref>         Get properties of element (e.g., props e5)
    click <ref>         Click element by ref
    type <text>         Type text into focused element
    key <key>           Press key (Tab, Return, Escape, Up, Down, etc.)
    snap                Take screenshot
    record              Record video (ffmpeg x11grab)
    test <scenario>     Run test scenario (YAML/JSON)
    sanity              Check dependencies and list accessible apps

READ OPTIONS:
    --depth N           Limit tree depth (default: 10)
    --role ROLE         Filter by role (button, text-field, list-item, etc.)
    --name NAME         Filter by name pattern

TYPE OPTIONS:
    --ref REF           Type into specific element (default: focused)
    --clear             Clear field before typing

SNAP OPTIONS:
    --output FILE       Output path (default: /tmp/surf-qml-{timestamp}.png)
    --element REF       Screenshot specific element bounds

RECORD OPTIONS:
    --output FILE       Output path (default: /tmp/surf-qml-{timestamp}.mp4)
    --element REF       Record element region (+10px margin)
    --window NAME       Record specific window
    --duration N        Duration in seconds (default: 10)
    --framerate N       Framerate (default: 30)

TEST OPTIONS:
    scenario            YAML/JSON file or built-in name from scenarios/

EXAMPLES:
    # Find and interact with Horus overlay
    ./run.sh find "Horus"
    ./run.sh read
    ./run.sh type "calculator"
    ./run.sh key Tab
    ./run.sh snap --output /tmp/horus-test.png

    # Record 5-second video of specific window
    ./run.sh record --window "Horus" --duration 5

    # Run narrated UX scenario
    ./run.sh test scenarios/design_review.yaml

For more details, see SKILL.md
EOF
        ;;
esac
