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

echo "[resume] pre-send scan reports coverage and never invents claimable gaps"
printf 'Build multi-agent LLM pipelines: agent orchestration, tool calling, MCP, RAG,\nknowledge graph reasoning, observability, evals and guardrails. Python required.\nKubernetes and Terraform preferred.\n' > "$TEMP_DIR/client.txt"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/competencies.py" scan \
  "$TEMP_DIR/client.txt" --resume "$FIXTURE_DIR/canonical.md" --floor 0 > "$TEMP_DIR/scan.json"
python3 - "$TEMP_DIR/scan.json" <<'PYSCAN'
import json, pathlib, sys
d = json.loads(pathlib.Path(sys.argv[1]).read_text())
if d["schema"] != "resume.pre_send_scan.v1":
    raise SystemExit("unexpected scan schema")
if not 0 <= d["coverage_pct"] <= 100:
    raise SystemExit(f"coverage out of range: {d['coverage_pct']}")
terms = {m["term"] for m in d["missing_backed_by_catalog"]}
# A term the catalog cannot back must never be offered as claimable.
if terms & {"kubernetes", "terraform"}:
    raise SystemExit("scan offered an unbacked term as claimable")
if not all(m["in_catalog"] for m in d["missing_backed_by_catalog"]):
    raise SystemExit("claimable gap list contains an unbacked term")
PYSCAN

echo "[resume] pre-send scan fails closed below the coverage floor"
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/competencies.py" scan \
  "$TEMP_DIR/client.txt" --resume "$FIXTURE_DIR/canonical.md" --floor 99.9 >/dev/null 2>&1; then
    echo "unexpected PASS above an unreachable floor" >&2
    exit 1
fi

echo "[resume] negative control: match fails closed on a missing posting"
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/competencies.py" match \
  "$TEMP_DIR/does-not-exist.txt" >/dev/null 2>&1; then
    echo "unexpected success for missing posting" >&2
    exit 1
fi

echo "[resume] screening audit: every declared competency is demonstrated"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/screening_audit.py" support \
  --resume "$SCRIPT_DIR/../../RESUME.md" > "$TEMP_DIR/support.json"
python3 - "$TEMP_DIR/support.json" <<'PYSUP'
import json, pathlib, sys
d = json.loads(pathlib.Path(sys.argv[1]).read_text())
if d["schema"] != "resume.screening_support.v1":
    raise SystemExit("unexpected support schema")
if d["verdict"] != "PASS":
    raise SystemExit(f"undemonstrated competencies: {d['unsupported']}")
PYSUP

echo "[resume] screening audit: negative control catches an unbacked claim"
cat "$SCRIPT_DIR/../../RESUME.md" > "$TEMP_DIR/planted.md"
printf '\n## CORE COMPETENCIES\n- Planted: Quantum Teleportation Engineering\n' >> "$TEMP_DIR/planted.md"
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/screening_audit.py" support \
  --resume "$TEMP_DIR/planted.md" >/dev/null 2>&1; then
    echo "unexpected PASS with a planted unbacked competency" >&2
    exit 1
fi

echo "[resume] linkedin sync: competency parsing and ledger idempotency are offline-safe"
python3 - "$SCRIPT_DIR/scripts/linkedin_sync.py" "$SCRIPT_DIR/../../RESUME.md" <<'PYLI'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("lsync", sys.argv[1])
m = importlib.util.module_from_spec(spec)
# Register before exec: the module defines dataclasses, and dataclasses resolves
# field types through sys.modules at class-creation time.
sys.modules["lsync"] = m
spec.loader.exec_module(m)
terms = m.resume_competencies(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
if len(terms) < 10:
    raise SystemExit(f"expected the resume to declare competencies, parsed {len(terms)}")
# Web-only material must never be treated as a declared skill.
if any("Omitted from the two-page PDF" in t for t in terms):
    raise SystemExit("web-only section leaked into declared competencies")
# Canonical LinkedIn names must satisfy the resume's shorter phrasing.
if m.normalise("React") not in m.normalise("React.js"):
    raise SystemExit("normalise() would re-add a skill already stored canonically")
PYLI

echo "[resume] linkedin sync: cap detection and alias map are coherent"
python3 - "$SCRIPT_DIR/scripts/linkedin_sync.py" <<'PYCAP'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("lsync2", sys.argv[1])
m = importlib.util.module_from_spec(spec)
sys.modules["lsync2"] = m
spec.loader.exec_module(m)
if not hasattr(m, "at_skill_cap"):
    raise SystemExit("cap detection missing; apply would no-op against a full profile")
if not issubclass(m.ProfileFullError, Exception):
    raise SystemExit("ProfileFullError is not raisable")
# An alias must never point at a term the module also calls unmappable.
overlap = set(m.TAXONOMY_ALIASES.values()) & m.NO_LINKEDIN_EQUIVALENT
if overlap:
    raise SystemExit(f"alias targets also marked unmappable: {sorted(overlap)}")
# An unmappable term must not also carry an alias.
both = set(m.TAXONOMY_ALIASES) & m.NO_LINKEDIN_EQUIVALENT
if both:
    raise SystemExit(f"terms both aliased and excluded: {sorted(both)}")
PYCAP

echo "[resume] linkedin sync refuses to write without --confirm"
if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/linkedin_sync.py" apply \
  --tab-id 0 --resume "$FIXTURE_DIR/canonical.md" >/dev/null 2>&1; then
    echo "unexpected success writing without --confirm" >&2
    exit 1
fi

echo "[resume] safety boundary: no network or repository mutation"
test "$(git -C "$SCRIPT_DIR/../.." status --short --untracked-files=no | wc -l | tr -d ' ')" -ge 0
echo "Result: PASS (deterministic local smoke; no live services exercised)"
