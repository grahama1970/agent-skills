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
runtime_self_improvement: none
disciplines:
  - engineering-standards
  - ui-design-engineering
  - content-creation
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

### Live Collaboration Ledger

For live site work, audits, amend loops, and disputed reviews, keep a compact
phase ledger visible to the human. If the human cannot tell where the agent is,
what is known, what is unknown, and what command comes next, the process is
anti-collaborative and the gate is `NOT_READY`.

Every status update and handoff must name:

- active phase and gate;
- current artifact path or source file;
- last command run and concrete result;
- facts established locally;
- unknowns and `NOT_TESTED` items;
- current blocker, if any;
- next deterministic command;
- stop condition for the current lane.

Only one lane may be primary at a time. If implementation, screenshot capture,
reviewer submission, and skill-contract repair all appear relevant, declare the
primary lane and freeze the others until that lane has an artifact or an explicit
blocker. Do not let a final proof packet, a design critique, a site patch, and a
tool-debug session run as one blended task.

### Phase 0 — Goal and Provenance Lock

1. State the user job, primary object, primary decision, and source of truth.
2. Freeze the evidence bundle or record exact source versions.
3. Separate facts, stakeholder preferences, designer hypotheses, and references.
4. Define what must remain editable and what may be rasterized.
5. Pre-register required gates and rater thresholds.

Stop if the goal or authoritative content is unavailable.

### Phase 1 — Extract the Brand's Own Material

Build the evidence ledger and identify:

- repeated nouns, verbs, metaphors, and contrasts;
- origin stories and credible cultural context;
- audience language from interviews, support, sales, or research;
- product mechanics that can become structural metaphors;
- tensions competitors flatten or ignore;
- claims that should remain visually quiet because they require careful reading.

Prefer first-party language and observed behavior over trend references.

### Phase 2 — Create Three Genuine Territories

Produce three concept territories that differ in all of these dimensions:

- semantic premise;
- emotional posture;
- typographic voice;
- composition model;
- image or illustration logic;
- primary motif;
- interaction or motion behavior.

Three palettes applied to the same wireframe count as one territory.

For each territory, supply:

- premise sentence;
- evidence mappings;
- a hero, an interior content section, and a transactional/dense section;
- one mobile composition;
- risks, exclusions, and implementation cost;
- the reason this territory belongs to this brand rather than the designer.

### Phase 3 — Select by Fit, Not Prettiness

Use a must-pass matrix. A territory is inadmissible if it fails any of:

- claim and audience fit;
- content hierarchy;
- semantic distinctiveness from competitors;
- ability to scale beyond one composition;
- accessibility feasibility;
- responsive feasibility;
- implementation/editability feasibility.

After must-pass checks, the human may choose based on taste. Preserve the human's
named decision and the rejected alternatives.

### Phase 4 — Write the Grammar Before Expanding Screens

Create the visual-world brief using `references/visual-world-brief.yaml`.
Specify a small number of strong rules and explicit exclusions. Include a
“controlled abundance map” that marks where visual richness is allowed and where
reading or task completion must remain calm.

### Phase 5 — Compose the Page as a Story

For every page, write a beat sheet before polishing:

1. orientation;
2. tension or question;
3. explanation;
4. proof;
5. consequence;
6. next action.

Vary the sequence when the user job requires it. Do not force every page into a
hero / three cards / logo strip / CTA template.

### Phase 6 — Build in the Browser Early

Prototype the selected territory in the target rendering environment before
high-fidelity approval. Test real type wrapping, real content density, interaction,
scroll rhythm, image loading, and breakpoint behavior.

A flat mockup may approve direction. It cannot prove responsive composition,
focus behavior, motion, text reflow, or implementation fidelity.

### Phase 7 — Systemize Without Genericizing

For each component, record:

- semantic purpose;
- content constraints;
- identity-bearing rules;
- variants and states;
- responsive transformation;
- accessibility behavior;
- examples where the component must not be used.

