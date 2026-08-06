"""Living versioned deck: source-drift detection and version pinning (#1229).

snapshot_sources records sha256 per resolvable source into source_state.json;
check_drift compares current files against that snapshot and maps changed or
missing sources to the claims (via source_refs and evidence_spans) and slides
they invalidate. Validation reads the same snapshot at publish tier and fails
closed with SOURCE_DRIFT — a stale deck can present internally but cannot
publish until the snapshot is refreshed (which flows through decision memory,
so only changed claims re-review). pin_version writes the source-hash set +
bundle revision next to a published artifact so every published deck is
diffable against its predecessor. Failure modes: unresolvable sources are
reported as missing, never skipped silently.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from .models import ClaimLedger, DeckManifest, SourceManifest

SOURCE_STATE_FILE = "source_state.json"


def _resolve(path_text: str, source_manifest_dir: Path) -> Path:
    path = Path(os.path.expandvars(path_text))
    return path if path.is_absolute() else source_manifest_dir / path


def _hash_sources(sources: SourceManifest, source_manifest_dir: Path) -> tuple[dict[str, str], list[str]]:
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for source in sources.sources:
        path = _resolve(source.path, source_manifest_dir)
        if path.exists():
            hashes[source.id] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            missing.append(source.id)
    return hashes, missing


def snapshot_sources(bundle_dir: Path, sources: SourceManifest, source_manifest_dir: Path) -> dict[str, str]:
    hashes, missing = _hash_sources(sources, source_manifest_dir)
    payload = {"schema": "pitchdeck.source_state.v1", "hashes": hashes, "missing": missing}
    (bundle_dir / SOURCE_STATE_FILE).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    logger.info("source snapshot: {} hashed, {} missing", len(hashes), len(missing))
    return hashes


def check_drift(
    bundle_dir: Path,
    deck: DeckManifest,
    ledger: ClaimLedger,
    sources: SourceManifest,
    source_manifest_dir: Path,
) -> dict:
    state_path = bundle_dir / SOURCE_STATE_FILE
    if not state_path.exists():
        return {"snapshot": False, "changed": [], "missing": [], "affected_claims": [], "affected_slides": [], "no_op": True}
    recorded = json.loads(state_path.read_text())["hashes"]
    current, missing = _hash_sources(sources, source_manifest_dir)
    changed = sorted(
        sid for sid in set(recorded) | set(current) if recorded.get(sid) != current.get(sid)
    )
    changed_set = set(changed) | set(missing)
    affected_claims = sorted(
        c.id for c in ledger.claims
        if {r.source_id for r in c.source_refs} & changed_set
        or {s.source_id for s in c.evidence_spans} & changed_set
    )
    affected_slides = sorted(
        s.id for s in deck.slides if set(s.claim_ids) & set(affected_claims)
    )
    report = {
        "snapshot": True,
        "changed": changed,
        "missing": missing,
        "affected_claims": affected_claims,
        "affected_slides": affected_slides,
        "no_op": not changed and not missing,
        "repair_hint": (
            "re-run plan (decision memory carries unchanged approvals), re-review the "
            "affected claims, then refresh the snapshot with drift --update"
        ) if changed or missing else None,
    }
    logger.info("drift check: {} changed, {} affected claims", len(changed), len(affected_claims))
    return report


def pin_version(output_path: Path, bundle_dir: Path, deck: DeckManifest, revision: int) -> Path:
    state_path = bundle_dir / SOURCE_STATE_FILE
    hashes = json.loads(state_path.read_text())["hashes"] if state_path.exists() else {}
    version = {
        "schema": "pitchdeck.deck_version.v1",
        "deck_id": deck.deck.id,
        "bundle_revision": revision,
        "source_sha256": hashes,
        "pinned_at": datetime.now(UTC).isoformat(),
        "artifact": output_path.name,
    }
    version_path = output_path.with_suffix(output_path.suffix + ".version.json")
    version_path.write_text(json.dumps(version, indent=1), encoding="utf-8")
    return version_path
