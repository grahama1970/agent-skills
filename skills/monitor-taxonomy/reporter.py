"""Rich console output and JSON report generation for monitor-taxonomy.

Renders probe results as a Rich table for terminal output, or as structured
JSON for machine consumption and state persistence.

Inputs: list of ProbeResult from probe execution.
Outputs: Rich table to stderr, JSON to stdout (when --json), state file to disk.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from probes import ProbeResult, ProbeStatus

import config

console = Console(stderr=True)

_STATUS_STYLE = {
    ProbeStatus.PASS: "green",
    ProbeStatus.WARN: "yellow",
    ProbeStatus.FAIL: "red bold",
    ProbeStatus.SKIP: "dim",
    ProbeStatus.FIXED: "cyan",
}


def report_results(results: list[ProbeResult], json_output: bool = False) -> None:
    """Render probe results to console and optionally as JSON."""
    if not results:
        logger.warning("No probe results to report")
        return

    counts = {s: 0 for s in ProbeStatus}
    for r in results:
        counts[r.status] += 1

    total = len(results)
    health = "healthy"
    if counts[ProbeStatus.FAIL] > 0:
        health = "critical"
    elif counts[ProbeStatus.WARN] > 0:
        health = "warning"

    if not json_output:
        _render_table(results, health, counts, total)
    else:
        _render_json(results, health, counts, total)

    _save_state(results, health, counts, total)


def _render_table(
    results: list[ProbeResult],
    health: str,
    counts: dict,
    total: int,
) -> None:
    """Render Rich table to console."""
    health_color = {"healthy": "green", "warning": "yellow", "critical": "red"}[health]

    console.print(Panel(
        f"[{health_color} bold]{health.upper()}[/{health_color} bold]  "
        f"({counts[ProbeStatus.PASS]} pass, {counts[ProbeStatus.WARN]} warn, "
        f"{counts[ProbeStatus.FAIL]} fail, {counts[ProbeStatus.SKIP]} skip, "
        f"{counts[ProbeStatus.FIXED]} fixed)",
        title="Monitor Taxonomy",
        subtitle=time.strftime("%Y-%m-%d %H:%M"),
    ))

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Probe", min_width=24)
    table.add_column("Tier", justify="center", width=6)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Message")

    for r in results:
        style = _STATUS_STYLE.get(r.status, "")
        table.add_row(
            r.probe_id,
            r.name,
            str(r.tier),
            f"[{style}]{r.status.value.upper()}[/{style}]",
            r.message,
        )

    console.print(table)


def _render_json(
    results: list[ProbeResult],
    health: str,
    counts: dict,
    total: int,
) -> None:
    """Render JSON to stdout (not stderr)."""
    out_console = Console()
    payload = {
        "health": health,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {s.value: c for s, c in counts.items()},
        "total": total,
        "probes": [
            {
                "probe_id": r.probe_id,
                "name": r.name,
                "tier": r.tier,
                "status": r.status.value,
                "message": r.message,
                "details": r.details,
                "auto_fixable": r.auto_fixable,
                "fix_applied": r.fix_applied,
            }
            for r in results
        ],
    }
    out_console.print_json(json.dumps(payload))


def _save_state(
    results: list[ProbeResult],
    health: str,
    counts: dict,
    total: int,
) -> None:
    """Persist latest report to state directory."""
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = config.STATE_DIR / "latest_report.json"
    payload = {
        "health": health,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {s.value: c for s, c in counts.items()},
        "total": total,
        "probes": [
            {
                "probe_id": r.probe_id,
                "name": r.name,
                "tier": r.tier,
                "status": r.status.value,
                "message": r.message,
                "auto_fixable": r.auto_fixable,
                "fix_applied": r.fix_applied,
            }
            for r in results
        ],
    }
    try:
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, state_file)
    except OSError as e:
        logger.error("Failed to save state: {}", e)


def _render_proposals_tab() -> None:
    """Render vocabulary expansion proposals from /memory."""
    import httpx

    try:
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            resp = client.post("/recall", json={
                "q": "taxonomy_vocabulary_proposals",
                "scope": "operational",
                "k": 50,
            })
            if resp.status_code != 200:
                return
            data = resp.json()
            proposals = data.get("items", data.get("results", []))
    except Exception:
        return

    if not proposals:
        return

    status_style = {
        "pending": "yellow",
        "approved": "green",
        "applied": "cyan",
        "rejected": "red",
        "reverted": "magenta",
    }

    prop_table = Table(title="Vocabulary Expansion Proposals", show_header=True, header_style="bold")
    prop_table.add_column("Key", style="dim", max_width=25)
    prop_table.add_column("Type", width=16)
    prop_table.add_column("Scope", width=12)
    prop_table.add_column("Status", justify="center", width=10)
    prop_table.add_column("Terms", max_width=40)
    prop_table.add_column("Evidence", justify="right", width=10)

    for p in proposals:
        status = p.get("status", "unknown")
        style = status_style.get(status, "")
        terms = p.get("proposed_additions", [])
        terms_str = ", ".join(terms[:5])
        if len(terms) > 5:
            terms_str += f" (+{len(terms)-5})"
        evidence = p.get("evidence", {})
        ev_str = f"{evidence.get('warn_count', 0)} warns"

        prop_table.add_row(
            p.get("_key", "")[:25],
            p.get("vocab_type", ""),
            p.get("scope", ""),
            f"[{style}]{status.upper()}[/{style}]",
            terms_str,
            ev_str,
        )

    console.print(prop_table)


def show_dashboard() -> None:
    """Load latest report from state and render dashboard."""
    state_file = config.STATE_DIR / "latest_report.json"
    if not state_file.exists():
        console.print("[yellow]No report found. Run 'check' first.[/yellow]")
        return

    try:
        data = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Failed to load report: {e}[/red]")
        return

    health = data.get("health", "unknown")
    health_color = {"healthy": "green", "warning": "yellow", "critical": "red"}.get(
        health, "white",
    )

    console.print(Panel(
        f"[{health_color} bold]{health.upper()}[/{health_color} bold]",
        title="Monitor Taxonomy Dashboard",
        subtitle=data.get("timestamp", ""),
    ))

    summary = data.get("summary", {})
    summary_table = Table(title="Summary", show_header=True)
    summary_table.add_column("Status", style="cyan")
    summary_table.add_column("Count", justify="right")
    for status, count in summary.items():
        summary_table.add_row(status, str(count))
    console.print(summary_table)

    probes = data.get("probes", [])
    if probes:
        probe_table = Table(title="Probes", show_header=True, header_style="bold")
        probe_table.add_column("ID", style="dim", width=4)
        probe_table.add_column("Probe", min_width=24)
        probe_table.add_column("Tier", justify="center", width=6)
        probe_table.add_column("Status", justify="center", width=8)
        probe_table.add_column("Message")

        for p in probes:
            status = p.get("status", "unknown")
            style = {
                "pass": "green", "warn": "yellow", "fail": "red bold",
                "skip": "dim", "fixed": "cyan",
            }.get(status, "")
            probe_table.add_row(
                p.get("probe_id", ""),
                p.get("name", ""),
                str(p.get("tier", "")),
                f"[{style}]{status.upper()}[/{style}]",
                p.get("message", ""),
            )
        console.print(probe_table)

    # Vocabulary expansion proposals tab
    _render_proposals_tab()


def show_status() -> None:
    """Show cascade status: labels, shadow agreement, classifier."""
    # Label count
    label_count = 0
    if config.TRAINING_LABELS_FILE.exists():
        label_count = sum(1 for line in config.TRAINING_LABELS_FILE.read_text().splitlines() if line.strip())

    # Shadow stats
    shadow_stats = {"total": 0, "agreement_rate": 0.0, "status": "no_data"}
    if config.SHADOW_FILE.exists():
        import json as _json
        agree = disagree = 0
        for line in config.SHADOW_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = _json.loads(line)
                if entry.get("agreed"):
                    agree += 1
                else:
                    disagree += 1
            except (ValueError, KeyError):
                continue
        total = agree + disagree
        if total > 0:
            rate = agree / total
            shadow_stats = {
                "total": total,
                "agree": agree,
                "disagree": disagree,
                "agreement_rate": round(rate, 4),
                "status": "ready" if rate >= 0.90 else "learning" if rate >= 0.70 else "early",
            }

    # Classifier availability — check both create-gpt models and local state
    classifier_available = False
    classifier_location = ""
    skills_dir = config.SKILL_DIR.parent
    model_candidates = [
        skills_dir / "create-gpt" / "models" / "taxonomy-assessor" / "gguf",
        skills_dir / "create-gpt" / "models" / "taxonomy-assessor" / "sft",
        config.STATE_DIR / "models" / "taxonomy-assessor",
    ]
    for model_path in model_candidates:
        if model_path.exists() and any(model_path.iterdir()):
            classifier_available = True
            classifier_location = str(model_path)
            break

    console.print(Panel("Cascade Status", title="Monitor Taxonomy"))

    status_table = Table(show_header=True, header_style="bold")
    status_table.add_column("Component", min_width=20)
    status_table.add_column("Value", min_width=15)
    status_table.add_column("Status")

    # Labels
    pct = (label_count / config.RETRAIN_LABEL_THRESHOLD * 100) if config.RETRAIN_LABEL_THRESHOLD > 0 else 0
    label_status = "ready" if label_count >= config.RETRAIN_LABEL_THRESHOLD else "accumulating"
    label_color = "green" if label_status == "ready" else "yellow"
    status_table.add_row(
        "Training Labels",
        f"{label_count} / {config.RETRAIN_LABEL_THRESHOLD} ({pct:.0f}%)",
        f"[{label_color}]{label_status}[/{label_color}]",
    )

    # Shadow
    shadow_color = {"ready": "green", "learning": "yellow", "early": "dim", "no_data": "dim"}
    status_table.add_row(
        "Shadow Agreement",
        f"{shadow_stats['agreement_rate']:.1%} ({shadow_stats['total']} samples)",
        f"[{shadow_color.get(shadow_stats['status'], 'dim')}]{shadow_stats['status']}[/{shadow_color.get(shadow_stats['status'], 'dim')}]",
    )

    # Classifier
    clf_color = "green" if classifier_available else "dim"
    clf_status = "deployed" if classifier_available else "not trained"
    clf_value = classifier_location if classifier_available else "pending labels"
    status_table.add_row(
        "Classifier (T1.5)",
        clf_value,
        f"[{clf_color}]{clf_status}[/{clf_color}]",
    )

    console.print(status_table)
