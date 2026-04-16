#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# /voice-lab — Unified voice workbench: TTS eval, RVC sweep, recording, sessions, lessons

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$SCRIPT_DIR"

# Ensure uv available
if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Sync dependencies if needed
if [[ ! -d ".venv" ]]; then
    uv sync --quiet
fi

## Helper: resolve a friendly sink name to PipeWire port prefix
## wpctl set-default only affects NEW streams; pw-link moves EXISTING ones
_resolve_sink_port() {
    local name="$1"
    case "$name" in
        BTunes*|btunes*|bluetooth|bt)
            echo "bluez_output.00_18_91_8C_90_5C.1" ;;
        *Jabra*|jabra*|speaker)
            echo "alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo" ;;
        *Front*Headphone*|wired|usb)
            pw-link -i 2>/dev/null | grep "HiFi.*sink:playback_FL" | grep -v "monitor" | head -1 | sed 's/:.*//'; return ;;
        *)
            # Try matching directly in pw-link input ports
            pw-link -i 2>/dev/null | grep -i "$name" | head -1 | sed 's/:.*//'; return ;;
    esac
}

## Helper: route all active audio streams to a target sink
_route_streams_to_sink() {
    local friendly_name="$1"
    local target_port
    target_port=$(_resolve_sink_port "$friendly_name")

    if [[ -z "$target_port" ]]; then
        echo "  WARN: Cannot resolve sink for '$friendly_name'"
        return 1
    fi

    # Verify target ports exist
    if ! pw-link -i 2>/dev/null | grep -qF "${target_port}:playback_FL"; then
        echo "  WARN: Sink ports not found for $target_port"
        return 1
    fi

    # Set as default for future streams
    # Look for the sink ID in wpctl status Sinks section by matching the target port or friendly name
    local sink_id
    sink_id=$(wpctl status 2>/dev/null | awk '/Sinks:/,/Sink endpoints:/' | grep -i "$friendly_name" | grep -oP '\d+\.' | head -1 | tr -d '.') || true
    if [[ -n "$sink_id" ]]; then
        wpctl set-default "$sink_id" 2>/dev/null && echo "  Default sink: $friendly_name (id $sink_id)"
    fi

    # Find and move all active audio output streams
    local moved=0
    # Get all output ports that are app streams (not monitors, not midi)
    while IFS= read -r src_port; do
        [[ -z "$src_port" ]] && continue
        # Skip monitor ports and non-audio
        echo "$src_port" | grep -qE "monitor|Midi|capture" && continue

        # Find where this source is currently linked
        local current_dest
        current_dest=$(pw-link -l 2>/dev/null | grep -F "$src_port" | grep "|<-" | head -1) || true
        # pw-link -l might not work well, try pw-link -o -l approach
        # Instead, just try to link — pw-link is idempotent for existing links

        local channel
        channel=$(echo "$src_port" | sed 's/.*output_/playback_/')
        local target_dst="${target_port}:${channel}"

        if pw-link -i 2>/dev/null | grep -qF "$target_dst"; then
            # Disconnect from any current sink
            while IFS= read -r existing_link; do
                [[ -z "$existing_link" ]] && continue
                pw-link -d "$src_port" "$existing_link" 2>/dev/null || true
            done < <(pw-link -i 2>/dev/null | grep "playback_" | while read -r inp; do
                pw-link -l 2>/dev/null | grep -qF "$src_port" && grep -qF "$inp" && echo "$inp"
            done 2>/dev/null || true)

            # Brute-force disconnect from known sinks that aren't the target
            for sink_prefix in \
                "alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo" \
                "bluez_output.00_18_91_8C_90_5C.1"; do
                [[ "$sink_prefix" == "$target_port" ]] && continue
                pw-link -d "$src_port" "${sink_prefix}:${channel}" 2>/dev/null || true
            done

            # Connect to target
            pw-link "$src_port" "$target_dst" 2>/dev/null && moved=$((moved + 1))
        fi
    done < <(pw-link -o 2>/dev/null | grep "output_F[LR]$")

    if [[ $moved -gt 0 ]]; then
        echo "  Moved $((moved / 2)) stream(s) to ${target_port%%.*}..."
    else
        echo "  No active streams to move (default set for future playback)"
    fi
}

CMD="${1:-help}"
shift || true

