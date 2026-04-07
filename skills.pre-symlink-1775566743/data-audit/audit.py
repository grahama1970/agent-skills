#!/usr/bin/env python3
"""SPARTA Data Audit — completeness + per-entity gap reporting.

Reports:
    1. Framework-level coverage summary (original)
    2. Zero-coverage entities by category (NEW)
    3. SPARTA tactic distribution (NEW)
    4. High-priority gaps: entities with relationships but 0 QRAs (NEW)
"""
import datetime
import os
import typer
import sys
import duckdb
from pathlib import Path
from rich.console import Console
from rich.table import Table
from loguru import logger

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Config
DB_PATH = Path(os.environ.get("SPARTA_DB_PATH", str(Path.home() / "workspace/experiments/sparta/data/runs/run-recovery-verify/sparta.duckdb")))

app = typer.Typer(help="Run SPARTA Data Audit")
console = Console()


def _get_conn():
    if not DB_PATH.exists():
        console.print(f"[bold red]Error:[/bold red] DB not found at {DB_PATH}")
        sys.exit(1)
    return duckdb.connect(str(DB_PATH), read_only=True)


@app.command()
def summary(
    run_id: str = typer.Option(None, help="Result Run ID"),
):
    """Framework-level coverage summary (original audit)."""
    conn = _get_conn()

    query = """
    WITH url_stats AS (
        SELECT c.control_type, COUNT(DISTINCT c.control_id) as covered_count
        FROM controls c
        JOIN control_urls cu ON c.control_id = cu.control_id
        GROUP BY c.control_type
    ),
    know_stats AS (
        SELECT c.control_type, COUNT(DISTINCT c.control_id) as covered_count
        FROM controls c
        JOIN control_urls cu ON c.control_id = cu.control_id
        JOIN knowledge_chunks kc ON cu.url_id = kc.url_id
        GROUP BY c.control_type
    ),
    qra_stats AS (
        SELECT c.control_type, COUNT(DISTINCT c.control_id) as covered_count
        FROM controls c
        JOIN qra q ON c.control_id = q.control_id
        GROUP BY c.control_type
    )
    SELECT
        c.control_type,
        COUNT(DISTINCT c.control_id) as total,
        COALESCE(MAX(us.covered_count), 0) as with_urls,
        COALESCE(MAX(ks.covered_count), 0) as with_knowledge,
        COALESCE(MAX(qs.covered_count), 0) as with_qra
    FROM controls c
    LEFT JOIN url_stats us ON c.control_type = us.control_type
    LEFT JOIN know_stats ks ON c.control_type = ks.control_type
    LEFT JOIN qra_stats qs ON c.control_type = qs.control_type
    GROUP BY c.control_type
    ORDER BY with_qra ASC, total DESC
    """

    try:
        results = conn.execute(query).fetchall()

        table = Table(title=f"SPARTA Data Completeness ({datetime.datetime.now():%Y-%m-%d %H:%M})")
        table.add_column("Control Type", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("URLs", justify="right")
        table.add_column("Know.", justify="right")
        table.add_column("QRA", justify="right")
        table.add_column("Status", justify="right")

        for ctype, total, urls, know, qra in results:
            url_pct = f"{urls/total*100:.1f}%" if total > 0 else "0%"
            know_pct = f"{know/total*100:.1f}%" if total > 0 else "0%"
            qra_pct = f"{qra/total*100:.1f}%" if total > 0 else "0%"
            status = "🔴" if qra == 0 else ("🟡" if qra < total else "🟢")

            table.add_row(
                ctype, str(total),
                f"{urls} ({url_pct})", f"{know} ({know_pct})",
                f"{qra} ({qra_pct})", status,
            )

        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Audit failed:[/bold red] {e}")
        sys.exit(1)
    finally:
        conn.close()


@app.command()
def gaps(
    framework: str = typer.Option(None, "--framework", "-f", help="Filter by control_type"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max entities to show"),
    priority: bool = typer.Option(False, "--priority", "-p",
        help="Sort by relationship count (highest-impact gaps first)"),
):
    """List entities with ZERO QRAs — the actual coverage gaps.

    Use --priority to see entities that have relationships but no QRAs,
    indicating the pipeline skipped them rather than them being irrelevant.
    """
    conn = _get_conn()

    if priority:
        # Entities with relationships but 0 QRAs = pipeline missed them
        query = """
        WITH rel_counts AS (
            SELECT source_control_id as control_id, COUNT(*) as rel_count
            FROM relationships
            GROUP BY source_control_id
            UNION ALL
            SELECT target_control_id, COUNT(*)
            FROM relationships
            GROUP BY target_control_id
        ),
        agg_rels AS (
            SELECT control_id, SUM(rel_count) as total_rels
            FROM rel_counts
            GROUP BY control_id
        ),
        qra_controls AS (
            SELECT DISTINCT control_id FROM qra
        )
        SELECT c.control_id, c.name, c.control_type,
               COALESCE(ar.total_rels, 0) as relationships
        FROM controls c
        LEFT JOIN qra_controls qc ON c.control_id = qc.control_id
        LEFT JOIN agg_rels ar ON c.control_id = ar.control_id
        WHERE qc.control_id IS NULL
          AND COALESCE(ar.total_rels, 0) > 0
        """
        if framework:
            query += f" AND c.control_type = '{framework}'"
        query += f" ORDER BY relationships DESC LIMIT {limit}"
    else:
        # All entities with 0 QRAs
        query = """
        WITH qra_controls AS (
            SELECT DISTINCT control_id FROM qra
        )
        SELECT c.control_id, c.name, c.control_type, 0 as relationships
        FROM controls c
        LEFT JOIN qra_controls qc ON c.control_id = qc.control_id
        WHERE qc.control_id IS NULL
        """
        if framework:
            query += f" AND c.control_type = '{framework}'"
        query += f" ORDER BY c.control_type, c.control_id LIMIT {limit}"

    try:
        results = conn.execute(query).fetchall()

        title = "High-Priority Coverage Gaps" if priority else "Zero-QRA Entities"
        if framework:
            title += f" (framework={framework})"

        table = Table(title=f"{title} — {len(results)} shown")
        table.add_column("Control ID", style="cyan")
        table.add_column("Name", style="white", max_width=50)
        table.add_column("Type", style="yellow")
        if priority:
            table.add_column("Relationships", justify="right", style="red")

        for cid, name, ctype, rels in results:
            row = [cid, name or "", ctype or ""]
            if priority:
                row.append(str(rels))
            table.add_row(*row)

        console.print(table)

        # Summary
        total_gaps = conn.execute("""
            WITH qra_controls AS (SELECT DISTINCT control_id FROM qra)
            SELECT COUNT(*) FROM controls c
            LEFT JOIN qra_controls qc ON c.control_id = qc.control_id
            WHERE qc.control_id IS NULL
        """).fetchone()[0]
        total_controls = conn.execute("SELECT COUNT(DISTINCT control_id) FROM controls").fetchone()[0]
        console.print(
            f"\n[bold]Total gaps:[/bold] {total_gaps}/{total_controls} entities "
            f"({total_gaps/max(1,total_controls)*100:.1f}%) have zero QRAs"
        )

    except Exception as e:
        console.print(f"[bold red]Query failed:[/bold red] {e}")
        sys.exit(1)
    finally:
        conn.close()


@app.command()
def tactics():
    """Show QRA distribution across SPARTA tactic categories."""
    conn = _get_conn()

    query = """
    SELECT
        CASE
            WHEN control_id LIKE 'REC-%' THEN 'REC (Reconnaissance)'
            WHEN control_id LIKE 'RD-%' THEN 'RD (Resource Dev)'
            WHEN control_id LIKE 'IA-%' THEN 'IA (Initial Access)'
            WHEN control_id LIKE 'EX-%' THEN 'EX (Execution)'
            WHEN control_id LIKE 'PER-%' THEN 'PER (Persistence)'
            WHEN control_id LIKE 'DE-%' THEN 'DE (Defense Evasion)'
            WHEN control_id LIKE 'LM-%' THEN 'LM (Lateral Movement)'
            WHEN control_id LIKE 'EXF-%' THEN 'EXF (Exfiltration)'
            WHEN control_id LIKE 'IMP-%' THEN 'IMP (Impact)'
            WHEN control_id LIKE 'SV-%' THEN 'SV (Spacecraft Vuln)'
            WHEN control_id LIKE 'CWE-%' THEN 'CWE'
            WHEN control_id LIKE 'T1%' OR control_id LIKE 'T0%' THEN 'ATT&CK'
            WHEN control_id LIKE 'ESA-%' THEN 'ESA'
            WHEN control_id LIKE 'D3%' OR control_id LIKE 'd3f:%' THEN 'D3FEND'
            ELSE 'NIST/Other'
        END as category,
        COUNT(*) as qra_count,
        COUNT(DISTINCT control_id) as entities
    FROM qra
    GROUP BY category
    ORDER BY qra_count DESC
    """

    try:
        results = conn.execute(query).fetchall()

        table = Table(title="QRA Distribution by Tactic Category")
        table.add_column("Category", style="cyan")
        table.add_column("QRAs", justify="right")
        table.add_column("Entities", justify="right")
        table.add_column("Avg QRAs/Entity", justify="right")

        for cat, qra_count, entities in results:
            avg = round(qra_count / max(1, entities), 1)
            table.add_row(cat, str(qra_count), str(entities), str(avg))

        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Query failed:[/bold red] {e}")
        sys.exit(1)
    finally:
        conn.close()


@app.command()
def main(run_id: str = typer.Option(None, help="Result Run ID")):
    """Run full audit: summary + gap count."""
    monitor = TaskClient("data-audit", total=3) if TaskClient else None

    summary(run_id)
    if monitor:
        monitor.update(item="summary")
    console.print()

    conn = _get_conn()
    try:
        total_gaps = conn.execute("""
            WITH qra_controls AS (SELECT DISTINCT control_id FROM qra)
            SELECT COUNT(*) FROM controls c
            LEFT JOIN qra_controls qc ON c.control_id = qc.control_id
            WHERE qc.control_id IS NULL
        """).fetchone()[0]
        if monitor:
            monitor.update(item="gap_count")
        if total_gaps > 0:
            console.print(
                f"[bold yellow]⚠ {total_gaps} entities have zero QRAs.[/bold yellow] "
                f"Run [cyan]audit.py gaps --priority[/cyan] for details."
            )
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    finally:
        conn.close()

    if monitor:
        monitor.update(item="complete")
        monitor.finish()


if __name__ == "__main__":
    app()
