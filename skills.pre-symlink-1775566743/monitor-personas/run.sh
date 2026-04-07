#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# monitor-personas - Self-contained persona learning pipeline
# Monitors ALL sources, extracts QRAs, classifies streams, learns to memory
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# State directory
STATE_DIR="${PERSONA_MONITOR_STATE_DIR:-$HOME/.pi/monitor-personas}"
mkdir -p "$STATE_DIR"

usage() {
    cat <<EOF
monitor-personas - Self-Contained Persona Learning Pipeline

Usage: ./run.sh <command> [options]

Source Monitoring:
  check              Check YouTube personas for new content
  check-all          Check ALL sources (YouTube, RSS, arXiv, Books, Movies, etc.)
  ingest             Ingest new YouTube content
  ingest-all         Ingest from all source types
  status             Show current monitoring status
  list-personas      List all configured personas

Learning Pipeline:
  learn              Learn pending content to memory with taxonomy
  extract            Extract content to QRAs via /extractor
  classify-streams   Classify into Intent or Persona streams

Reflection Loop:
  archive            Archive sessions to episodic memory
  verify-edges       Verify relationships with existing knowledge
  reflect            Research knowledge gaps via /dogpile

Training:
  train              Generate training data + trigger train-persona
  pipeline-status    Show overall pipeline status
  close-loop         Run complete pipeline (all steps)

Automation:
  register-nightly   Register full pipeline with scheduler
  register-basic     Register basic monitoring only (check/ingest/learn)

Readiness:
  readiness          Assess if personas have sufficient QRAs for core competency
  readiness -v       Show per-bridge tag breakdown for each persona

Backfill:
  backfill-taxonomy  Shadow-LEGO backfill: stamp taxonomy_tags on existing QRAs
  backfill-taxonomy --dry-run   Preview without LLM calls
  backfill-taxonomy --scope X   Backfill specific scope(s)

Operations:
  qra-status         Show per-scope QRA counts from ArangoDB + running processes
  process-count      Show running doc2qra processes with PIDs

Options:
  --priority HIGH|MEDIUM|LOW    Filter by priority
  --category CATEGORY           Filter by category
  --persona ID                  Filter by persona ID
  --json                        Output as JSON
  --dry-run                     Preview without executing
  --max N                       Max items to process

Examples:
  ./run.sh check --priority HIGH
  ./run.sh check-all --json
  ./run.sh ingest --dry-run
  ./run.sh learn --max 50
  ./run.sh close-loop --dry-run
  ./run.sh pipeline-status
  ./run.sh register-nightly
EOF
}

# Register basic monitoring (check/ingest/learn only)
register_basic() {
    echo "Registering basic persona monitoring jobs..."

    # Register HIGH priority check at 2 AM
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-monitor-check" \
        --cron "0 2 * * *" \
        --command "$SCRIPT_DIR/run.sh check --priority HIGH --json > $STATE_DIR/check.json" \
        --workdir "$PROJECT_ROOT" \
        --description "Nightly persona source check (HIGH priority)" || true

    # Register ingestion at 3 AM
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-monitor-ingest" \
        --cron "0 3 * * *" \
        --command "$SCRIPT_DIR/run.sh ingest --priority HIGH" \
        --workdir "$PROJECT_ROOT" \
        --description "Nightly persona content ingestion" || true

    # Register learning at 4 AM
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-monitor-learn" \
        --cron "0 4 * * *" \
        --command "$SCRIPT_DIR/run.sh learn --max 100" \
        --workdir "$PROJECT_ROOT" \
        --description "Nightly persona learning to memory with taxonomy" || true

    echo "Registered 3 nightly jobs: check (2 AM), ingest (3 AM), learn (4 AM)"
}

# Register full nightly pipeline
register_nightly() {
    echo "Registering full nightly persona pipeline..."

    # 2 AM - Check ALL sources
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-check-all" \
        --cron "0 2 * * *" \
        --command "$SCRIPT_DIR/run.sh check-all --json > $STATE_DIR/check-all.json" \
        --workdir "$PROJECT_ROOT" \
        --description "Check all persona sources (YouTube, RSS, arXiv, etc.)" || true

    # 3 AM - Ingest new content
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-ingest-all" \
        --cron "0 3 * * *" \
        --command "$SCRIPT_DIR/run.sh ingest --priority HIGH --max-new 50" \
        --workdir "$PROJECT_ROOT" \
        --description "Ingest new content from all sources" || true

    # 4 AM - Extract to QRAs
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-extract" \
        --cron "0 4 * * *" \
        --command "$SCRIPT_DIR/run.sh extract --max 100" \
        --workdir "$PROJECT_ROOT" \
        --description "Extract content to QRAs" || true

    # 4:30 AM - Classify streams
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-classify" \
        --cron "30 4 * * *" \
        --command "$SCRIPT_DIR/run.sh classify-streams" \
        --workdir "$PROJECT_ROOT" \
        --description "Classify Intent vs Persona streams" || true

    # 5 AM - Learn to memory
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-learn" \
        --cron "0 5 * * *" \
        --command "$SCRIPT_DIR/run.sh learn --max 100" \
        --workdir "$PROJECT_ROOT" \
        --description "Learn to memory with taxonomy tags" || true

    # 5:30 AM - Archive + verify edges
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-archive" \
        --cron "30 5 * * *" \
        --command "$SCRIPT_DIR/run.sh archive --hours 24" \
        --workdir "$PROJECT_ROOT" \
        --description "Archive sessions to episodic memory" || true

    # 6 AM - Reflection loop
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-reflect" \
        --cron "0 6 * * *" \
        --command "$SCRIPT_DIR/run.sh reflect --max-gaps 5" \
        --workdir "$PROJECT_ROOT" \
        --description "Research knowledge gaps via dogpile" || true

    # Weekly (Sunday 7 AM) - Train persona models
    "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
        --name "persona-train" \
        --cron "0 7 * * 0" \
        --command "$SCRIPT_DIR/run.sh train" \
        --workdir "$PROJECT_ROOT" \
        --description "Weekly persona model training" || true

    echo ""
    echo "Registered 8 nightly jobs:"
    echo "  2:00 AM  - Check all sources"
    echo "  3:00 AM  - Ingest new content"
    echo "  4:00 AM  - Extract to QRAs"
    echo "  4:30 AM  - Classify streams"
    echo "  5:00 AM  - Learn to memory"
    echo "  5:30 AM  - Archive sessions"
    echo "  6:00 AM  - Reflect on gaps"
    echo "  7:00 AM  - Train models (Sunday only)"
}

