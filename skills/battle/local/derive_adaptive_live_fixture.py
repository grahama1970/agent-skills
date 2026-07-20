"""Derive a live-transport UX fixture that carries the REAL adaptive-lineage
captured stdout/stderr/packet evidence, so the spectator Agent Detail "Live"
tab streams the actual `RED_EXPLOIT_CONFIRMED` console instead of the generic
genetic-pixi proof stdout.

Inputs (both real run artifacts):
  - base:    battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json
  - capture: adaptive-lineage-capture-verify/capture/capture-events.jsonl

Output: battle-004-adaptive-live/battle.normalized_ux_fixture.json
The capture events are transformed into the shape the frame builder
(_live_event_payload -> source_event) and the Live tab
(source.output.stdout_excerpt / source.network_summary) read.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = ROOT / "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
CAPTURE = ROOT / "local/adaptive-lineage-capture-verify/capture/capture-events.jsonl"
OUT_DIR = ROOT / "spectator/public/battle-fixtures/battle-004-adaptive-live"
OUT = OUT_DIR / "battle.normalized_ux_fixture.json"

fixture = json.loads(BASE.read_text())
capture = [json.loads(line) for line in CAPTURE.read_text().splitlines() if line.strip()]

base_events = fixture["events"]
base_max = max((e.get("elapsed_seconds") or 0) for e in base_events)
base_order = max((e.get("order_index") or 0) for e in base_events)

GEN_LABEL = {0: "G0 SEED", 1: "G1 CANDIDATE", 2: "G2 DESCENDANT"}

# The Docker replay runs the exploit under container mount /workspace; the live
# transport guard forbids absolute-path markers to prevent host-path leaks.
# Normalize the container mount prefixes in the REAL captured excerpts so the
# traceback keeps its filename/line/exception (the meaningful evidence) without
# an absolute path.
_PATH_NORMALIZE = [("/workspace/", ""), ("/workspace", "sandbox"), ("/tmp/", "tmp/"), ("/home/", "home/"), ("/mnt/", "mnt/")]


def sanitize(text: str) -> str:
    for src, dst in _PATH_NORMALIZE:
        text = text.replace(src, dst)
    return text

derived = []
for i, cap in enumerate(capture):
    lane = cap["lane_id"]
    etype = cap["event_type"]
    pay = cap["payload"]
    gen = cap.get("generation", 0)
    ev = {
        "id": cap["event_id"],
        "actor_id": lane,
        "lane_id": lane,
        "team": "red",
        "actor_kind": "red_exploit",
        "event_type": etype,
        "kind": "payload",
        "generation": gen,
        "elapsed_seconds": base_max + 4.0 * (i + 1),
        "order_index": base_order + i + 1,
        "proof_mode": "receipt_backed_fixture",
        "proven": True,
        "evidence": {
            "receipt_id": cap["event_id"],
            "proof_mode": "receipt_backed_fixture",
            "artifact_ref": pay.get("before_artifact_uri") or pay.get("after_artifact_uri") or "judge/replays",
        },
    }
    if etype == "stdout_captured":
        # before_excerpt = original (vulnerable) target stdout; after = patched target
        ev["label"] = f"RED EXPLOIT STDOUT · {GEN_LABEL.get(gen, 'GEN')}"
        ev["output"] = {
            "stdout_excerpt": sanitize(pay.get("before_excerpt", "")),
            "before_stdout_excerpt": sanitize(pay.get("before_excerpt", "")),
            "after_stdout_excerpt": sanitize(pay.get("after_excerpt", "")),
        }
    elif etype == "stderr_captured":
        # after_excerpt = patched target raised (blue defence traceback)
        ev["label"] = f"BLUE PATCH STDERR · {GEN_LABEL.get(gen, 'GEN')}"
        ev["output"] = {
            "stderr_excerpt": sanitize(pay.get("after_excerpt", "") or pay.get("before_excerpt", "")),
            "before_stderr_excerpt": sanitize(pay.get("before_excerpt", "")),
            "after_stderr_excerpt": sanitize(pay.get("after_excerpt", "")),
        }
    elif etype == "packet_captured":
        ev["label"] = f"NETWORK CAPTURE · {GEN_LABEL.get(gen, 'GEN')}"
        ns = pay.get("network_summary", {"available": pay.get("available", True)})
        ev["network_summary"] = json.loads(sanitize(json.dumps(ns)))
        ev["summary"] = "in-process zip-slip exploit — no network egress under --network none"
    derived.append(ev)

fixture["events"] = base_events + derived
fixture["generated_at"] = fixture.get("generated_at", "1970-01-01T00:00:00Z")
fixture["source_proof_dir"] = "adaptive-lineage-capture-verify (real run) + genetic-pixi base shell"

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(fixture, indent=1))
print(f"wrote {OUT}")
print(f"base events {len(base_events)} + derived {len(derived)} = {len(fixture['events'])}")

# In-process validation via the real live-transport source builder.
import sys
sys.path.insert(0, str(ROOT / "src"))
from battle_skill.live_transport_server import build_live_transport_source  # noqa: E402

source = build_live_transport_source(fixture_path=OUT, battle_id="battle-004")
print(f"VALIDATED: {len(source.events)} live frames, run_id={source.run_id}")

# Prove a frame carries the real captured stdout the Live tab reads.
hits = []
for fr in source.events:
    src = (fr.get("payload") or {}).get("source_event") or {}
    out = src.get("output") or {}
    if out.get("stdout_excerpt", "").strip() or out.get("stderr_excerpt", "").strip():
        hits.append((fr["seq"], src.get("actor_id"), out.get("stdout_excerpt", "")[:30], out.get("stderr_excerpt", "")[:30]))
print(f"frames with real console excerpt: {len(hits)}")
for h in hits[:6]:
    print("  seq", h[0], "lane", h[1], "stdout=", repr(h[2]), "stderr=", repr(h[3]))
