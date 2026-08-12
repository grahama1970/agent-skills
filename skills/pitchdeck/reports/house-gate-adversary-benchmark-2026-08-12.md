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
