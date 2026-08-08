# Bespoke Design Acceptance Tests

These tests separate a strong design story from verifiable evidence. Run them on
rendered artifacts and runnable browser behavior. A reviewer opinion may contribute
to a receipt, but it cannot replace missing artifacts.

## Status Vocabulary

Every test reports exactly one status:

- `PASS` — required evidence exists and satisfies the pre-registered criterion.
- `FAIL` — evidence exists and disproves or misses the criterion.
- `NOT_TESTED` — no valid test was run.
- `BLOCKED` — a named dependency prevents the test.

`READY` requires all required tests to be `PASS`.

## Test Inputs

Freeze before testing:

- source and implementation revisions;
- visual-world brief;
- candidate screen list;
- viewport/state fixture list;
- target brand brief and decoy briefs;
- rater count, assignment, and threshold;
- accessibility and performance targets;
- reference corpus used during design;
- any exceptions and the person authorizing them.

## T01 — Evidence Ledger Integrity

**Question:** Did the art direction originate in authoritative material?

Procedure:

1. Validate every visual-world claim has at least one source.
2. Classify the source as authoritative, supporting, or hypothesis.
3. Verify each visual implication is framed as a design decision, not new factual
   evidence.
4. Verify every prohibited inference is honored.
5. Hash or version the source bundle.

Pass evidence:

- ledger file;
- exact source locations;
- source bundle digest or immutable revision;
- zero unmarked invented claims.

Automatic fail:

- fabricated metrics, values, audience claims, awards, or cultural context;
- a reference image treated as proof of brand truth;
- mutable source material with no revision record.

## T02 — Territory Separation

**Question:** Are the directions genuinely different hypotheses?

Procedure:

1. Remove palette swatches and logos from all territory boards.
2. Compare premise, emotional posture, type, composition, imagery, motif, and
   motion.
3. Count dimensions that differ materially.
4. Ask fresh reviewers to describe each territory in one sentence.

Pass criterion:

- at least three territories;
- each has a different semantic premise;
- each differs materially in at least five of the seven required design dimensions;
- reviewers do not collapse two territories into the same description.

Automatic fail:

- one wireframe with alternate skins;
- identical image treatment and component grammar;
- differences that exist only in mood-board references.

## T03 — Narrative Premise Traceability

**Question:** Does one useful premise govern the selected world?

Procedure:

1. State the premise without design jargon.
2. Link it to source claims and the user job.
3. Trace it into at least one rule in each of type, palette, motif, imagery,
   composition, components, and voice.
4. Identify where the premise must stay quiet to protect reading or task completion.

Pass criterion:

- all seven channels have a non-forced trace;
- at least one explicit calm zone exists;
- the premise remains meaningful without naming a design trend.

Automatic fail:

- premise is only an aesthetic label;
- motif is literal but unrelated to the user job;
- rationale can apply unchanged to a close competitor.

## T04 — Logo-Off Brief Match

**Question:** Can people identify the intended brand world without its badge?

Preparation:

- three representative screens: orientation, dense/interior, transactional/state;
- remove brand name, logo, and unique product names;
- target brief plus at least three same-category decoy briefs;
- at least five fresh-context raters;
- randomized order and no designer explanation.

Procedure:

1. Each rater matches every screen to one brief.
2. Each rater gives two visible reasons.
3. Record raw answers before aggregation.
4. Reject reasons based only on palette or an obvious industry noun.

Default pass criterion:

- at least 80% correct across all assignments;
- at least four of five raters match the target on at least two of three screens;
- explanations cite at least three non-color invariants across the corpus.

Report confidence intervals or small-sample limitations. Do not call a five-rater
result universal user evidence.

## T05 — Competitor Swap

**Question:** Is the design structurally incompatible with a close competitor?

Procedure:

1. Choose a competitor with similar category, scale, and audience.
2. Replace visible brand name, logo, product name, and obvious proprietary nouns.
3. Preserve layout, imagery treatment, motif, and component behavior.
4. Ask reviewers whether the swapped screen feels equally plausible.
5. Record which elements create tension or remain generic.

Pass criterion:

