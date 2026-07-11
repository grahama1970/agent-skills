from __future__ import annotations

import json
from pathlib import Path

import pytest

from battle_skill.normalized_music_fixture import normalize_music_fixture, validate_document, validate_normalized_music_fixture_path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "local/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
CATALOG = ROOT / "spectator/public/battle-audio/score/v1/runtime-catalog.json"


def test_music_fixture_normalizer_publishes_receipt_authorized_schedule(tmp_path: Path) -> None:
    local = tmp_path / "local"
    public = tmp_path / "public"
    audio = tmp_path / "public-root/battle-audio/promoted/v1"
    # Preserve the catalog's absolute public URL resolution in a temporary public tree.
    public_root = audio.parents[2]
    source_public = ROOT / "spectator/public"
    (public_root / "battle-audio").mkdir(parents=True)
    import shutil
    shutil.copytree(source_public / "battle-audio", public_root / "battle-audio", dirs_exist_ok=True)

    fixture = normalize_music_fixture(
        source_fixture=SOURCE,
        catalog=public_root / "battle-audio/score/v1/runtime-catalog.json",
        out_dir=local,
        public_out_dir=public,
        public_audio_root=audio,
        generated_at="2026-07-11T12:00:00Z",
    )
    assert fixture["events_present"] == ["live_arena_loop", "motif:plague_nurgling"]
    assert fixture["events_not_emitted"] == ["exploit_death_stinger", "exploit_victory_stinger", "next_battle_arena"]
    assert [entry["playback_class"] for entry in fixture["schedule"]["entries"]] == ["promoted", "promoted"]
    assert fixture["schedule"]["entries"][1]["authorization"]["permission_kind"] == "materialized_spawn"
    assert (local / "battle.normalized_music_fixture.json").read_bytes() == (public / "battle.normalized_music_fixture.json").read_bytes()
    assert validate_normalized_music_fixture_path(local / "battle.normalized_music_fixture.json")["status"] == "PASS"


def test_music_fixture_validation_rejects_runtime_path_leak(tmp_path: Path) -> None:
    fixture = json.loads((ROOT / "spectator/public/battle-fixtures/battle-004-music-runtime/battle.normalized_music_fixture.json").read_text())
    fixture["frontend_handoff"]["route"] = "/tmp/composer-workspace/output"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError, match="forbidden marker"):
        validate_normalized_music_fixture_path(path)


def test_music_fixture_validation_rejects_local_preview_in_authoritative_schedule(tmp_path: Path) -> None:
    fixture = json.loads((ROOT / "spectator/public/battle-fixtures/battle-004-music-runtime/battle.normalized_music_fixture.json").read_text())
    fixture["schedule"]["entries"][0]["playback_class"] = "local_preview"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError, match="playback_class=promoted"):
        validate_normalized_music_fixture_path(path)


def test_published_contract_examples_accept_valid_and_reject_invalid() -> None:
    base = ROOT / "local/battle-004-music-runtime/contract-fixtures"
    for valid_path in sorted((base / "valid").glob("*.json")):
        validate_document(json.loads(valid_path.read_text()))
    for invalid_path in sorted((base / "invalid").glob("*.json")):
        with pytest.raises(Exception):
            validate_document(json.loads(invalid_path.read_text()))
