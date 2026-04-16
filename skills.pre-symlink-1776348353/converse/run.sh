#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
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

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Check core dependencies
check_deps() {
    local missing=()

    if ! python3 -c "import numpy" 2>/dev/null; then
        missing+=("numpy")
    fi
    if ! python3 -c "import loguru" 2>/dev/null; then
        missing+=("loguru")
    fi
    if ! command -v pw-record &>/dev/null && ! command -v parecord &>/dev/null; then
        missing+=("pipewire-utils (pw-record/pw-play)")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo "ERROR: Missing dependencies: ${missing[*]}"
        echo ""
        echo "Install with:"
        echo "  pip install numpy loguru"
        echo "  sudo apt install pipewire-utils"
        exit 1
    fi
}

# Check optional dependencies and report status
check_optional() {
    echo "=== Core Dependencies ==="
    python3 -c "import numpy; print(f'  numpy: {numpy.__version__}')" 2>/dev/null || echo "  numpy: MISSING"
    python3 -c "import loguru; print('  loguru: OK')" 2>/dev/null || echo "  loguru: MISSING"
    command -v pw-record &>/dev/null && echo "  pw-record: OK" || echo "  pw-record: MISSING"
    command -v pw-play &>/dev/null && echo "  pw-play: OK" || echo "  pw-play: MISSING"

    echo ""
    echo "=== Optional Dependencies ==="
    python3 -c "import webrtcvad; print('  webrtcvad: OK')" 2>/dev/null || echo "  webrtcvad: MISSING (will use energy-based VAD fallback)"
    python3 -c "import faster_whisper; print('  faster-whisper: OK')" 2>/dev/null || echo "  faster-whisper: MISSING (will use CLI fallback)"
    python3 -c "import websockets; print('  websockets: OK')" 2>/dev/null || echo "  websockets: MISSING (needed for Horus surface)"
    python3 -c "import httpx; print('  httpx: OK')" 2>/dev/null || echo "  httpx: MISSING (needed for Ollama fallback)"
    command -v whisper &>/dev/null && echo "  whisper CLI: OK" || echo "  whisper CLI: MISSING"
    command -v espeak-ng &>/dev/null && echo "  espeak-ng: OK" || echo "  espeak-ng: MISSING (last-resort TTS)"
    command -v ffmpeg &>/dev/null && echo "  ffmpeg: OK" || echo "  ffmpeg: MISSING"

    echo ""
    echo "=== Skill Dependencies ==="
    local skills_root="$SKILL_DIR/.."
    [ -f "$skills_root/memory/brandon_simulacrum.py" ] && echo "  EmbrySPARTAIntern: OK" || echo "  EmbrySPARTAIntern: MISSING"
    [ -f "$skills_root/memory/persona_journal.py" ] && echo "  persona_journal: OK" || echo "  persona_journal: MISSING"
    [ -f "$skills_root/common/memory_client.py" ] && echo "  memory_client: OK" || echo "  memory_client: MISSING"
    [ -f "$skills_root/surf-qml/narration.py" ] && echo "  narration (taxonomy): OK" || echo "  narration (taxonomy): MISSING"
    [ -f "$skills_root/train-convo-steering/run.sh" ] && echo "  convo-steering: OK" || echo "  convo-steering: MISSING"
    [ -f "$skills_root/consume-music/search.py" ] && echo "  consume-music: OK" || echo "  consume-music: MISSING"

    echo ""
    echo "=== Voice Assets ==="
    local voices="/mnt/storage12tb/media/personas/embry/personaplex/voices"
    if [ -d "$voices" ]; then
        echo "  Voice dir: $voices"
        ls -1 "$voices"/*.pt 2>/dev/null | while read f; do
            echo "    $(basename "$f")"
        done || echo "    (no .pt files found)"
    else
        echo "  Voice dir: NOT FOUND ($voices)"
    fi

    local hum_cache="/mnt/storage12tb/media/personas/embry/hum-cache"
    if [ -d "$hum_cache" ]; then
        local count
        count=$(find "$hum_cache" -name "*.wav" -o -name "*.mp3" 2>/dev/null | wc -l)
        echo "  Hum cache: $count fragments"
    else
        echo "  Hum cache: NOT FOUND ($hum_cache)"
    fi

    echo ""
    echo "=== Music Registry ==="
    local registry="$HOME/.pi/consume-music/registry.json"
    if [ -f "$registry" ]; then
        local tracks
        tracks=$(python3 -c "import json; r=json.load(open('$registry')); print(len(r.get('contents',{})))" 2>/dev/null || echo "0")
        echo "  Registry: $tracks tracks"
    else
        echo "  Registry: NOT FOUND"
    fi
}

CMD="${1:-help}"
shift || true

case "$CMD" in
    start)
        check_deps
        python3 converse.py "$@"
        ;;

    sanity)
        check_optional
        echo ""
        echo "=== Module Import Test ==="
        python3 -c "
from emotion import EmotionStateMachine
from listener import Listener, VADProcessor
from thinker import Thinker
from speaker import Speaker
from mixer import AudioMixer
from idler import Idler, MusicSelector
from surfaces import SurfaceAdapter
from converse import ConversationOrchestrator, SessionConfig
print('  All modules imported successfully')
" && echo "  SANITY: PASS" || echo "  SANITY: FAIL (import error)"
        ;;

    test-emotion)
        python3 -c "
from emotion import EmotionStateMachine
e = EmotionStateMachine()
print('Initial:', e.to_dict())
print('Trigger check (james):', e.check_triggers('tell me about james'))
e.update_from_context('this is so frustrating')
print('After frustration:', e.to_dict())
e.decay_tick()
print('After decay:', e.to_dict())
"
        ;;

    test-listener)
        check_deps
        python3 -c "
import asyncio
from listener import Listener
l = Listener(on_speech=lambda r: print(f'Speech: {r.text}'), on_barge_in=lambda: print('Barge-in!'))
asyncio.run(l.test(duration=${1:-3}))
"
        ;;

    test-speaker)
        check_deps
        python3 -c "
import asyncio
from speaker import Speaker
s = Speaker(mode='${1:-recorded}')
asyncio.run(s.test('${2:-Hello, I am Embry.}'))
"
        ;;

    test-idler)
        python3 -c "
import asyncio
from idler import Idler
i = Idler()
asyncio.run(i.test_hum('${1:-calm}'))
"
        ;;

    test-mixer)
        python3 -c "
import numpy as np
from mixer import AudioMixer
m = AudioMixer()
m.add_channel('speech')
m.add_channel('humming', volume=0.5)
# Generate test tone
t = np.linspace(0, 0.5, 24000)
tone = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
m.write('speech', tone)
mixed = m.mix(24000)
print(f'Mixed {len(mixed)} samples, peak={np.max(np.abs(mixed))}')
print('Mixer status:', m.status())
"
        ;;

    help|*)
        cat <<'EOF'
converse - Real-time two-way voice conversation

USAGE:
    ./run.sh <command> [options]

COMMANDS:
    start           Start a conversation session
    sanity          Check all dependencies and assets
    test-emotion    Test emotion state machine
    test-listener   Test VAD + Whisper (records from mic)
    test-speaker    Test TTS output
    test-idler      Test idle behavior selection
    test-mixer      Test audio mixer
    help            Show this help

START OPTIONS:
    --persona NAME      Persona to use (default: embry)
    --surface TYPE      Audio surface: discord, kde, horus (default: kde)
    --mode MODE         TTS mode: live or recorded (default: live)
    --user-id ID        User identifier (default: default)
    --duration SECS     Max duration in seconds
    --scenario PATH     Path to surf-qml scenario YAML

EXAMPLES:
    # Start conversation on KDE desktop
    ./run.sh start --surface kde --persona embry

    # Start with scenario attached
    ./run.sh start --surface kde --persona embry \
        --scenario ../surf-qml/scenarios/design_review.yaml

    # Recorded mode (Qwen3-TTS, not live PersonaPlex)
    ./run.sh start --surface kde --mode recorded

    # Discord voice channel
    ./run.sh start --surface discord --persona embry

    # Time-limited session (30 seconds)
    ./run.sh start --surface kde --duration 30
EOF
        ;;
esac
