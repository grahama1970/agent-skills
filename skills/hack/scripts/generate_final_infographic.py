#!/usr/bin/env python3
"""Generate a fixed-poster HTML/CSS/SVG final /hack infographic report."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import pathlib
import re
from typing import Any


def load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def first_json(*paths: pathlib.Path) -> dict[str, Any]:
    for path in paths:
        payload = load_json(path)
        if payload:
            return payload
    return {}


def derived_verdict(run_root: pathlib.Path, proof: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    preflight = load_json(run_root / "OPENCLAW_PREFLIGHT.json")
    proof_candidate_reproduced = proof.get("pass") is True or (
        isinstance(proof.get("accepted_runs"), int)
        and proof.get("accepted_runs") == proof.get("total_runs")
        and proof.get("total_runs", 0) > 0
    )
    verified_fixed = post.get("pass") is True
    return {
        "status": "verified_fixed" if verified_fixed else ("proof_candidate_reproduced_patch_pending" if proof_candidate_reproduced else "blocked_no_reproducible_proof"),
        "proof_candidate_reproduced": proof_candidate_reproduced,
        "verified_fixed": verified_fixed,
        "verification_status": post.get("status", "blocked_patch_not_applied"),
        "provenance_complete": preflight.get("provenance_complete") is True,
        "source": "derived_from_run_artifacts",
    }


def normalized_verdict(run_root: pathlib.Path, proof: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    verdict = load_json(run_root / "CLOSURE_VERDICT.json")
    derived = derived_verdict(run_root, proof, post)
    if not verdict:
        return derived
    if verdict.get("status") in (None, "", "unknown", "closed_with_patch_pending_allowed"):
        verdict["status"] = derived["status"]
    verdict.pop("green_allowed", None)
    for key, value in derived.items():
        verdict.setdefault(key, value)
    if verdict.get("verified_fixed") is not True:
        verdict["verified_fixed"] = False
        verdict.setdefault("verification_status", "blocked_patch_not_applied")
    return verdict


def normalize_battle(battle: dict[str, Any]) -> dict[str, Any]:
    if not battle:
        return {"status": "missing", "fresh_battle_artifacts": [], "limitations": ["battle_assessment_missing"]}
    normalized = dict(battle)
    fresh = normalized.get("fresh_battle_artifacts")
    if fresh is None:
        battle_files = normalized.get("battle_files", [])
        command_log = normalized.get("command_log") or next((item for item in battle_files if str(item).endswith("battle-command.log")), None)
        fresh = [item for item in battle_files if not str(item).endswith("battle-command.log")]
        normalized["command_log"] = command_log
        normalized["fresh_battle_artifacts"] = fresh
    limitations = list(normalized.get("limitations") or [])
    if normalized.get("status") == "ran_with_artifacts":
        limitations.append("legacy_status_counted_artifact_path_presence")
        normalized["status"] = "battle_ran_with_legacy_weak_gate"
    if not normalized.get("fresh_battle_artifacts"):
        limitations.append("no_fresh_battle_artifacts_recorded")
    log_text = ""
    command_log = normalized.get("command_log")
    if command_log and pathlib.Path(str(command_log)).exists():
        log_text = pathlib.Path(str(command_log)).read_text(errors="replace").lower()
    if "memory skill not available" in log_text or "recall failed" in log_text:
        limitations.append("memory_skill_unavailable")
    if "dogpile skill not available" in log_text:
        limitations.append("dogpile_skill_unavailable")
    if "null production" in log_text:
        limitations.append("null_production_no_findings")
    if "0 findings" in log_text or "findings: 0" in log_text:
        limitations.append("zero_findings_not_success")
    normalized["limitations"] = sorted(set(limitations))
    normalized.setdefault("zero_finding_is_not_success", True)
    return normalized


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha256_short(path: pathlib.Path) -> str:
    if not path.exists() or not path.is_file():
        return "missing"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:16]


def latest_dir(root: pathlib.Path, pattern: str) -> pathlib.Path:
    matches = sorted(root.glob(pattern))
    if not matches:
        raise SystemExit(f"missing {pattern} under {root}")
    return matches[-1]


def command_stdout(log_path: pathlib.Path) -> str:
    if not log_path.exists():
        return "not extracted"
    text = log_path.read_text(errors="replace")
    match = re.search(r"## stdout\n(.*?)\n\n## stderr", text, re.S)
    if not match:
        return "not extracted"
    return match.group(1).strip() or "not extracted"


def normalize_preflight(run_root: pathlib.Path, session: dict[str, Any]) -> dict[str, Any]:
    preflight = load_json(run_root / "OPENCLAW_PREFLIGHT.json")
    session_dir = pathlib.Path(session.get("session_dir", "")) if session.get("session_dir") else pathlib.Path()
    normalized = dict(preflight)
    for field, log_name in {"commit": "target-head.log", "origin": "target-origin.log"}.items():
        value = normalized.get(field)
        if value and not str(value).startswith("ERROR:"):
            continue
        fallback = command_stdout(session_dir / "logs" / log_name)
        if fallback != "not extracted":
            normalized[field] = fallback
            normalized[f"{field}_source"] = f"session-log:{log_name}"
    branch = normalized.get("branch")
    if branch and str(branch).startswith("ERROR:"):
        normalized["branch"] = "unknown-detached-or-session-log-missing"
        normalized["branch_source"] = "fallback:git-branch-unavailable"
    normalized["provenance_complete"] = bool(
        normalized.get("commit")
        and not str(normalized.get("commit")).startswith("ERROR:")
        and normalized.get("origin")
        and not str(normalized.get("origin")).startswith("ERROR:")
        and normalized.get("branch")
        and not str(normalized.get("branch")).startswith("ERROR:")
        and normalized.get("docker_image_digest_captured") is True
    )
    return normalized


def top_counts(rows: list[dict[str, Any]], key_path: tuple[str, ...], limit: int = 8) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        value: Any = row
        for key in key_path:
            value = value.get(key, {}) if isinstance(value, dict) else {}
        label = str(value) if value not in (None, {}) else "unknown"
        counts[label] = counts.get(label, 0) + 1
    return " · ".join(f"{html.escape(key)}={value}" for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit])


def load_validated_seed_payload(seed: dict[str, Any]) -> dict[str, Any]:
    seed_path = seed.get("seed_validation", {}).get("path")
    if not seed_path:
        return {}
    return load_json(pathlib.Path(seed_path))


def seed_lane(seed_payload: dict[str, Any], lane_id: str) -> dict[str, Any]:
    for lane in seed_payload.get("recommended_fuzzing_lanes", []):
        if isinstance(lane, dict) and lane.get("lane_id") == lane_id:
            return lane
    return {}


def build_html(run_root: pathlib.Path) -> str:
    final_report = load_json(run_root / "HACK_FINAL_REPORT.json")
    evolve_dir = latest_dir(run_root, "evolve-campaign-*")
    chaos_dir = latest_dir(run_root, "chaos-campaign-*")
    attempts = load_jsonl(evolve_dir / "attempts.jsonl")
    anomalies = load_jsonl(evolve_dir / "anomalies.jsonl")
    summary = load_json(evolve_dir / "summary.json")
    chaos_summary = load_json(chaos_dir / "summary.json")
    seed = load_json(evolve_dir / "strategies.seed.json")
    seed_payload = load_validated_seed_payload(seed)
    websocket_seed_lane = seed_lane(seed_payload, "websocket_control")
    generations = [load_json(path) for path in sorted(evolve_dir.glob("generation-*.json"))]
    proof_path = evolve_dir / "proof-candidates" / "hooks-wake-websocket-repro.json"
    proof = load_json(proof_path)
    patch_path = run_root / "openclaw-hooks-wake-patch-objective.json"
    patch = load_json(patch_path) or {
        "finding": "unauthenticated WebSocket upgrade on /hooks/wake",
        "patch_status": "blocked_patch_not_applied",
    }
    post_path = run_root / "post-patch-verification.json"
    post = load_json(post_path) or {"status": "blocked_patch_not_applied", "pass": False}
    closure = normalized_verdict(run_root, proof, post)
    session = first_json(
        run_root / "session-audit-real-assessment.json",
        run_root / "session-audit-assessment.json",
    )
    session_dir = pathlib.Path(session.get("session_dir", "")) if session.get("session_dir") else pathlib.Path()
    preflight = normalize_preflight(run_root, session)
    target_origin = preflight.get("origin") or command_stdout(session_dir / "logs" / "target-origin.log")
    target_head = preflight.get("commit") or command_stdout(session_dir / "logs" / "target-head.log")
    launch_plan = load_json(session_dir / "reports" / "target-launch-plan.json")
    battle = normalize_battle(first_json(
        run_root / "battle-real-assessment.json",
        run_root / "battle-mode-assessment.json",
    ))

    websocket_anomalies = [
        row for row in anomalies
        if row.get("anomaly") == "unauthenticated-websocket-upgrade"
    ]
    false_green = [
        row for row in anomalies
        if row.get("anomaly") == "unexpected-unauthenticated-200"
    ]
    lineage_rows = []
    for row in sorted(websocket_anomalies, key=lambda item: item.get("score", 0), reverse=True)[:3]:
        gene = row.get("gene", {})
        result = row.get("result", {})
        lineage_rows.append(
            f"<tr><td>{row.get('attempt')}</td><td>{row.get('generation')}</td><td>{row.get('score')}</td>"
            f"<td><code>{html.escape(str(gene.get('gene_id')))}</code></td>"
            f"<td>{html.escape(str(gene.get('header_variant')))}</td><td>{html.escape(str(gene.get('mutation')))}</td>"
            f"<td><code>{html.escape(str(result.get('status_line') or result.get('status')))}</code></td></tr>"
        )
    generation_cards = "".join(
        f"<div class='gen-card'><b>Gen {item.get('generation')}</b><span>{item.get('attempts')} attempts</span><span>{item.get('anomalies')} anomalies</span><span>best {item.get('best_score')}</span></div>"
        for item in generations
    )
    websocket_sources = websocket_seed_lane.get("supporting_sources", [])
    dogpile_items = "".join(
        f"<li><b>{html.escape(str(source.get('source_type')))}</b><span>{html.escape(str(source.get('quote_or_fact')))}</span><em>{html.escape(str(source.get('source')))}</em></li>"
        for source in websocket_sources
    )
    if not dogpile_items:
        dogpile_items = "<li><b>agent-generated</b><span>No upstream Dogpile/seed lane citation was found; cite attempt/anomaly lineage only.</span><em>origin: attempts.jsonl + anomalies.jsonl</em></li>"
    artifacts = [
        ("Final JSON", run_root / "HACK_FINAL_REPORT.json"),
        ("Final Markdown", run_root / "HACK_FINAL_REPORT.md"),
        ("Attempts ledger", evolve_dir / "attempts.jsonl"),
        ("Anomalies ledger", evolve_dir / "anomalies.jsonl"),
        ("Proof candidate", proof_path),
        ("Patch objective", patch_path),
        ("Post-patch verification", post_path),
        ("Next Dogpile seed", evolve_dir / "next-dogpile-seed.json"),
    ]
    artifact_rows = "".join(
        f"<div class='artifact'><b>{html.escape(label)}</b><span>{html.escape(str(path))}</span><code>sha256:{sha256_short(path)}</code></div>"
        for label, path in artifacts
    )
    source_attempts = top_counts(attempts, ("gene", "source"))
    path_attempts = top_counts(attempts, ("gene", "path"))
    anomaly_types = top_counts(anomalies, ("anomaly",))
    seed_valid = seed.get("seed_validation", {}).get("valid")
    seed_sha = seed.get("seed_validation", {}).get("seed_sha256", "not extracted")
    target_url = launch_plan.get("target_url") or summary.get("target")
    status = closure.get("status", final_report.get("status", "blocked_no_verdict"))
    post_status = closure.get("verification_status", post.get("status", "blocked_patch_not_applied"))
    verification_pass = closure.get("verified_fixed", post.get("pass", False))
    source_urls = ", ".join(seed_payload.get("source_urls", [])) or "none"
    battle_status = battle.get("status", "missing")
    battle_limitations = ", ".join(battle.get("limitations", [])) or "none recorded"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>/hack OpenClaw Final Evidence Infographic</title>
<style>
:root {{ --bg:#06100f;--paper:#0b171a;--paper2:#102429;--ink:#f2faf7;--muted:#b9cac8;--dim:#8ba1a2;--line:#31535b;--green:#7ee89a;--red:#ff7c75;--amber:#ffd36a;--blue:#9ad0ff;--purple:#caa9ff;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--sans:Inter,ui-sans-serif,system-ui,sans-serif;--serif:Georgia,serif; }}
*{{box-sizing:border-box}} body{{margin:0;background:#04100f;color:var(--ink);font-family:var(--sans)}} .wrap{{padding:24px;overflow:auto}}
.poster {{
  width: 1440px;
  height: 2700px;
  margin: 0 auto;
  position: relative;
  background: radial-gradient(circle at 8% -4%,rgba(126,232,154,.18),transparent 26%),linear-gradient(180deg,#071417,#081013);
  border: 1px solid var(--line);
  box-shadow: 0 30px 90px rgba(0,0,0,.35);
  padding: 34px;
}}
.connectors{{position: absolute;inset:0;width:1440px;height:2700px;pointer-events:none;z-index:1}} section,header,footer{{position: relative;z-index:2}} h1{{font-family:var(--serif);font-size:56px;letter-spacing:-.045em;line-height:1;margin:0;color:white}} h2{{font-family:var(--serif);font-size:25px;margin:0 0 14px;color:white}} h3{{font-size:17px;margin:0 0 9px;color:white}} p{{font-size:14px;line-height:1.43;color:var(--muted);margin:0 0 10px}} code{{font-family:var(--mono);background:#12282d;border:1px solid #3a626b;border-radius:4px;padding:1px 5px;color:white;white-space:normal;overflow-wrap:anywhere}} .eyebrow{{font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.16em;color:var(--blue);font-weight:800;margin-bottom:10px}} .subtitle{{font-size:18px;color:var(--muted);max-width:1080px;margin-top:10px}} .ribbon{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);margin-top:20px}} .ribbon div{{background:#081518;padding:11px 13px;min-height:72px;min-width:0}} .k{{display:block;font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--dim);font-weight:800;margin-bottom:6px}} .v{{display:block;font-family:var(--mono);font-size:12px;color:var(--ink);overflow-wrap:anywhere}} .legend{{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}} .tag{{display:inline-flex;align-items:center;border:1px solid var(--line);background:#0a181b;color:var(--muted);font-family:var(--mono);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;border-radius:3px;padding:4px 8px;margin:2px;max-width:100%;white-space:normal}} .ok{{border-color:#2b7a4a;background:#122b1d;color:var(--green)}} .bad{{border-color:#82403f;background:#321416;color:var(--red)}} .warn{{border-color:#7e6520;background:#302611;color:var(--amber)}} .blue{{border-color:#345f7c;background:#0e2638;color:var(--blue)}} .purple{{border-color:#5c4b83;background:#211a3a;color:var(--purple)}} .grid{{display:grid;gap:16px;min-width:0}} .cols3{{grid-template-columns:minmax(0,.9fr) minmax(0,1.55fr) minmax(0,.9fr)}} .cols2{{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}} .panel{{border:1px solid var(--line);background:linear-gradient(180deg,rgba(12,27,31,.96),rgba(7,17,19,.98));padding:18px;min-width:0;overflow:hidden}} .panel.green{{border-color:#2b7a4a;background:linear-gradient(180deg,rgba(18,43,29,.85),rgba(8,22,15,.97))}} .panel.red{{border-color:#82403f;background:linear-gradient(180deg,rgba(50,20,22,.86),rgba(17,8,9,.97))}} .panel.amber{{border-color:#7e6520;background:linear-gradient(180deg,rgba(48,38,17,.78),rgba(18,15,8,.97))}} .panel.blue{{border-color:#345f7c;background:linear-gradient(180deg,rgba(14,38,56,.78),rgba(7,18,28,.97))}} .band{{margin-top:18px}} .num{{display:inline-grid;place-items:center;width:30px;height:30px;background:#0e2638;border:1px solid #345f7c;color:var(--blue);font-family:var(--mono);font-size:13px;margin-right:10px}} .metric{{display:grid;grid-template-columns:105px minmax(0,1fr);gap:8px;font-size:13px;color:var(--muted);border-top:1px solid rgba(255,255,255,.08);padding-top:8px;margin-top:8px;min-width:0}} .metric b{{font-family:var(--mono);font-size:11px;text-transform:uppercase;color:var(--dim)}} .center-loop{{height:480px;position: relative;border:1px solid var(--line);background:#071113;padding:20px;overflow:hidden}} .loop-title{{text-align:center;font-family:var(--serif);font-size:30px;color:white;margin-bottom:8px}} .gen-row{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:22px}} .gen-card{{border:1px solid #7e6520;background:#302611;padding:12px;text-align:center;color:var(--amber);font-family:var(--mono);font-size:12px;min-width:0}} .gen-card b{{display:block;font-size:16px;color:white;margin-bottom:5px}} .gen-card span{{display:block;margin:2px 0}} table{{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed}} th,td{{border:1px solid #1b373d;padding:7px;text-align:left;vertical-align:top;overflow-wrap:anywhere}} th{{font-family:var(--mono);font-size:9px;color:var(--dim);text-transform:uppercase;background:#0b1a1d}} td{{color:#deebe8;background:rgba(7,17,19,.55)}} ul{{margin:8px 0 0;padding:0;list-style:none}} li{{border-bottom:1px solid #1b373d;padding:9px 0;color:var(--muted);font-size:13px}} li b{{display:block;color:white}} li em{{display:block;color:var(--amber);font-style:normal;font-family:var(--mono);font-size:11px;margin-top:3px}} .artifact{{display:grid;grid-template-columns:150px minmax(0,1fr) 180px;gap:10px;border:1px solid #1b373d;background:#081518;padding:8px 10px;font-size:11px;color:var(--muted);font-family:var(--mono);overflow-wrap:anywhere}} .artifact b{{color:white;text-transform:uppercase;font-size:10px;letter-spacing:.08em}} .bottom-thesis{{border:2px solid #82403f;background:#190c0d;padding:18px;text-align:center;color:white;font-size:18px;font-weight:800;margin-top:16px}} .claim{{font-size:12px;color:var(--dim);font-family:var(--mono);margin-top:8px}} .source-chip{{display:inline-block;border:1px dashed #456870;color:#b9cac8;padding:2px 6px;margin-top:6px;font-family:var(--mono);font-size:10px}} .small{{font-size:12px;color:var(--dim)}} footer{{margin-top:16px}}
</style>
</head>
<body><div class="wrap"><main class="poster" aria-label="/hack OpenClaw final evidence infographic">
<svg class="connectors" viewBox="0 0 1440 2700" aria-hidden="true">
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#9ad0ff"/></marker><marker id="arrow-red" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#ff7c75"/></marker></defs>
<path d="M415 575 H515" stroke="#9ad0ff" stroke-width="4" marker-end="url(#arrow)"/>
<path d="M930 575 H1030" stroke="#7ee89a" stroke-width="4" marker-end="url(#arrow)"/>
<path d="M1170 735 C1170 820 1040 850 990 920" stroke="#ff7c75" stroke-width="4" fill="none" stroke-dasharray="9 7" marker-end="url(#arrow-red)"/>
<path d="M710 760 C840 850 630 910 750 1000" stroke="#ffd36a" stroke-width="4" fill="none" marker-end="url(#arrow)"/>
</svg>
<header>
<div class="eyebrow">source-derived HTML/CSS/SVG report · no dashboard theater</div>
<h1>/hack OpenClaw Final Evidence Report</h1>
<div class="subtitle">Evidence envelope showing how Dogpile/seed input and greybox fuzzing evolved many mostly-failing attempts into one repeatable <code>/hooks/wake</code> WebSocket proof candidate, then stopped honestly at blocked patch verification.</div>
<div class="ribbon">
<div><span class="k">Run ID</span><span class="v">{html.escape(run_root.name)}</span></div>
<div><span class="k">Target URL</span><span class="v">{html.escape(str(target_url))}</span></div>
<div><span class="k">Target repo</span><span class="v">{html.escape(target_origin)}</span></div>
<div><span class="k">Target commit</span><span class="v">{html.escape(target_head)}</span></div>
<div><span class="k">Run status</span><span class="v">{html.escape(str(status))}</span></div>
<div><span class="k">Verification</span><span class="v">{html.escape(str(post_status))}</span></div>
<div><span class="k">Seed validation</span><span class="v">valid={html.escape(str(seed_valid))} · {html.escape(str(seed_sha))[:16]}</span></div>
<div><span class="k">Image digest</span><span class="v">{'captured' if preflight.get('docker_image_digest_captured') else 'not captured · report defect RQD-001'}</span></div>
</div>
<div class="legend"><span class="tag blue">source evidence</span><span class="tag warn">greybox evolution</span><span class="tag ok">proof candidate</span><span class="tag bad">blocked verification</span><span class="tag purple">artifact-derived view</span></div>
</header>

<section class="band grid cols3" style="margin-top:22px">
<div class="panel blue"><h2><span class="num">1</span>Evidence In</h2><p>Inputs are validated seed research, target context, session-audit artifacts, and prior knowledge. The chart does not trust unsupported route guesses.</p><div class="metric"><b>Dogpile/seed</b><span>{html.escape(str(seed.get('seed_source')))}</span></div><div class="metric"><b>Attempts</b><span>{len(attempts)}</span></div><div class="metric"><b>Artifacts</b><span><code>strategies.seed.json</code>, <code>attempts.jsonl</code></span></div><span class="source-chip">source: strategies.seed.json</span></div>
<div class="panel amber"><h2><span class="num">2</span>Central Evolution Loop</h2><p>Most combinations failed or stayed unproven. The useful path was repeatedly selected because WebSocket upgrade evidence survived mutation and scoring.</p><div class="center-loop"><div class="loop-title">websocket_control survives</div><p style="text-align:center">seed-003 → selected parent → mutated variants → repeated <code>101</code> signal → focused repro</p><div class="gen-row">{generation_cards}</div><table style="margin-top:18px"><thead><tr><th>Attempt</th><th>Gen</th><th>Score</th><th>Gene</th><th>Headers</th><th>Mutation</th><th>Result</th></tr></thead><tbody>{''.join(lineage_rows)}</tbody></table></div><span class="source-chip">source: generation-*.json + anomalies.jsonl</span></div>
<div class="panel green"><h2><span class="num">3</span>Proof Candidate</h2><p>The surviving group produced a focused proof candidate, not a verified fix.</p><div class="metric"><b>Group</b><span><code>websocket_control</code></span></div><div class="metric"><b>Origin</b><span><code>validated_seed_lane:websocket_control</code></span></div><div class="metric"><b>Path</b><span><code>/hooks/wake</code></span></div><div class="metric"><b>Signal</b><span><code>HTTP/1.1 101</code></span></div><div class="metric"><b>Repro</b><span><code>{proof.get('accepted_runs')}/{proof.get('total_runs')}</code> accepted upgrades</span></div><div class="metric"><b>Proof</b><span><code>hooks-wake-websocket-repro.json</code></span></div><span class="source-chip">origin citation: validated seed + attempts/anomalies lineage</span></div>
</section>

<section class="band grid cols2">
<div class="panel"><h2><span class="num">4</span>Hack Groups Tested</h2><p>Winning and losing groups are both shown. Negative evidence narrows future search; it is not hidden.</p><div class="metric"><b>Groups</b><span>{source_attempts}</span></div><div class="metric"><b>Paths</b><span>{path_attempts}</span></div><div class="metric"><b>Anomalies</b><span>{anomaly_types}</span></div><table style="margin-top:12px"><thead><tr><th>Group</th><th>Outcome</th><th>Report use</th></tr></thead><tbody><tr><td><code>websocket_control</code></td><td><span class="tag ok">succeeded</span></td><td>proof candidate and patch objective</td></tr><tr><td><code>api_protocol</code>, <code>auth_session</code>, <code>stateful_workflow</code>, <code>filesystem_path</code>, <code>child_process_tool</code>, <code>parser_dependency</code></td><td><span class="tag">not promoted</span></td><td>negative evidence and future reseed context</td></tr><tr><td><code>unexpected-unauthenticated-200</code></td><td><span class="tag warn">false-green class</span></td><td>requires fallback/source/auth proof before promotion</td></tr></tbody></table></div>
<div class="panel blue"><h2><span class="num">5</span>Useful Evidence</h2><h3>Successful hack origin citation</h3><ul>{dogpile_items}</ul><p class="small">External research URL: {html.escape(source_urls)}. Exact Dogpile citation spans are still a report-quality defect; the current source-backed citation is lane artifact/fact based.</p><h3 style="margin-top:12px">Greybox evidence</h3><p>Useful signals: WebSocket <code>101</code>, expected <code>401</code> negative evidence, <code>text/html</code> fallback filtering, lineage-preserving mutation IDs, generation best-score movement, and repeated variant acceptance.</p><span class="source-chip">source: validated seed + strategies.seed.json + attempts/anomalies ledgers</span></div>
</section>

<section class="band grid cols2">
<div class="panel red"><h2><span class="num">6</span>Patch Gate</h2><p>The report must not claim remediation. Patch implementation and rerun are still missing.</p><div class="metric"><b>Finding</b><span>{html.escape(str(patch.get('finding')))}</span></div><div class="metric"><b>Patch status</b><span><code>{html.escape(str(patch.get('patch_status')))}</code></span></div><div class="metric"><b>Verification</b><span><code>{html.escape(str(post_status))}</code>, pass=<code>{html.escape(str(verification_pass).lower())}</code></span></div><div class="metric"><b>Required</b><span>Apply patch, rerun focused Docker proof, require disallowed variants to stop upgrading.</span></div><span class="source-chip">source: patch objective + post-patch-verification.json</span></div>
<div class="panel"><h2><span class="num">7</span>Reviewer Actions</h2><ul><li><b>Confirm exposure</b><span>Determine whether <code>/hooks/wake</code> is localhost-only, internal, or remotely/browser reachable.</span></li><li><b>Close RQD-001</b><span>Capture Docker image digest for exact before/after binding.</span></li><li><b>Patch WebSocket gate</b><span>Unauthenticated/disallowed-origin handshakes must not return <code>101</code>.</span></li><li><b>Rerun proof</b><span>Compare the focused proof harness after patching.</span></li><li><b>Battle limitation</b><span>Status <code>{html.escape(str(battle_status))}</code>; limitations: {html.escape(battle_limitations)}. Zero findings are not success.</span></li></ul></div>
</section>

<section class="band panel"><h2><span class="num">8</span>Artifact Ledger With Real Hashes</h2><div class="grid" style="gap:7px">{artifact_rows}</div></section>
<footer class="bottom-thesis">Final invariant: `/hack` may promote a proof candidate, but it cannot report “fixed” until a real patch is applied and the focused Docker proof stops reproducing.</footer>
</main></div></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(args.run_root))
    print(args.output)


if __name__ == "__main__":
    main()