# Handle special commands first
case "${1:-help}" in
    register-nightly|register)
        shift
        register_nightly
        exit 0
        ;;
    register-basic)
        shift
        register_basic
        exit 0
        ;;
    help|--help|-h)
        usage
        exit 0
        ;;
    qra-status)
        shift
        # Query ArangoDB for per-scope QRA counts in memory.lessons
        ARANGO_URL="${ARANGO_URL:-http://localhost:8529}"
        ARANGO_DB="${ARANGO_DB:-memory}"
        ARANGO_USER="${ARANGO_USER:-root}"
        ARANGO_PASS="${ARANGO_PASSWORD:-}"

        AQL_QUERY='FOR doc IN lessons COLLECT scope = doc.scope WITH COUNT INTO cnt SORT cnt DESC RETURN { scope, count: cnt }'

        echo "=== QRA Status (DB: $ARANGO_DB, Collection: lessons) ==="
        echo ""

        RESPONSE=$(curl -sf -u "${ARANGO_USER}:${ARANGO_PASS}" \
            -X POST "${ARANGO_URL}/_db/${ARANGO_DB}/_api/cursor" \
            -H "Content-Type: application/json" \
            -d "{\"query\": \"$AQL_QUERY\"}" 2>/dev/null) || {
            echo "Could not reach ArangoDB at $ARANGO_URL" >&2
            echo ""
            echo "Run this AQL manually in Arango web UI:"
            echo "  $AQL_QUERY"
            echo ""
            # Still show process count
            DOC2QRA_COUNT=$(ps aux | grep -c '[d]oc2qra' 2>/dev/null || echo 0)
            echo "Running doc2qra processes: $DOC2QRA_COUNT"
            exit 1
        }

        # Parse JSON response and display with progress bars
        echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
results = data.get('result', [])
if not results:
    print('  No QRAs found in lessons collection')
    sys.exit(0)
total = sum(r['count'] for r in results)
max_count = max(r['count'] for r in results)
print(f'  Total QRAs: {total}')
print(f'  Scopes: {len(results)}')
print()
for r in results:
    scope = r['scope'] or '(no scope)'
    count = r['count']
    bar_len = int(30 * count / max_count) if max_count > 0 else 0
    bar = '█' * bar_len + '░' * (30 - bar_len)
    target = 500
    pct = min(100, int(100 * count / target))
    print(f'  {scope:<25s} {bar} {count:>5d} ({pct}% of {target})')
" 2>/dev/null || {
            echo "  (Could not parse response — raw JSON below)"
            echo "$RESPONSE"
        }

        echo ""
        DOC2QRA_COUNT=$(ps aux | grep -c '[d]oc2qra' 2>/dev/null || echo 0)
        echo "Running doc2qra processes: $DOC2QRA_COUNT"
        if [[ "$DOC2QRA_COUNT" -gt 1 ]]; then
            echo "⚠  WARNING: Multiple doc2qra processes — risk of Chutes self-DoS"
            ps aux | grep '[d]oc2qra' | awk '{print "  PID " $2 ": " $11 " " $12 " " $13}'
        fi
        exit 0
        ;;
    process-count)
        shift
        echo "=== Running doc2qra Processes ==="
        echo ""
        DOC2QRA_PROCS=$(ps aux | grep '[d]oc2qra' 2>/dev/null || true)
        if [[ -z "$DOC2QRA_PROCS" ]]; then
            echo "  No doc2qra processes running"
        else
            COUNT=$(echo "$DOC2QRA_PROCS" | wc -l)
            echo "  Count: $COUNT"
            echo ""
            echo "$DOC2QRA_PROCS" | awk '{printf "  PID %-8s CPU %-5s MEM %-5s CMD %s %s %s %s\n", $2, $3, $4, $11, $12, $13, $14}'
            if [[ "$COUNT" -gt 1 ]]; then
                echo ""
                echo "  ⚠  WARNING: Multiple processes — Chutes limit is 5-6 connections/token"
                echo "  Safe rule: 1 doc2qra process at a time"
            fi
        fi
        exit 0
        ;;
esac

# Delegate all other commands to Python implementation
if [[ -f "$SCRIPT_DIR/monitor.py" ]]; then
    exec uv run --directory "$SCRIPT_DIR" python monitor.py "$@"
fi

echo "ERROR: monitor.py not found"
exit 1
