"""Two-stage matching policy: rough candidates, then a filter that can say no.

Scope, because it decides every threshold below: this skill establishes
NEAR-EXACT IDENTITY for compliance use. A control ID may never be approximated —
answering CWE-32 for CWE-23 is not a helpful correction, it is a different
weakness asserted with confidence. Semantic judgement about whether an entity is
the one a sentence meant belongs downstream in the /memory pipeline (intent ->
recall -> /create-evidence-case), which grounds a CAE verdict in crosswalk edges
and deterministic gates. Precision over recall here is the requirement.

Stage 1 (Flashtext, trie): rough candidates via `max_cost`. This is only
possible since the dependency moved to upstream flashtext -- PyPI 2.7 has no
`max_cost` and is exact-only, which is why the previous design could not be
rough-then-filter and used a full-dictionary RapidFuzz scan as a fallback
instead. Trie matching is O(text); the scan was O(dictionary), 11.6s per miss
against 391k entities.

Stage 2 (this module): filter the few candidates. A filter that only ranks is
not a filter -- it must be able to reject everything.

The rule that matters, and the reason a single global threshold is wrong here:

    an edit on an IDENTIFIER produces a DIFFERENT REAL ENTITY
    an edit on a NAME produces the same entity, misspelled

Measured, not assumed:

    CWE-19 -> CWE-79 at ratio 83   Data Processing Errors vs XSS
    CWE-88 -> CWE-89 at ratio 83   Argument Injection vs SQL Injection
    T1004  -> T1003  at ratio 80   different technique
    "OS Credentail Dumping" -> "OS Credential Dumping"   correct recovery

So a fuzzy identifier match is not a near-miss to be helpfully corrected. It is
a confident substitution of one real weakness for another -- worse than
returning nothing, because the caller cannot tell it happened.

Ties are treated as refusal rather than a coin flip: CWE-88 scores 83 against
BOTH CWE-89 and CWE-78. Two candidates equally close is positive evidence that
the match is unsafe, not a ranking problem.
"""
from __future__ import annotations

from dataclasses import dataclass

# Identifier shape per framework, checked structurally rather than by pattern.
# The suffix rule differs by family and getting it wrong silently reclassifies an
# identifier as prose: requiring digits everywhere dropped D3FEND, whose ids are
# alphabetic (D3-ACA), onto the NAME path where fuzzy matching is permitted.
_ID_SHAPES: tuple[tuple[str, str], ...] = (
    ("cwe", "digits"),
    ("cve", "digits"),
    ("capec", "digits"),
    ("tid", "digits"),
    ("amlt", "digits"),
    ("amlm", "digits"),
    ("d3", "alpha"),
)


def normalise_identifier(token: str) -> str:
    """Reduce an identifier to the characters that carry its identity.

    Punctuation, spacing and case are presentation: CWE-23, CWE23 and "cwe 23"
    denote one weakness. The alphanumeric sequence is the identity, so it is kept
    verbatim -- which is what makes CWE-23 and CWE-32 distinguishable no matter
    how similar they score.
    """
    return "".join(c for c in token.lower() if c.isalnum())


def looks_like_identifier(token: str) -> bool:
    """True when a token is an entity ID rather than prose.

    Identifiers are the class where fuzzy matching is unsafe, so this decides
    which threshold applies. Deliberately structural: a prefix plus digits, or a
    bare technique id like T1003.
    """
    # Classify on the NORMALISED form, because the formatting variants this
    # policy exists to handle are exactly the ones that break prefix matching:
    # "CWE23" and "cwe 23" do not start with "cwe-", so checking the raw token
    # sent them down the NAME path -- where a fuzzy match could accept a
    # different weakness for them. The bench passed anyway, for the wrong reason.
    normalised = normalise_identifier(token)
    if not normalised:
        return False
    for stem, suffix_kind in _ID_SHAPES:
        if not normalised.startswith(stem):
            continue
        suffix = normalised[len(stem):]
        if not suffix:
            continue
        if suffix.isdigit() if suffix_kind == "digits" else suffix.isalpha():
            return True
    # ATT&CK technique/sub-technique: T followed by digits, optionally .NNN
    if normalised.startswith("t") and len(normalised) >= 5:
        return normalised[1:].isdigit()
    return False


# Stage two is the expensive stage and must only ever see stage one's shortlist.
# Flashtext's trie is O(text) and handles 391k+ entities happily; RapidFuzz is
# O(candidates) per mention and cost 11.6s per miss when it was pointed at the
# whole dictionary. Exceeding this means a caller has reintroduced a full scan,
# which is a performance regression that otherwise only shows up as "the batch
# is slow" hours later.
MAX_CANDIDATES = 64


class CandidateSetTooLarge(ValueError):
    """Stage two was handed a dictionary instead of a shortlist."""


@dataclass
class MatchDecision:
    accepted: bool
    keyword: str | None
    reason: str
    score: float | None = None
    runner_up: float | None = None


def filter_candidates(
    mention: str,
    candidates: list[tuple[str, float]],
    *,
    name_cutoff: float = 85.0,
    tie_margin: float = 5.0,
) -> MatchDecision:
    """Second-stage filter over stage-one's rough candidates.

    `candidates` is (keyword, score) already scored by RapidFuzz, best first.
    Returns a decision that may reject everything -- which is the point.
    """
    if len(candidates) > MAX_CANDIDATES:
        raise CandidateSetTooLarge(
            f"stage two received {len(candidates)} candidates (max {MAX_CANDIDATES}). "
            "RapidFuzz is the expensive stage and must only score Flashtext's "
            "shortlist; scoring the dictionary is what made a miss cost 11.6s."
        )
    if not candidates:
        return MatchDecision(False, None, "no_candidates")

    best_keyword, best_score = candidates[0]

    # Identifiers tolerate FORMATTING differences and nothing else.
    #
    # Fuzzy matching earns its place here for punctuation and case only:
    # "CWE-23", "CWE23", "cwe 23" are the same weakness written differently. But
    # the alphanumerics carry the identity, so if they differ AT ALL the entity
    # is different -- CWE-23 and CWE-32 are Relative Path Traversal and Improper
    # Symbolic Link Resolution, and no similarity score should ever bridge them.
    #
    # This is exact matching on the normalised form, not edit distance. An edit
    # distance rule would accept CWE-32 for CWE-23 at a high score, which is the
    # failure mode: a confident substitution the caller cannot detect.
    if looks_like_identifier(mention):
        normalised_mention = normalise_identifier(mention)
        for keyword, score in candidates:
            if normalise_identifier(keyword) == normalised_mention:
                return MatchDecision(True, keyword, "identifier_formatting_normalised", score)
        return MatchDecision(
            False, None,
            "identifier_alphanumerics_differ: punctuation and case may vary, the "
            "alphanumerics may not",
            best_score,
        )

    # Names may be misspelled, but an ambiguous best is not a match.
    if len(candidates) > 1:
        runner_up = candidates[1][1]
        if best_score - runner_up < tie_margin:
            return MatchDecision(
                False, None,
                "ambiguous: top candidates within the tie margin, so the match is "
                "unsafe rather than merely unranked",
                best_score, runner_up,
            )

    if best_score < name_cutoff:
        return MatchDecision(False, None, "below_name_cutoff", best_score)
    return MatchDecision(True, best_keyword, "name_fuzzy_accepted", best_score)
