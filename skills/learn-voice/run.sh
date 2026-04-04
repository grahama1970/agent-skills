#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# learn-voice: Train RVC voice/instrument models from artist names
set -euo pipefail

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
CREATE_MUSIC_DIR="${SCRIPT_DIR}/../create-music"

# Storage paths
TRAINING_DATA_ROOT="/mnt/storage12tb/media/music/rvc-training"
MODELS_ROOT="/mnt/storage12tb/media/music/rvc-models"
RVC_LOGS_DIR="${CREATE_MUSIC_DIR}/rvc/logs"

# Docker settings
DOCKER_IMAGE="cherrymint/rvc_webui:rvc_boss"
DOCKER_NAME="rvc-training"

QUEUE_FILE="${MODELS_ROOT}/queue.txt"
STATE_FILE="${MODELS_ROOT}/daemon-state.json"
TASK_MONITOR_DIR="${SCRIPT_DIR}/../task-monitor"
TASK_MONITOR_API="http://localhost:8765"

show_help() {
    cat << 'EOF'
learn-voice: Train RVC voice models from artist names

Usage: ./run.sh <command> [options]

Commands:
  learn <artist> [type]    Easiest way - just say who to learn
  add <artist>             Add artist to training queue
  import <file>            Bulk import from CSV/JSON/text file
  queue                    Show current queue
  stats                    Show library statistics
  monitor [interval]       Live progress monitor (default: 30s refresh)
  daemon                   Run continuous training daemon (with watchdog)
  run-queue                Process all queued artists (one-shot)
  train <artist>           Train a voice model immediately
  list                     List trained voice models
  status <model>           Check training status

Simple Examples (for agents):
  ./run.sh learn "Tom Waits"
  ./run.sh learn "Keith Moon" drummer
  ./run.sh learn "Miles Davis" trumpet

Advanced Examples:
  ./run.sh add "Sierra Ferrell"
  ./run.sh add "JIREH"
  ./run.sh add "Pedal Steel" --category instrument
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
    echo "Consolidating vocal stems..."
    find "${output_dir}" -path "*/stems/demucs/htdemucs/*/vocals.wav" -exec sh -c '
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
        echo "Warning: Only ${minutes} minutes of audio (target: ${min_minutes})"
    fi

    echo "${output_dir}/vocals_all"
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

    echo "Building index for ${slug}..."
    docker exec "${DOCKER_NAME}" python /app/tools/infer/train-index-v2.py \
        "/app/logs/${slug}" \
        v2
}

save_model() {
    local slug="$1"
    local artist="$2"
    local category="${3:-voice}"

    local model_dir="${MODELS_ROOT}/${category}/${slug}"
    mkdir -p "${model_dir}"

    # Copy model files
    local latest_g
    latest_g=$(ls -t "${RVC_LOGS_DIR}/${slug}"/G_*.pth 2>/dev/null | head -1)
    if [[ -n "${latest_g}" ]]; then
        cp "${latest_g}" "${model_dir}/${slug}.pth"
    fi

    # Copy index
    local index_file="${RVC_LOGS_DIR}/${slug}/added_*.index"
    if ls ${index_file} 1>/dev/null 2>&1; then
        cp ${index_file} "${model_dir}/${slug}.index"
    fi

    # Create metadata
    cat > "${model_dir}/metadata.json" << EOF
{
    "name": "${slug}",
    "artist": "${artist}",
    "category": "${category}",
    "trained_at": "$(date -Iseconds)",
    "version": "v2",
    "sample_rate": "40k"
}
EOF

    echo "Model saved to ${model_dir}"
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

    if [[ "${skip_download}" != "true" ]]; then
        download_and_separate "${artist}" "${slug}" "${min_tracks}" "${min_minutes}"
    fi

    # Mount the new dataset
    docker exec "${DOCKER_NAME}" ln -sf "/app/datasets/${slug}/vocals_all" "/app/datasets/${slug}-vocals" 2>/dev/null || true

    preprocess "${slug}"
    extract_f0 "${slug}"
    extract_features "${slug}"
    generate_filelist "${slug}"
    train_model "${slug}" "${epochs}" "${batch_size}"
    build_index "${slug}"
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
    local current="$2"
    local total="$3"
    local status="${4:-running}"

    # Update via HTTP API if available
    curl -s -X POST "${TASK_MONITOR_API}/api/tasks/${name}" \
        -H "Content-Type: application/json" \
        -d "{\"current\": ${current}, \"total\": ${total}, \"status\": \"${status}\"}" \
        2>/dev/null || true
}

register_task() {
    local name="$1"
    local total="$2"

    curl -s -X POST "${TASK_MONITOR_API}/api/tasks" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${name}\", \"total\": ${total}, \"current\": 0, \"status\": \"pending\"}" \
        2>/dev/null || true
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

    echo "Starting learn-voice daemon..."
    echo "Watchdog interval: ${watchdog_interval}s"
    echo "PID: $$"
    echo ""

    # Register with task-monitor
    local queue_total
    queue_total=$(grep -v "^#" "${QUEUE_FILE}" 2>/dev/null | grep -v "^$" | wc -l)
    register_task "learn-voice" "${queue_total}"

    local position=0

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
            update_task_monitor "learn-voice" "${position}" "${queue_total}" "idle"
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
        update_task_monitor "learn-voice" "${position}" "${queue_total}" "running"

        # Run training with watchdog
        local slug
        slug=$(slugify "${next_artist}")

        # Start training in background
        (
            cmd_train "${next_artist}" \
                --epochs "${next_epochs}" \
                --batch-size "${batch_size}" \
                --category "${next_category}" 2>&1 | tee -a "${MODELS_ROOT}/daemon.log"
        ) &
        local train_pid=$!

        # Watchdog loop
        while kill -0 "${train_pid}" 2>/dev/null; do
            # Parse current epoch from log
            local current_epoch=0
            if [[ -f "${RVC_LOGS_DIR}/${slug}/train.log" ]]; then
                current_epoch=$(grep -oP "Epoch: \K\d+" "${RVC_LOGS_DIR}/${slug}/train.log" 2>/dev/null | tail -1 || echo "0")
            fi

            write_state "${next_artist}" "${current_epoch}" "${next_epochs}" "${position}" "${queue_total}" "training"

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

        wait "${train_pid}"
        local exit_code=$?

        if [[ ${exit_code} -eq 0 ]]; then
            echo "Completed: ${next_artist}"
            write_state "${next_artist}" "${next_epochs}" "${next_epochs}" "${position}" "${queue_total}" "completed"
        else
            echo "FAILED: ${next_artist} (exit code ${exit_code})"
            write_state "${next_artist}" 0 "${next_epochs}" "${position}" "${queue_total}" "failed"
        fi
    done
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
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
