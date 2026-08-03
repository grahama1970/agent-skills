#!/usr/bin/env python3
"""Dewey overnight morning report — create-report shaped human readout.

Intended workflow: Dewey runs overnight scans; this script assembles
report.json + report.md + report.html for morning human review.

Usage:
  python render_overnight_morning_report.py
  python render_overnight_morning_report.py --skip-scans  # use latest artifacts only
"""
from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

AGENT_SKILLS = Path(os.environ.get("AGENT_SKILLS_ROOT", "/home/graham/workspace/experiments/agent-skills"))
MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", "/home/graham/workspace/experiments/memory"))
SCRIPTS = AGENT_SKILLS / "agents/dba-auditor/scripts"
FOCUS_SCRIPT = SCRIPTS / "dewey_nightly_focus.py"
OUTPUT_BASE = Path(
    os.environ.get(
        "DEWEY_MORNING_REPORT_DIR",
        "/mnt/storage12tb/skills/review-db/outputs/dewey-morning-reports",
    )
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())


def _now_human() -> str:
    return time.strftime("%A %Y-%m-%d %H:%M UTC", time.gmtime())


def _run_scan(script: str, extra: list[str] | None = None) -> dict[str, Any]:
    out = Path(f"/tmp/dewey_scan_{Path(script).stem}.json")
    cmd = [sys.executable, str(SCRIPTS / script), "--out", str(out)]
    if extra:
        cmd.extend(extra)
    proc = subprocess.run(cmd, cwd=MEMORY_ROOT, capture_output=True, text=True)
    if proc.returncode != 0 and not out.is_file():
        return {"error": proc.stderr[-2000:], "script": script}
    if out.is_file():
        return json.loads(out.read_text(encoding="utf-8"))
    return json.loads(proc.stdout)


def _latest_glob(base: Path, pattern: str) -> Path | None:
    if not base.is_dir():
        return None
    files = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _load_latest_or_scan(name: str, scan_fn, skip_scans: bool) -> dict[str, Any]:
    bases = {
        "opportunities": Path("/mnt/storage12tb/skills/review-db/outputs/dewey-sparta-opportunities"),
        "framework": Path("/mnt/storage12tb/skills/review-db/outputs/dewey-framework-ingestion"),
        "qra": Path("/mnt/storage12tb/skills/review-db/outputs/dewey-qra-audits"),
    }
    if not skip_scans:
        return scan_fn()
    patterns = {
        "opportunities": "opportunities_*.json",
        "framework": "framework_ingestion_*.json",
        "qra": "qra_landscape_*.json",
    }
    path = _latest_glob(bases[name], patterns[name])
    if path:
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema": "dewey_scan_reference.v1",
        "name": name,
        "status": "missing_latest_artifact",
        "skip_scans": True,
        "searched_dir": str(bases[name]),
        "pattern": patterns[name],
        "generated_at": None,
        "non_claims": [
            "No live scan was run because --skip-scans was set.",
            "This placeholder is not operational evidence for the underlying lane.",
        ],
    }


def _decision(monitor: dict[str, Any], opps: list[dict[str, Any]]) -> str:
    passed = int((monitor or {}).get("passed") or 0)
    total = int((monitor or {}).get("total") or 0)
    high = [o for o in opps if o.get("impact") == "high"]
    if passed < total * 0.5:
        return "BLOCKED"
    if high or passed < total:
        return "CONDITIONAL_PASS"
    return "PASS"


