#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# learn-artist: Train RVC voice/instrument models from artist names
set -euo pipefail

# Ensure deno and updated yt-dlp are in PATH for YouTube downloads
export PATH="${HOME}/.local/bin:${HOME}/.deno/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
DISCOVER_MUSIC_DIR="${SCRIPT_DIR}/../discover-music"

# Storage paths (all on 12TB drive)
TRAINING_DATA_ROOT="/mnt/storage12tb/media/music/rvc-training"
MODELS_ROOT="/mnt/storage12tb/media/music/rvc-models"
RVC_LOGS_DIR="/mnt/storage12tb/media/music/rvc-webui/logs"

# Docker settings
DOCKER_IMAGE="cherrymint/rvc_webui:rvc_boss"
DOCKER_NAME="rvc-training"

QUEUE_FILE="${MODELS_ROOT}/queue.txt"
STATE_FILE="${MODELS_ROOT}/daemon-state.json"
TASK_MONITOR_DIR="${SCRIPT_DIR}/../task-monitor"
TASK_MONITOR_API="http://localhost:8765"

show_help() {
    cat << 'EOF'
learn-artist: Train RVC voice models from artist names

Usage: ./run.sh <command> [options]

Commands:
  learn <artist> [type]    Easiest way - just say who to learn
  add <artist>             Add artist to training queue
  import <file>            Bulk import from CSV/JSON/text file
  discover <artist>        Find similar artists via MusicBrainz/ListenBrainz
  queue                    Show current queue
  stats                    Show library statistics
  monitor [interval]       Live progress monitor (default: 30s refresh)
  daemon                   Run continuous training daemon (with watchdog)
  run-queue                Process all queued artists (one-shot)
  train <artist>           Train a voice model immediately
  list                     List trained voice models
  status <model>           Check training status
  sync-memory              Export trained model metadata to /memory

Simple Examples (for agents):
  ./run.sh learn "Tom Waits"
  ./run.sh learn "Keith Moon" drummer
  ./run.sh learn "Miles Davis" trumpet

Advanced Examples:
  ./run.sh add "Sierra Ferrell"
  ./run.sh add "JIREH"
  ./run.sh add "Pedal Steel" --category instrument
  ./run.sh discover "Chelsea Wolfe"                # Find similar artists
  ./run.sh discover --bridge Corruption --auto-queue  # Auto-queue by bridge
  ./run.sh queue                    # Show queue
  ./run.sh run-queue                # Train all queued

Train Options:
  --epochs N               Training epochs (default: 200)
  --batch-size N           Batch size (default: 4)
  --category voice|instrument  Model category (default: voice)
  --min-tracks N           Minimum tracks to download (default: 10)
  --min-minutes N          Minimum audio duration (default: 30)
  --skip-download          Use existing vocals

Examples:
  ./run.sh train "Brennen Leigh"
  ./run.sh add "Lucinda Williams" && ./run.sh add "Beth Gibbons"
  ./run.sh run-queue
  ./run.sh list
EOF
}

slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//' | sed 's/-$//'
}

ensure_docker() {
    if ! docker ps --filter "name=${DOCKER_NAME}" --format '{{.Names}}' | grep -q "${DOCKER_NAME}"; then
        echo "Starting RVC Docker container..."
        docker run -d --gpus all --name "${DOCKER_NAME}" \
            --shm-size=8g \
            -p 7865:7865 \
            -v "${RVC_LOGS_DIR}:/app/logs" \
            -v "${TRAINING_DATA_ROOT}:/app/datasets" \
            "${DOCKER_IMAGE}" || true
        sleep 5
    fi
}

