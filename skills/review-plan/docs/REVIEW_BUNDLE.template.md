# Review request

> **agent-skills:** save as `plans/REQUEST.md` (not `PLAN.md`). Regenerate with `./scripts/build_review_bundle.sh`.

- **Target**: `<plan.md or DAG path>`
- **Round**: `<N>`
- **Reviewer**: WebGPT tech lead (`$ask webgpt`, tab `<id>` or project `<name>`)
- **Question**: Is this plan/orchestration ready for `/orchestrate`? List only concrete blockers.

## This round acceptance

- [ ] `<criterion 1 — e.g. DAG schema validates>`
- [ ] `<criterion 2 — e.g. blind tests named per task>`
- [ ] `<criterion 3 — e.g. no code-runner curl DoD>`

## Local gates (already run)

| Gate | Command / artifact | Result |
|------|-------------------|--------|
| review-plan deterministic | `./run.sh review <plan> --json` | PASS / FAIL summary |
| pytest / phart / sanity | `<command>` | exit 0 |
| prior WebGPT round | `<path to review.md>` | NEEDS_CHANGES / PASS |

## Plan excerpt

Paste only the sections under review (Capability Overlap, task list, DoD, test manifest).
Do **not** paste the whole repo.

## File: `<relative/path>`

```text
<bounded excerpt — schema, DAG fragment, or task YAML>
```

## Agreement (WebGPT fills after review)

- **VERDICT**: PASS | NEEDS_CHANGES | BLOCKED | INSUFFICIENT_EVIDENCE
- **Blockers**: (numbered, concrete)
- **Non-claims**: what this review did not verify

---

**Delivery**

- **Text only** (no PNGs): save as `plans/REQUEST.md` (≤ 2 MiB) and pass to `/review-plan` as `--ask-review-bundle plans/REQUEST.md`.
- **With screenshots**: zip ≤ 5 files (`REQUEST.md` or legacy `REVIEW.md` + up to 4 PNGs) and pass `--ask-attach-file review.zip` (do not also list bare image paths in the prompt).

`/review-plan` validates bundle shape; `$ask` owns browser submit and artifact capture (`request.json`, `status.json`, `events.jsonl`, `review.md`).
