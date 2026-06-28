---
name: best-practices-chat
description: Keep Sparta Chat usable as a modern chat interface while preserving evidence-gated compliance semantics. Use when designing, reviewing, or implementing ChatWell, InlineEvidenceCase, EvidenceWorkspace, ArtifactPanel, distance modes, voice/qid interactions, evidence receipts, artifact previews, or assistant answer ordering.
version: 0.1.0
provides:
  - chat-ux-guidance
  - evidence-backed-chat-patterns
  - sparta-chat-contracts
composes:
  - best-practices-design
  - best-practices-sparta
  - review-design
complies:
  - best-practices-skills
  - best-practices-security
  - best-practices-sparta
  - best-practices-chat
---

# Best Practices Chat Skill — Sparta Chat

## Purpose

Use this skill to keep Sparta Chat from drifting into either of these failures:

1. **Generic chatbot authority** — prose answer with no inspectable evidence.
2. **Audit-console overload** — gates, claims, hashes, approvals, raw JSON, and figures dumped into the chat thread.

The correct model is:

```text
ChatWell = readable conversation + compact evidence/artifact receipts
EvidenceWorkspace = full evidence case adjudication
ArtifactPanel = full figure/table/PDF/source preview
```

Evidence-first means the answer is backed by inspectable evidence, **not** that the full evidence case appears inline.

---

## When to use this skill

Use this skill for any task involving:

- `ChatWell.tsx`
- `InlineEvidenceCase.tsx`
- `InlineArtifact.tsx`
- `InlineFigure.tsx`
- `ArtifactPanel.tsx`
- `EvidenceWorkspace.tsx`
- `SpartaExplorer.tsx` chat drawer or distance modes
- Sparta Chat 10ft / 5ft / lean-in behavior
- Voice, Stream Deck, qid, or `data-qs-action` contracts
- Evidence-case receipt design
- Artifact figure/table/PDF previews in chat
- OpenCode/gateway event mapping into chat UI

---

## Core rule

```text
Keep chat simple. Keep proof inspectable. Keep adjudication out of the thread.
```

The user should read the answer first, then see a compact receipt proving that the answer is backed by an evidence case. The user can open the right pane for full proof.

---

## Message order contract

For a normal evidence-backed turn:

```text
1. User question or heard voice transcript
2. Assistant synthesis: answer / clarify / deflect prose
3. Compact evidence-case receipt
4. Optional compact artifact receipt or preview
5. Composer
```

Do **not** use this order:

```text
Evidence case wall
→ gates
→ claims
→ citations
→ raw JSON
→ answer buried below
```

The answer must not feel like an afterthought.

---

## Evidence receipt contract

The inline evidence case in ChatWell is a **receipt**, not the evidence case itself.

### Required receipt fields

```text
EC-FPGA-CMMC-042 · INCONCLUSIVE · CLARIFY
Reason: source-page provenance missing
Summary: FPGA vendor risk found, but source proof is not audit-valid.
Artifact: Quarterly_Report.pdf · provenance pending
[Open in workspace ↗]
```

### Minimum information beyond pass/fail

The card must answer these four questions:

1. **What is this case?** → case ID
2. **Can I trust the answer?** → verdict + response action
3. **Why is it not resolved?** → one reason
4. **What do I do next?** → Open in workspace

### Strict limits

- One case object
- One state line
- One reason
- One summary line if available
- One artifact/provenance line
- One primary action
- No more than two or three status tokens

### Receipt states

```text
SATISFIED · ANSWER
INCONCLUSIVE · CLARIFY
NOT_SATISFIED · DEFLECT
DRAFT
```

Use one state color rail:

- Green for `SATISFIED / ANSWER`
- Amber for `INCONCLUSIVE / CLARIFY / DRAFT`
- Red for `NOT_SATISFIED / DEFLECT`

---

## What must not appear in the chat receipt

Never show these inside the ChatWell receipt:

- Full gate trace
- Full claims list
- Full citations list
- Full SHA/hash line unless summarized as provenance state
- Approve / Reject / Export
- Raw CAE tree
- Raw JSON
- Long draft-warning paragraph
- Reviewer workflow controls
- Full figure or full table
- Dashboard-like metrics/charts

These belong in `EvidenceWorkspace` or `ArtifactPanel`.

---

## Artifact receipt and preview contract

Inline figures and tables are allowed, but only as compact artifact receipts/previews.

### Keep an artifact receipt when

The artifact is a distinct generated or inspectable output beyond the evidence-case receipt:

```text
Figure: FPGA supplier provenance crosswalk · sample-derived
[Open artifact ↗]
```

```text
Table: Source-page provenance gaps · 3 rows
[Open artifact ↗]
```

### Drop the artifact receipt when

It duplicates the evidence receipt's artifact line.

### Compact previews are allowed

Allowed inline:

- Small thumbnail
- 2–3 row table preview
- Figure title + caption
- Source skill label
- Sample-derived / bound / unbound badge
- Open artifact action

Not allowed inline:

- Full-size chart
- Full table
- Full PDF/source excerpt
- Full crosswalk diagram
- Mini dashboard
- Multi-metric scorecard

Full artifact rendering goes to the right `ArtifactPanel`.

---

## Click and handoff behavior

