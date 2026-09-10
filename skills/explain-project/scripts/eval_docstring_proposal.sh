#!/usr/bin/env bash
# Deterministic eval: propose-docstring-links finds the breakpoint-owning
# function, proposes the durable diagram pointer, skips already-linked
# docstrings, and never mutates source.
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
T="$(mktemp -d)"
mkdir -p "$T/src"

cat > "$T/src/app.py" <<'EOF'
def publish(results):
    """Write results atomically.

    Stages first, swaps last.
    """
    tmp = results + '.tmp'
    return tmp


def already_linked(x):
    """Do a thing.

    Diagram: docs/diagram.svg
    """
    return x
EOF

python3 - "$DIR" "$T" <<'PY'
import json
import sys
from pathlib import Path

skill, tmp = sys.argv[1], Path(sys.argv[2])
src = json.loads(
    (
        Path(skill)
        / "fixtures/cockpit/project/docs/explain/explainers.jsonl"
    ).read_text().splitlines()[0]
)
src["feature_id"] = "demo.publish"
src["title"] = "Demo publish"
src["question"] = "Why publish?"
src["diagram"]["source_kind"] = "excalidraw"
src["diagram"]["source_path"] = "docs/boards/demo.excalidraw"
src["diagram"]["node_ids"] = ["n1"]
src["diagram"]["sha256"] = None
src["debugger_stops"] = [{
    "file": "src/app.py",
    "line": 6,
    "proves": "paused swap",
    "locals": ["tmp"],
}]
src["source_ranges"] = [{
    "file": "src/app.py",
    "start_line": 1,
    "end_line": 9,
    "symbol": "publish",
}]
src["steps"] = [{
    "step_id": "stop",
    "title": "Atomic swap",
    "bullets": ["stage first", "swap last"],
    "source_range_index": 0,
    "debugger_stop_index": 0,
    "diagram_node_ids": ["n1"],
    "source_explanation": "stages then swaps",
    "confidence": "medium",
    "proof_boundary": "local only",
}]
(tmp / "explainers.jsonl").write_text(
    json.dumps(src) + "\n"
)
PY

cd "$DIR"
./run.sh propose-docstring-links \
  --repo "$T" \
  --explainers "$T/explainers.jsonl" \
  --out "$T/proposal.json"

python3 - "$T/proposal.json" "$T" <<'PY'
import json
import sys
from pathlib import Path

d = json.load(open(sys.argv[1]))
assert d["schema"] == (
    "explain_project.docstring_link_proposal.v1"
), d
assert d["mutation"] == "proposal-only", d
assert len(d["proposals"]) == 1, d
p = d["proposals"][0]
assert p["function"] == "publish", p
assert p["breakpoint_line"] == 6, p
assert p["proposed_docstring_line"] == (
    "Excalidraw source: docs/boards/demo.excalidraw"
), p
# already-linked function must NOT be proposed
assert all(
    q["function"] != "already_linked"
    for q in d["proposals"]
)
# no source mutation: app.py unchanged shape
body = Path(sys.argv[2], "src/app.py").read_text()
assert "Excalidraw source:" not in body
print("EXPLAIN_PROJECT_DOCSTRING_PROPOSAL_OK")
PY
