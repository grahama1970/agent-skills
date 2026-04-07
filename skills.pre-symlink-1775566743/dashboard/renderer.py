"""Dashboard output renderers for JSON and plain-text modes."""
from __future__ import annotations

import json
from typing import Any


def render_json(data: dict[str, Any]) -> str:
    """Render dashboard data as pretty-printed JSON."""
    return json.dumps(data, indent=2, default=str)


def render_text(data: dict[str, Any]) -> str:
    """Render dashboard data as plain text summary."""
    lines: list[str] = []
    lines.append(f"=== Embry OS Dashboard === ({data.get('collected_at', 'N/A')})")
    lines.append("")

    # Daemons
    dh = data.get("daemon_health", {})
    if "error" not in dh:
        healthy = dh.get("healthy", 0)
        total = dh.get("total", 0)
        lines.append(f"Daemons: {healthy}/{total} healthy")
        for name, info in sorted(dh.get("daemons", {}).items()):
            lines.append(f"  {name}: {info.get('status', 'unknown')}")
    else:
        lines.append(f"Daemons: {dh['error']}")
    lines.append("")

    # LLM Metrics
    llm = data.get("llm_metrics", {})
    if "error" not in llm:
        lines.append(f"LLM Calls (24h): {llm.get('calls_today', 0)}")
        avg = llm.get("avg_latency_ms", 0)
        lines.append(f"  Avg Latency: {avg / 1000:.1f}s" if avg else "  Avg Latency: N/A")
        lines.append(f"  Cache Hit: {llm.get('cache_hit_rate', 0):.0%}")
    else:
        lines.append(f"LLM Metrics: {llm['error']}")
    lines.append("")

    # Shadow Agreement
    shadow = data.get("shadow_agreement", {})
    if "error" not in shadow:
        lines.append(f"Shadow Agreement: {shadow.get('agreement_rate', 0):.0%} ({shadow.get('total', 0)} entries)")
    else:
        lines.append(f"Shadow: {shadow['error']}")
    lines.append("")

    # Cascade
    cascade = data.get("cascade_state", {})
    if "error" not in cascade:
        lines.append(f"Cascade: {cascade.get('validators', 0)} validators, "
                      f"{cascade.get('classifiers', 0)} classifiers, "
                      f"{cascade.get('regressors', 0)} regressors")
    else:
        lines.append(f"Cascade: {cascade['error']}")
    lines.append("")

    # Chutes
    chutes = data.get("chutes_quota", {})
    if "used" in chutes:
        lines.append(f"Chutes: {chutes.get('used', 0):.0f}/{chutes.get('quota', 0):.0f} used")
        balance = chutes.get("balance", "?")
        if isinstance(balance, (int, float)):
            lines.append(f"  Balance: ${balance:.2f}")
        slots = chutes.get("slots_in_use", "?")
        lines.append(f"  Concurrency: {slots}/5 slots")
    elif "error" in chutes:
        lines.append(f"Chutes: {chutes['error']}")
    lines.append("")

    # Git Status
    git = data.get("git_status", {})
    if "error" not in git:
        branch = git.get("branch", "?")
        dirty = git.get("dirty_files", 0)
        age = git.get("last_commit_age_seconds", 0)
        age_str = f"{age / 3600:.1f}h" if age >= 3600 else f"{age / 60:.0f}m"
        lines.append(f"Git: {branch} ({dirty} dirty) last commit {age_str} ago")
        subj = git.get("last_commit_subject", "")
        if subj:
            lines.append(f"  {subj}")
    lines.append("")

    # Backend Health
    bh = data.get("backend_health", {})
    if "error" not in bh:
        lines.append(f"Backends: {bh.get('available', 0)}/{bh.get('total', 0)} available")
        for name, info in sorted(bh.get("backends", {}).items()):
            status = "UP" if info.get("available") else "DOWN"
            ver = info.get("version") or ""
            lines.append(f"  {name}: {status} {ver}")
    lines.append("")

    # Cost
    cost = data.get("cost_data", {})
    if "error" not in cost:
        today = cost.get("today", cost.get("daily_total", 0))
        mtd = cost.get("mtd", cost.get("monthly_total", 0))
        lines.append(f"Cost: Today ${today:.2f} / MTD ${mtd:.2f}")
        for prov, amt in sorted(cost.get("providers", cost.get("by_provider", {})).items()):
            if isinstance(amt, (int, float)):
                lines.append(f"  {prov}: ${amt:.2f}")
    elif "error" in cost:
        lines.append(f"Cost: {cost['error']}")
    lines.append("")

    # Subagents
    sub = data.get("subagent_state", {})
    if "error" not in sub:
        lines.append(f"Subagents: {sub.get('running', 0)} running, {sub.get('completed', 0)} done, {sub.get('errored', 0)} errors")
    lines.append("")

    # Active Tasks
    tasks = data.get("active_tasks", {})
    active = tasks.get("active", 0)
    lines.append(f"Active Tasks: {active}")
    for t in tasks.get("tasks", []):
        elapsed = t.get("elapsed_seconds", 0)
        if elapsed >= 3600:
            time_str = f"{elapsed / 3600:.1f}h"
        elif elapsed >= 60:
            time_str = f"{elapsed / 60:.0f}m"
        elif elapsed > 0:
            time_str = f"{elapsed:.0f}s"
        else:
            time_str = ""
        item = t.get("current_item", "")
        extra = f" [{time_str}]" if time_str else ""
        extra += f" {item}" if item else ""
        lines.append(f"  {t['name']}: {t.get('completed', 0)}/{t.get('total', '?')} ({t.get('pct', 0):.0f}%){extra}")
    lines.append("")

    # Skill Health
    sh = data.get("skill_health", {})
    if "error" not in sh:
        lines.append(f"Skill Health: {sh.get('overall_status', 'unknown').upper()} "
                      f"({sh.get('total_skills', 0)} skills)")
        counts = sh.get("status_counts", {})
        for k, v in counts.items():
            lines.append(f"  {k}: {v}")
    else:
        lines.append(f"Skill Health: {sh['error']}")
    return "\n".join(lines)
