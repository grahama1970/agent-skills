#!/bin/bash
# Behavioral sanity gates for monitor-projects.
# Positive control: discovery finds an amended skill in a synthetic repo.
# Negative control: a quiet repo yields no amendments.
# Packet shape: all five seats declared, equal-context packet fields present.
# Safety boundary: dry-run must not call /store and must not pass --execute.
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

uv sync --quiet
uv run --project "$SCRIPT_DIR" python - <<'PY'
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import monitor_projects as mp  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=30)


failures = []

with tempfile.TemporaryDirectory(prefix="monitor-projects-sanity-") as tmp:
    repo = Path(tmp)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "sanity@example.invalid")
    git(repo, "config", "user.name", "sanity")

    # Negative control: empty repo -> no amended skills.
    (repo / "README.md").write_text("x", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "non-skill change")
    if mp.discover_amended(repo, since_hours=24):
        failures.append("negative control: non-skill commit reported as amended skill")

    # Positive control: a skills/<name>/ change is discovered.
    skill = repo / "skills" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo-skill\ndescription: demo\n---\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "amend demo-skill")
    amended = mp.discover_amended(repo, since_hours=24)
    if [s.name for s in amended] != ["demo-skill"]:
        failures.append(f"positive control: expected [demo-skill], got {[s.name for s in amended]}")

    # Noise control: _shared and dotdirs are never skills.
    noise = repo / "skills" / "_shared"
    noise.mkdir(parents=True)
    (noise / "util.py").write_text("pass\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "amend _shared")
    if any(s.name == "_shared" for s in mp.discover_amended(repo, since_hours=24)):
        failures.append("noise control: _shared surfaced as a skill")

# Packet shape + safety boundary: build a packet with stubbed context sources
# (no live downstream calls, no /store, no --execute).
calls = []
original_run = mp._run
mp._run = lambda args, timeout, cwd=None, env=None: (calls.append(args), (0, "stub-context", ""))[1]
try:
    ctx = mp.RunContext(run_id="20260101T000000Z", run_dir=Path("."), dry_run=True)
    ctx.amended = [mp.AmendedSkill(name="demo-skill", files_changed=2, commits=("abc",))]
    packet = mp.build_packet(ctx)
finally:
    mp._run = original_run

for needed in ["Objective:", "Immutable goal", "Handlers:", "POSITION:", "EXECUTABLE_SLICES:",
               "Proof boundary", *mp.HANDLERS]:
    if needed not in packet:
        failures.append(f"packet missing required field: {needed}")
if len(mp.HANDLERS) != 5:
    failures.append("handler roster is not five seats")
flat_calls = json.dumps([c for c in calls if isinstance(c, list)])
if "--execute" in flat_calls or "/store" in flat_calls:
    failures.append("safety boundary: dry-run packet build touched execute/store")

if failures:
    print(json.dumps({"status": "FAIL", "failures": failures}, indent=2))
    raise SystemExit(1)
print(json.dumps({"status": "PASS", "gates": ["positive", "negative", "noise", "packet-shape", "safety"]}))
PY
