#!/usr/bin/env python3
"""Blind synthetic-interview eval (#drivewealth prep, 2026-08-26).

Replays each scripted mock interview through a REAL live-evidence server
(fresh consented meeting session per interview, real stage-1 resolver, real
retrieval lanes). The pipeline sees only turn text; expected_stems stay in
this harness. A grader then matches every scripted question against the
canonical questions the pipeline authored onto its cards.

PASS bar per interview: >= 75% of turns MATCH (stem overlap >= 0.5) and no
more than one MISS (< 0.3). The 2026-08-26 baseline measured 30/32 MATCH.

Usage: eval_synthetic_interviews.py <skill_root> [--set <fixture>] [--gap 13]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def stems(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w[:5] for w in words if len(w) > 3}


def wait_health(base: str, deadline_s: float = 60.0) -> None:
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=5) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1.0)
    raise RuntimeError("server never became healthy")


def post(base: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", type=Path)
    parser.add_argument("--set", dest="set_path", type=Path, default=None)
    parser.add_argument("--gap", type=float, default=13.0,
                        help="seconds between turns (compressed pacing)")
    parser.add_argument("--interview", default=None,
                        help="run only this interview_id")
    args = parser.parse_args()

    set_path = args.set_path or (
        args.skill_root / "fixtures" / "mock_interviews_drivewealth.json")
    interviews = json.loads(set_path.read_text())["interviews"]
    if args.interview:
        interviews = [i for i in interviews if i["interview_id"] == args.interview]
        if not interviews:
            print(f"unknown interview {args.interview}", file=sys.stderr)
            return 2

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env.setdefault(
        "LIVE_EVIDENCE_REPOS",
        ":".join(str(Path.home() / "workspace/experiments" / r)
                 for r in ("agent-skills", "tau", "memory", "sparta", "dw-openapi")))
    server = subprocess.Popen(
        ["bash", str(args.skill_root / "run.sh"), "serve", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    overall_ok = True
    results = []
    try:
        wait_health(base)
        for iv in interviews:
            baseline_ids = {c.get("card_id")
                            for c in get(base, "/api/state").get("cards", [])}
            post(base, "/api/session/start",
                 {"purpose": "meeting", "actor_role": "candidate",
                  "consent_confirmed": True})
            for turn in iv["turns"]:
                post(base, "/api/transcript",
                     {"speaker": "interviewer", "kind": "final",
                      "text": turn["text"]})
                time.sleep(args.gap)
            time.sleep(max(args.gap, 15))
            # Grade only THIS interview's cards. Match against the card's full
            # text: a pressure-chain follow-up revises the same canonical
            # question by design (revision fencing), so its content lands in
            # the thread's question/answer/evidence rather than a new card.
            cards = [c for c in get(base, "/api/state").get("cards", [])
                     if c.get("card_id") not in baseline_ids]
            extracted = [" ".join(filter(None, (
                c.get("question"), c.get("query"), c.get("answer"),
                c.get("evidence")))) for c in cards]
            match = miss = 0
            for turn in iv["turns"]:
                # Dual stem sets (tail|head): the '?' path canonicalizes the
                # tail clause, interviewer_statement keeps the head. Either
                # matching counts.
                best = 0.0
                for part in turn["expected_stems"].split("|"):
                    goal = stems(part)
                    if not goal:
                        continue
                    score = max((len(goal & stems(q)) / len(goal)
                                 for q in extracted), default=0.0)
                    best = max(best, score)
                if best >= 0.5:
                    match += 1
                elif best < 0.3:
                    miss += 1
            ok = match >= int(0.75 * len(iv["turns"])) and miss <= 1
            overall_ok = overall_ok and ok
            row = {"interview": iv["interview_id"], "turns": len(iv["turns"]),
                   "match": match, "miss": miss, "cards": len(cards), "ok": ok}
            results.append(row)
            print(json.dumps(row), flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
    receipt = {"schema": "live_evidence.synthetic_interview_eval_receipt.v1",
               "status": "PASS" if overall_ok else "FAIL", "results": results}
    print(json.dumps(receipt))
    print(f"synthetic interviews: {'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
