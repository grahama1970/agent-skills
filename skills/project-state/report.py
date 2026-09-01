"""Report generation and Markdown formatting.

Orchestrates all phase collectors into a single report dict, and provides
a human-readable Markdown formatter for the resulting data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from best_practices import collect_best_practices
from components import collect_components
from constants import PROJECT_NAME, PROJECT_PROFILE, PROJECT_ROOT
from doc_drift import collect_doc_drift
from gap_analysis import compute_gaps
from infrastructure import (
    collect_cascade,
    collect_daemon_cascade_wiring,
    collect_daemons,
    collect_deploy,
    collect_frontend,
    collect_skills,
    collect_tests,
)
from memory_recall import collect_memory
from research import collect_competitive
from schemas import validate_project_state_report


def generate_report(quick: bool = False, full: bool = False) -> dict[str, Any]:
    """Collect all phases into a single report dict."""
    # Phase 1: Infrastructure (always)
    daemon_data = collect_daemons()
    cascade_data = collect_cascade()
    daemon_wiring = collect_daemon_cascade_wiring()
    test_data = collect_tests()
    skills_data = collect_skills()
    frontend_data = collect_frontend()
    deploy_data = collect_deploy()

    components_data = collect_components()

    report = {
        "schema": "project_state.report.v1",
        "project": PROJECT_NAME,
        "project_root": str(PROJECT_ROOT),
        "project_profile": PROJECT_PROFILE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "quick" if quick else ("full" if full else "standard"),
        "phase_1_infrastructure": {
            "daemons": daemon_data,
            "tests": test_data,
            "cascade": cascade_data,
            "daemon_cascade_wiring": daemon_wiring,
            "skills": skills_data,
            "frontend": frontend_data,
            "deploy": deploy_data,
            "components": components_data,
        },
    }

    doc_drift = None
    best_practices = None
    research = None

    if not quick:
        # Phase 2: Memory
        report["phase_2_memory"] = collect_memory()

        # Phase 3: Doc-Code Drift
        doc_drift = collect_doc_drift()
        report["phase_3_doc_drift"] = doc_drift

        # Phase 4: Best Practices
        best_practices = collect_best_practices()
        report["phase_4_best_practices"] = best_practices

        # Phase 5 is intentionally full-only so standard/cleanup-tail remains
        # bounded and does not spend web/API calls for every state snapshot.
        research = collect_competitive(
            skip=not full, full=full,
            cascade=cascade_data, daemons=daemon_data, doc_drift=doc_drift,
        )
        report["phase_5_research"] = research

    # Phase 6: Gap Analysis (always, depth depends on phases run)
    report["phase_6_gaps"] = compute_gaps(
        report["phase_1_infrastructure"], cascade_data, daemon_data,
        daemon_wiring, doc_drift, best_practices, skills_data,
        research=research,
    )

    return validate_project_state_report(report)


def format_markdown(report: dict) -> str:
    """Format report as human-readable Markdown."""
    lines = []
    ts = report["timestamp"]
    mode = report.get("mode", "standard")
    project = report.get("project", "Project")
    profile = report.get("project_profile", "generic")
    lines.append(f"# {project} Project State -- {ts[:10]} ({mode} mode, {profile} profile)")
    lines.append("")

    infra = report["phase_1_infrastructure"]

    # Daemons
    d = infra["daemons"]
    lines.append("## Phase 1: Infrastructure")
    lines.append("")
    if d.get("applicable", True):
        lines.append(f"### Daemons ({d['up']}/{d['total']} up)")
        lines.append("")
        lines.append("| Daemon | Status |")
        lines.append("|--------|--------|")
        for name, info in d["daemons"].items():
            status = info["status"]
            icon = "OK" if status in ("ok", "healthy") else "DOWN"
            lines.append(f"| {name} | {icon} |")
        lines.append("")
    else:
        lines.append(f"### Daemons: not applicable ({d.get('reason', 'generic project')})")
        lines.append("")

    # Tests
    t = infra["tests"]
    if t.get("error") == "tests dir missing":
        lines.append("### Tests: not applicable (target has no tests/ directory)")
    elif not t.get("collected", True):
        lines.append(f"### Tests: COLLECTION FAILED — {str(t.get('error'))[:120]}")
    else:
        lines.append(f"### Tests: {t['total']} collected")
    lines.append("")

    # Cascade
    c = infra["cascade"]
    if c.get("applicable", True):
        lines.append("### 3-Tier Cascade")
        lines.append("")
        lines.append("| Tier | Status |")
        lines.append("|------|--------|")
        for tier, status in c["tier_status"].items():
            label = tier.replace("_", " ").replace("tier ", "Tier ").title()
            lines.append(f"| {label} | {status} |")
        lines.append("")

        r = c["registry"]
        lines.append(f"**Model Registry**: {r['validators']}V / {r['classifiers']}C / {r['regressors']}R / {r['gpts']}G")
        s = c["shadow"]
        lines.append(f"**Shadow Entries**: {s['usable']} usable / {s['total']} total")
        lines.append("")
    else:
        lines.append(f"### 3-Tier Cascade: not applicable ({c.get('reason', 'generic project')})")
        lines.append("")

    if c.get("training_data"):
        lines.append("| Task | Labels |")
        lines.append("|------|--------|")
        for task, count in sorted(c["training_data"].items()):
            lines.append(f"| {task} | {count} |")
        lines.append("")

    if c.get("classifiers_on_disk"):
        lines.append("**Classifiers on disk**: " + ", ".join(
            f"{clf['name']} ({clf['size_kb']}KB)" for clf in c["classifiers_on_disk"]
        ))
        lines.append("")

    # Daemon wiring
    wiring = infra["daemon_cascade_wiring"]
    if wiring.get("applicable", True):
        lines.append("### Cascade Wiring: " + ", ".join(
            f"{n}={'YES' if w else 'NO'}" for n, w in wiring.items()
        ))
    else:
        lines.append(f"### Cascade Wiring: not applicable ({wiring.get('reason', 'generic project')})")
    lines.append("")

    # Skills
    sk = infra["skills"]
    if sk.get("applicable") is False:
        lines.append(f"### Skills: not applicable ({sk.get('reason', 'target owns no skills tree')})")
    else:
        lines.append(f"### Skills: {sk['total']} total")
    if sk.get("missing_skill_md_count", 0) > 0:
        lines.append(f"  - {sk['missing_skill_md_count']} dirs without SKILL.md")
    if sk.get("missing_sanity_count", 0) > 0:
        lines.append(f"  - {sk['missing_sanity_count']} skills without sanity.sh")
    lines.append("")

    # Frontend + Deploy
    fe = infra["frontend"]
    dep = infra["deploy"]
    if fe.get("exists"):
        lines.append(f"### Frontend: {fe.get('tsx_components', 0)} TSX / {fe.get('rust_files', 0)} Rust")
    lines.append(f"### Deploy: {dep['systemd_units']} systemd units")
    lines.append("")

    # Component Projects
    comp_data = infra.get("components", {})
    if comp_data.get("registered", 0) > 0:
        ok = comp_data.get("ok", 0)
        total = comp_data["registered"]
        lines.append(f"### Component Projects ({ok}/{total} found)")
        lines.append("")
        lines.append("| Project | Tests | Last Commit | Dirty | Role |")
        lines.append("|---------|-------|-------------|-------|------|")
        for name, info in comp_data.get("projects", {}).items():
            if info.get("status") == "MISSING":
                lines.append(f"| {name} | - | MISSING | - | {info.get('role', '')} |")
                continue
            tests = info.get("tests", "-")
            t_status = info.get("test_status", "")
            if t_status == "SKIPPED":
                tests = "n/a"
            elif t_status == "ERROR":
                tests = "ERR"
            commit = info.get("last_commit", "unknown")
            dirty = "YES" if info.get("dirty") else "clean"
            if info.get("changed_files", 0) > 0:
                dirty = f"YES ({info['changed_files']})"
            role = info.get("role", "")[:40]
            lines.append(f"| {name} | {tests} | {commit} | {dirty} | {role} |")
        lines.append("")

    # Phase 2: Memory
    mem = report.get("phase_2_memory")
    if mem and mem.get("available"):
        lines.append("## Phase 2: Memory Recall")
        lines.append("")
        for recall in mem.get("recalls", []):
            found = "FOUND" if recall.get("found") else "NOT FOUND"
            conf = recall.get("confidence", 0)
            lines.append(f"- **{recall['query'][:60]}**: {found} (conf={conf:.2f}, {recall.get('count', 0)} items)")
            for item in recall.get("top_items", []):
                if item.get("problem"):
                    lines.append(f"  - {item['problem'][:100]}")
        lines.append("")

    # Phase 3: Doc Drift
    drift = report.get("phase_3_doc_drift")
    if drift:
        lines.append(f"## Phase 3: Doc-Code Drift ({drift['drift_count']} items)")
        lines.append("")
        if drift["drift_items"]:
            by_issue = {}
            for item in drift["drift_items"]:
                by_issue.setdefault(item["issue"], []).append(item)
            for issue, items in sorted(by_issue.items()):
                lines.append(f"- **{issue}** ({len(items)}x): {items[0].get('line', items[0].get('file', ''))[:80]}")
        lines.append("")

    # Phase 4: Best Practices
    bp = report.get("phase_4_best_practices")
    if bp:
        sev = bp.get("by_severity", {})
        lines.append(f"## Phase 4: Best Practices ({bp['total_findings']} findings)")
        lines.append(f"  Critical={sev.get('critical',0)} High={sev.get('high',0)} Medium={sev.get('medium',0)} Low={sev.get('low',0)}")
        lines.append("")
        if bp.get("findings"):
            shown = {}
            for f in bp["findings"][:15]:
                key = f"{f['issue']}"
                if key not in shown:
                    shown[key] = 0
                shown[key] += 1
            for issue, count in sorted(shown.items(), key=lambda x: -x[1]):
                lines.append(f"- {issue}: {count}x")
        lines.append("")

    # Phase 5: External Research
    research_data = report.get("phase_5_research")
    if research_data and not research_data.get("skipped"):
        rmode = research_data.get("mode", "standard")
        n = research_data.get("queries_run", 0)
        lines.append(f"## Phase 5: External Research ({n} queries, {rmode} mode)")
        lines.append("")
        for r in research_data.get("results", []):
            src = r.get("source", "?").upper()
            reason = r.get("reason", "")
            if r.get("error"):
                lines.append(f"- [{src}] **{reason}**: {r['error']}")
            else:
                output = r.get("output", "")[:300]
                lines.append(f"- [{src}] **{reason}**:")
                for out_line in output.splitlines()[:6]:
                    if out_line.strip():
                        lines.append(f"  {out_line.strip()}")
        lines.append("")
    elif research_data and research_data.get("skipped"):
        lines.append("## Phase 5: External Research (skipped -- quick mode)")
        lines.append("")

    # Phase 6: Gaps + Improvements
    phase6 = report.get("phase_6_gaps", {})
    if isinstance(phase6, list):
        # Backwards compat: old format was just a list of gaps
        gaps = phase6
        improvements = []
    else:
        gaps = phase6.get("gaps", [])
        improvements = phase6.get("improvements", [])

    if gaps:
        lines.append(f"## Phase 6: Gap Analysis ({len(gaps)} gaps)")
        lines.append("")
        for i, gap in enumerate(gaps, 1):
            sev = gap["severity"].upper()
            lines.append(f"{i}. **[{sev}]** {gap['gap']}")
            lines.append(f"   Action: {gap['action']}")
            if gap.get("arxiv_context"):
                lines.append(f"   ArXiv: {gap['arxiv_context'][:200]}")
        lines.append("")

    if improvements:
        lines.append(f"### Research-Informed Improvements ({len(improvements)} opportunities)")
        lines.append("")
        for i, imp in enumerate(improvements, 1):
            cat = imp.get("category", "general")
            opp = imp.get("opportunity", "")
            lines.append(f"{i}. **[{cat}]** {opp}")
            if imp.get("action"):
                lines.append(f"   Action: {imp['action']}")
            if imp.get("arxiv_context"):
                for ctx_line in imp["arxiv_context"].splitlines()[:3]:
                    if ctx_line.strip():
                        lines.append(f"   {ctx_line.strip()}")
            if imp.get("findings"):
                for find_line in imp["findings"].splitlines()[:3]:
                    if find_line.strip():
                        lines.append(f"   {find_line.strip()}")
        lines.append("")

    return "\n".join(lines)
