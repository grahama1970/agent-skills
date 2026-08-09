# grahama.co Iterative Design Amendments R1

Status: first implementation slice plus next bounded amendments. Not a compliance receipt.

## Implemented Slice A1

**Receipt Proof Workshop roles**

- Target: `site/components/receipt-ticket.tsx`, `site/app/globals.css`
- Change: turn each visible receipt into a structural pilot with explicit `Claim`, `Evidence`, `Raw artifact`, `Does not prove`, and `Bounded judgment` roles.
- Why: the roundtable warned that receipt-paper skin and mono styling were not enough. The user should see the claim/evidence/boundary/judgment grammar without needing to read explanatory prose.
- Template-residue removed: global monospace receipt skin; unlabeled proof boundary; duplicated footer caption as decoration; global homepage `footer` styling leaking into a receipt judgment block; thick side-tab accent border on the search scout card flagged by Impeccable.
- Deterministic guard: `npm run verify:proof-pilot`
- Rendered proof: `/tmp/grahama-proof-pilot-desktop-v2.png`, `/tmp/grahama-proof-pilot-mobile-v2.png`, `/tmp/grahama-proof-pilot-geometry-v2.json`

## Implemented Slice A2b

**Type Direction Decision**

- Target: `site/app/globals.css`, `site/app/layout.tsx`, `site/public/fonts/`
- Change: replace the overused Fraunces display face with locally hosted Literata roman/italic variable cuts for the human claim and section-thesis register.
- Why: Impeccable flagged Fraunces as an overused AI-template font. Literata keeps an editorial, screen-native proof-workshop voice without carrying the Fraunces startup-hero signature.
- Template-residue removed: Fraunces font references, Fraunces-only `SOFT`/`WONK` variation axes, and unused Fraunces font assets.
- Deterministic guard: `npm run verify:type-direction`
- Still not proved by this slice: full G16 type fidelity, blind logo-off recognition, competitor-swap distinctiveness, performance, or accessibility.

## Next Amendments

### A2 About Proof Path Pilot

- Target: one About/method subsection only.
- Change: replace decorative chronology with a claim-to-artifact-to-boundary path. Each waypoint must carry an existing real artifact or an explicit missing-evidence break.
- Do not add: career-timeline ornament, graph canvas, route animation, or new claims.
- Proof: screenshot at 390, 768, 1440; deterministic check that every path connector has source and target ids.

### A2b Type Direction Decision

- Target: global display type, currently Fraunces.
- Change: run a type-fidelity pass against the Proof Workshop world before swapping fonts. Impeccable flags Fraunces as overused; do not blindly replace it until the new face is proven to preserve the site's evidence/editorial voice.
- Proof: type specimen at hero, receipt, dense matrix, and mobile; Impeccable detector rerun; `no_mono_on_human_labels` remains `PASS`.

### A3 Competence Matrix As Evidence Index

- Target: `site/components/competence-matrix.tsx`.
- Change: keep the matrix as a secondary evidence index, not the homepage's primary world. Add per-cell "evidence state" language and remove any score/rating feel.
- Do not add: dashboard cards, fake health, fake grades, or generic "skills cloud" treatment.
- Proof: source check that counts are labeled as counts, not ratings; screenshot of dense and narrow views.

### A4 Decorative Serial Removal By Replacement

- Target: only sections where a functional provenance role replaces the serial.
- Change: remove decorative section numbering/rules when the replacement hierarchy is in place: claim role, evidence locator, boundary, next action.
- Do not remove globally before replacement, because that can reduce orientation.
- Proof: grep for retired serials in the target section and screenshot confirming orientation remains visible.

### A5 Missing Evidence State

- Target: unavailable receipt branches and evidence-private cards.
- Change: make absence a visible break/boundary state using the same Proof Workshop grammar.
- Do not render unavailable evidence as a quiet caption or success-adjacent widget.
- Proof: fixture with one missing artifact and screenshot showing the break.

### A6 Impeccable Finish Review Input

- Target: frozen direction model.
- Change: hand Impeccable `visual-world-brief.r1.yaml`, A1 screenshots, and this amendment list as the comparison contract.
- Required reviewer checks: G16 type fidelity, G17 material fidelity, G18 amend-loop integrity.
- Stop condition: no claim of bespoke compliance until finish-review receipt and local rendered checks exist.
