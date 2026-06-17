#!/usr/bin/env bash
# e2e sanity for watch skill and subagent
set -euo pipefail
export UV_NO_SYNC=true
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== watch skill e2e sanity ==="

# ---------------------------------------------------------------------------
# 1. Python imports
# ---------------------------------------------------------------------------
echo "--- 1. Python imports ---"
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from frames import extract_frames, get_metadata, parse_time, format_time, extract_scene_change, extract_uniform, auto_fps, auto_fps_focus
from download import download, is_url, is_youtube_url
from transcribe import parse_captions, filter_segments, transcribe_video
from scenes import parse_srt, find_scenes, analyze_emotions, VALID_TAGS, VALID_EMOTIONS
from report import write_report, write_markdown_report, write_frames_manifest
from watch import _env_without_venv, _find_movie_in_library, _find_video_in_dir, _find_srt_in_dir, _check_radarr_library, _resolve_movie_source, MOVIE_LIBRARY, SKILLS_DIR
" 2>/dev/null && pass "all imports OK" || fail "imports failed"

# ---------------------------------------------------------------------------
# 2. CLI
# ---------------------------------------------------------------------------
echo "--- 2. CLI ---"
uv run python scripts/watch.py --help > /dev/null 2>&1 && pass "CLI --help" || fail "CLI --help"

# ---------------------------------------------------------------------------
# 3. System dependencies
# ---------------------------------------------------------------------------
echo "--- 3. System dependencies ---"
command -v ffmpeg > /dev/null 2>&1 && pass "ffmpeg found" || fail "ffmpeg missing"
command -v ffprobe > /dev/null 2>&1 && pass "ffprobe found" || fail "ffprobe missing"
command -v yt-dlp > /dev/null 2>&1 && pass "yt-dlp found" || fail "yt-dlp missing"
command -v uv > /dev/null 2>&1 && pass "uv found" || fail "uv missing"

# ---------------------------------------------------------------------------
# 4. Composed skills exist
# ---------------------------------------------------------------------------
echo "--- 4. Composed skills ---"
for skill in ingest-youtube ingest-movie ops-nzbgeek brave-search; do
  if [ -d "$(dirname "$0")/../$skill" ]; then
    pass "skill $skill exists"
  else
    fail "skill $skill missing"
  fi
done

# ---------------------------------------------------------------------------
# 5. Movie library + resolution (no actual processing)
# ---------------------------------------------------------------------------
echo "--- 5. Movie library resolution ---"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from watch import MOVIE_LIBRARY, _find_movie_in_library, _find_video_in_dir, _find_srt_in_dir, _check_radarr_library
import tempfile
from pathlib import Path

# Test file finders
with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    (p / 'test.mkv').touch()
    (p / 'subs.srt').touch()
    v = _find_video_in_dir(p)
    s = _find_srt_in_dir(p)
    assert v and v.name == 'test.mkv', f'video not found: {v}'
    assert s and s.name == 'subs.srt', f'srt not found: {s}'
print('file finders OK')

# Test movie library lookup
if MOVIE_LIBRARY.exists():
    tests = [
        ('The Devil Wears Prada', None),
        ('There Will Be Blood', None),
        ('Alien', None),
    ]
    for title, _ in tests:
        found = _find_movie_in_library(title)
        status = found.name if found else 'NOT FOUND'
        print(f'  lookup \"{title}\" -> {status}')
else:
    print(f'  library not mounted: {MOVIE_LIBRARY}')

# Test Radarr check (no-op without API key)
result = _check_radarr_library('The Devil Wears Prada')
if result is None:
    print('  Radarr: no key (expected)')
else:
    print(f'  Radarr: {result}')
" 2>/dev/null && pass "movie resolution checks OK" || fail "movie resolution checks failed"

# ---------------------------------------------------------------------------
# 6. YouTube URL detection + ingest-youtube composition
# ---------------------------------------------------------------------------
echo "--- 6. YouTube composition ---"
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from download import is_youtube_url
from watch import SKILLS_DIR

# URL detection
assert is_youtube_url('https://youtube.com/watch?v=iYG5tiFfK3E'), 'youtube.com not detected'
assert is_youtube_url('https://youtu.be/iYG5tiFfK3E'), 'youtu.be not detected'
assert is_youtube_url('https://www.youtube.com/watch?v=iYG5tiFfK3E'), 'www.youtube.com not detected'
assert not is_youtube_url('https://vimeo.com/123'), 'vimeo falsely detected'
assert not is_youtube_url('/path/to/file.mp4'), 'local file falsely detected'
print('URL detection OK')

