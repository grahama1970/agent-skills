#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# F-36 Plant Floor Operations — Subcommand Router
#
# Usage:
#   f36-plant-ops test torque --part-id ABC123
#   f36-plant-ops disposition pass --part-id ABC123
#   f36-plant-ops escalate --part-id ABC123 --notify-qa
#   f36-plant-ops shift-handoff
#   f36-plant-ops scan-barcode
#   f36-plant-ops capture-photo --part-id ABC123
#   f36-plant-ops deviation-report
#   f36-plant-ops vendor-reject
#   f36-plant-ops assembly-status
#   f36-plant-ops maintenance-log
#   f36-plant-ops shift-summary
#   f36-plant-ops shift-log --today
#   f36-plant-ops log --part-id ABC123
#   f36-plant-ops next-part
#   f36-plant-ops buttons          # List all button definitions
#   f36-plant-ops buttons --page f36_machine_test
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$SKILLS_DIR")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Helper: find a composed skill's run.sh
find_skill() {
    local skill_name="$1"
    local skill_path="$SKILLS_DIR/$skill_name/run.sh"
    if [ -x "$skill_path" ]; then
        echo "$skill_path"
    else
        echo "ERROR: Required skill '$skill_name' not found at $skill_path" >&2
        return 1
    fi
}

# Helper: get part-id from args or clipboard
get_part_id() {
    for arg in "$@"; do
        if [[ "$prev" == "--part-id" ]]; then
            echo "$arg"
            return
        fi
        prev="$arg"
    done
    # Fallback: clipboard
    if command -v xclip &>/dev/null; then
        xclip -o 2>/dev/null
    fi
}

SUBCMD="${1:-help}"
shift 2>/dev/null || true

