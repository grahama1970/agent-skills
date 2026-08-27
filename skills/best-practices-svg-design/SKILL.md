---
name: best-practices-svg-design
description: >
  Design guardrails for SVG cards, diagrams, and animated illustrations that
  ship on real surfaces (grahama.co project cards, READMEs, docs). Prevents
  over-designed diagram art in thumbnail slots: enforces one-idea-per-card,
  glance legibility at render size, bounded text budgets, template-first
  composition through /create-svg, and screenshot-verified acceptance. Use
  before designing, reviewing, or accepting any SVG card or animated SVG, and
  whenever a previous SVG was rejected as cluttered, dense, or confusing.
metadata:
  short-description: Anti-clutter guardrails for shipped SVG cards and diagrams
provides:
  - svg-design-guardrails
  - card-legibility-contract
composes:
  - create-svg
  - review-design
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-design
  - best-practices-bespoke-design
disciplines:
  - ui-design-engineering
  - engineering-standards
---

# Best Practices: SVG Design

Load this before authoring or accepting any SVG that ships on a card, README,
or doc surface. It exists because the documented failure mode is real:
over-designed diagram art crammed into a thumbnail slot, rejected by the human
as "dense, text-heavy, visually confusing" (grahama.co memory card, 2026-08).

## Core Rule

One card communicates ONE idea, legible in under 3 seconds at the size it
actually renders. Everything that does not serve that idea is deleted, not
shrunk.

## Hard Budgets (fail the design, not the reader)

| Budget | Limit |
|---|---|
| Distinct ideas per card | 1 (a pipeline IS one idea; a pipeline + evidence model + decision matrix is three) |
| Text elements | <= 12 total; no paragraph-length sentences inside the graphic |
| Words per label | <= 4; captions <= 8 |
| Visual layers (bg, structure, accent) | 3 |
| Accent colors | <= 4, each carrying a distinct meaning |
| Font sizes | <= 4 distinct sizes |
| Animation | one synchronized cycle; motion explains flow order, never decorates |

## Process Rules

1. **State the one idea in a sentence before drawing.** For a project card:
   what is the project's crucial differentiator? Draw that, nothing else.
   (Memory example: "every query exits through one bounded route" — not the
   storage architecture, not the evidence model, not the decision rubric.)
2. **Template-first.** Compose through `/create-svg` scene templates
   (`fanout-anatomy`, `positive-negative`, ...) instead of hand-authoring
   freeform SVG. Bounded templates structurally prevent clutter; hand-drawn
   1920x1080 collages invite it. Extend the template library rather than
   bypassing it.
3. **Design at render size.** A card slot showing at ~400px wide must be
   judged in a screenshot at ~400px wide. If a label is unreadable there, the
   label goes, or the card's viewBox/typography changes.
4. **Screenshot inspection is mandatory acceptance evidence.** Base state
   (reduced-motion) plus at least one mid-cycle frame. DOM assertions, XML
   validation, and build passes are not visual proof.
5. **README-grade floor always.** No JS, self-contained, complete composition
   as base state, animation only under
   `@media (prefers-reduced-motion: no-preference)`. `/create-svg verify
   --receipt` must PASS before the artifact is presented.
6. **Rejection means subtraction.** When a human rejects an SVG as cluttered,
   the fix is fewer elements and a narrower idea — never rearranging the same
   density.

## Review Checklist (run before showing the human)

- [ ] The one idea is stated and everything on the card serves it.
- [ ] All hard budgets above hold.
- [ ] Screenshot at true render size read back and inspected this turn.
- [ ] Reduced-motion base state shows the complete composition.
- [ ] `/create-svg` verify receipt is PASS with zero findings.
- [ ] Palette/typography match the destination surface's theme tokens.

## Bespoke and Accessibility Rules (externally grounded)

