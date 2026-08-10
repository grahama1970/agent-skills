"""Rich console output and JSON report generation for monitor-memory.

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

try:
    from loguru import logger
except ModuleNotFoundError:  # pragma: no cover - repo-root pytest fallback
    class _Logger:
        def info(self, *_args, **_kwargs) -> None:
            pass

        def warning(self, *_args, **_kwargs) -> None:
            pass

        def error(self, *_args, **_kwargs) -> None:
            pass

        def debug(self, *_args, **_kwargs) -> None:
            pass

    logger = _Logger()

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ModuleNotFoundError:  # pragma: no cover - repo-root pytest fallback
    class Console:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def print(self, *args, **kwargs) -> None:
            pass

        def print_json(self, data: str) -> None:
            print(data)

    class Panel:
        def __init__(self, value: str, *args, **kwargs) -> None:
            self.value = value

    class Table:
        def __init__(self, *args, **kwargs) -> None:
            self.rows = []

        def add_column(self, *args, **kwargs) -> None:
            pass

        def add_row(self, *args, **kwargs) -> None:
            self.rows.append(args)

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

    # Compute summary
    counts = {s: 0 for s in ProbeStatus}
    for r in results:
        counts[r.status] += 1

    total = len(results)
    health = "healthy"
    if counts[ProbeStatus.FAIL] > 0:
        health = "critical"
    elif counts[ProbeStatus.WARN] > 0:
        health = "warning"

    # Rich output
    if not json_output:
        _render_table(results, health, counts, total)
    else:
        _render_json(results, health, counts, total)

    # Persist latest report
    _save_state(results, health, counts, total)

    # Generate health report with mermaid charts + store in memory
    generate_health_report(results, health, counts)


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
        title="Monitor Memory",
        subtitle=time.strftime("%Y-%m-%d %H:%M"),
    ))

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Probe", min_width=22)
    table.add_column("Tier", justify="center", width=4)
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
    health_score = 1.0 if health == "healthy" else 0.5 if health == "warning" else 0.0
    payload = {
        "health": health,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {s.value: c for s, c in counts.items()},
        "total": total,
        "figure_data": {
            "bar": {
                "metrics": {
                    "pass": counts[ProbeStatus.PASS],
                    "warn": counts[ProbeStatus.WARN],
                    "fail": counts[ProbeStatus.FAIL],
                    "skip": counts[ProbeStatus.SKIP],
                    "fixed": counts[ProbeStatus.FIXED],
                    "health_score": health_score,
                }
            }
        },
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
    health_score = 1.0 if health == "healthy" else 0.5 if health == "warning" else 0.0
    payload = {
        "health": health,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {s.value: c for s, c in counts.items()},
        "total": total,
        "figure_data": {
            "bar": {
                "metrics": {
                    "pass": counts[ProbeStatus.PASS],
                    "warn": counts[ProbeStatus.WARN],
                    "fail": counts[ProbeStatus.FAIL],
                    "skip": counts[ProbeStatus.SKIP],
                    "fixed": counts[ProbeStatus.FIXED],
                    "health_score": health_score,
                }
            }
        },
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
    try:
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, state_file)
    except OSError as e:
        logger.error("Failed to save state: {}", e)


def generate_health_report(results: list[ProbeResult], health: str, counts: dict) -> Path | None:
    """Generate REPORT.md with mermaid charts and store snapshot in /memory.

    Runs the test-lab report generator for full database health, then
    stores a lesson in memory via the daemon for historical tracking.
    """
    import subprocess

    report_dir = config.STATE_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"health_{ts}.md"

    # 1. Run the test-lab health report generator
    report_script = Path.home() / ".claude/skills/test-lab/tests/memory-database/report_memory_health.sh"
    if report_script.exists():
        try:
            result = subprocess.run(
                [str(report_script), str(report_path)],
                capture_output=True, text=True, timeout=120,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0:
                logger.info("Health report generated: {}", report_path)
            else:
                logger.warning("Report script exited {}: {}", result.returncode, result.stderr[:200])
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error("Report generation failed: {}", e)
            return None
    else:
        logger.warning("Report script not found: {}", report_script)
        return None

    # 2. Symlink as latest
    latest = report_dir / "REPORT.md"
    latest.unlink(missing_ok=True)
    try:
        latest.symlink_to(report_path)
    except OSError:
        pass

    # 3. Store health snapshot in memory via daemon
    _store_health_in_memory(health, counts, report_path, results=results)

    return report_path


def _collect_audit_metadata() -> dict:
    """Collect rich metadata from daemon /db/audit and embedding service /info."""
    metadata = {}
    try:
        import httpx
    except ImportError:
        return metadata

    # 1. Database audit via daemon
    daemon_sock = f"/run/user/{os.getuid()}/embry/memory.sock"
    if Path(daemon_sock).exists():
        try:
            transport = httpx.HTTPTransport(uds=daemon_sock)
            client = httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)
            resp = client.get("/db/audit")
            if resp.status_code == 200:
                audit = resp.json()
                # Collection counts
                cols = audit.get("collections", {})
                metadata["collections"] = {
                    name: info.get("count", 0) for name, info in cols.items()
                }
                # Embedding coverage
                emb_cov = audit.get("embedding_coverage", {})
                metadata["embedding_coverage"] = {
                    name: {
                        "total": info.get("total", 0),
                        "embedded": info.get("embedded", 0),
                        "missing": info.get("missing", 0),
                        "coverage_pct": round(info.get("embedded", 0) / max(info.get("total", 1), 1) * 100, 2),
                    }
                    for name, info in emb_cov.items()
                }
                # Vector indexes
                metadata["vector_indexes"] = audit.get("vector_indexes", {})
                # Views
                metadata["views"] = list(audit.get("views", {}).keys()) if isinstance(audit.get("views"), dict) else []
        except Exception as e:
            logger.debug("Audit metadata collection failed: {}", e)

    # 2. Embedding service info
    emb_url = config.EMBEDDING_SERVICE_URL
    try:
        resp = httpx.get(f"{emb_url}/info", timeout=5.0)
        if resp.status_code == 200:
            info = resp.json()
            metadata["embedding_service"] = {
                "model": info.get("model", "unknown"),
                "device": info.get("device", "unknown"),
                "dimensions": info.get("dimensions", 0),
                "uptime_s": info.get("uptime_s", 0),
                "requests_served": info.get("requests_served", 0),
            }
    except Exception as e:
        logger.debug("Embedding service info failed: {}", e)

    return metadata


def _store_health_in_memory(
    health: str,
    counts: dict,
    report_path: Path,
    results: list[ProbeResult] | None = None,
) -> None:
    """Store health snapshot as a lesson via the memory daemon.

    Includes rich metadata: ISO datetime, collection counts, embedding
    coverage, GPU info, and per-probe status breakdown.
    """
    try:
        import httpx
    except ImportError:
        logger.debug("httpx not available, skipping memory store")
        return

    daemon_sock = f"/run/user/{os.getuid()}/embry/memory.sock"
    if not Path(daemon_sock).exists():
        logger.debug("Daemon socket not found, skipping memory store")
        return

    iso_ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    ts_human = time.strftime("%Y-%m-%d %H:%M")
    pass_count = counts.get(ProbeStatus.PASS, 0)
    fail_count = counts.get(ProbeStatus.FAIL, 0)
    warn_count = counts.get(ProbeStatus.WARN, 0)
    fixed_count = counts.get(ProbeStatus.FIXED, 0)
    skip_count = counts.get(ProbeStatus.SKIP, 0)
    total = sum(counts.values())

    # Collect infrastructure metadata
    meta = _collect_audit_metadata()

    # Per-probe breakdown
    probe_details = []
    if results:
        for r in results:
            probe_details.append({
                "probe_id": r.probe_id,
                "name": r.name,
                "tier": r.tier,
                "status": r.status.value,
                "message": r.message,
                "auto_fixable": r.auto_fixable,
                "fix_applied": r.fix_applied,
            })

    # Build rich solution with structured metadata
    solution_parts = [
        f"Health: {health.upper()}.",
        f"Pass: {pass_count}, Fail: {fail_count}, Warn: {warn_count}, Fixed: {fixed_count}, Skip: {skip_count} (Total: {total}).",
        f"Report: {report_path}.",
    ]

    # Add collection sizes if available
    if meta.get("collections"):
        col_summary = ", ".join(
            f"{name}: {cnt:,}" for name, cnt in sorted(meta["collections"].items())
        )
        solution_parts.append(f"Collections: {col_summary}.")

    # Add embedding coverage if available
    if meta.get("embedding_coverage"):
        emb_summary = ", ".join(
            f"{name}: {info['coverage_pct']}%" for name, info in meta["embedding_coverage"].items()
        )
        solution_parts.append(f"Embedding coverage: {emb_summary}.")

    # Add GPU info if available
    if meta.get("embedding_service"):
        svc = meta["embedding_service"]
        solution_parts.append(
            f"Embedding service: {svc['model']} on {svc['device']}, {svc['dimensions']}d, "
            f"uptime {svc['uptime_s']}s, {svc['requests_served']} requests."
        )

    # Add failed/warned probe names
    if results:
        failed = [r.name for r in results if r.status == ProbeStatus.FAIL]
        warned = [r.name for r in results if r.status == ProbeStatus.WARN]
        if failed:
            solution_parts.append(f"Failed probes: {', '.join(failed)}.")
        if warned:
            solution_parts.append(f"Warning probes: {', '.join(warned)}.")

    problem = f"Memory database health check {ts_human}: {health.upper()} ({pass_count}/{total} pass, {fail_count} fail, {warn_count} warn)"
    solution = " ".join(solution_parts)

    # Build metadata dict for the lesson
    lesson_metadata = {
        "datetime": iso_ts,
        "health": health,
        "health_score": 1.0 if health == "healthy" else 0.5 if health == "warning" else 0.0,
        "probe_counts": {
            "pass": pass_count,
            "fail": fail_count,
            "warn": warn_count,
            "fixed": fixed_count,
            "skip": skip_count,
            "total": total,
        },
        "report_path": str(report_path),
    }
    if meta.get("collections"):
        lesson_metadata["collections"] = meta["collections"]
    if meta.get("embedding_coverage"):
        lesson_metadata["embedding_coverage"] = meta["embedding_coverage"]
    if meta.get("embedding_service"):
        lesson_metadata["embedding_service"] = meta["embedding_service"]
    if meta.get("vector_indexes"):
        lesson_metadata["vector_indexes"] = meta["vector_indexes"]
    if meta.get("views"):
        lesson_metadata["views"] = meta["views"]
    if probe_details:
        lesson_metadata["probes"] = probe_details

    try:
        transport = httpx.HTTPTransport(uds=daemon_sock)
        client = httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)
        resp = client.post("/learn", json={
            "problem": problem,
            "solution": solution,
            "scope": "operational",
            "tags": ["health_check", "monitor_memory", "database_health", health],
            "metadata": lesson_metadata,
        })
        if resp.status_code == 200:
            logger.info("Health snapshot stored in memory with {} metadata fields", len(lesson_metadata))
        else:
            logger.warning("Failed to store health snapshot: {}", resp.status_code)
    except Exception as e:
        logger.warning("Memory store failed (non-fatal): {}", e)


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
        title="Monitor Memory Dashboard",
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
        probe_table.add_column("Probe", min_width=22)
        probe_table.add_column("Tier", justify="center", width=4)
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