case "$SUBCMD" in
    # ── Machine Testing ────────────────────────────────
    test)
        TEST_TYPE="${1:-help}"
        shift 2>/dev/null || true
        PART_ID=$(get_part_id "$@")
        echo "F-36 Test: $TEST_TYPE | Part: $PART_ID"
        case "$TEST_TYPE" in
            torque)
                echo "Running torque test sequence for $PART_ID..."
                QUALITY_SKILL=$(find_skill "quality-audit")
                "$QUALITY_SKILL" check --type torque --part-id "$PART_ID" "$@"
                ;;
            thermal)
                echo "Running thermal cycling test for $PART_ID..."
                QUALITY_SKILL=$(find_skill "quality-audit")
                "$QUALITY_SKILL" check --type thermal --part-id "$PART_ID" "$@"
                ;;
            ndi)
                echo "Running NDI scan for $PART_ID..."
                QUALITY_SKILL=$(find_skill "quality-audit")
                "$QUALITY_SKILL" check --type ndi --part-id "$PART_ID" "$@"
                ;;
            inspect)
                echo "Running visual inspection for $PART_ID..."
                QUALITY_SKILL=$(find_skill "quality-audit")
                "$QUALITY_SKILL" check --type visual --part-id "$PART_ID" "$@"
                ;;
            *)
                echo "Usage: f36-plant-ops test {torque|thermal|ndi|inspect} --part-id <id>"
                exit 1
                ;;
        esac
        ;;

    # ── Disposition ────────────────────────────────────
    disposition)
        RESULT="${1:-help}"
        shift 2>/dev/null || true
        PART_ID=$(get_part_id "$@")
        echo "F-36 Disposition: $RESULT | Part: $PART_ID"
        BQ_SKILL=$(find_skill "batch-quality")
        case "$RESULT" in
            pass)
                "$BQ_SKILL" approve --part-id "$PART_ID" "$@"
                ;;
            fail)
                "$BQ_SKILL" reject --part-id "$PART_ID" "$@"
                ;;
            *)
                echo "Usage: f36-plant-ops disposition {pass|fail} --part-id <id>"
                exit 1
                ;;
        esac
        ;;

    # ── Escalation ─────────────────────────────────────
    escalate)
        PART_ID=$(get_part_id "$@")
        echo "F-36 Escalate: Part $PART_ID → QA Supervisor"
        INBOX_SKILL=$(find_skill "agent-inbox")
        "$INBOX_SKILL" send --to qa-supervisor --subject "ESCALATION: Part $PART_ID" \
            --body "Part $PART_ID escalated from plant floor. Requires QA review." "$@"
        ;;

    # ── Documentation ──────────────────────────────────
    capture-photo)
        PART_ID=$(get_part_id "$@")
        echo "F-36 Photo Capture: Part $PART_ID"
        # Check for --type flag
        PHOTO_TYPE="test"
        for arg in "$@"; do
            if [[ "$prev" == "--type" ]]; then
                PHOTO_TYPE="$arg"
            fi
            prev="$arg"
        done
        echo "Photo type: $PHOTO_TYPE"
        # Use system camera capture, tag with part-id and type
        if command -v fswebcam &>/dev/null; then
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            PHOTO_DIR="${HOME}/.pi/f36/photos"
            mkdir -p "$PHOTO_DIR"
            PHOTO_PATH="$PHOTO_DIR/${PART_ID}_${PHOTO_TYPE}_${TIMESTAMP}.jpg"
            fswebcam -r 1280x720 --no-banner "$PHOTO_PATH"
            echo "Photo saved: $PHOTO_PATH"
        else
            echo "WARNING: fswebcam not installed. Install with: sudo apt install fswebcam" >&2
            exit 1
        fi
        ;;

    log)
        PART_ID=$(get_part_id "$@")
        echo "F-36 Log Entry: Part $PART_ID"
        ARCHIVER=$(find_skill "episodic-archiver")
        "$ARCHIVER" store --scope f36-plant --tags "part:$PART_ID" "$@"
        ;;

    scan-barcode)
        echo "F-36 Barcode Scanner"
        # Read barcode via USB scanner (acts as keyboard) or zbarcam
        if command -v zbarcam &>/dev/null; then
            BARCODE=$(zbarcam --raw --oneshot /dev/video0 2>/dev/null)
            echo "$BARCODE" | xclip -selection clipboard
            echo "Scanned: $BARCODE (copied to clipboard)"
        else
            echo "Waiting for barcode scan (USB scanner)..."
            read -r BARCODE
            echo "$BARCODE" | xclip -selection clipboard
            echo "Scanned: $BARCODE (copied to clipboard)"
        fi
        ;;

    next-part)
        echo "F-36 Next Part"
        echo "Advancing to next part in queue..."
        # Clear clipboard, ready for next barcode scan
        echo "" | xclip -selection clipboard
        echo "Clipboard cleared. Scan next part barcode."
        ;;

    # ── Shift Operations ───────────────────────────────
    shift-handoff)
        echo "F-36 Shift Handoff Report"
        ARCHIVER=$(find_skill "episodic-archiver")
        "$ARCHIVER" store --scope f36-shift --tags "handoff,$(date +%Y-%m-%d)" "$@"
        echo "Handoff report filed."
        ;;

    shift-summary)
        echo "F-36 Shift Summary"
        ANALYTICS=$(find_skill "analytics")
        "$ANALYTICS" query --scope f36-plant --period today --format summary "$@"
        ;;

    shift-log)
        echo "F-36 Shift Log"
        ARCHIVER=$(find_skill "episodic-archiver")
        "$ARCHIVER" recall --scope f36-shift --period today "$@"
        ;;

    assembly-status)
        echo "F-36 Assembly Line Status"
        ANALYTICS=$(find_skill "analytics")
        "$ANALYTICS" query --scope f36-plant --type assembly-status "$@"
        ;;

    maintenance-log)
        echo "F-36 Maintenance Log Entry"
        ARCHIVER=$(find_skill "episodic-archiver")
        "$ARCHIVER" store --scope f36-maintenance --tags "maintenance,$(date +%Y-%m-%d)" "$@"
        ;;

    # ── Vendor Review ──────────────────────────────────
    deviation-report)
        echo "F-36 Deviation Report"
        REVIEW=$(find_skill "review-pdf")
        "$REVIEW" compare --scope vendor --flag-deviations "$@"
        ;;

    vendor-reject)
        echo "F-36 Vendor Material Rejection"
        BQ_SKILL=$(find_skill "batch-quality")
        "$BQ_SKILL" reject --scope vendor "$@"
        INBOX_SKILL=$(find_skill "agent-inbox")
        "$INBOX_SKILL" send --to procurement --subject "Vendor Material Rejected" \
            --body "Material batch rejected from plant floor." "$@"
        ;;

    # ── Button Manifest ────────────────────────────────
    buttons)
        if command -v yq &>/dev/null; then
            PAGE_FILTER=""
            for arg in "$@"; do
                if [[ "$prev" == "--page" ]]; then
                    PAGE_FILTER="$arg"
                fi
                prev="$arg"
            done
            if [ -n "$PAGE_FILTER" ]; then
                yq ".[] | select(.page == \"$PAGE_FILTER\")" "$SCRIPT_DIR/buttons.yaml"
            else
                yq '.' "$SCRIPT_DIR/buttons.yaml"
            fi
        else
            cat "$SCRIPT_DIR/buttons.yaml"
        fi
        ;;

    # ── Help ───────────────────────────────────────────
    help|--help|-h)
        echo "F-36 Plant Floor Operations"
        echo ""
        echo "Machine Testing:"
        echo "  test {torque|thermal|ndi|inspect} --part-id <id>"
        echo ""
        echo "Disposition:"
        echo "  disposition {pass|fail} --part-id <id>"
        echo "  escalate --part-id <id> [--notify-qa]"
        echo ""
        echo "Documentation:"
        echo "  capture-photo --part-id <id> [--type vendor-material]"
        echo "  log --part-id <id>"
        echo "  scan-barcode"
        echo "  next-part"
        echo ""
        echo "Shift Operations:"
        echo "  shift-handoff"
        echo "  shift-summary"
        echo "  shift-log [--today]"
        echo "  assembly-status"
        echo "  maintenance-log"
        echo ""
        echo "Vendor Review:"
        echo "  deviation-report"
        echo "  vendor-reject"
        echo ""
        echo "Utility:"
        echo "  buttons [--page <page_name>]"
        ;;

    *)
        echo "Unknown subcommand: $SUBCMD" >&2
        echo "Run 'f36-plant-ops help' for usage." >&2
        exit 1
        ;;
esac