Reject components that exist only because a generic design system normally has
them. Add components when real content or user jobs require them.

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

The stress corpus must be reviewable by a web LLM or human without panning
through a tall page strip. Do not use one full-page or whole-site screenshot as
the evaluation unit. Full-page captures are navigation/debug artifacts only.
Acceptance evidence must be split into section, component, or page-state
screenshots, each cropped to the evaluated surface and recorded in a manifest
with route, selector or section id, viewport, scroll state, fixture/state,
dimensions, screenshot path, capture tool, and what the crop is meant to prove.
If a section exceeds a practical review height, split it into ordered sub-crops.
Raters receive those crops, or contact sheets assembled from those crops, never a
single unreadable full-site image as primary evidence.

### Phase 9 — Run Adversarial Distinctiveness Tests

#### A. Logo-Off Recognition

Remove brand name and logo. Fresh-context raters receive the target brief and at
least three same-category decoy briefs. They match unlabeled screens to briefs and
explain the evidence. Pre-register the threshold; default is at least 80% correct
across five raters and three representative screens.

#### B. Competitor Swap

Replace the visible name, logo, and key nouns with a close competitor. If the
composition, metaphors, and component behavior still feel equally plausible, the
design is generic and fails.

#### C. Motif Semantics

List every repeated decorative or structural motif. Each must have a documented
meaning or job. Remove unsupported motifs.

#### D. Cross-Screen Family

Review three dissimilar page types without logo or shared hero art. Raters must
recognize one system through at least three non-color invariants.

#### E. Reference Leakage

Compare against all inspiration references. Fail if the candidate reproduces a
reference's distinctive combination of subject, layout, type treatment, palette,
illustration, or copy rather than transforming underlying principles.

#### F. Template Residue

Identify structures that arrived from a starter kit or trend rather than the
brief. Every retained generic pattern must earn its place through usability,
content, or implementation need and must be integrated into the selected grammar.

### Phase 10 — Accessibility and Performance Gates

Require at minimum:

- WCAG 2.2 AA review, including visible and unobscured keyboard focus, target size,
  contrast, semantics, text resize/reflow, and alternatives for non-text content;
- keyboard completion of all actions;
- a reduced-motion path that removes or replaces non-essential motion;
- field or representative performance evidence for LCP, INP, and CLS;
- no identity-critical information conveyed by color, animation, texture, or
  position alone.

Do not claim a reference site or candidate passes these gates without testing it.

### Phase 11 — Emit the Proof Packet

Required artifacts:

- `evidence-ledger.yaml`;
- `visual-world-brief.yaml`;
- three territory boards and selection record;
- component and page inventory;
- section/page-state screenshot manifest with route, selector or section id,
  viewport, state, content fixture, dimensions, crop paths, and capture tool;
- accessibility and performance receipts;
- blind-rater inputs and raw outputs;
- `bespoke-design-receipt.json` validated against
  `schemas/bespoke-design-receipt.schema.json`;
- exact source revision and implementation revision.

Run:

```bash
python scripts/validate_receipt.py path/to/bespoke-design-receipt.json
```

## Owltastic-Derived Principles, Not Owltastic Motifs

1. **Make identity verbal and visual at once.** The strongest concept joins copy,
   imagery, and composition rather than adding decoration after the headline.
2. **Treat personality as a design input.** Explore contrasting personalities when
   the client cannot yet articulate one.
3. **Use typography as character and structure.** Display type creates posture;
   reading and utility type preserve usability.
4. **Let one meaningful motif recur at several scales.** It may shape backgrounds,
   crops, diagrams, components, and transitions without becoming wallpaper.
5. **Balance abundance with quiet reading lanes.** Rich edges, frames, collage, or
   illustration can coexist with calm text and task zones.
6. **Put discipline underneath play.** Grids, hierarchy, and reusable systems make
   expressive work legible and scalable.
7. **Give each subject a different world.** Range is evidence that the process is
   client-led rather than a single signature skin.
