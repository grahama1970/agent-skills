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
  setup             Interview-driven setup wizard (safe by default)
  config            Initialize and validate release configuration
  doctor            Check runtime prerequisites and artifact writability
  chains            Inspect saved review workflows
  nightly           Run scheduled persona update (incremental learning)
  team-plan <request> Plan a role-based multi-agent team and preview/run its Tau DAG
  tau-dag <request> Compile a human request into a strict Tau DAG
  compete <request> Compile isolated competitors into a Tau compete DAG
  browser-availability Probe provider tabs for visible rate/capacity blockers
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
  --ask-id <id>         Stable runtime artifact id for this learn call
  --run-output-root <dir> Directory for request/status/events artifacts
  --overwrite           Replace an existing run directory for --ask-id
  --resume              Resume a non-terminal existing run directory for --ask-id
  --debug               Enable debug logging

Tau DAG Options:
  --repo <repo>         Repository/project binding for tau.dag_contract.v1
  --target <target>     Issue, task, path, or work target binding
  --solver-model <m>    Solver model to run; repeat for concurrent solvers
  --reviewer-model <m>  Reviewer model used to compare solver outputs
  --handler <h>         Browser or API handler/model; repeat for roundtable/compete
  --workflow-mode <m>   roundtable or compete
  --criterion <c>       Reviewer criterion; repeat for multiple criteria
  --execute             Send the emitted DAG to $tau after writing dag.json
  --local-fixture       Use local command workers for deterministic scheduler proof
  --allow-provider-calls Permit real provider calls through the SciLLM container
  --require-provider-calls Fail if SciLLM/provider calls are unavailable
  --viewer-link         Ask Tau for the React Flow DAG viewer link
  --run-output-root <dir> Directory for request/DAG/Tau receipt artifacts
  --json                JSON output

Ask Options:
  --scope <scope>       Memory scope to query (default: ask)
  --k <n>               Number of results (default: 5)
  --bridges             Also traverse bridge attributes
  --auto-learn          Auto-discover and learn if no knowledge found
  --collection <coll>   Taxonomy collection for auto-learn (default: behavioral)
  --raw                 Return raw memory results
  --image-generate      Generate image artifact(s) through scillm
  --image-model <m>     Image generation model (default: gpt-image-2)
  --image-size <s>      Image size, for example auto or 1024x1024
  --image-quality <q>   Image quality, for example auto, medium, or high
  --image-count <n>     Number of images to generate (default: 1)
  --image-output <path> Output file or directory for generated image(s)
  --image-output-format <f> Image format: png, jpeg, or webp
  --image-timeout <s>   Image generation timeout in seconds
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

  WebGPT/ChatGPT routing:
  WebGPT has been removed from /ask. Stale webgpt/chatgpt aliases and
  --webgpt-* flags fail closed. Use $surf webgpt.submit or the project-level
  $webgpt workflow directly.

  Other browser oracle backends (--oracle-backend):
  --gemini-tab-id <id>         Chrome tab id for webgemini
  --gemini-url <url>           Gemini conversation URL
  --kimi-tab-id <id>           Chrome tab id for webkimi
  --kimi-url <url>             Kimi conversation URL
  --cursor-browser-view-id <id>  Cursor Browser viewId (not Chrome tab id)
  --cursor-browser-url <url>     ChatGPT URL in Cursor Browser
  --cursor-browser-project <name>  ~/.pi/cursor-browser-projects/<name>.json
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
  --chain <name|path> Saved review chain spec
  --reviewer-spec <name|path> Reviewer spec (repeatable)
  --dag-json <json>     Execute inline ask/scillm-style DAG JSON
  --dag-file <path>     Execute ask/scillm-style DAG JSON file
  --dry-run             Emit execution spec/risk analysis without mutation
  --dogpile <auto|off|force> Freshness policy for oracle subagents
  --ask-id <id>      Stable runtime artifact id for this ask call
  --run-output-root <dir> Directory for request/status/events artifacts
  --overwrite           Replace an existing run directory for --ask-id
  --resume              Resume a non-terminal existing run directory for --ask-id
  --json                JSON output
  --debug               Enable debug logging


Browser-oracle setup (sibling skill: skills/browser-oracle):
  ./run.sh doctor --from <working-dir> --json
  Use browser-oracle directly for non-WebGPT reviewer tab bindings.
  See: skills/browser-oracle/SKILL.md

