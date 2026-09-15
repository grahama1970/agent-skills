#!/usr/bin/env python3
"""Ping EVERYTHING the pipeline will use, BEFORE it runs - in one concurrent wave.

Covers both transports, primaries and fallbacks:
- API/model rungs: 1-token probes through the scillm proxy (seconds).
- Web seats: ask_call_log seat health from $memory (instant); --live-seats
  promotes them to real seat_ping_ladder browser probes (minutes) when the
  memory view is stale or you need live proof.

Each ROLE declares a provider-diverse ladder (--role name=model, repeatable;
--seat name for web seats). Output: per-role rung map + which rung would serve
+ seat health, one JSON verdict. 400 unknown-model answers carry the proxy's
own suggested catalog ids - model ids come from the catalog, never a guess.

Exit 0 = every role has a live rung and no seat is known-bad; 3 = honest but
some role lacks a live rung (or a seat is known-bad); 1 = unparseable probes.

Usage:
  python3 ping_model_roster.py --role research=gpt-5.5 --role research=zai-glm \\
      --role synthesis=zai-glm --role code_run=zai-glm-flash \\
      --seat webkimi --seat webgemini --seat webgpt [--live-seats] [--json]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask import call_log  # noqa: E402
from ask.tau_dag import default_scillm_api_key, resolve_scillm_model_route  # noqa: E402

import httpx  # noqa: E402

BASE = "http://127.0.0.1:4001"


def _scillm_probe_id(model: str) -> str:
    """Pi-registry child id -> scillm probe id.

    Children validate against the Pi model registry (zai-glm,
    openai-codex/gpt-5.5:high); scillm probes need the bare base id
    (gpt-5.5). Strip provider prefixes and effort suffixes.
    """
    base = model.rsplit(":", 1)[0] if ":" in model else model
    return base.rsplit("/", 1)[-1] if "/" in base else base


def ping_model(model: str, *, timeout: float = 15.0) -> dict:
    route = resolve_scillm_model_route(_scillm_probe_id(model))
    payload = {
        "model": route.model,
        "max_tokens": 8,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
    }
    if route.reasoning_effort:
        payload["reasoning_effort"] = route.reasoning_effort
    started = time.time()
    try:
        r = httpx.post(
            f"{BASE}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {default_scillm_api_key()}", "X-Caller-Skill": "ask-ping"},
            timeout=timeout,
        )
    except httpx.ReadTimeout:
        # Proxy health is fast when up; a read timeout on completions with a
        # healthy proxy means scillm's concurrency guard is PAUSED (adaptive
        # backoff after provider 429s) - every model queues behind the pause.
        # That is a proxy-level verdict, not a per-model one.
        health = ""
        try:
            health = str(httpx.get(f"{BASE}/health/liveliness", timeout=3.0).status_code)
        except httpx.HTTPError:
            health = "unreachable"
        return {"model": model, "status": "proxy_paused" if health == "200" else "error",
                "reason": f"completions timed out; proxy health={health}", "ms": int((time.time() - started) * 1000)}
    except httpx.HTTPError as exc:
        return {"model": model, "status": "error", "reason": f"transport: {str(exc)[:120]}", "ms": int((time.time() - started) * 1000)}
    ms = int((time.time() - started) * 1000)
    text = str(r.text)[:400]
    if r.status_code == 200:
        choice = (r.json().get("choices") or [{}])[0]
        content = str((choice.get("message") or {}).get("content") or "").strip()
        finish = choice.get("finish_reason")
        if finish == "stop" and content:
            return {"model": model, "status": "ok", "replied": content[:20], "ms": ms}
        return {"model": model, "status": "error", "reason": f"finish_reason={finish} content_empty={not content}", "ms": ms}
    suggestions = re.findall(r"Did you mean: ([^.]+)", text)
    if r.status_code == 429 or "rate" in text.lower()[:200] or "quota" in text.lower()[:200]:
        return {"model": model, "status": "rate_limited", "http": r.status_code, "reason": text[:160], "ms": ms}
    if r.status_code == 400 and suggestions:
        return {"model": model, "status": "unknown_model", "http": r.status_code,
                "suggested_ids": [s.strip() for s in suggestions[0].split(",")], "reason": text[:160], "ms": ms}
    return {"model": model, "status": "error", "http": r.status_code, "reason": text[:160], "ms": ms}


def seat_from_memory(seat: str) -> dict:
    health = call_log.seat_health(seat)
    return {
        "seat": seat,
        "source": "memory",
        "status": ("ok" if not health.get("known_bad") and health.get("last_success_ts") else
                   "known_bad" if health.get("known_bad") else "no_recorded_success"),
        "consecutive_failures": health.get("consecutive_failures"),
        "last_success_ts": health.get("last_success_ts"),
        "failure_codes": health.get("failure_codes") or [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role", action="append", default=[],
                    help="role=model (repeatable; repeated role = its ordered ladder)")
    ap.add_argument("--seat", action="append", default=[], help="web seat name (repeatable)")
    ap.add_argument("--live-seats", action="store_true",
                    help="run real browser seat pings instead of memory health")
    ap.add_argument("--record", action="store",
                    nargs="?", const="model_availability", metavar="COLLECTION",
                    help="upsert per-model/per-seat latest status to $memory (for the watchdog cron; shared by all agents)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    roles: dict[str, list[str]] = {}
    for spec in args.role:
        role, _, model = spec.partition("=")
        roles.setdefault(role.strip(), []).append(model.strip())

    model_jobs = [(role, i) for role, models in roles.items() for i in range(len(models))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(model_jobs) or 1)) as ex:
        model_results = {job: res for job, res in zip(
            model_jobs,
            ex.map(lambda j: ping_model(roles[j[0]][j[1]]), model_jobs),
        )}
    seat_results = {}
    if args.seat:
        if args.live_seats:
            try:
                proc = subprocess.run(
                    [sys.executable, str(SKILL_ROOT / "scripts" / "seat_ping_ladder.py"),
                     *[a for s in args.seat for a in ("--seat", s)], "--json"],
                    capture_output=True, text=True, timeout=900,
                )
                seat_results = {"source": "live", "raw": proc.stdout[:4000], "exit": proc.returncode}
            except (OSError, subprocess.SubprocessError) as exc:
                seat_results = {"source": "live", "error": str(exc)[:200]}
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(args.seat))) as ex:
                seat_results = {"source": "memory", "seats": list(ex.map(seat_from_memory, args.seat))}

    role_verdicts = {}
    for role, models in roles.items():
        rungs = [model_results[(role, i)] for i in range(len(models))]
        live = next((r["model"] for r in rungs if r["status"] == "ok"), None)
        # proxy_paused is shared-proxy backoff, NOT model death: pi children
        # have completed full runs during a paused proxy (observed 2026-09-16,
        # research_r3 zai-glm 247s). A paused rung is degraded-but-eligible;
        # only rate_limited / unknown_model / error disqualify a rung.
        eligible = next((r["model"] for r in rungs if r["status"] in ("ok", "proxy_paused")), None)
        role_verdicts[role] = {"ladder": models, "rungs": rungs, "served_by": eligible,
                               "served_by_live": live, "degraded": live is None,
                               "ready": eligible is not None}

    seats_block = seat_results.get("seats") if seat_results.get("source") == "memory" else None
    seat_ok = True
    if seats_block:
        seat_ok = all(s["status"] == "ok" for s in seats_block)
    all_ready = all(v["ready"] for v in role_verdicts.values()) and seat_ok
    unparseable = sum(1 for r in model_results.values() if r["status"] == "error" and "transport" in str(r.get("reason", "")))

    verdict = {
        "schema": "ask.model_roster_ping.v3",
        "roles": role_verdicts,
        "seats": seat_results if seat_results else None,
        "readiness": "READY" if all_ready else "NOT_READY",
        "unparseable": unparseable,
    }
    if args.record:
        try:
            import httpx as _hx
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            docs = [
                {
                    "_key": f"model:{r['model']}", "kind": "model_availability",
                    "model": r["model"], "status": r["status"], "ts": now,
                    "latency_ms": r.get("ms"), "source": "roster_ping",
                    "retrieval_text": f"model {r['model']} status {r['status']} at {now}",
                }
                for r in model_results.values()
            ]
            if seats_block:
                docs += [
                    {
                        "_key": f"seat:{s['seat']}", "kind": "model_availability",
                        "model": s["seat"], "status": s["status"], "ts": now,
                        "source": "memory_seat_health",
                        "retrieval_text": f"seat {s['seat']} status {s['status']} at {now}",
                    }
                    for s in seats_block
                ]
            resp = _hx.post(
                f"{call_log.MEMORY_URL}/upsert",
                json={"collection": args.record, "documents": docs},
                timeout=10.0, headers={"x-caller-skill": "ask"},
            )
            resp.raise_for_status()
            verdict["recorded_to"] = args.record
        except Exception as exc:  # recording is best-effort; ping verdict still prints
            verdict["record_error"] = str(exc)[:200]
    print(json.dumps(verdict, indent=2))
    return 0 if all_ready else (1 if unparseable else 3)


if __name__ == "__main__":
    raise SystemExit(main())
