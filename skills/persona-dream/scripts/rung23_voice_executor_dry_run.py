#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def story_sentences(story):
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", story.strip()) if part.strip()]
    return parts[:6] or [story[:220].strip() or "No spoken line available."]


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", required=True)
parser.add_argument("--run-dir", required=True)
parser.add_argument("--story-chain-receipt", required=True)
args = parser.parse_args()

run_dir = Path(args.run_dir)
story_chain_path = Path(args.story_chain_receipt)
story_chain = load_json(story_chain_path)
executor_receipt = story_chain.get("advance_handoff", {}).get("executor_receipt", {})
story_contract_path = Path(executor_receipt.get("story_contract", {}).get("path", ""))
voice_out = run_dir / "voice_output"
voice_plan_path = voice_out / "voice_handoff_plan.json"

blockers = []
story_contract = {}
if not story_contract_path.is_file():
    blockers.append({"code": "story_contract_missing", "severity": "blocking"})
else:
    story_contract = load_json(story_contract_path)
    if story_contract.get("schema") != "persona_dream.story_contract.v1":
        blockers.append({"code": "story_contract_schema_mismatch", "severity": "blocking"})
    if not str(story_contract.get("story", "")).strip():
        blockers.append({"code": "story_text_missing", "severity": "blocking"})

speakers = story_contract.get("speaking_characters") or ["unnamed_narrator"]
lines = []
for idx, sentence in enumerate(story_sentences(story_contract.get("story", "")), 1):
    lines.append(
        {
            "line_id": f"line_{idx:02d}",
            "speaker": speakers[(idx - 1) % len(speakers)],
            "text": sentence,
            "source": "story_contract.story",
            "tts_required": False,
            "preview_only": True,
        }
    )

voice_plan = {
    "schema": "persona_dream.voice_handoff_plan.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "source_story_contract": {
        "path": str(story_contract_path),
        "sha256": file_hash(story_contract_path) if story_contract_path.is_file() else "",
    },
    "speakers": [
        {
            "speaker": speaker,
            "voice_identity_boundary": "fictional persona voice only",
            "provider_voice_id_bound": False,
            "local_preview_allowed": True,
        }
        for speaker in speakers
    ],
    "lines": lines,
    "provider_readiness": "blocked_until_authoritative_voice_provenance",
    "live_call_performed": False,
    "paid_call_performed": False,
}
if not blockers:
    atomic_write(voice_plan_path, voice_plan)

receipt = {
    "schema": "persona_dream.rung23_voice_executor_receipt.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung23_voice_executor_dry_run.py",
    "phase": "voice",
    "executor": "pipeline_s04_voice_dry_run",
    "executor_readonly": True,
    "story_chain_receipt": {
        "path": str(story_chain_path),
        "sha256": file_hash(story_chain_path),
        "schema": story_chain.get("schema"),
    },
    "story_contract": {
        "path": str(story_contract_path),
        "sha256": file_hash(story_contract_path) if story_contract_path.is_file() else "",
        "schema": story_contract.get("schema"),
        "artifact_id": story_contract.get("artifact_id"),
        "speaking_characters": speakers,
        "target_duration_s": story_contract.get("target_duration_s"),
    },
    "voice_handoff_plan": {
        "path": str(voice_plan_path),
        "sha256": file_hash(voice_plan_path) if voice_plan_path.is_file() else "",
        "schema": voice_plan.get("schema"),
        "speaker_count": len(voice_plan.get("speakers", [])),
        "line_count": len(voice_plan.get("lines", [])),
        "provider_readiness": voice_plan.get("provider_readiness"),
    },
    "output_contract": {
        "phase": "voice",
        "status": "READY_FOR_SHARED_GATE",
        "artifact_type": "voice_handoff_plan",
    },
    "unresolved_blockers": blockers,
    "active_artifact_mutation_performed": False,
    "provider_call_performed": False,
    "live_call_performed": False,
    "paid_call_performed": False,
}
receipt["ok"] = (
    not blockers
    and voice_plan_path.is_file()
    and receipt["voice_handoff_plan"]["schema"] == "persona_dream.voice_handoff_plan.v1"
    and receipt["voice_handoff_plan"]["line_count"] > 0
    and receipt["voice_handoff_plan"]["speaker_count"] > 0
    and receipt["provider_call_performed"] is False
    and receipt["live_call_performed"] is False
    and receipt["paid_call_performed"] is False
)

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 23, "executor": "voice", "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