Per `best-practices-bespoke-design`: template-first STRUCTURE is mandatory, but
template LOOK is not. A shipped card must read as authored for its brand —
derive palette, typography, and accent meaning from the destination site's
tokens (or a theme YAML extracted from them), never ship a bundled demo theme
onto a brand surface without an explicit palette decision. A card that could be
swapped onto any other project's site unchanged fails the specificity test.

Accessibility floor (sources: a11y-collective.com/blog/svg-accessibility,
mgifford/ACCESSIBILITY.md SVG best practices, deque.com/blog/creating-accessible-svgs,
accessibility.perpendicularangel.com):

- `role="img"` plus exactly one `<title>` and one `<desc>` (enforced by
  `/create-svg validate`).
- Essential labels stay as real `<text>` with sufficient contrast; never
  outline essential text to paths or hide it with font-size 0 / transparency.
- Paint an explicit background behind important content so Windows High
  Contrast Mode cannot silently change the ground under the labels.
- The design must remain recognizable across render sizes; whitespace is part
  of the composition, not leftover space.
- Animated variants keep the complete composition as the reduced-motion base
  state and never gate meaning behind motion or interaction.

## External / AI-Contributed SVG Intake

When a human or external reviewer (WebGPT, another agent) supplies a candidate
SVG, treat it as a design proposal to ADOPT AND HARDEN, not a rival to your own
draft. Session-proven intake steps (grahama.co memory card, 2026-08):

1. Render and screenshot it at full and slot size before judging it.
2. Run `/create-svg validate` — external SVGs typically fail `REDUCED_MOTION`
   because authors write motion-first CSS with a `reduce { animation: none }`
   override. The required pattern is no-motion-first (tatianamac.com/posts/
   prefers-reduced-motion, MDN prefers-reduced-motion): the static base state
   is the complete composition, and every `@keyframes` and `animation:`
   assignment lives inside `@media (prefers-reduced-motion: no-preference)`.
3. Re-tone to the destination brand tokens (bespoke rule) — palette swap only,
   never restructure a design the human chose.
4. Keep the human's structure. If your earlier draft loses, it loses.

## Domain Completeness (verify content against source truth)

A diagram of a system is a CLAIM about that system. Before accepting any
design — your own or an external contributor's — enumerate the domain's real
elements from source (routes, states, stages: grep the enums, endpoints, and
route emitters) and diff the diagram against that list. Adopting an external
design does not transfer responsibility for its accuracy: WebGPT's memory
card dropped the service's real DRAFT route and shipped that omission until
the human caught it. Every named element the human asked for appears, or its
exclusion is called out explicitly at handoff.

Copy is domain content too: name the pattern the way the PROJECT names it
(the memory card's headline is "Memory first." because the README calls it
the Memory First pattern). Clever wordplay that depends on the reader
guessing the subject ("Ask before you scan" — ask whom?) fails the
3-second test and misstates the architecture when read from the caller's
perspective.

## Text Containment (no label escapes its box)

- Every label must fit INSIDE its container with visible padding. Estimate
  before authoring: mono ≈ 0.62em/char, sans ≈ 0.5em/char, plus
  letter-spacing; if `label_px + gap + note_px > panel_width - 2*padding`,
  restructure — never let it ride.
- Inline name+note pairs on one baseline are the primary overflow source.
  Default to stacking: step line, name line, note line, each starting at the
  same left edge, panel height grown to fit.
- The mandatory screenshot inspection includes a containment sweep: check
  every label's right edge against its panel edge at full size. "Roughly
  fits" at authoring time is how "candidates" ended up outside the QDRANT
  panel.

## Type Scale Inside Nodes

A node's three text roles must be separable at a glance by BOTH size and
weight, not size alone: step/kicker (small, light, muted — e.g. 16px/620),
title (large, bold, bright — e.g. 31px/760), note (mid, regular, dim).
A kicker set at the title's weight ("01 · UNDERSTAND" competing with
"INTENT") flattens the hierarchy and reads as clutter. Uppercase mono at
equal weight is the usual culprit — drop the kicker two weight steps and
one opacity step below the title.

