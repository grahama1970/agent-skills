# Report enforcement ($create-architecture)

> **This is where the human checks your work.**
> Not chat. Not `gap-report.md` alone. Not "tests passed" in the agent reply.
> The human opens the HTML/CSS progress report to verify what you fixed and what is still open.

The **HTML/CSS progress report** is the primary human-facing artifact. Markdown
`gap-report.md` supplements it; it does **not** replace it.

If the human opens the report and cannot answer **what was fixed** and **what is
still outstanding**, the round is **not closed** — regardless of tests passing.

## When a report is required

| Project type | Report |
|--------------|--------|
| Brownfield / existing repo with routing or state machine | **Required** — path named in `GOAL.md` |
| Greenfield empty repo | Create `GOAL_PAGE.html` or project doc before engagement 2 |
| Test-only local closure | **Still required** — add engagement-log row + sanity row |

## Blocking closure checklist (every round)

Do **not** tell the human a slice is closed until **all** pass:

```
[ ] Live proof ran on real services (not mocks-only) — commands recorded
[ ] HTML engagement-log row added/updated (slice id, what changed, port delta)
[ ] HTML gaps table row matches proof (LIVE / PARTIAL / MISSING — not aspirational)
[ ] HTML sanity table row matches proof
[ ] Diagram/visual styling matches table (no "NOT BUILT" on LIVE nodes)
[ ] HTML "last updated" date refreshed
[ ] gap-report.md written (receipt — not substitute for HTML)
[ ] HANDOFF.md next-slice pointer updated
```

**Order:** proof → **HTML report** → `gap-report.md` → HANDOFF → claim closed.

## Required HTML sections (brownfield)

1. **Engagement log** — one row per round: slice id, status, what was fixed,
   port delta vs WebGPT zip, proof commands + exit codes, artifact paths
2. **Gaps table** — capability-level LIVE / PARTIAL / MISSING / NOT BUILT
3. **Sanity table** — test/command-level proof matrix
4. **Roadmap** — P0…Pn with DONE only when live proof exists
5. **Diagrams** — node styling must agree with gaps table

## LIVE rules

- **LIVE** only after live daemon/stack test passes (record command + exit code in HTML)
- **UNIT** when only unit tests exist
- Never mark LIVE in `gap-report.md` while HTML still shows MISSING
- Never mark LIVE in HTML while master diagram still styles the path as `gap`

## Serving (avoid stale `file://` cache)

Prefer HTTP for verification:

```bash
cd <repo-root> && python -m http.server 8771
```

Document the served URL in the engagement log.

## Anti-patterns (round rejected)

- Updating only `gap-report.md` and skipping HTML
- Patching one table cell without engagement-log narrative
- Claiming closure in chat without report update
- Diagram contradicting sanity table
- "Tests passed" without commands in the report

## Blocking verifier (required before closure)

Run from memory repo (or pass repo root):

```bash
../agent-skills/skills/create-architecture/verify_progress_report.sh \
  docs/SPARTA_ROUTING_EVIDENCE_CASE_FLOW.html \
  /home/graham/workspace/experiments/memory \
  docs/create-architecture/<slice-id>/ACCEPTANCE_GATES.yaml
```

**Exit 1 = do not mark HTML rows LIVE.** Fix repo or HTML first.

Rules enforced:
- Every §4 row with LIVE status must have matching pytest node or `scripts/sanity/*` file
- UNIT rows are exempt
- Script commands may include args (only path segment checked)
- Optional `ACCEPTANCE_GATES.yaml` cross-checks gate manifest

Closure order: **live proof → verifier PASS → HTML LIVE row → gap-report.md**

