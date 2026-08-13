# project-state — current implementation state (2026-08-13)

## What this skill is

One command that reports the state of a TARGET checkout: infrastructure
metrics (Phase 1), /memory recall (2), doc-code drift (3), best-practices
audit (4), external research via /brave-search + /github-search + /arxiv (5),
and gap analysis (6). `--quick` runs Phase 1 + 6 only.

## Scope contract (the rule this skill kept breaking)

**A report about target X describes X.** Nothing may be borrowed from an
unrelated tree, and no phase may claim a composed service is "available" when
nothing answered. Both failure modes shipped silently before 2026-08-13.

## Defects found and fixed 2026-08-13 (all reproduced first)

| # | Defect | Symptom | Fix |
|---|---|---|---|
| 1 | Cross-project test subprocess inherited this skill's `VIRTUAL_ENV`/`UV_PROJECT_ENVIRONMENT` | pitchdeck's 132 tests reported as 0 | strip both from the child env |
| 2 | `python -m pytest` skips dev groups | target had no pytest in its runtime env | `uv run --project X --with pytest pytest` |
| 3 | Parser expected "N tests collected"; modern pytest `-q` emits per-file `path.py: N` with no summary | count fell through to 0 | sum per-file counts, old parse as fallback |
| 4 | `collect_skills()` fell back to the GLOBAL skills tree | 386 unrelated skills reported as one skill's state | only roots the target owns; else `applicable: false` + reason |
| 5 | Research queries hardcoded ("extraction pipeline", "layout parsing") | a slide compiler was researched as a document-extraction tool | topic terms derived from target pyproject description / README heading |
| 6 | `phase_2` returned `available: true` whenever the memory skill FILE existed | "available, 0 found" when the service was unreachable | availability = at least one recall answered; `successful_recalls`/`attempted_recalls` reported |
| 7 | `phase_5` returned `available: true` unconditionally | 3 queries, 0 results, still "available" | availability = at least one lane answered; `queries_answered` reported |

## Regression armour

`fixtures/agentic_eval.json` (v2, trials 2, **7 cases, READY**) drives the real
`./run.sh report` entrypoint through `scripts/assert_report_scope.py`:
- skill target collects >=50 of its own tests and reports skills not-applicable
- repo root still counts >=100 skills
- adversarial: demanding a global skills count for a skill target must FAIL
- adversarial: demanding 500 tests where 132 exist must FAIL
- full report: all six phases present, memory + research queries name the target
- adversarial invariant: `available` must equal "something actually answered"
  (catches silent success without sabotaging a live service)
- adversarial: templated research queries must not return

## Still unproven — named, with evidence

- **Doc-drift precision is poor and untested.** Phase 3 flagged 13 items for
  pitchdeck; inspection shows they are keyword hits on `not_yet`, `planned`,
  `future` — including deliberately honest hedges ("the gate certifies
  HOUSE_NON_ANOMALOUS — it is not yet a validated positive"). It reports
  forward-looking language as drift. No case asserts precision.
- **Best-practices audit completeness.** Phase 4 returned 0 findings across
  all severities for a 20k-line target. The scanner is a regex pass for
  hardcoded secrets / bare excepts; 0 may be honest, but nothing proves the
  scan ran over the files it claims. No seeded-defect case exists.
- **Recall and research RESULT quality.** Availability is now honest, but
  whether the returned items are relevant is unasserted (pitchdeck's three
  recalls answered with `found: false, count: 0`).
- **Portability.** The fixture pins absolute paths on this workstation; it
  proves scoping here, not scoping in general.
- **Non-quick modes at scale.** `--full` takes ~10 min against one skill; no
  case covers a large repo target, cleanup-tail, or the figures path.

## Composition

Composes agentic-evals (regression armour), memory, brave-search,
github-search, project-knowledge, ingest-code, create-figure, service-status,
data-audit, assistant. ArangoDB is reached only through /memory.
