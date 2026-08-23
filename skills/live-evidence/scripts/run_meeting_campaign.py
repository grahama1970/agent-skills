#!/usr/bin/env python3
"""Goal-v2 meeting campaign: self-testing sessions with pre-derived oracles.

Each session is REAL audio through the live path (PipeWire null sink -> Docker
RealtimeSTT -> resolver -> retrieval -> cards). The question oracle is derived
BEFORE the run, and each expected question names the family its answer
provably lives in:

- memory  -> the matched card must carry a memory-lane source;
- research-> a bounded "Research externally" proposal must appear;
- code    -> the matched card must carry a ripgrep/code source with a path.

Session types:
- synthetic: an owned meeting script rendered line-by-line by the LIVE
  chatterbox server, concatenated with sox, and played through the null sink
  (a fully closed loop: the Sparta Explorer session asks about content that
  provably exists in /memory and the sparta repo);
- wav: a stored consented recording (the pinned interview) with its oracle.

Per oracle question the report records detection, family correctness, and
question-onset-to-usable-card latency measured from the FIRST transcript
event of the question to the matched card's publication (goal v2's metric).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))
sys.path.insert(0, str(SKILL / "scripts"))

import run_g2i_campaign as campaign  # Server/http helpers
import eval_live_youtube_oracle as oracle_mod  # null sink + bridge runner

CHATTERBOX = "http://127.0.0.1:8018"
CHATTERBOX_LOGS = Path.home() / "workspace" / "experiments" / "chatterbox" / "logs"
OUT_ROOT = Path("/mnt/storage12tb/skills/live-evidence/meeting-campaign")


def synthesize_script(lines: list[dict[str, Any]], work: Path) -> Path:
    """Render each line with the LIVE chatterbox server; concat with sox."""

    pieces: list[Path] = []
    silence = work / "sil.wav"
    for index, line in enumerate(lines):
        label = f"campaign-{hashlib.sha256(line['text'].encode()).hexdigest()[:10]}"
        request = urllib.request.Request(
            f"{CHATTERBOX}/synthesize",
            data=json.dumps({"text": line["text"], "label": label}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode())
        wav = CHATTERBOX_LOGS / f"{label}.wav"
        if not wav.is_file():
            wav = Path(str(payload.get("path") or ""))
        if not wav.is_file():
            raise RuntimeError(f"chatterbox produced no wav for line {index}")
        pieces.append(wav)
    # 2.5s silence between lines, matching the first piece's format. Real
    # agenda questions ("Next question ...", "Last one for the code side ...")
    # carry natural pauses; chatterbox renders each line tightly, and 0.8s
    # sits below RealtimeSTT's VAD finalization threshold, so three questions
    # buffered into one cumulative window and the resolver authored a single
    # merged canonical question (observed live: version+QRA merged, QRA lost).
    # 2.5s reliably exceeds any reasonable post-speech silence and forces a
    # clean final between questions -- more realistic, not a looser oracle.
    subprocess.run(["sox", str(pieces[0]), str(silence), "trim", "0", "2.5", "vol", "0"],
                   check=True, capture_output=True)
    out = work / "session.wav"
    interleaved: list[str] = []
    for piece in pieces:
        interleaved.extend([str(piece), str(silence)])
    subprocess.run(["sox", *interleaved, str(out)], check=True, capture_output=True)
    return out


def capture_live_session(
    session: dict[str, Any], out_dir: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Render/play one session through the real live path and return its journal.

    Shared by the token-family campaign scorer (score_session) and the
    agentic answer-similarity eval (eval_transcript_meeting): both must run
    through the IDENTICAL chatterbox -> PipeWire -> Docker STT -> resolver ->
    retrieval path, so the capture half lives here once. Returns
    (journal_rows, bridge_invocation); a BLOCKED session raises RuntimeError.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)
    if session["type"] == "synthetic":
        wav = synthesize_script(session["script"], work)
        # Budget from the ACTUAL rendered duration plus a tail: guessing from
        # line count under-budgeted once the inter-line silence grew and the
        # capture stopped mid-question (the QRA line was cut to "Where in our
        # Spark--"). soxi -D is the real length; +18s covers late solve work.
        rendered = float(subprocess.run(
            ["soxi", "-D", str(wav)], check=True, capture_output=True, text=True
        ).stdout.strip())
        max_seconds = rendered + 18.0
    else:
        wav = next((Path(c) for c in session["wav_candidates"] if Path(c).is_file()), None)
        if wav is None:
            raise RuntimeError("no stored wav available")
        max_seconds = float(session.get("max_seconds") or 108)

    repo_paths = [str(Path(r).expanduser()) for r in session.get("repos") or []]
    if session.get("fixture_repo") == "parentheses":
        fixture_repo = work / "live-evidence-proof"
        if not fixture_repo.exists():
            oracle_mod.write_repo(fixture_repo)
        repo_paths.append(str(fixture_repo))
    repos = ":".join(repo_paths)
    server_work = campaign.import_tmp(f"campaign-{session['session_id'][:12]}")
    server = campaign.Server(server_work / "server", live_resolver=True,
                             memory_url="http://127.0.0.1:8601",
                             repos=repos or None)

    # A client-meeting / leading-a-presentation scenario loads a briefing pack
    # so talking points surface as the other side opens a door -- a different
    # capability mix than a Q&A standup, exercised through the same live path.
    if session.get("briefing_pack"):
        pack = json.loads((SKILL / "fixtures" / session["briefing_pack"]).read_text())
        campaign.http("POST", f"{server.url}/api/briefing/load", pack)

    sink = f"le-campaign-{server.port}"
    oracle_mod.create_virtual_sink(sink)
    try:
        bridge_args = SimpleNamespace(
            playback_target=sink, capture_target=sink, capture_kind="sink-monitor",
            docker_image="live-evidence-realtimestt-gpu:local",
            max_seconds=max_seconds, tail_seconds=2.5,
            model="base.en", realtime_model="tiny.en", compute_type="int8",
        )
        invocation = oracle_mod.run_bridge(
            bridge_args, backend_url=server.url, source_wav=wav, output_dir=out_dir,
        )
        # Let late resolver/solver work land: the last question often arrives
        # in the final flushed at stream end, so wait for the journal to
        # QUIESCE (no growth for 12s) instead of a fixed sleep that races the
        # in-flight solve (observed live: the QRA card lost to a 30s cutoff).
        # A solve journals nothing between its ledger opening and its card, so
        # size-quiescence alone still races the last in-flight answer. Wait
        # until every OPENED question has a card or an explicit discard, then
        # a short idle, capped hard at 120s.
        journal_path = None
        rows: list[dict[str, Any]] = []
        deadline = time.monotonic() + 120
        last_size, quiet_since = -1, time.monotonic()
        while time.monotonic() < deadline:
            journal_path = next(server.data_dir.glob("*/session.jsonl"), None)
            size = journal_path.stat().st_size if journal_path else 0
            if size != last_size:
                last_size, quiet_since = size, time.monotonic()
            rows = [json.loads(line) for line in journal_path.read_text().splitlines()] \
                if journal_path else []
            opened = {r["payload"].get("question_id") for r in rows
                      if r.get("kind") == "requirement_ledger_opened"}
            settled = {r["payload"].get("question_id") for r in rows
                       if r.get("kind") == "evidence_card"
                       or "discard" in str(r.get("kind"))}
            if not (opened - settled) and time.monotonic() - quiet_since >= 8:
                break
            time.sleep(2)
    finally:
        oracle_mod.destroy_virtual_sink(sink)
        server.close()

    return rows, invocation


def run_session(session: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    try:
        rows, invocation = capture_live_session(session, out_dir)
    except RuntimeError as exc:
        return {"session_id": session["session_id"], "status": "BLOCKED",
                "reason": str(exc)}
    return score_session(session, rows, invocation, out_dir)


def score_session(session: dict[str, Any], rows: list[dict[str, Any]],
                  invocation: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    transcript = [r["payload"] for r in rows if r.get("kind") == "transcript"]
    cards = [r for r in rows if r.get("kind") == "evidence_card"]
    proposals = [r["payload"] for r in rows if r.get("kind") == "action_candidates_proposed"]
    pending_summary = json.dumps(
        [r["payload"] for r in rows if r.get("kind") in
         ("action_candidates_proposed", "action_executed")]).lower()

    def stamp(row: dict[str, Any]) -> float:
        return datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).timestamp() \
            if "ts" in row else 0.0

    results = []
    for expected in session["oracle"]:
        tokens = [t.lower() for t in expected["question_tokens"]]
        onset = None
        question_events: list[dict[str, Any]] = []
        for r in rows:
            if r.get("kind") != "transcript":
                continue
            text = str(r["payload"].get("text") or "").lower()
            if sum(1 for t in tokens if t in text) >= 2:
                if onset is None:
                    onset = r
                question_events.append(r)
        matched_card = None
        for r in cards:
            blob = (str(r["payload"].get("query") or "") + " "
                    + str(r["payload"].get("question") or "")).lower()
            if sum(1 for t in tokens if t in blob) >= 2:
                matched_card = r
                break
        family = expected["family"]
        family_ok = False
        detail = ""
        if family == "research":
            # A bounded external-research proposal satisfies the family whether
            # it came from the auto-proposal path ("Research externally: ...")
            # or the resolver authored a fact_check candidate directly.
            research_blobs = [
                str(c.get("summary") or "") + " " + str(c.get("kind") or "")
                for p in proposals for c in p.get("candidates") or []
                if c.get("kind") == "fact_check"
            ]
            if "research externally" in pending_summary:
                research_blobs.append(pending_summary)
            family_ok = any(
                sum(1 for t in tokens if t in blob.lower()) >= 2
                for blob in research_blobs
            )
            detail = "research proposal present" if family_ok else "no research proposal"
        elif matched_card is not None:
            lanes = {str(s.get("lane")) for s in matched_card["payload"].get("sources") or []}
            if family == "memory":
                family_ok = "memory" in lanes
            elif family == "code":
                family_ok = bool(lanes & {"ripgrep", "code"}) and any(
                    s.get("path") for s in matched_card["payload"].get("sources") or [])
            detail = f"lanes={sorted(lanes)}"
        latency = None
        latency_from_speech_end = None
        if onset is not None and matched_card is not None:
            def _t(row: dict[str, Any]) -> float:
                return datetime.fromisoformat(
                    str(row["payload"]["created_at"]).replace("Z", "+00:00")
                ).timestamp()

            try:
                t1 = _t(matched_card)
                latency = round(t1 - _t(onset), 2)
                # Speech-end proxy: the LAST transcript event that still
                # carries the question and precedes card publication -- the
                # closest observable moment to the speaker finishing the ask.
                ends = [_t(e) for e in question_events if _t(e) <= t1]
                if ends:
                    latency_from_speech_end = round(t1 - max(ends), 2)
            except Exception:
                latency = None
        results.append({
            "id": expected["id"], "family": family,
            "question_detected": onset is not None,
            "card_matched": matched_card is not None or family == "research",
            "family_correct": family_ok,
            "onset_to_card_s": latency,
            "speech_end_to_card_s": latency_from_speech_end,
            "detail": detail,
        })

    report = {
        "schema": "live_evidence.meeting_session_report.v1",
        "session_id": session["session_id"],
        "type": session["type"],
        "mocked": False,
        "audio_live": True,
        "bridge_returncode": invocation.get("returncode"),
        "transcript_events": len(transcript),
        "cards": len(cards),
        "research_proposals": len(proposals),
        "questions": results,
        "status": "PASS" if all(
            q["question_detected"] and q["family_correct"] for q in results) else "FAIL",
    }
    (out_dir / "session-report.json").write_text(json.dumps(report, indent=1))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", nargs="?")
    parser.add_argument("--session", action="append", default=None)
    args = parser.parse_args()
    campaign.ROOT = SKILL
    spec = json.loads((SKILL / "fixtures" / "meeting_campaign.json").read_text())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_root = OUT_ROOT / stamp
    reports = []
    for session in spec["sessions"]:
        if args.session and session["session_id"] not in args.session:
            continue
        print(f"== session {session['session_id']}")
        report = run_session(session, out_root / session["session_id"])
        reports.append(report)
        for q in report.get("questions", []):
            print(f"  {q['id']}: detected={q['question_detected']} "
                  f"family_ok={q['family_correct']} onset_to_card={q['onset_to_card_s']}s "
                  f"speech_end_to_card={q['speech_end_to_card_s']}s {q['detail']}")
        print(f"  -> {report['status']}")
    overall = {
        "schema": "live_evidence.meeting_campaign_report.v1",
        "run": stamp, "sessions": reports,
        "status": "PASS" if reports and all(r["status"] == "PASS" for r in reports) else "FAIL",
    }
    (out_root / "campaign-report.json").write_text(json.dumps(overall, indent=1))
    print(f"campaign: {overall['status']} -> {out_root / 'campaign-report.json'}")
    return 0 if overall["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
