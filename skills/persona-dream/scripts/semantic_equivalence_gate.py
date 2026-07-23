#!/usr/bin/env python3
"""GOAL_V5 Gate 0 — semantic-equivalence gate (the operator rule made mechanical).

Contract: a delivery text is EQUIVALENT to the approved answer iff the approved
answer's content-word sequence survives as an ordered subsequence, and every
extra token comes from the allowed delivery vocabulary (pause punctuation,
delivery preambles/connectives). Any change to propositions, named entities,
numbers, negation, modality, or commitment (hedges/intensifiers) is a VIOLATION.

Pure, deterministic, no network. Used to gate any future text-side phrasing
lever and the M-arm derivation path.
"""
from __future__ import annotations

import re
from typing import Any

SCHEMA = "persona_dream.semantic_equivalence_gate.v1"

# tokens a delivery rewrite may INSERT without changing meaning
ALLOWED_DELIVERY_TOKENS = {
    "okay", "alright", "so", "well", "now", "look", "listen",
    "let", "me", "be", "clear", "here", "it", "is", "right",
    "first", "then", "and", "also",
}
NEGATIONS = {"not", "no", "never", "none", "cannot", "cant", "wont", "dont",
             "doesnt", "didnt", "isnt", "arent", "wasnt", "werent", "nt"}
MODALS = {"must", "should", "might", "may", "could", "will", "would", "can",
          "shall", "ought", "need", "have"}
COMMITMENT = {"definitely", "certainly", "absolutely", "surely", "probably",
              "maybe", "perhaps", "possibly", "think", "believe", "guess",
              "know", "sure", "likely", "unlikely"}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower().replace("'", ""))


def check_equivalence(approved: str, delivery: str) -> dict[str, Any]:
    a, d = _tokens(approved), _tokens(delivery)
    violations: list[str] = []

    # numbers must match exactly (multiset)
    num = re.compile(r"^\d")
    if sorted(t for t in a if num.match(t)) != sorted(t for t in d if num.match(t)):
        violations.append("numbers_changed")

    # marked-class tokens must match as multisets (negation, modality, commitment)
    for name, vocab in (("negation", NEGATIONS), ("modality", MODALS),
                        ("commitment", COMMITMENT)):
        if sorted(t for t in a if t in vocab) != sorted(t for t in d if t in vocab):
            violations.append(f"{name}_changed")

    # approved token sequence must survive as an ordered subsequence of delivery
    it = iter(d)
    missing = [tok for tok in a if not any(x == tok for x in it)]
    if missing:
        violations.append(f"content_dropped_or_reordered:{','.join(missing[:5])}")

    # every extra delivery token must be allowed delivery vocabulary
    from collections import Counter
    extra = Counter(d) - Counter(a)
    illegal = sorted(t for t in extra if t not in ALLOWED_DELIVERY_TOKENS)
    if illegal:
        violations.append(f"illegal_insertions:{','.join(illegal[:5])}")

    return {"schema": SCHEMA, "equivalent": not violations,
            "violations": violations}
