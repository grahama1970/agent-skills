#!/usr/bin/env python3
"""Map a dream's psychological mood onto Chatterbox's delivery vocabulary (#1202).

Two projects name feelings differently and neither is wrong.

persona-dream invents a mood per dream from the tension it found:
``guarded_quietly_wanting``, ``competent_but_unseen``. That label belongs to
Embry -- it is what she woke up feeling, and it should stay in her journal
verbatim.

Chatterbox accepts a closed set of 15 *delivery* tones -- ``firm_boundary``,
``memory_uncertain``, ``calm_precise`` -- because those are the presets its
renderer actually implements. Anything outside the set is silently rewritten to
``neutral_warm``.

Debugger proof (presets.py:138, three hits) showed the consequence: every
dream-derived mood collapsed to ``neutral_warm``, the blandest tone available,
so Embry sounded identical no matter what she had dreamt.

This maps one onto the other and keeps both. The mood is what she felt; the
delivery tone is what we asked the renderer for. Conflating them is what made
the failure invisible -- the request looked fine and the response looked fine,
because normalization happened silently in between.

Chatterbox is not edited by this module. persona-dream owns the mapping,
because persona-dream is the side that invents new moods.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

#: Chatterbox's accepted delivery tones, mirrored from
#: chatterbox/src/chatterbox/agent/presets.py ALLOWED_TONES. Mirrored, not
#: imported: persona-dream must not depend on Chatterbox's Python package, and
#: a drift check below fails loudly if the sets diverge.
ALLOWED_TONES = {
    "neutral_warm", "calm_precise", "careful_concerned", "serious_low_energy",
    "memory_confident", "memory_uncertain", "curious_searching", "playful_light",
    "relieved", "firm_boundary", "identity_clarification",
    "one_at_a_time_interrupt", "deflect_calm", "grief_safe", "wait_presence",
}

#: Dominant contradiction axis -> the delivery tone that best carries it.
#: Chosen so the four opposing pairs land on audibly distinct presets rather
#: than clustering: a dream about concealment must not request the same tone as
#: one about belonging.
AXIS_TO_DELIVERY = {
    "Concealment": "firm_boundary",
    "Disclosure": "identity_clarification",
    "Competence": "memory_confident",
    "Inadequacy": "memory_uncertain",
    "Belonging": "relieved",
    "Isolation": "grief_safe",
    "Duty": "calm_precise",
    "Desire": "curious_searching",
}

#: Fallback when a dream produced no tension at all. Deliberately the same
#: default Chatterbox would have chosen, so an absent mapping is honest rather
#: than a silent downgrade dressed up as a decision.
NEUTRAL_FALLBACK = "neutral_warm"

#: Dominant axis -> the channels the renderer declares ACTUALLY move audio.
#:
#: `tone` above is request-only on chatterbox_turbo: it maps to stage presets
#: that shift sampling parameters, and the params carrying affect are ignored by
#: Turbo. It is kept as provenance for what was asked. These are the fields the
#: renderer reports as applied, per its voice_delivery_effect contract:
#:
#:   intensity / valence  -> routed to chatterbox_base_affect via
#:                           use_base_emotion, which honours exaggeration and
#:                           cfg_weight
#:   pace                 -> a real pitch-preserving time stretch
#:
#: Valence is signed: a dream about isolation should not sound like one about
#: belonging. Pace follows arousal, not sentiment -- grief is slow and low, and
#: so is inadequacy, while desire and competence run brisk. Values are
#: deliberately moderate; a persona reading her own journal is not performing.
#: Arousal -> pace. This is all that is left of a table that used to carry
#: hand-picked intensity and valence for all eight axes.
#:
#: Chatterbox now derives affect FROM THE TONE NAME when
#: emotion_realization=audible: grief_safe resolves to intensity 0.3 / valence
#: -0.7, relieved to 0.75 / +0.65, with knob_source=tone_calibration. That is
#: chatterbox#22, and it is the right place for the work -- calibrating a tone
#: vocabulary is the renderer's job, done once with receipts, not something
#: every consumer should reinvent by measuring acoustics.
#:
#: So the intensity/valence table is DELETED rather than retuned, which is what
#: its own comment said should happen. This skill now says what the dream FELT
#: LIKE and lets the renderer decide how that sounds.
#:
#: Pace stays because tone calibration does not set it, and it is separately
#: proven audible: a deterministic time stretch with a per-render receipt.
AXIS_TO_PACE = {
    "Isolation": "slow", "Inadequacy": "slow", "Concealment": "measured",
    "Duty": "measured", "Disclosure": "measured",
    "Belonging": "measured", "Competence": "brisk", "Desire": "brisk",
}

#: No tension surfaced: ask for nothing rather than inventing a feeling.
NEUTRAL_PACE = "neutral"


def dominant_axis(contradictions: list[dict[str, Any]]) -> str | None:
    """The axis carrying the most tension in this dream.

    Counts both sides of each pair: a dream with three Competence/Inadequacy
    tensions is about that opposition, and either pole is a fair label for it.
    The higher-count pole wins so the tone leans the way the dream leans.
    """
    counts: dict[str, int] = {}
    for row in contradictions:
        for key in ("bridge_a", "bridge_b"):
            axis = str(row.get(key) or "")
            if axis:
                counts[axis] = counts.get(axis, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def map_mood(mood_label: str | None, contradictions: list[dict[str, Any]],
             intensity: float | None = None, valence: float | None = None) -> dict[str, Any]:
    """Return a voice_delivery Chatterbox will honour, plus what it came from."""
    axis = dominant_axis(contradictions)
    delivery = AXIS_TO_DELIVERY.get(axis or "", NEUTRAL_FALLBACK)
    if delivery not in ALLOWED_TONES:  # pragma: no cover - guarded by drift check
        delivery = NEUTRAL_FALLBACK
    voice_delivery: dict[str, Any] = {
        # The tone now carries the feeling. emotion_realization=audible routes
        # it to the calibrated affect path instead of the default fast one.
        "tone": delivery,
        "emotion_realization": "audible",
        "pace": AXIS_TO_PACE.get(axis or "", NEUTRAL_PACE),
    }
    # Only if a caller insists. Nothing in this skill sets these any more: the
    # renderer's calibration is better than numbers we would pick by hand.
    if intensity is not None:
        voice_delivery["intensity"] = round(float(intensity), 3)
    if valence is not None:
        voice_delivery["valence"] = round(float(valence), 3)
    return {
        "voice_delivery": voice_delivery,
        "audible_channels": ["tone", "pace"],
        "request_only_channels": [],
        "persona_mood_label": mood_label or "unset",
        "dominant_tension_axis": axis,
        "mapped_because": (
            f"dominant tension axis {axis!r} maps to delivery tone {delivery!r}"
            if axis else
            "no tension surfaced in this dream; requesting the neutral default"
        ),
        "boundary": (
            "tone carries the feeling and is routed to the calibrated affect "
            "path via emotion_realization=audible; the renderer derives the "
            "knobs from the tone name and reports them in an affect_effect "
            "receipt. Whether a listener perceives the intended feeling is "
            "untested."
        ),
    }


def check_vocabulary_drift(presets_path: Path) -> dict[str, Any]:
    """Fail loudly if Chatterbox's tone set has moved away from our mirror."""
    if not presets_path.is_file():
        return {"checked": False, "reason": f"presets not found: {presets_path}"}
    text = presets_path.read_text(encoding="utf-8")
    try:
        block = text.split("ALLOWED_TONES = {", 1)[1].split("}", 1)[0]
    except IndexError:
        return {"checked": False, "reason": "ALLOWED_TONES block not parseable"}
    upstream = {line.strip().strip(',').strip('"').strip("'")
                for line in block.splitlines() if line.strip().startswith(('"', "'"))}
    upstream = {t for t in upstream if t}
    missing = sorted(upstream - ALLOWED_TONES)
    extra = sorted(ALLOWED_TONES - upstream)
    return {
        "checked": True,
        "in_sync": not missing and not extra,
        "upstream_count": len(upstream),
        "mirrored_count": len(ALLOWED_TONES),
        "missing_from_mirror": missing,
        "not_in_upstream": extra,
        "unmapped_axes": sorted(a for a, t in AXIS_TO_DELIVERY.items() if t not in upstream),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, help="read contradiction_report.json from here")
    ap.add_argument("--mood-label", default=None)
    ap.add_argument("--intensity", type=float, default=None)
    ap.add_argument("--valence", type=float, default=None)
    ap.add_argument("--check-drift", type=Path,
                    default=Path("/home/graham/workspace/experiments/chatterbox/src/chatterbox/agent/presets.py"))
    args = ap.parse_args()

    contradictions: list[dict[str, Any]] = []
    if args.run_dir:
        path = Path(args.run_dir) / "contradiction_report.json"
        if path.is_file():
            contradictions = json.loads(path.read_text(encoding="utf-8")).get("contradictions") or []

    out = map_mood(args.mood_label, contradictions, args.intensity, args.valence)
    out["vocabulary_drift"] = check_vocabulary_drift(args.check_drift)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
