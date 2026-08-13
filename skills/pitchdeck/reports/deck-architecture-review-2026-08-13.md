# Tier-1 deck architecture review — 2026-08-13

Reviewer: /ask -> Tau DAG -> scillm claude-opus-4-8, shown a contact sheet of all 15 rendered slides, the deck plan (section/recipe/claims/images per slide), the canonical README, and the 24-figure source inventory.

## Position

**ARCHITECTURE_VERDICT: INCOMPLETE**

The deck faithfully carries the README's *spine* — thesis (one inspectable decision thread), the three boundaries (relevance ≠ support), architecture, product proof, roadmap, partners. Sequence and claims are honest and well-anchored. But it under-represents two load-bearing README pillars — the **"At a Glance" reader/persona value** and the **Built on Embry OS / plant↔warfighter mission-separation** story — and it leaves the deck's single strongest available screenshots on the shelf. It represents the project's *argument* but not its full *scope*.

## Evidence

**(1) README sections with NO slide**
- **At a Glance** (four reader personas — compliance/assessor, analyst/engineer, program/supplier lead, platform/integration). This is a core buyer-mapping table; nothing carries it.
- **Built on Embry OS** as its own section. The Embry mission-separation model (plant profile ↔ warfighter profile, shared infrastructure / separated authority) is a headline README block but survives only as a passing line on the partners slide (14) via `sparta-global-posture` — not the `sparta-explorer-embry-os-value-prop-header` figure the README itself features.
- **Candidate-versus-reviewed** (RD-0003) — the README's sharpest "visibility is not compliance credit" proof — has no dedicated slide, though `working-surfaces` gestures at it.

**(2) Slides carrying no README-anchored claim**
- All dividers (4, 6, 9, 12) and cover/toc/close (1, 2, 15) — expected, structural.
- **Slide 8 (m-ask)** and **Slide 14 (m-partners)** carry claims but sit in `section: null` with no recipe — orphaned from the section model; they're doing real work but architecturally unlabeled.

**(3) Strong unused source images**
- `sparta-explorer-embry-os-value-prop-header.webp` — the README's own Embry OS hero figure. **Unused.** Belongs on a dedicated Embry OS / mission-separation slide (near 7 or 14).
- `sparta-explorer-threat-matrix-rd0003-candidate-20260721.webp` — the candidate-vs-reviewed proof. **Unused.** Belongs in the proof section (10–11) as the "visibility ≠ compliance credit" money shot.
- `sparta-explorer-f36-overview.webp` — would strengthen slide 8 (the F-36 demo ask).

**(4) Sequence vs README argument**
Matches well. README flows: thesis → product-in-one-view → personas → Embry OS → F-36 demo → why (three boundaries) → why collaborate. Deck flows: thesis → problem → architecture → ask → proof → roadmap → partners. The deck **front-loads architecture before proof**, which is fine, but it **inverts the README** by putting the boundaries (relevance-not-support) inside the *problem/solution* slide (5) rather than as a distinct "Why" beat, and it drops personas entirely, so the "who is this for" answer arrives late (slide 14) and thin.

**(5) Single biggest architectural fix**
Add a dedicated **Embry OS mission-separation slide** using the unused `embry-os-value-prop-header` figure, placed right after architecture (slide 7). It's the one headline README pillar with a purpose-built public image that the deck currently reduces to a one-liner.

## Uncertainties

- Whether the four reader personas were deliberately cut for a design-partner (single-audience) pitch vs. accidentally dropped — that changes whether the "At a Glance" gap is a flaw or a scope choice.
- Cannot confirm from the contact sheet whether slide 10/11 crops already visually convey candidate-vs-reviewed separation; if they do, the RD-0003 gap is softer.
- `sparta-global-posture` maps to an unclear source figure; can't verify it's the right stand-in for Embry OS.

## Blockers

- Need confirmation of intended audience (broad readership vs. single design-partner) before finalizing whether the personas section must be restored.
- Need the public-clearance status verified for `embry-os-value-prop-header` and `rd0003-candidate` — both appear in the README but the "9 cleared for public use" subset isn't enumerated here, so I can't confirm they're deployable.