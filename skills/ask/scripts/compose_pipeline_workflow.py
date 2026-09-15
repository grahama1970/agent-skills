#!/usr/bin/env python3
"""Compose the pipeline workflowScript from a ping-verified roster.

Every workflowScript is COMPOSED, not hand-rolled: this script (1) pings the
full roster concurrently (models + fallbacks + web seats), (2) prunes each
role's ladder to live rungs, (3) emits the ready-to-submit workflowScript with
the fallback prelude and live ladders baked in. A required role with no live
rung fails closed (exit 3, roster verdict printed) unless --allow-degraded,
which marks that stage settled-blocked in the emitted script.

Usage:
  python3 compose_pipeline_workflow.py --packet <dir> --nonce <TOKEN> \
      [--question "..."] [--out FILE.js] [--allow-degraded] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ping_model_roster import ping_model  # noqa: E402
from ask import call_log  # noqa: E402

# Candidate rungs per role, provider-diverse and ORDERED BY PREFERENCE. The
# compose-time ping prunes to live rungs, so a provider coming back (Claude
# 2026-09-16) or going dark needs NO edit here - availability knowledge is
# derived per compose, never hardcoded to a moment in time.
# PI-REGISTRY child ids (the subagent tool validates against the Pi model
# registry, NOT the scillm catalog - observed 2026-09-16: scillm-valid
# claude-fable-5/gpt-5.5 were registry-unknown; zai-glm runs). ping_model_roster
# translates these to scillm ids when probing.
DEFAULT_ROLES = {
    "research": ["openai-codex/gpt-5.5:high", "zai-glm"],
    "synthesis": ["openai-codex/gpt-5.5", "zai-glm"],
    "code_run": ["openai-codex/gpt-5.5:high", "zai-glm"],
}
DEFAULT_SEATS = ["webkimi", "webgemini", "webgpt"]


def build_roster(roles: dict[str, list[str]], seats: list[str]) -> dict:
    roster = {"roles": {}, "seats": []}
    for role, ladder in roles.items():
        rungs = [ping_model(m) for m in ladder]
        # Scillm probe status MISpredicts pi-child health in both directions
        # (openai-codex OAuth children run while scillm says gpt rate-limited;
        # zai children aborted while scillm said eligible - both observed
        # 2026-09-16). For CHILD ladders only registry-unknown is disqualifying;
        # ordering is ok > proxy_paused > rate_limited, and the runtime ladder
        # settles the truth.
        rank = {"ok": 0, "proxy_paused": 1, "rate_limited": 2}
        eligible = [r["model"] for r in rungs if r["status"] in rank]
        eligible.sort(key=lambda m: rank[next(r["status"] for r in rungs if r["model"] == m)])
        roster["roles"][role] = {"ladder": ladder, "rungs": rungs,
                                 "live": eligible, "ready": bool(eligible)}
    for seat in seats:
        h = call_log.seat_health(seat)
        ok = not h.get("known_bad") and h.get("last_success_ts")
        roster["seats"].append({"seat": seat, "ok": bool(ok),
                                "consecutive_failures": h.get("consecutive_failures")})
    roster["ready"] = all(v["ready"] for v in roster["roles"].values()) and all(s["ok"] for s in roster["seats"])
    return roster


PRELUDE = """\
function rung(key, agent, model, task) {
  return runs.run(key, { agent, task, context: "fresh", ...(model ? { model } : {}) });
}
function runWithFallback(key, ladder, task) {
  const attempts = [];
  function tryRung(i) {
    if (i >= ladder.length) {
      return Promise.resolve({ key, failed: true, failure_code: "all_rungs_failed", attempts, output: "" });
    }
    const spec = ladder[i];
    return rung(`${key}_r${i + 1}`, spec.agent, spec.model, task).then(
      (r) => ({ key, served_by: spec, output: r.output, attempts }),
      (err) => { attempts.push({ rung: spec, error: String(err).slice(0, 300) }); return tryRung(i + 1); }
    );
  }
  return tryRung(0);
}"""


def emit(roster: dict, packet: str, nonce: str, question: str, allow_degraded: bool) -> str:
    def ladder_js(role: str, agent: str) -> str:
        entry = roster["roles"][role]
        live = entry["live"]
        # Insurance rungs: candidates that pinged bad at compose still ride
        # along AFTER the live rungs - catalogs rotate mid-run (observed
        # 2026-09-16: claude-fable vanished between ping and launch) and a
        # rate limit may lift. Never emit a single-rung ladder if more
        # catalog-valid candidates exist.
        insurance = [m for m in entry["ladder"] if m not in live]
        ordered = live + insurance
        if not ordered:
            return "[]  // degraded: no catalog-valid rungs; stage settles blocked"
        marker = "" if live else "  // degraded: no live rung at compose; insurance rungs only"
        return "[" + ", ".join(f'{{ agent: "{agent}", model: "{m}" }}' for m in ordered) + f"]{marker}"

    ok_seats = [s["seat"] for s in roster["seats"] if s["ok"]] or ["webkimi"]
    role_args = " ".join(a for role, models in DEFAULT_ROLES.items() for m in models for a in (f"--role {role}={m}",))
    seat_args = " ".join(f"--seat {s}" for s in ok_seats)
    return f"""// Composed by compose_pipeline_workflow.py from a ping-verified roster.
