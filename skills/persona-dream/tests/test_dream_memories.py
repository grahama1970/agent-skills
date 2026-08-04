"""A dream's interpretation and its media are memories too.

This is the mechanism by which a persona deepens rather than resetting: she
dreams on her experiences, what she concludes becomes something she remembers,
and a later dream draws on it. The write had never worked -- it targeted the
`lessons` collection, which rejects a reflection with 422 "no extractable
taxonomy", and it failed soft, so every run reported success while the most
important write in the pipeline errored.

The counterweight is that an interpretation must never harden into fact. A dream
is what she made of her experience, not a record of what happened, and dream
imagery is not a photograph.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import persona_dream as pd  # noqa: E402
import store_dream_artifacts as sda  # noqa: E402


def test_reflections_go_to_a_collection_that_accepts_them():
    """`lessons` rejects a dream reflection; persona_memory is its home.

    It is also where the persona memories a later dream blends it with live.
    """
    src = Path(pd.__file__).read_text(encoding="utf-8")
    fn = src[src.index("def _store_reflection"):src.index("@app.command(\"generate\")")]
    assert "CENTRAL_PERSONA_MEMORY_COLLECTION" in fn
    assert '"lessons"' not in fn


def test_a_reflection_is_marked_synthetic_in_its_text():
    """Metadata can be dropped by a retrieval path; the text cannot."""
    src = Path(pd.__file__).read_text(encoding="utf-8")
    fn = src[src.index("def _store_reflection"):src.index("@app.command(\"generate\")")]
    assert "In a dream I interpreted" in fn
    assert '"synthetic": True' in fn
    assert "not a factual claim" in fn


def test_a_reflection_write_is_gated_on_read_back():
    """A store response is not evidence: this one returned 422 for months."""
    src = Path(pd.__file__).read_text(encoding="utf-8")
    fn = src[src.index("def _store_reflection"):src.index("@app.command(\"generate\")")]
    assert "reflection_not_retrievable_after_write" in fn
    assert '"/query"' in fn


def test_reflections_outrank_commit_churn_in_the_day_draw():
    """Her own prior conclusion is the channel through which anything accumulates.

    Losing its quota slot to a busy commit day would break the deepening it
    exists to produce.
    """
    kinds = ["Day event (code)", "Day event (dream_reflection)",
             "Day event (affect)", "Day event (conversation)"]

    def rank(kind: str) -> int:
        if "affect" in kind:
            return 0
        if "conversation" in kind:
            return 1
        if "dream_reflection" in kind:
            return 2
        if "project_state" in kind:
            return 3
        return 4

    order = sorted(kinds, key=lambda k: (rank(k), k))
    assert order.index("Day event (dream_reflection)") < order.index("Day event (code)")


def test_artifacts_carry_modality_and_the_hash_of_what_they_describe(tmp_path):
    """An artifact memory that cannot be tied to its bytes is a claim about a
    picture nobody can produce."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "contact_sheet.png").write_bytes(b"\x89PNG fake")
    (run / "journal.wav").write_bytes(b"RIFF fake")
    (run / "journal_spoken.txt").write_text("I woke with what.\n", encoding="utf-8")

    docs = sda.build_documents(run, "embry", "2026-08-04", "run-1")
    mods = {d["modality"] for d in docs}
    assert mods == {"image", "audio"}
    for d in docs:
        assert d["artifact_sha256"].startswith("sha256:")
        assert d["record_type"] == "dream_artifact"


def test_artifacts_are_marked_synthetic_in_their_text(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "contact_sheet.png").write_bytes(b"\x89PNG fake")
    docs = sda.build_documents(run, "embry", "2026-08-04", "run-1")
    assert docs[0]["solution"].startswith("From a dream:")
    assert docs[0]["synthetic"] is True


def test_the_same_artifact_does_not_duplicate(tmp_path):
    """Keyed by content hash, so re-registering the same media is an upsert."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "contact_sheet.png").write_bytes(b"\x89PNG fake")
    a = sda.build_documents(run, "embry", "2026-08-04", "run-1")
    b = sda.build_documents(run, "embry", "2026-08-04", "run-2")
    assert a[0]["_key"] == b[0]["_key"]


def test_a_run_with_no_media_is_not_an_error(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    assert sda.build_documents(run, "embry", "2026-08-04", "run-1") == []


def test_the_same_interpretation_is_one_memory_however_often_it_is_generated():
    """Keying on run_id wrote a fresh duplicate on every re-run.

    Three `generate --write-memory` runs produced three identical
    dream_reflection records. That inflates the dreamt record and skews the
    quota later dreams draw from — it corrupts the longitudinal record the
    project exists to build. All three memory writers are now content-addressed.
    """
    src = Path(pd.__file__).read_text(encoding="utf-8")
    fn = src[src.index("def _store_reflection"):src.index("@app.command(\"generate\")")]
    assert 'key_src = f"{persona.id}:{reflection}"' in fn, "reflection key must not include run_id"
    assert "packet['run_id']}:{reflection}" not in fn


def test_the_day_reader_skips_deprecated_records():
    """Memory is append-only, so a bad record is tombstoned, not deleted.

    A reader that ignored the tombstone would keep drawing a record its author
    has retracted — which is worse than the duplicate it was meant to retire.
    """
    src = Path(pd.__file__).read_text(encoding="utf-8")
    start = src.index("def _fetch_day_memories")
    fn = src[start:src.index("def _fetch_residue(", start)]
    assert "d.deprecated != true" in fn


def test_deprecation_preserves_the_original_record():
    """A tombstone is not a delete wearing a different word.

    The text must survive verbatim so an auditor can still see what was written
    and on what grounds it stopped counting.
    """
    import deprecate_memory as dm
    src = Path(dm.__file__).read_text(encoding="utf-8")
    assert 'doc["deprecated"] = True' in src
    assert 'doc["deprecated_reason"]' in src
    # The original document is fetched and amended, never rebuilt from scratch.
    assert "doc = fetch(client, key, collection)" in src
    assert "read_back_deprecated" in src
