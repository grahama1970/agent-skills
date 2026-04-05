#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
MEMORY_RUN="${SKILLS_DIR}/memory/run.sh"
SOURCES_FILE="${SCRIPT_DIR}/sources.json"

if [[ $# -lt 1 ]]; then
    echo "Usage:"
    echo "  $0 archive <transcript.json>     - Archive a single session"
    echo "  $0 archive-recent [--hours N]    - Archive recent unprocessed sessions from all registered sources"
    echo "  $0 analyze <session_id>          - Deep LLM analysis of an archived session"
    echo "  $0 research-gaps                 - List sessions with unresolved gaps"
    echo "  $0 list-unresolved               - List pending sessions for reflection"
    echo "  $0 resolve <session_id>          - Mark session resolved"
    echo "  $0 register <name> <path> <glob> - Register a transcript source (IDE/CLI)"
    echo "  $0 sources                       - List registered transcript sources"
    exit 1
fi

case "${1}" in
    register)
        # Register a new transcript source
        # Usage: run.sh register claude ~/.claude/projects "**/*.jsonl"
        #        run.sh register codex ~/.codex/sessions "**/*.jsonl"
        #        run.sh register pi ~/.pi/agent "**/*.jsonl"
        shift
        NAME="${1:?Usage: register <name> <path> <glob>}"
        SRC_PATH="${2:?Usage: register <name> <path> <glob>}"
        GLOB="${3:-**/*.jsonl}"
        shift 3 2>/dev/null || true

        # Initialize sources file if missing
        if [[ ! -f "$SOURCES_FILE" ]]; then
            echo '{"sources": []}' > "$SOURCES_FILE"
        fi

        # Add or update source
        uv run --project "${SCRIPT_DIR}" python -c "
import json, sys
with open('$SOURCES_FILE') as f:
    data = json.load(f)
sources = data.get('sources', [])
# Update existing or append
found = False
for s in sources:
    if s['name'] == '$NAME':
        s['path'] = '$SRC_PATH'
        s['glob'] = '$GLOB'
        found = True
        break
if not found:
    sources.append({'name': '$NAME', 'path': '$SRC_PATH', 'glob': '$GLOB', 'enabled': True})
data['sources'] = sources
with open('$SOURCES_FILE', 'w') as f:
    json.dump(data, f, indent=2)
print(f'Registered source: $NAME -> $SRC_PATH ($GLOB)')
"
        ;;

    sources)
        # List registered sources
        if [[ -f "$SOURCES_FILE" ]]; then
            uv run --project "${SCRIPT_DIR}" python -c "
import json
with open('$SOURCES_FILE') as f:
    data = json.load(f)
