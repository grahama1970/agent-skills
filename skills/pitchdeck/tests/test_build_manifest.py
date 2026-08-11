"""Build-manifest chain integrity (#1332).

A stored hash nobody checks is decoration, so verify_manifest RE-COMPUTES every
digest. Each test mutates one link of the chain the way the drift actually
happens — an edited ledger, a swapped template, a revised document, a different
delivered file, an uncommitted tree — and asserts the typed refusal.
"""

import json
from pathlib import Path

from pitchdeck.build_manifest import (
    BuildManifest,
    build_manifest,
    verify_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _sources(tmp_path: Path) -> dict[str, Path]:
    sources = {}
    for role, payload in (
        ("claim_ledger", "claims:\n  - id: c1\n    text: alpha\n"),
        ("canonical_document", '{"slides": []}'),
        ("template", "TEMPLATE-BYTES-V1"),
    ):
        path = tmp_path / f"{role}.dat"
        path.write_text(payload)
        sources[role] = path
    return sources


def _manifest(tmp_path: Path, sources: dict[str, Path]) -> BuildManifest:
    pptx = tmp_path / "deck.pptx"
    pptx.write_bytes(b"PPTX-BYTES-V1")
    return build_manifest(repo_root=REPO_ROOT, sources=sources, delivered_pptx=pptx)


def test_clean_chain_passes(tmp_path):
    sources = _sources(tmp_path)
    manifest = _manifest(tmp_path, sources)
    findings = verify_manifest(manifest, repo_root=REPO_ROOT, sources=sources,
                               delivered_pptx=tmp_path / "deck.pptx", allow_dirty=True)
    assert findings == []


def test_identical_inputs_produce_an_identical_chain_digest(tmp_path):
    sources = _sources(tmp_path)
    a = _manifest(tmp_path, sources)
    b = _manifest(tmp_path, sources)
    assert a.content_digest() == b.content_digest()


def test_edited_ledger_is_input_drift(tmp_path):
    sources = _sources(tmp_path)
    manifest = _manifest(tmp_path, sources)
    sources["claim_ledger"].write_text("claims:\n  - id: c1\n    text: alpha AND MORE\n")
    findings = verify_manifest(manifest, repo_root=REPO_ROOT, sources=sources, allow_dirty=True)
    assert any(f.code == "INPUT_DRIFT" and "claim_ledger" in f.detail for f in findings)


def test_swapped_template_is_a_hash_mismatch_not_generic_drift(tmp_path):
    """The review's finding: template_sha256 was stored but never compared."""
    sources = _sources(tmp_path)
    manifest = _manifest(tmp_path, sources)
    sources["template"].write_text("A-DIFFERENT-TEMPLATE-WITH-SIMILAR-LAYOUT-NAMES")
    findings = verify_manifest(manifest, repo_root=REPO_ROOT, sources=sources, allow_dirty=True)
    assert any(f.code == "TEMPLATE_HASH_MISMATCH" for f in findings)


def test_revised_document_is_refused(tmp_path):
    """The #1371 stale-document criterion: a document revised after the manifest."""
    sources = _sources(tmp_path)
    manifest = _manifest(tmp_path, sources)
    sources["canonical_document"].write_text('{"slides": [{"forged": true}]}')
    findings = verify_manifest(manifest, repo_root=REPO_ROOT, sources=sources, allow_dirty=True)
    assert any(f.code == "INPUT_DRIFT" and "canonical_document" in f.detail for f in findings)


def test_swapped_delivered_pptx_is_refused(tmp_path):
    sources = _sources(tmp_path)
    manifest = _manifest(tmp_path, sources)
    other = tmp_path / "other.pptx"
    other.write_bytes(b"PPTX-BYTES-V2")
    findings = verify_manifest(manifest, repo_root=REPO_ROOT, sources=sources,
                               delivered_pptx=other, allow_dirty=True)
    assert any(f.code == "DELIVERED_ARTIFACT_DRIFT" for f in findings)


def test_missing_input_is_reported_not_skipped(tmp_path):
    sources = _sources(tmp_path)
    manifest = _manifest(tmp_path, sources)
    sources["template"].unlink()
    findings = verify_manifest(manifest, repo_root=REPO_ROOT, sources=sources, allow_dirty=True)
    assert any(f.code == "INPUT_MISSING" and "template" in f.detail for f in findings)


def test_dirty_tree_is_refused_unless_explicitly_allowed(tmp_path):
    sources = _sources(tmp_path)
    manifest = _manifest(tmp_path, sources)
    if not manifest.compiler.dirty:
        import pytest

        pytest.skip("working tree is clean; dirtiness cannot be exercised here")
    findings = verify_manifest(manifest, repo_root=REPO_ROOT, sources=sources)
    assert any(f.code == "DIRTY_COMPILER_STATE" for f in findings)


def test_unresolvable_commit_is_refused(tmp_path):
    """The false-SHA incident: a receipt citing a commit that is not the code."""
    sources = _sources(tmp_path)
    manifest = _manifest(tmp_path, sources)
    forged = manifest.model_copy(deep=True)
    forged.compiler.commit = "deadbeef" * 5
    findings = verify_manifest(forged, repo_root=REPO_ROOT, sources=sources, allow_dirty=True)
    assert any(f.code == "COMMIT_UNRESOLVABLE" for f in findings)
