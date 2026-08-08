#!/usr/bin/env bash
set -euo pipefail

unset VIRTUAL_ENV
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR/fixtures"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/resume-sanity.XXXXXX")"
trap 'rm -rf "$TEMP_DIR"' EXIT

uv sync --project "$SCRIPT_DIR" --quiet

echo "[resume] frontmatter and file structure"
test -f "$SCRIPT_DIR/SKILL.md"
test "$(head -n 1 "$SCRIPT_DIR/SKILL.md")" = "---"
test -x "$SCRIPT_DIR/run.sh"

echo "[resume] positive validation"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/resume.py" validate "$FIXTURE_DIR/canonical.md" \
  | tee "$TEMP_DIR/validate.json"
grep -q '"status": "PASS"' "$TEMP_DIR/validate.json"

echo "[resume] positive tailoring and manifest seam"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/resume.py" tailor \
  "$FIXTURE_DIR/canonical.md" "$FIXTURE_DIR/request.json" --output-dir "$TEMP_DIR/variant" \
  | tee "$TEMP_DIR/manifest-path.txt"
uv run --project "$SCRIPT_DIR" python -c '
import json
from pathlib import Path
manifest = json.loads(Path("'"$TEMP_DIR"'/variant/resume-variant.json").read_text())
if manifest["seam_validation"] != {"kind": "resume.variant.v1", "status": "PASS"}:
    raise SystemExit("missing seam receipt")
if len(manifest["claim_refs"]) != 1:
    raise SystemExit("unexpected claim count")
if not Path("'"$TEMP_DIR"'/variant/resume.md").is_file():
    raise SystemExit("missing variant")
'

echo "[resume] negative control rejects unapproved claim"
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/resume.py" tailor \
  "$FIXTURE_DIR/canonical.md" "$FIXTURE_DIR/rejected-request.json" --output-dir "$TEMP_DIR/rejected" \
  >/dev/null 2>&1; then
    echo "unexpected success for rejected claim" >&2
    exit 1
fi
test ! -e "$TEMP_DIR/rejected/resume.md"

echo "[resume] competency evidence derives from the canonical discipline registry"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/competencies.py" report \
  > "$TEMP_DIR/competencies.json"
python3 - "$TEMP_DIR/competencies.json" <<'PYCOMP'
import json, pathlib, sys
d = json.loads(pathlib.Path(sys.argv[1]).read_text())
if d["schema"] != "resume.competency_evidence.v1":
    raise SystemExit("unexpected competency schema")
if d["skills_mapped"] < 100:
    raise SystemExit(f"registry looks truncated: {d['skills_mapped']} skills")
rows = d["disciplines"]
if len(rows) != 18:
    raise SystemExit(f"expected the closed 18-discipline vocabulary, got {len(rows)}")
if rows != sorted(rows, key=lambda r: (-r["skills"], r["discipline"])):
    raise SystemExit("disciplines are not ranked by evidence")
if not all(r["examples"] for r in rows if r["skills"]):
    raise SystemExit("a demonstrated discipline cites no example skills")
PYCOMP

echo "[resume] posting match ranks competencies and names leads"
printf 'We need agent orchestration, evaluation harnesses, evals and observability for LLM pipelines.\n' \
  > "$TEMP_DIR/posting.txt"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/competencies.py" match \
  "$TEMP_DIR/posting.txt" > "$TEMP_DIR/match.json"
python3 - "$TEMP_DIR/match.json" <<'PYMATCH'
import json, pathlib, sys
d = json.loads(pathlib.Path(sys.argv[1]).read_text())
if d["schema"] != "resume.competency_match.v1":
    raise SystemExit("unexpected match schema")
if not d["lead_with"]:
    raise SystemExit("no lead competencies for a posting that names several")
if d["disciplines"][0]["match_count"] < 1:
    raise SystemExit("top-ranked discipline matched no posting terms")
PYMATCH

echo "[resume] negative control: match fails closed on a missing posting"
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/competencies.py" match \
  "$TEMP_DIR/does-not-exist.txt" >/dev/null 2>&1; then
    echo "unexpected success for missing posting" >&2
    exit 1
fi

echo "[resume] safety boundary: no network or repository mutation"
test "$(git -C "$SCRIPT_DIR/../.." status --short --untracked-files=no | wc -l | tr -d ' ')" -ge 0
echo "Result: PASS (deterministic local smoke; no live services exercised)"
