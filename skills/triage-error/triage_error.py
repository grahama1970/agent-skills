"""triage-error: turn an ambiguous pipeline error into an unambiguous code.

Classifies a raw error / lane receipt from any layer of the model-calling
pipeline (/ask -> /tau -> {/surf | /scillm}) against a canonical catalog and
returns ONE unambiguous {code, cause, next_command}. When the signal is
ambiguous (no catalog match), it mints a deterministic code and can COMPOSE:

  - /ticket   draft (default) or file (--file) a bug ticket with the receipt,
  - /agentic-evals  scaffold a reproduction fixture (--scaffold-eval),
  - /memory   store the new code + resolution (memory/run.sh learn).

Guardrails (operator rules): filing a ticket publishes a GitHub issue, so it is
GATED behind --file (default drafts to stdout). ArangoDB is never touched
directly -- memory goes through memory/run.sh only.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import typer
from loguru import logger

from classifier import classify, load_catalog, _normalize, _mint_code, _first_error_line  # noqa: F401

app = typer.Typer(add_completion=False, help="Classify ambiguous pipeline errors into unambiguous codes.")

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "failure_codes.json"
SKILLS_ROOT = HERE.parent
TICKET_RUN = SKILLS_ROOT / "ticket" / "run.sh"
EVALS_RUN = SKILLS_ROOT / "agentic-evals" / "run.sh"
MEMORY_RUN = SKILLS_ROOT / "memory" / "run.sh"







def _read_signal(text: str | None, receipt: Path | None) -> str:
    if text:
        return text
    if receipt and receipt.is_file():
        return receipt.read_text(encoding="utf-8", errors="replace")
    return ""


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _draft_or_file_ticket(report: dict[str, Any], target: str, receipt_path: str, do_file: bool) -> dict[str, Any]:
    if not TICKET_RUN.exists():
        return {"ok": False, "error": "ticket skill not found"}
    args = [
        str(TICKET_RUN), "bug",
        "--target", target,
        "--observed", f"[{report['code']}] {report['cause']}",
        "--expected", "The pipeline surfaces this unambiguous code + cause + a deterministic next command, not a generic error.",
        "--repro", f"triage-error classify on receipt {receipt_path} -> code {report['code']}",
        "--proof", "A triage-error agentic-eval case that fails until the layer emits/normalizes this code.",
        "--label", "triage-error",
    ]
    if not do_file:
        args.append("--json")  # draft only; do NOT publish a GitHub issue
    proc = _run(args)
    return {"ok": proc.returncode == 0, "filed": do_file, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-500:]}


def _store_memory(report: dict[str, Any]) -> dict[str, Any]:
    if not MEMORY_RUN.exists():
        return {"ok": False, "error": "memory skill not found"}
    proc = _run([
        str(MEMORY_RUN), "learn",
        "-t", "Fragility", "-t", "error-taxonomy", "-t", str(report.get("layer") or "pipeline"),
        "--problem", f"Ambiguous pipeline error assigned code {report['code']}: {report['cause']}",
        "--solution", (report.get("next_command") or "No deterministic fix yet; ticket + agentic-eval opened to pin it down."),
    ])
    return {"ok": proc.returncode == 0, "stderr": proc.stderr[-300:]}


@app.command()
def catalog() -> None:
    """List the canonical failure codes."""
    for entry in load_catalog():
        typer.echo(f"{entry['code']:42} [{entry.get('layer','?'):7}] {entry.get('cause','')[:70]}")


@app.command(name="classify")
def classify_cmd(
    text: str = typer.Option("", "--text", help="Raw error text."),
    receipt: Path = typer.Option(None, "--receipt", help="A lane receipt / *.meta.json to read."),
    layer: str = typer.Option("", "--layer", help="ask|tau|surf|scillm (optional)."),
) -> None:
    """Classify one error signal into a canonical (or minted) code."""
    signal = _read_signal(text, receipt)
    if not signal.strip():
        typer.echo(json.dumps({"error": "no --text or --receipt content"}))
        raise typer.Exit(2)
    typer.echo(json.dumps(classify(signal, layer or None), indent=2))


@app.command()
def triage(
    text: str = typer.Option("", "--text"),
    receipt: Path = typer.Option(None, "--receipt"),
    layer: str = typer.Option("", "--layer"),
    target: str = typer.Option("skills/ask", "--target", help="Ticket target when ambiguous."),
    file_ticket: bool = typer.Option(False, "--file", help="PUBLISH a GitHub ticket (default: draft only)."),
    scaffold_eval: bool = typer.Option(False, "--scaffold-eval", help="Scaffold an agentic-eval repro fixture."),
    learn: bool = typer.Option(True, "--learn/--no-learn", help="Store the code to /memory."),
) -> None:
    """Classify; when ambiguous, draft/file a ticket, optionally scaffold an eval, and learn."""
    signal = _read_signal(text, receipt)
    if not signal.strip():
        typer.echo(json.dumps({"error": "no --text or --receipt content"}))
        raise typer.Exit(2)
    report = classify(signal, layer or None)
    actions: dict[str, Any] = {}
    if report["ambiguous"]:
        actions["ticket"] = _draft_or_file_ticket(report, target, str(receipt or "<inline>"), file_ticket)
        if scaffold_eval and EVALS_RUN.exists():
            proc = _run([str(EVALS_RUN), "scaffold-fixture", str(SKILLS_ROOT / Path(target).name)])
            actions["scaffold_eval"] = {"ok": proc.returncode == 0, "stderr": proc.stderr[-300:]}
        if learn:
            actions["memory"] = _store_memory(report)
    typer.echo(json.dumps({"report": report, "actions": actions}, indent=2))
    typer.echo("TRIAGE_COMPLETE")


if __name__ == "__main__":
    app()
