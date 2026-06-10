#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./run.sh list-pages >/dev/null
python3 - <<'PY'
from pathlib import Path
import json
required = [
    "SKILL.md", "run.sh", "page_review.py", "pyproject.toml",
    "templates/WEBGPT_REVIEW_PACKET.md", "templates/HUMAN_REPORT.html",
    "templates/review.json", "scripts/build_page_report.py",
    "examples/coverage/review.json", "examples/chat/review.json",
]
for p in required:
    assert Path(p).exists(), p
json.loads(Path("templates/review.json").read_text())
json.loads(Path("examples/coverage/review.json").read_text())
mf = json.loads(Path("templates/coverage-test-interactions-manifest.json").read_text())
assert "description" in str(mf), "manifest should use description not expect"
print("review-page sanity passed")
PY
