#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [mine-transcripts] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md run.sh mine_transcripts.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
[[ $FAIL -eq 0 ]] && echo "PASS"
[[ $FAIL -ne 0 ]] && exit 1

# Check 2: Python syntax check
echo -n "Check 2 - Python syntax: "
if python3 -m py_compile "$SCRIPT_DIR/mine_transcripts.py" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: syntax error in mine_transcripts.py"
    exit 1
fi

# Check 3: Core stdlib imports
echo -n "Check 3 - Core imports: "
python3 -c "
import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 4: Smoke test - text utility functions
echo -n "Check 4 - Text utilities: "
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from mine_transcripts import (
    text_hash, is_real_human_message,
    detect_emotional_state, extract_bridges, discover_sources
)

# Test text_hash
h = text_hash('hello world')
assert len(h) == 16, f'Expected 16 char hash, got {len(h)}'

# Test message filtering
assert is_real_human_message('This is a real conversation about fixing the bug') == True
assert is_real_human_message('/command') == False
assert is_real_human_message('short') == False
assert is_real_human_message('You are an expert in Python') == False

# Test emotional detection
emo = detect_emotional_state('This is perfect, great job!')
assert emo['satisfied'] == True, f'Expected satisfied, got {emo}'

emo2 = detect_emotional_state('This is broken and not working')
assert emo2['frustrated'] == True, f'Expected frustrated, got {emo2}'

# Test bridge extraction
bridges = extract_bridges('This is perfect, great job!')
assert 'Resilience' in bridges or 'Loyalty' in bridges, f'Expected Resilience/Loyalty in {bridges}'

# Test source discovery (just verify it runs)
sources = discover_sources()
assert isinstance(sources, dict)

print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 5: CLI help
echo -n "Check 5 - CLI help: "
if python3 "$SCRIPT_DIR/mine_transcripts.py" --help >/dev/null 2>&1; then
    echo "PASS"
else
    echo "WARN: CLI help returned non-zero"
fi

# Check 6: Sources command (non-destructive)
echo -n "Check 6 - Sources discovery: "
if python3 "$SCRIPT_DIR/mine_transcripts.py" sources >/dev/null 2>&1; then
    echo "PASS"
else
    echo "WARN: sources command failed"
fi

# Check 7: Optional deps
echo -n "Check 7 - Optional deps: "
WARN=0
if ! python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/../taxonomy')
from taxonomy import extract_keywords
" 2>/dev/null; then
    echo ""
    echo "  WARN: /taxonomy skill not importable (will use fallback labeling)"
    WARN=1
fi
[[ $WARN -eq 0 ]] && echo "PASS (taxonomy available)"

echo ""
echo "SKIP: Full mining (modifies data/ directory)"
echo "SKIP: Memory storage (requires ArangoDB)"
echo ""
echo "Result: PASS"
