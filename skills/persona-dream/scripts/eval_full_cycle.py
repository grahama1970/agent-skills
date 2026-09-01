#!/usr/bin/env python3
"""Eval: one complete persona-dream run, start to finish, in a fresh run dir.

The whole loop, live, through run.sh (the documented layer), asserting the
named receipt of every stage rather than trusting any stage's own exit code:

  1. ingest-day            -> PASS_DAY_INGESTED, events read back
  2. curate-transcript-context -> $mine-transcripts output filtered into bounded
                              operator-feedback context plus Memory probe
  3. dream (Tau DAG spine) -> tau.generic_dag_run_receipt.v1 PASS, both nodes;
                              dream_journal.md + persist_proof exact re-read
  4. materialize cycle    -> run dir consumes the Tau spine's watched dream,
                              dream_journal, residue, panels, observation, and
                              spoken journal text instead of re-generating a
                              generic side journal
  5. speak-journal         -> PASS_JOURNAL_SPOKEN, journal.wav bytes + sha256,
                              ASR verified
  6. journal memory        -> dream_journal.v1 persisted by the spine is present
                              and exact persistence proof was read back
  7. store-dream-artifacts -> PASS_DREAM_ARTIFACTS_STORED, read_back >= 1
  8. converse-dynamic --turns 3 -> PASS_DYNAMIC_CONVERSATION; conversation.jsonl
                              gains 3 horus + 3 embry turns, every one voiced
                              (tone + audio sha256), WAVs non-empty on disk;
                              later Horus turns conditioned on her real replies
  9. carry-conversation    -> PASS_CONVERSATION_CARRIED, read_back == carried

Fresh run dirs per invocation (dream spine and journal run), so each trial is
a real end-to-end pass, not a replay. BLOCKED_* markers when a required live
service (chatterbox, memory, scillm via doctor) is down.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
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


def _load_grounding():
    spec = importlib.util.spec_from_file_location("conversation_grounding", ROOT / "scripts" / "conversation_grounding.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load conversation_grounding")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _items_from_day_ingest_receipt(run_dir: Path, day: str) -> list[dict[str, object]]:
    receipt = run_dir / f"DAY_INGEST_{day}.json"
    if not receipt.is_file():
        return []
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    items: list[dict[str, object]] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict) or not str(event.get("text") or "").strip():
            continue
        items.append({
            "source_id": event.get("document_key"),
            "scope": payload.get("scope"),
            "text": event.get("text"),
            "type": f"Day event ({event.get('kind') or 'unknown'})",
            "day": day,
            "source": "current_day_ingest_receipt",
        })
    return items


def _fetch_day_context(persona: str, day: str, run_dir: Path) -> dict[str, object]:
    current_items = _items_from_day_ingest_receipt(run_dir, day)
    spec = importlib.util.spec_from_file_location("persona_dream", ROOT / "scripts" / "persona_dream.py")
    if spec is None or spec.loader is None:
        return {"status": "error", "error": "cannot_load_persona_dream", "items": current_items}
    module = importlib.util.module_from_spec(spec)
    sys.modules["persona_dream"] = module
    spec.loader.exec_module(module)
    try:
        fetched, receipt = module._fetch_day_memories(module.Persona(persona), day, 4)
    except Exception as exc:
        return {"status": "error", "error": str(exc), "items": current_items}
    seen = {str(i.get("source_id")) for i in current_items if isinstance(i, dict)}
    items = current_items + [item for item in fetched if str(item.get("source_id")) not in seen]
    return {"status": "ok", "day": day, "persona": persona, "items": items, "current_ingest_count": len(current_items), "receipt": receipt}


def materialize_cycle_context(cycle: Path, run_dir: Path, *, day: str | None = None, persona: str = "embry") -> dict[str, object]:
    """Copy the cognition spine outputs into the conversation run dir.

    The old full-cycle eval ran the rich Tau spine, proved its journal existed,
    then threw that context away and called the simpler generate lane. That made
    the live conversation audible but generic. This read-back/copy step makes
    the downstream speech and chat surfaces consume the exact dream Embry watched
    and journaled.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    copies = [
        ("dream_journal.v1.json", "dream_journal.v1.json"),
        ("dream_journal.md", "dream_journal.md"),
        ("dream_journal.md", "journal.md"),
        ("journal_spoken.txt", "journal_spoken.txt"),
        ("residue_links.json", "residue_links.json"),
        ("storyboard_plan.json", "storyboard_plan.json"),
        ("observation_packet.json", "observation_packet.json"),
        ("phase14_tom.json", "phase14_tom.json"),
        ("storyboard_contact_sheet.png", "storyboard_contact_sheet.png"),
        ("storyboard_contact_sheet.png", "contact_sheet.png"),
    ]
    copied: list[str] = []
    missing: list[str] = []
    for source_name, dest_name in copies:
        source = cycle / source_name
        if not source.is_file():
            missing.append(source_name)
            continue
        shutil.copyfile(source, run_dir / dest_name)
        copied.append(dest_name)
    entry = json.loads((run_dir / "dream_journal.v1.json").read_text(encoding="utf-8"))
    sources = [str(s) for s in entry.get("source_memory_ids") or []]
    day_context = _fetch_day_context(persona, day, run_dir) if day else {"status": "skipped", "items": []}
    (run_dir / "day_context.json").write_text(json.dumps(day_context, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    context_receipt = {
        "schema": "persona_dream.full_cycle_context_materialization.v1",
        "status": "PASS_CYCLE_CONTEXT_MATERIALIZED" if not missing else "BLOCKED_CYCLE_CONTEXT_MISSING",
        "cycle": str(cycle),
        "run_dir": str(run_dir),
        "copied": copied,
        "missing": missing,
        "source_memory_count": len(sources),
        "day_context_status": day_context.get("status"),
        "day_context_count": len(day_context.get("items") or []),
        "has_dream_journal": bool(str(entry.get("journal") or "").strip()),
        "has_session_mood": isinstance(entry.get("session_mood"), dict) and bool((entry.get("session_mood") or {}).get("mood_label")),
    }
    (run_dir / "FULL_CYCLE_CONTEXT_RECEIPT.json").write_text(json.dumps(context_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return context_receipt


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
    stage_receipts: dict[str, dict[str, object]] = {}

    # 1. day ingest
    p = sh(["ingest-day", "--date", day, "--from-commits",
            "--project-state", f"full-cycle eval {stamp}: the complete loop is being proven end to end",
            "--affect", "the human requires the whole loop, receipts at every joint",
            "--event", "the eval records a third bounded event so the day-ingest gate is self-contained even before today's first commit",
            "--event", "the conversation must discuss the specific dream, the watched dream images, the written journal, and today's memory residue rather than generic uncertainty",
            "--out", str(run_dir / f"DAY_INGEST_{day}.json"), "--json"], 300)
    if "PASS_DAY_INGESTED" not in p.stdout:
        fail("DAY_INGEST", p)
    checks.append("day_ingested")
    stage_receipts["day_ingested"] = {"status": "PASS_DAY_INGESTED"}

    p = sh(["curate-transcript-context", "--run-mine", "--sample", "120",
            "--output", str(run_dir / "transcript_context.json"), "--json"], 700)
    if "PASS_TRANSCRIPT_CONTEXT_CURATED" not in p.stdout:
        fail("TRANSCRIPT_CONTEXT", p)
    transcript_context = json.loads((run_dir / "transcript_context.json").read_text(encoding="utf-8"))
    if not transcript_context.get("items"):
        fail("TRANSCRIPT_CONTEXT_EMPTY")
    checks.append(f"transcript_context_curated:{len(transcript_context['items'])}")
    stage_receipts["transcript_context_curated"] = {
        "status": transcript_context.get("status"),
        "items": len(transcript_context.get("items") or []),
        "memory_found": (transcript_context.get("memory_probe") or {}).get("found"),
    }

    # 2. dream spine through Tau
    p = sh(["dream", "--run-dir", str(spine_dir), "--persona", "embry",
            "--idea", "today's persona-dream loop, watched dream images, journal, and specific memory residue"], 1800)
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
    stage_receipts["dream_spine"] = {
        "status": "PASS",
        "cycle": cycle.name,
        "receipt": str(spine_dir / "dag_run" / "run-receipt.json"),
    }

    # 3. materialize the watched dream + journal into the conversation run dir
    materialized = materialize_cycle_context(cycle, run_dir, day=day, persona="embry")
    if materialized.get("status") != "PASS_CYCLE_CONTEXT_MATERIALIZED":
        fail(f"CYCLE_CONTEXT:{materialized.get('missing')}")
    if not (run_dir / "dream_journal.v1.json").is_file() or not (run_dir / "storyboard_plan.json").is_file():
        fail("CYCLE_CONTEXT_NOT_READABLE")
    if materialized.get("day_context_count") == 0:
        fail("DAY_CONTEXT_NOT_READABLE")
    checks.append("cycle_context_materialized")
    stage_receipts["cycle_context_materialized"] = materialized

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
    stage_receipts["journal_spoken"] = {
        "status": audio_receipt.get("status"),
        "audio": str(wav),
        "audio_sha256": audio_receipt.get("audio_sha256"),
        "asr_ok": audio_receipt.get("asr_ok"),
    }

    # 5 + 6. the spine wrote the dream journal to memory; now store its media artifacts
    journal_entry = json.loads((run_dir / "dream_journal.v1.json").read_text(encoding="utf-8"))
    if not str(journal_entry.get("journal") or "").strip() or not journal_entry.get("source_memory_ids"):
        fail("JOURNAL_MEMORY_LINEAGE")
    p = sh(["store-dream-artifacts", "--run-dir", str(run_dir), "--day", day], 600)
    if "PASS_DREAM_ARTIFACTS_STORED" not in p.stdout:
        fail("ARTIFACT_STORE", p)
    checks.append("memory_written_and_artifacts_stored")
    stage_receipts["memory_written_and_artifacts_stored"] = {"status": "PASS_DREAM_ARTIFACTS_STORED"}

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
    grounding = _load_grounding()
    grounding_context = grounding.load_context(run_dir)
    anchored_turns = [t for t in horus + embry if grounding.has_anchor(t.get("text") or "", grounding_context)]
    if len(anchored_turns) < len(horus) + len(embry):
        missing = [t.get("text") for t in horus + embry if not grounding.has_anchor(t.get("text") or "", grounding_context)]
        fail(f"CONVERSATION_NOT_GROUNDED:{missing[:2]}")
    day_anchored_turns = [t for t in horus + embry if grounding.has_day_anchor(t.get("text") or "", grounding_context)]
    if not day_anchored_turns:
        fail("CONVERSATION_NO_DAY_EVENT_ANCHOR")
    checks.append(f"conversation:{len(pairs)}_pairs_all_voiced_grounded")
    stage_receipts["conversation"] = {
        "status": "PASS_DYNAMIC_CONVERSATION",
        "pairs": len(pairs),
        "anchored_turns": len(anchored_turns),
        "day_anchored_turns": len(day_anchored_turns),
        "anchor_terms": grounding_context.get("anchor_terms") or [],
        "day_anchor_terms": grounding_context.get("day_anchor_terms") or [],
        "receipt": str(run_dir / "dynamic_conversation_receipt.v1.json"),
    }

    # 8. carry back into memory
    p = sh(["carry-conversation", "--run-dir", str(run_dir), "--date", day], 600)
    m = re.search(r"carried=(\d+)\s+read_back=(\d+)", p.stdout)
    if "PASS_CONVERSATION_CARRIED" not in p.stdout or not m or m.group(1) != m.group(2):
        fail("CARRY", p)
    checks.append(f"carried:{m.group(1)}")
    stage_receipts["carried"] = {"status": "PASS_CONVERSATION_CARRIED", "carried": int(m.group(1))}

    receipt_path = Path(os.environ.get("PD_FULL_CYCLE_EVAL_RECEIPT", "/tmp/persona-dream-full-cycle-eval-receipt.json"))
    receipt_path.write_text(json.dumps({
        "schema": "persona_dream.full_cycle_eval_receipt.v1",
        "status": "FULL_CYCLE_OK",
        "mocked": False,
        "live": True,
        "run_dir": str(run_dir),
        "spine_dir": str(spine_dir),
        "stage_count": len(checks),
        "checks": checks,
        "stages": stage_receipts,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"FULL_CYCLE_OK stages={len(checks)} run={run_dir.name} " + " ".join(checks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