- the swap creates visible conceptual conflict in at least three independent
  channels, such as metaphor, image logic, voice, hierarchy, or component behavior;
- conflict is not dependent solely on color or logo.

Automatic fail:

- reviewers consider the swapped version equally natural;
- the only mismatch is palette;
- removing one hero illustration makes the remainder generic.

## T06 — Motif Semantics

**Question:** Has every repeated expressive device earned its place?

Procedure:

1. Inventory recurring shapes, lines, textures, frames, crops, illustrations,
   transitions, and motion.
2. Map each to a source claim, narrative function, user cue, or system function.
3. Remove each motif in a controlled variant.
4. Compare comprehension, hierarchy, and identity.

Pass criterion:

- every motif has documented provenance or function;
- removing the primary motif weakens identity or narrative without improving task
  clarity;
- removing any supporting motif that changes nothing results in its deletion.

Automatic fail:

- “visual interest” is the only rationale;
- decorative devices obscure content or focus;
- motif use becomes inconsistent across page types.

## T07 — Cross-Screen Family

**Question:** Is there a system rather than a single beautiful screen?

Procedure:

1. Select three dissimilar page types.
2. Remove logos and normalize screenshot framing.
3. Ask reviewers to group screens by visual system.
4. Require them to cite evidence beyond color.

Pass criterion:

- target screens are grouped together by at least 80% of raters;
- at least three non-color invariants are visible;
- each page has a distinct composition appropriate to its content.

Automatic fail:

- pages match only because they repeat one card grid;
- interior and state screens lose all identity;
- every page has the same narrative rhythm.

## T08 — Controlled Abundance

**Question:** Is expressive density intentionally placed?

Procedure:

1. Mark expressive, transition, reading, and task zones.
2. Count simultaneous attention-seeking devices in each viewport.
3. Run a five-second orientation test and a focused task test.
4. Test at 200% text zoom and with long content.

Pass criterion:

- reading and task zones retain one clear focal path;
- expressive devices do not obscure controls, labels, proof, or text;
- zoom and long content do not push decoration into critical content;
- a reviewer can state the page purpose and next action after five seconds.

Automatic fail:

- all zones compete at equal intensity;
- decoration carries required meaning without alternatives;
- responsive stacking creates a wall of ornaments.

## T09 — Responsive Choreography

**Question:** Does the world adapt rather than collapse into stacked desktop blocks?

Procedure:

1. Render required viewports with identical real content.
2. Compare reading order, grouping, crop logic, headline wrapping, navigation,
   controls, and motif behavior.
3. Record intentional transformations at each breakpoint.
4. Test intermediate widths, not only named devices.
5. Test orientation change and 200% text zoom.

Pass criterion:

- every major transformation is documented;
- identity survives through at least three non-color invariants;
- no horizontal scrolling except intentional data regions with accessible handling;
- controls remain usable and content order remains logical;
- decorative assets simplify or move when necessary.

Automatic fail:

- mobile is only a one-column stack of desktop sections;
- key images crop subjects incorrectly;
- display type creates orphaned or unreadable wraps;
- fixed decoration overlaps content.

## T10 — Content Stress

**Question:** Does the design work with real and difficult content?

Required fixtures:

- shortest and longest real headline;
- long navigation label;
- long CTA label;
- dense prose;
- many and few cards;
- missing image;
- error and empty state;
- localization expansion where relevant;
- unusually large metric or code token where relevant.

Pass criterion:

- no clipping, collision, hidden action, or misleading truncation;
- hierarchy remains understandable;
- fallback states retain the visual grammar without pretending data exists.

## T11 — Accessibility

**Question:** Can people perceive and operate the experience across modalities?

At minimum test:

- semantic structure and landmarks;
- keyboard order and full action completion;
- visible focus and focus not obscured;
- text and non-text contrast;
- link and control recognition beyond color;
- target sizing and spacing;
- alt text and decorative-image handling;
- form labels, errors, instructions, and status announcements;
- heading order;
- zoom and reflow;
- screen-reader names/roles/states;
- dragging alternatives when dragging exists;
- reduced-motion behavior.

Pass criterion:

