"""Accumulate labeled relevance examples for a future /classifier-lab classifier.

The data flywheel: the running system labels its own data — the adversarial set
seeds it, the opportunity-evaluator's KEEP/REJECT verdicts and the human's board
decisions (approved/applied = positive, closed/reject = negative) append to it.
When enough labels accrue, /classifier-lab trains a learned relevance classifier
that replaces the regex/fuzzy first pass (best-practices-python: a classifier
when the category is learned from examples).

Labels live in the /memory `opportunity_labels` collection (one doc per unique
text, deduped by text hash). No training here — this only collects the data.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

from .util import utc_now

MEMORY_URL = "http://127.0.0.1:8601"
LABELS_COLLECTION = "opportunity_labels"
ADVERSARIAL_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "relevance_adversarial.json"


def _store(doc: dict[str, Any], memory_url: str = MEMORY_URL) -> bool:
    body = json.dumps({"document": doc, "collection": LABELS_COLLECTION}).encode()
    req = urllib.request.Request(f"{memory_url}/store", data=body, headers={"Content-Type": "application/json"})
    try:
        return bool(json.loads(urllib.request.urlopen(req, timeout=20).read()).get("stored"))
    except OSError:
        return False


def append_label(text: str, label: int, source: str, extra: dict[str, Any] | None = None, memory_url: str = MEMORY_URL) -> bool:
    """Append one labeled example. label=1 relevant, 0 not. source=adversarial|evaluator|human.

    Deduped by text hash; a later human/evaluator label overwrites an earlier one
    (human > evaluator > adversarial is the caller's responsibility via source).
    """
    text = (text or "").strip()
    if not text or label not in (0, 1):
        return False
    doc = {
        "_key": hashlib.sha256(text.lower().encode()).hexdigest()[:16],
        "text": text,
        "label": label,
        "source": source,
        "labeled_at": utc_now(),
    }
    if extra:
        doc.update(extra)
    return _store(doc, memory_url)


def seed_from_adversarial(memory_url: str = MEMORY_URL) -> dict[str, int]:
    """Seed the label store from the adversarial fixture (must_match=1, must_not_match=0)."""
    data = json.loads(ADVERSARIAL_FIXTURE.read_text(encoding="utf-8"))
    pos = sum(append_label(t, 1, "adversarial", memory_url=memory_url) for t in data.get("must_match", []))
    neg = sum(append_label(t, 0, "adversarial", memory_url=memory_url) for t in data.get("must_not_match", []))
    return {"positive": pos, "negative": neg}


def label_from_verdict(text: str, verdict: str, memory_url: str = MEMORY_URL) -> bool:
    """Map an opportunity-evaluator verdict to a training label (called per evaluation)."""
    positive = {"KEEP", "ADJACENT", "CLIENT_SIGNAL"}
    negative = {"REJECT"}
    if verdict in positive:
        return append_label(text, 1, "evaluator", {"verdict": verdict}, memory_url)
    if verdict in negative:
        return append_label(text, 0, "evaluator", {"verdict": verdict}, memory_url)
    return False  # NEEDS_REVIEW is not a training signal


def label_from_board_state(text: str, state: str, memory_url: str = MEMORY_URL) -> bool:
    """Map a human board decision to a gold training label (human > evaluator)."""
    positive = {"state:approved", "state:applied", "state:responded"}
    negative = {"verdict:reject"}
    if state in positive:
        return append_label(text, 1, "human", {"board_state": state}, memory_url)
    if state in negative:
        return append_label(text, 0, "human", {"board_state": state}, memory_url)
    return False