## Iconography and State Semantics

- **Micro-icons anchor nodes.** Pair each stage's kicker with a small inline
  glyph (12-45px) drawn from the card's own stroke/fill classes — a doc-lines
  glyph for lexical search, a node-mesh for graph traversal, a point cluster
  for vectors, a check ring for gates. Icons cut label-parsing time and give
  the eye a landing point; text shifts right to keep containment.
- **Encode cost/state boundaries in the border, not just color.** Outcomes
  that leave the cheap path (a live-execution fallback like SCAN FRESH) get a
  dashed border plus an explicit exit arrow; equivalent-cost outcomes share
  the solid treatment. A reader should see which pill is the expensive escape
  hatch without reading it.
- **Directional arrowheads on every flow connector** (`<marker>`); flow that
  is only implied by proximity fails the 3-second read. Accent the decisive
  edge (into the gate) with the brand's primary.
- In HTML surfaces (React cards), use the site's icon library (lucide-react
  here) instead of hand-drawn glyphs; in self-contained SVG artifacts, embed
  the glyphs inline — no external requests.
- Never adopt reviewer suggestions that cannot function in an `<img>` context
  (hover states, tooltips, transitions) — note them as skipped instead.

## Connector Craft

- Route connectors orthogonally (vertical/horizontal steps, rounded elbows
  allowed); never cut diagonally across whitespace between nodes.
- Marker `refX` must place the arrow TIP at the path end (tip-x == refX, e.g.
  path tip at 7 → refX 8 with ~1px optical inset), and the path must stop
  2-8px short of the target's stroke so the tip rests flush, never
  penetrating the border.
- Dock every connector on the target's exact geometric center (panel
  x + width/2), computed, not eyeballed — off-by-a-few-px anchors read as
  sloppiness at full size.
- Triage external connector reviews against YOUR coordinates before editing:
  a reviewer critiquing their own mock's numbers can name flaws your card
  does not have. Verify each claimed flaw with the real geometry first.

## Slot Contract (read the CSS before authoring)

Before choosing a viewBox, read the destination slot's CSS: its
`aspect-ratio` and `object-fit`. Author the SVG at the slot's EXACT ratio.
With `object-fit: cover`, any ratio mismatch silently crops the edges of the
composition (a 16:9 card in a 16:10 slot loses ~10% of its width), which
reads as "cramped" even when the artwork itself is fine. grahama.co project
cards use `.shot { aspect-ratio: 16/10; object-fit: cover }` → author at
1920x1200. Fill freed space with layout (e.g. headline in a side column),
never with decoration. Balance vertical margins: each column's content block
centers on the canvas midline, and the tallest column keeps equal top/bottom
margins — asymmetric padding (110px above, 50px below) reads as drift even
when every element is individually placed.

## Screenshot Protocol (hard-won)

- Headless Chrome at t=0 captures fade-in animations at opacity 0: pass
  `--force-prefers-reduced-motion` for the base state, plus
  `--virtual-time-budget` for a mid-cycle frame.
- A window smaller than the viewBox screenshots a crop, not the card — wrap
  the SVG in an `<img style="width:...">` page or match window to aspect.
- After install, read back the SERVED bytes (curl + sha256 against source);
  static exports (`site/out`) and browser caches both serve stale art. A
  correct file on disk proves nothing about what the reader sees.

## Failure Recovery

| Symptom | Action |
|---|---|
| Human says cluttered/dense/confusing | Cut ideas to one, re-budget text, re-render; do not rearrange |
| Labels illegible at slot size | Delete labels or enlarge type; never shrink to fit more |
| Template does not fit the idea | Add a new bounded template to /create-svg; do not hand-author freeform |
| Motion feels decorative | Keep only enters/flows that explain order; delete pulses/glows first |
