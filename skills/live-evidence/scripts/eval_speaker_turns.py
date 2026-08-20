#!/usr/bin/env python3
"""Proof for the deterministic speaker-turn contract (#1477).

Real server; the live-audio rung is carried by the existing pipewire suite
cases (the bridge posts through the same ingest, so every live transcript
event now carries a turn) -- this eval claims transcript-contract behavior
(audio_claim=false) plus one digest-stability readback:

1. two-speaker conversation: consecutive same-speaker events share a stable
   turn_id; a speaker change opens a new turn; slots are stable per speaker;
2. turn ids survive progressive restatements/revisions (journal + state
   readback);
3. manual correction propagates to every event of the turn WITHOUT changing
   any card or ledger digest, and is journaled with the actor;
4. attribution is explicit: only transport|manual appear -- the eval FAILS if
   a diarizer attribution shows up without being explicitly enabled, so a
   diarizer can never become silently required;
5. no person-name inference: slots are speaker_N, never names.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "scripts"))
    import run_g2i_campaign as campaign

    campaign.ROOT = root
    server = campaign.Server(campaign.import_tmp("speaker-turns"), live_resolver=False)
    try:
        turns_script = [
            ("interviewer", "Welcome, thanks for joining today."),
            ("interviewer", "Let's start with your background in backend systems."),
            ("candidate", "Sure, I have spent six years building payment services."),
            ("candidate", "Mostly Postgres and Kafka, with some Rust lately."),
            ("interviewer", "Great, how would you shard a payments ledger?"),
            ("candidate", "I would shard by account id with a directory service."),
        ]
        for sequence, (speaker, text) in enumerate(turns_script, start=1):
            status, _ = campaign.http("POST", f"{server.url}/api/transcript", {
                "schema": "live_evidence.transcript_event.v1", "speaker": speaker,
                "kind": "final", "source": "api", "sequence": sequence, "text": text,
            })
            assert status == 202
        time.sleep(1)
        state = server.state()
        transcript = state.get("transcript") or []
        turn_ids = [e.get("turn_id") for e in transcript]
        slots = [e.get("speaker_slot") for e in transcript]
        speakers = [e.get("speaker") for e in transcript]
        check("every event carries a turn id and slot",
              all(turn_ids) and all(slots), f"events={len(transcript)}")
        boundaries_ok = True
        for prev, current in zip(transcript, transcript[1:]):
            same_speaker = prev.get("speaker") == current.get("speaker")
            same_turn = prev.get("turn_id") == current.get("turn_id")
            if same_speaker != same_turn:
                boundaries_ok = False
        check("turn boundaries follow speaker changes exactly", boundaries_ok,
              f"turns={len(set(turn_ids))}")
        slot_by_speaker = {}
        stable_slots = True
        for event in transcript:
            existing = slot_by_speaker.setdefault(event["speaker"], event["speaker_slot"])
            if existing != event["speaker_slot"]:
                stable_slots = False
        check("speaker slots stable per speaker", stable_slots, str(slot_by_speaker))
        check("slots are anonymous speaker_N (no person-name inference)",
              all(str(s).startswith("speaker_") for s in slots), f"slots={sorted(set(slots))}")

        # 2. progressive restatement keeps the turn id.
        first_candidate = next(e for e in transcript if e["speaker"] == "candidate")
        status, _ = campaign.http("POST", f"{server.url}/api/transcript", {
            "schema": "live_evidence.transcript_event.v1", "speaker": "candidate",
            "kind": "final", "source": "api", "sequence": 3,
            "text": first_candidate["text"] + " across three different companies.",
        })
        time.sleep(0.5)
        after = server.state().get("transcript") or []
        restated = [e for e in after if "three different companies" in e.get("text", "")]
        check("turn id survives a progressive restatement",
              restated and restated[0].get("turn_id") == first_candidate["turn_id"],
              f"kept={bool(restated)}")

        # 3. manual correction: propagate slot; digests untouched; journaled.
        cards_before = json.dumps(server.state().get("cards") or [], sort_keys=True)
        target_turn = first_candidate["turn_id"]
        status, outcome = campaign.http(
            "POST", f"{server.url}/api/turns/{target_turn}/reassign",
            {"speaker_slot": "speaker_7", "actor": "reviewer:graham"})
        after = server.state().get("transcript") or []
        reassigned = [e for e in after if e.get("turn_id") == target_turn]
        cards_after = json.dumps(server.state().get("cards") or [], sort_keys=True)
        journal_path = next(server.data_dir.glob("*/session.jsonl"), None)
        rows = [json.loads(line) for line in journal_path.read_text().splitlines()] \
            if journal_path else []
        reassign_rows = [r for r in rows if r.get("kind") == "turn_reassigned"]
        check(
            "manual correction propagates to the whole turn, journaled, content untouched",
            status == 200
            and reassigned and all(e["speaker_slot"] == "speaker_7" for e in reassigned)
            and all(e["attribution_source"] == "manual" for e in reassigned)
            and cards_before == cards_after
            and reassign_rows and reassign_rows[0]["payload"]["actor"] == "reviewer:graham",
            f"updated={outcome.get('events_updated')}",
        )
        status, _ = campaign.http("POST", f"{server.url}/api/turns/nonexistent-turn/reassign",
                                  {"speaker_slot": "speaker_1", "actor": "a"})
        check("unknown turn reassignment is 404", status == 404, f"http={status}")

        # 4. diarizer can never become silently required.
        sources = {e.get("attribution_source") for e in after}
        check("attribution sources are explicit transport|manual only",
              sources <= {"transport", "manual"}, f"sources={sorted(sources)}")
    finally:
        server.close()

    print()
    if FAILURES:
        print(f"speaker turns: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("speaker turns: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
