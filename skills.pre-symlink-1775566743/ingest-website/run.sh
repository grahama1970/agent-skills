#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<EOF
Usage: run.sh <command> [options]

Commands:
  ingest <URL>        Crawl website and store as RAG resource
  ingest --urls FILE  Ingest specific URLs from file
  report <SCOPE>      Show ingestion diagnostics for a scope

Ingest Options:
  --scope NAME        Memory scope (default: research)
  --images            Download images to output dir
  --output-dir DIR    Save fetched pages as local markdown/images
  --max-pages N       Max pages to fetch (default: 50)
  --depth N           Max crawl depth (default: 2)
  --dry-run           Fetch + save locally, skip memory storage
  --no-qra            Store raw text chunks, skip QRA extraction
  --delay MS          Delay between requests in ms (default: 500)

Report Options:
  --json              Output as JSON (for agent consumption)

Examples:
  run.sh ingest https://sparta.aerospace.org/resources --scope sparta
  run.sh ingest https://example.com/docs --scope research --images --output-dir ./ref/
  run.sh ingest --urls urls.txt --scope research
  run.sh ingest https://example.com/docs --dry-run --output-dir ./docs/
  run.sh report sparta
  run.sh report sparta --json
EOF
}

case "${1:-}" in
  ingest)
    shift
    unset VIRTUAL_ENV 2>/dev/null || true
    cd "$SCRIPT_DIR"
    uv run python ingest_website.py ingest "$@"
    ;;
  report)
    shift
    unset VIRTUAL_ENV 2>/dev/null || true
    cd "$SCRIPT_DIR"
    uv run python ingest_website.py report "$@"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1" >&2
    usage
    exit 1
    ;;
esac