for s in data.get('sources', []):
    status = 'enabled' if s.get('enabled', True) else 'disabled'
    print(f\"  {s['name']:15s} {s['path']:50s} {s['glob']:20s} [{status}]\")
"
        else
            echo "No sources registered. Use: run.sh register <name> <path> <glob>"
        fi
        ;;

    analyze)
        # Deep LLM analysis of an archived session
        shift
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/session_analysis.py" analyze "$@"
        ;;

    research-gaps)
        # List sessions with unresolved gaps suitable for dogpile
        shift
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/session_analysis.py" list-gaps "$@"
        ;;

    archive-recent)
        shift
        HOURS=24
        ANALYZE=1
        MAX_DOGPILE=3
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --hours) HOURS="$2"; shift 2 ;;
                --no-analyze) ANALYZE=0; shift ;;
                --max-dogpile) MAX_DOGPILE="$2"; shift 2 ;;
                *) shift ;;
            esac
        done

        # Build default sources if none registered
        if [[ ! -f "$SOURCES_FILE" ]]; then
            echo '{"sources": [
              {"name": "claude", "path": "'"${HOME}"'/.claude/projects", "glob": "**/*.jsonl", "enabled": true},
              {"name": "codex", "path": "'"${HOME}"'/.codex/sessions", "glob": "**/*.jsonl", "enabled": true}
            ]}' > "$SOURCES_FILE"
            echo "[episodic] Created default sources.json with claude + codex"
        fi

        ARCHIVED=0
        SKIPPED=0
        ERRORS=0
        TOTAL_FOUND=0
        ANALYZED=0
        ANALYSIS_ERRORS=0

        echo "[episodic] Scanning registered sources for sessions from last ${HOURS}h..."

        # Read sources and scan each
        while IFS= read -r source_line; do
            SRC_NAME=$(echo "$source_line" | cut -d'|' -f1)
            SRC_PATH=$(echo "$source_line" | cut -d'|' -f2)
            SRC_GLOB=$(echo "$source_line" | cut -d'|' -f3)
            SRC_ENABLED=$(echo "$source_line" | cut -d'|' -f4)

            if [[ "$SRC_ENABLED" != "True" ]]; then
                echo "[episodic] Skipping disabled source: $SRC_NAME"
                continue
            fi

            if [[ ! -d "$SRC_PATH" ]]; then
                echo "[episodic] Source path not found: $SRC_NAME ($SRC_PATH)"
                continue
            fi

            echo "[episodic] Scanning source: $SRC_NAME ($SRC_PATH)"

            # Find recent .jsonl files
            while IFS= read -r transcript; do
                TOTAL_FOUND=$((TOTAL_FOUND + 1))
                SESSION_ID="${SRC_NAME}:$(basename "$transcript" .jsonl)"

                # Check if already archived (by dedupe on session_id)
                ALREADY=$("${MEMORY_RUN}" search --query "${SESSION_ID}" --collection agent_conversations --limit 1 2>/dev/null \
                    | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('items',[])))" 2>/dev/null || echo "0")

                if [[ "$ALREADY" -gt 0 ]]; then
                    SKIPPED=$((SKIPPED + 1))
                    continue
                fi

                echo "[episodic]   Archiving: $SESSION_ID"
                if uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/archive_episode.py" archive "$transcript" 2>&1; then
                    ARCHIVED=$((ARCHIVED + 1))
                    # Trigger session analysis if enabled
                    if [[ "$ANALYZE" == "1" ]]; then
                        echo "[episodic]   Analyzing: $SESSION_ID"
                        if uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/session_analysis.py" analyze \
                            "$SESSION_ID" --max-dogpile "$MAX_DOGPILE" --json-stream 2>&1; then
                            ANALYZED=$((ANALYZED + 1))
                        else
                            echo "[episodic]   Analysis failed for $SESSION_ID (non-fatal)"
                            ANALYSIS_ERRORS=$((ANALYSIS_ERRORS + 1))
                        fi
                    fi
                else
                    ERRORS=$((ERRORS + 1))
                fi
            done < <(find "$SRC_PATH" -name "*.jsonl" -mmin "-$((HOURS * 60))" -type f 2>/dev/null)

        done < <(uv run --project "${SCRIPT_DIR}" python -c "
import json
with open('$SOURCES_FILE') as f:
    data = json.load(f)
for s in data.get('sources', []):
    print(f\"{s['name']}|{s['path']}|{s['glob']}|{s.get('enabled', True)}\")
" 2>/dev/null)

        echo ""
        echo "[episodic] === NIGHTLY ARCHIVE COMPLETE ==="
        echo "  Found:     $TOTAL_FOUND transcripts"
        echo "  Archived:  $ARCHIVED"
        echo "  Analyzed:  $ANALYZED"
        echo "  Skipped:   $SKIPPED (already archived)"
        echo "  Errors:    $ERRORS (archive) / $ANALYSIS_ERRORS (analysis)"

        # List unresolved for reflection
        echo ""
        echo "[episodic] Unresolved sessions for reflection:"
        uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/archive_episode.py" list-unresolved 2>&1 || true
        ;;

    archive-checkpointed)
        # Archive only sessions that have been checkpointed (with transcript_paths).
        # Queries the checkpoints collection via memory daemon for recent entries
        # that have transcript_paths, then archives only those specific files.
        # This replaces the blind filesystem scan that caused nightly timeouts.
        shift
        HOURS=24
        ANALYZE=0
        MAX_DOGPILE=3
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --hours) HOURS="$2"; shift 2 ;;
                --analyze) ANALYZE=1; shift ;;
                --max-dogpile) MAX_DOGPILE="$2"; shift 2 ;;
                *) shift ;;
            esac
        done

        ARCHIVED=0
        SKIPPED=0
        ERRORS=0
        TOTAL_FOUND=0
        ANALYZED=0
        ANALYSIS_ERRORS=0

        echo "[episodic] Querying checkpoints from last ${HOURS}h for transcript_paths..."

        # Query memory daemon for recent checkpoints with transcript_paths
        CHECKPOINT_DATA=$(python3 -c "
import json, sys, time
try:
    import httpx
except ImportError:
    sys.exit(0)

sock = '/run/user/1000/embry/memory.sock'
tcp = 'http://127.0.0.1:8601'
import os
if os.path.exists(sock):
    transport = httpx.HTTPTransport(uds=sock)
    base = 'http://localhost'
else:
    transport = None
    base = tcp

cutoff = time.time() - ($HOURS * 3600)
with httpx.Client(transport=transport, timeout=30.0) as client:
    resp = client.post(f'{base}/list', json={
        'collection': 'checkpoints',
        'limit': 100,
        'filters': {}
    })
    data = resp.json()
    docs = data.get('documents', data.get('items', []))
    results = []
    for doc in docs:
        ts = doc.get('updated_at', doc.get('created_at', 0))
        if isinstance(ts, str):
            from datetime import datetime
            try:
                ts = datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
            except (ValueError, TypeError): ts = 0
        paths = doc.get('transcript_paths', [])
        skills = doc.get('skills_used', [])
        if ts >= cutoff and paths:
            results.append({
                '_key': doc.get('_key', ''),
                'topic': doc.get('topic', ''),
                'grade': doc.get('grade', ''),
                'outcome': doc.get('outcome', ''),
                'scope': doc.get('scope', ''),
                'resume': doc.get('resume', ''),
                'skills_used': skills,
                'transcript_paths': paths,
            })
    print(json.dumps(results))
" 2>/dev/null) || CHECKPOINT_DATA="[]"

        if [[ -z "$CHECKPOINT_DATA" || "$CHECKPOINT_DATA" == "[]" ]]; then
            echo "[episodic] No recent checkpoints with transcript_paths found."
            echo "[episodic] Hint: /checkpoint save now records transcript_paths automatically."
            exit 0
        fi

        echo "[episodic] Found checkpoints with transcripts, processing..."

        # Locate chain-learn for skill chain storage
        CHAIN_LEARN="${SKILLS_DIR}/memory/run.sh"
        CHAINS_STORED=0

        # Process each checkpoint's transcript files
        # Emit: _key|topic|grade|outcome|skills_csv|transcript_path
        echo "$CHECKPOINT_DATA" | python3 -c "
import json, sys
for cp in json.load(sys.stdin):
    skills_csv = ','.join(cp.get('skills_used', []))
    outcome = cp.get('outcome', '')
    for p in cp.get('transcript_paths', []):
        print(f\"{cp['_key']}|{cp.get('topic','')}|{cp.get('grade','')}|{outcome}|{skills_csv}|{p}\")
" 2>/dev/null | while IFS='|' read -r CP_KEY CP_TOPIC CP_GRADE CP_OUTCOME CP_SKILLS TRANSCRIPT; do
            TOTAL_FOUND=$((TOTAL_FOUND + 1))

            if [[ ! -f "$TRANSCRIPT" ]]; then
                echo "[episodic]   File missing: $TRANSCRIPT"
                continue
            fi

            SESSION_ID="checkpoint:${CP_KEY}:$(basename "$TRANSCRIPT" .jsonl)"

            # Dedup check
            ALREADY=$("${MEMORY_RUN}" search --query "${SESSION_ID}" --collection agent_conversations --limit 1 2>/dev/null \
                | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('items',[])))" 2>/dev/null || echo "0")

            if [[ "$ALREADY" -gt 0 ]]; then
                SKIPPED=$((SKIPPED + 1))
                continue
            fi

            echo "[episodic]   Archiving: ${CP_TOPIC:0:50} (${CP_GRADE}) → $(basename "$TRANSCRIPT")"
            if uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/archive_episode.py" archive "$TRANSCRIPT" 2>&1; then
                ARCHIVED=$((ARCHIVED + 1))

                # Store skill chain for /recommend-skill-chain training
                # The chain doc needs rich problem/solution text for BM25 + embedding recall
                if [[ -n "$CP_SKILLS" && -x "$CHAIN_LEARN" ]]; then
                    SUCCESS_FLAG="--success"
                    if [[ "$CP_OUTCOME" == "failed" ]]; then
                        SUCCESS_FLAG="--no-success"
                    fi
                    if "$CHAIN_LEARN" chain-learn \
                        --skills "$CP_SKILLS" \
                        --task "$CP_TOPIC" \
                        --source "production" \
                        $SUCCESS_FLAG 2>/dev/null; then
                        CHAINS_STORED=$((CHAINS_STORED + 1))
                        echo "[episodic]   Stored skill chain: $CP_SKILLS ($CP_OUTCOME)"
                    fi
                fi

                if [[ "$ANALYZE" == "1" ]]; then
                    echo "[episodic]   Analyzing: $SESSION_ID"
                    if uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/session_analysis.py" analyze \
                        "$SESSION_ID" --max-dogpile "$MAX_DOGPILE" --json-stream 2>&1; then
                        ANALYZED=$((ANALYZED + 1))
                    else
                        ANALYSIS_ERRORS=$((ANALYSIS_ERRORS + 1))
                    fi
                fi
            else
                ERRORS=$((ERRORS + 1))
            fi
        done

        echo ""
        echo "[episodic] === CHECKPOINT-DRIVEN ARCHIVE COMPLETE ==="
        echo "  Found:     $TOTAL_FOUND transcripts from checkpoints"
        echo "  Archived:  $ARCHIVED"
        echo "  Chains:    $CHAINS_STORED stored for /recommend-skill-chain"
        echo "  Analyzed:  $ANALYZED"
        echo "  Skipped:   $SKIPPED (already archived)"
        echo "  Errors:    $ERRORS (archive) / $ANALYSIS_ERRORS (analysis)"
        ;;

    *)
        # Default: pass through to archive_episode.py
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/archive_episode.py" "$@"
        ;;
esac
