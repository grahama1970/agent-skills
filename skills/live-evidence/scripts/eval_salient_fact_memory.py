#!/usr/bin/env python3
"""Agentic eval: a salient fact is durable, and proven so from another process.

The nonce is generated at run time, so no fixture, cached response, or string
compiled into the code can satisfy this check. The write path never reads the
writer's response body; confirmation comes only from reading the document back.

The decisive assertion runs in a SEPARATE process that receives only the memory
URL, the collection name, and the nonce. It shares no objects, no client, and
no in-memory state with the writer, so a write that never landed cannot pass.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from live_evidence.models import Speaker, TranscriptEvent, TranscriptKind  # noqa: E402
from live_evidence.salient_facts import (  # noqa: E402
    SalientFactWriter,
    compute_fact_id,
    extract_decision,
)

MEMORY_URL = "http://127.0.0.1:8601"
failures: list[str] = []

READER = """
import json, sys, urllib.request
url, collection, nonce, fact_id = sys.argv[1:5]
req = urllib.request.Request(
    url + "/recall/by-keys",
    data=json.dumps({"collection": collection, "keys": [fact_id]}).encode(),
    headers={"Content-Type": "application/json", "X-Caller-Skill": "live-evidence-acceptance"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=15) as r:
    body = json.load(r)
docs = body.get("documents") or body.get("results") or []
hit = [d for d in docs if isinstance(d, dict) and d.get("_key") == fact_id]
print(json.dumps({
    "count": len(hit),
    "nonce_present": bool(hit) and nonce in json.dumps(hit[0]),
    "fact_type": hit[0].get("fact_type") if hit else None,
    "source_sha256": hit[0].get("source_sha256") if hit else None,
}))
"""


def check(name: str, passed: bool, detail: str) -> None:
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({detail})")
    if not passed:
        failures.append(name)


def read_from_fresh_process(collection: str, nonce: str, fact_id: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", READER, MEMORY_URL, collection, nonce, fact_id],
        capture_output=True, text=True, check=False, timeout=60,
    )
    if result.returncode != 0:
        return {"count": 0, "error": result.stderr.strip()[:200]}
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"count": 0, "error": "unparseable reader output"}


async def main() -> int:
    nonce = uuid.uuid4().hex[:12]
    control_nonce = uuid.uuid4().hex[:12]
    collection = f"live_evidence_facts_accept_{nonce}"
    session_id = uuid.uuid4().hex
    writer = SalientFactWriter(MEMORY_URL, collection=collection)

    print(f"nonce={nonce} control={control_nonce} collection={collection}\n")

    # Empty store: the reader must find nothing before anything is written.
    pre = read_from_fresh_process(collection, nonce, "0" * 64)
    check("negative control: empty store returns nothing", pre.get("count") == 0,
          f"count={pre.get('count')}")

    decision = TranscriptEvent(
        speaker=Speaker.INTERVIEWER, kind=TranscriptKind.FINAL, source="api", sequence=1,
        text=f"We decided that project {nonce} launches on Thursday at 09:00 with the new pipeline.",
    )
    fact = extract_decision(decision, session_id)
    check("decision extracted from final turn", fact is not None,
          f"fact_type={getattr(fact, 'fact_type', None)}")
    if fact is None:
        return 1

    confirmed, detail = await writer.write_and_confirm(fact)
    check("write confirmed by readback, not by response body", confirmed, detail)

    fresh = read_from_fresh_process(collection, nonce, fact.fact_id)
    check("fresh process finds exactly one record", fresh.get("count") == 1,
          f"count={fresh.get('count')} err={fresh.get('error')}")
    check("record carries the runtime nonce", bool(fresh.get("nonce_present")),
          "nonce cannot be a compiled-in string")
    check("fact_type is decision", fresh.get("fact_type") == "decision",
          f"{fresh.get('fact_type')}")

    recomputed = compute_fact_id(session_id, "decision", fact.source_event_ids)
    check("fact_id independently recomputed matches", recomputed == fact.fact_id,
          "deterministic identity")
    check("source digest survives the round trip",
          fresh.get("source_sha256") == fact.source_sha256, "digest matches")

    # Idempotency: replaying the same source events must not duplicate.
    await writer.write_and_confirm(fact)
    again = read_from_fresh_process(collection, nonce, fact.fact_id)
    check("replay does not duplicate", again.get("count") == 1, f"count={again.get('count')}")

    # Negative controls on extraction.
    for label, text in (
        ("question is not a decision", f"Did we decide that project {control_nonce} ships Thursday?"),
        ("hedged statement is not a decision", f"We might have decided project {control_nonce} ships Thursday."),
        ("plain statement is not a decision", f"Project {control_nonce} has a pipeline and a schedule attached."),
    ):
        event = TranscriptEvent(speaker=Speaker.INTERVIEWER, kind=TranscriptKind.FINAL,
                                source="api", sequence=2, text=text)
        check(f"negative control: {label}", extract_decision(event, session_id) is None, "rejected")

    interim = TranscriptEvent(speaker=Speaker.INTERVIEWER, kind=TranscriptKind.STABILIZED,
                              source="api", sequence=3,
                              text=f"We decided that project {control_nonce} launches Thursday at 09:00 sharp.")
    check("negative control: non-final turn is not written",
          extract_decision(interim, session_id) is None, "interim text still changing")

    print()
    if failures:
        print(f"salient fact memory: FAIL ({len(failures)} failed: {', '.join(failures)})")
        return 1
    print("salient fact memory: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
