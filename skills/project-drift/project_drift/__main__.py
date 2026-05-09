"""Typer CLI for project-drift."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .cleaner import clean_transcript_entries
from .knowledge import load_project_knowledge
from .llm import LLMExecutionError, call_openai_compatible
from .prompt import build_prompt_payload
from .schema import ProjectDriftReport, report_json_schema
from .transcript_extract import discover_transcripts, read_jsonl, read_many
from .utils import get_working_dir, parse_timestamp, safe_read_json, safe_write_json

app = typer.Typer(help="Conservative project knowledge drift auditor.")
console = Console()

DEFAULT_MODEL = "gpt-5.5-thinking"


def _resolve_project_root(project_root: Optional[Path]) -> Path:
    return (project_root or get_working_dir()).resolve()


def _auto_since_from_knowledge(knowledge: dict) -> str | None:
    raw = knowledge.get("last_updated")
    if not raw:
        return None
    # PROJECT_KNOWLEDGE often stores "YYYY-MM-DD HH:MM by agent".
    candidate = str(raw).split(" by ")[0].strip()
    dt = parse_timestamp(candidate.replace(" ", "T", 1)) or parse_timestamp(candidate)
    return dt.isoformat() if dt else None


@app.command("list-transcripts")
def list_transcripts(
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root; defaults to caller cwd."),
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum files to list."),
) -> None:
    """List likely transcript JSONL files."""
    root = _resolve_project_root(project_root)
    paths = discover_transcripts(root, limit=limit)
    table = Table(title=f"Likely transcripts for {root}")
    table.add_column("#", justify="right")
    table.add_column("Path")
    table.add_column("Size")
    for idx, path in enumerate(paths, start=1):
        table.add_row(str(idx), str(path), str(path.stat().st_size if path.exists() else 0))
    console.print(table)


@app.command("clean-transcript")
def clean_transcript(
    transcript: Path = typer.Option(..., "--transcript", "-t", exists=True, help="Transcript JSONL file."),
    out: Path = typer.Option(..., "--out", "-o", help="Output cleaned JSON path."),
    since: Optional[str] = typer.Option(None, "--since", help="Only include entries at or after this timestamp."),
    tail: Optional[int] = typer.Option(None, "--tail", min=1, help="Only scan last N lines."),
    include_routine: bool = typer.Option(False, "--include-routine", help="Include routine read/grep/list observations."),
    max_events: int = typer.Option(80, "--max-events", min=1, help="Maximum observations to keep."),
) -> None:
    """Extract and clean transcript entries into compact evidence JSON."""
    entries = read_jsonl(transcript, since=since, tail=tail)
    cleaned = clean_transcript_entries(entries, max_events=max_events, include_routine=include_routine)
    cleaned["transcript_paths"] = [str(transcript)]
    cleaned["since"] = since
    safe_write_json(out, cleaned)
    console.print(f"[green]Wrote cleaned evidence:[/green] {out}")
    console.print(f"Observations: {cleaned['observation_count']} | routine ignored: {cleaned['routine_successful_tool_calls']}")


@app.command("build-prompt")
def build_prompt(
    cleaned: Path = typer.Option(..., "--cleaned", exists=True, help="Cleaned evidence JSON."),
    out: Path = typer.Option(..., "--out", "-o", help="Output prompt payload JSON."),
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root; defaults to caller cwd."),
    knowledge_file: Optional[Path] = typer.Option(None, "--knowledge-file", help="PROJECT_KNOWLEDGE.md path."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Model name for payload."),
    since: Optional[str] = typer.Option(None, "--since", help="Window start label."),
    trigger: str = typer.Option("manual build-prompt", "--trigger", help="Trigger label."),
) -> None:
    """Build an OpenAI-compatible prompt payload from cleaned evidence and project knowledge."""
    root = _resolve_project_root(project_root)
    knowledge = load_project_knowledge(root, knowledge_file=knowledge_file)
    cleaned_data = safe_read_json(cleaned)
    payload = build_prompt_payload(
        model=model,
        knowledge=knowledge,
        cleaned=cleaned_data,
        source="cleaned_transcript",
        since=since or cleaned_data.get("since"),
        trigger=trigger,
    )
    safe_write_json(out, payload)
    console.print(f"[green]Wrote prompt payload:[/green] {out}")


@app.command("scan")
def scan(
    transcript: Optional[Path] = typer.Option(None, "--transcript", "-t", exists=True, help="Transcript JSONL file. If omitted, newest discovered transcript is used."),
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root; defaults to caller cwd."),
    knowledge_file: Optional[Path] = typer.Option(None, "--knowledge-file", help="PROJECT_KNOWLEDGE.md path."),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", help="Output directory; default .project-drift/latest."),
    since: str = typer.Option("auto", "--since", help="Timestamp, 'auto' for project_knowledge last update, or 'none'."),
    tail: Optional[int] = typer.Option(800, "--tail", min=1, help="Only scan last N lines per transcript."),
    include_routine: bool = typer.Option(False, "--include-routine", help="Include routine observations."),
    max_events: int = typer.Option(80, "--max-events", min=1, help="Maximum observations to keep."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Model for prompt payload."),
    execute: bool = typer.Option(False, "--execute/--no-execute", help="Call OpenAI-compatible endpoint and write drift_report.json."),
    llm_base_url: Optional[str] = typer.Option(None, "--llm-base-url", help="OpenAI-compatible base URL."),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Optional API key."),
    timeout: float = typer.Option(60.0, "--timeout", min=1.0, help="LLM HTTP timeout seconds."),
    trigger: str = typer.Option("manual scan", "--trigger", help="Trigger label for prompt payload."),
) -> None:
    """Run the full extract -> clean -> prompt -> optional report workflow."""
    root = _resolve_project_root(project_root)
    output = out_dir or (root / ".project-drift" / "latest")
    output.mkdir(parents=True, exist_ok=True)

    knowledge = load_project_knowledge(root, knowledge_file=knowledge_file)
    if since == "auto":
        since_value = _auto_since_from_knowledge(knowledge)
    elif since == "none":
        since_value = None
    else:
        since_value = since

    transcript_paths: list[Path]
    if transcript:
        transcript_paths = [transcript]
    else:
        transcript_paths = discover_transcripts(root, limit=1)
        if not transcript_paths:
            raise typer.BadParameter("No transcript supplied and no transcript JSONL discovered. Pass --transcript.")

    entries = read_many(transcript_paths, since=since_value, tail=tail)
    cleaned = clean_transcript_entries(entries, max_events=max_events, include_routine=include_routine)
    cleaned["transcript_paths"] = [str(p) for p in transcript_paths]
    cleaned["since"] = since_value

    prompt_payload = build_prompt_payload(
        model=model,
        knowledge=knowledge,
        cleaned=cleaned,
        source="transcript",
        since=since_value,
        trigger=trigger,
    )

    cleaned_path = output / "cleaned_transcript.json"
    knowledge_path = output / "project_knowledge_claims.json"
    payload_path = output / "prompt_payload.json"
    summary_path = output / "scan_summary.json"

    safe_write_json(cleaned_path, cleaned)
    safe_write_json(knowledge_path, knowledge)
    safe_write_json(payload_path, prompt_payload)

    summary = {
        "project_root": str(root),
        "out_dir": str(output),
        "transcripts": [str(p) for p in transcript_paths],
        "since": since_value,
        "knowledge_found": knowledge.get("found"),
        "knowledge_claim_count": knowledge.get("claim_count", len(knowledge.get("claims", []))),
        "observations": cleaned.get("observation_count"),
        "routine_successful_tool_calls": cleaned.get("routine_successful_tool_calls"),
        "execute": execute,
    }

    if execute:
        try:
            report_data = call_openai_compatible(prompt_payload, base_url=llm_base_url, api_key=api_key, timeout=timeout)
            report = ProjectDriftReport.model_validate(report_data)
            report_path = output / "drift_report.json"
            safe_write_json(report_path, report.model_dump(mode="json"))
            summary["drift_report"] = str(report_path)
            summary["verdict"] = report.verdict.value
            summary["severity"] = report.severity.value
            console.print(f"[green]Wrote drift report:[/green] {report_path}")
        except (LLMExecutionError, ValidationError) as exc:
            summary["llm_error"] = str(exc)
            safe_write_json(summary_path, summary)
            console.print(f"[red]LLM execution failed:[/red] {exc}")
            console.print(f"Prompt payload is available at {payload_path}")
            raise typer.Exit(2)

    safe_write_json(summary_path, summary)
    console.print(f"[green]Wrote scan artifacts:[/green] {output}")
    console.print(f"Prompt payload: {payload_path}")
    console.print(f"Observations: {cleaned.get('observation_count')} | routine ignored: {cleaned.get('routine_successful_tool_calls')}")
    if not execute:
        console.print("[yellow]No LLM call was made. Review or send prompt_payload.json through /scillm or rerun with --execute.[/yellow]")


@app.command("validate-report")
def validate_report(report: Path = typer.Argument(..., exists=True, help="drift_report.json path")) -> None:
    """Validate a drift report JSON file against the schema."""
    data = safe_read_json(report)
    parsed = ProjectDriftReport.model_validate(data)
    console.print(f"[green]Valid drift report[/green]: verdict={parsed.verdict.value} severity={parsed.severity.value} candidates={len(parsed.candidates)}")


@app.command("schema")
def schema(out: Optional[Path] = typer.Option(None, "--out", help="Optional output path.")) -> None:
    """Print or write the drift report JSON schema."""
    data = report_json_schema()
    if out:
        safe_write_json(out, data)
        console.print(f"[green]Wrote schema:[/green] {out}")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
