#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# /ask Skill Runner
# Low-cognitive-load learning and querying interface.
# Tightly integrated with /task-monitor for progress tracking.
#
# Usage:
#   ./run.sh learn "Robert Sapolsky" --scope behavioral-psych
#   ./run.sh ask "Why do humans commit violence?" --scope behavioral-psych --auto-learn
#   ./run.sh status --scope behavioral-psych
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "${SCRIPT_DIR}")"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Resolve skill runner paths
MEMORY_RUN="${SKILLS_DIR}/../../.agent/skills/memory/run.sh"
DISCOVER_BOOKS_RUN="${SKILLS_DIR}/discover-books/run.sh"
INGEST_YOUTUBE_RUN="${SKILLS_DIR}/../../.agent/skills/ingest-youtube/run.sh"
EXTRACTOR_RUN="${SKILLS_DIR}/extractor/run.sh"
TAXONOMY_RUN="${SKILLS_DIR}/taxonomy/run.sh"
TASK_MONITOR_RUN="${SKILLS_DIR}/../../.agent/skills/task-monitor/run.sh"

# Check which skills are available
skill_available() {
    [[ -x "$1" ]] && return 0
    return 1
}

show_help() {
    cat <<'EOF'
/ask — Low-cognitive-load learning and querying

Commands:
  learn <topic>     Discover, ingest, and extract knowledge about a topic
  ask <question>    Query accumulated knowledge (with optional auto-learn)
  status            Show learning progress and task-monitor state
  nightly           Run scheduled persona update (incremental learning)
  os learn          Crawl and index embry-os internals (skills, packages, config)
  os ask <question> Query OS knowledge from memory (scope=os)
  os health <question> Query runtime health of an OS subsystem
  intent <query>    Classify a query into an intent category

Learn Options:
  --scope <scope>       Memory scope (default: ask)
  --collection <coll>   Taxonomy collection (default: behavioral)
  --depth <level>       Learning depth: quick (5-10min), standard (30-60min), deep (hours)
  -i, --interactive     Use /interview to ask about learning preferences
  --youtube <url>       Specific YouTube URL to ingest (repeatable)
  --books-only          Only discover/process books
  --youtube-only        Only process YouTube content
  --max-books <n>       Max books to discover (default: 5)
  --max-videos <n>      Max YouTube videos to process (default: 3)
  --dry-run             Preview without storing
  --debug               Enable debug logging

Ask Options:
  --scope <scope>       Memory scope to query (default: ask)
  --k <n>               Number of results (default: 5)
  --bridges             Also traverse bridge attributes
  --auto-learn          Auto-discover and learn if no knowledge found
  --collection <coll>   Taxonomy collection for auto-learn (default: behavioral)
  --raw                 Return raw memory results
  --json                JSON output
  --debug               Enable debug logging

Status Options:
  --scope <scope>       Filter by scope
  --json                JSON output
  --debug               Enable debug logging

Nightly Options:
  --scope <scope>       Memory scope to update (default: ask)
  --persona <name>      Update a single persona by name
  --dry-run             Preview without storing
  --json                Output summary as JSON
  --debug               Enable debug logging

Examples:
  # Learn about a topic
  ./run.sh learn "Robert Sapolsky" --scope behavioral-psych

  # Ask a question (returns answer from memory)
  ./run.sh ask "What causes aggression?" --scope behavioral-psych

  # Ask with auto-learn (discovers + ingests if no knowledge exists)
  ./run.sh ask "What does Sapolsky say about free will?" --scope behavioral-psych --auto-learn

  # Ask with bridge traversal
  ./run.sh ask "Why is chronic stress harmful?" --scope behavioral-psych --bridges

  # Learn from specific YouTube lectures
  ./run.sh learn "behavioral neuroscience" --youtube https://youtube.com/watch?v=NNnIGh9g6fA --scope behavioral-psych

  # Check learning progress
  ./run.sh status --scope behavioral-psych

  # Task-monitor integration (progress tracked automatically)
  cat .pi/skills/ask/ask_task_state.json

  # Run nightly persona update
  ./run.sh nightly --scope behavioral-psych

  # Update a single persona
  ./run.sh nightly --persona "Lisa Feldman Barrett" --scope behavioral-psych
EOF
}

case "${1:-help}" in
    learn)
        shift
        exec uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/learn.py" "$@"
        ;;
    ask|query)
        shift
        exec uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/ask.py" "$@"
        ;;
    status)
        shift
        exec uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/status.py" "$@"
        ;;
    nightly)
        shift
        exec uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/nightly.py" "$@"
        ;;
    os)
        shift
        subcmd="${1:-ask}"
        shift 2>/dev/null || true
        case "$subcmd" in
            learn)
                exec uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/os_learn.py" learn "$@"
                ;;
            ask)
                exec uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/os_query.py" ask "$@"
                ;;
            health)
                exec uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/os_query.py" health "$@"
                ;;
            *)
                echo "Unknown os subcommand: $subcmd"
                echo "Usage: ./run.sh os {learn|ask|health} [options]"
                exit 1
                ;;
        esac
        ;;
    intent)
        shift
        exec uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/ask_intent.py" "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run './run.sh help' for usage."
        exit 1
        ;;
esac
