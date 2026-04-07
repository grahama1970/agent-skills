"""Review SPARTA conversation transcripts with full transparency.

Reads session JSONL files from sparta-stress-test results and renders
turn-by-turn conversation transcripts with entity gate decisions, QRA
citations, self-grade iterations, persona evaluation reasoning, and
student-vs-teacher comparison.

Inputs:
    - sessions_*.jsonl from sparta-stress-test/results/sessions/
    - shadow.jsonl from ~/.pi/assistant/ (for teacher grades)
    - shadow_deltas.jsonl from ~/.pi/assistant/ (for improvement tracking)

Outputs:
    - Rich terminal rendering of conversation transcripts
    - Optional markdown export for human annotation
    - JSON stream for automation (--json-stream)
    - Structured find/search for agent-human collaboration

Failure modes:
    - Missing session files: exits with clear error + path hint
    - Malformed JSONL lines: skips with warning, continues
    - Missing shadow data: shows "no teacher grade" instead of failing
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from loguru import logger
import typer
from dotenv import load_dotenv
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from models import (
    _DEFAULT_AUDIT_PATH,
    _DEFAULT_DELTA_PATH,
    _DEFAULT_SESSIONS_DIR,
    _DEFAULT_SHADOW_PATH,
    filter_sessions,
    find_latest_session_file,
    list_session_files,
    load_audit_index,
    load_delta_index,
    load_sessions,
    load_shadow_index,
)
from memory_integration import (
    learn_batch,
    memory_available,
    recall_conversations_context,
    semantic_find,
)
from models import grade_style
from renderers import (
    brief_session, brief_summary_table,
    build_heatmap_json, build_metrics_json, build_radar_json,
    console, render_session, render_summary_table, session_to_markdown,
)
from mermaid import session_to_mermaid, sessions_to_mermaid_batch

load_dotenv()

app = typer.Typer(help="Review SPARTA conversation transcripts and grading.")


#Shared helpers for file resolution


def _resolve_file(session_file: Optional[str], sessions_dir: str) -> Path:
    """Resolve session file path, falling back to latest."""
    if session_file:
        return Path(session_file)
    fpath = find_latest_session_file(Path(sessions_dir))
    if not fpath:
        console.print(f"[red]No session files found in {sessions_dir}[/red]")
        raise typer.Exit(1)
    return fpath


#CLI commands


@app.command("show")
def show(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    session_id: Optional[str] = typer.Option(
        None, "--id", "-i", help="Show specific session by ID"
    ),
    index: Optional[int] = typer.Option(
        None, "--index", "-n", help="Show session by index (1-based)"
    ),
    no_metadata: bool = typer.Option(
        False, "--no-metadata", help="Hide turn-level metadata"
    ),
    no_teacher: bool = typer.Option(
        False, "--no-teacher", help="Hide teacher comparison"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
    delta_path: str = typer.Option(
        str(_DEFAULT_DELTA_PATH), "--deltas", help="Shadow deltas path"
    ),
) -> None:
    """Show a conversation transcript with full debug detail."""
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    if not sessions:
        console.print(f"[red]No sessions in {fpath}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]File: {fpath.name} ({len(sessions)} sessions)[/dim]")

    shadow_index = load_shadow_index(Path(shadow_path))
    delta_index = load_delta_index(Path(delta_path))

    if session_id:
        matches = [s for s in sessions if s.get("session_id", "").startswith(session_id)]
        if not matches:
            console.print(f"[red]No session matching '{session_id}'[/red]")
            raise typer.Exit(1)
        targets = matches
    elif index is not None:
        if index < 1 or index > len(sessions):
            console.print(f"[red]Index {index} out of range (1-{len(sessions)})[/red]")
            raise typer.Exit(1)
        targets = [sessions[index - 1]]
    else:
        targets = sessions

    for s in targets:
        sid = s.get("session_id", "")
        render_session(
            s,
            shadow_entry=shadow_index.get(sid),
            delta_entry=delta_index.get(sid),
            show_metadata=not no_metadata,
            show_teacher=not no_teacher,
        )


@app.command("list")
def list_sessions_cmd(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
    delta_path: str = typer.Option(
        str(_DEFAULT_DELTA_PATH), "--deltas", help="Shadow deltas path"
    ),
    audit_path: Optional[str] = typer.Option(
        None, "--audit", help="/lie-detector audit JSON for verdict annotations"
    ),
) -> None:
    """List all sessions in a file with summary grades."""
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    if not sessions:
        console.print(f"[red]No sessions in {fpath}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]File: {fpath.name}[/dim]")

    shadow_index = load_shadow_index(Path(shadow_path))
    delta_index = load_delta_index(Path(delta_path))
    audit_index = load_audit_index(Path(audit_path)) if audit_path else None
    render_summary_table(sessions, shadow_index, delta_index, audit_index)


@app.command("compare")
def compare(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
) -> None:
    """Show only sessions where student and teacher DISAGREE."""
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    shadow_index = load_shadow_index(Path(shadow_path))

    disagreements = []
    for s in sessions:
        sid = s.get("session_id", "")
        shadow = shadow_index.get(sid)
        if shadow and not shadow.get("agreed", True):
            disagreements.append((s, shadow))

    if not disagreements:
        console.print("[green]No disagreements found.[/green]")
        return

    console.print(
        f"[bold red]{len(disagreements)} disagreements "
        f"out of {len(sessions)} sessions[/bold red]"
    )
    console.print()

    for s, shadow in disagreements:
        sid = s.get("session_id", "")
        persona = s.get("persona", "?")
        seed = s.get("seed_question", {})
        local_g = shadow.get("local_grade", "?")
        teacher_g = shadow.get("teacher_grade", "?")

        line = Text()
        line.append(f"{sid[:24]}", style="dim")
        line.append(f"  {persona}", style="cyan")
        line.append(f"  target={seed.get('target_control', '?')}", style="dim")
        line.append(f"  self=", style="dim")
        line.append(local_g, style=grade_style(local_g))
        line.append(f"  teacher=", style="dim")
        line.append(teacher_g, style=grade_style(teacher_g))
        console.print(line)


@app.command("export")
def export_md(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    output: str = typer.Option(
        None, "--output", "-o", help="Output markdown file (default: stdout)"
    ),
    session_id: Optional[str] = typer.Option(
        None, "--id", "-i", help="Export specific session by ID"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
    delta_path: str = typer.Option(
        str(_DEFAULT_DELTA_PATH), "--deltas", help="Shadow deltas path"
    ),
) -> None:
    """Export session(s) as annotated markdown for human review."""
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    shadow_index = load_shadow_index(Path(shadow_path))
    delta_index = load_delta_index(Path(delta_path))

    if session_id:
        sessions = [s for s in sessions if s.get("session_id", "").startswith(session_id)]

    parts: list[str] = []
    for s in sessions:
        sid = s.get("session_id", "")
        md = session_to_markdown(
            s,
            shadow_entry=shadow_index.get(sid),
            delta_entry=delta_index.get(sid),
        )
        parts.append(md)

    content = "\n\n---\n\n".join(parts)

    if output:
        Path(output).write_text(content)
        console.print(f"[green]Exported {len(sessions)} sessions to {output}[/green]")
    else:
        console.print(Markdown(content))


@app.command("files")
def list_files(
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
) -> None:
    """List available session files."""
    files = list_session_files(Path(sessions_dir))
    if not files:
        console.print(f"[red]No session files found in {sessions_dir}[/red]")
        raise typer.Exit(1)

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("File")
    table.add_column("Size", justify="right")
    table.add_column("Sessions", justify="right")

    for i, f in enumerate(files, 1):
        size = f.stat().st_size
        size_str = (
            f"{size / 1024:.1f} KB" if size < 1_000_000
            else f"{size / 1_000_000:.1f} MB"
        )
        count = sum(1 for line in f.read_text().splitlines() if line.strip())
        table.add_row(str(i), f.name, size_str, str(count))

    console.print(table)


@app.command("json-stream")
def json_stream(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
    delta_path: str = typer.Option(
        str(_DEFAULT_DELTA_PATH), "--deltas", help="Shadow deltas path"
    ),
) -> None:
    """Stream sessions as NDJSON with merged shadow/delta data."""
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    shadow_index = load_shadow_index(Path(shadow_path))
    delta_index = load_delta_index(Path(delta_path))

    for s in sessions:
        sid = s.get("session_id", "")
        record = {
            **s,
            "teacher": shadow_index.get(sid),
            "delta": delta_index.get(sid),
        }
        print(json.dumps(record, default=str))


#Find: structured + free-text search for agent-human collaboration


@app.command("find")
def find(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    grade: Optional[str] = typer.Option(
        None, "--grade", "-g", help="Filter by grade (A, B, C, F)"
    ),
    resolution: Optional[str] = typer.Option(
        None, "--resolution", "-r",
        help="Filter by resolution (resolved, partial, no_coverage, ambiguous)"
    ),
    evaluation: Optional[str] = typer.Option(
        None, "--eval", "-e",
        help="Filter by persona evaluation in any turn "
        "(satisfactory, incomplete, wrong, flaw_caught, flaw_missed). "
        "Prefix with ! to negate (e.g., !satisfactory)"
    ),
    first_eval: Optional[str] = typer.Option(
        None, "--first-eval",
        help="Filter by first persona evaluation only. Supports ! negation."
    ),
    min_composite: Optional[float] = typer.Option(
        None, "--min-composite",
        help="Minimum final composite score (0.0-1.0)"
    ),
    max_composite: Optional[float] = typer.Option(
        None, "--max-composite",
        help="Maximum final composite score (0.0-1.0)"
    ),
    difficulty: Optional[str] = typer.Option(
        None, "--difficulty", "-d",
        help="Filter by difficulty (simple, medium, complex, flawed, ambiguous)"
    ),
    persona: Optional[str] = typer.Option(
        None, "--persona", "-p", help="Filter by persona name"
    ),
    min_turns: Optional[int] = typer.Option(
        None, "--min-turns",
        help="Minimum number of turns (higher = more iteration)"
    ),
    text: Optional[str] = typer.Option(
        None, "--text", "-t",
        help="Free-text search across turn content, evaluations, rationales"
    ),
    semantic: Optional[str] = typer.Option(
        None, "--semantic", "-s",
        help="Semantic search via /memory recall (BM25 + embedding + multi-hop). "
        "Use for natural language queries like 'Brandon missed a fake control'"
    ),
    agree: Optional[bool] = typer.Option(
        None, "--agree/--disagree",
        help="Filter by teacher agreement"
    ),
    output_format: str = typer.Option(
        "brief", "--format", "-f",
        help="Output format: brief (markdown), show (Rich), count (just count)"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
    delta_path: str = typer.Option(
        str(_DEFAULT_DELTA_PATH), "--deltas", help="Shadow deltas path"
    ),
) -> None:
    """Find conversations matching structured filters + free-text search.

    All filters are AND-combined. Use --format show for Rich, brief for markdown, count for just the count.
    """
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    if not sessions:
        console.print(f"[red]No sessions in {fpath}[/red]")
        raise typer.Exit(1)

    shadow_index = load_shadow_index(Path(shadow_path))
    delta_index = load_delta_index(Path(delta_path))

    # Semantic search via /memory (pre-filter by session IDs)
    semantic_ids: set[str] | None = None
    if semantic:
        if not memory_available():
            console.print(
                "[yellow]Warning: /memory not available — "
                "falling back to --text search[/yellow]"
            )
            text = text or semantic  # fallback to bespoke text search
        else:
            semantic_ids_list = semantic_find(semantic, sessions, scope="sparta", k=20)
            if not semantic_ids_list:
                console.print(
                    f"[yellow]/memory found no matches for '{semantic}'. "
                    f"Falling back to --text search.[/yellow]"
                )
                text = text or semantic
            else:
                semantic_ids = set(semantic_ids_list)

    matches = filter_sessions(
        sessions,
        shadow_index,
        delta_index,
        grade=grade,
        resolution=resolution,
        evaluation=evaluation,
        first_eval=first_eval,
        min_composite=min_composite,
        max_composite=max_composite,
        difficulty=difficulty,
        persona=persona,
        min_turns=min_turns,
        text=text,
        agreed=agree,
    )

    # Intersect with semantic results if available
    if semantic_ids is not None:
        matches = [s for s in matches if s.get("session_id", "") in semantic_ids]
        if not matches:
            # Semantic found IDs but structured filters excluded them all —
            # show the semantic results without other filters as a fallback
            matches = [
                s for s in sessions
                if s.get("session_id", "") in semantic_ids
            ]
            if matches:
                console.print(
                    "[dim]Structured filters excluded all semantic matches. "
                    "Showing semantic results only.[/dim]"
                )

    if not matches:
        console.print("[yellow]No sessions match your filters.[/yellow]")
        raise typer.Exit(0)

    if output_format == "count":
        print(f"{len(matches)}/{len(sessions)} sessions match")
        return

    console.print(
        f"[bold]{len(matches)}/{len(sessions)} sessions match[/bold]"
    )
    console.print()

    if output_format == "show":
        for s in matches:
            sid = s.get("session_id", "")
            render_session(
                s,
                shadow_entry=shadow_index.get(sid),
                delta_entry=delta_index.get(sid),
            )
    else:
        # brief (default) — plain markdown for in-chat
        for s in matches:
            sid = s.get("session_id", "")
            print(brief_session(s, shadow_index.get(sid), delta_index.get(sid)))
            print("\n---\n")


#Flow: Mermaid conversation flow diagrams with inline grading


@app.command("flow")
def flow(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    session_id: Optional[str] = typer.Option(
        None, "--id", "-i", help="Show specific session by ID"
    ),
    index: Optional[int] = typer.Option(
        None, "--index", "-n", help="Show session by index (1-based)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o",
        help="Output markdown file with Mermaid diagrams (default: stdout)"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
    delta_path: str = typer.Option(
        str(_DEFAULT_DELTA_PATH), "--deltas", help="Shadow deltas path"
    ),
) -> None:
    """Generate Mermaid conversation flow diagrams with inline grading.

    Output is markdown with fenced mermaid blocks. Render in GitHub, VS Code, or mermaid.live.
    """
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    if not sessions:
        console.print(f"[red]No sessions in {fpath}[/red]")
        raise typer.Exit(1)

    shadow_index = load_shadow_index(Path(shadow_path))
    delta_index = load_delta_index(Path(delta_path))

    if session_id:
        sessions = [s for s in sessions if s.get("session_id", "").startswith(session_id)]
    elif index is not None:
        if index < 1 or index > len(sessions):
            console.print(f"[red]Index {index} out of range (1-{len(sessions)})[/red]")
            raise typer.Exit(1)
        sessions = [sessions[index - 1]]

    if not sessions:
        console.print("[yellow]No sessions match your selection.[/yellow]")
        raise typer.Exit(0)

    content = sessions_to_mermaid_batch(sessions, shadow_index, delta_index)

    if output:
        Path(output).write_text(content)
        console.print(
            f"[green]Wrote {len(sessions)} flow diagram(s) to {output}[/green]"
        )
        console.print(
            "[dim]Render with: VS Code Mermaid preview, GitHub markdown, "
            "or https://mermaid.live[/dim]"
        )
    else:
        print(content)


#Brief: plain markdown for in-chat display (no Rich)


@app.command("brief")
def brief_cmd(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    session_id: Optional[str] = typer.Option(
        None, "--id", "-i", help="Show specific session by ID"
    ),
    index: Optional[int] = typer.Option(
        None, "--index", "-n", help="Show session by index (1-based)"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
    delta_path: str = typer.Option(
        str(_DEFAULT_DELTA_PATH), "--deltas", help="Shadow deltas path"
    ),
) -> None:
    """Plain markdown for in-chat display (no Rich). Summary table or single session."""
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    if not sessions:
        print(f"No sessions in {fpath}", file=sys.stderr)
        raise typer.Exit(1)

    shadow_index = load_shadow_index(Path(shadow_path))
    delta_index = load_delta_index(Path(delta_path))

    if session_id or index is not None:
        if session_id:
            matches = [s for s in sessions if s.get("session_id", "").startswith(session_id)]
        elif index is not None:
            if index < 1 or index > len(sessions):
                print(f"Index {index} out of range (1-{len(sessions)})", file=sys.stderr)
                raise typer.Exit(1)
            matches = [sessions[index - 1]]
        else:
            matches = []

        for s in matches:
            sid = s.get("session_id", "")
            print(brief_session(s, shadow_index.get(sid), delta_index.get(sid)))
            print()
        return

    print(f"**{len(sessions)} sessions** from `{fpath.name}`\n")
    print(brief_summary_table(sessions, shadow_index))


#Data: JSON export for /create-figure and /analytics


@app.command("data")
def data_export(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    output_dir: str = typer.Option(
        ".", "--output-dir", "-o", help="Directory for JSON files"
    ),
    chart: str = typer.Option(
        "all", "--chart", "-c",
        help="Which chart: radar, heatmap, metrics, or all"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
) -> None:
    """Export JSON data files for /create-figure and /analytics."""
    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    if not sessions:
        print(f"No sessions in {fpath}", file=sys.stderr)
        raise typer.Exit(1)

    shadow_index = load_shadow_index(Path(shadow_path))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    if chart in ("radar", "all"):
        radar = build_radar_json(sessions)
        p = out / "radar.json"
        p.write_text(json.dumps(radar, indent=2))
        written.append(f"  radar.json ({len(radar.get('series', {}))} series)")

    if chart in ("heatmap", "all"):
        heatmap = build_heatmap_json(sessions)
        p = out / "heatmap.json"
        p.write_text(json.dumps(heatmap, indent=2))
        written.append(f"  heatmap.json ({len(heatmap)} rows)")

    if chart in ("metrics", "all"):
        metrics = build_metrics_json(sessions, shadow_index)
        for name, data in metrics.items():
            p = out / f"{name}.json"
            p.write_text(json.dumps(data, indent=2))
            written.append(f"  {name}.json")

    print(f"Exported from {fpath.name} ({len(sessions)} sessions):", file=sys.stderr)
    for w in written:
        print(w, file=sys.stderr)
    print("\nUsage with /create-figure:", file=sys.stderr)
    print("  ./run.sh radar --input radar.json --output radar.pdf", file=sys.stderr)
    print("  ./run.sh heatmap --input heatmap.json --output heatmap.pdf", file=sys.stderr)
    print("  ./run.sh metrics --input grade_distribution.json --type bar", file=sys.stderr)


#Ingest: learn sessions to /memory for semantic search


@app.command("ingest")
def ingest(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to sessions_*.jsonl (default: latest)"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    scope: str = typer.Option(
        "sparta", "--scope", help="Memory scope for storage"
    ),
) -> None:
    """Ingest session summaries into /memory for semantic search."""
    if not memory_available():
        console.print("[red]Error: /memory not available. Cannot ingest.[/red]")
        console.print("[dim]Ensure common.memory_client is importable.[/dim]")
        raise typer.Exit(1)

    fpath = _resolve_file(session_file, sessions_dir)
    sessions = load_sessions(fpath)
    if not sessions:
        console.print(f"[red]No sessions in {fpath}[/red]")
        raise typer.Exit(1)

    console.print(f"Ingesting {len(sessions)} sessions from {fpath.name}...")
    learned = learn_batch(sessions, scope=scope, tags=[fpath.stem])
    console.print(
        f"[green]Learned {len(learned)}/{len(sessions)} sessions to /memory "
        f"(scope={scope})[/green]"
    )


#Search: semantic search via /memory recall


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    session_file: Optional[str] = typer.Option(
        None, "--file", "-f", help="Path to sessions_*.jsonl for cross-reference"
    ),
    scope: str = typer.Option(
        "sparta", "--scope", help="Memory scope to search"
    ),
    k: int = typer.Option(
        5, "--k", "-k", help="Number of results"
    ),
    sessions_dir: str = typer.Option(
        str(_DEFAULT_SESSIONS_DIR), "--dir", help="Sessions directory"
    ),
    shadow_path: str = typer.Option(
        str(_DEFAULT_SHADOW_PATH), "--shadow", help="Shadow JSONL path"
    ),
    delta_path: str = typer.Option(
        str(_DEFAULT_DELTA_PATH), "--deltas", help="Shadow deltas path"
    ),
) -> None:
    """Semantic search for conversations via /memory recall (BM25 + embedding + multi-hop)."""
    if not memory_available():
        console.print("[red]Error: /memory not available.[/red]")
        console.print("[dim]Use 'find --text' as a fallback.[/dim]")
        raise typer.Exit(1)

    context = recall_conversations_context(query, scope=scope, k=k)
    if not context:
        console.print("[yellow]No results from /memory recall.[/yellow]")
        raise typer.Exit(0)

    # Try to cross-reference with actual session files for rich display
    try:
        fpath = _resolve_file(session_file, sessions_dir)
        sessions = load_sessions(fpath)
        shadow_index = load_shadow_index(Path(shadow_path))
        delta_index = load_delta_index(Path(delta_path))

        matched_ids = semantic_find(query, sessions, scope=scope, k=k)
        if matched_ids:
            console.print(
                f"[bold]{len(matched_ids)} sessions matched[/bold] "
                f"(via /memory recall)"
            )
            console.print()
            for s in sessions:
                sid = s.get("session_id", "")
                if sid in matched_ids:
                    print(brief_session(s, shadow_index.get(sid), delta_index.get(sid)))
                    print("\n---\n")
            return
    except typer.Exit:
        pass
    except Exception as exc:
        logger.debug(f"Could not cross-reference sessions: {exc}")

    # Fallback: show raw memory recall context
    console.print("[bold]Memory recall results:[/bold]")
    console.print()
    print(context)


#Entry point

if __name__ == "__main__":
    app()
