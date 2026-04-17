#!/bin/bash
set -euo pipefail

# Horus Lore Enrichment Pipeline
# Orchestrates ingestion, batch LLM enrichment, and graph edge creation.
# Scheduled for 9pm EST daily.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Paths
YOUTUBE_DIR="${PI_MONO_ROOT:-$HOME/workspace/experiments/pi-mono}/run/youtube-transcripts"
AUDIOBOOK_DIR="$HOME/clawd/library/books"
BATCH_DIR="/tmp/horus_lore_enrich"
BATCH_FILE="$BATCH_DIR/enrich_batch.jsonl"
RESULTS_FILE="$BATCH_DIR/enrich_results.jsonl"

# Ensure UV is available
UV="${UV:-$(which uv 2>/dev/null || echo "uv")}"

echo "[$(date)] Starting Horus Lore Pipeline..."

# 1. Ingest (Sync source files to ArangoDB)
echo "[1/4] Ingesting from source directories..."
$UV run horus_lore_ingest.py all \
    --youtube-dir "$YOUTUBE_DIR" \
    --audiobook-dir "$AUDIOBOOK_DIR"

# 2. Prepare Batch (Generate JSONL for LLM)
echo "[2/4] Preparing enrichment batch..."
mkdir -p "$BATCH_DIR"
rm -f "$BATCH_FILE" "$RESULTS_FILE" # Clean start

# Limit 2000 documents per run to manageable chunks
$UV run horus_lore_ingest.py enrich --limit 2000

if [[ ! -f "$BATCH_FILE" || ! -s "$BATCH_FILE" ]]; then
    echo "No documents need enrichment. Pipeline complete."
    exit 0
fi

# 3. Run Batch (Execute LLM calls via scillm)
echo "[3/4] Running batch completion via scillm..."
# scillm/batch.py batch --input ... --output ... --json
$UV run ../scillm/batch.py batch \
    --input "$BATCH_FILE" \
    --output "$RESULTS_FILE" \
    --json \
    --concurrency 10 \
    --timeout 60

# 4. Apply Results & Create Edges
if [[ -f "$RESULTS_FILE" && -s "$RESULTS_FILE" ]]; then
    echo "[4/4] Applying enrichment results..."
    $UV run horus_lore_ingest.py apply-enrichment --results "$RESULTS_FILE"
    
    echo "Creating plot-point edges..."
    $UV run horus_lore_ingest.py plot-edges
else
    echo "Error: Results file missing or empty."
    exit 1
fi

echo "[$(date)] Pipeline completed successfully."
