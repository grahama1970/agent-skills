# grahama.co Visual-World Direction Roundtable R1

## Objective

Run an equal-context roundtable for grahama.co's next visual-world direction. The output must be a receipt-backed direction contract and prioritized executable slice manifest that makes the site more uniquely bespoke while preserving the current core premise:

> claim -> evidence -> bounded judgment

This phase stops after synthesis. It must not implement UI changes.

## Immutable Goal

Produce a receipt-backed grahama.co visual-world direction contract and prioritized executable slice manifest that makes the site more uniquely bespoke while preserving claim-to-evidence-to-bounded-judgment, then stop before implementation.

## Target

- Site/repo: `/home/graham/workspace/experiments/agent-skills/site`
- Public surface: `grahama.co`
- Current source checkout: `/home/graham/workspace/experiments/agent-skills`
- Recent clean integration worktree used for pushed site amendments: `/home/graham/workspace/experiments/agent-skills-push-receipts`

## Current Evidence

Recent pushed amendments, with deterministic local proof:

- `0d84c1434` made generated receipts fail closed instead of silently disappearing.
- `3bc4fe832` repaired generated surface audit invariant.
- `a57f8c1ef` made receipts artifact-first.
- Remote check reported `origin/main = a57f8c1ef5ffaaefdc7e3309e8c8ce12967cfd26`.
- `skills/monitor-website/run.sh audit --no-live --json`: `ok: true`, `drift: []`.
- `skills/monitor-website/run.sh copy-audit --json`: `status: PASS`, `violations: []`, `strings_scanned: 364`.
- `skills/monitor-website/run.sh design-world-check --json`: `contract PASS`, `no_mono_on_human_labels PASS`; `responsive_choreography`, `distinctiveness_blind`, and `craft_integrity_render` remain `NOT_TESTED`.
- `npm run verify:qid`: `OK: 51 interactive elements carry data-qid, data-qs-action, title`.
- `npm run build`: Next production build completed.
- `python3 scripts/check_mock_evidence_claims.py`: no violations.
- Visual proof artifacts from the prior slice:
  - `/tmp/grahama-receipts-item2-desktop-viewport-v2.png`
  - `/tmp/grahama-receipts-item2-mobile-clean-crop.png`
- Visual geometry notes: desktop primary receipt area measured `1.85x` the largest secondary receipt area; mobile page overflow measured `0`.

## Known Gaps

Do not mark the design compliant or complete. `$best-practices-bespoke-design` still lacks required proof artifacts:

- `evidence-ledger.yaml`
- `visual-world-brief.yaml` or `DESIGN.md`
- three territory boards and selection record
- full screenshot stress corpus: 390x844, 768x1024, 1440x900, extra-wide, 200% zoom, reduced motion, focus traversal, failed-image and long-text states
- accessibility receipt
- performance receipt for LCP/INP/CLS
- five-rater logo-off, competitor-swap, and cross-screen-family evidence
- validated `bespoke-design-receipt.json`
- Impeccable finish-review receipt for G16-G18, if the runtime is available

## Current Directional Inputs

Earlier WebGPT design-review output suggested six ordered amendments:

1. Receipts fail closed instead of silently disappearing.
2. Receipts artifact-first layout.
3. About path-first using an existing real visual path.
4. Competence matrix-first.
5. Retire decorative section serials/rules.
6. Close G10 by deferring noncritical computation, then measuring LCP.

Items 1 and 2 have been implemented and locally exercised. Items 3-6 remain direction or implementation candidates, not accepted requirements.

## Constraints

- Do not invent brand claims, metrics, awards, cultural references, or product capabilities.
- Do not copy Owltastic motifs or any living designer's signature surface.
- Do not solve bespoke distinctiveness through decoration alone.
- Do not make the site converge with SPARTA Explorer or other Graham-owned projects into a shared dark-editorial template.
- Preserve evidence discipline: model consensus is advisory, not proof.
- The selected world must be usable for `$best-practices-bespoke-design` gates and Impeccable finish review.
- Impeccable should sharpen the chosen world later; it must not replace the direction gate with generic polish.

## Roundtable Questions

Each seat should answer from the same context:

1. What is the strongest brand-derived narrative premise for grahama.co, based on the current claim -> evidence -> bounded judgment direction?
2. What three semantically distinct visual territories should be explored before implementation?
3. Which territory best balances distinctiveness, usefulness, accessibility, performance, editability, and system depth?
4. What non-color component invariants would make the site recognizable without logo, name, or palette?
5. Which current or proposed patterns risk template residue, competitor-swappability, or cross-project convergence?
6. What should Impeccable later compare against for G16 type fidelity, G17 material fidelity, and G18 amend-loop integrity?
7. What is the smallest next implementation slice that can be proven with local screenshots and deterministic checks?

## Required Response Format

Return:

```markdown
## Position
One sentence naming the proposed direction.

## Proposed World Model
Premise, personality tensions, motif family, type character, material language, composition model, motion grammar, and voice.

## Three Territories
Three genuinely distinct territories with evidence mapping, risks, exclusions, and implementation cost.

## Recommended Direction
Which territory should be selected or combined, and why.

## Protected Invariants
At least three non-color rules that must survive across page types and breakpoints.

## Risks and Dissent
Genericity, leakage, accessibility, performance, implementation, or competitor-swap risks.

## Impeccable Comparison Model
What Impeccable should later test for type/material/finish fidelity.

## Next Slice
Smallest verifiable implementation slice, with local proof commands and screenshot states.
```

## Proof Boundary

This roundtable can produce direction, critique, candidate territories, and an executable slice manifest. It cannot prove implementation, accessibility, performance, distinctiveness thresholds, or final compliance. Those require local artifacts, browser screenshots, deterministic commands, and rater/test receipts.
