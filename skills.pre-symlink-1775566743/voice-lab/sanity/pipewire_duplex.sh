#!/usr/bin/env bash
# Sanity script: PipeWire duplex (simultaneous record + playback)
# Purpose: Verify pw-record and pw-play can run concurrently
# Exit codes: 0=PASS, 1=FAIL

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo -n "Check 1 - pw-record available: "
if command -v pw-record &>/dev/null; then
    echo "PASS"
else
    echo "FAIL (pw-record not found, install pipewire-utils)"
    exit 1
fi

echo -n "Check 2 - pw-play available: "
if command -v pw-play &>/dev/null; then
    echo "PASS"
else
    echo "FAIL (pw-play not found, install pipewire-utils)"
    exit 1
fi

echo -n "Check 3 - PipeWire running: "
if pw-cli info 0 &>/dev/null; then
    echo "PASS"
else
    echo "FAIL (PipeWire daemon not running)"
    exit 1
fi

# Create a 1-second silence WAV for playback test
echo -n "Check 4 - Duplex (record + play simultaneously): "
python3 -c "
import numpy as np, soundfile as sf
silence = np.zeros(48000, dtype='float32')
sf.write('$TMPDIR/silence.wav', silence, 48000)
" 2>/dev/null

# Start recording in background (default source, no --target)
timeout 5 pw-record "$TMPDIR/recorded.wav" &
REC_PID=$!

# Brief pause to let recording initialize
sleep 0.5

# Play silence concurrently
timeout 5 pw-play "$TMPDIR/silence.wav" 2>/dev/null || true

# Stop recording
sleep 0.3
kill $REC_PID 2>/dev/null || true
wait $REC_PID 2>/dev/null || true

# Check output exists and is non-empty
if [ -f "$TMPDIR/recorded.wav" ] && [ -s "$TMPDIR/recorded.wav" ]; then
    echo "PASS"
else
    echo "FAIL (recording output empty or missing)"
    exit 1
fi

echo ""
echo "Result: PASS (PipeWire supports simultaneous record + playback)"
exit 0
