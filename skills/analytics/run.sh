#!/usr/bin/env bash
# Analytics skill - Data science insights

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure dependencies
if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Sync dependencies if needed
if [[ ! -d ".venv" ]]; then
    uv sync --quiet
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    # Schema discovery and recommendations (START HERE)
    describe)
        uv run python -m src.cli describe "$@"
        ;;
    # Flexible analysis
    group-by)
        uv run python -m src.cli group-by "$@"
        ;;
    stats)
        uv run python -m src.cli stats "$@"
        ;;
    chart)
        uv run python -m src.cli chart "$@"
        ;;
    # Timestamped data specific
    insights)
        uv run python -m src.cli insights "$@"
        ;;
    trends)
        uv run python -m src.cli trends "$@"
        ;;
    sessions)
        uv run python -m src.cli sessions "$@"
        ;;
    time-patterns)
        uv run python -m src.cli time-patterns "$@"
        ;;
    evolution)
        uv run python -m src.cli evolution "$@"
        ;;
    export)
        uv run python -m src.cli export "$@"
        ;;
    report)
        # Full report for Horus
        uv run python -m src.cli insights "$@" --horus
        ;;
    sanity)
        ./sanity.sh
        ;;
    help|--help|-h)
        cat << 'EOF'
analytics: Flexible data science analytics with auto chart recommendations

DISCOVERY (start here for any dataset):
  describe <file>      Schema discovery + chart recommendations

FLEXIBLE ANALYSIS (works with any data):
  group-by <file>      Group by any column with aggregation
  stats <file>         Numerical statistics and correlations
  chart <file>         Generate chart spec for create-figure

TIMESTAMPED DATA (for ingest-* outputs):
  insights <file>      Full analysis summary
  trends <file>        Viewing trends over time
  sessions <file>      Session detection and binge analysis
  time-patterns <file> Time-of-day distribution
  evolution <file>     Content preference evolution

OUTPUT:
  export <file>        Batch export for create-figure
  report <file>        Horus-style narrative report

OPTIONS:
  -j, --json           Output as JSON
  --for-figure         Export in create-figure format
  -b, --by COL         Column to group by
  -a, --agg COL        Column to aggregate
  -f, --func FUNC      Aggregation: count, sum, mean, min, max

WORKFLOW (any dataset → visualization):
  1. ./run.sh describe data.jsonl          # Discover schema, see recommendations
  2. ./run.sh chart data.jsonl --name X -o chart.json  # Generate chart data
  3. create-figure metrics -i chart.json   # Render PDF/PNG

EXAMPLES:
  # Discover what's in the data
  ./run.sh describe ~/.pi/ingest-yt-history/history.jsonl

  # Flexible grouping
  ./run.sh group-by data.jsonl --by channel --for-figure -o by_channel.json
  ./run.sh group-by data.jsonl --by category --agg price --func sum

  # Generate recommended chart
  ./run.sh chart data.jsonl --name distribution_channel -o chart.json

  # Then use create-figure
  cd .agent/skills/create-figure
  ./run.sh metrics -i /path/to/chart.json --type bar -o chart.pdf
EOF
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
