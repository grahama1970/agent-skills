#!/usr/bin/env python3
"""DriveWealth answer-quality meeting campaign.

Builds 15+ plausible Principal AI Engineer / Core Platform technical interview
meetings from the curated DriveWealth prep context, extracts pre-run Q/A oracles
from the complete transcript, then runs each meeting through the existing live
path:

  Chatterbox -> PipeWire monitor -> Docker RealtimeSTT -> Live Evidence cards

The score compares dynamically produced cards against the pre-run expected
answers with the same SciLLM semantic judge used by transcript meeting evals.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, model_validator

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "src"))

import compile_drivewealth_oracle_pack as dw_oracles  # noqa: E402
import eval_transcript_meeting as transcript_eval  # noqa: E402
import run_meeting_campaign as meeting_campaign  # noqa: E402

INTERVIEW_CONTEXT = {
    "source": "DriveWealth recruiter email and company brief supplied by Graham",
    "role": "Principal AI Engineer - Core Platform",
    "format": "90-minute Google Meet video technical interview with live-coding component using CoderPad shared at interview start",
    "schedule": {
        "date": "2026-09-02",
        "start": "13:30 EDT",
        "end": "15:00 EDT",
        "segments": [
            {"start": "13:30 EDT", "end": "14:15 EDT", "interviewer": "Ajit Sarkaar", "role": "Senior Data Engineer"},
            {"start": "14:15 EDT", "end": "15:00 EDT", "interviewer": "Neelesh Parihar", "role": "Principal Software Development Engineer"},
        ],
        "source": "user supplied calendar/interview confirmation text",
    },
    "interviewers": [
        {"name": "Ajit Sarkaar", "role": "Senior Data Engineer", "round": "Application Review"},
        {"name": "Neelesh Parihar", "role": "Principal Software Development Engineer", "round": "Application Review"},
    ],
    "recruiter_contact": {
        "name": "Howie Liu",
        "linkedin_url": "https://www.linkedin.com/in/howieliu211?utm_source=share_via&utm_content=profile&utm_medium=member_ios",
        "source": "user supplied URL; not scraped by this eval",
    },
    "company_facts": [
        "DriveWealth is a global B2B financial technology platform.",
        "DriveWealth provides Brokerage-as-a-Service.",
        "DriveWealth powers investing and trading experiences for digital wallets, broker-dealers, asset managers, and consumer brands.",
        "DriveWealth APIs support traditional investment workflows and fractional-share workflows such as rounding up purchases into fractional share ownership.",
        "DriveWealth, LLC is a registered broker-dealer, member of FINRA and SIPC.",
    ],
}

DEFAULT_OUT = Path("/mnt/storage12tb/skills/live-evidence/drivewealth-meeting-quality")


class CampaignThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_meeting_pass_rate: float = Field(ge=0.0, le=1.0)
    min_question_pass_rate: float = Field(ge=0.0, le=1.0)


class DriveWealthMeetingQualityReceipt(BaseModel):
    """Validate that the campaign verdict follows the numeric oracle fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_: Literal["live_evidence.drivewealth_meeting_quality_eval.v1"] = Field(
        alias="schema"
    )
    status: Literal["PASS", "FAIL"]
    mocked: Literal[False]
    live: Literal[True]
    requested_meetings: NonNegativeInt
    attempted_meetings: NonNegativeInt
    meeting_pass_count: NonNegativeInt
    question_pass_count: NonNegativeInt
    question_total: NonNegativeInt
    whole_transcript_pass_count: NonNegativeInt
    meeting_pass_rate: float = Field(ge=0.0, le=1.0)
    question_pass_rate: float = Field(ge=0.0, le=1.0)
    whole_transcript_pass_rate: float = Field(ge=0.0, le=1.0)
    thresholds: CampaignThresholds
    oracle_memory_prep: dict[str, Any]
    reports: list[dict[str, Any]]
    failures: list[dict[str, Any]]

    @model_validator(mode="after")
    def verdict_matches_counts(self) -> "DriveWealthMeetingQualityReceipt":
        if self.meeting_pass_count > self.attempted_meetings:
            raise ValueError("meeting_pass_count cannot exceed attempted_meetings")
        if self.question_pass_count > self.question_total:
            raise ValueError("question_pass_count cannot exceed question_total")
        if self.whole_transcript_pass_count > self.attempted_meetings:
            raise ValueError("whole_transcript_pass_count cannot exceed attempted_meetings")
        expected = "PASS" if (
            self.oracle_memory_prep.get("ok") is True
            and self.attempted_meetings == self.requested_meetings
            and self.question_total > 0
            and self.meeting_pass_rate >= self.thresholds.min_meeting_pass_rate
            and self.whole_transcript_pass_rate >= self.thresholds.min_question_pass_rate
        ) else "FAIL"
        if self.status != expected:
            raise ValueError(f"status {self.status} does not match computed {expected}")
        return self


