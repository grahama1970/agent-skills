#!/usr/bin/env bash
# Sanity checks for /hum skill (Orpheus + Seed-VC v2)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== /hum Sanity Checks (v2) ==="
echo ""

PASS=0
FAIL=0
WARN=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS  ${label}"
        ((PASS++)) || true
    else
        echo "  FAIL  ${label}"
        ((FAIL++)) || true
    fi
}

warn() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS  ${label}"
        ((PASS++)) || true
    else
        echo "  WARN  ${label}"
        ((WARN++)) || true
    fi
}

echo "[1/7] System tools"
check "ffmpeg" command -v ffmpeg
check "ffprobe" command -v ffprobe
warn  "pw-play" command -v pw-play

echo ""
echo "[2/7] Required skills"
check "create-stems" test -f "${SKILLS_ROOT}/create-stems/run.sh"
check "tts-voice" test -f "${SKILLS_ROOT}/tts-voice/run.sh"
check "voice-segment-selector" test -f "${SKILLS_ROOT}/voice-segment-selector/run.sh"
warn  "ingest-youtube" test -f "${SKILLS_ROOT}/ingest-youtube/run.sh"

echo ""
echo "[3/7] Python deps (hum venv)"
cd "$SCRIPT_DIR"
if uv sync --quiet 2>/dev/null; then
    echo "  PASS  uv sync"
    ((PASS++)) || true
else
    echo "  FAIL  uv sync"
    ((FAIL++)) || true
fi

check "basic-pitch import" uv run python -c "import basic_pitch"
check "pretty_midi import" uv run python -c "import pretty_midi"
check "httpx import" uv run python -c "import httpx"

echo ""
echo "[4/7] Orpheus infer service"
ORPHEUS_URL="${ORPHEUS_INFER_URL:-http://127.0.0.1:${ORPHEUS_INFER_PORT:-8767}}"
HEALTH_BODY="$(curl -fsS "${ORPHEUS_URL}/health" 2>/dev/null || true)"
if [[ -n "$HEALTH_BODY" ]] && python3 -c "import sys,json; d=json.load(sys.stdin); raise SystemExit(0 if d.get('status')=='ok' else 1)" <<<"$HEALTH_BODY" 2>/dev/null; then
    echo "  PASS  Orpheus infer healthy (${ORPHEUS_URL})"
    ((PASS++)) || true
else
    echo "  WARN  Orpheus infer not running (${ORPHEUS_URL}) — run: skills/tts-voice/run.sh docker-up"
    ((WARN++)) || true
fi

echo ""
echo "[5/7] Seed-VC"
SEEDVC_DIR="${SEEDVC_DIR:-/mnt/storage12tb/tools/seed-vc}"
if [[ -f "${SEEDVC_DIR}/inference.py" ]]; then
    echo "  PASS  Seed-VC inference.py (${SEEDVC_DIR})"
    ((PASS++)) || true
else
    echo "  WARN  Seed-VC missing at ${SEEDVC_DIR}"
    echo "        git clone https://github.com/Plachtaa/seed-vc ${SEEDVC_DIR}"
    ((WARN++)) || true
fi

echo ""
echo "[6/7] Storage + persona Orpheus checkpoints"
check "12TB mount" test -d /mnt/storage12tb/media/personas
CHECKPOINTS="/mnt/storage12tb/skills/voice-segment-selector/checkpoints"
PERSONA_COUNT=0
for ckpt in "$CHECKPOINTS"/*_orpheus_lora; do
    [[ -d "$ckpt" ]] || continue
    persona=$(basename "$ckpt" | sed 's/_orpheus_lora$//')
    ((PERSONA_COUNT++)) || true
    echo "  ── ${persona} (Orpheus) ──"
    if [[ -d "${ckpt}/lora" ]]; then
        echo "    PASS  LoRA adapter present"
        ((PASS++)) || true
    else
        echo "    WARN  LoRA missing"
        ((WARN++)) || true
    fi
    cache_dir="/mnt/storage12tb/media/personas/${persona}/hum-cache"
    if [[ -f "$cache_dir/manifest.json" ]]; then
        echo "    PASS  hum-cache manifest"
        ((PASS++)) || true
    else
        echo "    WARN  no hum-cache yet"
        ((WARN++)) || true
    fi
done
if [[ "$PERSONA_COUNT" -eq 0 ]]; then
    echo "  WARN  No Orpheus checkpoints found under ${CHECKPOINTS}"
    ((WARN++)) || true
fi

echo ""
echo "[7/7] GPU"
CUDA=$(uv run python -c "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')" 2>/dev/null || echo "unknown")
if [[ "$CUDA" == "cuda" ]]; then
    GPU=$(uv run python -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "unknown")
    echo "  PASS  GPU: $GPU"
    ((PASS++)) || true
else
    echo "  WARN  No GPU (Seed-VC / Demucs will be slow)"
    ((WARN++)) || true
fi

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed, ${WARN} warnings ==="
[[ ${FAIL} -eq 0 ]] && exit 0 || exit 1
