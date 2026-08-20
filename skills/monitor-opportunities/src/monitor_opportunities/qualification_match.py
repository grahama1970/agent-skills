"""Read a posting's stated qualifications and answer them from approved claims.

Graham's instruction (2026-08-17): when a posting — or LinkedIn's own match
panel — says a qualification is missing, the skill must ATTEMPT TO ADDRESS IT
if that is possible. "Possible" has exactly one meaning here: the approved claim
snapshot already carries evidence that answers the requirement, and the tailored
resume simply is not surfacing it. Anything the claim snapshot does not cover is
a real gap and is reported as one. This module never invents a qualification,
never softens a hard blocker, and never writes a claim.

Three dispositions per requirement:

- ``ANSWERABLE_FROM_APPROVED_CLAIM`` — an approved claim wording covers it. The
  claim_key and wording_id travel with the row so tailoring can surface exactly
  that approved wording. This is the "attempt to address it" path.
- ``NOT_EVIDENCED`` — nothing in the snapshot answers it. The human decides:
  propose a claim amendment (if it is true and merely unrecorded), or accept the
  gap. The skill does not decide for him and does not write the resume around it.
- ``HARD_BLOCKER`` — clearance, citizenship, a required degree, or mandatory
  relocation. These are eligibility facts, not presentation problems, and no
  amount of tailoring addresses them.

Requirement text comes from evidence already captured in
`discovery/candidates.jsonl` (`posting_text`, which holds the posting's own HTML)
and, for LinkedIn rows, from the premium match panel captured per job. Concept
matching delegates to `/extract-entities` over the `opportunity_vocabulary`
corpus, the same path ranking uses, and degrades to no-match rather than
guessing when that vocabulary is unavailable.
"""

from __future__ import annotations

import html
import json
import re
import math
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from loguru import logger

POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "qualification_policy.json"
MAX_REQUIREMENTS_PER_POSTING = 12
EMBED_TIMEOUT = 30
EMBEDDER_UNAVAILABLE = (
    "The embedding service was unreachable, so requirements were not matched against approved claims. "
    "Unmatched is reported as a gap; it is never assumed covered."
)


def _terms(text: str, stopwords: set[str]) -> set[str]:
    """Content words worth matching on. Lower-cased, stopped, short words dropped."""

    words = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{2,}", str(text or "").lower())
    return {w.strip("./-") for w in words if len(w) > 3 and w not in stopwords}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class _RequirementParser(HTMLParser):
    """Collect list items that follow a requirements heading.

    Posting bodies are employer-authored HTML with a known grammar (headings then
    <ul><li>), so this is a structural parse, not pattern-guessing over prose.
    """

    def __init__(self, headings: list[str], preferred: list[str]) -> None:
        super().__init__(convert_charrefs=True)
        self._headings = [h.lower() for h in headings]
        self._preferred = [p.lower() for p in preferred]
        self._in_heading = False
        self._in_item = False
        self._heading_buffer: list[str] = []
        self._item_buffer: list[str] = []
        self._active = False
        self._active_is_preferred = False
        self.items: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "li":
            self._in_item = True
            self._item_buffer = []
        elif tag in {"h1", "h2", "h3", "h4"} or (tag in {"strong", "b"} and not self._in_item):
            # A <strong> inside an <li> is emphasis, not a heading. Treating it as
            # one stopped item capture, so every posting that bolds a bullet lead-in
            # ("<li><p><strong>Systems:</strong> ...") extracted zero requirements.
            self._in_heading = True
            self._heading_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "strong", "b"} and self._in_heading:
            self._in_heading = False
            heading = " ".join("".join(self._heading_buffer).split()).lower().strip(": ")
            if any(h in heading for h in self._headings):
                self._active = True
                self._active_is_preferred = any(p in heading for p in self._preferred)
            elif heading:
                self._active = False
        elif tag == "li" and self._in_item:
            self._in_item = False
            text = " ".join("".join(self._item_buffer).split())
            if self._active and len(text) > 8:
                self.items.append((text, self._active_is_preferred))

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            self._heading_buffer.append(data)
        if self._in_item:
            self._item_buffer.append(data)


