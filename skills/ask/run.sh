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
  doctor            Preflight memory, dogpile, scillm, subagent, specs, chains
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
  --oracle              Use scillm/Codex for final oracle synthesis
  --oracle-backend <b>  Oracle backend: auto, scillm, subagent-runner
  --oracle-model <m>    Oracle synthesis model (default: gpt-5.5)
  --oracle-reasoning <r> Oracle reasoning effort (default: high; deep-review default: xhigh)
  --oracle-timeout <s>  Oracle HTTP timeout in seconds (default: 300)
  --oracle-idle-timeout <s> Subagent silence timeout before stalled recovery
  --oracle-heartbeat-interval <s> Memory heartbeat write interval
  --oracle-persona <p>  Primary persona/subagent for oracle synthesis
  --oracle-peer <p>     Second persona/subagent for oracle deliberation
  --oracle-persona-model <m> Model for primary persona turns
  --oracle-peer-model <m> Model for peer persona turns
  --oracle-iterations <n> Sequential oracle deliberation calls (default: 1)
  --roundtable         Run sequential protocolized persona deliberation
  --roundtable-personas <p> Comma-separated persona[:role] participants
  --roundtable-role-preset <p> Role preset (default: adversarial-review)
  --roundtable-rounds <n> Number of roundtable rounds (default: 2)
  --roundtable-persist <summary|full> Persist compact state or full turns
  --parallel-review    Run independent parallel adversarial reviewers
  --parallel-reviewers <n> Number of default reviewers (default: 3)
  --parallel-review-personas <p> Comma-separated reviewer persona[:role] specs
  --parallel-review-focus <f> Comma-separated reviewer focus labels
  --deep-review         Run read-only deep review with review.md/review.json artifacts
  --deep-review-target <target> Explicit target: paths, diff, plan, manifest, or artifact
  --deep-reviewers <n> Reviewer breadth requested for deep review
  --deep-review-focus <f> Comma-separated deep-review focus labels
  --run-id <id>      Explicit run id for artifact/status correlation
  --review-context <fresh|fork> Context mode for review/oracle child runs
  --inherit-memory <yes|no|summary> Memory inheritance policy
  --inherit-skills <yes|no|selected> Skill inheritance policy
  --inherit-project-context <yes|no> Project-context inheritance policy
  --dogpile <auto|off|force> Freshness policy for oracle subagents
  --json                JSON output
  --debug               Enable debug logging

Status Options:
  --scope <scope>       Filter by scope
  --runs                Show recent /ask runtime runs
  --last <n>            Number of recent runs (default: 10)
  --id <run_id>         Show one runtime run
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

  # Ask with GPT oracle synthesis
  ./run.sh ask "What is the strongest interpretation?" --oracle --oracle-reasoning high

  # Natural persona syntax: resolves the stored persona and uses the focused oracle subagent
  ./run.sh ask Brandon what is the state of space-based cybersecurity in 2016?

  # Ask with persona ping-pong deliberation
  ./run.sh ask "What should we do?" --oracle --oracle-persona "architect" --oracle-peer "critic" --oracle-iterations 3

  # Ask with GPT-5.5 conversing with a scillm one-shot model
  ./run.sh ask "What should we do?" --oracle --oracle-backend subagent-runner --oracle-persona "architect" --oracle-peer "DeepSeek critic" --oracle-peer-model opencode-go/deepseek-v4-pro --oracle-iterations 3

  # Natural N-persona roundtable syntax
  ./run.sh ask Brandon, Margaret, and Jennifer to debate the relevance of Formal Methods in aerospace projects in 2026

  # Explicit protocolized roundtable
  ./run.sh ask "Formal Methods in aerospace projects in 2026" --roundtable --roundtable-personas "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer" --roundtable-rounds 2

  # Independent parallel adversarial reviewers
  ./run.sh ask "Review this architecture" --parallel-review --parallel-reviewers 3 --parallel-review-focus correctness,tests,maintainability

  # First-class deep review artifacts
  ./run.sh ask "deep review this implementation" --deep-review --deep-review-target src/ask/ask.py

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
        exec uv run --project "$SCRIPT_DIR" python -m ask.learn "$@"
        ;;
    ask|query)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.ask "$@"
        ;;
    status)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.status "$@"
        ;;
    doctor)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.doctor "$@"
        ;;
    nightly)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.nightly "$@"
        ;;
    os)
        shift
        subcmd="${1:-ask}"
        shift 2>/dev/null || true
        case "$subcmd" in
            learn)
                exec uv run --project "$SCRIPT_DIR" python -m ask.os_learn learn "$@"
                ;;
            ask)
                exec uv run --project "$SCRIPT_DIR" python -m ask.os_query ask "$@"
                ;;
            health)
                exec uv run --project "$SCRIPT_DIR" python -m ask.os_query health "$@"
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
        exec uv run --project "$SCRIPT_DIR" python -m ask.ask_intent "$@"
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
