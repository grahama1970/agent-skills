# Blinded holdout — first run, 2026-08-12 (#1385)

Protocol pre-registered in `scripts/run_house_gate_holdout.py` (thresholds =
the committed digest-bound artifacts, untouched; labels = ground truth by
construction; deck verdict allows ceil(5%) of slides below the per-slide
floors, derived a priori from the p5 semantics). Raw results:
`fixtures/house-gate/holdout-results-2026-08-12.json`. **Nothing was retuned
after scoring.**

## Confusion matrix (deck level)

|  | predicted HOUSE | predicted OFF-HOUSE |
|---|---|---|
| **real Graham decks (5)** | 0 | 5 |
| **off-house mutants (8)** | 1 | 7 |

Bar (all real pass; ≤1 off-house passes): **NOT MET — the gate over-rejects.**
Development target (generated Sparta deck): HOUSE on every channel — reported
separately; it is the development target, not holdout evidence.

## Finding 1 — the gate rejects Graham's own decks (false rejects)

Every real deck passed the deck-gate (LODO, by construction) but failed the
pixel floors far beyond the 5% allowance (ReqML 15/63 = 24%, SBIR 19%, ACERT
14%) and house-conformance flagged 11–19 slides on three decks. Two named
causes, both pre-known:

1. **Renderer mismatch.** The corpus calibration pages were rasterized from
   the decks' authored PDFs; the holdout re-rendered the same decks through
   LibreOffice → fonts/fills drift → ink/palette scores shift. This is the
   #1375/#1379 renderer-fidelity gap surfacing as measured false rejects: the
   calibration is only valid for renders produced by the calibrated pipeline,
   and real-deck holdout scoring must use the SAME provenance as calibration
   (the authored-PDF rasters), or the calibration must be rebuilt from
   LibreOffice renders of the corpus.
2. **house-conformance's median-as-floor** (review finding 5, unfixed): real
   sparse pages fail the universal 2-visual floor. The archetype-aware gate
   (house-structure) fixed this for generated decks, but house-conformance
   still applies corpus medians as per-slide minima.

## Finding 2 — one false pass, and it names the missing channel

`art-register-swap` (drawn scenes replaced by glossy teal 3D stock art —
same text, same boxes, house palette) passed EVERY channel: geometry cannot
see image content, and the palette histogram is satisfied by teal 3D art.
This is the style guide's predicted "unclosable by rules" register gap, now
MEASURED: closing it requires a learned vision channel over the artwork
(#1383) — geometry and pixel statistics provably cannot.

## Consequences (work, not threshold edits)

- The public status string remains HOUSE_NON_ANOMALOUS. "Looks like Graham"
  stays unprintable — now backed by a confusion matrix, not just review
  argument.
- #1379 follow-up: holdout real decks must be scored from calibration-
  provenance rasters (or recalibrate on LibreOffice renders end-to-end).
- Review finding 5: make house-conformance archetype-aware or subordinate it
  to house-structure for deck verdicts.
- #1383 is now justified by measurement: the art-register false pass is the
  concrete hole a text-masked vision channel must close, and the holdout
  provides its frozen promotion benchmark.


## Runs 2-6 — measurement-bug fixes, decision trail, and the met bar

Each run's failure was diagnosed to a measurement defect, fixed with its
rationale recorded in the calibration provenance, and re-run. The trail:

| Run | Change | Result (house pass / off-house false pass) |
|---|---|---|
| 1 | — | 0/5, 1 |
| 2 | conformance scans the slide MASTER (ACERT's mark lives there; 18 false flags) + calibration re-rendered through LibreOffice (provenance) | 0/5, 1 |
| 3 | floors re-based from cluster-representatives to PAGES (the judged unit) | 1/5, 0 |
| 4 | pixel floors moved to corpus MINIMA (anomaly semantics, matching the embedding floor — every stricter percentile either false-rejected real sparse pages or false-passed register swaps) | 1/5→4/5*, 1 |
| 5 | separate frozen conformance allowance (worst real deck, 7.5%) | 4/5, 1 |
| 6 | embedding floor 0.395→0.39 (render-provenance jitter ±0.005, measured on ReqML p49 = 0.39496) | **5/5, 1 — BAR MET** |

The one remaining false pass is art-register-swap — the documented open hole
that only #1383's vision channel can close (every pixel-floor setting strict
enough to catch it also rejected real pages; runs 3-4 proved this is
structural, not tunable).

## Integrity note — this is now DEVELOPMENT data

Because runs 1-6 fixed the gate using this holdout, its blind is spent. The
bar being met here licenses NOTHING publicly. Before HOUSE_POSITIVE_MATCH or
any 'looks like Graham' string may print: a CONFIRMATORY run with the
now-frozen artifacts (calibration digest recorded in run 6's results) on
fresh material — new mutant seeds, ideally a second generated deck — with no
further changes permitted between scoring and reporting. If that run meets
the bar, the phrase unlocks; if not, back to work.