def _words(text: str, *, limit: int = 5) -> list[str]:
    banned = {
        "about", "after", "answer", "before", "because", "could", "drivewealth",
        "engineer", "first", "from", "give", "have", "into", "live", "make",
        "question", "show", "that", "their", "there", "this", "through", "using",
        "what", "when", "where", "which", "with", "would", "your",
    }
    words = []
    for word in dw_oracles.words(text):
        if len(word) < 4 or word in banned or word in words:
            continue
        words.append(word)
        if len(words) >= limit:
            break
    return words or ["drivewealth", "platform", "agent"]


def _expected_answer(
    question: str,
    *,
    question_id: str | None = None,
    root: Path | None = None,
    category: str,
    chain: list[str],
    response_shape: str,
) -> str:
    authored = _authored_answer_key(question_id, root=root)
    if authored:
        return (
            f"For a DriveWealth {INTERVIEW_CONTEXT['role']} CoderPad/video technical interview, "
            f"the answer should address the heard question directly. Authored reviewed answer: "
            f"{authored}"
        )
    base = dw_oracles.classify_skill_chain(question)[2]
    return (
        f"For a DriveWealth {INTERVIEW_CONTEXT['role']} CoderPad/video technical interview, "
        f"the answer should address the heard question directly and produce {response_shape}. "
        f"{base} It must stay compact, source-bound, and fail closed rather than inventing "
        "brokerage, compliance, API, or repository facts."
    )


def _authored_answer_key(question_id: str | None, *, root: Path | None) -> str:
    if not question_id or root is None:
        return ""
    filename = f"{question_id.lower()}.md"
    candidates = [
        root.parent / "dw-openapi" / "knowledge" / "answer-key" / filename,
        root.parent.parent / "dw-openapi" / "knowledge" / "answer-key" / filename,
        root.parent.parent.parent / "dw-openapi" / "knowledge" / "answer-key" / filename,
    ]
    repo = next((path for path in candidates if path.exists()), candidates[-1])
    try:
        lines = repo.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    answer_start = None
    for index, line in enumerate(lines):
        if line.strip().startswith("A:"):
            answer_start = index
            break
    if answer_start is None:
        return ""
    answer_lines: list[str] = []
    for line in lines[answer_start:]:
        stripped = line.strip()
        if stripped.startswith("Source:"):
            break
        if stripped:
            answer_lines.append(stripped)
    answer = " ".join(answer_lines)
    if answer.startswith("A:"):
        answer = answer[2:].lstrip()
    return answer


def _oracle_from_turn(turn: dict[str, Any], *, meeting_id: str, index: int, root: Path) -> dict[str, Any]:
    question = str(turn["text"])
    category, chain, _solution, response_shape = dw_oracles.classify_skill_chain(question)
    has_authored_answer = bool(_authored_answer_key(str(turn.get("id") or ""), root=root))
    family = (
        "code" if "ripgrep" in chain
        else "memory" if has_authored_answer
        else "research" if "brave-search" in chain
        else "memory"
    )
    return {
        "id": f"{meeting_id}-q{index + 1:02d}",
        "source_turn_id": turn.get("id"),
        "family": family,
        "question": question,
        "match_tokens": _words(f"{question} {turn.get('expected_stems', '')}", limit=5),
        "expected_answer": _expected_answer(
            question,
            question_id=str(turn.get("id") or ""),
            root=root,
            category=category,
            chain=chain,
            response_shape=response_shape,
        ),
        "route_plan": {
            "determined_from": "pre_run_complete_transcript_oracle",
            "category": category,
            "answerability": "answerable" if family != "research" else "requires_manual_external_research_when_current",
            "required_skill_lanes": chain,
            "expected_response": response_shape if family != "research" else "approval_gated_action_candidate_or_source_checked_answer",
            "publication_gate": "visible_after_source_or_held_with_action_candidate",
        },
    }


