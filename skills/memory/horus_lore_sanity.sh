#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Testing horus_lore_ingest modular CLI..."

# Activate venv if it exists
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Core CLI help
python "$SCRIPT_DIR/horus_lore_cli.py" --help >/dev/null && echo "OK main --help"

# Subcommands help
python "$SCRIPT_DIR/horus_lore_cli.py" youtube --help >/dev/null && echo "OK youtube --help"
python "$SCRIPT_DIR/horus_lore_cli.py" audiobook --help >/dev/null && echo "OK audiobook --help"
python "$SCRIPT_DIR/horus_lore_cli.py" all --help >/dev/null && echo "OK all --help"
python "$SCRIPT_DIR/horus_lore_cli.py" status --help >/dev/null && echo "OK status --help"
python "$SCRIPT_DIR/horus_lore_cli.py" setup --help >/dev/null && echo "OK setup --help"
python "$SCRIPT_DIR/horus_lore_cli.py" edges --help >/dev/null && echo "OK edges --help"
python "$SCRIPT_DIR/horus_lore_cli.py" plot-edges --help >/dev/null && echo "OK plot-edges --help"
python "$SCRIPT_DIR/horus_lore_cli.py" query --help >/dev/null && echo "OK query --help"
python "$SCRIPT_DIR/horus_lore_cli.py" persona --help >/dev/null && echo "OK persona --help"
python "$SCRIPT_DIR/horus_lore_cli.py" enrich --help >/dev/null && echo "OK enrich --help"
python "$SCRIPT_DIR/horus_lore_cli.py" apply-enrichment --help >/dev/null && echo "OK apply-enrichment --help"

# Module imports (verify no import errors)
echo ""
echo "Testing module imports..."
python -c "from horus_lore_config import ENTITIES, extract_entities; print('OK horus_lore_config')"
python -c "from horus_lore_chunking import chunk_text, chunk_audiobook; print('OK horus_lore_chunking')"
python -c "from horus_lore_embeddings import get_embedder; print('OK horus_lore_embeddings')"
python -c "from horus_lore_storage import get_db, ensure_collections; print('OK horus_lore_storage')"
python -c "from horus_lore_query import query_lore, retrieve_persona_context; print('OK horus_lore_query')"
python -c "from horus_lore_ingest import ingest_youtube_transcript, ingest_audiobook; print('OK horus_lore_ingest')"
python -c "from horus_lore_enrichment import prepare_enrichment_batch; print('OK horus_lore_enrichment')"

# Count lines in each module to verify < 500 lines
echo ""
echo "Module line counts (all should be < 500):"
for f in "$SCRIPT_DIR"/horus_lore_*.py; do
    lines=$(wc -l < "$f")
    name=$(basename "$f")
    if [ "$lines" -gt 500 ]; then
        echo "FAIL $name: $lines lines (exceeds 500)"
        exit 1
    else
        echo "OK $name: $lines lines"
    fi
done

echo ""
echo "All sanity checks passed!"
