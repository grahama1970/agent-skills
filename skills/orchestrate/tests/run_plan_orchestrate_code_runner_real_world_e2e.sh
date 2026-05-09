#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PLAN="$ROOT/skills/plan/run.sh"
REVIEW_PLAN="$ROOT/skills/review-plan/run.sh"
ORCH="$ROOT/skills/orchestrate/run.sh"
TMP="${TMPDIR:-/tmp}/plan-orchestrate-code-runner-real-world-e2e-$$"
REPO="$TMP/repo"
ORCH_HOME="$TMP/orchestrate-home"

cleanup() {
  status=$?
  if [[ "${PRESERVE_E2E_TMP:-0}" == "1" || "$status" != "0" ]]; then
    echo "Preserving E2E temp dir: $TMP" >&2
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

curl -fsS --max-time 5 http://localhost:4001/health >/dev/null

mkdir -p "$REPO/src/billing" "$REPO/tests" "$ORCH_HOME"
cd "$REPO"
git init -q
git config user.email "plan-orchestrate-code-runner-e2e@example.invalid"
git config user.name "Plan Orchestrate Code Runner E2E"
touch src/__init__.py src/billing/__init__.py tests/__init__.py

cat > pyproject.toml <<'TOML'
[tool.pytest.ini_options]
pythonpath = ["src"]
TOML

cat > src/billing/invoice.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineItem:
    sku: str
    quantity: int
    unit_price_cents: int
    taxable: bool = True


@dataclass(frozen=True)
class InvoiceSummary:
    subtotal_cents: int
    discount_cents: int
    taxable_subtotal_cents: int
    tax_cents: int
    total_cents: int


def calculate_invoice_summary(
    items: list[LineItem],
    *,
    discount_rate: float,
    tax_rate: float,
) -> InvoiceSummary:
    subtotal = sum(item.quantity * item.unit_price_cents for item in items)

    # BUG: discount should be rounded on the full subtotal and applied before tax.
    discount = int(subtotal * discount_rate)

    # BUG: taxable subtotal ignores discounts, which overcharges tax.
    taxable_subtotal = sum(
        item.quantity * item.unit_price_cents
        for item in items
        if item.taxable
    )
    tax = int(taxable_subtotal * tax_rate)
    total = subtotal - discount + tax
    return InvoiceSummary(
        subtotal_cents=subtotal,
        discount_cents=discount,
        taxable_subtotal_cents=taxable_subtotal,
        tax_cents=tax,
        total_cents=total,
    )
PY

cat > tests/test_invoice_public.py <<'PY'
from billing.invoice import LineItem, calculate_invoice_summary


def test_discount_is_applied_before_tax_for_mixed_taxability():
    summary = calculate_invoice_summary(
        [
            LineItem("hardware", quantity=2, unit_price_cents=10_000, taxable=True),
            LineItem("training", quantity=1, unit_price_cents=5_000, taxable=False),
        ],
        discount_rate=0.10,
        tax_rate=0.0825,
    )

    assert summary.subtotal_cents == 25_000
    assert summary.discount_cents == 2_500
    assert summary.taxable_subtotal_cents == 18_000
    assert summary.tax_cents == 1_485
    assert summary.total_cents == 23_985
PY

git add pyproject.toml src/__init__.py src/billing/__init__.py src/billing/invoice.py tests/__init__.py tests/test_invoice_public.py
git commit -q -m "initial invoice service"
BASE_HEAD="$(git rev-parse HEAD)"
echo "operator scratch must survive" > scratch.txt

if python -m pytest tests/test_invoice_public.py -q >/tmp/plan-orchestrate-code-runner-public-before.log 2>&1; then
  echo "Expected public invoice test to fail before code-runner" >&2
  exit 1
fi

cat > "$TMP/plan.yaml" <<YAML
version: 1
kind: orchestrate-plan
metadata:
  title: Real-world invoice calculator repair through plan/orchestrate/code-runner
  goal: Fix invoice discount and tax calculation in an isolated code-runner worktree.
  plan_type: code
  created: "2026-05-03"
  primary_persona:
    name: "Nico Bailon"
    role: "QA Engineer"
    source: "synthetic E2E fixture"
repo_root: "$REPO"
capability_overlap:
  - "Existing /plan, /orchestrate, and /code-runner skills are being composed; no bespoke runner is introduced."
  - "This is a sanity test for the composed execution boundary, not a replacement for any existing skill."
questions_blockers:
  - "None"
execution:
  max_concurrency: 1
  wave_barrier: true
  scheduling_policy: dependency_only
lanes:
  - id: "0"
    label: "Wave 0: Plan validation and implementation"
  - id: "1"
    label: "Wave 1: Patch artifact verification"
tasks:
  - id: "1"
    title: Repair invoice discount and tax calculation
    lane: "0"
    runner: code-runner
    backend: codex
    mode: iterative
    skills:
      - code-runner
    depends_on: []
    prompt: |
      Fix the invoice calculation bug in src/billing/invoice.py.
      Requirements:
      - Compute subtotal as quantity times unit price for every line item.
      - Compute discount_cents by rounding subtotal_cents * discount_rate to the nearest cent.
      - Allocate the discount proportionally across taxable line items before computing taxable_subtotal_cents.
      - Compute tax_cents by rounding taxable_subtotal_cents * tax_rate to the nearest cent.
      - Preserve the public dataclasses and function signature.
      - Modify only src/billing/invoice.py.
    allowlist:
      - src/billing/invoice.py
    read_context:
      - src/billing/invoice.py
      - tests/test_invoice_public.py
    dirty_worktree_policy: isolated_worktree
    max_rounds: 3
    timeout_seconds: 900
    definition_of_done:
      command: "python -m pytest tests/test_invoice_public.py -q"
      assertion: "exit_code == 0"
    tests:
      - "python -m pytest tests/test_invoice_public.py -q"
    blind_tests:
      - command: |
          python - <<'PY'
          from billing.invoice import LineItem, calculate_invoice_summary

          summary = calculate_invoice_summary(
              [
                  LineItem("subscription", quantity=1, unit_price_cents=10000, taxable=True),
              ],
              discount_rate=0.10,
              tax_rate=0.05,
          )

          assert summary.subtotal_cents == 10000, summary
          assert summary.discount_cents == 1000, summary
          assert summary.taxable_subtotal_cents == 9000, summary
          assert summary.tax_cents == 450, summary
          assert summary.total_cents == 9450, summary
          PY
YAML

"$PLAN" --validate "$TMP/plan.yaml"

if "$REVIEW_PLAN" review "$TMP/plan.yaml" > "$TMP/review-plan.log" 2>&1; then
  echo "review-plan passed"
else
  echo "review-plan failed; output follows" >&2
  python - <<PY
from pathlib import Path
print(Path("$TMP/review-plan.log").read_text())
PY
  exit 1
fi

env -u CODE_RUNNER_MOCK_RESPONSE \
  SKILLS_DIR="$ROOT/skills" \
  ORCHESTRATE_HOME="$ORCH_HOME" \
  ORCHESTRATE_ALLOW_LOCAL_BLIND_TESTS=1 \
  CODE_RUNNER_LIVE_BACKEND=codex \
  "$ORCH" run "$TMP/plan.yaml"

SESSION_DIR="$(find "$ORCH_HOME/structured" -maxdepth 1 -type d -name 'session-*' | sort | tail -1)"
test -n "$SESSION_DIR"

python - <<PY
import json
import subprocess
from pathlib import Path

repo = Path("$REPO")
session = Path("$SESSION_DIR")
status = json.loads((session / "status.json").read_text())
assert all(task["status"] == "passed" or task.get("raw_status") == "completed" for task in status["tasks"]), status

result_files = sorted(session.glob("1*.result.json"))
assert result_files, list(session.iterdir())
result = json.loads(result_files[-1].read_text())
assert result["status"] == "pass", result
assert result["dod_passed"] is True, result
assert result["execution_mode"] == "isolated_worktree", result
assert result["worktree_removed"] is True, result
assert not Path(result["worktree_path"]).exists(), result
assert result["backend"] == "codex", result

patch = Path(result["patch_artifact"])
assert patch.exists() and patch.read_text().strip(), result
patch_text = patch.read_text()
assert "src/billing/invoice.py" in patch_text, patch_text
assert "scratch.txt" not in patch_text, patch_text
assert "tests/test_invoice_public.py" not in patch_text, patch_text

assert (repo / "scratch.txt").read_text() == "operator scratch must survive\\n"
assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip() == "$BASE_HEAD"
assert subprocess.run(["git", "status", "--short"], cwd=repo, text=True, capture_output=True, check=True).stdout == "?? scratch.txt\\n"

review = repo / "review-applied"
subprocess.run(["git", "worktree", "add", "--detach", str(review), "HEAD"], cwd=repo, check=True, text=True, capture_output=True)
try:
    subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)], cwd=review, check=True, text=True, capture_output=True)
    subprocess.run(["python", "-m", "pytest", "tests/test_invoice_public.py", "-q"], cwd=review, check=True, text=True)
    subprocess.run(
        [
            "python",
            "-c",
            "from billing.invoice import LineItem, calculate_invoice_summary; "
            "s=calculate_invoice_summary([LineItem('subscription',1,10000,True)], discount_rate=0.10, tax_rate=0.05); "
            "assert (s.subtotal_cents,s.discount_cents,s.taxable_subtotal_cents,s.tax_cents,s.total_cents)==(10000,1000,9000,450,9450), s",
        ],
        cwd=review,
        check=True,
        text=True,
    )
finally:
    subprocess.run(["git", "worktree", "remove", "--force", str(review)], cwd=repo, check=False, text=True, capture_output=True)

print("plan -> orchestrate -> code-runner real-world e2e passed")
PY
