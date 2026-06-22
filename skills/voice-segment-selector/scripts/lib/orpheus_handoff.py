"""Orpheus train/inference/publish handoff helpers."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

OPS_HF = Path(__file__).resolve().parents[3] / "ops-huggingface" / "run.sh"
STORAGE_ROOT = Path("/mnt/storage12tb/skills/voice-segment-selector")
SKILL_ROOT = Path(__file__).resolve().parents[2]


def skill_root() -> Path:
    if STORAGE_ROOT.is_dir():
        return SKILL_ROOT
    return SKILL_ROOT


def training_root() -> Path:
    storage_training = STORAGE_ROOT / "training"
    if (storage_training / ".venv").is_dir():
        return storage_training
    return skill_root() / "training"


def default_checkpoint_dir(speaker: str) -> Path:
    if STORAGE_ROOT.is_dir():
        return STORAGE_ROOT / "checkpoints" / f"{speaker}_orpheus_lora"
    return skill_root() / "checkpoints" / f"{speaker}_orpheus_lora"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_receipt_best_effort(path: Path, receipt: dict) -> None:
    try:
        path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    except PermissionError:
        sidecar = path.with_name(path.stem + ".agent.json")
        sidecar.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        receipt["agent_sidecar_receipt"] = str(sidecar)


EVENT_WORDS_BY_TAG = {
    "laugh": ("laugh", "laughs", "laughing", "laughed"),
    "chuckle": ("chuckle", "chuckles", "chuckling", "chuckled"),
    "sigh": ("sigh", "sighs", "sighing", "sighed"),
    "cough": ("cough", "coughs", "coughing", "coughed"),
    "sniffle": ("sniffle", "sniffles", "sniffling", "sniffled"),
    "groan": ("groan", "groans", "groaning", "groaned"),
    "yawn": ("yawn", "yawns", "yawning", "yawned"),
    "gasp": ("gasp", "gasps", "gasping", "gasped"),
}


def _prompt_event_tags(prompt: str | None) -> list[str]:
    if not prompt:
        return []
    lowered = prompt.lower()
    found: list[str] = []
    for tag, words in EVENT_WORDS_BY_TAG.items():
        if any(re.search(rf"[\[<][^\]>]*\b{re.escape(word)}\b", lowered) for word in words):
            found.append(tag)
    return found


def _prompt_spoken_text(prompt: str | None) -> str:
    if not prompt:
        return ""
    cleaned = str(prompt)
    for words in EVENT_WORDS_BY_TAG.values():
        for word in words:
            cleaned = re.sub(rf"[\[<][^\]>]*\b{re.escape(word)}\b[^\]>]*[\]>]", " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _apply_literal_tag_asr_check(*, receipt: dict, output_dir: Path, prompt: str | None) -> dict:
    if receipt.get("status") != "PASS":
        return receipt
    tags = _prompt_event_tags(prompt or str(receipt.get("prompt") or ""))
    if not tags:
        return receipt
    wav_path = output_dir / "inference_smoke.wav"
    if not wav_path.is_file():
        receipt["literal_tag_check"] = {"status": "skipped", "reason": "missing_local_wav"}
        return receipt
    try:
        from lib.transcribe import transcribe_clip

        transcript, confidence = transcribe_clip(wav_path)
    except Exception as exc:  # Keep generation usable when ASR extras are absent.
        receipt["literal_tag_check"] = {
            "status": "skipped",
            "reason": "transcription_unavailable",
            "error": str(exc),
        }
        return receipt

    lowered = transcript.lower()
    allowed_lowered = _prompt_spoken_text(prompt or str(receipt.get("prompt") or "")).lower()
    spoken = []
    for tag in tags:
        words = [
            word
            for word in EVENT_WORDS_BY_TAG[tag]
            if not re.search(rf"\b{re.escape(word)}\b", allowed_lowered)
        ]
        if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words):
            spoken.append(tag)

    receipt["literal_tag_check"] = {
        "status": "FAIL" if spoken else "PASS",
        "prompt_tags": tags,
        "spoken_literal_tags": spoken,
        "asr_transcript": transcript,
        "asr_confidence": confidence,
    }
    if spoken:
        receipt["status"] = "FAIL"
        receipt["verified"] = "literal_tag_spoken"
        receipt["error"] = f"Generated audio spoke tag word(s) literally: {', '.join(spoken)}"
    return receipt


def run_inference_smoke(
    *,
    speaker: str,
    lora_dir: Path,
    output_dir: Path,
    prompt: str | None = None,
    load_in_4bit: bool = True,
    model_name: str = "unsloth/orpheus-3b-0.1-ft",
    use_docker: bool = True,
    docker_image: str = "orpheus-infer:gpu",
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    if use_docker:
        return run_inference_smoke_docker(
            speaker=speaker,
            lora_dir=lora_dir,
            output_dir=output_dir,
            prompt=prompt,
            load_in_4bit=load_in_4bit,
            image=docker_image,
        )
    py = training_root() / ".venv" / "bin" / "python"
    script = training_root() / "inference_orpheus_unsloth.py"
    if not py.is_file():
        raise RuntimeError(f"Missing training venv python: {py}")
    if not script.is_file():
        raise RuntimeError(f"Missing inference script: {script}")

    cmd = [
        str(py),
        str(script),
        "--lora-dir",
        str(lora_dir),
        "--speaker",
        speaker,
        "--output-dir",
        str(output_dir),
        "--model-name",
        model_name,
    ]
    if load_in_4bit:
        cmd.append("--load-in-4bit")
    if prompt:
        cmd.extend(["--prompt", prompt])

    env = os.environ.copy()
    if not env.get("HF_TOKEN"):
        token = subprocess.check_output(["zsh", "-lic", "print -r -- ${HF_TOKEN}"], text=True).strip()
        if token:
            env["HF_TOKEN"] = token

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    receipt_path = output_dir / "inference_receipt.json"
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
    else:
        receipt = {
            "schema": "voice_segment_selector.orpheus_inference_receipt.v1",
            "status": "FAIL",
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "returncode": proc.returncode,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    if proc.returncode != 0 and receipt.get("status") != "PASS":
        receipt.setdefault("error", proc.stderr.strip() or proc.stdout.strip() or "inference failed")
    receipt = _apply_literal_tag_asr_check(receipt=receipt, output_dir=output_dir, prompt=prompt)
    _write_receipt_best_effort(receipt_path, receipt)
    return receipt


def build_model_card(
    *,
    speaker: str,
    repo_id: str,
    train_receipt: dict,
    inference_receipt: dict,
    dataset_info: dict | None = None,
) -> str:
    example_count = train_receipt.get("example_count") or (dataset_info or {}).get("example_count")
    train_loss = (train_receipt.get("train_metrics") or {}).get("train_loss")
    wav_path = inference_receipt.get("wav_path")
    duration = inference_receipt.get("duration_sec")
    wav_bytes = inference_receipt.get("wav_bytes")
    inference_status = inference_receipt.get("status")
    inference_prompt = inference_receipt.get("prompt")
    inference_gpu = inference_receipt.get("gpu")
    base_model = train_receipt.get("model_name", "unsloth/orpheus-3b-0.1-ft")
    dataset_path = train_receipt.get("dataset")
    lora_rank = train_receipt.get("lora_rank", 64)
    lora_alpha = train_receipt.get("lora_alpha", 64)
    limitations = [
        "Experimental LoRA adapter trained from voice-segment-selector clips.",
        "Speaker identity is diarization-assisted, not forensic proof.",
        "Bootstrap or lightly reviewed transcripts may remain in the training set.",
        "Use only with rights/consent for the cloned voice.",
    ]
    if dataset_info:
        limitations.extend(dataset_info.get("limitations") or [])

    return f"""---
