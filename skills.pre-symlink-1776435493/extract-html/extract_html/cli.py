"""cli - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Literal

import typer
from loguru import logger
from rich.console import Console

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

from extract_html.pipeline import run_pipeline
from extract_html.util import read_json_file, read_text_file, write_json_file, write_text_file

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

OutFormat = Literal["json", "md", "both"]
NormMode = Literal["off", "basic", "nfkc"]


@app.command()
def convert(
    html: Path = typer.Option(..., help="Path to local HTML file."),
    schema: Path = typer.Option(..., help="Path to JSON Schema file."),
    out: Path = typer.Option(Path("out.json"), help="Output JSON path."),
    out_format: OutFormat = typer.Option("json", help="Output format: json|md|both."),
    md_out: Path = typer.Option(Path("out.md"), help="Markdown output path (if md/both)."),
    ollama_base_url: str = typer.Option("http://localhost:11434", help="Ollama base URL."),
    model: str = typer.Option("schematron-3b", help="Ollama model name/tag."),
    timeout_s: float = typer.Option(120.0, help="Ollama HTTP timeout seconds."),
    max_attempts: int = typer.Option(3, help="Max self-improvement attempts (default 3)."),
    max_html_chars: int = typer.Option(220_000, help="Initial max chars of cleaned HTML."),
    normalize: NormMode = typer.Option("nfkc", help="Normalization: off|basic|nfkc."),
    include_sections: bool = typer.Option(True, help="Include deterministic section hierarchy as model context."),
    emit_sections: bool = typer.Option(False, help="Emit 'sections' into JSON output (only if schema permits)."),

    # NEW: deterministic tables
    extract_tables: bool = typer.Option(True, help="Extract HTML <table> elements deterministically (pandas.read_html)."),
    max_tables: int = typer.Option(20, help="Max tables to include."),

    # NEW: media -> text extraction
    extract_media_text: bool = typer.Option(True, help="Extract text from qualifying <img> media and include src+alt."),
    min_image_px: int = typer.Option(128 * 128, help="Min image area (width*height) to process."),
    max_image_px: int = typer.Option(4000 * 4000, help="Max image area (width*height) to process."),
    min_image_dim: int = typer.Option(200, help="Min width AND height to process (helps skip icons)."),
    fetch_remote_media: bool = typer.Option(False, help="Allow fetching http(s) images referenced by HTML."),
    vision_api_base: Optional[str] = typer.Option(None, help="OpenAI-compatible API base for vision (e.g. Chutes)."),
    vision_api_key: Optional[str] = typer.Option(None, help="API key for vision endpoint."),
    vision_model: str = typer.Option("gpt-4o-mini", help="Vision model name on your vision endpoint."),
    vision_concurrency: int = typer.Option(8, help="Concurrent vision calls (batch)."),

    debug_dir: Optional[Path] = typer.Option(None, help="If set, writes per-attempt debug artifacts here."),
) -> None:
    if max_attempts < 1:
        raise typer.BadParameter("--max-attempts must be >= 1")
    if not html.exists():
        raise typer.BadParameter(f"HTML file not found: {html}")
    if not schema.exists():
        raise typer.BadParameter(f"Schema file not found: {schema}")

    raw_html = read_text_file(html)
    schema_obj = read_json_file(schema)

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)

    monitor = TaskClient("extract-html", total=1) if TaskClient else None
    result = run_pipeline(
        html_path=html,
        raw_html=raw_html,
        json_schema=schema_obj,
        ollama_base_url=ollama_base_url,
        model=model,
        timeout_s=timeout_s,
        max_attempts=max_attempts,
        max_html_chars=max_html_chars,
        normalize_mode=normalize,
        include_sections=include_sections,
        emit_sections=emit_sections,
        extract_tables=extract_tables,
        max_tables=max_tables,
        extract_media_text=extract_media_text,
        min_image_px=min_image_px,
        max_image_px=max_image_px,
        min_image_dim=min_image_dim,
        fetch_remote_media=fetch_remote_media,
        vision_api_base=vision_api_base,
        vision_api_key=vision_api_key,
        vision_model=vision_model,
        vision_concurrency=vision_concurrency,
        debug_dir=debug_dir,
    )

    write_json_file(out, result)
    if monitor:
        monitor.update(item=str(html))
        monitor.finish()
    console.print(f"[green]Wrote[/green] {out}")

    if out_format in ("md", "both"):
        raise NotImplementedError("Markdown rendering not yet implemented in extract-html")


if __name__ == "__main__":
    app()
