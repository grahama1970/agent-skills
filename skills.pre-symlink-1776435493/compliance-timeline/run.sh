#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UV="${UV:-uv}"

# ── Memory-first: route all DB access through /memory ─────────────────
MEMORY_RUN="${SCRIPT_DIR}/../memory/run.sh"

usage() {
    cat <<'EOF'
compliance-timeline — chronological audit view of compliance changes

USAGE:
    ./run.sh show [--days N] [--scope NAME] [--dry-run]
    ./run.sh diff --from DATE --to DATE [--dry-run]

SUBCOMMANDS:
    show    Display recent compliance changes (default: last 30 days)
    diff    Show changes between two explicit dates

FLAGS:
    --days N      Number of days back to query (default: 30, show only)
    --scope NAME  Filter to a specific scope/domain
    --from DATE   Start date, ISO-8601 (diff only)
    --to DATE     End date, ISO-8601 (diff only)
    --dry-run     Emit sample data without querying ArangoDB
EOF
    exit 0
}

[[ $# -eq 0 ]] && usage

SUBCMD="$1"; shift

DAYS=30
SCOPE=""
FROM_DATE=""
TO_DATE=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --days)    DAYS="$2"; shift 2 ;;
        --scope)   SCOPE="$2"; shift 2 ;;
        --from)    FROM_DATE="$2"; shift 2 ;;
        --to)      TO_DATE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h) usage ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
done

# ── Dry-run sample data ──────────────────────────────────────────────
emit_dry_run() {
    local scope_filter="$1"
    $UV run --project "$SCRIPT_DIR" python3 - "$scope_filter" <<'PYEOF'
import sys, json

scope_filter = sys.argv[1] if len(sys.argv) > 1 else ""

SAMPLE = [
    {"ts": "2026-01-05T09:15:00Z", "action": "CREATE", "scope": "sparta",        "doc": "ctrl/AC-2",                  "detail": "Added access control baseline from NIST 800-171"},
    {"ts": "2026-01-12T11:42:00Z", "action": "UPDATE", "scope": "manufacturing",  "doc": "proc/welding-spec-7A",       "detail": "Tolerance changed 0.05mm -> 0.03mm per ECN-4421"},
    {"ts": "2026-01-18T14:08:00Z", "action": "LINK",   "scope": "manufacturing",  "doc": "edge/vendor-alloy-batch-91", "detail": "Linked Ti-6Al-4V batch to CNC-07 output records"},
    {"ts": "2026-01-25T08:30:00Z", "action": "FLAG",   "scope": "drift",          "doc": "drift/F16-F35-AC-2",         "detail": "Control AC-2 diverged between F-16 rev3 and F-35 rev1"},
    {"ts": "2026-02-02T16:55:00Z", "action": "UPDATE", "scope": "sparta",         "doc": "ctrl/SI-7",                  "detail": "Software integrity verification updated for CMMC L3"},
    {"ts": "2026-02-10T10:20:00Z", "action": "DELETE", "scope": "manufacturing",  "doc": "proc/heat-treat-legacy",     "detail": "Superseded by proc/heat-treat-v2 per QA-2026-009"},
    {"ts": "2026-02-14T13:45:00Z", "action": "CREATE", "scope": "sparta",         "doc": "ctrl/AU-12",                 "detail": "Audit generation control added from STIG V2R1"},
    {"ts": "2026-02-18T17:10:00Z", "action": "LINK",   "scope": "drift",          "doc": "edge/F22-F35-thermal-spec",  "detail": "Cross-program thermal tolerance edge verified"},
]

if scope_filter:
    SAMPLE = [e for e in SAMPLE if e["scope"] == scope_filter]

# Header
hdr = f"{'TIMESTAMP':<22}| {'ACTION':<9}| {'SCOPE':<16}| {'DOCUMENT':<30}| DETAIL"
sep = f"{'-'*22}+{'-'*10}+{'-'*17}+{'-'*31}+{'-'*45}"
print(hdr)
print(sep)
for e in SAMPLE:
    print(f"{e['ts']:<22}| {e['action']:<9}| {e['scope']:<16}| {e['doc']:<30}| {e['detail']}")
PYEOF
}

# ── Memory-first query via /memory sample ────────────────────────────
query_memory() {
    local collection="$1"
    local limit="$2"
    local filter_expr="$3"
    local scope_filter="$4"

    local cmd=("$MEMORY_RUN" "sample" "--collection" "$collection" "--limit" "$limit")
    if [[ -n "$filter_expr" ]]; then
        cmd+=("--filter" "$filter_expr")
    fi

    local raw
    raw=$("${cmd[@]}" 2>&1)
    if [ $? -ne 0 ]; then
        echo "FATAL: /memory unavailable: $raw" >&2
        exit 1
    fi

    # Format the JSON output as timeline table
    $UV run --project "$SCRIPT_DIR" python3 - "$raw" "$scope_filter" <<'PYEOF'
import sys, json

raw_json = sys.argv[1]
scope_filter = sys.argv[2] if len(sys.argv) > 2 else ""

try:
    data = json.loads(raw_json)
except json.JSONDecodeError:
    print("(no results)")
    sys.exit(0)

rows = data.get("items", [])
if scope_filter:
    rows = [r for r in rows if r.get("scope") == scope_filter]

if not rows:
    print("(no results)")
    sys.exit(0)

hdr = f"{'TIMESTAMP':<22}| {'ACTION':<9}| {'SCOPE':<16}| {'DOCUMENT':<30}| DETAIL"
sep = f"{'-'*22}+{'-'*10}+{'-'*17}+{'-'*31}+{'-'*45}"
print(hdr)
print(sep)
for r in rows:
    ts     = str(r.get("ts", ""))[:22]
    action = r.get("action", "?")
    scope  = r.get("scope", "")
    doc    = r.get("doc", "")
    detail = r.get("detail", "")
    print(f"{ts:<22}| {action:<9}| {scope:<16}| {doc:<30}| {detail}")
PYEOF
}

# ── Subcommand: show ─────────────────────────────────────────────────
cmd_show() {
    if $DRY_RUN; then
        emit_dry_run "$SCOPE"
        return
    fi

    # Query lesson_revisions and edge_revisions via /memory sample
    # Limit to reasonable batch, sorted by recency (default sort)
    local limit=$(( DAYS * 20 ))  # estimate ~20 changes/day max
    query_memory "lesson_revisions" "$limit" "" "$SCOPE"
}

# ── Subcommand: diff ─────────────────────────────────────────────────
cmd_diff() {
    if [[ -z "$FROM_DATE" || -z "$TO_DATE" ]]; then
        echo "Error: --from and --to are required for diff" >&2
        exit 1
    fi

    if $DRY_RUN; then
        emit_dry_run "$SCOPE"
        return
    fi

    # Query via /memory sample with date filter
    local filter="doc.ts >= \"${FROM_DATE}T00:00:00Z\" AND doc.ts <= \"${TO_DATE}T23:59:59Z\""
    query_memory "lesson_revisions" "1000" "$filter" "$SCOPE"
}

# ── Dispatch ─────────────────────────────────────────────────────────
case "$SUBCMD" in
    show) cmd_show ;;
    diff) cmd_diff ;;
    -h|--help) usage ;;
    *) echo "Unknown subcommand: $SUBCMD" >&2; exit 1 ;;
esac
