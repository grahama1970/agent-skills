#!/usr/bin/env bash
# Sanity checks for /hum skill
# Tests: external skills, tools, storage, persona assets

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== /hum Sanity Checks ==="
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

# ── Section 1: System tools ──
echo "[1/6] System tools"
check "yt-dlp" command -v yt-dlp
check "ffmpeg" command -v ffmpeg
check "ffprobe" command -v ffprobe
warn  "pw-play" command -v pw-play

# ── Section 2: Required skills ──
echo ""
echo "[2/6] Required skills"
check "ingest-youtube" test -f "${SKILLS_ROOT}/ingest-youtube/run.sh"
check "create-stems"   test -f "${SKILLS_ROOT}/create-stems/run.sh"
check "create-music"   test -f "${SKILLS_ROOT}/create-music/run.sh"
check "learn-artist"   test -f "${SKILLS_ROOT}/learn-artist/run.sh"
warn  "consume-music"  test -f "${SKILLS_ROOT}/consume-music/run.sh"

# ── Section 3: Skill sanity pass-through ──
echo ""
echo "[3/6] Skill health (quick checks)"

echo -n "  "
if bash "${SKILLS_ROOT}/create-stems/sanity.sh" >/dev/null 2>&1; then
    echo "PASS  create-stems sanity"
    ((PASS++)) || true
else
    echo "WARN  create-stems sanity (may need venv sync)"
    ((WARN++)) || true
fi

# ── Section 4: Storage ──
echo ""
echo "[4/6] Storage"
check "12TB mount"  test -d /mnt/storage12tb/media/personas

# ── Section 5: Persona assets (check all personas with TTS samples) ──
echo ""
echo "[5/6] Persona readiness"

PERSONAS_ROOT="/mnt/storage12tb/media/personas"
RVC_ROOT="/mnt/storage12tb/media/music/rvc-models/voice"
PERSONA_COUNT=0

for persona_dir in "$PERSONAS_ROOT"/*/; do
    [[ -d "$persona_dir" ]] || continue
    persona=$(basename "$persona_dir")
    tts_dir="${persona_dir}tts_output"
    rvc_dir="${RVC_ROOT}/${persona}"
    cache_dir="${persona_dir}hum-cache"

    # Only check personas that have TTS samples (trainable)
    [[ -d "$tts_dir" ]] || continue
    sample_count=$(find "$tts_dir" -name "*.wav" 2>/dev/null | wc -l || echo 0)
    [[ "$sample_count" -eq 0 ]] && continue
    ((PERSONA_COUNT++)) || true

    echo "  ── ${persona} ──"

    echo -n "    "
    echo "PASS  TTS samples (${sample_count} files)"
    ((PASS++)) || true

    echo -n "    "
    if [[ -d "$rvc_dir" ]] && find "$rvc_dir" -name "*.pth" 2>/dev/null | head -1 | grep -q .; then
        echo "PASS  RVC model trained"
        ((PASS++)) || true
    else
        echo "WARN  RVC model not trained (run: ./run.sh train --persona ${persona})"
        ((WARN++)) || true
    fi

    echo -n "    "
    if [[ -f "$cache_dir/manifest.json" ]]; then
        track_count=$(python3 -c "import json; print(len(json.load(open('$cache_dir/manifest.json'))['tracks']))" 2>/dev/null || echo 0)
        echo "PASS  Hum cache (${track_count} tracks)"
        ((PASS++)) || true
    else
        echo "WARN  No hum cache (run: ./run.sh add <url> --persona ${persona})"
        ((WARN++)) || true
    fi
done

if [[ "$PERSONA_COUNT" -eq 0 ]]; then
    echo "  WARN  No personas with TTS samples found"
    ((WARN++)) || true
fi

# ── Section 6: GPU ──
echo ""
echo "[6/6] GPU"
CUDA=$(python3 -c "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')" 2>/dev/null || echo "unknown")
if [[ "$CUDA" == "cuda" ]]; then
    GPU=$(python3 -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "unknown")
    echo "  PASS  GPU: $GPU"
    ((PASS++)) || true
else
    echo "  WARN  No GPU (pipeline will be slow)"
    ((WARN++)) || true
fi

# ── Summary ──
echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed, ${WARN} warnings ==="
[[ ${FAIL} -eq 0 ]] && exit 0 || exit 1