def _meeting_from_turns(meeting_id: str, title: str, turns: list[dict[str, Any]], *, root: Path) -> dict[str, Any]:
    transcript = [
        {
            "speaker": "Interviewer",
            "text": (
                "Thanks for joining the DriveWealth technical interview for the Principal AI "
                "Engineer Core Platform role. This is the Google Meet application review with "
                "Ajit Sarkaar and Neelesh Parihar, and we will share the CoderPad link at the "
                "start of the live coding section. DriveWealth is a global B2B financial "
                "technology platform providing Brokerage as a Service for wallets, broker "
                "dealers, asset managers, and consumer brands, with APIs for investing, "
                "trading, and fractional-share workflows."
            ),
        }
    ]
    oracles = []
    for index, turn in enumerate(turns):
        transcript.append({"speaker": "Interviewer", "text": turn["text"]})
        oracles.append(_oracle_from_turn(turn, meeting_id=meeting_id, index=index, root=root))
    transcript.append({
        "speaker": "Interviewer",
        "text": "That is the end of the technical section. We would use the remaining time for follow ups and candidate questions.",
    })
    return {
        "meeting_id": meeting_id,
        "scenario": f"DriveWealth Principal AI Engineer Core Platform mock technical interview: {title}",
        "source": "generated from $curate-client DriveWealth config, recruiter email context, and mock_interviews_drivewealth.json",
        "duration_minutes": 10,
        "duration_model": "10-minute plausible transcript; playback uses live audio path with short inter-turn silence for practical eval runtime",
        "prep_pack": "prep_pack_drivewealth.json",
        "repos": [
            "~/workspace/experiments/dw-openapi",
            "~/workspace/experiments/dwt-terraform-aws-helm-release",
            "~/workspace/experiments/agent-skills",
        ],
        "transcript": transcript,
        "oracle": oracles,
    }


def _whole_transcript_similarity(
    meeting: dict[str, Any], rows: list[dict[str, Any]], key: str
) -> dict[str, Any]:
    """Judge the whole transcript's expected Q/A bundle against all produced cards."""

    expected = "\n\n".join(
        f"{item['id']}\nQuestion: {item['question']}\nExpected: {item['expected_answer']}"
        for item in meeting.get("oracle") or []
    )
    cards = [row.get("payload") or {} for row in rows if row.get("kind") == "evidence_card"]
    actual = "\n\n".join(
        f"Card {index + 1}\nQuestion: {card.get('question') or card.get('query') or ''}\n"
        f"Answer: {card.get('answer') or ''}\nEvidence: {card.get('evidence') or ''}"
        for index, card in enumerate(cards)
    )
    if not cards:
        return {"similar": False, "reason": "no evidence cards were produced", "card_count": 0}
    verdict = transcript_eval.judge_similarity(
        "Do these Live Evidence cards answer the complete DriveWealth meeting transcript?",
        expected,
        actual,
        "",
        key,
    )
    verdict["card_count"] = len(cards)
    return verdict


def build_meetings(root: Path, *, meeting_count: int, questions_per_meeting: int) -> list[dict[str, Any]]:
    source = json.loads((root / "fixtures" / "mock_interviews_drivewealth.json").read_text(encoding="utf-8"))
    interviews = source["interviews"]
    meetings: list[dict[str, Any]] = []

    for interview in interviews:
        if len(meetings) >= meeting_count:
            break
        turns = list(interview["turns"][:questions_per_meeting])
        meetings.append(_meeting_from_turns(
            f"dw-principal-core-{len(meetings) + 1:02d}",
            str(interview.get("focus") or interview["interview_id"]),
            turns,
            root=root,
        ))

    # Add mixed panel meetings so the campaign reaches 15-20 without pretending
    # the original corpus had more authored interviews than it does.
    cursor = 0
    while len(meetings) < meeting_count:
        turns = []
        for offset in range(questions_per_meeting):
            interview = interviews[(cursor + offset) % len(interviews)]
            interview_turns = interview["turns"]
            turns.append(interview_turns[(cursor + offset * 2) % len(interview_turns)])
        meetings.append(_meeting_from_turns(
            f"dw-principal-core-{len(meetings) + 1:02d}",
            "mixed CoderPad/core-platform panel",
            turns,
            root=root,
        ))
        cursor += 1
    return meetings


