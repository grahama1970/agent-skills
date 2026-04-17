#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
monitor-misuse — Analyze misuse_events and propose corrections

Usage:
    ./run.sh analyze [--hours N] [--auto-apply]
    ./run.sh pending
    ./run.sh approve --key <key>
    ./run.sh reject --key <key>
    ./run.sh apply [--skill NAME] [--dry-run]
    ./run.sh report [--days N]
    ./run.sh skills

Commands:
    analyze     Analyze recent misuse events, cluster, propose corrections
    pending     List pending corrections awaiting review
    approve     Approve a correction (changes status to approved)
    reject      Reject a proposed correction
    apply       Apply approved corrections to skill misuse_guard.py files
    report      Generate misuse statistics report
    skills      List skills with registered misuse guards

Options:
    --hours N      Time window for analysis (default: 24)
    --days N       Time window for report (default: 7)
    --auto-apply   Auto-apply high-confidence corrections during analyze
    --skill NAME   Apply corrections only to specific skill
    --dry-run      Show what would be applied without making changes
EOF
}

case "${1:-}" in
    analyze)
        shift
        python3 "$SKILL_DIR/scripts/analyze.py" "$@"
        ;;
    pending)
        python3 "$SKILL_DIR/scripts/pending.py"
        ;;
    approve)
        shift
        python3 "$SKILL_DIR/scripts/approve.py" "$@"
        ;;
    reject)
        shift
        python3 "$SKILL_DIR/scripts/reject.py" "$@"
        ;;
    apply)
        shift
        python3 "$SKILL_DIR/scripts/apply.py" "$@"
        ;;
    report)
        shift
        python3 "$SKILL_DIR/scripts/report.py" "$@"
        ;;
    skills)
        python3 -c "from scripts.skill_registry import SKILL_GUARDS; print('\n'.join(f'{k}: {v.guard_path}' for k,v in SKILL_GUARDS.items()))"
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage
        exit 1
        ;;
esac
