"""Map GitHub commit provenance signals to detector labels using metadata only.

Three provenance classes, kept DISTINCT so weak labels never launder into strong
ones (the immutable-goal integrity rule):

- agent_authored: commit author is a known coding-agent bot account; closest to
  pure-agent output.
- ai_assisted:    a human author but an agent co-author / "generated with" trailer;
  the human almost always edited the diff, so this is a weak AI label.
- human_proxy:    no agent signal at all; a WEAK human baseline, NOT consented
  ground truth.

This module reads commit metadata only (author login + message). It never fetches
or stores code content, so it carries no licensing/consent exposure on its own;
pulling code bodies for training stays gated behind explicit human clearance.
"""
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum


class Provenance(StrEnum):
    AGENT_AUTHORED = "agent_authored"
    AI_ASSISTED = "ai_assisted"
    HUMAN_PROXY = "human_proxy"


# Bot accounts that commit as coding agents. github-actions[bot] is deliberately
# excluded: it is generic CI automation, not authored code.
AGENT_BOT_LOGINS = frozenset({
    "claude[bot]", "cursor[bot]", "devin-ai-integration[bot]",
    "copilot-swe-agent[bot]", "google-labs-jules[bot]",
})

# Lowercased trailer/message markers left by agent-assisted commits.
AI_ASSIST_MARKERS = (
    "co-authored-by: claude", "generated with claude code",
    "co-authored-by: openai-codex", "co-authored-by: cursor",
    "co-authored-by: devin", "co-authored-by: copilot",
)

# Which classes may feed the efficacy (strong-label) tier. gh-mined weak labels
# are red-team/realism input only and must never establish detection accuracy.
EFFICACY_ELIGIBLE: frozenset[Provenance] = frozenset()  # none from gh mining


@dataclass(frozen=True, slots=True)
class CommitSignal:
    """Metadata-only provenance signal for one commit (no code content)."""

    author_login: str
    message: str


def classify(signal: CommitSignal) -> Provenance:
    """Classify one commit into a provenance class from metadata alone."""
    if signal.author_login.strip().lower() in AGENT_BOT_LOGINS:
        return Provenance.AGENT_AUTHORED
    message = signal.message.lower()
    if any(marker in message for marker in AI_ASSIST_MARKERS):
        return Provenance.AI_ASSISTED
    return Provenance.HUMAN_PROXY


def detector_label(provenance: Provenance) -> str:
    """Map a provenance class to the detector's human/machine label."""
    return "human" if provenance == Provenance.HUMAN_PROXY else "machine"


def survey(signals: list[CommitSignal]) -> dict[str, int]:
    """Count commits per provenance class; the basis for a corpus-plan decision."""
    counts = Counter(classify(s).value for s in signals)
    return {p.value: counts.get(p.value, 0) for p in Provenance}