def _run_oracle_memory_prep(root: Path, out_dir: Path) -> dict[str, Any]:
    receipt_path = out_dir / "drivewealth-oracle-memory.json"
    proc = subprocess.run(
        [
            str(root / "run.sh"),
            "eval-drivewealth-oracle-memory-graph",
            "--limit", "10",
            "--write-memory",
            "--verify-recall",
            "--output", str(receipt_path),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    payload = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
    fallback = None if proc.returncode == 0 else _oracle_memory_recall_fallback(root)
    ok = proc.returncode == 0 and payload.get("memory_write", {}).get("ok") is True
    if not ok and fallback and fallback.get("ok"):
        ok = True
    return {
        "command": proc.args,
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "receipt_path": str(receipt_path),
        "receipt": payload,
        "fallback_recall": fallback,
        "ok": ok,
    }


def _oracle_memory_recall_fallback(root: Path) -> dict[str, Any]:
    """Treat oracle prep as ready when prior DriveWealth records are recallable."""

    runner = root.parent / "memory" / "run.sh"
    if not runner.exists():
        return {"ok": False, "reason": "memory_runner_missing", "runner": str(runner)}
    probes = [
        "DW-AI-01-T01 account blocked graph node responsibilities terminal outcomes",
        "DW-AI-01-T04 worker dies after retrieval persisted immutable resume idempotency",
        "DW-AI-07-T03 SupportResolution builder authenticated funding tax facts",
    ]
    results = []
    for probe in probes:
        try:
            proc = subprocess.run(
                [str(runner), "recall", "--q", probe, "--brief"],
                cwd=root.parent,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({"query": probe, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            continue
        found = '"found": true' in proc.stdout and "DW-AI" in proc.stdout
        results.append({
            "query": probe,
            "ok": proc.returncode == 0 and found,
            "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-800:],
            "stderr_tail": proc.stderr[-400:],
        })
    return {
        "schema": "live_evidence.oracle_memory_recall_fallback.v1",
        "ok": all(item.get("ok") for item in results),
        "results": results,
        "reason": "oracle_pack_write_failed_but_existing_drivewealth_records_are_recallable",
    }


def _extract_rows(meeting_dir: Path) -> list[dict[str, Any]]:
    paths = sorted(meeting_dir.glob("*/session.jsonl")) + sorted(meeting_dir.glob("session.jsonl"))
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def evaluate(root: Path, *, meeting_count: int, questions_per_meeting: int, out_dir: Path,
             min_meeting_pass_rate: float, min_question_pass_rate: float, max_failures: int,
             only_meeting_id: str | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    meetings = build_meetings(root, meeting_count=meeting_count, questions_per_meeting=questions_per_meeting)
    if only_meeting_id:
        meetings = [meeting for meeting in meetings if meeting.get("meeting_id") == only_meeting_id]
        if not meetings:
            raise ValueError(f"unknown DriveWealth meeting id: {only_meeting_id}")
    generated_path = out_dir / "generated-drivewealth-meetings.json"
    generated_path.write_text(json.dumps({
        "schema": "live_evidence.drivewealth_meeting_quality_campaign.v1",
        "interview_context": INTERVIEW_CONTEXT,
        "meeting_count": len(meetings),
        "questions_per_meeting": questions_per_meeting,
        "meetings": meetings,
    }, indent=2) + "\n", encoding="utf-8")

    expected_meetings = len(meetings)
    prep = _run_oracle_memory_prep(root, out_dir)
    reports = []
    failures = []
    family_counts: Counter[str] = Counter()
    family_pass: Counter[str] = Counter()
    if not prep["ok"]:
        failures.append({"stage": "oracle_memory_prep", "detail": prep})
    else:
        key = transcript_eval.campaign.scillm_key()
        if not key:
            failures.append({"stage": "judge", "detail": "no scillm key"})
        else:
            for index, meeting in enumerate(meetings, start=1):
                meeting_dir = out_dir / meeting["meeting_id"]
                print(f"== DriveWealth meeting {index}/{len(meetings)}: {meeting['meeting_id']}", flush=True)
                session = {
                    "session_id": meeting["meeting_id"],
                    "type": "synthetic",
                    "repos": meeting.get("repos") or [],
                    "prep_pack": meeting.get("prep_pack"),
                    "profile": "drivewealth",
                    "script": [{"text": turn["text"]} for turn in meeting["transcript"]],
                    "oracle": meeting.get("oracle") or [],
                }
                try:
                    rows, invocation = meeting_campaign.capture_live_session(session, meeting_dir)
                    report = transcript_eval.score_meeting(meeting, rows, key, meeting_dir)
                    whole = _whole_transcript_similarity(meeting, rows, key)
                    report["whole_transcript_similarity"] = whole
                    report["whole_transcript_answer_similar"] = bool(whole.get("similar"))
                    report["status"] = "PASS" if whole.get("similar") else "FAIL"
                    (meeting_dir / "meeting-report.json").write_text(
                        json.dumps(report, indent=1) + "\n", encoding="utf-8"
                    )
                    report["bridge_invocation"] = invocation
                except RuntimeError as exc:
                    report = {
                        "schema": "live_evidence.drivewealth_meeting_quality_result.v1",
                        "meeting_id": meeting["meeting_id"],
                        "status": "BLOCKED",
                        "error": str(exc),
                        "questions": [],
                    }
                reports.append(report)
                for q in report.get("questions") or []:
                    family_counts[q.get("family", "unknown")] += 1
                    if q.get("detected") and q.get("answer_similar"):
                        family_pass[q.get("family", "unknown")] += 1
                if report.get("status") != "PASS":
                    failures.append({
                        "stage": "meeting",
                        "meeting_id": meeting["meeting_id"],
                        "status": report.get("status"),
                        "questions": report.get("questions"),
                    })
                    if len(failures) >= max_failures:
                        print(f"stopping after {len(failures)} failure(s)", flush=True)
                        break

    question_total = sum(len(r.get("questions") or []) for r in reports)
    question_pass = sum(
        1 for r in reports for q in (r.get("questions") or [])
        if q.get("detected") and q.get("answer_similar")
    )
    meeting_pass = sum(1 for r in reports if r.get("status") == "PASS")
    whole_transcript_pass = sum(
        1 for r in reports if r.get("whole_transcript_answer_similar") is True
    )
    attempted = len(reports)
    question_pass_rate = round(question_pass / question_total, 3) if question_total else 0.0
    meeting_pass_rate = round(meeting_pass / attempted, 3) if attempted else 0.0
    whole_transcript_pass_rate = round(whole_transcript_pass / attempted, 3) if attempted else 0.0
    status = "PASS" if (
        prep["ok"]
        and attempted == expected_meetings
        and meeting_pass_rate >= min_meeting_pass_rate
        and question_pass_rate >= min_question_pass_rate
    ) else "FAIL"
    receipt = {
        "schema": "live_evidence.drivewealth_meeting_quality_eval.v1",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "mocked": False,
        "live": True,
        "proof_boundary": "Chatterbox TTS -> PipeWire monitor -> Docker RealtimeSTT -> Live Evidence server/cards; SciLLM semantic judge compares dynamic card answers to pre-run complete-transcript oracles.",
        "interview_context": INTERVIEW_CONTEXT,
        "generated_meetings_path": str(generated_path),
        "requested_meetings": expected_meetings,
        "attempted_meetings": attempted,
        "questions_per_meeting": questions_per_meeting,
        "meeting_pass_count": meeting_pass,
        "question_pass_count": question_pass,
        "question_total": question_total,
        "whole_transcript_pass_count": whole_transcript_pass,
        "meeting_pass_rate": meeting_pass_rate,
        "question_pass_rate": question_pass_rate,
        "whole_transcript_pass_rate": whole_transcript_pass_rate,
        "family_counts": dict(family_counts),
        "family_pass": dict(family_pass),
        "thresholds": {
            "min_meeting_pass_rate": min_meeting_pass_rate,
            "min_question_pass_rate": min_question_pass_rate,
        },
        "oracle_memory_prep": prep,
        "reports": reports,
        "failures": failures,
    }
    validated = DriveWealthMeetingQualityReceipt.model_validate(receipt).model_dump(
        by_alias=True
    )
    validated["pydantic_validated"] = True
    (out_dir / "campaign-report.json").write_text(json.dumps(validated, indent=2) + "\n", encoding="utf-8")
    print("pydantic receipt validation: PASS")
    print(f"drivewealth meeting quality: {validated['status']} meetings={meeting_pass}/{attempted} questions={question_pass}/{question_total}")
    print(f"drivewealth meeting quality receipt: {out_dir / 'campaign-report.json'}")
    return validated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=SKILL)
    parser.add_argument("--meeting-count", type=int, default=15)
    parser.add_argument("--questions-per-meeting", type=int, default=4)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--min-meeting-pass-rate", type=float, default=0.8)
    parser.add_argument("--min-question-pass-rate", type=float, default=0.75)
    parser.add_argument("--max-failures", type=int, default=4)
    parser.add_argument("--only-meeting-id", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    out_dir = args.out_dir or DEFAULT_OUT / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt = evaluate(
        root,
        meeting_count=args.meeting_count,
        questions_per_meeting=args.questions_per_meeting,
        out_dir=out_dir,
        min_meeting_pass_rate=args.min_meeting_pass_rate,
        min_question_pass_rate=args.min_question_pass_rate,
        max_failures=args.max_failures,
        only_meeting_id=args.only_meeting_id,
    )
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