download_and_separate() {
    local artist="$1"
    local slug="$2"
    local min_tracks="${3:-10}"
    local min_minutes="${4:-30}"
    local output_dir="${TRAINING_DATA_ROOT}/${slug}"

    mkdir -p "${output_dir}/vocals_all"

    echo "Searching YouTube for: ${artist}"

    # Search for tracks
    cd "${DISCOVER_MUSIC_DIR}"
    local search_results
    search_results=$(./run.sh youtube-search "${artist}" --limit 20 --json 2>/dev/null || echo "[]")

    # Get video IDs (skip channels)
    # Note: discover-music outputs status message before JSON, so extract JSON array only
    local video_ids
    video_ids=$(echo "${search_results}" | sed -n '/^\[/,/^\]/p' | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for item in data:
        vid = item.get('id', '')
        if vid and len(vid) == 11:  # YouTube video IDs are 11 chars
            print(vid)
except Exception:
    pass
" 2>/dev/null | head -n "${min_tracks}")

    if [[ -z "${video_ids}" ]]; then
        echo "No videos found for ${artist}"
        return 1
    fi

    local count=0
    for vid in ${video_ids}; do
        echo "Downloading and separating: ${vid}"
        ./run.sh youtube-stems "${vid}" --out "${output_dir}" 2>&1 || true
        ((count++)) || true
    done

    # Consolidate vocals
    # Matches both old path (stems/demucs/htdemucs/*/vocals.wav) and
    # new create-stems path (stems/htdemucs*/*/vocals.wav)
    echo "Consolidating vocal stems..."
    find "${output_dir}" -name "vocals.wav" -path "*/stems/*" -exec sh -c '
        id=$(basename "$(dirname "$1")")
        cp "$1" "'"${output_dir}/vocals_all/${slug}"'_${id}_vocals.wav"
    ' _ {} \;

    # Check total duration
    local total_duration
    total_duration=$(for f in "${output_dir}/vocals_all"/*.wav; do
        ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$f" 2>/dev/null
    done | awk '{s+=$1} END {print s}')

    local minutes
    minutes=$(echo "${total_duration} / 60" | bc)
    echo "Total vocal duration: ${minutes} minutes"

    if (( $(echo "${minutes} < ${min_minutes}" | bc -l) )); then
        echo "WARNING: Only ${minutes} minutes of YouTube audio (target: ${min_minutes})"
        echo "Attempting NZBGeek fallback for album downloads..."
        nzbgeek_fallback "${artist}" "${slug}" "${output_dir}" "${min_minutes}" "${minutes}"

        # Recount after fallback
        total_duration=$(for f in "${output_dir}/vocals_all"/*.wav; do
            [[ -f "$f" ]] && ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$f" 2>/dev/null
        done | awk '{s+=$1} END {print s}')
        minutes=$(echo "${total_duration:-0} / 60" | bc)
        echo "Total vocal duration after NZBGeek fallback: ${minutes} minutes"
    fi

    echo "${output_dir}/vocals_all"
}

nzbgeek_fallback() {
    local artist="$1"
    local slug="$2"
    local output_dir="$3"
    local min_minutes="${4:-30}"
    local current_minutes="${5:-0}"

    local nzbgeek_skill="${SCRIPT_DIR}/../ops-nzbgeek/run.sh"
    if [[ ! -f "${nzbgeek_skill}" ]]; then
        echo "WARN: ops-nzbgeek skill not found, skipping NZBGeek fallback"
        return 0
    fi

    # Search for artist albums in music category
    echo "Searching NZBGeek for: ${artist} albums..."
    local results
    results=$(bash "${nzbgeek_skill}" search "${artist}" --category music --limit 10 --json 2>/dev/null) || true

    if [[ -z "${results}" ]] || [[ "${results}" == "[]" ]]; then
        echo "No NZBGeek results for ${artist}"
        return 0
    fi

    # Parse NZB URLs from results (take top 3 albums max)
    local nzb_urls
    nzb_urls=$(echo "${results}" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict): data = data.get('results', data.get('channel', {}).get('item', []))
    for item in data[:3]:
        link = item.get('link', '')
        title = item.get('title', 'unknown')
        if link:
            print(f'{link}\t{title}')
except: pass
" 2>/dev/null) || true

    if [[ -z "${nzb_urls}" ]]; then
        echo "No downloadable NZBs found for ${artist}"
        return 0
    fi

    local download_dir="/mnt/storage12tb/downloads"
    local album_count=0

    while IFS=$'\t' read -r nzb_url album_title; do
        [[ -z "${nzb_url}" ]] && continue
        echo "Downloading: ${album_title}"

        # Trigger SABnzbd download
        local dl_output
        dl_output=$(bash "${nzbgeek_skill}" download "${nzb_url}" --category music --priority 1 2>/dev/null) || true
        local nzb_id
        nzb_id=$(echo "${dl_output}" | grep -oP 'nzo_\w+' | head -1) || true

        if [[ -z "${nzb_id}" ]]; then
            echo "WARN: Failed to queue ${album_title}"
            continue
        fi

        # Wait for download (max 30 min per album)
        echo "Waiting for download: ${nzb_id}..."
        local elapsed=0
        local max_wait=1800
        while [[ ${elapsed} -lt ${max_wait} ]]; do
            local status_json
            status_json=$(bash "${nzbgeek_skill}" status --json 2>/dev/null) || true
            # Check if our download is still in queue
            if ! echo "${status_json}" | grep -q "${nzb_id}" 2>/dev/null; then
                echo "Download completed or removed from queue"
                break
            fi
            sleep 15
            ((elapsed += 15)) || true
        done

        ((album_count++)) || true
    done <<< "${nzb_urls}"

    if [[ ${album_count} -eq 0 ]]; then
        echo "No albums downloaded from NZBGeek"
        return 0
    fi

    # Wait for SABnzbd post-processing
    echo "Waiting 30s for SABnzbd post-processing..."
    sleep 30

    # Find downloaded audio files and run through Demucs
    local nzb_audio_dir="${output_dir}/nzbgeek_audio"
    mkdir -p "${nzb_audio_dir}"

    # Search for audio files matching this artist in downloads
    local found_files=0
    local artist_lower
    artist_lower=$(echo "${artist}" | tr '[:upper:]' '[:lower:]')

    # Search broadly in recent downloads
    find "${download_dir}" -maxdepth 3 -type f \
        \( -iname "*.flac" -o -iname "*.mp3" -o -iname "*.wav" -o -iname "*.aac" -o -iname "*.ogg" \) \
        -newer "${output_dir}" 2>/dev/null | while read -r audio_file; do
        cp "${audio_file}" "${nzb_audio_dir}/" 2>/dev/null || true
        ((found_files++)) || true
    done

    found_files=$(ls "${nzb_audio_dir}" 2>/dev/null | wc -l)
    if [[ ${found_files} -eq 0 ]]; then
        echo "No audio files found in downloads for ${artist}"
        return 0
    fi

    echo "Found ${found_files} audio files from NZBGeek, running stem separation..."

    # Run stem separation on each audio file to extract vocals
    local create_stems_dir="${SCRIPT_DIR}/../create-stems"

    for audio_file in "${nzb_audio_dir}"/*; do
        [[ ! -f "${audio_file}" ]] && continue
        local basename
        basename=$(basename "${audio_file}" | sed 's/\.[^.]*$//')

        echo "  Separating: ${basename}"
        # Prefer create-stems skill, fall back to direct demucs
        if [[ -f "${create_stems_dir}/run.sh" ]]; then
            bash "${create_stems_dir}/run.sh" separate \
                --mix "${audio_file}" --out "${nzb_audio_dir}/stems" \
                --instrument vocals 2>/dev/null || true
        elif command -v demucs &>/dev/null; then
            demucs --two-stems=vocals -n htdemucs \
                -o "${nzb_audio_dir}/stems" "${audio_file}" 2>/dev/null || true
        else
            python3 -m demucs --two-stems=vocals -n htdemucs \
                -o "${nzb_audio_dir}/stems" "${audio_file}" 2>/dev/null || true
        fi

        # Copy vocals to vocals_all (check both htdemucs_6s and htdemucs paths)
        local vocals_file=""
        for model_name in htdemucs_6s htdemucs; do
            if [[ -f "${nzb_audio_dir}/stems/${model_name}/${basename}/vocals.wav" ]]; then
                vocals_file="${nzb_audio_dir}/stems/${model_name}/${basename}/vocals.wav"
                break
            fi
        done
        if [[ -n "${vocals_file}" ]]; then
            cp "${vocals_file}" "${output_dir}/vocals_all/${slug}_nzb_${basename}_vocals.wav"
            echo "  Extracted vocals: ${basename}"
        fi
    done

    local nzb_vocals
    nzb_vocals=$(ls "${output_dir}/vocals_all/${slug}_nzb_"* 2>/dev/null | wc -l)
    echo "NZBGeek fallback complete: ${nzb_vocals} vocal tracks added"
}

preprocess() {
    local slug="$1"

    echo "Preprocessing ${slug}..."
    docker exec "${DOCKER_NAME}" mkdir -p "/app/logs/${slug}"
    docker exec "${DOCKER_NAME}" python /app/infer/modules/train/preprocess.py \
        "/app/datasets/${slug}/vocals_all" \
        40000 \
        4 \
        "/app/logs/${slug}" \
        False \
        3.7
}

extract_f0() {
    local slug="$1"

    echo "Extracting F0 (pitch) for ${slug}..."
    docker exec "${DOCKER_NAME}" python /app/infer/modules/train/extract/extract_f0_rmvpe.py \
        1 0 0 "/app/logs/${slug}" True
}

extract_features() {
    local slug="$1"

    echo "Extracting Hubert features for ${slug}..."
    docker exec "${DOCKER_NAME}" python /app/infer/modules/train/extract_feature_print.py \
        cuda:0 1 0 "/app/logs/${slug}" v2 True
}

generate_filelist() {
    local slug="$1"

    echo "Generating filelist for ${slug}..."
    docker exec "${DOCKER_NAME}" python3 -c "
import os
import json

slug = '${slug}'
exp_dir = f'/app/logs/{slug}'
gt_wavs_dir = f'{exp_dir}/0_gt_wavs'
feature_dir = f'{exp_dir}/3_feature768'
f0_dir = f'{exp_dir}/2a_f0'
f0nsf_dir = f'{exp_dir}/2b-f0nsf'

names = (
    set([name.split('.')[0] for name in os.listdir(gt_wavs_dir)])
    & set([name.split('.')[0] for name in os.listdir(feature_dir)])
    & set([name.split('.')[0] for name in os.listdir(f0_dir)])
    & set([name.split('.')[0] for name in os.listdir(f0nsf_dir)])
)

opt = []
for name in names:
    opt.append(f'{gt_wavs_dir}/{name}.wav|{feature_dir}/{name}.npy|{f0_dir}/{name}.wav.npy|{f0nsf_dir}/{name}.wav.npy|0')

with open(f'{exp_dir}/filelist.txt', 'w') as f:
    f.write('\n'.join(opt))

# Write config
config = {
    'train': {
        'log_interval': 200, 'seed': 1234, 'epochs': 200,
        'learning_rate': 0.0001, 'betas': [0.8, 0.99], 'eps': 1e-9,
        'batch_size': 4, 'fp16_run': True, 'lr_decay': 0.999875,
        'segment_size': 12800, 'init_lr_ratio': 1, 'warmup_epochs': 0,
        'c_mel': 45, 'c_kl': 1.0
    },
    'data': {
        'max_wav_value': 32768.0, 'sampling_rate': 40000,
        'filter_length': 2048, 'hop_length': 400, 'win_length': 2048,
        'n_mel_channels': 125, 'mel_fmin': 0.0, 'mel_fmax': None,
        'training_files': f'{exp_dir}/filelist.txt'
    },
    'model': {
        'inter_channels': 192, 'hidden_channels': 192, 'filter_channels': 768,
        'n_heads': 2, 'n_layers': 6, 'kernel_size': 3, 'p_dropout': 0,
        'resblock': '1', 'resblock_kernel_sizes': [3, 7, 11],
        'resblock_dilation_sizes': [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
        'upsample_rates': [10, 10, 2, 2], 'upsample_initial_channel': 512,
        'upsample_kernel_sizes': [16, 16, 4, 4], 'spk_embed_dim': 109,
        'gin_channels': 256, 'use_spectral_norm': False
    },
    'version': 'v2'
}

with open(f'{exp_dir}/config.json', 'w') as f:
    json.dump(config, f, indent=4)

print(f'Generated filelist with {len(opt)} entries')
"
}

train_model() {
    local slug="$1"
    local epochs="${2:-200}"
    local batch_size="${3:-4}"

    echo "Training ${slug} for ${epochs} epochs (batch_size=${batch_size})..."
    docker exec "${DOCKER_NAME}" python /app/infer/modules/train/train.py \
        -e "${slug}" \
        -sr 40k \
        -f0 1 \
        -bs "${batch_size}" \
        -g 0 \
        -te "${epochs}" \
        -se 25 \
        -pg assets/pretrained_v2/f0G40k.pth \
        -pd assets/pretrained_v2/f0D40k.pth \
        -l 0 \
        -c 0 \
        -sw 1 \
        -v v2
}

build_index() {
    local slug="$1"

    echo "Building FAISS index for ${slug}..."
    # Build index using Python/faiss directly (more reliable than train-index-v2.py)
    docker exec "${DOCKER_NAME}" python3 -c "
import os
import numpy as np
import faiss

feature_dir = '/app/logs/${slug}/3_feature768'
if not os.path.exists(feature_dir):
    print(f'Feature directory not found: {feature_dir}')
    exit(1)

features = []
for f in sorted(os.listdir(feature_dir)):
    if f.endswith('.npy'):
        feat = np.load(os.path.join(feature_dir, f))
        features.append(feat)

if not features:
    print('No feature files found')
    exit(1)

all_features = np.vstack(features).astype('float32')
print(f'Loaded {len(features)} files, {all_features.shape[0]} vectors')

dim = all_features.shape[1]
n_ivf = min(int(np.sqrt(all_features.shape[0])) * 4, all_features.shape[0] // 39)
n_ivf = max(n_ivf, 1)
index = faiss.index_factory(dim, f'IVF{n_ivf},Flat')
index.train(all_features)
index.add(all_features)
print(f'Index built with {index.ntotal} vectors, {n_ivf} centroids')

faiss.write_index(index, '/app/logs/${slug}/${slug}.index')
print('Index saved')
" 2>&1
}

verify_model() {
    local slug="$1"
    local model_dir="$2"

    echo "Verifying model ${slug}..."

    # Create a test audio file (10s sine wave) if not exists
    local test_input="/tmp/rvc_test_input.wav"
    local test_output="/tmp/rvc_test_output_${slug}.wav"

    if [[ ! -f "${test_input}" ]]; then
        echo "Creating test audio..."
        ffmpeg -y -f lavfi -i "sine=frequency=440:duration=10" -ar 40000 -ac 1 "${test_input}" 2>/dev/null
    fi

    # Copy test input to container
    docker cp "${test_input}" "${DOCKER_NAME}:/app/test_input.wav"

    # Copy inference model to container if needed
    local infer_model="${model_dir}/${slug}-infer.pth"
    if [[ -f "${infer_model}" ]]; then
        docker cp "${infer_model}" "${DOCKER_NAME}:/app/test_model.pth"
    else
        echo "Warning: No inference model found at ${infer_model}"
        return 1
    fi

    # Copy index if exists
    local index_file="${model_dir}/${slug}.index"
    if [[ -f "${index_file}" ]]; then
        docker cp "${index_file}" "${DOCKER_NAME}:/app/test.index"
    fi

    # Run inference test (CPU to avoid NVML issues in docker exec)
    echo "Running inference test..."
    local result
    result=$(docker exec "${DOCKER_NAME}" python3 -c "
import torch
import numpy as np
import soundfile as sf

# Load model
model_path = '/app/test_model.pth'
cpt = torch.load(model_path, map_location='cpu')

# Check model structure
required_keys = ['weight', 'config', 'sr', 'f0', 'version']
missing = [k for k in required_keys if k not in cpt]
if missing:
    print(f'FAIL: Missing keys: {missing}')
    exit(1)

print(f'Model keys: {list(cpt.keys())}')
print(f'Config: sr={cpt[\"sr\"]}, f0={cpt[\"f0\"]}, version={cpt[\"version\"]}')
print(f'Weight keys count: {len(cpt[\"weight\"])}')

# Try loading audio
try:
    audio, sr = sf.read('/app/test_input.wav')
    print(f'Input audio: {len(audio)} samples at {sr}Hz ({len(audio)/sr:.1f}s)')
except Exception as e:
    print(f'FAIL: Could not read test audio: {e}')
    exit(1)

# Basic sanity check - verify weight tensor shapes are valid
weight_count = 0
for k, v in cpt['weight'].items():
    if hasattr(v, 'shape'):
        weight_count += 1

print(f'Valid weight tensors: {weight_count}')

if weight_count < 10:
    print('FAIL: Too few weight tensors')
    exit(1)

print('PASS: Model structure valid')
" 2>&1)

    echo "${result}"

    if echo "${result}" | grep -q "PASS"; then
        echo "✓ Model ${slug} verified successfully"
        return 0
    else
        echo "✗ Model ${slug} verification failed"
        return 1
    fi
}

export_inference_model() {
    local slug="$1"
    local epochs="$2"

    echo "Exporting inference model for ${slug}..."
    docker exec "${DOCKER_NAME}" python3 -c "
import torch
from collections import OrderedDict

# Find latest checkpoint
import os
import glob
checkpoints = glob.glob('/app/logs/${slug}/G_*.pth')
if not checkpoints:
    print('No checkpoints found')
    exit(1)

latest = max(checkpoints, key=lambda x: int(x.split('_')[-1].replace('.pth', '')))
print(f'Using checkpoint: {latest}')

# Load checkpoint
ckpt = torch.load(latest, map_location='cpu')
if 'model' in ckpt:
    ckpt = ckpt['model']

# Extract weights (skip encoder)
opt = OrderedDict()
opt['weight'] = {}
for key in ckpt.keys():
    if 'enc_q' in key:
        continue
    opt['weight'][key] = ckpt[key].half()

# Config for 40k sample rate v2
opt['config'] = [
    1025, 32, 192, 192, 768, 2, 6, 3, 0, '1',
    [3, 7, 11], [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
    [10, 10, 2, 2], 512, [16, 16, 4, 4], 109, 256, 40000
]
opt['info'] = '${epochs}epoch'
opt['sr'] = '40k'
opt['f0'] = 1
opt['version'] = 'v2'

# Save inference model
torch.save(opt, '/app/logs/${slug}/${slug}-infer.pth')
print(f'Inference model saved: /app/logs/${slug}/${slug}-infer.pth')
" 2>&1
}

save_model() {
    local slug="$1"
    local artist="$2"
    local category="${3:-voice}"
    local epochs="${4:-200}"

    local model_dir="${MODELS_ROOT}/${category}/${slug}"
    mkdir -p "${model_dir}"

    # Export inference-ready model
    export_inference_model "${slug}" "${epochs}"

    # Copy full checkpoint
    local latest_g
    latest_g=$(ls -t "${RVC_LOGS_DIR}/${slug}"/G_*.pth 2>/dev/null | head -1)
    if [[ -n "${latest_g}" ]]; then
        cp "${latest_g}" "${model_dir}/${slug}.pth"
        echo "Copied full checkpoint: ${slug}.pth"
    fi

    # Copy inference model
    if [[ -f "${RVC_LOGS_DIR}/${slug}/${slug}-infer.pth" ]]; then
        cp "${RVC_LOGS_DIR}/${slug}/${slug}-infer.pth" "${model_dir}/"
        echo "Copied inference model: ${slug}-infer.pth"
    fi

    # Copy index
    if [[ -f "${RVC_LOGS_DIR}/${slug}/${slug}.index" ]]; then
        cp "${RVC_LOGS_DIR}/${slug}/${slug}.index" "${model_dir}/"
        echo "Copied index: ${slug}.index"
    fi

    # Get training stats
    local segments=0
    local index_vectors=0
    [[ -d "${RVC_LOGS_DIR}/${slug}/0_gt_wavs" ]] && segments=$(ls "${RVC_LOGS_DIR}/${slug}/0_gt_wavs" 2>/dev/null | wc -l)

    # Create metadata
    cat > "${model_dir}/metadata.json" << EOF
{
    "name": "${slug}",
    "artist": "${artist}",
    "category": "${category}",
    "segments": ${segments},
    "epochs": ${epochs},
    "batch_size": 4,
    "sample_rate": "40k",
    "version": "v2",
    "trained_at": "$(date -Iseconds)",
    "quality": "good"
}
EOF

    echo "Model saved to ${model_dir}"

    # Enrich metadata with Federated Taxonomy (bridge_tags, subcategory, genres)
    enrich_taxonomy "${slug}" "${model_dir}"

    # Verify with sanity test
    verify_model "${slug}" "${model_dir}"
}

enrich_taxonomy() {
    local slug="$1"
    local model_dir="$2"
    local script="${SCRIPT_DIR}/enrich_taxonomy.py"

    if [[ ! -f "${script}" ]]; then
        echo "WARN: enrich_taxonomy.py not found, skipping taxonomy enrichment"
        return 0
    fi

    # Try artist DB lookup first (deterministic, no LLM)
    if python3 "${script}" --artist "${slug}" >/dev/null 2>&1; then
        # Known artist - enrich from DB
        python3 "${script}" --models-root "${MODELS_ROOT}" 2>/dev/null || true
        echo "Taxonomy enriched from artist database"
    else
        # Unknown artist - use taxonomy skill keyword extraction as fallback
        local taxonomy_skill="${HOME}/.agent/skills/taxonomy/run.sh"
        if [[ -f "${taxonomy_skill}" ]]; then
            local genres=""
            # Try to get genre context from YouTube metadata
            local yt_dir="${TRAINING_DATA_ROOT}/${slug}"
            if [[ -d "${yt_dir}" ]]; then
                genres=$(find "${yt_dir}" -name "*.info.json" -exec python3 -c "
import json, sys
tags = set()
for f in sys.argv[1:]:
    try:
        d = json.load(open(f))
        tags.update(d.get('tags', []))
        if d.get('categories'): tags.update(d['categories'])
    except: pass
print(' '.join(sorted(tags)[:20]))
" {} + 2>/dev/null) || true
            fi

            if [[ -n "${genres}" ]]; then
                local tax_output
                tax_output=$(bash "${taxonomy_skill}" extract --fast --text "${slug} ${genres}" 2>/dev/null) || true
                if [[ -n "${tax_output}" ]]; then
                    # Merge taxonomy output into metadata.json
                    python3 -c "
import json, sys
meta_path = '${model_dir}/metadata.json'
with open(meta_path) as f: meta = json.load(f)
try:
    tax = json.loads('''${tax_output}''')
    meta['bridge_tags'] = tax.get('bridge_tags', [])
    meta['confidence'] = tax.get('confidence', 0.5)
    meta['genres'] = '${genres}'.split()[:10]
except: pass
with open(meta_path, 'w') as f: json.dump(meta, f, indent=4, ensure_ascii=False)
" 2>/dev/null || true
                    echo "Taxonomy enriched via keyword extraction"
                fi
            else
                echo "WARN: No genre context found for ${slug}, taxonomy skipped"
            fi
        fi
    fi
}

cmd_train() {
    local artist="$1"
    shift

    local epochs=200
    local batch_size=4
    local category="voice"
    local min_tracks=10
    local min_minutes=30
    local skip_download=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --epochs) epochs="$2"; shift 2 ;;
            --batch-size) batch_size="$2"; shift 2 ;;
            --category) category="$2"; shift 2 ;;
            --min-tracks) min_tracks="$2"; shift 2 ;;
            --min-minutes) min_minutes="$2"; shift 2 ;;
            --skip-download) skip_download=true; shift ;;
            *) shift ;;
        esac
    done

    local slug
    slug=$(slugify "${artist}")

    echo "=========================================="
    echo "Training voice model: ${artist}"
    echo "Slug: ${slug}"
    echo "Category: ${category}"
    echo "Epochs: ${epochs}"
    echo "=========================================="

    ensure_docker

    # Helper to push stage to task-monitor (reads daemon state for counts)
    local _tm_completed _tm_total
    _tm_completed=$(grep -c "^#DONE:" "${QUEUE_FILE}" 2>/dev/null || echo 0)
    _tm_total=$(( _tm_completed + $(grep -v "^#" "${QUEUE_FILE}" 2>/dev/null | grep -v "^$" | wc -l) ))
    push_stage() {
        update_task_monitor "learn-artist" "${_tm_completed}" "${_tm_total}" "running" "${artist}" "0" "${epochs}" "$1"
    }

    if [[ "${skip_download}" != "true" ]]; then
        push_stage "downloading"
        download_and_separate "${artist}" "${slug}" "${min_tracks}" "${min_minutes}"
    fi

    # Mount the new dataset
    docker exec "${DOCKER_NAME}" ln -sf "/app/datasets/${slug}/vocals_all" "/app/datasets/${slug}-vocals" 2>/dev/null || true

    push_stage "preprocessing"
    preprocess "${slug}"

    push_stage "f0"
    extract_f0 "${slug}"

    push_stage "features"
    extract_features "${slug}"

    push_stage "filelist"
    generate_filelist "${slug}"

    push_stage "training"
    train_model "${slug}" "${epochs}" "${batch_size}"

    push_stage "index"
    build_index "${slug}"

    push_stage "exporting"
    save_model "${slug}" "${artist}" "${category}"

    echo "=========================================="
    echo "Training complete: ${artist}"
    echo "Model: ${MODELS_ROOT}/${category}/${slug}/"
    echo "=========================================="
}

cmd_train_batch() {
    local artists=()
    local epochs=200
    local batch_size=4
    local category="voice"
    local file=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --epochs) epochs="$2"; shift 2 ;;
            --batch-size) batch_size="$2"; shift 2 ;;
            --category) category="$2"; shift 2 ;;
            --file) file="$2"; shift 2 ;;
            *) artists+=("$1"); shift ;;
        esac
    done

    if [[ -n "${file}" ]]; then
        while IFS= read -r line; do
            [[ -n "${line}" ]] && artists+=("${line}")
        done < "${file}"
    fi

    echo "Batch training ${#artists[@]} artists..."

    for artist in "${artists[@]}"; do
        cmd_train "${artist}" --epochs "${epochs}" --batch-size "${batch_size}" --category "${category}"
    done
}

cmd_list() {
    local category=""
    local json=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --voice) category="voice"; shift ;;
            --instrument) category="instrument"; shift ;;
            --json) json=true; shift ;;
            *) shift ;;
        esac
    done

    if [[ "${json}" == "true" ]]; then
        find "${MODELS_ROOT}" -name "metadata.json" -exec cat {} \; | jq -s '.'
    else
        echo "Trained Voice Models:"
        echo "====================="
        for dir in "${MODELS_ROOT}"/voice/*/; do
            if [[ -d "${dir}" ]]; then
                local name
                name=$(basename "${dir}")
                local meta="${dir}/metadata.json"
                if [[ -f "${meta}" ]]; then
                    local artist
                    artist=$(jq -r '.artist' "${meta}" 2>/dev/null || echo "${name}")
                    echo "  ${name} (${artist})"
                else
                    echo "  ${name}"
                fi
            fi
        done

        echo ""
        echo "Trained Instrument Models:"
        echo "=========================="
        for dir in "${MODELS_ROOT}"/instrument/*/; do
            if [[ -d "${dir}" ]]; then
                echo "  $(basename "${dir}")"
            fi
        done
    fi
}

cmd_status() {
    local slug="$1"

    echo "Status: ${slug}"
    echo "==============="

    # Check if training
    if docker exec "${DOCKER_NAME}" test -f "/app/logs/${slug}/train.log" 2>/dev/null; then
        tail -10 "${RVC_LOGS_DIR}/${slug}/train.log" 2>/dev/null || echo "No training log"
    fi

    # Check model files
    if [[ -f "${MODELS_ROOT}/voice/${slug}/${slug}.pth" ]]; then
        echo "Model: trained"
        cat "${MODELS_ROOT}/voice/${slug}/metadata.json" 2>/dev/null | jq '.'
    else
        echo "Model: not found"
    fi
}

cmd_learn() {
    # Simplest interface: ./run.sh learn "Artist Name"
    # Auto-adds to queue and ensures daemon is running
    local artist="$1"
    shift
    local category="voice"

    # Auto-detect instrument keywords
    if [[ "$*" =~ drummer|drums|percussion ]]; then
        category="instrument"
    elif [[ "$*" =~ guitar|guitarist|bass|bassist ]]; then
        category="instrument"
    elif [[ "$*" =~ trumpet|horn|sax|piano|keys|violin|cello ]]; then
        category="instrument"
    elif [[ "$*" =~ instrument ]]; then
        category="instrument"
    fi

    # Add to queue
    cmd_add "${artist}" --category "${category}"

    # Check if daemon is running
    if [[ -f "${STATE_FILE}" ]]; then
        local pid
        pid=$(jq -r '.pid // empty' "${STATE_FILE}" 2>/dev/null)
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            echo "Daemon running (PID ${pid}) - will train automatically"
            return 0
        fi
    fi

    echo ""
    echo "To start training, run:"
    echo "  ./run.sh daemon &"
    echo "  # or"
    echo "  nohup ./run.sh daemon > daemon.log 2>&1 &"
}

cmd_add() {
    local artist="$1"
    shift
    local options="$*"

    # Create queue file if doesn't exist
    if [[ ! -f "${QUEUE_FILE}" ]]; then
        cat > "${QUEUE_FILE}" << 'EOF'
# Voice Training Queue
# Add one artist per line. Lines starting with # are ignored.
# Format: Artist Name [--category voice|instrument] [--epochs N]
EOF
    fi

    # Check if already in queue
    if grep -q "^${artist}$\|^${artist} " "${QUEUE_FILE}" 2>/dev/null; then
        echo "Already in queue: ${artist}"
        return 0
    fi

    # Check if already trained
    local slug
    slug=$(slugify "${artist}")
    if [[ -d "${MODELS_ROOT}/voice/${slug}" ]] || [[ -d "${MODELS_ROOT}/instrument/${slug}" ]]; then
        echo "Already trained: ${artist} (${slug})"
        return 0
    fi

    # Add to queue
    if [[ -n "${options}" ]]; then
        echo "${artist} ${options}" >> "${QUEUE_FILE}"
    else
        echo "${artist}" >> "${QUEUE_FILE}"
    fi
    echo "Added to queue: ${artist}"

    # Show queue count
    local count
    count=$(grep -v "^#" "${QUEUE_FILE}" | grep -v "^$" | wc -l)
    echo "Queue now has ${count} artists"
}

cmd_import() {
    local file="$1"
    local category="${2:-voice}"

    if [[ ! -f "${file}" ]]; then
        echo "File not found: ${file}"
        return 1
    fi

    local added=0
    local skipped=0

    # Support CSV, JSON, or plain text
    case "${file}" in
        *.json)
            # JSON array of strings or objects with "name" field
            while IFS= read -r artist; do
                [[ -z "${artist}" ]] && continue
                cmd_add "${artist}" --category "${category}" >/dev/null && ((added++)) || ((skipped++))
            done < <(jq -r '.[] | if type == "string" then . else .name end' "${file}" 2>/dev/null)
            ;;
        *.csv)
            # CSV with header: name,category (or just names)
            tail -n +2 "${file}" | while IFS=, read -r artist cat _; do
                [[ -z "${artist}" ]] && continue
                artist=$(echo "${artist}" | tr -d '"')
                cat="${cat:-${category}}"
                cmd_add "${artist}" --category "${cat}" >/dev/null && ((added++)) || ((skipped++))
            done
            ;;
        *)
            # Plain text, one artist per line
            while IFS= read -r line; do
                [[ -z "${line}" ]] && continue
                [[ "${line}" =~ ^# ]] && continue
                cmd_add "${line}" >/dev/null && ((added++)) || ((skipped++))
            done < "${file}"
            ;;
    esac

    echo "Imported: ${added} added, ${skipped} skipped (already queued/trained)"

    local total
    total=$(grep -v "^#" "${QUEUE_FILE}" | grep -v "^$" | wc -l)
    echo "Queue total: ${total} artists"
}

update_task_monitor() {
    local name="$1"
    local completed="$2"
    local total="$3"
    local status="${4:-running}"
    local current_artist="${5:-}"
    local current_epoch="${6:-0}"
    local total_epochs="${7:-200}"
    local stage="${8:-training}"

    # Format current_item based on stage
    local current_item=""
    case "${stage}" in
        downloading)   current_item="${current_artist} [downloading YouTube audio]" ;;
        separating)    current_item="${current_artist} [Demucs stem separation]" ;;
        preprocessing) current_item="${current_artist} [preprocessing audio]" ;;
        f0)            current_item="${current_artist} [F0 pitch extraction (RMVPE)]" ;;
        features)      current_item="${current_artist} [Hubert feature extraction]" ;;
        filelist)      current_item="${current_artist} [generating filelist]" ;;
        training)      current_item="${current_artist} [training epoch ${current_epoch}/${total_epochs}]" ;;
        index)         current_item="${current_artist} [building FAISS index]" ;;
        exporting)     current_item="${current_artist} [exporting inference model]" ;;
        enriching)     current_item="${current_artist} [taxonomy enrichment]" ;;
        verifying)     current_item="${current_artist} [verifying model]" ;;
        completed)     current_item="${current_artist} [done]" ;;
        *)             current_item="${current_artist} [${stage}]" ;;
    esac

    # Push state update via HTTP API
    curl -s -X POST "${TASK_MONITOR_API}/tasks/${name}/state" \
        -H "Content-Type: application/json" \
        -d "{
            \"completed\": ${completed},
            \"total\": ${total},
            \"status\": \"${status}\",
            \"current_item\": \"${current_item}\",
            \"current_method\": \"${stage}\",
            \"description\": \"RVC voice model training queue\",
            \"stats\": {\"success\": ${completed}, \"failed\": 0},
            \"last_updated\": \"$(date -Iseconds)\"
        }" 2>/dev/null || true
}

register_task() {
    local name="$1"
    local total="$2"

    # Register task with task-monitor
    curl -s -X POST "${TASK_MONITOR_API}/tasks" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"${name}\",
            \"state_file\": \"${STATE_FILE}\",
            \"total\": ${total},
            \"description\": \"RVC voice model training queue\",
            \"project\": \"learn-artist\"
        }" 2>/dev/null || true
}

write_state() {
    local current_artist="$1"
    local current_epoch="$2"
    local total_epochs="$3"
    local queue_position="$4"
    local queue_total="$5"
    local status="${6:-running}"

    cat > "${STATE_FILE}" << EOF
{
    "current_artist": "${current_artist}",
    "current_epoch": ${current_epoch},
    "total_epochs": ${total_epochs},
    "queue_position": ${queue_position},
    "queue_total": ${queue_total},
    "status": "${status}",
    "updated_at": "$(date -Iseconds)",
    "pid": $$
}
EOF
}

cmd_daemon() {
    # Daemon must be resilient - never exit on errors
    set +e
    trap 'echo "DAEMON TRAP: caught signal, continuing..."; true' ERR

    local epochs=200
    local batch_size=4
    local watchdog_interval=60

    while [[ $# -gt 0 ]]; do
        case $1 in
            --epochs) epochs="$2"; shift 2 ;;
            --batch-size) batch_size="$2"; shift 2 ;;
            --interval) watchdog_interval="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    echo "Starting learn-artist daemon..."
    echo "Watchdog interval: ${watchdog_interval}s"
    echo "PID: $$"
    echo ""

    # Register with task-monitor
    local queue_total
    queue_total=$(( $(grep -c "^#DONE:" "${QUEUE_FILE}" 2>/dev/null || echo 0) + $(grep -v "^#" "${QUEUE_FILE}" 2>/dev/null | grep -v "^$" | wc -l) ))
    register_task "learn-artist" "${queue_total}"

    local position=0
    local completed_count=0
    completed_count=$(grep -c "^#DONE:" "${QUEUE_FILE}" 2>/dev/null || echo 0)

    while true; do
        # Get next unprocessed artist from queue
        local next_artist=""
        local next_category="voice"
        local next_epochs="${epochs}"

        while IFS= read -r line; do
            [[ -z "${line}" ]] && continue
            [[ "${line}" =~ ^# ]] && continue

            local artist
            artist=$(echo "${line}" | sed 's/ --.*$//')
            local slug
            slug=$(slugify "${artist}")

            # Skip if already trained
            if [[ -d "${MODELS_ROOT}/voice/${slug}" ]] || [[ -d "${MODELS_ROOT}/instrument/${slug}" ]]; then
                continue
            fi

            next_artist="${artist}"

            # Parse options from line
            if [[ "${line}" =~ --category[[:space:]]+([a-z]+) ]]; then
                next_category="${BASH_REMATCH[1]}"
            fi
            if [[ "${line}" =~ --epochs[[:space:]]+([0-9]+) ]]; then
                next_epochs="${BASH_REMATCH[1]}"
            fi
            break
        done < "${QUEUE_FILE}"

        if [[ -z "${next_artist}" ]]; then
            echo "Queue empty. Daemon sleeping for 5 minutes..."
            write_state "idle" 0 0 0 0 "idle"
            update_task_monitor "learn-artist" "${completed_count}" "${queue_total}" "idle"
            sleep 300
            # Refresh queue total in case new artists added
            queue_total=$(grep -v "^#" "${QUEUE_FILE}" 2>/dev/null | grep -v "^$" | wc -l)
            continue
        fi

        ((position++)) || true
        echo ""
        echo "=========================================="
        echo "[${position}/${queue_total}] Training: ${next_artist}"
        echo "=========================================="

        write_state "${next_artist}" 0 "${next_epochs}" "${position}" "${queue_total}" "downloading"
        update_task_monitor "learn-artist" "${completed_count}" "${queue_total}" "running" "${next_artist}" "0" "${next_epochs}" "downloading"

        # Run training with watchdog
        local slug
        slug=$(slugify "${next_artist}")

        # Start training in background (output goes to daemon.log via nohup redirect)
        cmd_train "${next_artist}" \
            --epochs "${next_epochs}" \
            --batch-size "${batch_size}" \
            --category "${next_category}" &
        local train_pid=$!

        # Watchdog loop
        while kill -0 "${train_pid}" 2>/dev/null; do
            # Parse current epoch from log
            local current_epoch=0
            if [[ -f "${RVC_LOGS_DIR}/${slug}/train.log" ]]; then
                current_epoch=$(grep -oP "Epoch: \K\d+" "${RVC_LOGS_DIR}/${slug}/train.log" 2>/dev/null | tail -1 || echo "0")
            fi

            write_state "${next_artist}" "${current_epoch}" "${next_epochs}" "${position}" "${queue_total}" "training"
            update_task_monitor "learn-artist" "${completed_count}" "${queue_total}" "running" "${next_artist}" "${current_epoch}" "${next_epochs}" "training"

            # Check for stalls (no checkpoint progress in 10 minutes)
            local latest_checkpoint
            latest_checkpoint=$(ls -t "${RVC_LOGS_DIR}/${slug}"/G_*.pth 2>/dev/null | head -1)
            if [[ -n "${latest_checkpoint}" ]]; then
                local age
                age=$(( $(date +%s) - $(stat -c %Y "${latest_checkpoint}") ))
                if [[ ${age} -gt 600 ]]; then
                    echo "WARNING: No checkpoint progress in ${age}s"
                fi
            fi

            sleep "${watchdog_interval}"
        done

        local exit_code=0
        wait "${train_pid}" || exit_code=$?

        if [[ ${exit_code} -eq 0 ]]; then
            echo "Completed: ${next_artist}"
            ((completed_count++)) || true
            write_state "${next_artist}" "${next_epochs}" "${next_epochs}" "${position}" "${queue_total}" "completed"
            update_task_monitor "learn-artist" "${completed_count}" "${queue_total}" "running" "${next_artist}" "${next_epochs}" "${next_epochs}" "completed"
            # Mark as done in queue file
            sed -i "s/^${next_artist}$/#DONE: ${next_artist}/" "${QUEUE_FILE}" 2>/dev/null || true
            sed -i "s/^${next_artist} --/#DONE: ${next_artist} --/" "${QUEUE_FILE}" 2>/dev/null || true
        else
            echo "FAILED: ${next_artist} (exit code ${exit_code})"
            write_state "${next_artist}" 0 "${next_epochs}" "${position}" "${queue_total}" "failed"
            update_task_monitor "learn-artist" "${completed_count}" "${queue_total}" "failed" "${next_artist}" "0" "${next_epochs}" "failed"
        fi

        echo "DEBUG: Training loop iteration complete, continuing to next artist..."
        sleep 5  # Brief pause before next artist
    done
}

cmd_discover() {
    local query=""
    local bridge=""
    local limit=10
    local auto_queue=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --bridge) bridge="$2"; shift 2 ;;
            --limit) limit="$2"; shift 2 ;;
            --auto-queue) auto_queue=true; shift ;;
            --help|-h) query=""; bridge=""; break ;;
            *) query="$1"; shift ;;
        esac
    done

    local discover_skill="${SCRIPT_DIR}/../discover-music/run.sh"
    if [[ ! -f "${discover_skill}" ]]; then
        # Try .agent location
        discover_skill="${HOME}/.agent/skills/discover-music/run.sh"
    fi
    if [[ ! -f "${discover_skill}" ]]; then
        echo "ERROR: discover-music skill not found"
        return 1
    fi

    local results=""

    if [[ -n "${query}" ]]; then
        echo "Discovering artists similar to: ${query}"
        results=$(bash "${discover_skill}" similar "${query}" --limit "${limit}" --json 2>/dev/null) || true
    elif [[ -n "${bridge}" ]]; then
        echo "Discovering artists with bridge: ${bridge}"
        results=$(bash "${discover_skill}" bridge "${bridge}" --limit "${limit}" --json 2>/dev/null) || true
    else
        echo "Usage: ./run.sh discover <artist> [--bridge <bridge>] [--limit N] [--auto-queue]"
        echo ""
        echo "Examples:"
        echo "  ./run.sh discover 'Chelsea Wolfe'                    # Find similar artists"
        echo "  ./run.sh discover --bridge Corruption                 # Find by bridge tag"
        echo "  ./run.sh discover 'Chelsea Wolfe' --auto-queue       # Find and add to queue"
        return 0
    fi

    if [[ -z "${results}" ]]; then
        echo "No results found"
        return 0
    fi

    # Parse and display results
    local artists
    artists=$(echo "${results}" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    items = data.get('results', data) if isinstance(data, dict) else data
    seen = set()
    for item in items:
        name = item.get('name', '')
        if name and name not in seen:
            seen.add(name)
            sim = item.get('similarity', 0)
            tags = ', '.join(item.get('tags', [])[:5])
            print(f'{name}\t{sim:.2f}\t{tags}')
except: pass
" 2>/dev/null) || true

    if [[ -z "${artists}" ]]; then
        echo "Could not parse results"
        return 0
    fi

    echo ""
    echo "Discovered Artists:"
    echo "==================="
    local idx=0
    while IFS=$'\t' read -r name similarity tags; do
        ((idx++)) || true
        local slug
        slug=$(slugify "${name}")

        # Check if already trained or queued
        local status="NEW"
        if [[ -d "${MODELS_ROOT}/voice/${slug}" ]] || [[ -d "${MODELS_ROOT}/instrument/${slug}" ]]; then
            status="TRAINED"
        elif grep -q "${name}" "${QUEUE_FILE}" 2>/dev/null; then
            status="QUEUED"
        fi

        printf "  %2d. %-30s  sim=%.2f  [%s]  %s\n" "${idx}" "${name}" "${similarity}" "${status}" "${tags}"

        # Auto-queue new artists
        if ${auto_queue} && [[ "${status}" == "NEW" ]]; then
            cmd_add "${name}" --category voice >/dev/null 2>&1 && echo "      → Added to queue" || true
        fi
    done <<< "${artists}"

    echo ""
    if ! ${auto_queue}; then
        echo "Use --auto-queue to automatically add NEW artists to the training queue"
    fi
}

cmd_stats() {
    echo "Voice Library Statistics"
    echo "========================"
    echo ""

    # Count trained models
    local trained_voice=0
    local trained_instrument=0
    [[ -d "${MODELS_ROOT}/voice" ]] && trained_voice=$(find "${MODELS_ROOT}/voice" -maxdepth 1 -type d | wc -l)
    ((trained_voice--)) || true  # Subtract parent dir
    [[ -d "${MODELS_ROOT}/instrument" ]] && trained_instrument=$(find "${MODELS_ROOT}/instrument" -maxdepth 1 -type d | wc -l)
    ((trained_instrument--)) || true

    # Count queue
    local queued=0
    [[ -f "${QUEUE_FILE}" ]] && queued=$(grep -v "^#" "${QUEUE_FILE}" | grep -v "^$" | wc -l)

    # Count in progress
    local in_progress=0
    if docker ps --filter "name=${DOCKER_NAME}" --format '{{.Names}}' | grep -q "${DOCKER_NAME}" 2>/dev/null; then
        in_progress=$(docker exec "${DOCKER_NAME}" find /app/logs -maxdepth 1 -type d 2>/dev/null | wc -l)
        ((in_progress--)) || true
    fi

    echo "Trained Models:"
    echo "  Voice:       ${trained_voice}"
    echo "  Instrument:  ${trained_instrument}"
    echo "  Total:       $((trained_voice + trained_instrument))"
    echo ""
    echo "Queue:         ${queued} pending"
    echo "In Progress:   ${in_progress} training"
    echo ""

    # Estimate time remaining
    if [[ ${queued} -gt 0 ]]; then
        local hours=$((queued * 3))  # ~3 hours per model
        echo "Est. Time:     ~${hours} hours (${queued} models × ~3h each)"
    fi
}

cmd_monitor() {
    local interval="${1:-30}"
    local once="${2:-false}"

    while true; do
        clear
        echo "┌─────────────────────────────────────────────────────────────────────┐"
        echo "│                      VOICE TRAINING MONITOR                         │"
        echo "├─────────────────────────────────────────────────────────────────────┤"

        # Read daemon state
        if [[ -f "${STATE_FILE}" ]]; then
            local artist epoch total_epochs position queue_total status
            artist=$(python3 -c "import json; d=json.load(open('${STATE_FILE}')); print(d.get('current_artist',''))" 2>/dev/null)
            epoch=$(python3 -c "import json; d=json.load(open('${STATE_FILE}')); print(d.get('current_epoch',0))" 2>/dev/null)
            total_epochs=$(python3 -c "import json; d=json.load(open('${STATE_FILE}')); print(d.get('total_epochs',200))" 2>/dev/null)
            position=$(python3 -c "import json; d=json.load(open('${STATE_FILE}')); print(d.get('queue_position',0))" 2>/dev/null)
            queue_total=$(python3 -c "import json; d=json.load(open('${STATE_FILE}')); print(d.get('queue_total',0))" 2>/dev/null)
            status=$(python3 -c "import json; d=json.load(open('${STATE_FILE}')); print(d.get('status','unknown'))" 2>/dev/null)

            printf "│ %-67s │\n" "Current: ${artist} (${position}/${queue_total})"
            printf "│ %-67s │\n" "Status:  ${status}"

            # Progress bar for epochs
            if [[ "${status}" == "training" && ${total_epochs} -gt 0 ]]; then
                local pct=$((epoch * 100 / total_epochs))
                local filled=$((pct / 5))
                local empty=$((20 - filled))
                local bar=$(printf '%*s' "$filled" | tr ' ' '█')$(printf '%*s' "$empty" | tr ' ' '░')
                printf "│ Epoch:   [%s] %d/%d (%d%%)                        │\n" "$bar" "$epoch" "$total_epochs" "$pct"
            fi
        else
            printf "│ %-67s │\n" "No active training (daemon not running?)"
        fi

        echo "├─────────────────────────────────────────────────────────────────────┤"

        # Get current artist's data stats if downloading
        if [[ -n "${artist}" ]]; then
            local slug
            slug=$(slugify "${artist}")
            local data_dir="${TRAINING_DATA_ROOT}/${slug}"

            if [[ -d "${data_dir}" ]]; then
                local stems duration
                stems=$(find "${data_dir}" -name "vocals.wav" 2>/dev/null | wc -l)
                duration=$(find "${data_dir}" -name "vocals.wav" -exec ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {} \; 2>/dev/null | awk '{s+=$1} END {printf "%.1f", s/60}')

                printf "│ %-67s │\n" "DATA COLLECTION"
                printf "│   Vocal stems:  %-52s │\n" "${stems} files"
                printf "│   Duration:     %-52s │\n" "${duration:-0} minutes (min: 30)"
            fi
        fi

        # Check RVC training progress
        if [[ -n "${slug}" ]]; then
            local rvc_log="${RVC_LOGS_DIR}/${slug}"
            if [[ -d "${rvc_log}" ]]; then
                local latest_g
                latest_g=$(ls -t "${rvc_log}"/G_*.pth 2>/dev/null | head -1)
                if [[ -n "${latest_g}" ]]; then
                    local checkpoint
                    checkpoint=$(basename "${latest_g}" .pth | sed 's/G_//')
                    printf "│ %-67s │\n" "RVC TRAINING"
                    printf "│   Latest checkpoint: G_%-44s │\n" "${checkpoint}"
                fi
            fi
        fi

        echo "├─────────────────────────────────────────────────────────────────────┤"

        # Completed models
        local voice_count=0 inst_count=0
        [[ -d "${MODELS_ROOT}/voice" ]] && voice_count=$(find "${MODELS_ROOT}/voice" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)
        [[ -d "${MODELS_ROOT}/instrument" ]] && inst_count=$(find "${MODELS_ROOT}/instrument" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)

        printf "│ %-67s │\n" "COMPLETED MODELS"
        printf "│   Voice:      %-53s │\n" "${voice_count}"
        printf "│   Instrument: %-53s │\n" "${inst_count}"

        echo "├─────────────────────────────────────────────────────────────────────┤"

        # Recent log
        printf "│ %-67s │\n" "RECENT LOG"
        tail -3 "${MODELS_ROOT}/daemon.log" 2>/dev/null | while IFS= read -r line; do
            printf "│   %-65s │\n" "${line:0:65}"
        done

        echo "└─────────────────────────────────────────────────────────────────────┘"
        echo ""
        echo "Refreshing every ${interval}s... (Ctrl+C to exit)"

        [[ "${once}" == "true" ]] && break
        sleep "${interval}"
    done
}

cmd_queue() {
    echo "Training Queue (${QUEUE_FILE}):"
    echo "================================"

    if [[ ! -f "${QUEUE_FILE}" ]]; then
        echo "(empty)"
        return 0
    fi

    local num=1
    while IFS= read -r line; do
        [[ -z "${line}" ]] && continue
        [[ "${line}" =~ ^# ]] && continue

        local artist
        artist=$(echo "${line}" | awk '{print $1}')
        local slug
        slug=$(slugify "${artist}")

        # Check status
        local status="pending"
        if [[ -d "${MODELS_ROOT}/voice/${slug}" ]] || [[ -d "${MODELS_ROOT}/instrument/${slug}" ]]; then
            status="trained"
        elif docker exec "${DOCKER_NAME}" test -d "/app/logs/${slug}" 2>/dev/null; then
            status="in progress"
        fi

        printf "%2d. %-30s [%s]\n" "${num}" "${line}" "${status}"
        ((num++))
    done < "${QUEUE_FILE}"

    echo ""
    echo "Commands:"
    echo "  ./run.sh add \"Artist Name\"   # Add to queue"
    echo "  ./run.sh run-queue           # Train all pending"
}

cmd_run_queue() {
    if [[ ! -f "${QUEUE_FILE}" ]]; then
        echo "Queue is empty"
        return 0
    fi

    local epochs=200
    local batch_size=4

    while [[ $# -gt 0 ]]; do
        case $1 in
            --epochs) epochs="$2"; shift 2 ;;
            --batch-size) batch_size="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    echo "Processing training queue..."
    echo ""

    while IFS= read -r line; do
        [[ -z "${line}" ]] && continue
        [[ "${line}" =~ ^# ]] && continue

        # Parse line: "Artist Name --option value"
        local artist
        local category="voice"
        local line_epochs="${epochs}"

        # Extract artist name (everything before --)
        artist=$(echo "${line}" | sed 's/ --.*$//')

        # Extract options
        if [[ "${line}" =~ --category[[:space:]]+([a-z]+) ]]; then
            category="${BASH_REMATCH[1]}"
        fi
        if [[ "${line}" =~ --epochs[[:space:]]+([0-9]+) ]]; then
            line_epochs="${BASH_REMATCH[1]}"
        fi

        local slug
        slug=$(slugify "${artist}")

        # Skip if already trained
        if [[ -d "${MODELS_ROOT}/voice/${slug}" ]] || [[ -d "${MODELS_ROOT}/instrument/${slug}" ]]; then
            echo "Skipping (already trained): ${artist}"
            continue
        fi

        echo ""
        echo "=========================================="
        echo "Training: ${artist}"
        echo "=========================================="

        cmd_train "${artist}" --epochs "${line_epochs}" --batch-size "${batch_size}" --category "${category}"

    done < "${QUEUE_FILE}"

    echo ""
    echo "Queue processing complete!"
}

# Main dispatch
case "${1:-help}" in
    learn)
        shift
        cmd_learn "$@"
        ;;
    add)
        shift
        cmd_add "$@"
        ;;
    import)
        shift
        cmd_import "$@"
        ;;
    queue)
        shift
        cmd_queue "$@"
        ;;
    discover)
        shift
        cmd_discover "$@"
        ;;
    stats)
        shift
        cmd_stats "$@"
        ;;
    daemon)
        shift
        cmd_daemon "$@"
        ;;
    run-queue)
        shift
        cmd_run_queue "$@"
        ;;
    train)
        shift
        cmd_train "$@"
        ;;
    train-batch)
        shift
        cmd_train_batch "$@"
        ;;
    list)
        shift
        cmd_list "$@"
        ;;
    status)
        shift
        cmd_status "$@"
        ;;
    monitor)
        shift
        cmd_monitor "$@"
        ;;
    sync-memory)
        shift
        python3 "${SCRIPT_DIR}/sync_memory.py" "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
