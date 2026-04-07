#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# run.sh - ingest-yt-history skill wrapper
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'



SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Load .env from common locations
for env_file in "$HOME/.env" "$HOME/workspace/experiments/pi-mono/.env" ".env"; do
    [[ -f "$env_file" ]] && source "$env_file" 2>/dev/null || true
done

case "${1:-help}" in
    ingest|parse)
        shift
        uv run python -m src.ingest "$@"
        ;;
    enrich)
        shift
        uv run python -m src.enrich "$@"
        ;;
    stats)
        shift
        uv run python -m src.stats "$@"
        ;;
    filter)
        shift
        uv run python -m src.filter "$@"
        ;;
    find-music)
        shift
        uv run python -m src.find_music "$@"
        ;;
    profile)
        shift
        uv run python -m src.profile build "$@"
        ;;
    export)
        shift
        uv run python -m src.export "$@"
        ;;
    sync-memory)
        shift
        uv run python -m src.sync_memory "$@"
        ;;
    artist-profiles)
        shift
        uv run python -m src.artist_profiles build "$@"
        ;;
    sanity)
        echo "=== Running sanity checks ==="
        echo ""
        echo "--- Takeout Format ---"
        uv run python sanity/takeout_format.py
        echo ""
        echo "--- YouTube API ---"
        uv run python sanity/youtube_api.py
        ;;
    help|--help|-h)
        cat << 'EOF'
ingest-yt-history - YouTube/YouTube Music history ingestion

COMMANDS:
  ingest <file>     Parse Takeout watch-history.json
  enrich <file>     Enrich with YouTube API metadata
  stats <file>      Show statistics
  filter <file>     Filter by date/service/channel
  find-music <file> Find music by mood, genre, or artist
  profile <file>    Build taste profile
  export <file>     Export for memory integration
  sync-memory <file> Sync music entries to /memory skill (JSONL output)
  artist-profiles <file> Build artist profiles with instrument classification
  sanity            Run sanity checks

EXAMPLES:
  ./run.sh ingest ~/Downloads/Takeout/YouTube*/history/watch-history.json -o history.jsonl
  ./run.sh stats history.jsonl --by-service
  ./run.sh enrich history.jsonl -o enriched.jsonl
  ./run.sh find-music enriched.jsonl --mood melancholic
  ./run.sh find-music enriched.jsonl --artist "Chelsea Wolfe" --limit 5
  ./run.sh profile enriched.jsonl -o taste_profile.json
  ./run.sh export taste_profile.json --format memory
  ./run.sh sync-memory enriched.jsonl -o memory_entries.jsonl --stats
  ./run.sh artist-profiles enriched.jsonl --export-file artist_memory.jsonl
  ./run.sh artist-profiles enriched.jsonl --export-memory  # direct to ArangoDB

ENVIRONMENT:
  YOUTUBE_API_KEY   Required for enrichment
EOF
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
