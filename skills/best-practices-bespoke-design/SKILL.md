---
name: best-practices-bespoke-design
description: >
  Evidence-first art direction and review rules for creating digital experiences
  that feel genuinely custom to one brand instead of template-derived. Use when
  a user asks for bespoke web design, a distinctive visual world, personality-led
  art direction, an analysis of what makes a designer's work unique, or an audit
  of whether a website is memorable without copying another designer's signature.
triggers:
  - bespoke web design
  - make this feel custom
  - make this site distinctive
  - build a visual world
  - brand personality art direction
  - avoid template design
  - analyze what makes this design unique
  - audit whether this looks bespoke
metadata:
  short-description: Evidence-backed visual-world design and bespoke-design audit
provides:
  - bespoke-design-brief
  - brand-world-grammar
  - visual-distinctiveness-audit
  - responsive-art-direction-gates
  - bespoke-design-proof-receipt
composes:
  - best-practices-font
  - impeccable
  - best-practices-design
  - best-practices-react
  - review-design
  - agentic-evals
  - interview
complies:
  - best-practices-skills
  - best-practices-design
  - best-practices-react
taxonomy:
  - design
  - branding
  - distinctiveness
  - validation
  - accessibility
disciplines:
  - engineering-standards
  - ui-design-engineering
  - content-creation
runtime_self_improvement: none
domains:
  - marketing
---

# Best Practices: Bespoke Digital Design

## Position

A bespoke interface is not a fashionable component library with unusual colors.
It is a traceable transformation:

**brand and audience truth → personality → narrative premise → visual grammar →
responsive component system → rendered proof.**

This skill was informed by Meagan Fisher Couldwell's Owltastic portfolio. The
lesson to retain is her method of making each project feel authored for its
subject. Do not reproduce her owls, celestial engravings, exact typography,
page compositions, palettes, illustrations, or other signature surfaces.

## Immutable Outcome

The finished work must be:

1. **Specific** — it could not be swapped onto a close competitor without visible
   conceptual tension.
2. **Useful** — the expressive system strengthens the user job and content
   hierarchy rather than competing with them.
3. **Coherent** — typography, palette, imagery, motifs, composition, motion, and
   voice express the same premise.
4. **Systemic** — the premise survives across page types, components, states, and
   breakpoints; it is not confined to a hero illustration.
5. **Inclusive and performant** — personality does not excuse inaccessible type,
   contrast, focus, motion, controls, or poor field performance.
6. **Provable** — acceptance is based on source-backed artifacts, rendered screens,
   browser behavior, and adversarial review, not prose confidence.

When evidence is missing, report `NOT_TESTED`, `NOT_ESTABLISHED`, or `BLOCKED`.
Never summarize missing proof as success.

## Modes

Use one of three explicit modes:

- **ANALYZE** — reverse-engineer the durable method behind a body of work while
  separating method from copyable surface style.
- **DIRECT** — create a new, brand-specific visual world and implementation brief.
- **AUDIT** — test an existing design for specificity, coherence, usability,
  accessibility, system depth, and template residue.

## Evidence Tiers

Do not run the formal certification path when the human only needs a design
decision, release-risk read, or next repair slice. Choose the lightest tier that
answers the current decision and state the tier in every report.

| Tier | Use when | Evidence required | Legal conclusion |
| --- | --- | --- | --- |
| `directional` | Choosing or improving a concept | source claims, rendered crops, concrete critique | `promising`, `needs repair`, or `not established` |
| `release-risk` | Deciding whether to keep, patch, or deploy a public candidate | current local render, focused checks, known gaps, highest-risk reviewer input | `credible with gaps`, `hold release`, or `ready for bounded deployment` |
| `formal-certification` | The human asks for `READY`, a final gate, or adversarial proof | every required G0-G20 gate with current receipts | `READY` only when every gate is `PASS` |

Default to `release-risk` for live website work. Escalate to
`formal-certification` only when the human explicitly asks for formal READY,
when a deployment policy requires it, or when the disputed claim is itself a
formal gate. A `release-risk` pass is not a `formal-certification` pass.

