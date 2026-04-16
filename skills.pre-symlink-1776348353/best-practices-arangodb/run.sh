#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ArangoDB docs-hugo repo
DOCS_REPO="https://github.com/arangodb/docs-hugo.git"
DOCS_CACHE="/mnt/storage12tb/cache/arangodb-docs-hugo"
DOCS_CONTENT_DIR="site/content"  # where the actual markdown lives in docs-hugo

# Composable skills
INGEST_CODE="${SKILLS_DIR}/ingest-code/run.sh"

usage() {
    cat <<'EOF'
best-practices-arangodb: ArangoDB documentation ingestion + best practices

Commands:
  ingest              Clone/pull docs-hugo, ingest markdown into /memory
  ingest --dry-run    Preview what would be ingested without storing
  update              Pull latest changes and ingest only new/modified files
  status              Show docs cache state and last ingestion time

The ingest command clones arangodb/docs-hugo, filters to documentation
markdown (skipping Hugo config, themes, layouts), and stores sections
in /memory via /ingest-code with scope "arangodb-docs".

After ingestion, agents query docs with: /memory recall --q "AQL BM25 scoring"
EOF
}

_ensure_cache() {
    if [[ -d "$DOCS_CACHE/.git" ]]; then
        echo "Updating docs-hugo cache..."
        git -C "$DOCS_CACHE" pull --ff-only 2>&1 | head -5
    else
        echo "Cloning docs-hugo (first time)..."
        mkdir -p "$(dirname "$DOCS_CACHE")"
        git clone --depth 1 "$DOCS_REPO" "$DOCS_CACHE"
    fi
}

cmd_ingest() {
    local dry_run=""
    [[ "${1:-}" == "--dry-run" ]] && dry_run="--dry-run"

    _ensure_cache

    local content_dir="$DOCS_CACHE/$DOCS_CONTENT_DIR"
    if [[ ! -d "$content_dir" ]]; then
        echo "ERROR: Content directory not found: $content_dir"
        echo "Repo structure may have changed. Check: ls $DOCS_CACHE"
        exit 1
    fi

    local md_count
    md_count=$(find "$content_dir" -name '*.md' -not -path '*/node_modules/*' | wc -l)
    echo "Found ${md_count} markdown files in ${content_dir}"

    echo "Ingesting via /ingest-code (scope: arangodb-docs)..."
    "$INGEST_CODE" scan "$content_dir" \
        --glob '*.md' \
        --scope arangodb-docs \
        $dry_run

    if [[ -z "$dry_run" ]]; then
        # Record last ingestion time
        date -Iseconds > "$DOCS_CACHE/.last-ingested"
        echo "Done. Query with: /memory recall --q \"your ArangoDB question\""
    fi
}

cmd_update() {
    _ensure_cache

    local content_dir="$DOCS_CACHE/$DOCS_CONTENT_DIR"
    local since="1d"

    echo "Re-ingesting files modified in last ${since}..."
    "$INGEST_CODE" rescan \
        --since "$since" \
        -c "$content_dir" \
        --scope arangodb-docs

    date -Iseconds > "$DOCS_CACHE/.last-ingested"
    echo "Incremental update complete."
}

cmd_status() {
    if [[ ! -d "$DOCS_CACHE/.git" ]]; then
        echo "Not cloned yet. Run: ./run.sh ingest"
        return 1
    fi

    local commit
    commit=$(git -C "$DOCS_CACHE" log -1 --format='%h %s (%ar)')
    local md_count
    md_count=$(find "$DOCS_CACHE/$DOCS_CONTENT_DIR" -name '*.md' 2>/dev/null | wc -l)

    echo "Cache: $DOCS_CACHE"
    echo "Latest commit: $commit"
    echo "Markdown files: $md_count"

    if [[ -f "$DOCS_CACHE/.last-ingested" ]]; then
        echo "Last ingested: $(cat "$DOCS_CACHE/.last-ingested")"
    else
        echo "Last ingested: never"
    fi
}

case "${1:-help}" in
    ingest)   shift; cmd_ingest "$@" ;;
    update)   cmd_update ;;
    status)   cmd_status ;;
    help|*)   usage ;;
esac