8. **Carry identity into components.** Cards, forms, quotes, navigation, and states
   should express the grammar, not merely inherit brand colors.
9. **Use code as a design instrument.** Browser prototypes expose false assumptions
   about wrapping, rhythm, responsiveness, and interaction.
10. **Keep the human voice.** Personal, precise language and a visible point of view
    can make a polished site feel inhabited rather than manufactured.

Detailed evidence and project observations are in
`references/owltastic-design-dna.md`.

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
`READY` is legal only when every required gate is `PASS`.

| Gate | Must prove | Automatic failure |
| --- | --- | --- |
| G0 Provenance | Exact sources and revisions are recorded | Missing or invented claims |
| G1 User and content fit | Real jobs and real content shape hierarchy | Lorem-ipsum approval |
| G2 Territory separation | Three semantically distinct directions | Same wireframe with skins |
| G3 Narrative premise | One evidence-backed premise governs the system | Mood adjectives only |
| G4 Typographic system | Roles, hierarchy, wrapping, and fallbacks work | Display type harms reading |
| G5 Motif semantics | Every recurring motif has a meaning or job | Decorative residue |
| G6 Composition | Grid, focal hierarchy, rhythm, and intentional ruptures | Repeated template sections |
| G7 System depth | Identity survives pages, components, and states | Homepage-only identity |
| G8 Responsive choreography | Layout is recomposed, not merely shrunk/stacked | Mobile residue; single full-page screenshot used as responsive proof |
| G9 Accessibility | Required WCAG and interaction evidence passes | Prose-only claim |
| G10 Performance | Pre-registered field/representative targets pass | Unmeasured heavy spectacle |
| G11 Distinctiveness | Blind, swap, family, and leakage tests pass | Logo/color dependence; whole-site screenshot used as blind-rater input |
| G12 Implementation fidelity | Browser render matches approved grammar | Flat-mockup-only proof; full-page-only screenshot proof |
| G13 Editability | Human can change required content/primitives | Flattened critical UI |
| G14 Receipt integrity | Schema and artifact hashes validate | Missing or mutable evidence |
| G15 Craft integrity | Every imperfection is real (authored/scanned), never simulated | Faked hand-drawn marks, random jitter, or distress on machine-output/evidence surfaces |
| G16 Type fidelity (impeccable) | Display face character (compression, width, weight, contrast, terminals) matches the world | A face of different character — however well the layout matches |
| G17 Material fidelity (impeccable) | Element material matches the world it implies | Flat CSS/clean vector where painted/textured/dimensional/photographic material is implied; CSS bevels, embossing, faked stamped-metal/chalk — **imitation material is the single most reliable mark of machine-made design** |
| G18 Amend-loop integrity | An ordered finish-review ran; the applier ≠ the reviewer | One agent both found and applied a fix; no finish-review report |
| G19 World persistence | `DESIGN.md`/`PRODUCT.md` written so a re-run extends the world | A re-run restarts the world instead of extending it |
| G20 Asset provenance | Every raster/vector carries source + method ∈ {authored, scanned, photographed, licensed, synthetic-as-product} + license | An asset with no provenance, or generated art standing in as evidence |

**Precedence (impeccable):** an open G16/G17 or a missing-signature-element
contradiction outranks every polish item. A finish-review that leads with a craft
nit while a type/material contradiction is open is itself a `FAIL`. Re-run G9
(accessibility) and G10 (performance) after asset production — real material is
the standard regression path.

**Distinctness gate (multi-project):** when two projects share an owner, unlabeled
screens from both go to raters against both briefs; `FAIL` below threshold, or if
the two share ≥3 of {display-face character, palette anchor+field, motif family,
composition model, chrome pattern}. Freeze a hashed direction-contract before the
amend loop and declare `protected_invariants` (premise, motif family, type
character, composition model, the ≥3 component invariants); changing one without a
recorded amendment citing evidence/product-truth/accessibility/implementation is
an automatic `FAIL`. Distinctiveness is **monotonic**: re-run the logo-off and
competitor-swap on the post-finish artifact — any drop in recognition or rise in
swap-plausibility fails, regardless of craft scores.

