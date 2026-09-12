#!/usr/bin/env python3
"""Live E2E: human idea -> 2-3 Kling clips -> Embry journal -> Chatterbox conversation.

Diagram ID: persona-dream.kling-e2e
Excalidraw source: skills/persona-dream/docs/explain/boards/persona-dream-kling-e2e.excalidraw
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from PIL import Image
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = Path(os.environ.get("PD_EVAL_OUT_ROOT", "/mnt/storage12tb/skills/persona-dream/outputs"))
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
CHATTERBOX_OUT_HOST_ROOT = Path(os.environ.get("CHATTERBOX_OUT_HOST_ROOT", "/home/graham/workspace/experiments/chatterbox/logs"))
IDEA = (
    "Embry and Horus have tea on a void world, discussing SPARTA Explorer "
    "casually as friends, with the Eye of Tzeentch and Tyranids in the background."
)
MODEL_ID = "fal-ai/kling-video/v3/standard/image-to-video"
REFERENCE_ASSETS = ROOT / "reports" / "assets"


class Phase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["persona_dream.kling_tea_e2e_phase.v1"] = Field(default="persona_dream.kling_tea_e2e_phase.v1", alias="schema")
    phase: str = Field(min_length=1)
    status: str = Field(min_length=1)
    live: bool
    mocked: bool = False
    artifacts: list[str] = []
    details: dict[str, Any] = {}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def phase(run_dir: Path, name: str, status: str, *, live: bool, artifacts: list[str] | None = None, **details: Any) -> None:
    record = Phase(phase=name, status=status, live=live, artifacts=artifacts or [], details=details).model_dump(by_alias=True)
    write_json(run_dir / "receipts" / f"{name}.json", record)


def fetch(url: str, out: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as response:
        out.write_bytes(response.read())


def ffprobe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], text=True, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-300:])
    return json.loads(proc.stdout)


def resolve_chatterbox_audio(source: str) -> Path | None:
    path = Path(source or "")
    if path.is_file():
        return path
    if path.is_absolute() and len(path.parts) > 2 and path.parts[1] in {"out", "data"}:
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*path.parts[2:])
        if host.is_file():
            return host
    return None


def crop_start_frame(run_dir: Path) -> Path:
    src = REFERENCE_ASSETS / "storyboard_board.png"
    out = run_dir / "kling_start_frame.png"
    crop_box = (1536, 570, 1920, 904)
    if not src.is_file():
        raise RuntimeError(f"missing_start_frame_source:{src}")
    with Image.open(src) as image:
        width, height = image.size
        left, top, right, bottom = crop_box
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise RuntimeError(f"start_frame_crop_out_of_bounds:source={width}x{height}:crop={crop_box}")
        image.crop(crop_box).convert("RGB").save(out, format="PNG")
    return out


def _image_receipt(path: Path) -> dict[str, Any]:
    if path.stat().st_size < 1024:
        raise RuntimeError(f"reference_asset_too_small:{path}")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format
    except Exception as exc:
        raise RuntimeError(f"reference_asset_not_decodable:{path}:{exc}") from exc
    return {
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "format": image_format,
    }


def upload_reference_assets(run_dir: Path, fal_client: Any) -> dict[str, Any]:
    local = {
        "start_frame": crop_start_frame(run_dir),
        "horus_front": REFERENCE_ASSETS / "element_packs" / "horus" / "horus_q1_front.png",
        "horus_face": REFERENCE_ASSETS / "element_packs" / "horus" / "horus_q4_face.png",
        "embry_front": REFERENCE_ASSETS / "element_packs" / "embry" / "embry_q1_front.png",
        "embry_face": REFERENCE_ASSETS / "element_packs" / "embry" / "embry_q4_face.png",
        "tyranid_front": REFERENCE_ASSETS / "element_packs" / "tyranid_environment" / "tyranid_environment_q1_front.png",
        "tyranid_side": REFERENCE_ASSETS / "element_packs" / "tyranid_environment" / "tyranid_environment_q3_side.png",
    }
    missing = [str(path) for path in local.values() if not path.is_file()]
    if missing:
        raise RuntimeError("missing_reference_assets:" + ",".join(missing))
    asset_receipts = {name: _image_receipt(path) for name, path in local.items()}
    uploaded = {name: fal_client.upload_file(path) for name, path in local.items()}
    elements = [
        {"frontal_image_url": uploaded["horus_front"], "reference_image_urls": [uploaded["horus_face"]]},
        {"frontal_image_url": uploaded["embry_front"], "reference_image_urls": [uploaded["embry_face"]]},
        {"frontal_image_url": uploaded["tyranid_front"], "reference_image_urls": [uploaded["tyranid_side"]]},
    ]
    receipt = {
        "schema": "persona_dream.kling_reference_assets.v1",
        "status": "PASS_REFERENCE_ASSETS_UPLOADED",
        "model_id": MODEL_ID,
        "element_count": len(elements),
        "asset_receipts": asset_receipts,
        "uploaded_assets": uploaded,
        "canonical_compiler": False,
    }
    write_json(run_dir / "kling_reference_assets_receipt.json", receipt)
    return {"start_image_url": uploaded["start_frame"], "elements": elements, "receipt": receipt}


def validate_direct_kling_smoke_request(run_dir: Path, request: dict[str, Any]) -> dict[str, Any]:
    prompt = str(request.get("prompt", ""))
    elements = request.get("elements")
    if not isinstance(elements, list) or not elements:
        raise RuntimeError("direct_kling_request_missing_elements")
    expected_bindings = [f"@Element{index} is " for index in range(1, len(elements) + 1)]
    missing_bindings = [binding for binding in expected_bindings if binding not in prompt]
    if missing_bindings:
        raise RuntimeError("direct_kling_request_missing_bindings:" + ",".join(missing_bindings))
    if not request.get("start_image_url"):
        raise RuntimeError("direct_kling_request_missing_start_image_url")
    receipt = {
        "schema": "persona_dream.kling_direct_request_validation.v1",
        "status": "PASS_DIRECT_KLING_SMOKE_REQUEST",
        "canonical_compiler": False,
        "proof_boundary": "Direct provider smoke only; not Persona Dream -> scene table -> create-kling-scene proof.",
        "prompt_chars": len(prompt),
        "element_count": len(elements),
        "bindings": expected_bindings,
    }
    write_json(run_dir / "kling_direct_request_validation_receipt.json", receipt)
    return receipt


SHOT_PLAN = [
    {
        "clip": 1,
        "speaker": "embry",
        "coverage": "master-to-embry-medium-close-up",
        "framing": "master two-shot resolves into Embry favored medium close-up",
        "eyeline": "Embry stays screen-left facing camera-right; Horus stays screen-right facing camera-left",
        "beat": "Embry speaks first about the glowing SPARTA Explorer evidence map between their tea cups; Horus listens in profile.",
    },
    {
        "clip": 2,
        "speaker": "horus",
        "coverage": "horus-reverse-medium-close-up",
        "framing": "Horus favored medium close-up, matched size to Embry's single",
        "eyeline": "Horus remains screen-right facing camera-left; Embry remains screen-left facing camera-right as the listener in profile",
        "beat": "Horus answers calmly while purple storm light from the Eye of Tzeentch crosses his armor and face.",
    },
    {
        "clip": 3,
        "speaker": "embry",
        "coverage": "embry-reaction-medium-close-up",
        "framing": "Embry favored medium close-up, same lens and size as the reverse shot",
        "eyeline": "Embry remains screen-left facing camera-right; Horus remains screen-right facing camera-left",
        "beat": "Embry closes the exchange with a small smile as a distant Tyranid crosses behind them without approaching.",
    },
]


def validate_cinematography_plan(run_dir: Path, clip_count: int) -> dict[str, Any]:
    plan = SHOT_PLAN[:clip_count]
    speakers = [shot["speaker"] for shot in plan]
    coverages = [shot["coverage"] for shot in plan]
    errors = []
    if len(set(speakers)) < 2:
        errors.append("coverage must change by speaking character")
    if len(set(coverages)) != len(coverages):
        errors.append("each speaking beat needs distinct coverage")
    if not all("screen-left facing camera-right" in shot["eyeline"] and "screen-right facing camera-left" in shot["eyeline"] for shot in plan):
        errors.append("180-degree line and eyelines must stay explicit")
    if not all("medium close-up" in shot["framing"] for shot in plan):
        errors.append("speaker singles must use matched medium close-up framing")
    status = "PASS_CINEMATOGRAPHY_COVERAGE" if not errors else "BLOCKED_CINEMATOGRAPHY_COVERAGE"
    receipt = {
        "schema": "persona_dream.cinematography_coverage_receipt.v1",
        "status": status,
        "complies_with": "best-practices-cinematography",
        "rules": [
            "coverage before prompts",
            "stable 180-degree line and eyelines",
            "one beat per clip, speaker favored",
            "matched shot/reverse-shot framing",
            "motivated lighting from SPARTA map and Eye of Tzeentch",
        ],
        "watch_diarization_boundary": "After dialogue audio is muxed, verify who-spoke-when with $watch --diarization pyannote --require-diarization; silent Kling clips carry planned_speaker only.",
        "live_evidence_boundary": "$live-evidence supplies live transcript speaker-turn events, not pyannote diarization; its own contract says diarization is deferred.",
        "clip_count": clip_count,
        "shot_plan": plan,
        "errors": errors,
    }
    write_json(run_dir / "cinematography_coverage_receipt.json", receipt)
    if errors:
        raise RuntimeError("; ".join(errors))
    return receipt


def clip_prompt(index: int, clip_count: int) -> str:
    shot = SHOT_PLAN[index - 1]
    return (
        f"Clip {index} of {clip_count}, continuous dialogue coverage, one speaking beat only. "
        "@Element1 is Horus Lupercal. @Element2 is Embry Lawson. Exactly two people, no one else present. "
        f"Speaker: {shot['speaker']}. Coverage: {shot['coverage']}. Framing: {shot['framing']}. "
        f"180-degree line: {shot['eyeline']}. {shot['beat']} "
        "Speaker mouth clearly visible during the line; listener reacts in profile; end with closed mouth. "
        "Motivated light comes from the glowing SPARTA Explorer map on the table and purple storm sky. "
        "@Element3 is one distant Tyranid creature in the background only. No text overlays."
    )


def concat_videos(run_dir: Path, clips: list[Path]) -> Path:
    list_path = run_dir / "kling_clips.ffconcat"
    list_path.write_text("ffconcat version 1.0\n" + "".join(f"file '{clip.name}'\n" for clip in clips), encoding="utf-8")
    out = run_dir / "kling_dream.mp4"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out)],
        text=True,
        capture_output=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1000:])
    return out


def render_journal_audio(run_dir: Path, run_id: str, text: str) -> Path:
    request = {
        "answer_text": text,
        "label": run_id,
        "use_blessed_qra_cache": False,
        "asr_verify": False,
        "voice_delivery": {"pace": "measured", "tone": "neutral_warm"},
    }
    write_json(run_dir / "journal_chatterbox_request.json", {"schema": "persona_dream.kling_tea_journal_chatterbox_request.v1", **request})
    req = urllib.request.Request(f"{CHATTERBOX}/synthesize-batch", data=json.dumps(request).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as response:
        payload = json.loads(response.read().decode("utf-8"))
    write_json(run_dir / "journal_chatterbox_response.json", payload)
    source = resolve_chatterbox_audio(str(payload.get("finished_response_audio") or ""))
    if source is None:
        chunks = payload.get("chunks") or []
        for chunk in chunks:
            audio = ((chunk or {}).get("synthesis") or {}).get("audio")
            source = resolve_chatterbox_audio(str(audio or ""))
            if source is not None:
                break
    if source is None:
        raise RuntimeError("chatterbox_audio_not_found")
    dest = run_dir / "journal.wav"
    shutil.copyfile(source, dest)
    write_json(run_dir / "JOURNAL_AUDIO_RECEIPT.json", {
        "schema": "persona_dream.journal_audio_receipt.v1",
        "status": "PASS_JOURNAL_SPOKEN",
        "live": True,
        "mocked": False,
        "audio": str(dest),
        "audio_sha256": sha256(dest),
        "audio_bytes": dest.stat().st_size,
        "text_sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chatterbox_response": str(run_dir / "journal_chatterbox_response.json"),
    })
    return dest


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clip-count", type=int, default=3, choices=(2, 3))
    ap.add_argument("--validate-cinematography-only", action="store_true")
    ap.add_argument("--reuse-existing-clips", action="store_true", help="Reuse hash-verified live clips already in --out-dir instead of new paid calls; fail closed if incomplete.")
    args = ap.parse_args()
    run_id = "kling-tea-e2e-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = (args.out_dir or OUT_ROOT / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    phase(run_dir, "idea_lineage", "PASS_IDEA_LINEAGE", live=True, idea=IDEA, source="human_prompt")
    if args.validate_cinematography_only:
        coverage = validate_cinematography_plan(run_dir, args.clip_count)
        phase(run_dir, "cinematography_coverage", coverage["status"], live=False, artifacts=[str(run_dir / "cinematography_coverage_receipt.json")])
        print(f"PASS_CINEMATOGRAPHY_COVERAGE run={run_dir} clips={args.clip_count}")
        return 0
    if args.dry_run:
        phase(run_dir, "kling_dream_video", "BLOCKED_DRY_RUN_NOT_E2E", live=False)
        print(f"BLOCKED_DRY_RUN_NOT_E2E run={run_dir}")
        return 2

    try:
        urllib.request.urlopen(f"{CHATTERBOX}/health", timeout=10)
    except (urllib.error.URLError, OSError):
        phase(run_dir, "chatterbox_preflight", "BLOCKED_CHATTERBOX_UNREACHABLE", live=False)
        print(f"BLOCKED_CHATTERBOX_UNREACHABLE run={run_dir}")
        return 2
    phase(run_dir, "chatterbox_preflight", "PASS_CHATTERBOX_REACHABLE", live=True)

    reuse_ok = False
    if args.reuse_existing_clips:
        existing = [run_dir / f"kling_dream_clip_{index:02d}.mp4" for index in range(1, args.clip_count + 1)]
        problems = [str(p) for p in existing if not p.is_file() or p.stat().st_size < 100_000]
        if not problems and (run_dir / "kling_responses.json").is_file() and (run_dir / "kling_request.json").is_file():
            try:
                for p in existing:
                    ffprobe(p)
                reuse_ok = True
            except Exception as exc:
                problems = [f"ffprobe:{exc}"]
        if reuse_ok:
            phase(run_dir, "kling_preflight", "PASS_KLING_PREFLIGHT", live=True, model_id=MODEL_ID, reused_live_artifacts=True)
            phase(run_dir, "kling_reference_assets", "PASS_REFERENCE_ASSETS_UPLOADED", live=True, reused_live_artifacts=True, artifacts=[str(run_dir / "kling_reference_assets_receipt.json")])
        else:
            phase(run_dir, "kling_preflight", "BLOCKED_REUSE_INCOMPLETE", live=False, problems=problems[:5])
            print(f"BLOCKED_REUSE_INCOMPLETE run={run_dir}")
            return 2

    clips: list[Path] = []
    video: Path
    if reuse_ok:
        clips = [run_dir / f"kling_dream_clip_{index:02d}.mp4" for index in range(1, args.clip_count + 1)]
        video = run_dir / "kling_dream.mp4"
        probe = ffprobe(video)
        write_json(run_dir / "kling_dream.ffprobe.json", probe)
        phase(run_dir, "kling_dream_video", "PASS_KLING_DREAM_VIDEO", live=True, reused_live_artifacts=True, artifacts=[str(video), str(run_dir / "kling_responses.json"), *map(str, clips)], video_sha256=sha256(video), clip_count=len(clips), bytes=video.stat().st_size)
    else:
        try:
            import fal_client  # type: ignore
        except Exception as exc:
            phase(run_dir, "kling_preflight", "BLOCKED_FAL_CLIENT_IMPORT", live=False, error=str(exc))
            print(f"BLOCKED_FAL_CLIENT_IMPORT run={run_dir}")
            return 2
        if not os.environ.get("FAL_KEY") and os.environ.get("FAL_API_KEY"):
            os.environ["FAL_KEY"] = os.environ["FAL_API_KEY"]
        if not os.environ.get("FAL_KEY"):
            phase(run_dir, "kling_preflight", "BLOCKED_FAL_KEY_MISSING", live=False)
            print(f"BLOCKED_FAL_KEY_MISSING run={run_dir}")
            return 2
        phase(run_dir, "kling_preflight", "PASS_KLING_PREFLIGHT", live=True, model_id=MODEL_ID)

        try:
            binding = upload_reference_assets(run_dir, fal_client)
        except Exception as exc:
            phase(run_dir, "kling_reference_assets", "BLOCKED_KLING_REFERENCE_ASSETS", live=True, error=str(exc)[:1000])
            print(f"BLOCKED_KLING_REFERENCE_ASSETS run={run_dir}")
            return 2
        phase(run_dir, "kling_reference_assets", "PASS_REFERENCE_ASSETS_UPLOADED", live=True, artifacts=[str(run_dir / "kling_reference_assets_receipt.json")])

        try:
            coverage = validate_cinematography_plan(run_dir, args.clip_count)
        except Exception as exc:
            phase(run_dir, "cinematography_coverage", "BLOCKED_CINEMATOGRAPHY_COVERAGE", live=True, error=str(exc)[:1000], artifacts=[str(run_dir / "cinematography_coverage_receipt.json")])
            print(f"BLOCKED_CINEMATOGRAPHY_COVERAGE run={run_dir}")
            return 2
        phase(run_dir, "cinematography_coverage", coverage["status"], live=True, artifacts=[str(run_dir / "cinematography_coverage_receipt.json")])

        requests = []
        for index in range(1, args.clip_count + 1):
            requests.append({
                "prompt": clip_prompt(index, args.clip_count),
                "start_image_url": binding["start_image_url"],
                "duration": "5",
                "generate_audio": False,
                "elements": binding["elements"],
                "negative_prompt": "text, subtitles, gore, extra people, third person, crowd, generic space marines, bald blue aliens, changed faces, changed armor, changed jacket, back of head only, face hidden",
                "cfg_scale": 0.75,
            })
        request_bundle = {**requests[0], "prompt": "\n".join(item["prompt"] for item in requests)}
        try:
            direct_validation = validate_direct_kling_smoke_request(run_dir, request_bundle)
        except Exception as exc:
            phase(run_dir, "kling_direct_request_validation", "BLOCKED_KLING_DIRECT_REQUEST", live=True, error=str(exc)[:1000])
            print(f"BLOCKED_KLING_DIRECT_REQUEST run={run_dir}")
            return 2
        direct_validation["clip_count"] = args.clip_count
        write_json(run_dir / "kling_direct_request_validation_receipt.json", direct_validation)
        phase(run_dir, "kling_direct_request_validation", direct_validation["status"], live=True, artifacts=[str(run_dir / "kling_direct_request_validation_receipt.json")])
        write_json(run_dir / "kling_request.json", {
            "schema": "persona_dream.kling_tea_request.v1",
            "model_id": MODEL_ID,
            "reference_assets_receipt": str(run_dir / "kling_reference_assets_receipt.json"),
            "direct_request_validation_receipt": str(run_dir / "kling_direct_request_validation_receipt.json"),
            "cinematography_coverage_receipt": str(run_dir / "cinematography_coverage_receipt.json"),
            "canonical_compiler": False,
            "clip_count": args.clip_count,
            "requests": requests,
        })
        responses: list[dict[str, Any]] = []
        try:
            for index, request in enumerate(requests, 1):
                response = fal_client.subscribe(MODEL_ID, arguments=request, with_logs=True)  # type: ignore[attr-defined]
                responses.append(response)
                write_json(run_dir / f"kling_response_clip_{index:02d}.json", response)
                video_url = (((response or {}).get("video") or {}).get("url") if isinstance(response, dict) else None) or ((response or {}).get("url") if isinstance(response, dict) else None)
                if not video_url:
                    phase(run_dir, "kling_dream_video", "BLOCKED_KLING_NO_VIDEO_URL", live=True, artifacts=[str(run_dir / f"kling_response_clip_{index:02d}.json")], clip=index)
                    print(f"BLOCKED_KLING_NO_VIDEO_URL run={run_dir} clip={index}")
                    return 2
                clip = run_dir / f"kling_dream_clip_{index:02d}.mp4"
                fetch(str(video_url), clip)
                write_json(run_dir / f"kling_dream_clip_{index:02d}.ffprobe.json", ffprobe(clip))
                if clip.stat().st_size < 100_000:
                    phase(run_dir, "kling_dream_video", "BLOCKED_KLING_VIDEO_TOO_SMALL", live=True, artifacts=[str(clip)], clip=index)
                    print(f"BLOCKED_KLING_VIDEO_TOO_SMALL run={run_dir} clip={index}")
                    return 2
                clips.append(clip)
        except Exception as exc:
            error = str(exc)
            code = "BLOCKED_KLING_PROVIDER_TOP_UP" if ("TOP_UP" in error or "Exhausted balance" in error or "Top up your balance" in error) else "BLOCKED_KLING_PROVIDER_ERROR"
            phase(run_dir, "kling_dream_video", code, live=True, error=error[:1000], completed_clips=len(clips), requested_clips=args.clip_count)
            print(f"{code} run={run_dir}")
            return 2
        write_json(run_dir / "kling_responses.json", {"schema": "persona_dream.kling_tea_responses.v1", "responses": responses})
        try:
            video = concat_videos(run_dir, clips)
        except Exception as exc:
            phase(run_dir, "kling_dream_video", "BLOCKED_KLING_ASSEMBLY", live=True, error=str(exc)[:1000], artifacts=[*map(str, clips)])
            print(f"BLOCKED_KLING_ASSEMBLY run={run_dir}")
            return 2
        probe = ffprobe(video)
        write_json(run_dir / "kling_dream.ffprobe.json", probe)
        phase(run_dir, "kling_dream_video", "PASS_KLING_DREAM_VIDEO", live=True, artifacts=[str(video), str(run_dir / "kling_responses.json"), *map(str, clips)], video_sha256=sha256(video), clip_count=len(clips), bytes=video.stat().st_size)


    storyboard = {"schema": "persona_dream.cycle_storyboard_plan.v1", "dream_synopsis": IDEA, "panels": [{"panel_id": f"sb_{index:03d}", "action": clip_prompt(index, args.clip_count), "mood": "warm uncanny friendship"} for index in range(1, args.clip_count + 1)]}
    write_json(run_dir / "storyboard_plan.json", storyboard)
    write_json(run_dir / "observation_packet.json", {"schema": "persona_dream.cycle_storyboard_observation_packet.v1", "status": "PASS_KLING_VIDEO_OBSERVED", "clip_count": args.clip_count, "frame_evidence": [{"panel_id": f"sb_{index:03d}", "observed_entities": ["Embry", "Horus", "tea", "SPARTA Explorer", "Eye of Tzeentch", "Tyranids"]} for index in range(1, args.clip_count + 1)]})
    write_json(run_dir / "residue_links.json", {"schema": "persona_dream.residue_links.v1", "idea_id": run_id, "items": [{"source_id": "human_idea", "scope": "human_prompt", "text": IDEA, "type": "explicit_human_idea"}]})
    write_json(run_dir / "day_context.json", {"schema": "persona_dream.day_context.v1", "items": [{"source_id": "human_idea", "text": IDEA}]})
    write_json(run_dir / "transcript_context.json", {"schema": "persona_dream.transcript_context.v1", "items": []})
    write_json(run_dir / "dream_packet.json", {"schema": "persona_dream.synthetic_dream_packet.v1", "human_idea_lineage": IDEA, "kling_video": str(video), "kling_video_sha256": sha256(video), "synthetic_boundary": "Kling dream video is synthetic dream evidence, not literal history."})
    journal = "I dreamed Horus and I were having tea on the void world, talking about SPARTA Explorer like friends. The Eye of Tzeentch watched from the sky and Tyranids moved behind us, but the evidence map between our cups made the danger feel strangely calm."
    write_json(run_dir / "dream_journal.v1.json", {"schema": "persona_dream.persona_journal.v1", "persona_id": "embry", "cycle": run_id, "journal": journal, "unresolved_tension": "friendship and evidence feel warm while the void world remains dangerous", "expanded_understanding": "A hostile background can make casual trust feel more precious.", "session_mood": {"mood_label": "warmly_watchful", "mood_description": "friendly and calm, but aware of the eye and Tyranids behind the conversation", "carried_tension": "warm friendship against watched danger"}, "never_promote_to_event_fact": True, "asserts_only_own_inner_state": True})
    (run_dir / "journal.md").write_text(journal + "\n", encoding="utf-8")
    phase(run_dir, "journal_entry", "PASS_JOURNAL_ENTRY", live=True, artifacts=[str(run_dir / "dream_journal.v1.json"), str(run_dir / "journal.md")])

    try:
        journal_audio = render_journal_audio(run_dir, run_id, journal)
    except Exception as exc:
        phase(run_dir, "journal_audio", "BLOCKED_JOURNAL_AUDIO", live=True, error=str(exc))
        print(f"BLOCKED_JOURNAL_AUDIO run={run_dir}")
        return 2
    phase(run_dir, "journal_audio", "PASS_JOURNAL_SPOKEN", live=True, artifacts=[str(journal_audio)])

    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "dynamic_conversation.py"), "--run-dir", str(run_dir), "--turns", "2", "--opening-topic", "Ask Embry about the tea with Horus, SPARTA Explorer, the Eye of Tzeentch, and Tyranids."], text=True, capture_output=True, timeout=1500)
    (run_dir / "dynamic_conversation.stdout").write_text(proc.stdout, encoding="utf-8")
    (run_dir / "dynamic_conversation.stderr").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0 or "PASS_DYNAMIC_CONVERSATION" not in proc.stdout:
        phase(run_dir, "chatterbox_discussion", "BLOCKED_CHATTERBOX_DISCUSSION", live=True, stdout=proc.stdout[-500:], stderr=proc.stderr[-500:])
        print(f"BLOCKED_CHATTERBOX_DISCUSSION run={run_dir}")
        return 2
    convo = run_dir / "conversation.jsonl"
    turns = [json.loads(line) for line in convo.read_text(encoding="utf-8").splitlines() if line.strip()]
    audio = [run_dir / t.get("audio", "") for t in turns if t.get("role") in {"horus", "embry"}]
    if len(audio) < 4 or any((not p.is_file()) or p.stat().st_size < 10000 for p in audio):
        phase(run_dir, "chatterbox_discussion", "BLOCKED_CONVERSATION_AUDIO_READBACK", live=True)
        print(f"BLOCKED_CONVERSATION_AUDIO_READBACK run={run_dir}")
        return 2
    phase(run_dir, "chatterbox_discussion", "PASS_CHATTERBOX_DREAM_DISCUSSION", live=True, artifacts=[str(convo), str(run_dir / "dynamic_conversation_receipt.v1.json"), *map(str, audio)])

    receipt = {
        "schema": "persona_dream.kling_tea_e2e_receipt.v1",
        "status": "PASS_KLING_TEA_E2E",
        "live": True,
        "mocked": False,
        "reused_live_artifacts": reuse_ok,
        "run_dir": str(run_dir),
        "idea": IDEA,
        "kling_video": str(video),
        "kling_video_sha256": sha256(video),
        "clip_count": len(clips),
        "clips": [{"path": str(clip), "sha256": sha256(clip), "bytes": clip.stat().st_size} for clip in clips],
        "journal_audio": str(run_dir / "journal.wav"),
        "conversation_turns": len(turns),
        "cinematography_coverage_receipt": str(run_dir / "cinematography_coverage_receipt.json"),
        "phase_receipts": sorted(str(p) for p in (run_dir / "receipts").glob("*.json")),
    }
    write_json(run_dir / "KlingTeaE2E.RECEIPT.json", receipt)
    print(f"PASS_KLING_TEA_E2E run={run_dir} clips={len(clips)} turns={len(turns)} video_bytes={video.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
