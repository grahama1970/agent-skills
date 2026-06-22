from __future__ import annotations

import json
import pytest

from lib.orpheus_sfx import (
    MANIFEST_SCHEMA,
    PROMPT_REVIEW_SCHEMA,
    build_prompt_specs,
    generate_orpheus_sfx,
)


def test_build_prompt_specs_uses_native_tags_and_safety_constraints() -> None:
    specs = build_prompt_specs(tags=["laugh", "<yawn>"], samples_per_tag=2)

    assert [spec.tag for spec in specs] == ["laugh", "laugh", "yawn", "yawn"]
    assert all("no celebrity names" in spec.prompt for spec in specs)
    assert all("no words" in spec.prompt for spec in specs)


def test_generate_orpheus_sfx_dry_run_writes_review_bundle(tmp_path) -> None:
    manifest = generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path,
        tags=["laugh", "yawn"],
        samples_per_tag=1,
        dry_run=True,
    )

    assert manifest["schema"] == MANIFEST_SCHEMA
    assert manifest["dry_run"] is True
    assert manifest["requested"]["planned_count"] == 2
    assert manifest["counts_by_tag"] == {"<laugh>": 1, "<yawn>": 1}
    assert manifest["voice_segment_selector_candidates"]["count"] == 0

    review_path = tmp_path / "prompt-review" / "prompt_review_bundle.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["schema"] == PROMPT_REVIEW_SCHEMA
    assert review["reviewer"]["intended_subagent"] == "prompt-reviewer"
    assert len(review["prompts"]) == 2


def test_generate_orpheus_sfx_voice_tts_dry_run_records_voice_id(tmp_path) -> None:
    manifest = generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path,
        tags=["chuckle"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts",
        voice_id="voice_123",
        voice_name="Husky Female Candidate",
    )

    assert manifest["generation_mode"] == "voice-tts"
    assert manifest["requested"]["voice_id"] == "voice_123"
    assert manifest["requested"]["model_id"] == "eleven_v3"
    assert manifest["records"][0]["source_type"] == "elevenlabs_voice_sfx"
    assert manifest["records"][0]["source"] == "elevenlabs_text_to_speech_audio_tags"
    assert "[chuckles]" in manifest["records"][0]["prompt"]
    assert manifest["records"][0]["prompt"].strip("[") == manifest["records"][0]["prompt"]

    review_path = tmp_path / "prompt-review" / "prompt_review_bundle.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["generation_mode"] == "voice-tts"
    assert review["voice"]["voice_id"] == "voice_123"