// Roster at compose time: {json.dumps({r: v['live'] for r, v in roster['roles'].items()})}, seats ok: {ok_seats}
{PRELUDE}

// STAGE 0 (mandatory): re-verify availability at execution time. A compose-time
// green light can go dark before launch; this stage fails fast (~15s) instead
// of burning minutes discovering limits mid-pipeline.
const rosterCheck = await runs.run("verify_roster", {{ context: "fresh", agent: "delegate", model: "{roster["roles"]["research"]["live"][0] if roster["roles"]["research"]["live"] else ""}",
  task: `Run EXACTLY, from /home/graham/workspace/experiments/agent-skills:
python3 skills/ask/scripts/ping_model_roster.py {role_args} {seat_args}
Your ENTIRE reply must be exactly one final line and nothing else:
ROSTER_VERDICT_GO if the command exited 0, otherwise ROSTER_VERDICT_HALT followed by the failing roles. Do not quote statuses, do not explain.`,
}});
if (rosterCheck.output.includes("ROSTER_VERDICT_HALT")) {{
  return JSON.stringify({{ status: "BLOCKED", stage: "verify_roster", roster_output: rosterCheck.output.slice(0, 3000) }});
}}

const ROOT = "{packet}";
const NONCE = "{nonce}";
const RESEARCH_LADDER = {ladder_js('research', 'worker')};
const SYNTH_LADDER = {ladder_js('synthesis', 'worker')};  // worker: the gate WRITES synthesis.md + lane-specs.json (reviewer has no write tool)

const research = await runWithFallback("research", RESEARCH_LADDER,
  `Run EXACTLY, from /home/graham/workspace/experiments/agent-skills/skills/ask:
./run.sh one-shot --out-dir ${{ROOT}} "{question} End with the exact token: ${{NONCE}}" {' '.join('--handler ' + s for s in ok_seats)} --min-answered 1
Report per-seat state, each seat run dir, and each answer file path. Do not edit repo files.`);
if (research.failed) {{
  return JSON.stringify({{ status: "BLOCKED", stage: "research", failure_code: research.failure_code, attempts: research.attempts }});
}}

const verify = await runWithFallback("verify_and_packet", SYNTH_LADDER,
  `You are the verification gate. READ ${{ROOT}}/one-shot-verdict.json FIRST - it lists each seat lane's run dir and answer path. Use THOSE paths. For each seat verify on disk: For each seat verify on disk: receipt ok=true AND response contains ${{NONCE}}. Write ${{ROOT}}/synthesis.md and ${{ROOT}}/lane-specs.json (schema per skills/ask/references/lane-handoff.md; lanes keyed cross_check and extract_quality with derived_from). A seat that fails verification is recorded, never dropped. Return packet dir + per-seat ok table.`);
if (verify.failed) {{
  return JSON.stringify({{ status: "BLOCKED", stage: "verify", failure_code: verify.failure_code, attempts: verify.attempts, research_output: research.output.slice(0, 2000) }});
}}

const lanes = await runs.all([
  {{ key: "cross_check", agent: "reviewer", task: `READ FIRST: ${{ROOT}}/lane-specs.json (your lane: cross_check) and ${{ROOT}}/synthesis.md. Use ONLY the exact file paths named there (seat response.md files under source_run). NEVER run find or grep across directories - read the named files directly. Read-only. End with: DERIVED_FROM: <your lane's derived_from>.` }},
  {{ key: "extract_quality", agent: "reviewer", task: `READ FIRST: ${{ROOT}}/lane-specs.json (your lane: extract_quality) and ${{ROOT}}/synthesis.md. Use ONLY the exact file paths named there (seat response.md files under source_run). NEVER run find or grep across directories - read the named files directly. Read-only. End with: DERIVED_FROM: <your lane's derived_from>.` }},
]);
return ["=== research ===", research.output, "=== verify ===", verify.output,
        "=== lanes ===", ...lanes.map((r) => r.output)].join("\\n");
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--nonce", required=True)
    ap.add_argument("--question", default="What single quality matters most in a code review? One sentence.")
    ap.add_argument("--out", help="write emitted workflowScript to this file")
    ap.add_argument("--allow-degraded", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    roster = build_roster(DEFAULT_ROLES, DEFAULT_SEATS)
    unready = [r for r, v in roster["roles"].items() if not v["ready"]]
    bad_seats = [s["seat"] for s in roster["seats"] if not s["ok"]]
    if (unready or bad_seats) and not args.allow_degraded:
        print(json.dumps({"schema": "ask.compose_pipeline.v1", "status": "BLOCKED",
                          "reason": "roster not ready; rerun with --allow-degraded to compose a degraded script",
                          "unready_roles": unready, "known_bad_seats": bad_seats, "roster": roster}, indent=2))
        return 3
    script = emit(roster, args.packet, args.nonce, args.question, args.allow_degraded)
    if args.out:
        Path(args.out).write_text(script, encoding="utf-8")
    if args.json:
        print(json.dumps({"schema": "ask.compose_pipeline.v1", "status": "COMPOSED",
                          "out": args.out, "degraded": bool(unready or bad_seats),
                          "roles": {r: v["live"] for r, v in roster["roles"].items()}}, indent=2))
    else:
        print(script)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
