#!/usr/bin/env python3
"""Audit Orpheus emotion-tag coverage and write next-action artifacts.

The script is intentionally read-only for candidate state. It does not accept,
reject, generate, export, or train. It summarizes reviewed coverage, identifies
gaps, and writes a bounded request plus an interview packet for items the agent
cannot decide without human review.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ORPHEUS_TAGS = ("laugh", "chuckle", "sigh", "cough", "sniffle", "groan", "yawn", "gasp")
TAG_RE = re.compile(r"<(laugh|chuckle|sigh|cough|sniffle|groan|yawn|gasp)>", re.I)


@dataclass(frozen=True)
class JobInput:
    path: Path
    role: str


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            rows.append({"_parse_error": str(exc), "_path": str(path), "_line": line_no})
            continue
        row["_path"] = str(path)
        row["_line"] = line_no
        rows.append(row)
    return rows


def row_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("candidate_id") or row.get("sample_id") or f"{row.get('_path')}:{row.get('_line')}")


def row_status(row: dict[str, Any]) -> str:
    raw = str(row.get("status") or row.get("review_status") or row.get("review") or "unknown").lower()
    review_status = str(row.get("review_status") or "").lower()
    if raw in {"accept", "accepted"}:
        return "accepted"
    if raw in {"reject", "rejected"}:
        return "rejected"
    if raw == "maybe":
        return "maybe"
    if "pending" in raw or "pending" in review_status:
        return "pending"
    return raw


def row_tag(row: dict[str, Any]) -> str:
    for key in ("tag", "emotion_tag", "orpheus_tag", "label"):
        value = row.get(key)
        if value:
            if isinstance(value, list):
                value = value[0] if value else ""
            text = str(value).strip().lower()
            match = TAG_RE.search(text) or re.fullmatch(r"(laugh|chuckle|sigh|cough|sniffle|groan|yawn|gasp)", text)
            if match:
                return match.group(1).lower()
    for key in ("tts_text", "transcript", "transcript_final", "plain_caption"):
        match = TAG_RE.search(str(row.get(key) or ""))
        if match:
            return match.group(1).lower()
    return "no_tag"


def candidate_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row_id(row),
        "status": row_status(row),
        "tag": row_tag(row),
        "tts_text": row.get("tts_text") or row.get("transcript") or row.get("transcript_final"),
        "audio_path": row.get("audio_path") or row.get("clip") or row.get("path"),
        "source_type": row.get("source_type"),
        "source": row.get("source"),
        "path": row.get("_path"),
    }


def audit_jobs(jobs: list[JobInput], target_per_tag: int) -> dict[str, Any]:
    coverage: dict[str, Any] = {
        f"<{tag}>": {
            "accepted": 0,
            "maybe": 0,
            "pending": 0,
            "rejected": 0,
            "other": 0,
            "accepted_ids": [],
            "maybe_ids": [],
            "pending_ids": [],
            "rejected_ids": [],
            "accepted_examples": [],
            "maybe_examples": [],
            "pending_examples": [],
            "rejected_examples": [],
            "needed_for_target": target_per_tag,
            "status": "missing",
        }
        for tag in ORPHEUS_TAGS
    }
    jobs_report: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []

    for job in jobs:
        path = job.path.expanduser().resolve()
        rows = load_jsonl(path)
        by_tag_status: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            if "_parse_error" in row:
                parse_errors.append(row)
                continue
            tag = row_tag(row)
            status = row_status(row)
            by_tag_status[tag][status] += 1
            if tag not in ORPHEUS_TAGS:
                continue
            bucket = coverage[f"<{tag}>"]
            if status not in {"accepted", "maybe", "pending", "rejected"}:
                status = "other"
            bucket[status] += 1
            bucket[f"{status}_ids"].append(row_id(row))
            examples_key = f"{status}_examples"
            if len(bucket[examples_key]) < 8:
                bucket[examples_key].append(candidate_summary(row))
        jobs_report.append(
            {
                "path": str(path),
                "role": job.role,
                "row_count": len(rows),
                "by_tag_status": {tag: dict(counter) for tag, counter in sorted(by_tag_status.items())},
            }
        )

    for tag in ORPHEUS_TAGS:
        bucket = coverage[f"<{tag}>"]
        accepted = bucket["accepted"]
        bucket["needed_for_target"] = max(0, target_per_tag - accepted)
        if accepted >= target_per_tag:
            bucket["status"] = "target_met"
        elif accepted > 0:
            bucket["status"] = "under_target"
        elif bucket["maybe"] or bucket["pending"]:
            bucket["status"] = "needs_review"
        else:
            bucket["status"] = "missing"

    return {
        "schema": "orpheus_tts_voice_trainer.emotion_coverage_audit.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "target_per_tag": target_per_tag,
        "jobs": jobs_report,
        "coverage": coverage,
        "parse_errors": parse_errors,
    }


def build_loop_request(
    *,
    persona: str,
    voice_id: str,
    voice_name: str,
    audit: dict[str, Any],
    max_attempts: int,
    max_cost_usd: float,
) -> dict[str, Any]:
    missing_or_under = [
        tag.strip("<>")
        for tag, data in audit["coverage"].items()
        if data["status"] in {"missing", "under_target", "needs_review"}
    ]
    return {
        "schema": "subagent_dag_request.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "target_subagent": "agents/orpheus-tts-trainer",
        "persona": persona,
        "elevenlabs_voice_id": voice_id,
        "elevenlabs_voice_name": voice_name,
        "target_orpheus_tags": [f"<{tag}>" for tag in missing_or_under],
        "target_accept_count_per_tag": audit["target_per_tag"],
        "max_attempts": max_attempts,
        "max_cost_usd": max_cost_usd,
        "required_loop": [
            "load_context",
            "preflight_generation",
            "review_prompt_bundle",
            "generate_candidate",
            "analyze_waveform",
            "classify_audio",
            "decide_candidate",
            "mutate_or_store_recipe",
            "interview_if_blocked",
        ],
        "decision_policy": {
            "hard_gates": [
                "Every prompt batch must be reviewed by agents/prompt-reviewer before ElevenLabs generation.",
                "A prompt-reviewer receipt with verdict PASS is required before any non-dry-run generation.",
                "Prompt preflight is not prompt review and cannot unlock provider spend.",
            ],
            "agent_may_accept": [
                "classifier expected label is strong",
                "waveform features match expected tag shape",
                "audio has no lexical words except approved context phrase",
                "persona voice fit is not obviously wrong",
            ],
            "agent_must_interview": [
                "classifier abstains or conflicts with waveform",
                "laugh/chuckle boundary is ambiguous",
                "gasp/yawn/sigh boundary is ambiguous",
                "persona fit is subjective",
                "same failure repeats twice",
            ],
        },
        "coverage_input": audit,
    }


def build_interview_questions(*, persona: str, audit: dict[str, Any]) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []
    for tag, data in audit["coverage"].items():
        if data["status"] == "target_met":
            continue
        maybe = data.get("maybe_examples") or []
        pending = data.get("pending_examples") or []
        examples = (maybe + pending)[:8]
        if not examples:
            continue
        options = [
            {
                "label": "Agent classify first (Recommended)",
                "description": "Run classifier and waveform gates before asking for human decisions.",
            },
            {
                "label": "Human review now",
                "description": "Open these candidate ids in the review UI because the tag boundary is subjective.",
            },
            {
                "label": "Reject current batch",
                "description": "Treat the current unresolved candidates as unsuitable and generate a new prompt batch.",
            },
        ]
        example_lines = [
            f"{item['id']} | {item.get('status')} | {item.get('tts_text')} | {item.get('audio_path')}"
            for item in examples
        ]
        questions.append(
            {
                "id": f"{tag.strip('<>')}_decision",
                "header": tag.strip("<>").title()[:12],
                "text": (
                    f"{persona} {tag} has {data['accepted']} accepted of target {audit['target_per_tag']}. "
                    "How should unresolved candidates be handled?\n\n"
                    + "\n".join(example_lines)
                ),
                "options": options,
                "multi_select": False,
                "recommendation": "Agent classify first (Recommended)",
                "reason": "Use deterministic/audio classifier gates before spending human attention.",
            }
        )
    return {
        "title": f"{persona.title()} Orpheus Emotion Review",
        "context": "Only answer items where classifier/waveform gates cannot confidently separate the intended Orpheus emotion tag.",
        "questions": questions,
    }


def parse_job(value: str) -> JobInput:
    if "=" in value:
        role, path = value.split("=", 1)
        return JobInput(path=Path(path), role=role)
    return JobInput(path=Path(value), role="candidate_state")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", required=True)
    parser.add_argument("--voice-id", required=True)
    parser.add_argument("--voice-name", required=True)
    parser.add_argument("--target-per-tag", type=int, default=20)
    parser.add_argument("--max-attempts", type=int, default=20)
    parser.add_argument("--max-cost-usd", type=float, default=2.0)
    parser.add_argument("--job", action="append", required=True, help="ROLE=/path/to/candidates.jsonl")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    jobs = [parse_job(item) for item in args.job]
    audit = audit_jobs(jobs, args.target_per_tag)
    loop_request = build_loop_request(
        persona=args.persona,
        voice_id=args.voice_id,
        voice_name=args.voice_name,
        audit=audit,
        max_attempts=args.max_attempts,
        max_cost_usd=args.max_cost_usd,
    )
    interview = build_interview_questions(persona=args.persona, audit=audit)

    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coverage.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    (out_dir / "subagent-request.json").write_text(json.dumps(loop_request, indent=2) + "\n", encoding="utf-8")
    (out_dir / "interview-questions.json").write_text(json.dumps(interview, indent=2) + "\n", encoding="utf-8")
    next_tags = ",".join(tag.strip("<>") for tag in loop_request["target_orpheus_tags"])
    next_command = {
        "dry_run_prompt_review": (
            "skills/voice-segment-selector/run.sh generate-orpheus-sfx "
            f"--job-dir {out_dir / 'next-elevenlabs-batch'} "
            f"--speaker {args.persona} "
            f"--tags {next_tags} "
            "--samples-per-tag 20 "
            "--generation-mode voice-tts-context "
            f"--voice-id {args.voice_id!r} "
            f"--voice-name {args.voice_name!r} "
            "--dry-run"
        ),
        "prompt_reviewer_required_receipt": str(
            out_dir / "next-elevenlabs-batch" / "prompt-review" / "prompt-reviewer-receipt.json"
        ),
        "generation_gate": (
            "Do not run non-dry-run generate-orpheus-sfx until agents/prompt-reviewer "
            "writes prompt-review/prompt-reviewer-receipt.json with verdict PASS."
        ),
        "interview_if_needed": f"skills/interview/run.sh --mode html --file {out_dir / 'interview-questions.json'}",
    }
    (out_dir / "next-actions.json").write_text(json.dumps(next_command, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "coverage": str(out_dir / "coverage.json"),
                "subagent_request": str(out_dir / "subagent-request.json"),
                "interview_questions": str(out_dir / "interview-questions.json"),
                "next_actions": str(out_dir / "next-actions.json"),
                "target_tags": loop_request["target_orpheus_tags"],
                "interview_question_count": len(interview["questions"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
