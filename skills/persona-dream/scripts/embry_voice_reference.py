"""Single source of truth for which clip is Embry's authorized voice.

Two lanes disagreed. The continuity lane conditioned live Chatterbox renders on
``voice_clone_candidates/embry_kling_clone_candidate.wav`` (the service default,
``CHATTERBOX_REF_AUDIO``), while the emotion-proof lane staged
``persona_dream_voice_refs/embry_authorized_ref_30s_8s.wav``. The two recordings
score 0.7384 against each other, below the 0.75 same-speaker floor, so "which
file is Embry" had two different answers depending on which lane you read.

Resolved 2026-07-28 by operator decision: the clone candidate is promoted,
because it is the only Embry clip that exists and the one every live render has
actually used. ``reports/goal_v5/peer_review/SPEC_arc_state_to_voice.md``
recorded the underlying asset reality on 2026-07-25: "The anchor bank does not
exist. Only ONE clip per persona is present."

Import ``AUTHORIZED_EMBRY_REFERENCE`` rather than writing a path. A literal path
in one more file is how the lanes diverged in the first place.

Historical receipts under ``reports/`` are NOT rewritten to match. They record
which clip a past run actually used, and editing them would destroy the evidence
that the divergence happened.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The authorized Embry voice. Promoted from voice_clone_candidates 2026-07-28.
AUTHORIZED_EMBRY_REFERENCE = ROOT / "voice_clone_candidates" / "embry_kling_clone_candidate.wav"

#: What the emotion-proof lane staged before the promotion. Kept so historical
#: receipts remain interpretable; not a current default for anything.
LEGACY_STAGING_REFERENCE = Path(
    "/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs/"
    "embry_authorized_ref_30s_8s.wav"
)

#: Container path the Chatterbox service resolves CHATTERBOX_REF_AUDIO to. The
#: host side is bind-mounted from AUTHORIZED_EMBRY_REFERENCE.
CHATTERBOX_CONTAINER_REFERENCE = "/data/embry_ref.wav"


def reference_sha256(path: Path | None = None) -> str | None:
    """Hash the reference so a receipt can prove which clip it used."""
    target = path or AUTHORIZED_EMBRY_REFERENCE
    if not target.is_file():
        return None
    return "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()


def reference_provenance(path: Path | None = None) -> dict[str, object]:
    """Receipt-ready description of the clip in use."""
    target = path or AUTHORIZED_EMBRY_REFERENCE
    return {
        "path": str(target),
        "exists": target.is_file(),
        "bytes": target.stat().st_size if target.is_file() else 0,
        "sha256": reference_sha256(target),
        "is_authorized": target.resolve() == AUTHORIZED_EMBRY_REFERENCE.resolve(),
        "promoted_at": "2026-07-28",
    }
