---
title: Cap files by what they contain, not by one number
impact: CRITICAL
impactDescription: prevents the page-monolith failure mode this skill already warns about
tags: composition, modularity, file-size, enforcement
---

## Cap files by what they contain, not by one number

**Impact: CRITICAL**

This skill already says a large page monolith is wrong, and shows a 2,000-line
route component owning grid, alerts, voice UI, chat well, timers and command
registry. What it did not say is where the line is — so nothing failed until a
real file reached **14,767 lines with 173 top-level declarations**, including a
6,280-line root component.

A ceiling only enforces modularity if it is low enough to fire. Measured across a
99-file React surface after that file was split, the median module was 56–192
lines. A ceiling of 800 flagged 2 files out of 99; the same code at 400 flags the
ones actually worth splitting.

Do not reuse a Python line limit here. JSX is verbally bulky: one element carrying
`data-qid`, `data-qs-action`, `title`, `onClick` and `style` costs 6–8 lines, so
800 lines of TSX holds far less logic — and far more branching — than 800 lines of
Python. Copying the number silently triples the real budget.

**Two ceilings, because the kinds fail differently:**

| Contents | Ceiling | Why |
|---|---|---|
| Anything with logic — components, hooks, helpers | **400** | Size here means branching and state. A component past 400 lines is doing more than one job, which is the blast-radius problem this skill already describes. |
| Pure data — style maps, token tables, fixtures, generated catalogs | **800** | A long lookup table is reviewable by scanning. It has no control flow, so splitting it further adds imports without reducing risk. |

The distinction matters more than either number. A 795-line style map is fine. A
500-line component is not.

**Incorrect (one component owning several concerns):**

```tsx
// 1,061 lines: fetches writers, builds prompt payloads, renders the draft
// editor, owns reviewer state, and renders the console shell.
function DirectorConsole({ stage, onSelect }: Props) {
  // ...
}
```

**Correct (the shell composes; each concern is its own module):**

```tsx
function DirectorConsole({ stage, onSelect }: Props) {
  return (
    <ConsoleShell>
      <WriterPicker stage={stage} onSelect={onSelect} />
      <DraftEditor stage={stage} />
      <ReviewerPanel stage={stage} />
    </ConsoleShell>
  )
}
```

**Enforcement.** `scripts/verify-file-size.py` exits 1 on violation and must run
in CI and in `/plan` DoD for any UX task, alongside `verify-data-qid.py`.
`/review-plan` must fail a UX plan that omits it.

```bash
python3 scripts/verify-file-size.py src/            # default ceilings
python3 scripts/verify-file-size.py src/ --json     # machine-readable
```

Existing violations are recorded in a `.file-size-allowlist` next to the checked
tree, with one path per line. An allowlist entry is a debt marker, not an
exemption: it names the file, and the check fails if an allowlisted file grows
further. New files get no allowance.

Reference: this skill's own "Rebuilding a chat/control well inside a large page
monolith" rule, which this makes measurable.