case "$CMD" in
    # --- TTS Quality (original voice-lab) ---
    test)
        uv run --project "$SCRIPT_DIR" python voice_lab.py test "$@"
        ;;
    waveform)
        uv run --project "$SCRIPT_DIR" python voice_lab.py waveform "$@"
        ;;
    eval)
        uv run --project "$SCRIPT_DIR" python voice_lab.py eval "$@"
        ;;
    compare)
        uv run --project "$SCRIPT_DIR" python voice_lab.py compare "$@"
        ;;
    iterate)
        uv run --project "$SCRIPT_DIR" python voice_lab.py iterate "$@"
        ;;
    status)
        uv run --project "$SCRIPT_DIR" python voice_lab.py status "$@"
        ;;

    # --- RVC Parameter Sweep (merged from hum-lab) ---
    sweep)
        uv run --project "$SCRIPT_DIR" python voice_lab.py sweep "$@"
        ;;
    rank)
        uv run --project "$SCRIPT_DIR" python voice_lab.py rank "$@"
        ;;
    preset)
        uv run --project "$SCRIPT_DIR" python voice_lab.py preset "$@"
        ;;
    presets)
        uv run --project "$SCRIPT_DIR" python voice_lab.py presets "$@"
        ;;

    # --- PipeWire Recording ---
    devices)
        uv run --project "$SCRIPT_DIR" python voice_lab.py devices "$@"
        ;;
    record)
        uv run --project "$SCRIPT_DIR" python voice_lab.py record "$@"
        ;;

    # --- Follow-Along Sessions ---
    follow)
        uv run --project "$SCRIPT_DIR" python voice_lab.py follow "$@"
        ;;

    # --- Unified Voice Lab App (tabbed) ---
    edit)
        ARGS=("$@")
        if [[ -n "${YOUTUBE_URL:-}" ]]; then
            ARGS+=(--youtube-url "$YOUTUBE_URL")
        fi
        uv run --project "$SCRIPT_DIR" --extra editor python voice_lab.py edit "${ARGS[@]}"
        ;;

    gui|app)
        uv run --project "$SCRIPT_DIR" --extra editor python voice_lab.py gui "$@"
        ;;

    # --- Agent-Human Collaborative Workflow ---
    hum-session)
        # One-command humming session: agent runs this, Graham hums
        # Defaults: Jabra mic, wired headphones for playback, Embry persona
        # Env vars: PERSONA, TRACK, HEADPHONES (wired|bluetooth)
        PERSONA="${PERSONA:-embry}"
        TRACK="${TRACK:-hawaiian_war_chant}"
        HEADPHONES="${HEADPHONES:-wired}"
        HUM_CACHE="/mnt/storage12tb/media/personas/${PERSONA}/hum-cache"
        CLIP="${HUM_CACHE}/${TRACK}_vocals.wav"
        SRT="${HUM_CACHE}/${TRACK}.srt"

        if [[ ! -f "$CLIP" ]]; then
            echo "ERROR: Vocals not found: $CLIP"
            echo "Run './run.sh prepare' first"
            exit 1
        fi
        if [[ ! -f "$SRT" ]]; then
            echo "WARN: No SRT found: $SRT — running without karaoke display"
            SRT=""
        fi

        # Resolve headphone device
        case "$HEADPHONES" in
            wired|usb)
                HP_DEVICE="Front Headphones"
                HP_LABEL="USB Audio Front Headphones (wired, ~0ms latency)"
                ;;
            bluetooth|bt|btunes)
                HP_DEVICE="BTunes"
                HP_LABEL="BTunes M50X/5 (aptX Bluetooth, ~40ms latency)"
                ;;
            *)
                HP_DEVICE="$HEADPHONES"
                HP_LABEL="$HEADPHONES (custom)"
                ;;
        esac

        echo "=== Embry Hum Session ==="
        echo "Track:      $TRACK"
        echo "Mic:        Jabra SPEAK 510"
        echo "Headphones: $HP_LABEL"
        echo "Persona:    $PERSONA"
        echo ""
        echo "Graham: Put on headphones. You'll hear the reference track."
        echo "         The Jabra will record your humming."
        echo ""

        # Route all active audio streams to headphones (pw-link moves existing streams)
        echo "Routing audio to headphones..."
        _route_streams_to_sink "$HP_DEVICE"
        echo ""

        ARGS=(
            --clip "$CLIP"
            --device "Jabra"
            --headphones "$HP_DEVICE"
            --persona "$PERSONA"
        )
        if [[ -n "$SRT" ]]; then
            ARGS+=(--srt "$SRT")
        fi
        # Pass the original vocals as stem for alignment comparison
        if [[ -f "$CLIP" ]]; then
            ARGS+=(--stem "$CLIP")
        fi
        uv run --project "$SCRIPT_DIR" python voice_lab.py follow "${ARGS[@]}" "$@"
        ;;

    route-audio)
        # Route all active streams to a specific sink
        # Usage: ./run.sh route-audio bluetooth|wired|jabra
        TARGET="${1:-bluetooth}"
        case "$TARGET" in
            bluetooth|bt|btunes) _route_streams_to_sink "BTunes" ;;
            wired|usb|headphones) _route_streams_to_sink "Front Headphones" ;;
            jabra|speaker) _route_streams_to_sink "Jabra" ;;
            *) _route_streams_to_sink "$TARGET" ;;
        esac
        ;;

    prepare)
        # Full readiness check for a collaborative agent-human hum session
        # Verifies: audio routing, Jabra recording, clip + SRT, RVC model, Docker
        PERSONA="${PERSONA:-embry}"
        TRACK="${TRACK:-hawaiian_war_chant}"
        HEADPHONES="${HEADPHONES:-bluetooth}"
        HUM_CACHE="/mnt/storage12tb/media/personas/${PERSONA}/hum-cache"
        RVC_DIR="/mnt/storage12tb/media/music/rvc-models/voice/${PERSONA}"
        OK=true

        echo "=== Hum Session Readiness Check ==="
        echo "Persona: $PERSONA | Track: $TRACK | Headphones: $HEADPHONES"
        echo ""

        # ── 1. Bluetooth Headphones: Connected & Routed ──────────
        echo "── Audio Routing ──"
        if wpctl status 2>/dev/null | grep -qi "btunes"; then
            CODEC=$(pw-cli info 103 2>/dev/null | grep "api.bluez5.codec" | sed 's/.*= "\(.*\)"/\1/' || echo "unknown")
            PROFILE=$(pw-cli info 103 2>/dev/null | grep "api.bluez5.profile" | sed 's/.*= "\(.*\)"/\1/' || echo "unknown")
            echo "✓ BTunes M50X/5 connected (codec: ${CODEC}, profile: ${PROFILE})"

            # Check if BTunes is the default sink (for new streams)
            DEFAULT_SINK=$(wpctl inspect @DEFAULT_AUDIO_SINK@ 2>/dev/null | grep "node.description" | sed 's/.*= "\(.*\)"/\1/')
            if echo "$DEFAULT_SINK" | grep -qi "btunes"; then
                echo "✓ BTunes is default sink (new streams route here)"
            else
                echo "⚠ Default sink is '$DEFAULT_SINK' — routing to BTunes..."
                _route_streams_to_sink "BTunes"
            fi

            # Check if any active streams are going to wrong sink
            JABRA_STREAMS=$(wpctl status 2>/dev/null | grep -c "Jabra.*playback.*active" || true)
            if [[ "$JABRA_STREAMS" -gt 0 ]]; then
                echo "⚠ ${JABRA_STREAMS} stream(s) still on Jabra — moving to BTunes..."
                _route_streams_to_sink "BTunes"
            else
                echo "✓ No streams misrouted to Jabra speaker"
            fi
        else
            echo "⚠ BTunes M50X/5 not connected"
            if wpctl status 2>/dev/null | grep -qi "front headphones"; then
                echo "✓ Fallback: Wired headphones available (USB Audio Front Headphones)"
            else
                echo "✗ No headphones available"
                OK=false
            fi
        fi
        echo ""

        # ── 2. Jabra Recording Test ──────────────────────────────
        echo "── Jabra Mic Recording Test ──"
        if wpctl status 2>/dev/null | grep -qi "jabra.*source\|jabra.*mono"; then
            JABRA_VOL=$(wpctl get-volume 61 2>/dev/null | awk '{print $2}')
            echo "✓ Jabra SPEAK 510 mic connected (volume: ${JABRA_VOL})"

            # Quick 1-second recording test
            TEST_WAV="/tmp/voice_lab_mic_test.wav"
            rm -f "$TEST_WAV"
            pw-record --target 61 --rate 48000 --channels 1 --format s16 "$TEST_WAV" &
            TEST_PID=$!
            sleep 1.5
            kill $TEST_PID 2>/dev/null || true
            wait $TEST_PID 2>/dev/null || true

            if [[ -f "$TEST_WAV" ]] && [[ $(stat -c%s "$TEST_WAV" 2>/dev/null || echo 0) -gt 1000 ]]; then
                MIC_INFO=$(uv run --project "$SCRIPT_DIR" python -c "
import soundfile as sf; import numpy as np
a, sr = sf.read('$TEST_WAV')
rms_db = 20*np.log10(np.sqrt(np.mean(a**2))+1e-10)
peak_db = 20*np.log10(np.max(np.abs(a))+1e-10)
print(f'rms={rms_db:.0f}dB peak={peak_db:.0f}dB sr={sr}')
" 2>/dev/null) || MIC_INFO="parse_failed"

                echo "✓ Jabra recording works ($MIC_INFO)"
                rm -f "$TEST_WAV"
            else
                echo "✗ Jabra recording FAILED — pw-record produced no output"
                OK=false
            fi
        else
            echo "✗ Jabra SPEAK 510 NOT found"
            OK=false
        fi
        echo ""

        # ── 3. Clip + SRT ────────────────────────────────────────
        echo "── Track: ${TRACK} ──"
        if [[ -f "${HUM_CACHE}/${TRACK}_vocals.wav" ]]; then
            VOCALS_INFO=$(uv run --project "$SCRIPT_DIR" python -c "
import soundfile as sf
a, sr = sf.read('${HUM_CACHE}/${TRACK}_vocals.wav')
dur = len(a)/sr
print(f'{dur:.0f}s {sr}Hz')
" 2>/dev/null) || VOCALS_INFO="unknown"
            echo "✓ Original vocals: ${TRACK}_vocals.wav (${VOCALS_INFO})"
        else
            echo "✗ Original vocals MISSING: ${HUM_CACHE}/${TRACK}_vocals.wav"
            OK=false
        fi

        if [[ -f "${HUM_CACHE}/${TRACK}.srt" ]]; then
            SEG_COUNT=$(grep -c "^[0-9]\+$" "${HUM_CACHE}/${TRACK}.srt" 2>/dev/null || echo "0")
            echo "✓ SRT file: ${TRACK}.srt (${SEG_COUNT} segments)"
        else
            echo "✗ SRT file MISSING: ${HUM_CACHE}/${TRACK}.srt"
            echo "  Create with: whisper or manual timing sections"
            OK=false
        fi

        if [[ -f "${HUM_CACHE}/${TRACK}.wav" ]]; then
            echo "✓ Converted cache: ${TRACK}.wav (Embry voice)"
        fi
        echo ""

        # ── 4. RVC Model & Docker ────────────────────────────────
        echo "── RVC Infrastructure ──"
        if [[ -f "${RVC_DIR}/${PERSONA}.pth" ]]; then
            MODEL_SIZE=$(du -sh "${RVC_DIR}/${PERSONA}.pth" 2>/dev/null | awk '{print $1}')
            echo "✓ RVC model: ${PERSONA}.pth (${MODEL_SIZE})"
        else
            echo "✗ RVC model MISSING"
            OK=false
        fi

        if [[ -f "${RVC_DIR}/${PERSONA}.index" ]]; then
            echo "✓ FAISS index: ${PERSONA}.index"
        else
            echo "⚠ FAISS index missing (sweep will work without it)"
        fi

        if docker ps --filter name=rvc-training --format '{{.Names}}' 2>/dev/null | grep -q rvc-training; then
            echo "✓ Docker RVC container running"
        else
            echo "✗ Docker RVC container NOT running"
            OK=false
        fi
        echo ""

        # ── 5. Storage & References ──────────────────────────────
        echo "── Storage ──"
        for dir in references lab-results presets; do
            if [[ -d "${HUM_CACHE}/${dir}" ]]; then
                COUNT=$(find "${HUM_CACHE}/${dir}" -maxdepth 1 -type f 2>/dev/null | wc -l)
                echo "✓ ${dir}/ (${COUNT} files)"
            else
                mkdir -p "${HUM_CACHE}/${dir}"
                echo "✓ ${dir}/ (created)"
            fi
        done

        TTS_DIR="/mnt/storage12tb/media/personas/${PERSONA}/tts_output"
        TTS_COUNT=$(find "$TTS_DIR" -name "*.wav" 2>/dev/null | wc -l)
        echo "✓ TTS reference samples: ${TTS_COUNT} WAV files"

        if ls "${HUM_CACHE}/references/"*".wav" &>/dev/null; then
            echo "✓ Human reference recording exists"
        else
            echo "⚠ No human reference recording yet — will be created during session"
        fi
        echo ""

        # ── Summary ──────────────────────────────────────────────
        if $OK; then
            echo "═══ READY ═══"
            echo ""
            echo "Run:  HEADPHONES=$HEADPHONES ./run.sh hum-session"
            echo ""
            echo "Workflow:"
            echo "  1. Graham puts on headphones (${HEADPHONES})"
            echo "  2. Agent runs: ./run.sh hum-session"
            echo "  3. 3-second countdown, then reference plays in headphones"
            echo "  4. Graham hums along — Jabra records"
            echo "  5. Agent evaluates alignment + similarity"
            echo "  6. Agent runs sweep: ./run.sh sweep --persona $PERSONA --track $TRACK"
        else
            echo "═══ NOT READY ═══"
            echo "Fix the ✗ issues above before starting"
        fi
        ;;

    # --- Voice Lesson Packages ---
    lesson)
        uv run --project "$SCRIPT_DIR" python voice_lab.py lesson "$@"
        ;;

    # --- Quality Gate ---
    gate)
        uv run --project "$SCRIPT_DIR" python voice_lab.py gate "$@"
        ;;

    # --- Alignment ---
    align)
        uv run --project "$SCRIPT_DIR" python voice_lab.py align "$@"
        ;;

    # --- Sanity ---
    sanity)
        bash "${SCRIPT_DIR}/sanity.sh"
        ;;

    help|--help|-h)
        echo "voice-lab: Unified voice workbench"
        echo ""
        echo "TTS Quality:"
        echo "  test               Generate test audio from trained voice model"
        echo "  waveform           Visualize audio waveform (ASCII or HTML)"
        echo "  eval               Run quality evaluation on generated voice"
        echo "  compare            Compare different checkpoints or models"
        echo "  iterate            Self-improvement iteration loop"
        echo "  status             Show voice training status"
        echo ""
        echo "RVC Parameter Sweep (from hum-lab):"
        echo "  sweep              Full parameter sweep (diagnostic + cross phases)"
        echo "  rank               Show ranked results from last sweep"
        echo "  preset             Save or load parameter presets"
        echo "  presets            List all presets for a persona"
        echo ""
        echo "PipeWire Recording:"
        echo "  devices            List PipeWire audio devices"
        echo "  record             Record audio from PipeWire device"
        echo ""
        echo "Follow-Along Sessions:"
        echo "  follow             Play clip + record simultaneously with SRT display"
        echo "  edit               Open unified app on Record tab with session loaded"
        echo "                     Env: YOUTUBE_URL=https://www.youtube.com/embed/..."
        echo "  gui|app            Unified voice lab app (tabbed: Record, TTS, Dashboard)"
        echo "                     Options: --tab record|tts-compare|dashboard|rvc-sweep"
        echo ""
        echo "Agent-Human Collaborative Workflow:"
        echo "  prepare            Check all prerequisites for a hum session"
        echo "  route-audio        Route active streams: bluetooth|wired|jabra"
        echo "  hum-session        One-command follow-along (Jabra mic + headphones)"
        echo "                     Env: PERSONA=embry TRACK=hawaiian_war_chant"
        echo "                          HEADPHONES=wired|bluetooth (default: wired)"
        echo ""
        echo "Voice Lessons:"
        echo "  lesson             Assemble voice lesson package for Horus"
        echo "  align              SRT-aligned audio segmentation"
        echo "  gate               Per-segment quality gate"
        echo ""
        echo "Utility:"
        echo "  sanity             Check dependencies and environment"
        echo ""
        echo "Examples:"
        echo "  ./run.sh test 'Cate Blanchett' --phrases 'Hello world'"
        echo "  ./run.sh waveform output/test.wav"
        echo "  ./run.sh devices --source-only"
        echo "  ./run.sh record --device Jabra --duration 10 --output /tmp/test.wav"
        echo "  ./run.sh follow --clip scene.wav --srt scene.srt --persona embry"
        echo "  ./run.sh sweep --persona embry --track hawaiian_war_chant"
        echo "  YOUTUBE_URL='https://www.youtube.com/embed/Dordpe3KX_I?start=55' ./run.sh edit vocals.wav scene.srt"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