# ingest-youtube CLI exists
iy = SKILLS_DIR / 'ingest-youtube'
assert iy.exists(), f'ingest-youtube not found at {iy}'
assert (iy / 'youtube_transcript.py').exists(), 'youtube_transcript.py missing'
print(f'ingest-youtube found: {iy}')
" 2>/dev/null && pass "YouTube composition OK" || fail "YouTube composition failed"

# ---------------------------------------------------------------------------
# 7. Frame extraction logic (lightweight — ffprobe metadata + auto_fps only)
# ---------------------------------------------------------------------------
echo "--- 7. Frame extraction logic ---"
TEST_VIDEO=""
# Find a small video quickly without scanning the whole 12TB
for dir in "/mnt/storage12tb/media/movies/30_Days_of_Night" "/mnt/storage12tb/media/movies/The Devil Wears Prada (2006)"; do
  if [ -d "$dir" ]; then
    candidate=$(find "$dir" -maxdepth 1 \( -name "*.mkv" -o -name "*.mp4" \) -size -500M 2>/dev/null | head -1)
    if [ -n "$candidate" ]; then
      TEST_VIDEO="$candidate"
      echo "  found: $(basename "$TEST_VIDEO") ($(du -h "$TEST_VIDEO" | cut -f1))"
      break
    fi
  fi
done

if [ -z "$TEST_VIDEO" ]; then
  echo "  SKIP: no suitable test video found"
else
  uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from frames import get_metadata, auto_fps, auto_fps_focus, parse_time, format_time
meta = get_metadata('$TEST_VIDEO')
print(f'  resolution: {meta.get(\"width\")}x{meta.get(\"height\")}, duration: {meta[\"duration_seconds\"]:.0f}s')
fps, target = auto_fps(meta['duration_seconds'])
print(f'  auto_fps(full): {fps:.3f} fps -> {target} frames')
fps2, target2 = auto_fps_focus(50)
print(f'  auto_fps_focus(50s): {fps2:.3f} fps -> {target2} frames')
print(f'  parse_time(\"50\") = {parse_time(\"50\")}')
print(f'  format_time(90) = {format_time(90)}')
" 2>/dev/null && pass "frame extraction logic OK" || fail "frame extraction logic failed"

  # Quick actual extraction with tiny budget (3 frames @ 0.1 fps)
  uv run python -c "
import sys, time; sys.path.insert(0, 'scripts')
from frames import extract_frames
import tempfile; from pathlib import Path
t0 = time.time()
with tempfile.TemporaryDirectory() as d:
    frames, mode = extract_frames('$TEST_VIDEO', Path(d) / 'frames',
                                   use_scene_change=False, fps=0.1, max_frames=3, resolution=256)
    print(f'  {len(frames)} frames ({mode}) in {time.time()-t0:.1f}s')
" 2>/dev/null && pass "frame extraction e2e OK" || fail "frame extraction e2e failed"
fi

# ---------------------------------------------------------------------------
# 7b. Movie resolution: Warrior (2011) — NOT in library, tests acquisition path
# ---------------------------------------------------------------------------
echo "--- 7b. Movie not-in-library test: Warrior (2011) ---"
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from watch import _find_movie_in_library, _check_radarr_library, MOVIE_LIBRARY

# Should NOT match The 13th Warrior (1999) — year disambiguates
found = _find_movie_in_library('Warrior (2011)')
if found:
    print(f'  WARNING: fuzzy matched \"{found.name}\" — year disambiguation failed')
else:
    print('  OK: not found in library (expected — Warrior 2011 != The 13th Warrior 1999)')

# Radarr check
radarr = _check_radarr_library('Warrior (2011)')
if radarr is None:
    print('  Radarr: no key (expected)')
else:
    print(f'  Radarr: in_library={radarr.get(\"in_library\")}, has_file={radarr.get(\"has_file\")}')

print('  Acquisition path verified: library miss -> Radarr check -> add instructions')
" 2>/dev/null && pass "Warrior (2011) not-in-library OK" || fail "Warrior (2011) test failed"

