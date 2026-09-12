#!/usr/bin/env python3
"""Deterministic canon-entity vetting for persona-dream scene/story text.

Observed 2026-09-12 (human-caught): the human idea text "Zeitch Eye" flowed
uncorrected through storyboard, Kling prompts, journal, and the Horus/Embry
conversation. The canon entity is Tzeentch (Warhammer 40K, the Changer of
Ways; "Eye of Tzeentch" for the watching-sky image). Canon fidelity is a
pipeline concern, not a post-hoc human catch: known misspellings are corrected
deterministically with a receipt, and ambiguous near-misses to canon names
fail closed with typed candidates instead of flowing into generated media.

The immutable Phase 01 human-idea artifact keeps the original wording; the
correction applies downstream to generated content, recorded in
canon_entity_corrections.json.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Verified Warhammer 40K canon names (operator-sourced 2026-09-12).
CANON_ENTITIES = {
    "tzeentch", "horus", "tyranids", "tyranid", "khorne", "nurgle", "slaanesh",
    "warmaster", "thousand sons", "lords of change", "kairos fateweaver",
}

# Persona/project vocabulary that is intentionally NOT Warhammer canon.
WHITELIST = {
    "embry", "horus", "sparta", "explorer", "evidence", "kling", "chatterbox",
    "warmaster",  # canon and whitelisted both fine
}

# Deterministic corrections seeded from the observed defect. Keyed lowercase,
# matched on word boundaries; longest key wins.
MISSPELLING_CORRECTIONS = {
    "zeitch eye": "Eye of Tzeentch",
    "zeitch": "Tzeentch",
}

NEAR_MISS_THRESHOLD = 0.70  # zeitch->tzeentch 0.714; persona-name noise ~0.15
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']{3,}")


@dataclass
class CanonResult:
    corrected: str
    corrections: list[dict[str, str]] = field(default_factory=list)
    ambiguous: list[dict[str, object]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.ambiguous


def _ratio(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def correct_canon_entities(text: str) -> CanonResult:
    """Correct known canon misspellings; flag ambiguous near-misses.

    Deterministic: same input, same output, no network, no model calls.
    """
    corrected = str(text or "")
    corrections: list[dict[str, str]] = []
    for wrong in sorted(MISSPELLING_CORRECTIONS, key=len, reverse=True):
        canon = MISSPELLING_CORRECTIONS[wrong]
        pattern = re.compile(re.escape(wrong), re.I)
        if pattern.search(corrected):
            corrected = pattern.sub(canon, corrected)
            corrections.append({"original": wrong, "corrected": canon, "entity": "Tzeentch" if "tzeentch" in canon.lower() else canon})

    canon_list = sorted(CANON_ENTITIES)
    ambiguous: list[dict[str, object]] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(corrected):
        token = match.group(0).lower()
        if token in seen:
            continue
        seen.add(token)
        if token in CANON_ENTITIES or token in WHITELIST:
            continue
        candidates = sorted(
            {c for c in canon_list if _ratio(token, c) >= NEAR_MISS_THRESHOLD}
        )
        if candidates:
            ambiguous.append({"token": match.group(0), "candidates": candidates})
    return CanonResult(corrected=corrected, corrections=corrections, ambiguous=ambiguous)


def blocked_response(result: CanonResult) -> dict[str, object]:
    """Typed fail-closed payload for the generate command."""
    return {
        "status": "blocked",
        "reason": "canon_entity_ambiguous",
        "required_step": "canon_entity_resolution",
        "detail": (
            "Scene text contains tokens that near-match Warhammer 40K canon "
            "entities but are not canon and have no deterministic correction. "
            "Fix the spelling explicitly; the pipeline will not guess."
        ),
        "ambiguous_entities": result.ambiguous,
        "schema": "persona_dream.canon_entity_gate.v1",
    }


def self_check() -> None:
    r = correct_canon_entities(
        "Tea on a void world with the Zeitch Eye and Tyranids behind."
    )
    assert "Eye of Tzeentch" in r.corrected and "Zeitch" not in r.corrected, r
    assert r.ok and len(r.corrections) == 1, r
    a = correct_canon_entities("The Tzenntch Eye watches.")
    assert not a.ok and a.ambiguous[0]["candidates"] == ["tzeentch"], a
    clean = correct_canon_entities("Embry and Horus discuss SPARTA Explorer.")
    assert clean.ok and not clean.corrections, clean


if __name__ == "__main__":
    self_check()
    print("CANON_ENTITIES_OK")