def extract_requirements(posting_text: str, policy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Requirement bullets stated by the posting itself. [] when it states none."""

    if not posting_text:
        return []
    # Some boards hand back escaped markup (&lt;h1&gt;Minimum Qualifications&lt;/h1&gt;).
    # Unescape once so the same structural parse works for both encodings.
    if "&lt;" in posting_text and "<li" not in posting_text:
        posting_text = html.unescape(posting_text)
    if "<" not in posting_text:
        return []
    policy = policy or load_policy()
    parser = _RequirementParser(policy["requirement_headings"], policy["preferred_headings"])
    try:
        parser.feed(posting_text)
    except Exception as exc:  # noqa: BLE001 - a malformed posting is not a run failure
        logger.warning("requirement parse failed: {}", exc)
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for text, preferred in parser.items:
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"text": text, "preferred": preferred, "source": "posting_body"})
        if len(rows) >= MAX_REQUIREMENTS_PER_POSTING:
            break
    return rows


def linkedin_missing_qualifications(
    insights_text: str,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Requirements LinkedIn itself reports as missing from Graham's profile.

    Reads the captured job-page text. Only lines that follow one of the policy's
    `linkedin_missing_markers` are taken, so an unrecognised panel yields nothing
    rather than a fabricated gap list.
    """

    if not insights_text:
        return []
    policy = policy or load_policy()
    markers = [m.lower() for m in policy["linkedin_missing_markers"]]
    lines = [" ".join(line.split()) for line in insights_text.split("\n")]
    rows: list[dict[str, Any]] = []
    capturing = False
    for line in lines:
        low = line.lower()
        if any(marker in low for marker in markers):
            capturing = True
            continue
        if not capturing:
            continue
        if not line or len(line) < 4:
            capturing = False
            continue
        rows.append({"text": line, "preferred": False, "source": "linkedin_match_panel"})
        if len(rows) >= MAX_REQUIREMENTS_PER_POSTING:
            break
    return rows


def _hard_blocker(text: str, policy: dict[str, Any]) -> str | None:
    low = text.lower()
    for kind, phrases in policy["hard_blockers"].items():
        if any(phrase in low for phrase in phrases):
            return kind
    return None


def _claim_texts(claim: dict[str, Any]) -> str:
    wordings = " ".join(
        str(w.get("text") or "") for w in claim.get("wordings", []) if w.get("approved")
    )
    return f"{claim.get('claim_key', '')} {wordings}"


def _claim_rows(claim_snapshot: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    """(claim, first approved wording, text to embed) for every approved claim."""

    rows = []
    for claim in claim_snapshot.get("claims", []):
        if not claim.get("approved"):
            continue
        wording = next((w for w in claim.get("wordings", []) if w.get("approved")), None)
        if wording is None:
            continue
        rows.append((claim, wording, _claim_texts(claim)))
    return rows


def _hard_blocker_row(requirement: dict[str, Any], blocker: str) -> dict[str, Any]:
    return {
        **requirement,
        "disposition": "HARD_BLOCKER",
        "blocker_kind": blocker,
        "claim_key": None,
        "wording_id": None,
        "shared_term_count": None,
        "human_action": "eligibility_decision_only",
        "rationale": (
            f"The posting requires {blocker.replace('_', ' ')}. Tailoring cannot address this; "
            "only Graham can decide whether the opportunity stays in scope."
        ),
    }


def _gap_row(requirement: dict[str, Any], similarity: int | None, rationale: str, action: str) -> dict[str, Any]:
    return {
        **requirement,
        "disposition": "NOT_EVIDENCED",
        "blocker_kind": None,
        "claim_key": None,
        "wording_id": None,
        "shared_term_count": similarity,
        "human_action": action,
        "rationale": rationale,
    }


def answer_requirements(
    requirements: list[dict[str, Any]],
    claim_snapshot: dict[str, Any],
    *,
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Classify requirements against approved claims by shared terms.

    Every verdict names the words that produced it, so a human can see why a
    requirement was called answered. That is the whole reason this is lexical:
    a cosine score of 0.57 explains nothing and cannot be argued with.
    """

    limitations: list[str] = []
    if not requirements:
        return [], limitations
    match_policy = policy["match"]
    min_shared = int(match_policy.get("min_shared_terms", 2))
    stopwords = set(match_policy.get("stopwords") or [])

    claim_rows = _claim_rows(claim_snapshot)
    claim_terms = [(claim, wording, _terms(text, stopwords)) for claim, wording, text in claim_rows]
    if not claim_terms:
        limitations.append("The claim snapshot carries no approved wording; nothing can be answered.")

    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        text = str(requirement.get("text") or "")
        blocker = _hard_blocker(text, policy)
        if blocker:
            rows.append(_hard_blocker_row(requirement, blocker))
            continue
        if not claim_terms:
            rows.append(_gap_row(requirement, None, limitations[-1], "human_review"))
            continue
        wanted = _terms(text, stopwords)
        best: tuple[int, dict[str, Any], dict[str, Any], list[str]] | None = None
        for claim, wording, terms in claim_terms:
            shared = sorted(wanted & terms)
            if best is None or len(shared) > best[0]:
                best = (len(shared), claim, wording, shared)
        assert best is not None
        count, claim, wording, shared = best
        if count < min_shared:
            rows.append(
                _gap_row(
                    requirement,
                    count,
                    (
                        "No approved claim answers this requirement"
                        + (f" (closest is {claim['claim_key']}, sharing {shared})" if shared else "")
                        + f"; {min_shared} shared terms are required. If Graham has the experience it must "
                        "enter the claim snapshot before any resume or message may state it."
                    ),
                    "propose_claim_amendment_or_accept_gap",
                )
            )
            continue
        rows.append(
            {
                **requirement,
                "disposition": "ANSWERABLE_FROM_APPROVED_CLAIM",
                "blocker_kind": None,
                "claim_key": claim["claim_key"],
                "wording_id": wording["wording_id"],
                "claim_tier": int(claim.get("tier", 2)),
                "shared_terms": shared,
                "approved_wording": wording["text"],
                "human_action": "surface_claim_in_tailored_resume",
                "rationale": (
                    f"Approved claim {claim['claim_key']} shares the terms {', '.join(shared)} with this "
                    "requirement; the tailored variant should surface its approved wording verbatim."
                ),
            }
        )
    return rows, limitations


_SOFT_REQUIREMENT_MARKERS = (
    "mindset", "thrive", "passionate", "obsessed", "comfortable", "self-directed",
    "self directed", "generalist", "collaborat", "communicat", "partner", "curious",
    "ownership", "bias for action", "fast-moving", "fast moving", "ambiguous",
    "team player", "eager", "adaptable", "resourceful", "autonomous problem",
)


def is_hard_requirement(text: str) -> bool:
    """A hard requirement names a skill, tool, credential, or year count you either
    have or you don't. A soft one describes a working style. Only UNMET hard
    requirements should keep a role out of the top-candidate pool - Graham meets
    'thrives in ambiguity', he just has no claim that lexically says so."""

    low = str(text or "").lower()
    if any(marker in low for marker in _SOFT_REQUIREMENT_MARKERS):
        return False
    return True


def candidate_strength(report: dict[str, Any]) -> dict[str, Any]:
    """Where does Graham sit in the applicant pool for this role?

    Graham (2026-08-20): only roles where he would be in the top candidate pool
    are worth surfacing. A hard blocker is out. Otherwise it's the count of HARD
    requirements he cannot evidence that decides it - soft/behavioral gaps do not
    disqualify a real candidate.
    """

    requirements = report.get("requirements") or []
    if any(r.get("disposition") == "HARD_BLOCKER" for r in requirements):
        blocker = next(r for r in requirements if r["disposition"] == "HARD_BLOCKER")
        return {"tier": "BLOCKED", "reason": f"hard blocker: {blocker.get('blocker_kind')}", "hard_gaps": 0}
    hard_gaps = [
        r for r in requirements
        if r.get("disposition") == "NOT_EVIDENCED" and is_hard_requirement(r.get("text", ""))
    ]
    answerable = sum(1 for r in requirements if r.get("disposition") == "ANSWERABLE_FROM_APPROVED_CLAIM")
    n = len(hard_gaps)
    if n == 0:
        tier = "TOP_CANDIDATE"
    elif n <= 2 and answerable >= 1:
        tier = "POSSIBLE"
    else:
        tier = "WEAK"
    return {
        "tier": tier,
        "hard_gaps": n,
        "hard_gap_requirements": [r["text"][:80] for r in hard_gaps[:5]],
        "answerable": answerable,
        "reason": f"{n} unmet hard requirement(s), {answerable} answerable",
    }


def qualification_report(
    candidate: dict[str, Any],
    claim_snapshot: dict[str, Any],
    *,
    linkedin_insights_text: str = "",
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-opportunity qualification answer sheet. Local, read-only, no effects."""

    policy = policy or load_policy()
    requirements = [
        *linkedin_missing_qualifications(linkedin_insights_text, policy),
        *extract_requirements(str(candidate.get("posting_text") or ""), policy),
    ][:MAX_REQUIREMENTS_PER_POSTING]
    rows, limitations = answer_requirements(requirements, claim_snapshot, policy=policy)
    counts = {
        "requirements_read": len(rows),
        "answerable_from_approved_claim": sum(
            1 for r in rows if r["disposition"] == "ANSWERABLE_FROM_APPROVED_CLAIM"
        ),
        "not_evidenced": sum(1 for r in rows if r["disposition"] == "NOT_EVIDENCED"),
        "hard_blockers": sum(1 for r in rows if r["disposition"] == "HARD_BLOCKER"),
        "from_linkedin_match_panel": sum(1 for r in rows if r["source"] == "linkedin_match_panel"),
    }
    report = {
        "schema": "monitor_opportunities.qualification_report.v1",
        "candidate_id": candidate.get("candidate_id"),
        "title": candidate.get("title"),
        "organization": candidate.get("organization"),
        "posting_url": candidate.get("posting_url") or candidate.get("primary_evidence_url"),
        "claim_snapshot_profile_id": claim_snapshot.get("candidate_profile_id"),
        "requirements": rows,
        "counts": counts,
        "limitations": limitations,
        "non_claims": [
            "A requirement marked ANSWERABLE means an approved claim already covers it, not that the "
            "resume currently says so.",
            "NOT_EVIDENCED means the claim snapshot is silent. It is never treated as satisfied, and no "
            "wording may be invented to cover it.",
            "Hard blockers are eligibility facts; tailoring does not address them.",
        ],
        "external_effects": False,
        "action_worthy": True,
        "visible_in_report": True,
    }
    report["candidate_strength"] = candidate_strength(report)
    return report
