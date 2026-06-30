#!/usr/bin/env bash
set -euo pipefail

# Checkpoint Skill Sanity — E2E tests against live ArangoDB
# Tests: save → last → recall → list → resume
# Fails loud on ANY broken path.

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${1:-$HOME/workspace/experiments/sparta}"

echo "=== Checkpoint Skill E2E Sanity ==="
echo "  skill: $SKILL_DIR"
echo "  project: $PROJECT_DIR"
echo ""

SKILL_DIR="$SKILL_DIR" PROJECT_DIR="$PROJECT_DIR" python3 << 'PYEOF'
import httpx, json, sys, subprocess, os

SKILL_DIR = os.environ["SKILL_DIR"]
PROJECT_DIR = os.environ["PROJECT_DIR"]
RUN = os.path.join(SKILL_DIR, "run.sh")

transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
client = httpx.Client(transport=transport, timeout=30)
failures = []
total = 0

def check(name, condition, detail=""):
    global total
    total += 1
    status = "PASS" if condition else "FAIL"
    suffix = f" — {detail}" if detail and not condition else ""
    print(f"  {status}: {name}{suffix}")
    if not condition:
        failures.append(name)

def run_cmd(*args, expect_json=True):
    """Run checkpoint CLI and return parsed output."""
    result = subprocess.run(
        [RUN, *args],
        capture_output=True, text=True, timeout=120,
        cwd=PROJECT_DIR,
    )
    if not expect_json:
        return result.stdout, result.returncode
    out = result.stdout.strip()
    # Try each line from the end to find valid JSON
    lines = out.split('\n')
    for i in range(len(lines) - 1, -1, -1):
        candidate = '\n'.join(lines[i:])
        candidate = candidate.strip()
        if candidate and candidate[0] in '{[':
            try:
                return json.loads(candidate), result.returncode
            except json.JSONDecodeError:
                continue
    return {}, result.returncode

# ========================================================
# Test 1: CLI help commands
# ========================================================
print("Test 1: CLI help commands")
for cmd in ["--help", "save --help", "recall --help", "list --help", "last --help"]:
    out, rc = run_cmd(*cmd.split(), expect_json=False)
    check(f"{cmd} exits 0", rc == 0)

# ========================================================
# Test 2: Save a checkpoint
# ========================================================
print("\nTest 2: Save checkpoint")
TOPIC = f"sanity-test-{os.getpid()}"
save_json, rc = run_cmd(
    "save", "-t", TOPIC, "-g", "clean",
    "-r", "Sanity test — delete after verification",
    "--json",
)
check("save exit code 0", rc == 0)
check("save returned checkpoint_version", save_json.get("checkpoint_version") == 5)
check("save topic matches", save_json.get("topic") == TOPIC, save_json.get("topic"))
check("save has tag", bool(save_json.get("tag")))
check("save has git context", bool(save_json.get("git", {}).get("branch")))

# ========================================================
# Test 3: Write verification — doc in checkpoints collection
# ========================================================
print("\nTest 3: Write verification — doc in checkpoints collection")
# Use /list (not BM25 /recall) for immediate write verification
r = client.post("http://localhost/list", json={
    "collection": "checkpoints", "limit": 200,
    "filters": {"scope": "sparta"},
})
docs = r.json().get("documents", [])
matching = [d for d in docs if d.get("topic") == TOPIC]
check("doc found in checkpoints collection", len(matching) > 0, f"{len(matching)} matches in {len(docs)} docs")
if matching:
    m = matching[0]
    check("has checkpoint_version=5", m.get("checkpoint_version") == 5)
    check("has grade=clean", m.get("grade") == "clean", m.get("grade"))
    check("has resume text", bool(m.get("resume")), m.get("resume", "")[:50])
    check("has scope=sparta", m.get("scope") == "sparta", m.get("scope"))

# ========================================================
# Test 4: last returns the newest checkpoint
# ========================================================
print("\nTest 4: 'last' returns newest checkpoint")
last_json, rc = run_cmd("last", "--json")
check("last exit code 0", rc == 0)
check("last topic is sanity test", last_json.get("topic") == TOPIC, last_json.get("topic", ""))
check("last grade is clean", last_json.get("grade") == "clean", last_json.get("grade"))
check("last has resume", bool(last_json.get("resume")))
check("last has timestamp", bool(last_json.get("timestamp")))

# ========================================================
# Test 5: recall finds it with populated fields
# ========================================================
print("\nTest 5: 'recall' returns populated fields")
recall_json, rc = run_cmd("recall", "-t", TOPIC, "--limit", "1", "--json")
if isinstance(recall_json, list):
    recall_json = recall_json[0] if recall_json else {}
check("recall exit code 0", rc == 0)
check("recall topic matches", recall_json.get("topic") == TOPIC, recall_json.get("topic", ""))
check("recall grade not empty", bool(recall_json.get("grade")), recall_json.get("grade", ""))
check("recall resume not empty", bool(recall_json.get("resume")))

# ========================================================
# Test 6: list includes the checkpoint, newest-first order
# ========================================================
print("\nTest 6: 'list' returns checkpoints newest-first")
list_json, rc = run_cmd("list", "--limit", "5", "--json")
check("list exit code 0", rc == 0)
check("list is array", isinstance(list_json, list))
if isinstance(list_json, list) and len(list_json) > 0:
    check("list[0] is sanity test", list_json[0].get("topic") == TOPIC, list_json[0].get("topic", ""))
    if len(list_json) >= 2:
        ts0 = list_json[0].get("timestamp", "")
        ts1 = list_json[1].get("timestamp", "")
        check("list[0] newer than list[1]", ts0 >= ts1, f"{ts0} vs {ts1}")

# ========================================================
# Test 7: Legacy recall (lessons_v2 items) returns populated fields
# ========================================================
print("\nTest 7: Legacy recall (lessons_v2 items) returns populated fields")
recall_legacy, rc = run_cmd("recall", "-t", "SPARTA Explorer", "--limit", "2", "--json")
if isinstance(recall_legacy, list):
    for i, cp in enumerate(recall_legacy):
        check(f"legacy[{i}] topic not empty", bool(cp.get("topic")), cp.get("topic", "")[:40])

# ========================================================
# Test 8: resume command works
# ========================================================
print("\nTest 8: 'resume' command")
resume_out, rc = run_cmd("resume", "-t", TOPIC, expect_json=False)
check("resume exit code 0", rc == 0)
check("resume shows topic", TOPIC in resume_out, resume_out[:200] if TOPIC not in resume_out else "")

# ========================================================
# Summary
# ========================================================
print(f"\n{'='*60}")
print(f"Results: {total - len(failures)}/{total} passed")
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
PYEOF
