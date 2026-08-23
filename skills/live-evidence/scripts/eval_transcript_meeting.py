#!/usr/bin/env python3
"""Agentic transcript-meeting eval (goal v2).

The design (Graham, 2026-08-23): take a COMPLETE speaker transcript -- a real
YouTube transcript or an invented multi-speaker meeting -- and extract its
answerable questions and their expected answers IN ADVANCE. Then play that
transcript through chatterbox in real time down the live path, and check
whether the evidence cards the product produces are SEMANTICALLY SIMILAR to
the expected answers.

Why this over the token-family campaign: token-in-query matching is brittle
(STT variance flaps the surface words) and it never checks that the card
actually ANSWERS the question. Here the questions come from the transcript,
and an agentic judge (SciLLM, the same provider boundary the resolver uses)
decides similarity of the produced answer to the expected one.

Proof boundary: audio is live (chatterbox render -> PipeWire null sink),
transcription is live (Docker RealtimeSTT GPU), retrieval is live (Memory +
ripgrep + the stage-2 solver). The similarity verdict is an agentic SciLLM
judge, named as such -- not a deterministic proxy. No scillm key -> the run
reports INFRA_BLOCKED, never a fake pass.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))
sys.path.insert(0, str(SKILL / "scripts"))

import run_meeting_campaign as campaign_mod  # capture_live_session, synth
import run_g2i_campaign as campaign  # ROOT + scillm_key (env, then docker inspect)

OUT_ROOT = Path("/mnt/storage12tb/skills/live-evidence/meeting-campaign/transcript")
JUDGE_URL = "http://127.0.0.1:4001/v1/chat/completions"
JUDGE_MODEL = "claude-sonnet-5"

JUDGE_PROMPT = """You are grading a live meeting-assistant card against an expected answer.

QUESTION asked in the meeting:
{question}

EXPECTED answer (the information a correct card must convey):
{expected}

CARD the assistant actually produced:
answer: {answer}
evidence: {evidence}

Does the CARD convey the same core information as the EXPECTED answer? Judge by
MEANING, not wording. It is similar if a human reading the card would learn the
expected answer's key facts. It is NOT similar if the card is on-topic but
misses or contradicts the expected key facts, or is an insufficient/empty card.

Reply with ONLY a JSON object: {{"similar": true|false, "reason": "<one sentence>"}}"""


def judge_similarity(question: str, expected: str, answer: str, evidence: str,
                     key: str) -> dict[str, Any]:
    """One agentic SciLLM call: is the produced answer similar to expected?"""

    payload = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": JUDGE_PROMPT.format(
            question=question, expected=expected,
            answer=answer or "(no answer)", evidence=(evidence or "(none)")[:1500])}],
        "reasoning_effort": "low",
        "stream": False,
    }
    request = urllib.request.Request(
        JUDGE_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}",
                 "X-Caller-Skill": "live-evidence",
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=90) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        return {"similar": False, "reason": f"unparseable judge reply: {content[:120]}"}
    return json.loads(content[start:end + 1])


def _card_for(cards: list[dict[str, Any]], tokens: list[str]) -> dict[str, Any] | None:
    """Best card whose query/question carries >=2 of the oracle match tokens."""

    best, best_score = None, 1
    for card in cards:
        blob = (str(card.get("query") or "") + " " + str(card.get("question") or "")).lower()
        score = sum(1 for t in tokens if t.lower() in blob)
        if score > best_score:
            best, best_score = card, score
    return best


def score_meeting(meeting: dict[str, Any], rows: list[dict[str, Any]],
                  key: str, out_dir: Path) -> dict[str, Any]:
    cards = [r["payload"] for r in rows if r.get("kind") == "evidence_card"]
    transcript = [r["payload"] for r in rows if r.get("kind") == "transcript"]
    proposal_blob = json.dumps(
        [r["payload"] for r in rows if r.get("kind") == "action_candidates_proposed"]).lower()

    results = []
    for item in meeting["oracle"]:
        tokens = item["match_tokens"]
        detected = any(
            sum(1 for t in tokens if t.lower() in str(e.get("text") or "").lower()) >= 2
            for e in transcript)
        if item["family"] == "research":
            has_proposal = "fact_check" in proposal_blob and any(
                t.lower() in proposal_blob for t in tokens[:2])
            results.append({
                "id": item["id"], "family": "research", "detected": detected,
                "card_matched": has_proposal, "answer_similar": has_proposal,
                "reason": "bounded research proposed" if has_proposal
                else "no research proposal",
            })
            continue
        card = _card_for(cards, tokens)
        if card is None:
            results.append({"id": item["id"], "family": item["family"],
                            "detected": detected, "card_matched": False,
                            "answer_similar": False, "reason": "no matching card"})
            continue
        verdict = judge_similarity(
            item["question"], item["expected_answer"],
            str(card.get("answer") or ""), str(card.get("evidence") or ""), key)
        results.append({
            "id": item["id"], "family": item["family"], "detected": detected,
            "card_matched": True, "answer_similar": bool(verdict.get("similar")),
            "reason": str(verdict.get("reason") or ""),
            "card_answer": str(card.get("answer") or "")[:200],
        })

    report = {
        "schema": "live_evidence.transcript_meeting_report.v1",
        "meeting_id": meeting["meeting_id"], "audio_live": True, "mocked": False,
        "judge": {"kind": "agentic_scillm", "model": JUDGE_MODEL},
        "transcript_events": len(transcript), "cards": len(cards),
        "questions": results,
        "status": "PASS" if all(
            q["detected"] and q["answer_similar"] for q in results) else "FAIL",
    }
    (out_dir / "meeting-report.json").write_text(json.dumps(report, indent=1))
    return report


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else SKILL
    campaign.ROOT = root
    campaign_mod.campaign.ROOT = root
    key = campaign.scillm_key()
    if not key:
        print("transcript meeting: INFRA_BLOCKED (no scillm key; agentic judge unavailable)")
        return 0

    spec = json.loads((root / "fixtures" / "transcript_meetings.json").read_text())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_root = OUT_ROOT / stamp
    reports = []
    for meeting in spec["meetings"]:
        print(f"== meeting {meeting['meeting_id']}")
        session = {
            "session_id": meeting["meeting_id"], "type": "synthetic",
            "repos": meeting.get("repos") or [],
            "fixture_repo": meeting.get("fixture_repo"),
            "script": [{"text": turn["text"]} for turn in meeting["transcript"]],
        }
        try:
            rows, _ = campaign_mod.capture_live_session(
                session, out_root / meeting["meeting_id"])
        except RuntimeError as exc:
            print(f"  INFRA_BLOCKED: {exc}")
            return 0
        report = score_meeting(meeting, rows, key, out_root / meeting["meeting_id"])
        reports.append(report)
        for q in report["questions"]:
            print(f"  {q['id']} ({q['family']}): detected={q['detected']} "
                  f"card={q['card_matched']} similar={q['answer_similar']} — {q['reason']}")
        print(f"  -> {report['status']}")

    overall = {"schema": "live_evidence.transcript_meeting_campaign.v1", "run": stamp,
               "meetings": reports,
               "status": "PASS" if reports and all(
                   r["status"] == "PASS" for r in reports) else "FAIL"}
    (out_root / "campaign-report.json").write_text(json.dumps(overall, indent=1))
    print(f"transcript meeting: {overall['status']} -> {out_root}/campaign-report.json")
    return 0 if overall["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
