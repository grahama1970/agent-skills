#!/usr/bin/env python3
"""voice-segment-selector CLI."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.bundle import build_bundle
from lib.export import export_dataset, export_orpheus_dataset
from lib.gender import ClassifierMode
from lib.analyze import analyze_job
from lib.prepare import prepare_job, prepare_multi_job
from lib.prepare_aligned import prepare_aligned_job
from lib.sources import load_sources
from lib.tag_propose import tag_propose_job
from lib.review import append_decision, serve_review
from lib.orpheus_handoff import default_checkpoint_dir, publish_orpheus_model, run_inference_smoke
from lib.orpheus_audio_classifier import classify_audio_file, classify_manifest
from lib.orpheus_sfx import ORPHEUS_TAGS, generate_orpheus_sfx
from lib.verify_job import verify_aligned_job, verify_vad_job, write_verify_receipt
from lib.maintainer_ticket import build_ticket_packet, file_github_issue

app = typer.Typer(add_completion=False, help="Select clean gender-bucketed voice segments for TTS training")


def default_job_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Path(f"/tmp/voice-segment-selector-{stamp}")


@app.command()
def prepare(
    inputs: list[str] = typer.Option(
        None,
        "--input",
        help="Repeat for multiple local files. YouTube URLs also work when download is enabled.",
    ),
    inputs_file: Path | None = typer.Option(
        None,
        "--inputs-file",
        help="JSON/JSONL/text file listing paths or YouTube URLs (one per line or JSON objects).",
    ),
    job_dir: Path | None = typer.Option(None, "--job-dir", help="Job output directory"),
    classifier: ClassifierMode = typer.Option("both", "--classifier", help="f0, hf, or both"),
    min_clip_sec: float = typer.Option(6.0, "--min-clip-sec"),
    max_clip_sec: float = typer.Option(18.0, "--max-clip-sec"),
    no_transcribe: bool = typer.Option(False, "--no-transcribe"),
    language: str = typer.Option("en", "--language"),
    chapters_json: Path | None = typer.Option(None, "--chapters-json"),
    max_duration_sec: float = typer.Option(7200.0, "--max-duration-sec"),
    start_sec: float | None = typer.Option(None, "--start-sec", help="Single-input only: absolute start time in seconds"),
    end_sec: float | None = typer.Option(None, "--end-sec", help="Single-input only: absolute end time in seconds"),
    download_youtube: bool = typer.Option(
        True,
        "--download-youtube/--no-download-youtube",
        help="Download YouTube URLs with yt-dlp before prepare.",
    ),
) -> None:
    """Normalize, split, score, classify, and transcribe candidate clips."""
    out = job_dir or default_job_dir()
    sources = load_sources(inputs=inputs, inputs_file=inputs_file)
    if len(sources) == 1 and chapters_json is None and start_sec is None and end_sec is None:
        input_path = Path(sources[0].value).expanduser()
        if sources[0].is_youtube:
            manifest = prepare_multi_job(
                sources=sources,
                job_dir=out,
                classifier=classifier,
                min_clip_sec=min_clip_sec,
                max_clip_sec=max_clip_sec,
                transcribe=not no_transcribe,
                language=language,
                max_duration_sec=max_duration_sec,
                download_youtube=download_youtube,
            )
        else:
            manifest = prepare_job(
                input_path=input_path,
                job_dir=out,
                classifier=classifier,
                min_clip_sec=min_clip_sec,
                max_clip_sec=max_clip_sec,
                transcribe=not no_transcribe,
                language=language,
                chapters_json=chapters_json,
                max_duration_sec=max_duration_sec,
                start_sec=sources[0].start_sec if sources[0].start_sec is not None else start_sec,
                end_sec=sources[0].end_sec if sources[0].end_sec is not None else end_sec,
            )
    elif len(sources) == 1 and (chapters_json is not None or start_sec is not None or end_sec is not None):
        source = sources[0]
        if source.is_youtube:
            raise typer.BadParameter("Use --inputs-file per-source ranges for YouTube URLs with start/end.")
        manifest = prepare_job(
            input_path=Path(source.value).expanduser(),
            job_dir=out,
            classifier=classifier,
            min_clip_sec=min_clip_sec,
            max_clip_sec=max_clip_sec,
            transcribe=not no_transcribe,
            language=language,
            chapters_json=chapters_json,
            max_duration_sec=max_duration_sec,
            start_sec=source.start_sec if source.start_sec is not None else start_sec,
            end_sec=source.end_sec if source.end_sec is not None else end_sec,
        )
    else:
        if chapters_json is not None:
            raise typer.BadParameter("--chapters-json is supported for single local audiobook inputs only.")
        if start_sec is not None or end_sec is not None:
            raise typer.BadParameter("Use per-source start_sec/end_sec in --inputs-file for multi-input jobs.")
        manifest = prepare_multi_job(
            sources=sources,
            job_dir=out,
            classifier=classifier,
            min_clip_sec=min_clip_sec,
            max_clip_sec=max_clip_sec,
            transcribe=not no_transcribe,
            language=language,
            max_duration_sec=max_duration_sec,
            download_youtube=download_youtube,
        )
    typer.echo(json.dumps(manifest, indent=2))



@app.command("prepare-aligned")
def prepare_aligned(
    input_path: Path = typer.Option(..., "--input", help="Local video/audio file"),
    job_dir: Path | None = typer.Option(None, "--job-dir"),
    language: str = typer.Option("en", "--language"),
    speaker_id: str | None = typer.Option(None, "--speaker-id", help="Keep only this diarized speaker id"),
    min_speaker_overlap: float = typer.Option(0.55, "--min-speaker-overlap"),
    min_clip_sec: float = typer.Option(6.0, "--min-clip-sec"),
    max_clip_sec: float = typer.Option(18.0, "--max-clip-sec"),
    classifier: ClassifierMode = typer.Option("f0", "--classifier"),
    whisper_model: str = typer.Option("base", "--whisper-model"),
    device: str = typer.Option("auto", "--device", help="auto, cuda, or cpu"),
    hf_token: str | None = typer.Option(None, "--hf-token"),
    start_sec: float | None = typer.Option(None, "--start-sec"),
    end_sec: float | None = typer.Option(None, "--end-sec"),
) -> None:
    """WhisperX alignment + pyannote diarization -> utterance clips."""
    out = job_dir or default_job_dir()
    manifest = prepare_aligned_job(
        input_path=input_path.expanduser(),
        job_dir=out,
        language=language,
        speaker_id=speaker_id,
        min_speaker_overlap=min_speaker_overlap,
        min_clip_sec=min_clip_sec,
        max_clip_sec=max_clip_sec,
        classifier=classifier,
        whisper_model=whisper_model,
        device=device,
        hf_token=hf_token,
        start_sec=start_sec,
        end_sec=end_sec,
    )
    typer.echo(json.dumps(manifest, indent=2))


@app.command()
def analyze(
    job_dir: Path = typer.Option(..., "--job-dir"),
    clip_id: list[str] = typer.Option(None, "--id"),
    limit: int = typer.Option(0, "--limit"),
    no_emotion: bool = typer.Option(False, "--no-emotion"),
    no_prosody: bool = typer.Option(False, "--no-prosody"),
) -> None:
    """Prosody events + weak emotion sidecars for aligned candidates."""
    summary = analyze_job(
        job_dir=job_dir,
        clip_ids=clip_id,
        run_emotion=not no_emotion,
        run_prosody=not no_prosody,
        limit=limit,
    )
    typer.echo(json.dumps(summary, indent=2))



@app.command("tag-propose")
def tag_propose(
    job_dir: Path = typer.Option(..., "--job-dir"),
    gender: str | None = typer.Option(None, "--gender"),
    clip_id: list[str] = typer.Option(None, "--id", help="Repeat to limit to specific clip ids"),
    limit: int = typer.Option(0, "--limit", help="Max clips to process (0 = all matching)"),
    no_scillm: bool = typer.Option(False, "--no-scillm", help="Skip scillm; local prosody/caption only"),
    audio_llm: bool = typer.Option(False, "--audio-llm", help="Use Gemini audio (expensive); default is text-only chutes-deepseek"),
    scillm_refine: bool = typer.Option(False, "--scillm-refine", help="On aligned jobs: chutes text refine when prosody found no tags"),
    force: bool = typer.Option(False, "--force", help="Re-run even if tts_text_candidate exists"),
    auto_insert_high_confidence: bool = typer.Option(
        False,
        "--auto-insert-high-confidence",
        help="Opt-in: copy high-confidence tag candidates into tts_text (default: sidecar only).",
    ),
    scillm_url: str | None = typer.Option(None, "--scillm-url"),
    scillm_auth: str | None = typer.Option(None, "--scillm-auth"),
    model: str = typer.Option("chutes-deepseek", "--model", help="Text-only scillm model (default: chutes-deepseek)"),
) -> None:
    """Propose Orpheus event tags from clip audio + draft transcript."""
    summary = tag_propose_job(
        job_dir=job_dir,
        gender=gender,
        clip_ids=clip_id,
        limit=limit,
        use_scillm=not no_scillm,
        force=force,
        auto_insert_high_confidence=auto_insert_high_confidence,
        scillm_url=scillm_url,
        scillm_auth=scillm_auth,
        model=model,
        use_audio_llm=audio_llm,
        use_scillm_refine=scillm_refine,
    )
    typer.echo(json.dumps(summary, indent=2))

@app.command()
def review(
    job_dir: Path = typer.Option(..., "--job-dir"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8791, "--port"),
) -> None:
    """Start a lightweight HTTP review API."""
    serve_review(job_dir, host=host, port=port)


@app.command("decide")
def decide(
    job_dir: Path = typer.Option(..., "--job-dir"),
    clip_id: str = typer.Option(..., "--id"),
    decision: str = typer.Option(..., "--decision", help="accept, reject, or maybe"),
) -> None:
    """Record a human review decision for one clip."""
    append_decision(job_dir, clip_id, decision)
    typer.echo(json.dumps({"id": clip_id, "decision": decision}, indent=2))


@app.command()
def export(
    job_dir: Path = typer.Option(..., "--job-dir"),
    out_dir: Path = typer.Option(None, "--out-dir"),
    gender: str | None = typer.Option(None, "--gender", help="male, female, or omit for all"),
    auto_accept_top: int = typer.Option(0, "--auto-accept-top", help="Auto-export top N ranked clips"),
    allow_empty_transcript: bool = typer.Option(
        False,
        "--allow-empty-transcript",
        help="Allow metadata export without transcripts. Use only with explicit human approval.",
    ),
) -> None:
    """Export accepted clips to a TTS-ready dataset with metadata.jsonl."""
    target = out_dir or (job_dir / "voice-dataset")
    summary = export_dataset(
        job_dir=job_dir,
        out_dir=target,
        gender=gender,
        auto_accept_top=auto_accept_top,
        allow_empty_transcript=allow_empty_transcript,
    )
    typer.echo(json.dumps(summary, indent=2))


@app.command("export-orpheus")
def export_orpheus(
    job_dir: Path = typer.Option(..., "--job-dir"),
    speaker: str = typer.Option(..., "--speaker", help="Speaker/persona id"),
    out_dir: Path = typer.Option(None, "--out-dir"),
    gender: str | None = typer.Option(None, "--gender", help="male, female, or omit for all"),
) -> None:
    """Export accepted transcript-backed clips as an Orpheus/Hugging Face dataset."""
    target = out_dir or (job_dir / "orpheus-dataset")
    summary = export_orpheus_dataset(
        job_dir=job_dir,
        out_dir=target,
        speaker=speaker,
        gender=gender,
    )
    typer.echo(json.dumps(summary, indent=2))


@app.command("generate-orpheus-sfx")
def generate_orpheus_sfx_command(
    speaker: str = typer.Option("embry", "--speaker", help="Target speaker/persona id"),
    job_dir: Path = typer.Option(..., "--job-dir", help="voice-segment-selector job directory to populate"),
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated Orpheus tags; default all native tags"),
    samples_per_tag: int = typer.Option(4, "--samples-per-tag", min=1),
    duration_seconds: float = typer.Option(1.4, "--duration-seconds", min=0.5, max=10.0),
    generation_mode: str = typer.Option(
        "sound-generation",
        "--generation-mode",
        help="sound-generation for generic SFX, voice-tts for isolated Eleven v3 voice_id audio tags, voice-tts-context for bracketed emotion plus speech context",
    ),
    prompt_profile: str = typer.Option(
        "default",
        "--prompt-profile",
        help="Prompt profile for voice-tts-context generation: default, second-pass, or third-pass",
    ),
    voice_id: str | None = typer.Option(None, "--voice-id", help="ElevenLabs voice_id for --generation-mode voice-tts"),
    voice_name: str | None = typer.Option(None, "--voice-name", help="Human-readable selected ElevenLabs voice name"),
    model_id: str = typer.Option("eleven_v3", "--model-id", help="ElevenLabs TTS model for voice-tts mode"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Write prompt-review bundle and planned manifest without API calls"),
    no_candidates: bool = typer.Option(False, "--no-candidates", help="Do not write candidate JSONL"),
) -> None:
    """Generate ElevenLabs SFX gap-fill candidates for Orpheus-native emotion tags.

    This creates synthetic candidates with explicit provenance. Movie-curated
    clips remain preferred when available.
    """
    selected_tags = ORPHEUS_TAGS if tags is None else tuple(tag.strip() for tag in tags.split(",") if tag.strip())
    manifest = generate_orpheus_sfx(
        speaker=speaker,
        out_dir=job_dir,
        tags=selected_tags,
        samples_per_tag=samples_per_tag,
        duration_seconds=duration_seconds,
        dry_run=dry_run,
        write_candidates=not no_candidates,
        generation_mode=generation_mode,  # type: ignore[arg-type]
        prompt_profile=prompt_profile,  # type: ignore[arg-type]
        voice_id=voice_id,
        voice_name=voice_name,
        model_id=model_id,
    )
    typer.echo(json.dumps(manifest, indent=2))


@app.command("classify-orpheus-sfx")
def classify_orpheus_sfx_command(
    manifest_path: Path | None = typer.Option(
        None,
        "--manifest",
        help="Path to elevenlabs_orpheus_sfx_manifest.json. Defaults to --job-dir/elevenlabs_orpheus_sfx_manifest.json.",
    ),
    job_dir: Path | None = typer.Option(None, "--job-dir", help="Synthetic SFX job directory"),
    audio_path: Path | None = typer.Option(None, "--audio", help="Classify one audio file instead of a manifest"),
    expected_tag: str | None = typer.Option(None, "--expected-tag", help="Expected Orpheus tag for --audio"),
    out_path: Path | None = typer.Option(None, "--out", help="Classifier receipt path"),
    model_name: str = typer.Option("MIT/ast-finetuned-audioset-16-16-0.442", "--model"),
    top_k: int = typer.Option(12, "--top-k", min=1, max=50),
    min_label_score: float = typer.Option(0.08, "--min-label-score", min=0.0, max=1.0),
    hard_neighbor_reject_score: float = typer.Option(0.20, "--hard-neighbor-reject-score", min=0.0, max=1.0),
    no_ast: bool = typer.Option(False, "--no-ast", help="Use waveform gate only; no Hugging Face AST model"),
) -> None:
    """Classify Orpheus SFX candidates with AudioSet labels plus waveform gates."""
    if audio_path is not None:
        if not expected_tag:
            raise typer.BadParameter("--expected-tag is required with --audio")
        result = classify_audio_file(
            audio_path,
            expected_tag=expected_tag,
            model_name=model_name,
            top_k=top_k,
            min_label_score=min_label_score,
            hard_neighbor_reject_score=hard_neighbor_reject_score,
            use_ast=not no_ast,
        )
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            result["classifier_result_path"] = str(out_path.resolve())
    else:
        manifest = manifest_path
        if manifest is None:
            if job_dir is None:
                raise typer.BadParameter("Provide --manifest, --job-dir, or --audio")
            manifest = job_dir / "elevenlabs_orpheus_sfx_manifest.json"
        result = classify_manifest(
            manifest_path=manifest,
            out_path=out_path,
            model_name=model_name,
            top_k=top_k,
            min_label_score=min_label_score,
            hard_neighbor_reject_score=hard_neighbor_reject_score,
            use_ast=not no_ast,
        )
    typer.echo(json.dumps(result, indent=2))


@app.command()
def bundle(
    job_dir: Path = typer.Option(..., "--job-dir"),
    gender: str = typer.Option(..., "--gender"),
    target_sec: float = typer.Option(30.0, "--target-sec"),
    out: Path = typer.Option(None, "--out"),
) -> None:
    """Build one WAV of target duration from ranked clips."""
    output = out or (job_dir / f"{gender}_best_{int(target_sec)}s.wav")
    payload = build_bundle(job_dir=job_dir, out_path=output, gender=gender, target_sec=target_sec)
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def verify(
    job_dir: Path = typer.Option(..., "--job-dir"),
    mode: str = typer.Option("auto", "--mode", help="auto, aligned, or vad"),
    min_candidates: int = typer.Option(1, "--min-candidates"),
    speaker_id: str | None = typer.Option(None, "--speaker-id"),
    require_cuda_if_available: bool = typer.Option(
        True,
        "--require-cuda-if-available/--allow-cpu-when-cuda-available",
    ),
    write_receipt: bool = typer.Option(True, "--write-receipt/--no-write-receipt"),
) -> None:
    """Deterministic post-run verification for a job directory."""
    resolved_mode = mode
    if mode == "auto":
        manifest_path = job_dir / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            resolved_mode = manifest.get("prepare_mode") or "vad"
        else:
            resolved_mode = "vad"

    if resolved_mode == "aligned":
        result = verify_aligned_job(
            job_dir,
            min_candidates=min_candidates,
            speaker_id=speaker_id,
            require_cuda_if_available=require_cuda_if_available,
        )
    elif resolved_mode == "vad":
        result = verify_vad_job(job_dir, min_candidates=min_candidates)
    else:
        raise typer.BadParameter("mode must be auto, aligned, or vad")

    if write_receipt:
        receipt = write_verify_receipt(job_dir, result)
        result["verify_receipt"] = str(receipt.resolve())

    typer.echo(json.dumps(result, indent=2))
    if result.get("status") != "PASS":
        raise typer.Exit(code=1)


@app.command("file-maintainer-ticket")
def file_maintainer_ticket(
    job_dir: Path = typer.Option(..., "--job-dir"),
    mode: str = typer.Option("auto", "--mode", help="auto, aligned, or vad"),
    reference_source: str | None = typer.Option(
        None,
        "--reference-source",
        help="Optional absolute path/URL used in maintainer repro block",
    ),
    notes: str | None = typer.Option(None, "--notes"),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo"),
    create: bool = typer.Option(False, "--create", help="Create GitHub issue via gh"),
    require_fail: bool = typer.Option(
        True,
        "--require-fail/--allow-pass",
        help="Only file when verify status is FAIL",
    ),
) -> None:
    """Build (and optionally create) a skill-maintainer GitHub ticket from verify output."""
    resolved_mode = mode
    if mode == "auto":
        manifest_path = job_dir / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            resolved_mode = manifest.get("prepare_mode") or "vad"
        else:
            resolved_mode = "vad"

    if resolved_mode == "aligned":
        verify_result = verify_aligned_job(job_dir)
    else:
        verify_result = verify_vad_job(job_dir)

    write_verify_receipt(job_dir, verify_result)

    if require_fail and verify_result.get("status") == "PASS":
        typer.echo(json.dumps({"status": "SKIP", "reason": "verify PASS"}, indent=2))
        raise typer.Exit(code=0)

    packet = build_ticket_packet(
        verify_result,
        reference_source=reference_source,
        notes=notes,
    )
    packet_path = job_dir / "maintainer-ticket.json"
    packet_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    packet["packet_path"] = str(packet_path.resolve())

    if create:
        filed = file_github_issue(
            title=packet["title"],
            body=packet["body"],
            repo=repo,
            labels=packet["labels"],
            dry_run=False,
        )
        packet["filed"] = filed
        if not filed.get("ok"):
            typer.echo(json.dumps(packet, indent=2))
            raise typer.Exit(code=1)

    typer.echo(json.dumps(packet, indent=2))
    if verify_result.get("status") != "PASS":
        raise typer.Exit(code=1)



@app.command("inference-smoke")
def inference_smoke(
    speaker: str = typer.Option(..., "--speaker", help="Persona/speaker id used in prompts"),
    lora_dir: Path | None = typer.Option(None, "--lora-dir"),
    output_dir: Path | None = typer.Option(None, "--out-dir"),
    prompt: str | None = typer.Option(None, "--prompt"),
    load_in_4bit: bool = typer.Option(True, "--load-in-4bit/--no-4bit"),
) -> None:
    """Generate a live GPU smoke WAV from a fine-tuned Orpheus LoRA adapter."""
    checkpoint = lora_dir or (default_checkpoint_dir(speaker) / "lora")
    out = output_dir or checkpoint.parent
    receipt = run_inference_smoke(
        speaker=speaker,
        lora_dir=checkpoint,
        output_dir=out,
        prompt=prompt,
        load_in_4bit=load_in_4bit,
    )
    typer.echo(json.dumps(receipt, indent=2))
    if receipt.get("status") != "PASS":
        raise typer.Exit(code=1)


@app.command("publish-orpheus")
def publish_orpheus(
    speaker: str = typer.Option(..., "--speaker"),
    lora_dir: Path | None = typer.Option(None, "--lora-dir"),
    publish_dir: Path | None = typer.Option(None, "--publish-dir"),
    repo_id: str | None = typer.Option(None, "--repo-id", help="Default: <hf-user>/<speaker>-orpheus-lora"),
    execute: bool = typer.Option(False, "--execute", help="Actually create/upload private Hub repo"),
) -> None:
    """Validate model card and publish LoRA to a private Hugging Face model repo via ops-huggingface."""
    checkpoint = lora_dir or (default_checkpoint_dir(speaker) / "lora")
    out = publish_dir or checkpoint.parent
    receipt = publish_orpheus_model(
        speaker=speaker,
        lora_dir=checkpoint,
        publish_dir=out,
        repo_id=repo_id,
        execute=execute,
    )
    typer.echo(json.dumps(receipt, indent=2))
    if receipt.get("status") == "FAIL":
        raise typer.Exit(code=1)


@app.command("finish-orpheus")
def finish_orpheus(
    job_dir: Path = typer.Option(..., "--job-dir"),
    speaker: str = typer.Option(..., "--speaker"),
    publish_repo: str | None = typer.Option(None, "--repo-id"),
    skip_train: bool = typer.Option(False, "--skip-train"),
    skip_publish: bool = typer.Option(False, "--skip-publish"),
    publish_execute: bool = typer.Option(False, "--publish-execute"),
    load_in_4bit: bool = typer.Option(True, "--load-in-4bit/--no-4bit"),
) -> None:
    """Mandatory Orpheus closure: export already done -> train -> inference smoke -> HF publish dry-run/execute."""
    import subprocess

    out_dir = job_dir / "orpheus-dataset"
    hf_dataset = out_dir / "hf_dataset"
    if not hf_dataset.is_dir():
        raise typer.BadParameter(f"Missing exported dataset: {hf_dataset}")

    checkpoint = default_checkpoint_dir(speaker)
    train_script = Path(__file__).resolve().parents[1] / "training" / "run_train.sh"
    storage_train = Path("/mnt/storage12tb/skills/voice-segment-selector/training/run_train.sh")
    runner = storage_train if storage_train.is_file() else train_script

    steps: list[dict] = []
    if not skip_train:
        for mode in ("--smoke", "--full"):
            cmd = ["bash", str(runner), speaker, mode]
            if load_in_4bit:
                cmd.append("--load-in-4bit")
            env = os.environ.copy()
            env["VOICE_SEGMENT_SELECTOR_ORPHEUS_DATASET"] = str(hf_dataset.resolve())
            proc = subprocess.run(cmd, env=env)
            steps.append({"step": f"train{mode}", "returncode": proc.returncode})
            if proc.returncode != 0:
                typer.echo(json.dumps({"status": "FAIL", "steps": steps}, indent=2))
                raise typer.Exit(code=1)

    inference = run_inference_smoke(
        speaker=speaker,
        lora_dir=checkpoint / "lora",
        output_dir=checkpoint,
        load_in_4bit=load_in_4bit,
    )
    steps.append({"step": "inference-smoke", "status": inference.get("status")})
    if inference.get("status") != "PASS":
        typer.echo(json.dumps({"status": "FAIL", "steps": steps, "inference": inference}, indent=2))
        raise typer.Exit(code=1)

    publish = None
    if not skip_publish:
        publish = publish_orpheus_model(
            speaker=speaker,
            lora_dir=checkpoint / "lora",
            publish_dir=checkpoint,
            repo_id=publish_repo,
            execute=publish_execute,
        )
        steps.append({"step": "publish-orpheus", "status": publish.get("status")})

    summary = {
        "status": "PASS" if inference.get("status") == "PASS" else "FAIL",
        "job_dir": str(job_dir.resolve()),
        "speaker": speaker,
        "checkpoint_dir": str(checkpoint.resolve()),
        "inference_receipt": str((checkpoint / "inference_receipt.json").resolve()),
        "publish_receipt": str((checkpoint / "publish_receipt.json").resolve()) if publish else None,
        "steps": steps,
        "inference_ready": inference.get("status") == "PASS",
        "hub_published": bool(publish and publish.get("status") == "PUBLISHED"),
    }
    typer.echo(json.dumps(summary, indent=2))
    if summary["status"] != "PASS":
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