license: apache-2.0
library_name: peft
base_model: {base_model}
tags:
  - text-to-speech
  - orpheus
  - unsloth
  - lora
  - private
pipeline_tag: text-to-speech
---

# {speaker} Orpheus LoRA

Private Orpheus 3B LoRA adapter for persona `{speaker}`.

## Model Details

- Base model: `{base_model}`
- Adapter type: LoRA (Unsloth)
- Training examples: {example_count}
- Training loss: {train_loss}
- Inference smoke WAV: `{wav_path}` ({duration}s)
- Training dataset (local): `{dataset_path}`

## Intended Use

Experimental text-to-speech generation for authorized `{speaker}` persona workflows inside Embry OS.

## Out-of-Scope / Misuse

- Impersonation without consent
- Public redistribution as a verified identity clone
- Production deployment without human review of generated audio

## Limitations

{chr(10).join(f'- {item}' for item in limitations)}

## Evaluation

Live GPU inference smoke test before Hub publication:

- Status: `{inference_status}`
- Prompt: `{inference_prompt}`
- Output WAV: `{wav_path}` ({duration}s, {wav_bytes} bytes)
- GPU: `{inference_gpu}`
- Receipt schema: `{inference_receipt.get('schema')}`

This is a generation smoke test, not a benchmark score. Human review of
`inference_smoke.wav` is still required before production use.