| User clicks | Target |
|---|---|
| Evidence receipt body | Evidence Workspace → Trace tab |
| `Open in workspace` | Evidence Workspace → Trace tab |
| Artifact line inside evidence receipt | Evidence Workspace → Sources tab, or no-op until wired |
| Separate artifact/figure/table receipt | ArtifactPanel |
| Full preview needed | ArtifactPanel |

Do not make the chat receipt expand into a full audit console.

---

## Distance-mode rules

| Mode | Chat behavior |
|---|---|
| 10ft Glance | No inline evidence cards. Show domain aggregate/map only. |
| 5ft Triage | Compact evidence receipt + Open Trace hero. No full inline audit case. |
| lean-in Drilldown | Compact receipt + workspace open. Full adjudication in right pane. |

Full inline `InlineEvidenceCase` audit panels should not be the default in any distance mode.

---

## Evidence Workspace ownership

`EvidenceWorkspace` owns:

- Full gates
- Claims
- Citations
- Full hashes
- Source-page provenance
- Draft warnings
- Approve / Edit / Defer / Reject / Export
- Reviewer state
- Raw/debug details when needed

The chat receipt can link to this, but must not duplicate it.

---

## ArtifactPanel ownership

`ArtifactPanel` owns:

- Full figure preview
- Full table
- PDF/source excerpt
- Code/raw tab
- Artifact metadata
- SHA256 / provenance details
- Export controls and export-blocked reasons

Chat can show a compact artifact receipt only.

---

## Visual style guidance

Borrow from modern chat products:

- Readable answer first
- Clear message bubbles
- Structured cards
- Inline image/table previews
- Captions
- One primary action per card
- Composer fixed at bottom

Translate into Sparta/Embry/NVIS:

- Dark tactical surfaces
- Compact spacing
- Monospace IDs/hashes/status
- Green for pass/active
- Cyan for Embry/action links
- Amber for draft/clarify/stale
- Red for blocked/deflect
- No Google branding clone
- No purple-dominant generic AI assistant styling
- No dashboard theater

---

## QID and interaction rules

QIDs are runtime contracts for voice, Stream Deck, agents, accessibility, and deterministic tests.

Preserve or add stable qids for:

```text
sparta:chat:panel
sparta:chat:thread
sparta:chat:heard-query
sparta:chat:evidence-receipt
sparta:chat:evidence-receipt:open-workspace
sparta:chat:artifact-receipt:*
artifact:panel
artifact:expand:*
sparta:evidence-workspace
sparta:evidence-workspace:tab-trace
sparta:evidence-workspace:tab-sources
sparta:hud:input
sparta:hud:transmit
```

Do not remove or rename qids without explicit migration.

---

## Review checklist

Before approving a PR or mockup, answer:

1. Is the actual user question visible?
2. Does readable assistant synthesis appear before audit detail?
3. Is the evidence case a compact receipt, not an inline audit console?
4. Does the receipt include case ID, state/action, reason, summary, artifact state, and one CTA?
5. Are gates/claims/citations/hashes/actions removed from the chat card?
6. Are figures/tables compact inline previews only?
7. Does `Open in workspace` focus the Evidence Workspace Trace tab?
8. Does artifact click open the ArtifactPanel?
9. Are disabled reviewer/export states explained in the workspace/panel, not hidden in chat?
10. Are qids stable and testable?
11. Is there any dashboard theater in the thread?
12. Does the mode obey 10ft/5ft/lean-in rules?

If any answer fails, return `NEEDS_CHANGES`.

---

## Acceptance tests to request

Minimum deterministic tests:

- Receipt exists after evidence-case turn.
- Receipt includes case ID, verdict/action, reason, artifact state, CTA.
- Receipt does not contain Approve, Reject, Export, full gates, claims, citations, raw JSON.
- `Open in workspace` opens/focuses `sparta:evidence-workspace:tab-trace`.
- Separate artifact receipt opens `artifact:panel`.
- 5ft uses receipt mode, not full inline case.
- 10ft suppresses inline evidence cards.
- Lean-in has workspace visible and receipt compact.

---

## Default recommendation for current Sparta Chat PR4

Use these defaults unless the human overrides:

```text
1. Artifact receipt in chat: KEEP, optional and deduped.
2. Summary line: ALWAYS when present, one line max.
3. Receipt mode: 5ft + lean-in. 10ft suppresses cards.
4. Artifact chip click: opens ArtifactPanel.
5. Begin with: tests + minimal inline dedupe.
6. Done for receipt slice: demo URL + vitest + TI; live gateway mapping is next slice.
```

---

## Output template for a project-agent review

```markdown
VERDICT: PASS | NEEDS_CHANGES | BLOCKED

CHAT_MODEL:
- pass/degraded/fail — rationale

RECEIPT_CONTRACT:
- pass/degraded/fail — rationale

ARTIFACT_INLINE_PREVIEWS:
- pass/degraded/fail — rationale

WORKSPACE_HANDOFF:
- pass/degraded/fail — rationale

DUPLICATION_CHECK:
- pass/degraded/fail — rationale

P0_FIXES:
1. ...
2. ...
3. ...

NEXT_STEP: IMPLEMENT | MOCKUP_ROUND | HUMAN_REQUIRED
```
