"""One digest chain binding every input to the delivered artifact (#1332).

Until now each stage carried its own partial receipt and nothing joined them, so
several classes of drift were undetectable: a template swapped for one with
matching layout names (``template_sha256`` was stored but never compared), a
claim edited after approval, a font substituted, or a document revised between
approval and emission. The review also caught a receipt citing a commit SHA that
resolved to an unrelated lane's commit — a false receipt is worse than none.

A BuildManifest content-addresses the whole chain: sources, ledger, approved
outline, transform policy, canonical document, template, assets, fonts, icon
library, compiler commit and dirty state, renderer versions, and the delivered
package. ``verify_manifest`` then RE-COMPUTES each digest rather than trusting
the recorded value, because a stored hash nobody checks is decoration.

Inputs: the artifacts of one build. Outputs: a manifest, and typed drift
findings. Failure modes: a missing input is recorded as absent rather than
skipped silently, and a dirty compiler tree is reported — never quietly treated
as reproducible.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field

from .models import StrictModel


def file_digest(path: Path) -> str | None:
    """sha256 of a file, or None when it is absent (recorded, never assumed)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, TypeError):
        return None


def bytes_digest(payload: bytes | str) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_json_digest(value) -> str:
    """Digest of a structure, independent of key order and whitespace."""
    return bytes_digest(json.dumps(value, sort_keys=True, separators=(",", ":")))


class InputDigest(StrictModel):
    role: str
    path: str | None = None
    sha256: str | None = None
    present: bool = True


class CompilerState(StrictModel):
    """Which implementation actually produced this build."""

    commit: str | None = None
    dirty: bool = True
    dirty_paths: list[str] = Field(default_factory=list)
    python: str = ""

    @property
    def reproducible(self) -> bool:
        return bool(self.commit) and not self.dirty


class BuildManifest(StrictModel):
    schema_: Literal["pitchdeck.build_manifest.v1"] = Field(
        default="pitchdeck.build_manifest.v1", alias="schema"
    )
    inputs: list[InputDigest] = Field(default_factory=list)
    compiler: CompilerState
    renderers: dict[str, str] = Field(default_factory=dict)
    delivered_pptx_sha256: str | None = None

    def digest_for(self, role: str) -> str | None:
        return next((i.sha256 for i in self.inputs if i.role == role), None)

    def content_digest(self) -> str:
        """The chain digest: identical inputs must produce an identical value."""
        payload = {
            "inputs": sorted(
                ({"role": i.role, "sha256": i.sha256, "present": i.present} for i in self.inputs),
                key=lambda entry: entry["role"],
            ),
            "compiler": {"commit": self.compiler.commit, "dirty": self.compiler.dirty},
            "renderers": dict(sorted(self.renderers.items())),
            "delivered_pptx_sha256": self.delivered_pptx_sha256,
        }
        return canonical_json_digest(payload)


def compiler_state(repo_root: Path) -> CompilerState:
    """Record the commit AND whether the tree was dirty.

    A receipt that cites a commit while the tree had uncommitted changes is
    misleading in exactly the way the false-SHA incident was, so dirtiness is
    recorded as a first-class field rather than inferred later."""
    import sys

    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(repo_root), *args],
                                  capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    commit = git("rev-parse", "HEAD") or None
    status = git("status", "--porcelain", "--", "skills/pitchdeck")
    dirty_paths = [line[3:] for line in status.splitlines() if line.strip()]
    return CompilerState(
        commit=commit,
        dirty=bool(dirty_paths),
        dirty_paths=dirty_paths[:20],
        python=sys.version.split()[0],
    )


def build_manifest(
    *,
    repo_root: Path,
    sources: dict[str, Path],
    delivered_pptx: Path | None = None,
    renderers: dict[str, str] | None = None,
) -> BuildManifest:
    """Digest every input by role. Absence is recorded, never skipped."""
    inputs = [
        InputDigest(role=role, path=str(path), sha256=file_digest(path), present=Path(path).is_file())
        for role, path in sorted(sources.items())
    ]
    return BuildManifest(
        inputs=inputs,
        compiler=compiler_state(repo_root),
        renderers=dict(renderers or {}),
        delivered_pptx_sha256=file_digest(delivered_pptx) if delivered_pptx else None,
    )


class ManifestFinding(StrictModel):
    code: Literal[
        "INPUT_DRIFT",
        "INPUT_MISSING",
        "TEMPLATE_HASH_MISMATCH",
        "DELIVERED_ARTIFACT_DRIFT",
        "DIRTY_COMPILER_STATE",
        "COMMIT_UNRESOLVABLE",
    ]
    detail: str


def verify_manifest(
    manifest: BuildManifest,
    *,
    repo_root: Path,
    sources: dict[str, Path],
    delivered_pptx: Path | None = None,
    allow_dirty: bool = False,
) -> list[ManifestFinding]:
    """RE-COMPUTE every digest. A stored hash nobody checks is decoration."""
    findings: list[ManifestFinding] = []
    recorded = {i.role: i for i in manifest.inputs}

    for role, path in sorted(sources.items()):
        entry = recorded.get(role)
        actual = file_digest(path)
        if entry is None:
            findings.append(ManifestFinding(
                code="INPUT_MISSING", detail=f"input '{role}' is not recorded in the manifest"))
            continue
        if actual is None:
            findings.append(ManifestFinding(
                code="INPUT_MISSING", detail=f"input '{role}' recorded but absent at {path}"))
            continue
        if entry.sha256 != actual:
            findings.append(ManifestFinding(
                code="TEMPLATE_HASH_MISMATCH" if role == "template" else "INPUT_DRIFT",
                detail=(f"input '{role}' changed since the manifest was written "
                        f"(recorded {str(entry.sha256)[:12]}…, actual {actual[:12]}…)")))

    if delivered_pptx is not None:
        actual = file_digest(delivered_pptx)
        if actual != manifest.delivered_pptx_sha256:
            findings.append(ManifestFinding(
                code="DELIVERED_ARTIFACT_DRIFT",
                detail=("the delivered pptx is not the file this manifest describes "
                        f"(recorded {str(manifest.delivered_pptx_sha256)[:12]}…, actual {str(actual)[:12]}…)")))

    if manifest.compiler.dirty and not allow_dirty:
        findings.append(ManifestFinding(
            code="DIRTY_COMPILER_STATE",
            detail=(f"built from an uncommitted tree ({len(manifest.compiler.dirty_paths)} changed paths); "
                    "the cited commit does not describe the implementation used")))
    if manifest.compiler.commit:
        probe = subprocess.run(["git", "-C", str(repo_root), "cat-file", "-e", f"{manifest.compiler.commit}^{{commit}}"],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            findings.append(ManifestFinding(
                code="COMMIT_UNRESOLVABLE",
                detail=f"manifest cites commit {manifest.compiler.commit[:12]}… which does not resolve in this repo"))
    return findings