## Training

- Base model: `{base_model}`
- Adapter: LoRA rank {lora_rank}, alpha {lora_alpha} (Unsloth)
- Training examples: {example_count}
- Final train loss: {train_loss}
- Dataset (local): `{dataset_path}`
- Train receipt schema: `{train_receipt.get('schema')}`

## Inference

Load the base Orpheus model and apply this LoRA adapter with Unsloth/PEFT on a CUDA GPU.
Run `voice-segment-selector/run.sh inference-smoke` to regenerate the proof WAV locally.

## Training Provenance

- Published at: {datetime.now(UTC).isoformat()}
- Hub repo: `{repo_id}` (private)
"""




def _infer_service_url() -> str:
    return os.environ.get("ORPHEUS_INFER_URL", "http://127.0.0.1:8767")


def _infer_service_healthy() -> bool:
    try:
        import httpx

        response = httpx.get(f"{_infer_service_url()}/health", timeout=2.0)
        if response.status_code != 200:
            return False
        data = response.json()
        return data.get("status") == "ok" and bool(data.get("warm_runtime"))
    except Exception:
        return False


def run_inference_smoke_http(
    *,
    speaker: str,
    output_dir: Path,
    prompt: str | None = None,
    load_in_4bit: bool = True,
    model_name: str = "unsloth/orpheus-3b-0.1-ft",
    temperature: float | None = None,
    top_p: float | None = None,
    repetition_penalty: float | None = None,
) -> dict:
    import httpx

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "speaker": speaker,
        "prompt": prompt or "Hey there, this is a smoke test of the fine-tuned Orpheus voice.",
        "load_in_4bit": load_in_4bit,
        "model_name": model_name,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if repetition_penalty is not None:
        payload["repetition_penalty"] = repetition_penalty
    response = httpx.post(
        f"{_infer_service_url()}/v1/synthesize",
        json=payload,
        timeout=600.0,
    )
    response.raise_for_status()
    body = response.json()
    receipt = body.get("receipt") or body
    receipt_path = output_dir / "inference_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt

def run_inference_smoke_docker(
    *,
    speaker: str,
    lora_dir: Path,
    output_dir: Path,
    prompt: str | None = None,
    load_in_4bit: bool = True,
    image: str = "orpheus-infer:gpu",
) -> dict:
    """Run Orpheus inference inside the GPU Docker image."""
    output_dir.mkdir(parents=True, exist_ok=True)
    docker_dir = skill_root() / "docker"
    script = docker_dir / "run_docker_smoke.sh"
    if not script.is_file():
        raise RuntimeError(f"Missing docker smoke script: {script}")

    env = os.environ.copy()
    env["ORPHEUS_INFER_IMAGE"] = image
    env["LOAD_4BIT"] = "1" if load_in_4bit else "0"
    env["ORPHEUS_SMOKE_CKPT"] = str(lora_dir.resolve().parent)
    env["ORPHEUS_SMOKE_OUTPUT_DIR"] = str(output_dir.resolve())
    if not env.get("HF_TOKEN"):
        token = subprocess.check_output(["zsh", "-lic", "print -r -- ${HF_TOKEN}"], text=True).strip()
        if token:
            env["HF_TOKEN"] = token

    default_lora_dir = (default_checkpoint_dir(speaker) / "lora").resolve()
    use_warm_service = lora_dir.resolve() == default_lora_dir
    if use_warm_service and _infer_service_healthy():
        try:
            receipt = run_inference_smoke_http(
                speaker=speaker,
                output_dir=output_dir,
                prompt=prompt,
                load_in_4bit=load_in_4bit,
            )
            receipt["verified"] = "live_docker_warm"
            receipt = _apply_literal_tag_asr_check(receipt=receipt, output_dir=output_dir, prompt=prompt)
            _write_receipt_best_effort(output_dir / "inference_receipt.json", receipt)
            return receipt
        except Exception:
            pass

    cmd = [str(script), speaker, prompt or "Hey there, this is a smoke test of the fine-tuned Orpheus voice."]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    receipt_path = output_dir / "inference_receipt.json"
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
    else:
        receipt = {
            "schema": "voice_segment_selector.orpheus_inference_receipt.v1",
            "status": "FAIL",
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "returncode": proc.returncode,
        }
        _write_receipt_best_effort(receipt_path, receipt)
    receipt["verified"] = "live_docker" if receipt.get("status") == "PASS" else "docker_failed"
    receipt = _apply_literal_tag_asr_check(receipt=receipt, output_dir=output_dir, prompt=prompt)
    _write_receipt_best_effort(receipt_path, receipt)
    return receipt

def publish_orpheus_model(
    *,
    speaker: str,
    lora_dir: Path,
    publish_dir: Path,
    repo_id: str | None = None,
    execute: bool = False,
) -> dict:
    lora_dir = lora_dir.resolve()
    publish_dir = publish_dir.resolve()
    publish_dir.mkdir(parents=True, exist_ok=True)

    train_receipt_path = lora_dir.parent / "train_receipt.json"
    inference_receipt_path = lora_dir.parent / "inference_receipt.json"
    if not train_receipt_path.is_file():
        raise RuntimeError(f"Missing train receipt: {train_receipt_path}")
    if not inference_receipt_path.is_file():
        raise RuntimeError(
            "Missing inference_receipt.json. Run inference-smoke before publish-orpheus."
        )

    train_receipt = read_json(train_receipt_path)
    inference_receipt = read_json(inference_receipt_path)
    if inference_receipt.get("status") != "PASS":
        raise RuntimeError(
            f"Inference receipt status is {inference_receipt.get('status')}; publish blocked."
        )

    dataset_info = None
    dataset_path = Path(str(train_receipt.get("dataset") or ""))
    dataset_info_path = dataset_path.parent.parent / "dataset_info.json"
    if dataset_info_path.is_file():
        dataset_info = read_json(dataset_info_path)

    if not repo_id:
        whoami = _ops_hf(["whoami"], execute=False)
        username = whoami.get("name") or "local-user"
        repo_id = f"{username}/{speaker}-orpheus-lora"

    bundle_dir = publish_dir / "hub_model_bundle"
    if bundle_dir.exists():
        import shutil

        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    import shutil

    for item in lora_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, bundle_dir / item.name)

    card = build_model_card(
        speaker=speaker,
        repo_id=repo_id,
        train_receipt=train_receipt,
        inference_receipt=inference_receipt,
        dataset_info=dataset_info,
    )
    readme = bundle_dir / "README.md"
    readme.write_text(card, encoding="utf-8")

    smoke_wav = Path(str(inference_receipt.get("wav_path") or ""))
    if smoke_wav.is_file():
        shutil.copy2(smoke_wav, bundle_dir / "inference_smoke.wav")
    shutil.copy2(train_receipt_path, bundle_dir / "train_receipt.json")
    shutil.copy2(inference_receipt_path, bundle_dir / "inference_receipt.json")

    validate = _ops_hf(["validate-card", str(readme), "--type", "model"], execute=False)
    if not validate.get("valid"):
        missing = validate.get("missing") or []
        raise RuntimeError(
            "Model card failed ops-huggingface validate-card: "
            + ", ".join(str(item) for item in missing)
        )
    create = _ops_hf(
        ["create-repo", repo_id, "--type", "model", "--private", "--exist-ok", *(["--execute"] if execute else [])],
        execute=execute,
    )
    upload = _ops_hf(
        [
            "upload",
            str(bundle_dir),
            "--repo",
            repo_id,
            "--type",
            "model",
            "--message",
            f"Publish {speaker} Orpheus LoRA",
            *(["--execute"] if execute else []),
        ],
        execute=execute,
    )

    receipt = {
        "schema": "voice_segment_selector.orpheus_publish_receipt.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "DRY_RUN" if not execute else "PUBLISHED",
        "speaker": speaker,
        "repo_id": repo_id,
        "repo_type": "model",
        "private": True,
        "bundle_dir": str(bundle_dir.resolve()),
        "validate_card": validate,
        "create_repo": create,
        "upload": upload,
        "executed": execute,
        "verified": "live" if execute else "dry_run",
    }
    if execute and not upload.get("executed"):
        receipt["status"] = "FAIL"
    (publish_dir / "publish_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def _ops_hf(args: list[str], *, execute: bool) -> dict:
    if not OPS_HF.is_file():
        raise RuntimeError(f"Missing ops-huggingface entrypoint: {OPS_HF}")
    cmd = [str(OPS_HF), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 and execute:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "ops-huggingface failed")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