## Call Budget

External reviewers are bounded by tier. No reviewer call may run until the local
checks for the surface are `PASS` or explicitly waived with a reason. Exceeding
the budget is a process failure, not an evidence upgrade.
Reviewer calls must not diagnose local CSS/source defects, missing sections,
stale receipts, missing crops, or harness failures; those stay in deterministic repair lanes. Web review before local artifacts are current is instability.

| Tier | Local checks | Reviewer providers | Submissions | Controlled tabs |
| --- | --- | --- | --- | --- |
| `directional` | required | 0-1 | one compact packet | reviewer + site |
| `release-risk` | required | 0-2 | one compact packet per provider | one per provider + site |
| `formal-certification` | required | pre-registered G11 set | one per rater seat | one per provider + site |

## Required Inputs

Before art direction, collect or mark missing:

- authoritative brand/product claims and source locations;
- primary audiences, jobs, anxieties, desired feelings, and decisions;
- real content inventory, including awkward and dense content;
- current identity assets and constraints;
- three to five close competitors or plausible substitutes;
- implementation environment and editable primitives;
- required page types, states, and breakpoints;
- accessibility, browser, and performance targets;
- human approver and approval boundary.

Do not invent brand values, audience needs, product capabilities, awards, metrics,
or cultural references to make a visual concept easier.

## Core Model

### 1. Truth

Create an evidence ledger before a mood board. Each row contains:

- `claim_id`;
- exact claim or observation;
- source and source type;
- confidence;
- audience relevance;
- possible visual implication;
- prohibited inference.

A visual decision may be inspired by a claim, but it must not become evidence for
that claim.

### 2. Personality

Describe the brand as behavior, not a pile of adjectives. Use paired tensions,
for example:

- learned ↔ plainspoken;
- precise ↔ improvisational;
- archival ↔ future-facing;
- quiet ↔ theatrical;
- institutional ↔ intimate;
- rigorous ↔ mischievous;
- protective ↔ provocative.

For each selected position, name the source evidence and the audience consequence.
Avoid generic combinations such as “modern, clean, friendly, innovative.”

### 3. Narrative Premise

Write one sentence that joins subject, action, and emotional promise:

> This experience behaves like **[specific world or instrument]** so that
> **[audience]** can **[job or decision]** while feeling **[earned emotion]**.

The premise must be semantically related to the brand and useful to page
composition. A mood such as “retro-futurist” is not yet a premise.

### 4. Visual Grammar

Define rules, not a collage of preferences:

- **typographic roles** — display, reading, utility, data, annotation;
- **palette roles** — anchor, field, signal, atmosphere, semantic state;
- **motif family** — one primary device and a small supporting vocabulary;
- **image system** — subject, crop, treatment, sequencing, and provenance;
- **spatial grammar** — grid, reading lane, focal scale, rhythm, and permitted
  ruptures;
- **material language** — line, border, texture, depth, radius, and shadow;
- **motion grammar** — what moves, why, amplitude, duration, and reduced-motion
  equivalent;
- **voice** — headline behavior, labels, calls to action, wit boundary, and
  prohibited tones;
- **component invariants** — at least three identity-bearing rules that remain
  recognizable without the logo or palette;
- **responsive choreography** — what reorders, collapses, crops, simplifies, or
  changes modality at each breakpoint.

Every recurring expressive device must map to a claim, audience need, or narrative
function. “It looks interesting” is insufficient provenance.

For font choice, pairing, hierarchy, delivery, and type-specific proof, compose
with `best-practices-font`. Bespoke design owns the world model and distinctness
gates; `best-practices-font` owns the font-world contract and receipt.

### 5. System

Translate the grammar into reusable primitives without sanding off its identity.
The component inventory must include:

