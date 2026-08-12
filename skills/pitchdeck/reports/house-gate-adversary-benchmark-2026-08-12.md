# House-gate adversary benchmark — 2026-08-12 (#1380)

Source deck: the north-star eval's passing 15-slide Sparta Explorer deck.
Mutants built by `scripts/build_house_gate_adversaries.py` (seed 7,
deterministic), rendered through the calibrated 50-dpi profile with per-mutant
render receipts, scored against the frozen `fixtures/house-gate/calibration.v1.json`
(digest 9727e608…).

| Mutant | Breaks | house-conformance | house-similarity | Honest reading |
|---|---|---|---|---|
| bbox-shuffle | layout (with overlaps) | PASS 0 findings | FAIL 9/15 | Rejected for the WRONG reason: stacked shapes reduced ink below floor. Side effect, not detection. |
| typography-swap | type hierarchy | PASS 0 findings | FAIL 2/15 | Two slides tripped ink only; 13/15 ransom-note slides passed every channel. |
| two-tiny-visuals | visual substance | PASS 0 findings | FAIL 15/15 | Ink floor caught the stripped art — the one mutant genuinely covered. |
| **layout-mirror** | composition/reading order | **PASS 0 findings** | FAIL 1/15 | **The reproduced hole: ink, palette, words exactly preserved; 14/15 fully mirrored slides pass every channel.** The single failure is a 0.013 wobble on the text-dominated embedding — luck, not detection. |

## Verdict

The review's central claim is CONFIRMED: the v2 gate is spatially blind.
A deck whose every slide is horizontally mirrored — chevrons on the wrong
side, art in the wrong corner, marks displaced, reading order reversed —
clears house-conformance completely and clears the style channels on 14 of
15 slides. Only #1381 (archetype-conditioned structural distance over role
bboxes) can close this class; ink/palette floors cannot, by construction.

typography-swap is a second open hole (13/15 pass): no channel reads fonts,
sizes, alignment, or emphasis. Also #1381's territory (typography
distributions from the OOXML).

Reproduce:
```bash
uv run python scripts/build_house_gate_adversaries.py \
  --source-pptx <passing-deck.pptx> --output-dir /tmp/pd-adversaries
# render each mutant at 50 dpi, write receipt, then:
./run.sh house-similarity --slides-dir /tmp/pd-adversaries/<mutant> --glob "s*.png" \
  --calibration fixtures/house-gate/calibration.v1.json \
  --render-receipt /tmp/pd-adversaries/<mutant>/render-receipt.json \
  --pptx /tmp/pd-adversaries/<mutant>.pptx
```


## Update — same day, after #1381 landed

`house-structure` (archetype-conditioned role-region + typography + visual-
substance contracts on the delivered pptx, roles resolved via el:<id> from the
canonical document) now runs as its own eval stage. Re-benchmark:

| Mutant | house-structure |
|---|---|
| layout-mirror | **FINDINGS 28** (chevrons right-anchored, marks displaced, divider heading off-center) |
| typography-swap | **FINDINGS 15** (sizes outside per-role house ranges, >12pt intra-role spread) |
| two-tiny-visuals | **FINDINGS 7** (visual AREA floors per archetype — count without area is not substance) |
| bbox-shuffle | **FINDINGS 15** |
| honest deck | **PASS 0** |

Every seeded mutant is rejected while the honest deck stays clean — #1380's
second acceptance criterion is met for the current mutant set. Sparse
archetypes (divider/toc/close) carry no area floor, so they are not pressured
toward filler art. Remaining mutants (palette-matched card grid, art-register
swap, arc-shuffle) still to build; deck-level bar is #1382.


## Update 2 — #1382 deck-level LODO bar + full coverage matrix

`house-deck-gate`: spatially-aware structural features (3x3 occupancy grid +
kind areas/counts/words) computed identically from the corpus records and the
delivered pptx; bar = the WORST held-out real deck under leave-one-deck-out
(median 0.1945 = RAES; folds: ACERT 0.0, CyberSummit 0.0 — cross-deck
duplicates — SBIR 0.0229, ReqML 0.103). The candidate deck is in no fold.

| Deck | house-structure | house-deck-gate | pixel floors | net |
|---|---|---|---|---|
| honest deck | PASS 0 | MATCH 0.117 ≤ 0.195 | PASS | **passes all** |
| layout-mirror | FAIL 28 | (passes — bbox features are role-blind) | (passes) | rejected |
| typography-swap | FAIL 15 | (passes — type is not geometry) | (2/15) | rejected |
| two-tiny-visuals | FAIL 7 | — | FAIL 15/15 | rejected |
| bbox-shuffle | FAIL 15 | — | FAIL 9/15 (side effect) | rejected |

Single channels keep known blind spots; the COMPOSITION catches every seeded
mutant while the honest deck passes every channel
(tests/test_house_deck_gate.py::test_composed_gate_catches_every_mutant pins
this). The honest deck's DECK_STRUCTURAL_MATCH is the first calibrated
POSITIVE deck-level evidence — still not the blinded-holdout validation
(#1385) required to print 'looks like Graham'.