Status Options:
  --scope <scope>       Filter by scope
  --run <id|path>       Show runtime status for an ask id, run dir, or status file
  --tail-events <n>     Include the last N runtime events with --run
  --watch               Watch runtime status until terminal
  --serve               Serve a local auto-updating HTML viewer for --run
  --open                Open the local HTML viewer in a browser with --serve
  --serve-port <n>      Port for --serve; 0 selects a free port
  --serve-ttl-seconds <s> Seconds to keep viewer alive after terminal state
  --watch-timeout-seconds <s> Maximum seconds to wait with --watch
  --poll-interval-seconds <s> Polling interval for --watch
  --runs                List recent runtime runs
  --limit <n>           Maximum runs to list with --runs
  --prune               Prune old runtime run directories
  --older-than-days <n> Age threshold for --prune (default: 14)
  --dry-run             Preview --prune without deleting
  --run-output-root <dir> Runtime artifact root for --run ids
  --json                JSON output
  --debug               Enable debug logging

Nightly Options:
  --scope <scope>       Memory scope to update (default: ask)
  --persona <name>      Update a single persona by name
  --dry-run             Preview without storing
  --ask-id <id>         Stable runtime artifact id for this nightly call
  --run-output-root <dir> Directory for request/status/events artifacts
  --overwrite           Replace an existing run directory for --ask-id
  --resume              Resume a non-terminal existing run directory for --ask-id
  --json                Output summary as JSON
  --debug               Enable debug logging
Setup Options:
  --interactive         Always use /interview for high-level setup choices
  --profile <profile>   local-dev or shared-stack
  --dry-run             Preview without writing config or starting services
  --json                JSON output
  --yes                 Accept inferred defaults without prompting
  --start-missing       Explicit consent to start missing services

Doctor Options:
  --live                Run live subprocess/service checks
  --json                JSON output

Config Commands:
  config doctor         Validate ask.config.yml and release prerequisites
  config init           Launch /interview to create ask.config.yml

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

  # Compile a strict Tau DAG and stop before execution if fields are incomplete
  ./run.sh tau-dag "Ask 2 GPT 5.6 xhigh subagents to solve X, then Claude Fable reviews by criteria Y and Z" --repo local/tau --target issue-123 --criterion Y --criterion Z --json

  # Execute the emitted DAG through Tau using local command workers
  ./run.sh tau-dag "Solve X" --repo local/tau --target issue-123 --solver-model gpt-5.6-xhigh --solver-model gpt-5.6-xhigh --reviewer-model claude-fable --criterion correctness --criterion maintainability --execute --local-fixture --viewer-link --json

  # Compile isolated browser/API competitors into a Tau compete DAG
  ./run.sh compete "Implement the focused patch, then prepare a winner revision request" --repo local/agent-skills --target ask-compete --handler webgpt --handler webclaude --handler gpt-5.5-high --criterion skill-contract --criterion deterministic-proof --json

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
    ask)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.ask "$@"
        ;;
    setup)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.config_cli setup "$@"
        ;;
    status)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.status "$@"
        ;;
    config)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.config_cli "$@"
        ;;
    doctor)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.doctor "$@"
        ;;
    chains)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.chains_cli "$@"
        ;;
    nightly)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.nightly "$@"
        ;;
    team-plan)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.team_plan_cli "$@"
        ;;
    tau-dag)
        shift
        case "${1:-run}" in
            probe-scillm|compete|--help|-h|help)
                exec uv run --project "$SCRIPT_DIR" python -m ask.tau_dag_cli "$@"
                ;;
            *)
                exec uv run --project "$SCRIPT_DIR" python -m ask.tau_dag_cli run "$@"
                ;;
        esac
        ;;
    compete)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.tau_dag_cli compete "$@"
        ;;
    browser-availability)
        shift
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/probe_browser_provider_availability.py" "$@"
        ;;
    close-stale-tabs)
        shift
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/close_stale_ask_tabs.py" "$@"
        ;;
    webgpt-project)
        shift
        echo "WebGPT/ChatGPT routing has been removed from /ask. Use \$surf webgpt.submit or the project-level \$webgpt workflow directly." >&2
        exit 2
        ;;
    cursor-browser-project)
        shift
        exec uv run --project "$SCRIPT_DIR" python -m ask.cursor_browser_project_cli "$@"
        ;;
    os)
        shift
        subcmd="${1:-ask}"
        shift 2>/dev/null || true
        case "$subcmd" in
            learn)
                exec uv run --project "$SCRIPT_DIR" python -m ask.os_learn "$@"
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