def test_generate_orpheus_sfx_voice_tts_context_maps_prompt_to_tts_text(tmp_path) -> None:
    manifest = generate_orpheus_sfx(
        speaker="horus",
        out_dir=tmp_path,
        tags=["laugh"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts-context",
        voice_id="voice_horus",
        voice_name="James - Deep, Raspy and Grim",
    )

    record = manifest["records"][0]
    assert manifest["generation_mode"] == "voice-tts-context"
    assert manifest["requested"]["model_id"] == "eleven_v3"
    assert record["source_type"] == "elevenlabs_voice_context"
    assert record["source"] == "elevenlabs_text_to_speech_context_tags"
    assert record["prompt"].startswith("What do you mean?! [")
    assert "not a chuckle" in record["prompt"]
    assert record["tts_text"] == "What do you mean?! <laugh>"

    review_path = tmp_path / "prompt-review" / "prompt_review_bundle.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["generation_mode"] == "voice-tts-context"
    assert review["prompts"][0]["prompt"] == record["prompt"]
    assert review["prompts"][0]["tts_text"] == record["tts_text"]


def test_voice_tts_context_never_emits_pure_bracket_prompt_for_eleven_v3(tmp_path) -> None:
    manifest = generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path,
        tags=["cough", "gasp"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts-context",
        voice_id="voice_embry",
        voice_name="Embry Voice",
    )

    records = manifest["records"]
    assert records[0]["prompt"].startswith("I can't stop coughing... [")
    assert records[0]["tts_text"] == "I can't stop coughing... <cough>"
    assert records[1]["prompt"].startswith("Wait... [")
    assert records[1]["tts_text"] == "Wait... <gasp>"
    assert all(not record["prompt"].startswith("[") for record in records)


def test_second_pass_profile_uses_learned_stronger_laugh_prompt(tmp_path) -> None:
    manifest = generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path,
        tags=["laugh", "gasp"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts-context",
        prompt_profile="second-pass",
        voice_id="voice_embry",
        voice_name="Embry Voice",
    )

    laugh, gasp = manifest["records"]
    assert manifest["prompt_profile"] == "second-pass"
    assert "full belly laugh, not a chuckle" in laugh["prompt"]
    assert laugh["tts_text"] == "Wait, really?!!!!! <laugh>"
    assert gasp["prompt"] == "Oh! [tiny sharp inhale gasp!]"
    assert gasp["tts_text"] == "Oh! <gasp>"


def test_third_pass_profile_uses_remaining_gap_prompt_recipes(tmp_path) -> None:
    manifest = generate_orpheus_sfx(
        speaker="horus",
        out_dir=tmp_path,
        tags=["chuckle", "gasp"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts-context",
        prompt_profile="third-pass",
        voice_id="voice_horus",
        voice_name="Horus Voice",
    )
    embry_manifest = generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path / "embry",
        tags=["sigh"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts-context",
        prompt_profile="third-pass",
        voice_id="voice_embry",
        voice_name="Embry Voice",
    )

    chuckle, gasp = manifest["records"]
    sigh = embry_manifest["records"][0]
    assert chuckle["tts_text"] == "Hmph. <chuckle>"
    assert "short low dry chuckle" in chuckle["prompt"]
    assert gasp["tts_text"] == "Hah! <gasp>"
    assert "sharp startled inhale gasp" in gasp["prompt"]
    assert "no sigh" not in gasp["prompt"]
    assert sigh["tts_text"] == "Okay... <sigh>"
    assert "long breathy exhale sigh" in sigh["prompt"]


def test_third_pass_single_tag_gap_runs_do_not_fall_back_to_default_prompts(tmp_path) -> None:
    horus_manifest = generate_orpheus_sfx(
        speaker="horus",
        out_dir=tmp_path / "horus",
        tags=["gasp"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts-context",
        prompt_profile="third-pass",
        voice_id="voice_horus",
        voice_name="Horus Voice",
    )
    embry_manifest = generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path / "embry",
        tags=["sigh"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts-context",
        prompt_profile="third-pass",
        voice_id="voice_embry",
        voice_name="Embry Voice",
    )

    horus_gasp = horus_manifest["records"][0]
    embry_sigh = embry_manifest["records"][0]
    assert horus_gasp["prompt"] == "Hah! [sharp startled inhale gasp!!!!!! very short]"
    assert horus_gasp["tts_text"] == "Hah! <gasp>"
    assert embry_sigh["prompt"] == "Okay... [long breathy exhale sigh!!!!!! one smooth breath]"
    assert embry_sigh["tts_text"] == "Okay... <sigh>"
    horus_review = json.loads((tmp_path / "horus" / "prompt-review" / "prompt_review_bundle.json").read_text())
    embry_review = json.loads((tmp_path / "embry" / "prompt-review" / "prompt_review_bundle.json").read_text())
    assert horus_review["prompts"][0]["learned_provider_trigger_evidence"]
    assert embry_review["prompts"][0]["learned_provider_trigger_evidence"]
    assert "unproved carrier/dialogue words" in horus_review["policy"]["forbidden"]


def test_generate_orpheus_sfx_blocks_paid_generation_without_prompt_review(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")

    with pytest.raises(RuntimeError, match="prompt_review_required"):
        generate_orpheus_sfx(
            speaker="embry",
            out_dir=tmp_path,
            tags=["laugh"],
            samples_per_tag=1,
            generation_mode="voice-tts-context",
            voice_id="voice_embry",
            voice_name="Embry Voice",
        )


def test_generate_orpheus_sfx_allows_paid_generation_with_prompt_review_receipt(monkeypatch, tmp_path) -> None:
    generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path,
        tags=["laugh"],
        samples_per_tag=1,
        dry_run=True,
        generation_mode="voice-tts-context",
        voice_id="voice_embry",
        voice_name="Embry Voice",
    )
    receipt_path = tmp_path / "prompt-review" / "prompt-reviewer-receipt.json"
    receipt_path.write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    def fake_generate_voice_tts(*, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"mp3")
        return {"status": "ok", "status_code": 200, "bytes": 3, "request": kwargs}

    def fake_convert(mp3_path, wav_path):
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(b"wav")
        return {"status": "ok", "bytes": 3}

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr("lib.orpheus_sfx.elevenlabs_generate_voice_tts", fake_generate_voice_tts)
    monkeypatch.setattr("lib.orpheus_sfx.convert_to_wav24k", fake_convert)

    result = generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path,
        tags=["laugh"],
        samples_per_tag=1,
        generation_mode="voice-tts-context",
        voice_id="voice_embry",
        voice_name="Embry Voice",
    )

    assert result["prompt_review_status"]["ok"] is True
    assert result["records"][0]["status"] == "ok"


def test_generate_orpheus_sfx_reuses_existing_ok_wav(monkeypatch, tmp_path) -> None:
    wav = tmp_path / "wav24k" / "embry_cough_0001.wav"
    wav.parent.mkdir(parents=True)
    wav.write_bytes(b"existing")
    manifest = {
        "records": [
            {
                "id": "embry_cough_0001",
                "status": "ok",
                "orpheus_tag": "<cough>",
                "prompt": "I can't stop coughing... [old]",
                "tts_text": "I can't stop coughing... <cough>",
                "duration_seconds": 1.4,
                "wav_path": str(wav),
            }
        ]
    }
    (tmp_path / "elevenlabs_orpheus_sfx_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def fail_generate(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("existing ok WAV should be reused, not regenerated")

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr("lib.orpheus_sfx.elevenlabs_generate_voice_tts", fail_generate)

    result = generate_orpheus_sfx(
        speaker="embry",
        out_dir=tmp_path,
        tags=["cough"],
        samples_per_tag=1,
        generation_mode="voice-tts-context",
        voice_id="voice-id",
        voice_name="voice",
    )

    assert result["records"][0]["wav_path"] == str(wav)
    assert result["voice_segment_selector_candidates"]["count"] == 1


def test_yawn_context_uses_learned_sentence_trigger_for_horus_and_embry(tmp_path) -> None:
    for speaker in ("horus", "embry"):
        out_dir = tmp_path / speaker
        manifest = generate_orpheus_sfx(
            speaker=speaker,
            out_dir=out_dir,
            tags=["yawn"],
            samples_per_tag=1,
            dry_run=True,
            generation_mode="voice-tts-context",
            voice_id=f"voice_{speaker}",
            voice_name=f"{speaker.title()} Voice",
        )

        record = manifest["records"][0]
        assert record["prompt"] == "I'm so tired... [yawn!!!!!!]"
        assert record["tts_text"] == "I'm so tired... <yawn>"
        assert record["orpheus_tag"] == "<yawn>"

        review_path = out_dir / "prompt-review" / "prompt_review_bundle.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        assert review["prompts"][0]["prompt"] == "I'm so tired... [yawn!!!!!!]"
        assert review["prompts"][0]["tts_text"] == "I'm so tired... <yawn>"
        assert review["policy"]["minimal_carrier_sentence_allowed_when_learned_provider_trigger"] is True


def test_sniffle_context_uses_learned_sentence_trigger_for_horus_and_embry(tmp_path) -> None:
    for speaker in ("horus", "embry"):
        out_dir = tmp_path / speaker
        manifest = generate_orpheus_sfx(
            speaker=speaker,
            out_dir=out_dir,
            tags=["sniffle"],
            samples_per_tag=3,
            dry_run=True,
            generation_mode="voice-tts-context",
            voice_id=f"voice_{speaker}",
            voice_name=f"{speaker.title()} Voice",
        )

        first, second, third = manifest["records"][:3]
        assert first["prompt"] == "I've got a bad cold.. [sniffle!!!!!!]"
        assert first["tts_text"] == "I've got a bad cold.. <sniffle>"
        assert first["orpheus_tag"] == "<sniffle>"
        assert second["prompt"] == "I've got a bad cold.. [sniffle sniffle sniffle!!!!!!]"
        assert second["tts_text"] == "I've got a bad cold.. <sniffle>"
        assert second["orpheus_tag"] == "<sniffle>"
        assert third["prompt"] == "I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]"
        assert third["tts_text"] == "I've got a bad cold.. <sniffle>"
        assert third["orpheus_tag"] == "<sniffle>"

        review_path = out_dir / "prompt-review" / "prompt_review_bundle.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        assert review["prompts"][0]["prompt"] == "I've got a bad cold.. [sniffle!!!!!!]"
        assert review["prompts"][0]["tts_text"] == "I've got a bad cold.. <sniffle>"
        assert review["prompts"][1]["prompt"] == "I've got a bad cold.. [sniffle sniffle sniffle!!!!!!]"
        assert review["prompts"][1]["tts_text"] == "I've got a bad cold.. <sniffle>"
        assert review["prompts"][2]["prompt"] == "I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]"
        assert review["prompts"][2]["tts_text"] == "I've got a bad cold.. <sniffle>"
        assert review["policy"]["minimal_carrier_sentence_allowed_when_learned_provider_trigger"] is True


def test_write_review_candidates_uses_review_server_path(tmp_path) -> None:
    records = [
        {
            "id": "horus_laugh_0001",
            "status": "ok",
            "orpheus_tag": "<laugh>",
            "prompt": "[1.2 second full belly laugh with three clear pulses; no speech; not a chuckle]",
            "tts_text": "<laugh>",
            "duration_seconds": 1.4,
            "wav_path": str(tmp_path / "horus_laugh_0001.wav"),
            "source_type": "elevenlabs_voice_context",
            "source": "elevenlabs_text_to_speech_context_tags",
            "generation_mode": "voice-tts-context",
            "voice_id": "voice_123",
            "voice_name": "Horus Voice",
            "model_id": "eleven_v3",
            "prompt_review_bundle": str(tmp_path / "prompt-review" / "prompt_review_bundle.json"),
        }
    ]

    from lib.orpheus_sfx import write_review_candidates
    from lib.review import filter_srt_review_candidates

    candidates_path, count = write_review_candidates(records, tmp_path, speaker="horus")

    assert count == 1
    assert candidates_path == tmp_path / "voice_segment_selector_candidates.jsonl"
    assert (tmp_path / "candidates.jsonl").exists()
    rows = [json.loads(line) for line in (tmp_path / "candidates.jsonl").read_text().splitlines()]
    assert filter_srt_review_candidates(rows)[0]["id"] == "horus_laugh_0001"
