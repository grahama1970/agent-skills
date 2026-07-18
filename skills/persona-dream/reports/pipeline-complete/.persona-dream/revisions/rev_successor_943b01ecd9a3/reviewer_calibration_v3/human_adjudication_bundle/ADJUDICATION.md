# Human adjudication bundle — reviewer calibration v3 (face-crop subgate)

Revision: `rev_successor_943b01ecd9a3` · run `pipeline-complete` · date 2026-07-18

## Why this bundle exists

The identity reviewer was augmented with a **mandatory face-crop identity subgate**
(zoom into each required face, crop candidate + multiple pose-matched reference
views, run a feature-level face-to-face comparison). Both the hardened full-frame
review AND the face-crop subgate must PASS for an identity PASS. This closed the
full-frame **dilution blind spot** for non-marginal cases.

After the maximum **3 subgate-prompt revisions**, calibration v3 still does **not**
cleanly PASS. The residual dispute is a single, genuinely subtle case:
`known_bad_sb_001` — a **near-look-alike**. It is not separable from the accepted
positive controls by `gpt-5.5` at face-crop scale, and the model's verdicts on
these borderline crops are **unstable run-to-run** (SAME / DIFFERENT / empty
verdict across identical inputs). This is the same case the v2 receipt already
flagged as requiring human adjudication.

Calibration v3 tallies (see `../reviewer_calibration_receipt.v3.json`):
- known-bad FAIL: **2/3** (`sb_002`, `sb_003` fail; **`sb_001` PASSes — CRITICAL**)
- positive controls PASS: **1/2** (unstable; `sb_002` Kai returned an empty verdict)
- tamper FAIL: **1/1** (reference-grounding intact)

The subgate demonstrably works on grosser mismatches: under the strict first
prompt it correctly FAILED `sb_001` via the subgate (Embry judged "face appears
longer") — but the same strictness over-failed the genuine positives on surface
warmth/pose. No single prompt within the 3-revision budget separated the subtlest
near-look-alike from genuine matches without either missing it or over-rejecting
good frames.

## What to look at

- `dispute_01_embry_sb001_known_bad_vs_positive.png` — top row (red) = the
  **disputed** known_bad_sb_001 Embry candidate crop beside the three v3 reference
  poses (frontal / three-quarter / profile). Bottom row (green) = an **accepted**
  positive-control Embry candidate beside the same references, for boundary calibration.
- `dispute_02_kai_sb001_known_bad_vs_positive.png` — same layout for Kai.

All reference crops are cut from the accepted `embry_contact_sheet_v3`
(sha256:3ce40b3b…) and `kai_akana_character_sheet.png` (sha256:692cf37c…).

## The exact question per frame

**Q1 — Embry, known_bad_sb_001 (dispute_01):** Is the red-row candidate a
*different specific woman* than the reference (recorded ground truth: cooler/paler,
narrower/longer face than the warm-olive, fuller-oval reference), or is she an
acceptable identity match? Compare bone width-to-length at the matched
three-quarter pose against the green-row accepted candidate.
- If **DIFFERENT** → `sb_001` is correctly known-bad; the subgate needs a signal
  or model it currently lacks (or a second reviewer / higher-resolution crop).
- If **acceptable match** → the recorded ground truth for `sb_001` is too strict
  and the case should be reclassified; calibration would then pass at 2/2 known-bad
  that are genuinely different.

**Q2 — Kai, known_bad_sb_001 (dispute_02):** Same question for Kai. Is the red-row
Kai a different man than the reference, or an acceptable match?

**Q3 — reviewer stability:** On `positive_control_sb_002` the subgate returned an
**empty verdict** for Kai on a clearly-visible face (a model refusal, not a
mismatch). Should borderline face-crop comparisons require **N-of-M agreement**
(e.g. best-of-3) or a **second independent reviewer** before a FAIL is trusted?

## Decision routing

- Any **DIFFERENT** verdict on Q1/Q2 → keep the rung blocked; add a second
  stricter reviewer or higher-resolution crops for the subtlest tier, then re-run
  calibration.
- **Acceptable match** on both → reclassify `sb_001` ground truth, re-run
  calibration (expected PASS), then proceed to the 8-frame augmented re-review,
  lane C, and rung restoration.
- Persistent instability (Q3) → adopt best-of-3 agreement in the subgate before
  any rung is certified.
