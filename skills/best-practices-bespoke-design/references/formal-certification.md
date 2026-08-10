# Formal Certification Reference

Use this reference only for `formal-certification` tier, when the human asks for
`READY`, a final bespoke gate, or adversarial proof. Directional and release-risk
reviews should use the lean loop in `SKILL.md` and report missing formal gates
without trying to close them.

## Gate Semantics

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
| G15 Craft integrity | Every imperfection is real, authored, scanned, or produced, never simulated | Faked hand-drawn marks, random jitter, or distress on machine-output/evidence surfaces |
| G16 Type fidelity | Display face character matches the world | A face of different character, however polished |
| G17 Material fidelity | Element material matches the world it implies | CSS bevels, embossing, faked stamped-metal/chalk, or other imitation material |
| G18 Amend-loop integrity | Ordered finish-review ran; applier is not the reviewer | One agent both found and applied a fix; no finish-review report |
| G19 World persistence | `DESIGN.md` or `PRODUCT.md` lets a re-run extend the world | A re-run restarts the world instead of extending it |
| G20 Asset provenance | Every raster/vector carries source, method, and license | Missing provenance, or generated art standing in as evidence |

## Precedence

Open G16/G17 or missing-signature-element contradictions outrank polish items.
A finish review that leads with craft nits while a type/material contradiction is
open is itself a `FAIL`. Re-run G9 and G10 after asset production because real
material is the standard regression path.

For multi-project distinctness, unlabeled screens from sibling projects go to
raters against both briefs. Fail below threshold, or if two projects share three
or more of: display-face character, palette anchor and field, motif family,
composition model, chrome pattern. Freeze a hashed direction contract before the
amend loop and declare protected invariants.

Distinctiveness is monotonic: re-run logo-off and competitor-swap on the
post-finish artifact. Any drop in recognition or rise in swap plausibility fails,
regardless of craft scores.

## AI-Generated Template Residue

Surface tells such as palette, monospace, and rounded boxes are weak evidence.
Load-bearing tells are structural: uniform chrome, identical card grids, one
global type setting, and monospace on human labels. Rank structural
distinctiveness above decoration, and never ship simulated craft. Full guidance:
`ai-template-residue.md`.

## Amend Loop

This skill owns direction; `$impeccable` owns finish. The loop is:

```text
direction contract -> build / render -> finish-review
-> apply fixes -> produce real assets -> re-render -> re-review -> document
```

Roles:

- `impeccable-finish-reviewer`: fresh eyes on the rendered artifact return an
  ordered list of material fixes. Reviewer does not edit.
- `impeccable-manual-edit-applier`: parent applies fixes. Reviewer never edits
  its own findings.
- `impeccable-asset-producer`: real raster/vector assets are produced from
  approved references. Never generate imagery to fake authenticity or evidence.
- `impeccable-documenter`: persist the built world in `DESIGN.md` or
  `PRODUCT.md` so a re-run extends it.

Do not hand-simulate a creator/reviewer loop. When formal certification is
required, compile it as a `$tau` creator-reviewer DAG with receipts.

## Direction Guard

Before the amend loop runs, and at every re-review, this skill must hold that the
world is opinionated and brand-derived, not a comp swapped in for polish.

- G2/G11 competitor-swap is the guard. If the brand name, nouns, and logo could
  be swapped for a competitor and the composition still feels equally plausible,
  reject the world however polished it is.
- The direction must trace to the brand's own evidence and premise and make
  choices a generic polish pass would not.
- Finish must sharpen that opinion with real materials, type fidelity, and real
  assets. A re-review that makes the page more generic fails G6/G11 even if craft
  scores rise.

For grahama.co and SPARTA Explorer specifically: the goal is a distinct,
opinionated world for each, not two projects converging on the same polished
dark-editorial template.
