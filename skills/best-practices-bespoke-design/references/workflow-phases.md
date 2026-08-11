# Workflow Phase Detail

Use this reference when the main `SKILL.md` phase summary is not enough.

## Phase 0 — Goal and Provenance Lock

1. State the user job, primary object, primary decision, and source of truth.
2. Freeze the evidence bundle or record exact source versions.
3. Separate facts, stakeholder preferences, designer hypotheses, and references.
4. Define what must remain editable and what may be rasterized.
5. Pre-register required gates and rater thresholds when the tier requires them.

Stop if the goal or authoritative content is unavailable.

## Phase 1 — Extract the Brand's Own Material

Build the evidence ledger and identify repeated nouns, verbs, metaphors,
contrasts, origin stories, audience language, product mechanics, and claims that
should stay visually quiet. Prefer first-party language and observed behavior
over trend references.

## Phase 2 — Create Three Genuine Territories

Produce three concept territories that differ in semantic premise, emotional
posture, typographic voice, composition model, image or illustration logic,
primary motif, and interaction or motion behavior. Three palettes on the same
wireframe count as one territory.

Each territory should include a premise sentence, evidence mappings, hero,
interior content section, dense or transactional section, mobile composition,
risks, exclusions, implementation cost, and the reason it belongs to the brand
rather than the designer.

## Phase 3 — Select by Fit, Not Prettiness

Use a must-pass matrix: claim and audience fit, content hierarchy, competitor
distinctiveness, system scalability, accessibility feasibility, responsive
feasibility, and implementation/editability feasibility. Preserve the human's
named decision and rejected alternatives.

## Phase 4 — Write the Grammar Before Expanding Screens

Create the visual-world brief using `visual-world-brief.yaml`. Specify a small
number of strong rules, explicit exclusions, and a controlled abundance map:
where richness is allowed, and where reading or task completion must stay calm.

## Phase 5 — Compose the Page as a Story

For every page, write a beat sheet before polishing:
orientation, tension/question, explanation, proof, consequence, next action.
Vary the sequence when the user job requires it.

## Phase 6 — Build in the Browser Early

Prototype in the target rendering environment before high-fidelity approval.
Test type wrapping, content density, interaction, scroll rhythm, image loading,
and breakpoints. A flat mockup approves direction; it does not prove responsive
composition, focus behavior, motion, text reflow, or implementation fidelity.

## Phase 7 — Systemize Without Genericizing

For each component, record semantic purpose, content constraints,
identity-bearing rules, variants and states, responsive transformation,
accessibility behavior, and examples where the component must not be used.

Reject components that exist only because a generic design system normally has
them. Add components when real content or user jobs require them.

## Project Lane Bindings

Every project using this skill should bind one deterministic render-repair lane
and one formal certification lane. The render lane answers "is the current
browser/source surface coherent enough to keep repairing?" The certification
lane answers "may this claim READY?"

For grahama.co:

- render repair:
  `skills/monitor-website/run.sh design-render-check --json`
- formal certification:
  `skills/monitor-website/run.sh design-certify --json`

Missing blind-rater output means certification remains `NOT_TESTED`; it is not a
broken section crop and should not trigger visual redesign by itself.

## Phase 10 — Accessibility and Performance Gates

Require WCAG 2.2 AA review, visible and unobscured keyboard focus, target size,
contrast, semantics, text resize/reflow, alternatives for non-text content,
keyboard completion of all actions, reduced-motion equivalence, representative
LCP/INP/CLS evidence, and no identity-critical information conveyed by color,
animation, texture, or position alone.

Do not claim a reference site or candidate passes these gates without testing it.

## Phase 11 — Emit the Proof Packet

Formal proof packets include:

- `evidence-ledger.yaml`;
- `visual-world-brief.yaml`;
- three territory boards and selection record;
- component and page inventory;
- section/page-state screenshot manifest;
- review bundle and transport receipts when external raters are used;
- accessibility and performance receipts;
- blind-rater inputs and raw outputs;
- validated `bespoke-design-receipt.json`;
- exact source revision and implementation revision.

Receipt evidence must be current to the implementation it claims. Historical
reviewer rounds may be preserved for diagnosis, but they must not be counted as
current acceptance unless prompt, raw outputs, screenshot corpus, artifact
hashes, and source state all match the implementation under review.
