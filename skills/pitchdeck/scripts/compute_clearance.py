"""Publication clearance ledger: canonical truth vs what may be published.

The canonical source of truth is the PRIVATE repo (code, docs, evidence, full
image inventory). Publication is a separate question: an asset or claim may be
true and canonical yet not cleared to leave the building. This module computes
that second layer deterministically.

An asset is cleared PUBLIC-BY-PRECEDENT when a byte-identical file already
appears in the public mirror at a pinned commit — mechanically checkable, no
human judgement needed. Everything else is PRIVATE and requires a named human
attestation bound to the exact blob before it can enter a public deck
(scanners cannot see hostnames, browser chrome, or customer names in a capture).

Inputs: canonical root, public mirror root, public ref. Outputs: a clearance
ledger JSON. Failure modes: a missing root raises; a same-name-different-bytes
pair is reported as NOT cleared (never assumed equivalent).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(help="Compute the publication clearance ledger for deck assets.")


@dataclass(frozen=True, slots=True)
class ClearanceRecord:
    asset: str
    canonical_path: str
    sha256: str
    cleared: bool
    basis: str
    public_evidence: str | None = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory(root: Path) -> dict[str, Path]:
    assets = root / "docs" / "assets"
    if not assets.is_dir():
        raise typer.BadParameter(f"no docs/assets under {root}")
    found: dict[str, Path] = {}
    for path in sorted(assets.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".webp", ".png", ".svg", ".jpg"}:
            if "/source/" in str(path):  # working originals, not published figures
                continue
            found[path.name] = path
    return found


@app.command()
def compute(
    canonical_root: Path = typer.Option(..., help="PRIVATE repo checkout — the source of truth."),
    public_root: Path = typer.Option(..., help="Public mirror checkout — evidence of prior clearance."),
    public_ref: str = typer.Option("HEAD", help="Pinned public commit the precedent is bound to."),
    output: Path = typer.Option(Path("examples/sparta-explorer/clearance_ledger.json")),
) -> None:
    """Emit the clearance ledger: which canonical assets may be published, and why."""
    canonical = _inventory(canonical_root)
    public = _inventory(public_root)
    records: list[ClearanceRecord] = []
    for name, path in canonical.items():
        digest = _sha256(path)
        match = public.get(name)
        if match is None:
            records.append(ClearanceRecord(name, str(path), digest, False,
                                           "canonical-only: requires named human attestation"))
            continue
        public_digest = _sha256(match)
        if public_digest == digest:
            records.append(ClearanceRecord(name, str(path), digest, True,
                                           f"public-by-precedent@{public_ref}", str(match)))
        else:
            # same name, different bytes: NOT equivalent, never assumed cleared
            logger.warning("{} differs between canonical and public mirror", name)
            records.append(ClearanceRecord(name, str(path), digest, False,
                                           "name matches public mirror but BYTES DIFFER — not cleared",
                                           str(match)))
    payload = {
        "schema": "pitchdeck.clearance_ledger.v1",
        "canonical_root": str(canonical_root),
        "public_root": str(public_root),
        "public_ref": public_ref,
        "cleared_count": sum(1 for r in records if r.cleared),
        "attestation_required_count": sum(1 for r in records if not r.cleared),
        "records": [asdict(r) for r in records],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=1))
    typer.echo(json.dumps({"status": "PASS", "output": str(output),
                           "cleared": payload["cleared_count"],
                           "attestation_required": payload["attestation_required_count"]}, indent=1))


if __name__ == "__main__":
    app()