- navigation and wayfinding;
- hero and editorial lead;
- dense prose and long-form reading;
- card/list/index patterns;
- proof, quote, metric, and source treatment;
- forms and transactional states;
- empty, loading, error, disabled, and success states;
- footer/contact/end-state;
- at least one high-density and one low-density page;
- small, medium, and large viewport behavior.

A bespoke design that works only on the homepage is a campaign image, not a system.

### 6. Proof

Use screenshots and runnable behavior. A design is not accepted because a model,
designer, or stakeholder says it feels special.

## Protocol

### Reliability Guard — Candidate Binding and Two Verdicts

Do not collapse practical site judgment and formal proof status into one word.
Every run must report two separate verdicts when both are relevant:

- `release_design_verdict` — whether the rendered site is coherent, useful, and
  appropriate for the stated audience based on the current review bundle.
- `formal_bespoke_ready` — whether every required G0-G20 gate has current,
  hash-bound evidence and therefore may legally report `READY`.

A site may be acceptable for public use while `formal_bespoke_ready` is
`NOT_READY`. That is not a design contradiction; it means the formal packet is
incomplete. Conversely, a historical `READY` receipt is not current proof.

Every receipt, crop corpus, contact sheet, rater output, accessibility result,
performance result, and finish-review packet must be bound to the active
candidate by source revision or candidate fingerprint. If the active candidate
changes, older receipts become historical evidence only. They may inform the
next slice, but they must not count toward current `formal_bespoke_ready`.

Candidate freshness is fail-closed:

- matching candidate + passing evidence → gate may `PASS`;
- matching candidate + absent evidence → gate is `NOT_TESTED`;
- matching candidate + disproving evidence → gate is `FAIL`;
- stale or mismatched candidate evidence → gate is `FAIL` for the current run
  unless explicitly archived outside the active proof packet.

This guard exists to prevent brittle false-green behavior: a checker must not
say the current implementation passes because an older commit produced valid
screenshots or reviewer outputs.

### Live Collaboration Ledger

For live site work, audits, amend loops, and disputed reviews, keep a compact
phase ledger visible to the human. If the human cannot tell where the agent is,
what is known, what is unknown, and what command comes next, the process is
anti-collaborative and the gate is `NOT_READY`.

Every status update and handoff must name:

`tier=<tier> lane=<lane> gate=<gate>:<status> artifact=<path> next=<command>`

Expand with facts, unknowns, blocker, and stop condition on handoff, blocker,
tier change, or human status request. Do not make every normal update a nine-field
report if the compact stamp answers where the work is.

Only one lane may be primary at a time. If implementation, screenshot capture,
reviewer submission, and skill-contract repair all appear relevant, declare the
primary lane and freeze the others until that lane has an artifact or an explicit
blocker. Do not let a final proof packet, a design critique, a site patch, and a
tool-debug session run as one blended task.

### Lean Default Loop

The normal loop is small and visible:

1. Name the current tier, lane, and stop condition.
2. Capture or inspect section/component/page-state crops for the surface under
   discussion.
3. Ask one direct design question: what should change next, and why?
4. Apply the smallest repair that improves the brand-derived world without
   broad redesign.
5. Re-render the same crop set and report what changed, what remains untested,
   and whether escalation is needed.

Do not create dashboards, broad orchestration, multi-tab browser campaigns, web
review loops, or full G0-G20 proof packets before this loop has answered the immediate decision.
If the loop fails twice on the same blocker, preserve the two receipts and ask
for a reviewer or human decision instead of expanding the machinery.

Bind one deterministic local render command and one certification command per
project. Missing blind-rater output means certification is `NOT_TESTED`, not a
broken crop. Project lane examples live in `references/workflow-phases.md`.

### Phase Summary

Use the full phase detail only when it helps the current tier:
`references/workflow-phases.md`.