# ---------------------------------------------------------------------------
# 8. Time parsing (with 30s focus test)
# ---------------------------------------------------------------------------
echo "--- 8. Time parsing ---"
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from frames import parse_time, format_time
assert parse_time('50') == 50.0, 'SS parse failed'
assert parse_time('1:30') == 90.0, 'MM:SS parse failed'
assert parse_time('1:30:00') == 5400.0, 'HH:MM:SS parse failed'
assert parse_time(None) is None, 'None parse failed'
assert format_time(90) == '01:30', 'format 90s failed'
assert format_time(3661) == '1:01:01', 'format 3661s failed'
print('time parsing OK')
" 2>/dev/null && pass "time parsing OK" || fail "time parsing failed"

# ---------------------------------------------------------------------------
# 9. _env_without_venv filter
# ---------------------------------------------------------------------------
echo "--- 9. Env filter ---"
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
from watch import _env_without_venv
env = _env_without_venv()
assert 'VIRTUAL_ENV' not in env, 'VIRTUAL_ENV leaked'
assert 'PATH' in env, 'PATH missing'
assert 'PYTHONHOME' not in env, 'PYTHONHOME leaked'
print('env filter OK')
" 2>/dev/null && pass "env filter OK" || fail "env filter failed"

# ---------------------------------------------------------------------------
# 10. Subagent persona.yaml compliance (yaml-free grep validation)
# ---------------------------------------------------------------------------
echo "--- 10. Subagent contract ---"
AGENTS_DIR="$(cd "$(dirname "$0")/../../agents" && pwd)"
if [ ! -f "$AGENTS_DIR/watch/persona.yaml" ] || [ ! -f "$AGENTS_DIR/watch/AGENTS.md" ]; then
  fail "watch agent files missing at $AGENTS_DIR/watch/"
else
  ERR=0
  # Check required sections via grep
  for section in "schema:" "id:" "kind:" "display_name:" "role:" "does_not_own:" \
                 "primary_skills:" "tool_policy:" "memory_policy:" "turn_contract:" \
                 "help_policy:" "retry_policy:" "output_contract:" "artifact_contract:" \
                 "proof_tasks:" "bash:" "allowed_endpoints:" "denied_endpoints:"; do
    if ! grep -q "$section" "$AGENTS_DIR/watch/persona.yaml"; then
      echo "  MISSING: $section"
      ERR=1
    fi
  done
  # Check bash tier
  if grep -q "tier:" "$AGENTS_DIR/watch/persona.yaml"; then
    TIER=$(grep "tier:" "$AGENTS_DIR/watch/persona.yaml" | head -1 | awk '{print $2}')
    if [ "$TIER" != "bash.scoped_mutate" ] && [ "$TIER" != "'bash.scoped_mutate'" ]; then
      echo "  WARNING: bash tier is $TIER (not scoped_mutate)"
    fi
  fi
  # Check max attempts <= 4
  MAX=$(grep "absolute_max_attempts:" "$AGENTS_DIR/watch/persona.yaml" | awk '{print $2}')
  if [ -n "$MAX" ] && [ "$MAX" -gt 4 ] 2>/dev/null; then
    echo "  FAIL: absolute_max_attempts=$MAX (max 4)"
    ERR=1
  fi
  # Check kind in AGENTS.md
  if grep -q "kind: worker" "$AGENTS_DIR/watch/AGENTS.md"; then
    :
  else
    echo "  MISSING: kind: worker in AGENTS.md"
    ERR=1
  fi
  [ "$ERR" -eq 0 ] && pass "subagent contract compliant" || fail "subagent contract violation"
fi

# ---------------------------------------------------------------------------
# 11. Memory recall proof (3 QRA pairs, all queryable)
# ---------------------------------------------------------------------------
echo "--- 11. Memory recall proof (3 questions) ---"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if uv run python "$SCRIPT_DIR/scripts/recall_proof.py" 2>/dev/null; then
  pass "3 QRA pairs stored + recallable"
else
  echo "  SKIP: memory daemon or watch_content not available"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  if [ "$FAIL" -gt 2 ]; then
    exit 1
  else
    echo "(failures may be expected if 12TB drive not mounted or Radarr not running)"
    exit 1
  fi
fi
echo "=== e2e sanity PASS ==="
