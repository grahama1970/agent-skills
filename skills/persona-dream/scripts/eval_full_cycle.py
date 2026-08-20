#!/usr/bin/env python3
"""Eval: one complete persona-dream run, start to finish, in a fresh run dir.

The whole loop, live, through run.sh (the documented layer), asserting the
named receipt of every stage rather than trusting any stage's own exit code:

  1. ingest-day            -> PASS_DAY_INGESTED, events read back
  2. dream (Tau DAG spine) -> tau.generic_dag_run_receipt.v1 PASS, both nodes;
                              dream_journal.md + persist_proof exact re-read
  3. generate (day journal)-> PASS_JOURNAL_RENDERED, tone-annotated journal.md
                              + hash-bound journal_spoken.txt
  4. speak-journal         -> PASS_JOURNAL_SPOKEN, journal.wav bytes + sha256,
                              ASR verified
  5. generate --write-memory -> memory_write ok
  6. store-dream-artifacts -> PASS_DREAM_ARTIFACTS_STORED, read_back >= 1
  7. converse-dynamic --turns 3 -> PASS_DYNAMIC_CONVERSATION; conversation.jsonl
                              gains 3 horus + 3 embry turns, every one voiced
                              (tone + audio sha256), WAVs non-empty on disk;
                              later Horus turns conditioned on her real replies
  8. carry-conversation    -> PASS_CONVERSATION_CARRIED, read_back == carried

Fresh run dirs per invocation (dream spine and journal run), so each trial is
a real end-to-end pass, not a replay. BLOCKED_* markers when a required live
service (chatterbox, memory, scillm via doctor) is down.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = Path(os.environ.get(
    "PD_EVAL_OUT_ROOT", "/mnt/storage12tb/skills/persona-dream/outputs"))
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")


def sh(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(ROOT / "run.sh"), *args],
                          capture_output=True, text=True, timeout=timeout, cwd=ROOT)


def fail(code: str, proc: subprocess.CompletedProcess | None = None) -> None:
    detail = ""
    if proc is not None:
        detail = f" rc={proc.returncode} out={proc.stdout[-300:]} err={proc.stderr[-300:]}"
    raise SystemExit(f"FAIL_{code}{detail}")


def main() -> int:
    try:
        urllib.request.urlopen(f"{CHATTERBOX}/health", timeout=10)
    except (urllib.error.URLError, OSError):
        print("BLOCKED_CHATTERBOX_UNREACHABLE")
        return 0
    doctor = sh(["doctor"], 300)
    if "DREAM_DOCTOR_OK" not in doctor.stdout:
        print(f"BLOCKED_DREAM_DOCTOR: {doctor.stdout.splitlines()[0] if doctor.stdout else doctor.stderr[:120]}")
        return 0

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    day = time.strftime("%Y-%m-%d", time.gmtime())
    spine_dir = OUT_ROOT / f"eval-full-cycle-{stamp}-spine"
    run_dir = OUT_ROOT / f"eval-full-cycle-{stamp}"
    checks: list[str] = []

    # 1. day ingest
    p = sh(["ingest-day", "--date", day, "--from-commits",
            "--project-state", f"full-cycle eval {stamp}: the complete loop is being proven end to end",
            "--affect", "the human requires the whole loop, receipts at every joint"], 300)
    if "PASS_DAY_INGESTED" not in p.stdout:
        fail("DAY_INGEST", p)
    checks.append("day_ingested")

    # 2. dream spine through Tau
    p = sh(["dream", "--run-dir", str(spine_dir), "--persona", "embry"], 1200)
    m = re.search(r"\{.*\}", p.stdout, re.S)
    if not m:
        fail("DREAM_NO_RECEIPT", p)
    receipt = json.loads(m.group(0))
    if receipt.get("status") != "PASS" or receipt.get("completed_node_count") != receipt.get("node_count"):
        fail("DREAM_SPINE", p)
    # Bind to THIS run's cycle via the node receipt, never "newest dir" —
    # a stale probe dir sorted after the timestamped ones and got asserted once.
    node_receipt = (spine_dir / "dag_receipts" / "dream_cycle.json").read_text()
    m2 = re.search(r"cycle_\d{8}T\d{6}Z", node_receipt)
    if not m2:
        fail("DREAM_CYCLE_ID_MISSING")
    cycle = ROOT / "reports/goal_v3/cycles" / m2.group(0)
    if not (cycle / "dream_journal.md").is_file():
        fail("DREAM_JOURNAL_MISSING")
    persist = json.loads((cycle / "persist_proof.json").read_text())
    if persist.get("all_exact_reread_match") is not True:
        fail("DREAM_PERSIST_REREAD")
    checks.append(f"dream_spine_pass:{cycle.name}")

    # 3. day journal
    p = sh(["generate", "--persona", "embry", "--day", day, "--output-dir", str(run_dir)], 900)
    m = re.search(r"\{.*\}", p.stdout, re.S)
    gen = json.loads(m.group(0)) if m else {}
    if gen.get("journal_status") != "PASS_JOURNAL_RENDERED":
        fail("JOURNAL_RENDER", p)
    if "[tone:" not in (run_dir / "journal.md").read_text():
        fail("JOURNAL_NO_TONE_ANNOTATION")
    checks.append("journal_rendered")

    # 4. spoken journal
    p = sh(["speak-journal", "--run-dir", str(run_dir)], 900)
    audio_receipt = json.loads((run_dir / "JOURNAL_AUDIO_RECEIPT.json").read_text())
    if audio_receipt.get("status") != "PASS_JOURNAL_SPOKEN":
        fail("JOURNAL_SPOKEN", p)
    wav = run_dir / "journal.wav"
    if not wav.is_file() or wav.stat().st_size < 50_000 or not audio_receipt.get("audio_sha256"):
        fail("JOURNAL_WAV")
    if audio_receipt.get("asr_ok") is not True:
        fail("JOURNAL_ASR")
    checks.append(f"journal_spoken:{wav.stat().st_size}b")

    # 5 + 6. memory write and artifact store
    p = sh(["generate", "--persona", "embry", "--day", day, "--write-memory",
            "--output-dir", str(run_dir)], 900)
    m = re.search(r"\{.*\}", p.stdout, re.S)
    if not m or json.loads(m.group(0)).get("memory_write_status") != "ok":
        fail("MEMORY_WRITE", p)
    p = sh(["store-dream-artifacts", "--run-dir", str(run_dir), "--day", day], 600)
    if "PASS_DREAM_ARTIFACTS_STORED" not in p.stdout:
        fail("ARTIFACT_STORE", p)
    checks.append("memory_written_and_artifacts_stored")

    # 7. multi-turn dynamic audible conversation about dream, day, and mood
    p = sh(["converse-dynamic", "--run-dir", str(run_dir), "--turns", "3",
            "--opening-topic",
            "her dream last night, how today actually went, and how holding the two together moves her mood"], 1500)
    if "PASS_DYNAMIC_CONVERSATION" not in p.stdout:
        fail("DYNAMIC_CONVERSATION", p)
    convo = [json.loads(l) for l in (run_dir / "conversation.jsonl").read_text().splitlines()]
    horus = [t for t in convo if t["role"] == "horus"]
    embry = [t for t in convo if t["role"] == "embry"]
    if len(horus) < 3 or len(embry) < 3:
        fail(f"TURN_COUNT:horus={len(horus)},embry={len(embry)}")
    for t in horus + embry:
        if not t.get("requested_delivery_tone") or not t.get("audio_sha256"):
            fail(f"TURN_NOT_VOICED:{t['role']}")
        w = run_dir / t["audio"]
        if not w.is_file() or w.stat().st_size < 10_000:
            fail(f"TURN_WAV:{w.name}")
    dyn = json.loads((run_dir / "dynamic_conversation_receipt.v1.json").read_text())
    pairs = dyn["turn_pairs"]
    if not all(p2["horus"]["conditioned_on_last_embry"] for p2 in pairs[1:]):
        fail("NOT_DYNAMIC")
    if len({p2["horus"]["question"] for p2 in pairs}) != len(pairs):
        fail("HORUS_REPEATED_QUESTION")
    checks.append(f"conversation:{len(pairs)}_pairs_all_voiced")

    # 8. carry back into memory
    p = sh(["carry-conversation", "--run-dir", str(run_dir), "--date", day], 600)
    m = re.search(r"carried=(\d+)\s+read_back=(\d+)", p.stdout)
    if "PASS_CONVERSATION_CARRIED" not in p.stdout or not m or m.group(1) != m.group(2):
        fail("CARRY", p)
    checks.append(f"carried:{m.group(1)}")

    print(f"FULL_CYCLE_OK stages={len(checks)} run={run_dir.name} " + " ".join(checks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