- the pre-registered WCAG 2.2 AA scope passes;
- automated tools have no unresolved serious issues;
- required manual keyboard and assistive-technology checks pass;
- exceptions are documented and do not support a `READY` claim unless the
  acceptance contract explicitly permits them.

Automated scans alone are insufficient.

## T12 — Motion Purpose and Reduction

**Question:** Does motion communicate rather than decorate compulsively?

Procedure:

1. Inventory every animation and transition.
2. State its purpose: orientation, continuity, feedback, emphasis, or atmosphere.
3. Test interruption, repeated exposure, and low-powered devices.
4. enable `prefers-reduced-motion: reduce` and compare task equivalence.

Pass criterion:

- every motion has a purpose;
- non-essential motion is removed, reduced, or replaced under user preference;
- no task or meaning depends solely on animation;
- no large-scale panning/scaling or autoplay spectacle remains without a safe path.

## T13 — Performance

**Question:** Does the crafted world remain responsive in real use?

Procedure:

1. Record page, route, device class, connection, build revision, and test method.
2. Prefer field data; supplement with repeatable lab runs.
3. Measure LCP, INP, and CLS.
4. Identify identity assets contributing to each metric.
5. Test image, font, script, animation, and third-party budgets.

Default good thresholds at the 75th percentile:

- LCP ≤ 2.5 seconds;
- INP ≤ 200 milliseconds;
- CLS ≤ 0.1.

Pass criterion:

- pre-registered targets pass for mobile and desktop scopes;
- critical identity survives any required optimization;
- decorative assets do not block primary content or interaction.

Do not claim field performance from one local Lighthouse run.

## T14 — Reference Leakage

**Question:** Did inspiration become copying?

Procedure:

1. Preserve the complete reference corpus used during design.
2. Compare candidate and reference on subject, composition, type treatment, palette,
   image treatment, motif, motion, and copy.
3. Look for distinctive combinations, not isolated commonplace elements.
4. Ask a fresh reviewer to identify the closest reference and explain why.
5. Run a variant with suspect elements removed or transformed.

Pass criterion:

- no reference supplies the same distinctive combination of major dimensions;
- rationale traces to the target brief rather than to admiration for the reference;
- a living designer's recognizable signature has not been requested or recreated.

Automatic fail:

- the candidate is described mainly by another designer's name;
- signature motifs, composition, type behavior, and palette travel together;
- changing the source brand story does not change the candidate direction.

## T15 — Implementation Fidelity

**Question:** Did the browser preserve the approved grammar?

Procedure:

1. Freeze approved keyframes and implementation revision.
2. Render identical content and viewports.
3. Compare typography, spacing, crops, layering, rhythm, states, and responsive
   transformations.
4. Inspect actual interaction, not only screenshot pixels.
5. Record authorized deltas and their rationale.

Pass criterion:

- required visual and behavioral invariants match;
- all deltas are approved and traceable;
- no implementation shortcut removes the distinctive grammar;
- no design-only element implies unavailable functionality.

## T16 — Editability and Ownership

**Question:** Can the human maintain the experience after delivery?

Procedure:

1. Identify every editable content and design primitive.
2. Change a headline, image, card count, CTA, and one palette token.
3. Re-render and verify no manual reconstruction is required.
4. Record asset licenses, generators, and source files.

Pass criterion:

- required content and components are native/editable;
- critical UI is not flattened into an image;
- generated decorative assets have provenance and reproducible parameters where
  required;
- ownership and license boundaries are explicit.

## T17 — Receipt Integrity

**Question:** Does the acceptance packet describe the artifacts truthfully?

Procedure:

1. Hash each required artifact.
2. Validate the JSON receipt against the schema and local validator.
3. Recompute artifact hashes independently.
4. Verify `READY` implies every required gate is `PASS`.
5. Verify raw rater outputs exist and aggregate counts can be replayed.

Pass criterion:

- schema validation succeeds;
- independent hashes match;
- no contradictory status fields;
- no required artifact is missing or mutable without a revision.

Run:

```bash
python scripts/validate_receipt.py path/to/bespoke-design-receipt.json
```
