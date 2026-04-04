#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Ensure dependencies
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 required"
    exit 1
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    mine)
        python3 mine_transcripts.py mine "$@"
        ;;

    analyze)
        python3 mine_transcripts.py analyze "$@"
        ;;

    export)
        python3 mine_transcripts.py export "$@"
        ;;

    merge)
        python3 mine_transcripts.py merge "$@"
        ;;

    sources)
        # List discovered CLI agent sources
        python3 mine_transcripts.py sources
        ;;

    help|*)
        cat <<EOF
mine-transcripts - Extract training data from CLI agent conversations

USAGE:
    ./run.sh <command> [options]

COMMANDS:
    mine        Mine transcripts for bridge classifier training
    analyze     Analyze bridge coverage in dataset
    export      Export samples for human review
    merge       Merge reviewed data into training set
    sources     List discovered CLI agent sources

MINE OPTIONS:
    --all-agents          Mine from all CLI agents (Claude, Codex, Gemini, Pi)
    --dedupe              Deduplicate against existing training data
    --store-memory        Store unique examples to /memory as lessons
    --output FILE         Output JSONL file (default: data/mined.jsonl)
    --sample N            Sample N examples (for review)

EXAMPLES:
    # Mine from all CLI agents with deduplication
    ./run.sh mine --all-agents --dedupe

    # Analyze coverage
    ./run.sh analyze data/mined.jsonl

    # Export 500 samples for review
    ./run.sh export --sample 500 --output for_review.jsonl

    # List available sources
    ./run.sh sources

INTEGRATION:
    Uses /taxonomy for bridge label extraction
    Uses /memory for deduplication
    Uses /episodic-archiver for emotional context
    Registered with /scheduler for nightly runs

For more details, see SKILL.md
EOF
        ;;
esac
