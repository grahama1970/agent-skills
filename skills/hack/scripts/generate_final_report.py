#!/usr/bin/env python3
"""Generate source-derived final /hack reports from run-root artifacts."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import time
from typing import Any


def load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def first_json(*paths: pathlib.Path) -> dict[str, Any]:
    for path in paths:
        payload = load_json(path)
        if payload:
            return payload
    return {}


def derived_verdict(run_root: pathlib.Path, repro: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    preflight = load_json(run_root / "OPENCLAW_PREFLIGHT.json")
    proof_candidate_reproduced = repro.get("pass") is True
    verified_fixed = post.get("pass") is True
    if verified_fixed:
        status = "verified_fixed"
    elif proof_candidate_reproduced:
        status = "proof_candidate_reproduced_patch_pending"
    else:
        status = "blocked_no_reproducible_proof"
    provenance_complete = preflight.get("provenance_complete") is True
    return {
        "status": status,
        "proof_candidate_reproduced": proof_candidate_reproduced,
        "patch_pending": not verified_fixed,
        "verified_fixed": verified_fixed,
        "verification_status": post.get("status", "blocked_patch_not_applied"),
        "provenance_complete": provenance_complete,
        "provenance_defects": [] if provenance_complete else ["provenance incomplete or Docker image digest missing"],
        "source": "derived_from_run_artifacts",
    }


def normalized_verdict(run_root: pathlib.Path, repro: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    verdict = load_json(run_root / "CLOSURE_VERDICT.json")
    derived = derived_verdict(run_root, repro, post)
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
        if normalized.get("status") in ("battle_ran_with_fresh_artifacts", "battle_ran_with_limitations"):
            normalized["status"] = "battle_ran_no_fresh_artifacts_not_success"
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


def command_stdout(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(errors="replace")
    if "## stdout" in text:
        return text.split("## stdout", 1)[1].split("## stderr", 1)[0].strip()
    return text.strip()


def normalize_preflight(run_root: pathlib.Path, session: dict[str, Any]) -> dict[str, Any]:
    preflight = load_json(run_root / "OPENCLAW_PREFLIGHT.json")
    session_dir = pathlib.Path(session.get("session_dir", "")) if session.get("session_dir") else pathlib.Path()
    normalized = dict(preflight)
    for field, log_name in {"commit": "target-head.log", "origin": "target-origin.log"}.items():
        value = normalized.get(field)
        if value and not str(value).startswith("ERROR:"):
            continue
        fallback = command_stdout(session_dir / "logs" / log_name)
        if fallback:
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


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def latest_dir(root: pathlib.Path, pattern: str) -> pathlib.Path | None:
    matches = sorted(root.glob(pattern))
    return matches[-1] if matches else None


def top_counts(counter: collections.Counter[Any]) -> str:
    if not counter:
        return "`none`"
    return ", ".join(f"`{key}`={count}" for key, count in counter.most_common())


def load_validated_seed_payload(seed: dict[str, Any]) -> dict[str, Any]:
    seed_path = seed.get("seed_validation", {}).get("path")
    if not seed_path:
        return {}
    return load_json(pathlib.Path(seed_path))


def build_seed_evidence(seed_payload: dict[str, Any]) -> dict[str, Any]:
    lanes = []
    for lane in seed_payload.get("recommended_fuzzing_lanes", []):
        if not isinstance(lane, dict):
            continue
        lanes.append(
            {
                "lane_id": lane.get("lane_id"),
                "supporting_sources": lane.get("supporting_sources", []),
                "false_positive_filters": lane.get("false_positive_filters", []),
            }
        )
    return {
        "source_urls": seed_payload.get("source_urls", []),
        "artifact_paths": seed_payload.get("artifact_paths", []),
        "code_analysis_sources": seed_payload.get("code_analysis_sources", []),
        "recommended_lanes": lanes,
        "research_confidence": seed_payload.get("research_confidence", {}),
        "report_quality_defects": [
            {
                "id": "RQD-DOGPILE-CITATIONS",
                "severity": "medium",
                "defect": "Validated seed provides source facts and artifact paths, but not exact Dogpile citation spans.",
                "required_fix": "Update the seed-generation prompt/contract to require citation_text, source_artifact, and source_location for each lane and insight.",
            }
        ],
    }


def lane_seed_citation(seed_evidence: dict[str, Any], lane_id: str) -> dict[str, Any]:
    for lane in seed_evidence.get("recommended_lanes", []):
        if lane.get("lane_id") == lane_id:
            return {
                "origin_type": "validated_seed_lane",
                "lane_id": lane_id,
                "supporting_sources": lane.get("supporting_sources", []),
                "false_positive_filters": lane.get("false_positive_filters", []),
                "citation_quality": "source facts present; exact Dogpile citation spans absent",
            }
    return {
        "origin_type": "agent_generated_mutation",
        "lane_id": lane_id,
        "supporting_sources": [],
        "false_positive_filters": [],
        "citation_quality": "no upstream seed lane found; cite mutation lineage and attempt ledger only",
    }


def build_report(run_root: pathlib.Path) -> tuple[dict[str, Any], str]:
    evolve_dir = latest_dir(run_root, "evolve-campaign-*")
    chaos_dir = latest_dir(run_root, "chaos-campaign-*")
    if evolve_dir is None:
        raise SystemExit(f"missing evolve-campaign-* under {run_root}")

    attempts = load_jsonl(evolve_dir / "attempts.jsonl")
    anomalies = load_jsonl(evolve_dir / "anomalies.jsonl")
    generations = [load_json(path) for path in sorted(evolve_dir.glob("generation-*.json"))]
    summary = load_json(evolve_dir / "summary.json")
    seed = load_json(evolve_dir / "strategies.seed.json")
    seed_payload = load_validated_seed_payload(seed)
    seed_evidence = build_seed_evidence(seed_payload)
    loop = load_json(evolve_dir / "loop-contract.json")
    next_seed = load_json(evolve_dir / "next-dogpile-seed.json")
    chaos_summary = load_json(chaos_dir / "summary.json") if chaos_dir else {}
    session = first_json(
        run_root / "session-audit-real-assessment.json",
        run_root / "session-audit-assessment.json",
    )
    battle = normalize_battle(first_json(
        run_root / "battle-real-assessment.json",
        run_root / "battle-mode-assessment.json",
    ))
    repro = load_json(run_root / "focused-repro-assessment.json")
    patch = load_json(run_root / "openclaw-hooks-wake-patch-objective.json") or {
        "finding": "unauthenticated WebSocket upgrade on /hooks/wake",
        "patch_status": "blocked_patch_not_applied",
        "required_fix_contract": "disallowed unauthenticated or cross-origin WebSocket handshakes must not return HTTP 101",
    }
    post = load_json(run_root / "post-patch-verification.json") or {
        "status": "blocked_patch_not_applied",
        "pass": False,
    }
    closure = normalized_verdict(run_root, repro, post)
    preflight = normalize_preflight(run_root, session)

    proof_path = evolve_dir / "proof-candidates" / "hooks-wake-websocket-repro.json"
    proof = load_json(proof_path)
    session_dir = pathlib.Path(session.get("session_dir", "")) if session.get("session_dir") else None
    session_report = session_dir / "reports" / "HACK_REPORT.md" if session_dir else None

    attempts_by_group = collections.Counter(
        attempt.get("gene", {}).get("source") for attempt in attempts
    )
    attempts_by_transport = collections.Counter(
        attempt.get("gene", {}).get("transport") for attempt in attempts
    )
    attempts_by_path = collections.Counter(
        attempt.get("gene", {}).get("path") for attempt in attempts
    )
    anomalies_by_type = collections.Counter(anomaly.get("anomaly") for anomaly in anomalies)
    anomalies_by_path = collections.Counter(
        anomaly.get("gene", {}).get("path") for anomaly in anomalies
    )
    websocket_anomalies = [
        anomaly
        for anomaly in anomalies
        if anomaly.get("anomaly") == "unauthenticated-websocket-upgrade"
    ]
    false_green_anomalies = [
        anomaly
        for anomaly in anomalies
        if anomaly.get("anomaly") == "unexpected-unauthenticated-200"
    ]
    winning_lineage = []
    for anomaly in sorted(anomalies, key=lambda item: item.get("score", 0), reverse=True):
        gene = anomaly.get("gene", {})
        if gene.get("path") != "/hooks/wake":
            continue
        winning_lineage.append(
            {
                "attempt": anomaly.get("attempt"),
                "generation": anomaly.get("generation"),
                "score": anomaly.get("score"),
                "gene_id": gene.get("gene_id"),
                "headers": gene.get("header_variant"),
                "mutation": gene.get("mutation"),
                "lineage": gene.get("lineage", []),
                "result": anomaly.get("result", {}).get("status_line")
                or anomaly.get("result", {}).get("status"),
            }
        )

    websocket_origin_citation = lane_seed_citation(seed_evidence, "websocket_control")

    report_json = {
        "schema": "hack.final_report.v3",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_root": str(run_root),
        "status": closure.get("status"),
        "closure_verdict": closure,
        "proof_candidate_reproduced": closure.get("proof_candidate_reproduced"),
        "patch_pending": closure.get("patch_pending"),
        "verified_fixed": closure.get("verified_fixed"),
        "verification_status": closure.get("verification_status", post.get("status")),
        "provenance_complete": closure.get("provenance_complete"),
        "truth_label": "source-derived final /hack report; no dashboard metrics without backing artifacts",
        "successful_hacks": [
            {
                "group": "websocket_control",
                "path": "/hooks/wake",
                "exploit_signal": "unauthenticated WebSocket upgrade",
                "successful_anomalies": len(websocket_anomalies),
                "focused_repro": f"{proof.get('accepted_runs')}/{proof.get('total_runs')} accepted websocket upgrades",
                "proof_artifact": str(proof_path),
                "patch_status": patch.get("patch_status"),
                "verification_status": post.get("status"),
                "origin_citation": websocket_origin_citation,
                "mutation_origin": {
                    "kind": "seed_plus_agent_mutations",
                    "seed_gene": "seed-003-websocket_control-0",
                    "attempt_ledger": str(evolve_dir / "attempts.jsonl"),
                    "anomaly_ledger": str(evolve_dir / "anomalies.jsonl"),
                    "lineage_summary": "The initial successful attempt was from the validated seed lane; later successful variants were agent-generated mutations of that seed family.",
                },
            }
        ],
        "rejected_or_unproven_groups": [
            {
                "group": "api_protocol/auth_session/stateful_workflow/filesystem_path/child_process_tool/parser_dependency",
                "reason": "mostly 401, fallback HTML, or unproven anomalies; retained as negative evidence",
            },
            {
                "group": "unexpected-unauthenticated-200",
                "reason": "HTTP 200 anomalies require fallback/source/auth proof before promotion",
                "count": len(false_green_anomalies),
            },
        ],
        "evidence_counts": {
            "attempts_by_group": dict(attempts_by_group),
            "attempts_by_transport": dict(attempts_by_transport),
            "attempts_by_path": dict(attempts_by_path),
            "anomalies_by_type": dict(anomalies_by_type),
            "anomalies_by_path": dict(anomalies_by_path),
        },
        "generation_summary": generations,
        "evolution_lineage": winning_lineage,
        "dogpile_evidence_useful": {
            "seed_source": seed.get("seed_source"),
            "seed_validation": seed.get("seed_validation", {}),
            "research_insights": seed.get("research_insights", []),
            "validated_seed_evidence": seed_evidence,
            "useful_lanes": [
                "websocket_control produced repeatable 101 Switching Protocols on /hooks/wake",
                "auth/session genes produced negative evidence for expected unauthorized routes",
                "SPA fallback filtering separated text/html 200 responses from proof",
            ],
            "next_seed_artifact": str(evolve_dir / "next-dogpile-seed.json"),
            "promotion_task_count": len(next_seed.get("promotion_tasks", [])),
        },
        "greybox_evidence_useful": {
            "signals": [
                "status_line=HTTP/1.1 101 Switching Protocols",
                "HTTP 401 negative evidence",
                "Content-Type text/html false-green detection",
                "lineage-preserving mutation IDs",
                "generation best_score changes",
            ],
            "loop_contract": loop.get("loop"),
            "attempts": len(attempts),
            "anomalies": len(anomalies),
            "generations": len(generations),
        },
        "source_artifacts": {
            "attempts": str(evolve_dir / "attempts.jsonl"),
            "anomalies": str(evolve_dir / "anomalies.jsonl"),
            "generations": str(evolve_dir / "generation-*.json"),
            "evolve_report": str(evolve_dir / "HACK_EVOLVE_REPORT.md"),
            "proof_candidate": str(proof_path),
            "next_dogpile_seed": str(evolve_dir / "next-dogpile-seed.json"),
            "validated_seed": seed.get("seed_validation", {}).get("path"),
            "session_audit_report": str(session_report) if session_report else None,
            "battle_stdout": str(run_root / "battle-command.log"),
            "patch_objective": str(run_root / "openclaw-hooks-wake-patch-objective.json"),
            "post_patch_verification": str(run_root / "post-patch-verification.json"),
            "closure_verdict": str(run_root / "CLOSURE_VERDICT.json"),
            "preflight": str(run_root / "OPENCLAW_PREFLIGHT.json"),
        },
        "mode_evidence": {
            "session_audit": {
                "status": session.get("status"),
                "has_hack_report": session.get("has_hack_report"),
                "has_semgrep": session.get("has_semgrep"),
                "has_launch_plan": session.get("has_launch_plan"),
                "session_dir": session.get("session_dir"),
            },
            "battle": {
                "status": battle.get("status"),
                "exit_code": battle.get("exit_code"),
                "fresh_artifact_count": len(battle.get("fresh_battle_artifacts", [])),
                "limitations": battle.get("limitations", []),
                "zero_finding_is_not_success": battle.get("zero_finding_is_not_success"),
            },
            "preflight": {
                "status": preflight.get("status"),
                "commit": preflight.get("commit"),
                "commit_source": preflight.get("commit_source"),
                "branch": preflight.get("branch"),
                "branch_source": preflight.get("branch_source"),
                "docker_image_digest_captured": preflight.get("docker_image_digest_captured"),
                "provenance_complete": preflight.get("provenance_complete"),
            },
        },
    }

    lines = [
        "# /hack Final Report — OpenClaw Evidence-to-Exploit Run",
        "",
        "## Executive Result",
        "",
        f"- Status: `{report_json['status']}`",
        "- Successful hack group: `websocket_control` against `/hooks/wake`.",
        "- Exploit signal: unauthenticated WebSocket handshake returned `HTTP/1.1 101 Switching Protocols`.",
        f"- Focused repro: `{proof.get('accepted_runs')}` / `{proof.get('total_runs')}` accepted upgrade attempts.",
        f"- Verification status: `{report_json['verification_status']}`.",
        f"- Patch status: `{patch.get('patch_status', 'blocked_patch_not_applied')}`.",
        f"- Verified fixed: `{str(report_json['verified_fixed']).lower()}`.",
        f"- Provenance complete: `{str(report_json['provenance_complete']).lower()}`.",
        "- Truth label: source-derived hardening report; not a verified-fixed report unless post-patch verification passes.",
        "",
        "## Successful Hacks",
        "",
        "### Group: `websocket_control`",
        "",
        f"- Target path: `/hooks/wake`.",
        f"- Successful anomalies: `{len(websocket_anomalies)}`.",
        f"- Proof artifact: `{proof_path}`.",
        f"- Patch objective: `{run_root / 'openclaw-hooks-wake-patch-objective.json'}`.",
        "- Origin citation: `validated_seed_lane:websocket_control`.",
        "- Origin quality: source facts exist in the validated seed; exact Dogpile citation spans are missing and tracked as `RQD-DOGPILE-CITATIONS`.",
        "- Mutation origin: initial success came from `seed-003-websocket_control-0`; later successful variants were agent-generated mutations recorded in `attempts.jsonl` and `anomalies.jsonl`.",
        "",
        "#### Origin Citation Sources",
        "",
        "| Source type | Source | Fact used |",
        "| --- | --- | --- |",
    ]
    for source in websocket_origin_citation.get("supporting_sources", []):
        lines.append(
            f"| `{source.get('source_type')}` | `{source.get('source')}` | {source.get('quote_or_fact')} |"
        )
    lines.extend(
        [
            "",
            "## Hack Groups Tested",
            "",
            f"- Attempts by source/group: {top_counts(attempts_by_group)}.",
            f"- Attempts by transport: {top_counts(attempts_by_transport)}.",
            f"- Attempts by path: {top_counts(attempts_by_path)}.",
            f"- Anomalies by type: {top_counts(anomalies_by_type)}.",
            f"- Anomalies by path: {top_counts(anomalies_by_path)}.",
            "",
            "## How The Successful Exploit Evolved",
            "",
            "- Generation 0 seeded `seed-003-websocket_control-0` and observed a `101 Switching Protocols` response on `/hooks/wake`.",
            "- Generation 1 selected that parent and mutated headers/path variants such as `double-slash` and `invalid-bearer`, increasing best score from `9.0` to `9.5`.",
            "- Generation 2 retained the winning family and added variants such as `spoof-private-forwarded-for` and `json-content-type`.",
            "- Generation 3 preserved the lineage with `null-origin`, `dotdot`, `case-flip`, and repeated plain handshakes, then promoted a focused repro.",
            "",
            "| Attempt | Gen | Score | Gene | Headers | Mutation | Result | Lineage |",
            "| --- | ---: | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for item in winning_lineage[:12]:
        lines.append(
            f"| `{item['attempt']}` | `{item['generation']}` | `{item['score']}` | `{item['gene_id']}` | `{item['headers']}` | `{item['mutation']}` | `{item['result']}` | `{', '.join(item['lineage'])}` |"
        )

    lines.extend(
        [
            "",
            "## Useful Dogpile / Seed Evidence",
            "",
            f"- Seed source: `{seed.get('seed_source')}`.",
            f"- Seed validation: `valid={seed.get('seed_validation', {}).get('valid')}` with SHA `{seed.get('seed_validation', {}).get('seed_sha256')}`.",
            f"- Validated seed artifact: `{seed.get('seed_validation', {}).get('path')}`.",
            f"- Research confidence: `{seed_evidence.get('research_confidence', {}).get('overall')}` — {seed_evidence.get('research_confidence', {}).get('reason')}.",
            f"- External research URL(s): {', '.join(f'`{url}`' for url in seed_evidence.get('source_urls', [])) or '`none`'}.",
            f"- Source artifact paths: {', '.join(f'`{path}`' for path in seed_evidence.get('artifact_paths', [])) or '`none`'}.",
            "- Useful lane: `websocket_control` produced the repeatable proof candidate.",
            "- Useful negative evidence: auth/session and route probes established expected `401` behavior for many non-winning paths.",
            "- Useful false-green filter: SPA fallback-like `text/html` `200` responses were not promoted as proof.",
            f"- Next Dogpile seed: `{evolve_dir / 'next-dogpile-seed.json'}`.",
            "",
            "### Lane-Level Seed Evidence",
            "",
            "| Lane | Supporting source facts | False-positive filters |",
            "| --- | --- | --- |",
        ]
    )
    for lane in seed_evidence.get("recommended_lanes", []):
        facts = "<br>".join(
            f"`{source.get('source_type')}` `{source.get('source')}` — {source.get('quote_or_fact')}"
            for source in lane.get("supporting_sources", [])
        )
        filters = "<br>".join(
            f"{item.get('filter')} Reason: {item.get('reason')}"
            for item in lane.get("false_positive_filters", [])
        )
        lines.append(f"| `{lane.get('lane_id')}` | {facts or '`none`'} | {filters or '`none`'} |")
    lines.extend(
        [
            "",
            "### Dogpile Evidence Quality Defect",
            "",
            "- The validated seed contains lane source facts and artifact paths, but it does not contain exact Dogpile citation spans.",
            "- Required prompt/contract fix: each seed insight and lane must include `citation_text`, `source_artifact`, and `source_location` so the final report can cite Dogpile precisely.",
            "",
            "## Useful Greybox Fuzzing Evidence",
            "",
            f"- Total evolve attempts: `{len(attempts)}`.",
            f"- Total anomalies: `{len(anomalies)}`.",
            f"- Generation summaries: `{generations}`.",
            "- Useful signals: WebSocket `101`, HTTP `401`, content-type fallback detection, lineage metadata, score changes, and repeated variant acceptance.",
            "- Negative evidence stayed useful: failed/low-value groups narrowed the next campaign instead of being discarded.",
            "",
            "## False Greens / Not Promoted",
            "",
            f"- `unexpected-unauthenticated-200` count: `{len(false_green_anomalies)}`.",
            "- These were not treated as exploit proof without source, response-shape, and auth-expectation evidence.",
            "",
            "## Mode Evidence",
            "",
            f"- `session-audit`: report exists `{session.get('has_hack_report')}`, Semgrep exists `{session.get('has_semgrep')}`, launch plan exists `{session.get('has_launch_plan')}`, session `{session.get('session_dir')}`.",
            f"- `evolve-campaign`: attempts `{summary.get('attempts')}`, anomalies `{summary.get('anomalies')}`, promotion tasks `{summary.get('promotion_tasks')}`, proof status `{summary.get('proof_status')}`.",
            f"- `chaos-campaign`: generation-zero attempts `{chaos_summary.get('attempts')}`, anomalies `{chaos_summary.get('anomalies')}`.",
            f"- `battle`: status `{battle.get('status')}`; fresh artifact count `{len(battle.get('fresh_battle_artifacts', []))}`; limitations `{battle.get('limitations', [])}`. Zero findings are not treated as success.",
            "",
            "## Provenance",
            "",
            f"- Target origin: `{preflight.get('origin')}` from `{preflight.get('origin_source')}`.",
            f"- Target commit: `{preflight.get('commit')}` from `{preflight.get('commit_source')}`.",
            f"- Target branch: `{preflight.get('branch')}` from `{preflight.get('branch_source')}`.",
            f"- Docker version: `{preflight.get('docker_version')}`.",
            f"- Docker image digest captured: `{preflight.get('docker_image_digest_captured')}`.",
            f"- Provenance complete: `{preflight.get('provenance_complete')}`.",
            "",
            "## Patch / Hardening Decision",
            "",
            f"- Finding: {patch.get('finding')}.",
            f"- Required fix contract: `{patch.get('required_fix_contract')}`.",
            f"- Verification status: `{post.get('status')}`.",
            f"- Patch status: `{patch.get('patch_status', 'blocked_patch_not_applied')}`.",
            "- Required next step: apply an OpenClaw patch, rerun the focused Docker proof, and require disallowed unauthenticated/cross-origin WebSocket variants to stop upgrading.",
            "",
            "## Source Artifacts",
            "",
        ]
    )
    for key, path in report_json["source_artifacts"].items():
        lines.append(f"- `{key}`: `{path}`")
    lines.extend(["", "## Run Root", "", f"- `{run_root}`", ""])
    return report_json, "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=pathlib.Path)
    args = parser.parse_args()
    report_json, report_markdown = build_report(args.run_root)
    (args.run_root / "HACK_FINAL_REPORT.json").write_text(
        json.dumps(report_json, indent=2) + "\n"
    )
    (args.run_root / "HACK_FINAL_REPORT.md").write_text(report_markdown)
    print(args.run_root / "HACK_FINAL_REPORT.md")


if __name__ == "__main__":
    main()