| Phase | Output | Stop condition |
| --- | --- | --- |
| 0 Goal/provenance | user job, primary object, source of truth | content or authority missing |
| 1 Brand material | evidence ledger | visual idea lacks source evidence |
| 2 Territories | three genuinely different directions | territories differ only by style |
| 3 Selection | chosen direction and rejected alternatives | no human selection for implementation |
| 4 Grammar | `visual-world-brief.yaml` | rules are vague or decorative |
| 5 Page story | beat sheet per page | page falls back to template sequence |
| 6 Browser build | rendered prototype | browser disproves the composition |
| 7 System | component rules and states | identity exists only on homepage |

### Phase 8 — Render the Stress Corpus

Render at minimum:

- 390 × 844;
- 768 × 1024;
- 1440 × 900;
- one extra-wide viewport;
- 200% text zoom;
- long headline and long-label fixtures;
- no-image or failed-image state;
- keyboard focus traversal;
- reduced-motion mode;
- low- and high-density pages.

Use real or claim-valid content, not lorem ipsum, for acceptance.

The stress corpus must be reviewable without panning through a tall page strip.
Do not use one full-page or whole-site screenshot as the evaluation unit.
Full-page captures are navigation/debug artifacts only. Acceptance evidence must
be split into section, component, or page-state screenshots, each cropped to the
evaluated surface and recorded in a manifest with route, selector or section id,
viewport, scroll state, fixture/state, dimensions, screenshot path, capture tool,
and what the crop is meant to prove. If a section exceeds a practical review
height, split it into ordered sub-crops. Raters receive those crops, or compact
contact sheets assembled from those crops, never a single unreadable full-site
image as primary evidence.

### Phase 9 — Run Adversarial Distinctiveness Tests

G11 is a composite gate, not a single vague reviewer verdict. Status reports and
receipts must expose these child states separately:

- `corpus_current` — the section/component/page-state crop manifest exists,
  hashes match, counts are nonzero, failures are zero, and rater inputs use
  reviewable crops/contact sheets instead of one whole-site image;
- `raters_recorded` — the pre-registered number of fresh usable rater records
  exists and every counted rater has preserved raw/parsed output;
- `thresholds_met` — logo-off, competitor-swap, cross-screen-family,
  generic-template, and leakage thresholds pass.

If the crop corpus is current but fresh raters are absent, G11 is `NOT_TESTED`
with next lane `rater_submission`. If the fresh rater set is complete and a
threshold fails, G11 is `FAIL`, not `NOT_TESTED`. Transport acknowledgements,
old browser tabs, previous-corpus rater results, and advisory reviewer responses
must never be counted as G11 rater evidence.

#### Default Reviewer Workflow

Default review is URL-first, crop-backed, and transport-neutral. Use
`references/review-url-transport.md`, `schemas/bespoke-review-bundle.schema.json`,
and `schemas/bespoke-review-transport.schema.json`.

The order is: local deterministic checks; current section/page-state crops;
hash-bound review bundle; verified immutable review URL; direct canonical
artifact/attachment fallback only when URL inspection is unsupported. A URL
preflight never counts as a rater. A counted rater must echo the expected
candidate fingerprint and unit IDs, preserve raw output, and answer the
registered G11 questions directly.

For `directional` and `release-risk`, zero external reviewers is the default
when local evidence answers the decision. For `formal-certification`, use one
compact review index URL per rater seat and apply registered sequential stopping.
Provider rate limits, stale tabs, upload failures, and login pages are
`reviewer_transport`, not design findings.

Run the registered G11 questions: logo-off recognition, competitor swap, motif
semantics, cross-screen family, reference leakage, and template residue. The full
formal threshold table lives in `references/formal-certification.md`.

### Phase 10 — Accessibility and Performance Gates

Run these only for `release-risk` or `formal-certification` tiers unless the
human asks specifically about accessibility or performance. The detailed checklist
lives in `references/workflow-phases.md`.

### Phase 11 — Emit the Proof Packet

Emit a proof packet only for `formal-certification` or when the human requests a
durable receipt. Receipt evidence must be current to the implementation it
claims; stale receipts make the affected gate `NOT_TESTED` or `FAIL`. Required
artifact detail lives in `references/workflow-phases.md`.

Run:

```bash
python scripts/validate_receipt.py path/to/bespoke-design-receipt.json
```

## Owltastic-Derived Principles, Not Owltastic Motifs

The source lesson is method, not motif: make the subject's own premise govern
words, type, imagery, composition, components, and responsive behavior. Detailed
evidence and transferable principles live in `references/owltastic-design-dna.md`.

## Misuse Guard

Reject these shortcuts:

- copying Owltastic's owl, night-sky, astronomy, vintage-engraving, warm-cream,
  dark-brown, chunky-serif, or framed-portfolio combination without independent
  brand evidence;
- asking for “the Owltastic style” as a substitute for a brief;
- treating a palette or font pairing as a complete visual world;
- producing three nearly identical territories;
- adding random squiggles, stars, gradients, grain, arches, stickers, or collages
  merely to signal “bespoke”;
- **imitation material** — CSS bevel/emboss, faux letterpress, faux foil, faux
  stamped-metal, or a gradient standing in for a produced texture/asset;
- using image generation to fabricate evidence or cultural specificity;
- hiding weak information architecture under decorative density;
- approving desktop beauty while mobile becomes a stacked residue;
- sending a whole website screenshot to a web LLM as the primary design-review
  artifact; use section/page-state crops with a manifest instead;
- claiming accessibility, performance, usability, originality, or shipped impact
  from screenshots alone;
- replacing all standard controls with novel interactions that reduce clarity.

## Acceptance Gate

Every required gate uses one of `PASS`, `FAIL`, `NOT_TESTED`, or `BLOCKED`.
`READY` is legal only in `formal-certification` tier when every required gate is
`PASS`. In `directional` and `release-risk` tiers, report a bounded decision and
the missing formal gates; do not block useful repair work on evidence that is not
needed for the current decision.

Formal certification details live in `references/formal-certification.md`. Keep
the main workflow lean; load that reference only when formal READY is actually
the current tier.

### Failure Classification

- `site_defect` — rendered source violates the visual-world contract; affected
  design gate is `FAIL`.
- `evidence_gap` — crops, receipts, raters, or hashes are missing/stale; affected
  gate is `NOT_TESTED`.
- `reviewer_transport` — rate limit, stale tab, upload, or context failure;
  reviewer lane is `BLOCKED`, design gate status is unchanged.
- `harness_defect` — validator, manifest, runner, or schema error; tooling lane
  is `BLOCKED`, design gate status is unchanged.

A transport or harness failure never becomes a design finding and never changes a
design gate in either direction.

## Review Output

Return:

```markdown
## Position
One sentence: what makes the work specific or generic.
## Evidence
Claim-by-claim observations tied to sources or rendered artifacts.
## Distinctive Grammar
The semantic premise and the non-color invariants that create the visual world.
## Genericity and Leakage Risks
What could be swapped, copied, or reduced to a trend.
## Acceptance
Gate statuses, failed tests, and exact artifact references.
## Uncertainties
What screenshots, research, browser behavior, or source material cannot prove.
## Next Slice
The smallest verifiable change that closes the highest-priority failed gate.
```

## Stop Conditions

Stop and report the blocker when:

- authoritative claims or content are unavailable;
- the three territories cannot be distinguished beyond surface styling;
- the human has not selected a territory but implementation is requested;
- a culturally specific motif lacks credible research or review;
- browser implementation disproves the approved composition and no narrow repair
  is authorized;
- required accessibility or performance evidence cannot be collected;
- blind evaluation inputs or outputs are missing;
- a request requires cloning a living designer's distinctive style rather than
  learning general methods.

## References

- `references/owltastic-design-dna.md`
- `references/visual-world-brief.yaml`
- `references/acceptance-tests.md`
- `references/workflow-phases.md`
- `references/formal-certification.md`
- `references/review-url-transport.md`
- `schemas/bespoke-design-receipt.schema.json`
- `schemas/bespoke-review-bundle.schema.json`
- `schemas/bespoke-review-transport.schema.json`
- `fixtures/`