def load_nightly_focus() -> dict[str, Any] | None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("dewey_nightly_focus", FOCUS_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import httpx
    with httpx.Client(base_url=os.environ.get("MEMORY_URL", "http://127.0.0.1:8601"), timeout=30.0) as client:
        active = mod._list_active(client)
    active.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
    return active[0] if active else None


def build_report_model(skip_scans: bool) -> dict[str, Any]:
    opportunities_report = _load_latest_or_scan(
        "opportunities",
        lambda: _run_scan("sparta_dataset_opportunities.py", ["--manifest-limit", "50"]),
        skip_scans,
    )
    framework_report = _load_latest_or_scan(
        "framework",
        lambda: _run_scan("sparta_framework_ingestion_scan.py"),
        skip_scans,
    )
    qra_report = _load_latest_or_scan(
        "qra",
        lambda: _run_scan("audit_qra_landscape.py", ["--manifest-limit", "50"]),
        skip_scans,
    )

    monitor = opportunities_report.get("monitor_health") or {}
    opps = opportunities_report.get("improvement_opportunities") or []
    fw_gaps = framework_report.get("ingestion_gaps") or []
    decision = _decision(monitor, opps)
    nightly_focus = load_nightly_focus()

    top_actions = []
    for o in opps[:5]:
        top_actions.append({
            "priority": o.get("rank", len(top_actions) + 1),
            "owner": o.get("owner_lane", "human_review"),
            "action": o.get("action"),
            "scale": o.get("scale"),
            "kind": o.get("kind"),
        })

    findings = []
    if int((qra_report.get("source_text_qra_coverage") or {}).get("qra_missing_generation_required") or 0):
        n = (qra_report["source_text_qra_coverage"])["qra_missing_generation_required"]
        findings.append({
            "id": "direct_qra_gap",
            "observation": f"{n} controls lack direct/canonical QRA coverage.",
            "impact": "Explorer and monitor qra_coverage_per_control remain red.",
            "response": "Queue canonical QRA generation via monitor-sparta lane.",
        })
    if fw_gaps:
        missing = [g for g in fw_gaps if g.get("corpus_count") == 0 or "new_category" in str(g.get("id", ""))]
        if missing:
            findings.append({
                "id": "framework_ingestion_gaps",
                "observation": f"{len(missing)} new or empty framework categories referenced but not ingested.",
                "impact": "Crosswalk and adversarial banks incomplete (EMB3D, CSF, aviation PDFs).",
                "response": "Route to ingest-sparta; use brave/github for upstream version proof.",
            })

    return {
        "schema": "dewey_overnight_morning_report.v1",
        "generated_at": _now(),
        "generated_at_human": _now_human(),
        "persona": "dba_auditor",
        "display_name": "Dewey",
        "primary_object": "SPARTA dataset + memory infrastructure overnight audit",
        "intended_reader": "human operator (morning review)",
        "decision": decision,
        "executive_summary": (
            f"Monitor health {monitor.get('passed', '?')}/{monitor.get('total', '?')}. "
            f"{len(opps)} improvement opportunities ranked. "
            f"{len(fw_gaps)} framework ingestion signals. "
            "Corpus is present; primary work is dataset enrichment and mechanical hygiene—not emergency restore."
        ),
        "monitor_health": monitor,
        "top_actions": top_actions,
        "improvement_opportunities": opps,
        "framework_ingestion_gaps": fw_gaps,
        "qra_landscape_summary": {
            "missing_direct_qras": (qra_report.get("source_text_qra_coverage") or {}).get("qra_missing_generation_required"),
            "control_to_control_pending": (qra_report.get("control_to_control_backlog") or {}).get("gated_pairs_pending"),
        },
        "findings": findings,
        "source_artifacts": {
            "opportunities_report": opportunities_report.get("generated_at"),
            "framework_report": framework_report.get("generated_at"),
            "qra_report": qra_report.get("generated_at"),
        },
        "non_claims": [
            "Overnight report does not prove all QRAs passed create-evidence-case.",
            "Opportunity ranking is heuristic until human approves execution order.",
            "External search (brave/github) may be required for upstream version confirmation.",
            "Mechanical repairs were not auto-applied unless a separate db_repair_session ran.",
        ],
        "human_nightly_focus": nightly_focus,
        "plan_iterate_seed": {
            "recommended_phase": "sparta-dataset-improvement",
            "objective": "Execute top 3 ranked opportunities with owner lanes and verification gates.",
            "acceptance": "monitor-sparta health improves on targeted dimensions without corpus regression.",
        },
    }


def _focus_block(model: dict[str, Any]) -> str:
    f = model.get("human_nightly_focus")
    if not f:
        return "- No active nightly focus in `subagent_memory`. Human may set via `/ask` Dewey + `dewey_nightly_focus.py store`."
    lanes = ", ".join(f.get("monitor_sparta_lanes") or []) or "unspecified"
    return (
        f"- **Objective:** {f.get('focus_objective')}\n"
        f"- **Lanes:** {lanes}\n"
        f"- **Memory key:** `{f.get('_key')}`"
    )


def render_markdown(model: dict[str, Any]) -> str:
    lines = [
        f"# Dewey Morning Report — {model['generated_at_human']}",
        "",
        "## Decision",
        f"**{model['decision']}** — {model['executive_summary']}",
        "",
        "## Human Focus (overnight directive)",
        _focus_block(model),
        "",
        "## Action Sheet (read this first)",
        f"- **Status:** {model['decision']}",
        f"- **Monitor:** {model['monitor_health'].get('passed')}/{model['monitor_health'].get('total')} checks passing",
        f"- **Opportunities:** {len(model['improvement_opportunities'])} ranked",
        f"- **Missing direct QRAs:** {model['qra_landscape_summary'].get('missing_direct_qras')}",
        f"- **Control-to-control pending:** {model['qra_landscape_summary'].get('control_to_control_pending')}",
        "",
        "### Top actions",
    ]
    for a in model["top_actions"]:
        lines.append(f"{a['priority']}. **[{a.get('kind')}]** {a['action']} _(owner: {a['owner']}, scale: {a.get('scale')})_")
    lines.extend(["", "## Findings", ""])
    for f in model["findings"]:
        lines.append(f"### {f['id']}\n- **Observation:** {f['observation']}\n- **Impact:** {f['impact']}\n- **Response:** {f['response']}\n")
    lines.extend(["", "## Framework ingestion gaps", ""])
    for g in model["framework_ingestion_gaps"][:8]:
        label = g.get("label") or g.get("framework") or g.get("id")
        lines.append(f"- **{label}:** {g.get('action')}")
    lines.extend(["", "## Non-claims", ""])
    for n in model["non_claims"]:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def render_html(model: dict[str, Any], md: str) -> str:
    esc = html.escape
    actions_rows = "".join(
        f"<tr><td>{esc(str(a.get('priority')))}</td><td>{esc(str(a.get('kind')))}</td>"
        f"<td>{esc(str(a.get('action') or ''))}</td><td>{esc(str(a.get('owner') or ''))}</td>"
        f"<td>{esc(str(a.get('scale') or ''))}</td></tr>"
        for a in model["top_actions"]
    )
    findings_html = "".join(
        f"<section><h3>{esc(f['id'])}</h3><p><strong>Observation:</strong> {esc(f['observation'])}</p>"
        f"<p><strong>Impact:</strong> {esc(f['impact'])}</p>"
        f"<p><strong>Response:</strong> {esc(f['response'])}</p></section>"
        for f in model["findings"]
    )
    non_claims = "".join(f"<li>{esc(n)}</li>" for n in model["non_claims"])
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Dewey Morning Report</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:920px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#111}}
.decision{{font-size:1.25rem;font-weight:700;padding:1rem;border-left:4px solid #2563eb;background:#f8fafc}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}} th,td{{border:1px solid #ddd;padding:.5rem;text-align:left}}
th{{background:#f1f5f9}} section{{margin:1rem 0;padding:.75rem;background:#fafafa;border:1px solid #eee}}
@media print{{body{{margin:0;max-width:none}}}}
</style></head><body>
<h1>Dewey Morning Report</h1>
<p><em>{esc(model['generated_at_human'])}</em></p>
<div class="decision">Decision: {esc(model['decision'])} — {esc(model['executive_summary'])}</div>
<h2>Human Focus</h2><pre>{esc(_focus_block(model))}</pre>
<h2>Action Sheet</h2>
<ul>
<li>Monitor: {esc(str(model['monitor_health'].get('passed')))}/{esc(str(model['monitor_health'].get('total')))} passing</li>
<li>Missing direct QRAs: {esc(str(model['qra_landscape_summary'].get('missing_direct_qras')))}</li>
<li>Control-to-control pending: {esc(str(model['qra_landscape_summary'].get('control_to_control_pending')))}</li>
</ul>
<h2>Top Actions</h2>
<table><thead><tr><th>#</th><th>Kind</th><th>Action</th><th>Owner</th><th>Scale</th></tr></thead>
<tbody>{actions_rows}</tbody></table>
<h2>Findings</h2>{findings_html}
<h2>Non-claims</h2><ul>{non_claims}</ul>
<details><summary>Markdown fallback</summary><pre>{esc(md)}</pre></details>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-scans", action="store_true", help="use latest scan artifacts only")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    model = build_report_model(args.skip_scans)
    out_dir = args.out_dir or (OUTPUT_BASE / model["generated_at"])
    out_dir.mkdir(parents=True, exist_ok=True)

    report_json = out_dir / "report.json"
    report_md = out_dir / "report.md"
    report_html = out_dir / "report.html"
    latest = OUTPUT_BASE / "latest"

    md = render_markdown(model)
    html_doc = render_html(model, md)
    report_json.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_md.write_text(md, encoding="utf-8")
    report_html.write_text(html_doc, encoding="utf-8")

    latest.mkdir(parents=True, exist_ok=True)
    for name, src in [("report.json", report_json), ("report.md", report_md), ("report.html", report_html)]:
        (latest / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    print(md)
    print(f"\nWrote {report_json}\nWrote {report_md}\nWrote {report_html}\nLatest: {latest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
