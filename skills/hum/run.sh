#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# /hum — Persona humming pipeline
# Orchestrates: segment → Basic Pitch → guide hum → Orpheus → Seed-VC

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load project .env if present. Do not source interactive shell rc files here:
# they may contain zsh-only code or exit/return paths that break this bash wrapper.
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
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
    decompose)
        uv run python -m src.cli decompose "$@"
        ;;
    decompose-dataset)
        uv run python -m src.cli decompose-dataset "$@"
        ;;
    decompose-youtube)
        uv run python -m src.cli decompose-youtube "$@"
        ;;
    build-female-humming-dataset)
        uv run python -m src.cli build-female-humming-dataset "$@"
        ;;
    ingest-humtrans)
        uv run python -m src.cli ingest-humtrans "$@"
        ;;
    build-humtrans-pairs)
        uv run python -m src.cli build-humtrans-pairs "$@"
        ;;
    train-control-dataset)
        uv run python -m src.cli train-control-dataset "$@"
        ;;
    export-techsinger-smoke)
        uv run python -m src.cli export-techsinger-smoke "$@"
        ;;
    validate-techsinger-smoke)
        uv run python -m src.cli validate-techsinger-smoke "$@"
        ;;
    score-to-midi)
        uv run python -m src.cli score-to-midi "$@"
        ;;
    render-female-hum)
        uv run python -m src.cli render-female-hum "$@"
        ;;
    train-hum-timbre)
        uv run python -m src.cli train-hum-timbre "$@"
        ;;
    render-trained-hum)
        uv run python -m src.cli render-trained-hum "$@"
        ;;
    train-neural-hum-renderer)
        uv run python -m src.cli train-neural-hum-renderer "$@"
        ;;
    render-neural-hum)
        uv run python -m src.cli render-neural-hum "$@"
        ;;
    evaluate-hum-render)
        uv run python -m src.cli evaluate-hum-render "$@"
        ;;
    render-articulated-psola)
        uv run python -m src.cli render-articulated-psola "$@"
        ;;
    generate-elevenlabs-articulations)
        uv run python -m src.cli generate-elevenlabs-articulations "$@"
        ;;
    pitch-correct-guide)
        uv run python -m src.cli pitch-correct-guide "$@"
        ;;
    add)
        uv run python -m src.cli add "$@"
        ;;
    train)
        uv run python -m src.cli train "$@"
        ;;
    list)
        uv run python -m src.cli list "$@"
        ;;
    play)
        uv run python -m src.cli play "$@"
        ;;
    info)
        uv run python -m src.cli info "$@"
        ;;
    prepare-ace)
        uv run python -m src.cli prepare-ace "$@"
        ;;
    sanity)
        bash "${SCRIPT_DIR}/sanity.sh"
        ;;
    help|--help|-h)
        echo "hum: Persona humming pipeline"
        echo ""
        echo "Commands:"
        echo "  decompose AUDIO      Extract melody/cadence JSON + neutral_hum.wav"
        echo "  decompose-dataset P  Batch extract pitch/cadence/sound artifacts"
        echo "  decompose-youtube U  Download YouTube audio then batch decompose"
        echo "  build-female-humming-dataset  Collect HF/YouTube female humming + decompose"
        echo "  ingest-humtrans               Download HumTrans MIDI/splits and optional full WAV archive"
        echo "  build-humtrans-pairs          Build HumTrans WAV/MIDI JSONL pair manifest"
        echo "  train-control-dataset         Extract bounded HumTrans MIDI/audio controls"
        echo "  export-techsinger-smoke       Export control manifest to TechSinger-compatible metadata"
        echo "  validate-techsinger-smoke     Validate TechSinger-compatible smoke metadata"
        echo "  score-to-midi                 Convert score PDF/MusicXML to MIDI"
        echo "  render-female-hum             Render controllable female_hum.wav from decomposed carriers"
        echo "  train-hum-timbre              Train lightweight continuous hum timbre model"
        echo "  render-trained-hum            Render MIDI/notes through trained hum timbre model"
        echo "  train-neural-hum-renderer     Train bounded MIDI-control hum renderer"
        echo "  render-neural-hum             Render MIDI through bounded trained hum renderer"
        echo "  evaluate-hum-render           Evaluate F0/timing/glissando alignment"
        echo "  render-articulated-psola      Render deterministic PSOLA artifact bundle from MIDI + articulation samples"
        echo "  generate-elevenlabs-articulations  Generate required articulation WAV inventory with ElevenLabs Sound Effects"
        echo "  pitch-correct-guide       Lightly pitch-center an STS guide before bakeoff"
        echo "  add [url]            Diagnostic candidate; cache only after gates"
        echo "  train                Deprecated (use /tts-voice)"
        echo "  list                 List cached hums"
        echo "  play <track>         Play a cached hum through PipeWire"
        echo "  info <track>         Show track metadata"
        echo "  prepare-ace          ACE Studio MIDI + lyric bundle"
        echo "  sanity               Check all dependencies"
        echo ""
        echo "Examples:"
        echo "  ./run.sh decompose /path/to/source.wav --out-dir /tmp/hum_decompose --max-duration 60 --json"
        echo "  ./run.sh decompose-dataset /path/to/humming_wavs --out-dir /tmp/hum_dataset --max-duration 60 --json"
        echo "  ./run.sh decompose-youtube 'https://youtu.be/...' --out-dir /tmp/hum_youtube --limit 1 --max-duration 60 --json"
        echo "  ./run.sh build-female-humming-dataset --youtube-url 'https://youtu.be/...' --out-dir /tmp/female_humming --youtube-limit 1 --json"
        echo "  ./run.sh ingest-humtrans --out-dir /mnt/storage12tb/datasets/humtrans --download-wav --json"
        echo "  ./run.sh build-humtrans-pairs --humtrans-dir /mnt/storage12tb/datasets/humtrans --json"
        echo "  ./run.sh export-techsinger-smoke --controls-manifest /mnt/storage12tb/datasets/hum_mvp/controls_smoke/manifest.json --json"
        echo "  ./run.sh score-to-midi /path/to/score.pdf --out-dir /tmp/score_midi --json"
        echo "  ./run.sh render-female-hum --dataset-index /tmp/female_humming/decomposition/index.json --out-dir /tmp/female_hum_render --json"
        echo "  ./run.sh train-hum-timbre --dataset-index /tmp/female_humming/decomposition/index.json --out-dir /tmp/hum_timbre --json"
        echo "  ./run.sh render-trained-hum --model-json /tmp/hum_timbre/hum_timbre_model.json --midi /path/to/melody.mid --json"
        echo "  ./run.sh generate-elevenlabs-articulations --output-dir /tmp/hwc_articulations --duration-seconds 1.2 --prompt-influence 0.72 --json"
        echo "  ./run.sh pitch-correct-guide /path/to/guide.wav --out-dir /tmp/hum_pitch_corrected --json"
        echo "  ./run.sh render-articulated-psola --midi /path/to/melody.mid --samples /path/to/articulation_wavs --output-dir /tmp/hwc_psola --json"
        echo ""
        echo "Options (add):"
        echo "  --song PATH          Licensed local audio (preferred over URL)"
        echo "  --start TIME         Segment start (default: 00:00:00)"
        echo "  --duration TIME      Segment length (default: 00:00:20)"
        echo "  --persona NAME       Target persona (default: embry)"
        echo "  --midi PATH          Manual MIDI melody override"
        echo "  --source-hum PATH    Manual guide hum override"
        echo "  --semi-tone-shift N  Seed-VC semitone shift (default: 0)"
        echo "  --diffusion-steps N  Seed-VC steps (default: 45)"
        echo "  --json               Output as JSON"
        echo ""
        echo "Add examples:"
        echo "  ./run.sh add --song /path/to/song.wav --persona embry --start 00:00:08"
        echo "  ./run.sh list --persona embry"
        echo "  ./run.sh play hawaiian_war_chant"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
