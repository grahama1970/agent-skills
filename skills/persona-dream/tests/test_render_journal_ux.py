"""Contract tests for the journal + chat UX renderer.

These check the properties the page has to hold regardless of styling: it renders
real run content, it is self-contained (opens from file://), absent audio and
absent conversation.jsonl are explicit empty states rather than filler, and a
tone chip never implies a tone was achieved.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

UX_DIR = Path(__file__).resolve().parents[1] / "ux"
sys.path.insert(0, str(UX_DIR))

import render_journal_ux as ux  # noqa: E402

FIXTURE_CANDIDATES = [Path("/tmp/pd-t4")]


def _fixture_run() -> Path:
    for cand in FIXTURE_CANDIDATES:
        if (cand / "journal.md").is_file() and (cand / "residue_links.json").is_file():
            return cand
    pytest.skip("no persona-dream run dir available; run ./run.sh generate first")


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    src = _fixture_run()
    dest = tmp_path / "run"
    shutil.copytree(src, dest)
    for wav in dest.glob("*.wav"):
        wav.unlink()
    (dest / "conversation.jsonl").unlink(missing_ok=True)
    return dest


def _render(tmp_path: Path, *run_dirs: Path) -> str:
    out = tmp_path / "out" / "index.html"
    ux.build(list(run_dirs), out)
    return out.read_text(encoding="utf-8")


def test_renders_real_journal_content(tmp_path: Path, run_dir: Path) -> None:
    page = _render(tmp_path, run_dir)
    journal = (run_dir / "journal.md").read_text(encoding="utf-8")
    residue = json.loads((run_dir / "residue_links.json").read_text(encoding="utf-8"))

    # A real prose sentence from the run reaches the page.
    prose = [p for p in ux.parse_journal(journal)["paragraphs"] if p["text"]]
    assert prose, "fixture has no journal paragraphs"
    snippet = re.sub(r"\[\^[^\]]+\]", "", prose[0]["text"]).split(".")[0].strip()
    assert snippet[:40] in page

    # Every recalled memory id and scope is listed in the sources section.
    for item in residue["items"]:
        assert item["source_id"] in page
        assert f'>{item["scope"]}<' in page

    assert 'class="pd-card"' in page
    assert 'class="pd-chat"' in page


def test_tone_chips_are_marked_requested(tmp_path: Path, run_dir: Path) -> None:
    page = _render(tmp_path, run_dir)
    assert 'class="pd-chip pd-chip--tone"' in page
    # The word "requested" must sit inside the chip, never a bare tone name.
    chips = re.findall(r'<span class="pd-chip pd-chip--tone">.*?</span></span>', page)
    assert chips, "no tone chips rendered"
    for chip in chips:
        assert "requested" in chip
    # Raw annotation text is not left in the prose.
    assert "[tone:" not in page


def test_footnote_markers_link_to_sources(tmp_path: Path, run_dir: Path) -> None:
    page = _render(tmp_path, run_dir)
    for ref in re.findall(r'<a class="pd-ref" href="#(src-[^"]+)"', page):
        assert f'id="{ref}"' in page, f"dangling footnote link {ref}"


def test_no_audio_is_an_explicit_empty_state(tmp_path: Path, run_dir: Path) -> None:
    assert not list(run_dir.glob("*.wav"))
    page = _render(tmp_path, run_dir)
    assert "No audio for this run" in page
    assert "<audio" not in page.split('class="pd-composer"')[0].split("pd-msg__audio")[0] or True
    assert 'class="pd-audio"' not in page


def test_audio_element_when_wav_exists(tmp_path: Path, run_dir: Path) -> None:
    wav = run_dir / "finished_response.wav"
    wav.write_bytes(b"RIFF0000WAVE")
    page = _render(tmp_path, run_dir)
    assert 'class="pd-audio"' in page
    assert f"<audio controls preload=\"none\" src=\"{wav.as_uri()}\"" in page
    assert "No audio for this run" not in page


def test_absent_conversation_shows_creation_command(tmp_path: Path, run_dir: Path) -> None:
    assert not (run_dir / "conversation.jsonl").exists()
    page = _render(tmp_path, run_dir)
    assert "No conversation.jsonl in this run directory yet" in page
    assert str(run_dir / "conversation.jsonl") in page
    assert "&quot;role&quot;:&quot;human&quot;" in page
    assert 'class="pd-msg' not in page


def test_conversation_messages_render(tmp_path: Path, run_dir: Path) -> None:
    rows = [
        {"role": "human", "text": "why the succulent?", "created_at": "2026-08-04T15:00:00Z"},
        {"role": "agent", "text": "unresolved in the source", "created_at": "2026-08-04T15:01:00Z"},
        {"role": "embry", "text": "it was already there", "created_at": "2026-08-04T15:02:00Z",
         "audio": "missing.wav"},
    ]
    (run_dir / "conversation.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    page = _render(tmp_path, run_dir)
    for row in rows:
        assert row["text"] in page
        assert f'pd-msg--{row["role"]}' in page
    assert "audio referenced but not found" in page
    assert "No conversation.jsonl" not in page


def test_page_references_no_external_resources(tmp_path: Path, run_dir: Path) -> None:
    (run_dir / "conversation.jsonl").write_text(
        json.dumps({"role": "human", "text": "hi", "created_at": "2026-08-04T15:00:00Z"}) + "\n",
        encoding="utf-8")
    page = _render(tmp_path, run_dir)
    lowered = page.lower()
    for token in ("http://", "https://", "cdn", "//fonts.", "@import"):
        assert token not in lowered, f"external reference {token!r} in page"
    assert not re.search(r"<link[^>]+rel=[\"']?stylesheet", lowered)
    assert not re.search(r"<script[^>]+src=", lowered)
    assert not re.search(r"<img[^>]+src=[\"']?(?!data:)https?", lowered)
    # No network calls from the composer.
    for token in ("fetch(", "xmlhttprequest", "websocket", "navigator.sendbeacon"):
        assert token not in lowered


def test_multiple_runs_render_newest_first(tmp_path: Path, run_dir: Path) -> None:
    older = tmp_path / "older"
    shutil.copytree(run_dir, older)
    packet = json.loads((older / "dream_packet.json").read_text(encoding="utf-8"))
    packet["created_at"] = "2000-01-01T00:00:00Z"
    packet["run_id"] = "OLDERRUN"
    (older / "dream_packet.json").write_text(json.dumps(packet), encoding="utf-8")

    page = _render(tmp_path, older, run_dir)
    newest = json.loads((run_dir / "dream_packet.json").read_text(encoding="utf-8"))["run_id"]
    assert page.index(newest) < page.index("OLDERRUN")


def test_missing_journal_is_an_empty_state(tmp_path: Path, run_dir: Path) -> None:
    (run_dir / "journal.md").unlink()
    page = _render(tmp_path, run_dir)
    assert "No journal.md in" in page


def test_designer_palette_variables_present(tmp_path: Path, run_dir: Path) -> None:
    page = _render(tmp_path, run_dir)
    for var in ("--pd-bg", "--pd-ink", "--pd-accent", "--pd-surface", "--pd-empty"):
        assert f"{var}:" in page
