# GOAL_V4 Amendment 1 — composer output vocabulary remapped onto chatterbox ALLOWED_TONES

Date: 2026-07-23. Authorized by operator directive: "proceed with: If you want
the tuning executed, the first concrete step is the amendment remapping the
composer's output vocabulary onto ALLOWED_TONES, then the n≥3
variance-calibrated rerun of the four-arm probe."

## Verified basis

`chatterbox/src/chatterbox/agent/presets.py` (read 2026-07-23):
- `ALLOWED_TONES` is a closed 15-tone vocabulary.
- `normalize_tone()` silently converts any other label to `neutral_warm`
  (neutral stage, default sampling params). Tone reaches sound only via
  tone -> delivery stage -> STAGE_PRESETS (temperature 0.70–0.90 etc.).
- Therefore most original V4.1 output labels (`gentle_firm`, `warm_direct`,
  `yearning_warm`, `hesitant_reflective`, ...) were acoustically inert.

## Amended frozen tables (V4.1)

All composer output tones (TAG_FAMILY_TONE values, TAG_FLOOR_TONE values,
MISSING_POLICY_TONE) must be members of chatterbox `ALLOWED_TONES`. Canonical
family assignments for the allowed tones are added to `EXPRESSIVE_FAMILY` so
the family gate ("composer never leaves the situational family") remains
well-defined and collision-free. The fail-closed missing-policy tone becomes
`memory_uncertain` (the best-practices-chatterbox-agent contract's suggested
default).

The fixture probe gains a vocabulary-compliance check that parses
`ALLOWED_TONES` from the chatterbox presets file on disk and asserts every
composer output tone is a member.

## Unchanged

Safety-override, expressive-family, dispositional-floor, unknown-passthrough,
thermal-limiter semantics; all V4.2/V4.3 gates; all forbidden-drift rules
(/intent and voice-render remain untouched).

## Rerun obligation

`run_four_arm_acoustic_probe.py` is amended to n>=3 renders per arm (default
5) with per-arm medians and spread, giving a same-parameter variance estimate
(flat vs wrong arms render with identical sampling params by design) against
which the dream arm's shift is judged.