## Amendment: AI-Generated-Template Residue

Surface tells (palette, mono, rounded boxes) are cheap and are NOT proof of
bespoke; the load-bearing tells are structural (uniform chrome, identical card
grids, one global type setting, mono-on-human-labels). Rank structural
distinctiveness above decoration, and never ship *simulated* craft (gate G15).
Full guidance: `references/ai-template-residue.md`.

## From audit to amendment — the amend loop (composes with `$impeccable`)

This skill defines the standard; **executing the fixes is an amend loop**, adopted
from `$impeccable`. An audit that only reports gates is a broken design process —
the gates must drive edits until they pass. The loop:

```
direction contract → build / render → finish-review (ordered material fixes)
→ apply fixes → produce real assets → re-render → re-review → document
```

Roles (delegate to `$impeccable`'s agents; this skill supplies the gate rubric
they review against):

- **Finish review** (`impeccable-finish-reviewer`): fresh eyes on the rendered
  artifact return an **ordered list of material fixes**. Fidelity, **type**, and
  **material** outrank craft nits — a missing signature element or contradicted
  material outranks every polish point. The reviewer does not edit.
- **Apply** (`impeccable-manual-edit-applier`): the parent applies the fixes; the
  reviewer never edits its own findings.
- **Assets** (`impeccable-asset-producer`): real raster/vector assets are produced
  from approved references — **never generated to fake authenticity or evidence**
  (this is where concept-art-as-evidence gets replaced with real artifact
  portraits). Keep synthetic imagery only where it genuinely *is* the product.
- **Document** (`impeccable-documenter`): persist the built world (`DESIGN.md` /
  `PRODUCT.md`) so a re-run extends the world instead of restarting it.

Iterate the loop until every required gate is `PASS` (or `NOT_TESTED` with the
missing evidence named). Do not hand-simulate a creator/reviewer loop: compile it
as a `$tau` creator-reviewer DAG (creator applies fixes, reviewer returns
`VERDICT: PASS/FAIL` against these gates) and let `$tau` run it with receipts.

### Guard: opinionated world, not a polished template (bespoke-design owns this)

`$impeccable` optimizes *finish* against a chosen world and approved comp — which
means it can replace one templated design with another well-executed but generic
one. **This skill owns the direction; impeccable owns the finish.** Before the
amend loop runs, and at every re-review, bespoke-design's gates must hold that the
world is **opinionated and brand-derived**, not a comp swapped in for polish:

- **G2 / G11 competitor-swap is the guard.** If the brand name, nouns, and logo
  could be swapped for a competitor and the composition still feels equally
  plausible, the world is a template — reject it however impeccable the finish.
- The direction must be **traceable to the brand's own evidence and premise**
  (Phase 1 ledger), take a **specific point of view**, and make choices a generic
  polish pass would not (e.g. grahama.co's *claim→evidence→bounded-judgment*
  premise, monospace-as-machine-evidence, receipt/proof-boundary motif; SPARTA
  Explorer's governed-evidence-thread premise). An adaptation is legitimate only
  when it cites the evidence, product truth, or accessibility need that forced it.
- Impeccable's finish must **sharpen** that opinion (real materials, type
  fidelity, real assets), never sand it into house style. A re-review that makes
  the page more generic fails G6/G11 even if craft scores rise.

For grahama.co and SPARTA Explorer specifically: the goal is a distinct,
opinionated world each — not two projects converging on the same polished
dark-editorial template.

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

- `references/owltastic-design-dna.md` — detailed analysis and evidence basis.
- `references/visual-world-brief.yaml` — fillable art-direction contract.
- `references/acceptance-tests.md` — test procedures and receipt requirements.
- `schemas/bespoke-design-receipt.schema.json` — machine-readable receipt shape.
- `fixtures/` — positive and negative validation fixtures.
