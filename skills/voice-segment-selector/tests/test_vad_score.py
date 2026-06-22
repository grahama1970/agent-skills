import json
import numpy as np
import pytest
import sys
import types

from lib.audio_io import write_clip_array
from lib.bundle import build_bundle, select_collection
from lib.export import _literal_tag_asr_check_clip, export_dataset, export_orpheus_dataset
from lib.prepare import _process_span_range
from lib.review import render_review_html, save_selection
from lib.score import score_clip
from lib.vad import detect_speech_spans, merge_intervals


def test_merge_intervals():
    merged = merge_intervals([(0.0, 1.0), (1.2, 2.0), (5.0, 6.0)], 0.45)
    assert merged == [(0.0, 2.0), (5.0, 6.0)]


def test_detect_speech_spans_on_tone():
    sr = 16000
    y = np.zeros(sr * 10, dtype=np.float32)
    y[sr * 2 : sr * 8] = 0.2 * np.sin(2 * np.pi * 180 * np.arange(sr * 6) / sr)
    spans = detect_speech_spans(y, sr, min_clip_sec=3.0, max_clip_sec=8.0, top_db=35)
    assert isinstance(spans, list)


def test_score_clip_positive():
    sr = 16000
    t = np.arange(sr * 5) / sr
    y = (0.08 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    score, metrics = score_clip(y, sr)
    assert score > 0.2
    assert "speech_ratio" in metrics


def test_process_chapter_shifted_spans_use_local_audio_for_scoring(tmp_path):
    sr = 16000
    full = np.zeros(sr * 12, dtype=np.float32)
    local = np.zeros(sr * 2, dtype=np.float32)
    tone = (0.12 * np.sin(2 * np.pi * 120 * np.arange(sr) / sr)).astype(np.float32)
    full[int(10.5 * sr) : int(11.5 * sr)] = tone
    local[int(0.5 * sr) : int(1.5 * sr)] = tone

    source_wav = tmp_path / "source.wav"
    write_clip_array(full, sr, source_wav)
    raw_dir = tmp_path / "clips" / "raw"

    rows, idx = _process_span_range(
        y=local,
        sr=sr,
        source_label="source.wav::chapter",
        source_wav=source_wav,
        raw_dir=raw_dir,
        spans=[(10.5, 11.5)],
        classifier="f0",
        hf_pipe=None,
        transcribe=False,
        language="en",
        start_index=0,
        slice_offset_sec=10.0,
    )

    assert idx == 1
    assert rows[0].start_sec == 10.5
    assert rows[0].end_sec == 11.5
    assert rows[0].quality_score > 0.2
    assert (tmp_path / rows[0].clip).exists()


def test_select_collection_uses_saved_order_when_supplied():
    rows = [
        {"id": "0001", "start_sec": 0.0, "duration_sec": 10.0, "gender_label": "female", "gender_score": 0.9, "rank_score": 0.9},
        {"id": "0002", "start_sec": 10.0, "duration_sec": 10.0, "gender_label": "female", "gender_score": 0.9, "rank_score": 0.1},
        {"id": "0003", "start_sec": 20.0, "duration_sec": 10.0, "gender_label": "female", "gender_score": 0.9, "rank_score": 0.8},
    ]

    chosen = select_collection(rows, target_sec=15.0, gender="female", min_score=0.0, ordered_ids=["0002", "0001"])

    assert [row["id"] for row in chosen] == ["0002", "0001"]
    assert chosen[1]["use_duration_sec"] == 5.0


def test_export_dataset_rejects_missing_transcripts_by_default(tmp_path):
    job_dir = tmp_path / "job"
    raw_dir = job_dir / "clips" / "raw"
    raw_dir.mkdir(parents=True)
    write_clip_array(np.zeros(16000, dtype=np.float32), 16000, raw_dir / "0001.wav")
    write_clip_array(np.zeros(16000, dtype=np.float32), 16000, raw_dir / "0002.wav")
    (job_dir / "candidates.jsonl").write_text(
        "\n".join(
            [
                '{"id":"0001","clip":"clips/raw/0001.wav","source":"fixture","start_sec":0,"end_sec":1,"duration_sec":1,"gender_label":"female","quality_score":0.9,"rank_score":0.9,"transcript":"clean words","status":"accepted"}',
                '{"id":"0002","clip":"clips/raw/0002.wav","source":"fixture","start_sec":1,"end_sec":2,"duration_sec":1,"gender_label":"female","quality_score":0.9,"rank_score":0.8,"transcript":"","status":"accepted"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = export_dataset(job_dir=job_dir, out_dir=tmp_path / "dataset")

    assert summary["exported_clips"] == 1
    assert summary["rejected_clips"] == 1
    assert "clean words" in (tmp_path / "dataset" / "metadata.jsonl").read_text(encoding="utf-8")
    assert "missing_transcript" in (tmp_path / "dataset" / "rejected.jsonl").read_text(encoding="utf-8")


def test_literal_tag_asr_check_rejects_spoken_event_word(tmp_path, monkeypatch):
    wav = tmp_path / "clip.wav"
    write_clip_array(np.zeros(16000, dtype=np.float32), 16000, wav)
    fake_transcribe = types.ModuleType("lib.transcribe")
    fake_transcribe.transcribe_clip = lambda path: ("I've got a bad cold. Cough. Continue.", 0.51)
    monkeypatch.setitem(sys.modules, "lib.transcribe", fake_transcribe)

    check = _literal_tag_asr_check_clip(wav, ["<cough>"])

    assert check["status"] == "FAIL"
    assert check["reason"] == "literal_tag_spoken"
    assert check["spoken_literal_tags"] == ["cough"]


def test_literal_tag_asr_check_allows_tag_word_already_in_spoken_text(tmp_path, monkeypatch):
    wav = tmp_path / "clip.wav"
    write_clip_array(np.zeros(16000, dtype=np.float32), 16000, wav)
    fake_transcribe = types.ModuleType("lib.transcribe")
    fake_transcribe.transcribe_clip = lambda path: ("I can't stop coughing.", 0.61)
    monkeypatch.setitem(sys.modules, "lib.transcribe", fake_transcribe)

    check = _literal_tag_asr_check_clip(wav, ["<cough>"], "I can't stop coughing.")

    assert check["status"] == "PASS"
    assert check["spoken_literal_tags"] == []


def test_export_orpheus_rejects_literal_spoken_tag_before_training_manifest(tmp_path, monkeypatch):
    pytest.importorskip("datasets")
    job_dir = tmp_path / "job"
    raw_dir = job_dir / "clips" / "raw"
    raw_dir.mkdir(parents=True)
    write_clip_array(np.zeros(16000, dtype=np.float32), 16000, raw_dir / "0001.wav")
    (job_dir / "candidates.jsonl").write_text(
        json.dumps(
            {
                "id": "0001",
                "clip": "clips/raw/0001.wav",
                "source": "fixture",
                "start_sec": 0,
                "end_sec": 1,
                "duration_sec": 1,
                "quality_score": 0.9,
                "rank_score": 0.9,
                "plain_caption": "Continue.",
                "tts_text": "<cough> Continue.",
                "emotion_tags": ["<cough>"],
                "review_status": "human",
                "status": "accepted",
                "accepted_by": "human",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fake_transcribe = types.ModuleType("lib.transcribe")
    fake_transcribe.transcribe_clip = lambda path: ("Cough. Continue.", 0.51)
    monkeypatch.setitem(sys.modules, "lib.transcribe", fake_transcribe)

    summary = export_orpheus_dataset(job_dir=job_dir, out_dir=tmp_path / "orpheus", speaker="fixture")

    assert summary["example_count"] == 0
    rejected = (tmp_path / "orpheus" / "rejected.jsonl").read_text(encoding="utf-8")
    assert "literal_tag_spoken" in rejected
    assert "Cough. Continue." in rejected


def test_render_review_html_exposes_audio_selection_and_exports(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "candidates.jsonl").write_text("", encoding="utf-8")
    html = render_review_html(
        job_dir,
        [
            {
                "id": "0001",
                "clip": "clips/raw/0001.wav",
                "start_sec": 0,
                "end_sec": 8,
                "duration_sec": 8,
                "gender_label": "female",
                "gender_classifier": "f0",
                "quality_score": 0.8,
                "rank_score": 0.9,
                "transcript": "example words",
            }
        ],
    )

    assert 'class="play-btn"' in html and "shared-player" in html
    assert "Selected Takes" in html
    assert "Export Orpheus HF dataset" in html
    assert "Save selection.json" in html


def test_build_bundle_reports_selection_source_and_provider_not_ready(tmp_path):
    job_dir = tmp_path / "job"
    raw_dir = job_dir / "clips" / "raw"
    workdir = job_dir / "_work"
    raw_dir.mkdir(parents=True)
    workdir.mkdir(parents=True)
    source = np.zeros(16000 * 4, dtype=np.float32)
    source[: 16000 * 4] = (0.05 * np.sin(2 * np.pi * 120 * np.arange(16000 * 4) / 16000)).astype(np.float32)
    write_clip_array(source, 16000, workdir / "source.mono16k.wav")
    (job_dir / "candidates.jsonl").write_text(
        "\n".join(
            [
                '{"id":"0001","clip":"clips/raw/0001.wav","source":"fixture","start_sec":0,"end_sec":2,"duration_sec":2,"gender_label":"male","gender_score":0.9,"quality_score":0.9,"rank_score":0.9,"status":"pending"}',
                '{"id":"0002","clip":"clips/raw/0002.wav","source":"fixture","start_sec":2,"end_sec":4,"duration_sec":2,"gender_label":"male","gender_score":0.9,"quality_score":0.9,"rank_score":0.1,"status":"pending"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    save_selection(job_dir, ["0002", "0001"])

    payload = build_bundle(job_dir=job_dir, out_path=tmp_path / "selected.wav", gender="male", target_sec=3, min_score=0.0)

    assert payload["selection_source"] == "selection.json"
    assert payload["status"] == "CLONE_REFERENCE_CANDIDATE_NOT_PROVIDER_READY"
    assert [part["id"] for part in payload["parts"]] == ["0002", "0001"]
    assert (tmp_path / "selected.wav").exists()

def test_filter_srt_review_candidates_keeps_movie_slices_and_orpheus_sfx():
    from lib.review import filter_srt_review_candidates, is_sfx_review_candidate, is_srt_review_candidate

    movie_slice = {
        "id": "1",
        "tag_source": "release-srt-slice",
        "source": "phase-a-movie:twilight-amzn-2008:laugh",
        "prepare_mode": "srt-slice",
        "audio_track": "eng",
        "transcript": "<laugh> Hi, Bella.",
    }
    phase_b_slice = {
        "id": "6",
        "tag_source": "release-srt-slice",
        "source": "phase-b-movie:new-moon-2009:gasp",
        "prepare_mode": "srt-slice",
        "audio_track": "eng",
        "transcript": "<gasp> It's like diamonds.",
    }
    rows = [
        movie_slice,
        {"id": "2", "tag_source": "prosody-heuristic", "transcript": "<chuckle> pause"},
        {"id": "3", "tag_source": "none", "transcript": "plain speech"},
        {
            "id": "4",
            "tag_source": "phase-a-twilight",
            "source": "phase-a-twilight:VWkD1KMuw5w:sigh",
            "transcript": "<sigh> interview line",
        },
        {
            "id": "5",
            "tag_source": "release-srt-slice",
            "source": "phase-a-movie:twilight-amzn-2008:chuckle",
            "prepare_mode": "srt-slice",
            "transcript": "",
        },
        {
            "id": "7",
            "source_type": "sfx",
            "emotion_tags": ["<yawn>"],
            "review_status": "pending",
            "transcript": "<yawn>",
        },
        {
            "id": "8",
            "source_type": "sfx",
            "emotion_tags": ["<giggle>"],
            "review_status": "pending",
            "transcript": "<giggle>",
        },
    ]
    assert is_srt_review_candidate(movie_slice)
    assert is_srt_review_candidate(phase_b_slice)
    assert not is_srt_review_candidate(rows[1])
    assert not is_srt_review_candidate(rows[3])
    assert not is_srt_review_candidate(rows[4])
    assert is_sfx_review_candidate(rows[5])
    assert not is_sfx_review_candidate(rows[6])
    assert filter_srt_review_candidates(rows + [phase_b_slice]) == [movie_slice, rows[5], phase_b_slice]



def test_save_trim_writes_shortened_wav(tmp_path):
    import json
    import struct
    import wave
    from lib.review import save_trim

    job = tmp_path / "job"
    clips = job / "clips" / "raw"
    clips.mkdir(parents=True)
    wav = clips / "0001.wav"
    rate = 16000
    samples = [0] * (rate * 2) + [20000] * (rate * 2)
    with wave.open(str(wav), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    (job / "candidates.jsonl").write_text(
        json.dumps({"id": "0001", "clip": "clips/raw/0001.wav", "duration_sec": 4.0}) + "\n"
    )

    updated = save_trim(job, "0001", 2.0, 4.0)
    assert updated["duration_sec"] == pytest.approx(2.0, abs=0.05)
    assert len(updated["trim_history"]) == 1
