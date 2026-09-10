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
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import typer
from loguru import logger

from classifier import classify, load_catalog, _normalize, _mint_code, _first_error_line  # noqa: F401

app = typer.Typer(add_completion=False, help="Classify ambiguous pipeline errors into unambiguous codes.")

HERE = Path(__file__).resolve().parent
CATALOG_PATH = Path(os.environ.get("TRIAGE_ERROR_CATALOG_PATH", HERE / "failure_codes.json"))
SKILLS_ROOT = HERE.parent
TICKET_RUN = SKILLS_ROOT / "ticket" / "run.sh"
EVALS_RUN = SKILLS_ROOT / "agentic-evals" / "run.sh"
MEMORY_RUN = SKILLS_ROOT / "memory" / "run.sh"


def _catalog_match_tokens(signal: str, code: str) -> list[str]:
    first = _first_error_line(signal)
    tokens = [code]
    if first:
        tokens.append(first[:180])
    return tokens


def _upsert_catalog_entry(report: dict[str, Any], signal: str, catalog_path: Path = CATALOG_PATH) -> dict[str, Any]:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    codes = data.setdefault("codes", [])
    for entry in codes:
        if entry.get("code") == report["code"]:
            return {"ok": True, "updated": False, "code": report["code"]}
    entry = {
        "code": report["code"],
        "layer": report.get("layer") or "unknown",
        "match": _catalog_match_tokens(signal, report["code"]),
        "cause": report.get("cause") or f"Unclassified error signal assigned {report['code']}.",
        "next_command": report.get("next_command")
        or "Read the original receipt, replace this provisional catalog entry with the root-cause classification, and add a regression case to skills/triage-error/tests/test_classify.py.",
        "recoverable": report.get("recoverable") if report.get("recoverable") is not None else True,
        "not_this": report.get("not_this", []),
    }
    codes.append(entry)
    rendered = json.dumps(data, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(catalog_path.parent), delete=False) as tmp:
        tmp.write(rendered)
        tmp_name = tmp.name
    os.replace(tmp_name, catalog_path)
    return {"ok": True, "updated": True, "code": report["code"], "path": str(catalog_path)}


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
        f"[{report['code']}] {report['cause'][:70]}",
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
        "-t", str(report["code"]),
        "--problem", f"Ambiguous pipeline error assigned code {report['code']}: {report['cause']}",
        "--solution", (report.get("next_command") or "No deterministic fix yet; ticket + agentic-eval opened to pin it down."),
    ])
    return {"ok": proc.returncode == 0, "stderr": proc.stderr[-300:]}


@app.command()
def catalog() -> None:
    """List the canonical failure codes."""
    for entry in load_catalog():
        typer.echo(f"{entry['code']:42} [{entry.get('layer','?'):7}] {entry.get('cause','')[:70]}")


TAU_CLASSIFICATION_SCHEMA = "tau.triage_error_classification.v1"
TAU_CONTRACT_LAYERS = frozenset(
    {"tau", "dag-runtime", "scheduler", "adapter", "worker", "resource",
     "workspace", "replay", "transition", "correction"}
)


def _tau_contract_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Map the simple classify() result onto tau's strict canonical contract.

    tau.triage_error_classification.v1 consumers (the tau triage bridge) reject
    anything else byte-level (`triage_contract_non_canonical_json`), which is
    why every external classification degraded to triage_contract_invalid
    before this existed. Output must be single-line compact sorted JSON.
    """
    code = str(report.get("code") or "triage_unclassified")
    layer = str(report.get("layer") or "tau") or "tau"
    if layer not in TAU_CONTRACT_LAYERS:
        layer = "tau"
    cause = " ".join(str(report.get("cause") or code).split()) or code
    if "runner not found" in cause.lower() or code == "tau_triage_unavailable":
        disposition, family = "UNAVAILABLE", "triage_unavailable"
    else:
        disposition, family = "AMBIGUOUS", "unknown_internal_failure"
    return {
        "schema": TAU_CLASSIFICATION_SCHEMA,
        "code": code,
        "layer": layer,
        "cause": cause,
        "repair_family": family,
        "disposition": disposition,
        "requires_human": bool(report.get("ambiguous")),
        "diagnostics": {
            "classifier_kind": "EXTERNAL_CLASSIFIER",
            "next_command": report.get("next_command"),
            "matched_tokens": report.get("matched_tokens") or [],
            "recoverable": report.get("recoverable"),
            "source": "triage-error skill",
        },
    }


def _emit_tau_contract(report: dict[str, Any]) -> None:
    payload = _tau_contract_payload(report)
    typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


@app.command(name="classify")
def classify_cmd(
    text: str = typer.Option("", "--text", help="Raw error text."),
    receipt: Path = typer.Option(None, "--receipt", help="A lane receipt / *.meta.json to read."),
    layer: str = typer.Option("", "--layer", help="ask|tau|surf|scillm (optional)."),
    contract: str = typer.Option(
        "simple", "--contract",
        help="simple (default) or tau (tau.triage_error_classification.v1 canonical, single-line).",
    ),
) -> None:
    """Classify one error signal into a canonical (or minted) code."""
    signal = _read_signal(text, receipt)
    if not signal.strip():
        typer.echo(json.dumps({"error": "no --text or --receipt content"}))
        raise typer.Exit(2)
    report = classify(signal, layer or None)
    if contract == "tau":
        _emit_tau_contract(report)
        return
    typer.echo(json.dumps(report, indent=2))


@app.command()
def triage(
    text: str = typer.Option("", "--text"),
    receipt: Path = typer.Option(None, "--receipt"),
    layer: str = typer.Option("", "--layer"),
    target: str = typer.Option("skills/ask", "--target", help="Ticket target when ambiguous."),
    file_ticket: bool = typer.Option(False, "--file", help="PUBLISH a GitHub ticket (default: draft only)."),
    ticket: bool = typer.Option(True, "--ticket/--no-ticket", help="Draft/file a ticket for ambiguous signals."),
    scaffold_eval: bool = typer.Option(False, "--scaffold-eval", help="Scaffold an agentic-eval repro fixture."),
    learn: bool = typer.Option(True, "--learn/--no-learn", help="Store the code to /memory."),
    update_catalog: bool = typer.Option(True, "--update-catalog/--no-update-catalog", help="Append a provisional catalog entry for a newly minted ambiguous code."),
) -> None:
    """Classify; when ambiguous, draft/file a ticket, optionally scaffold an eval, learn, and update the catalog."""
    signal = _read_signal(text, receipt)
    if not signal.strip():
        typer.echo(json.dumps({"error": "no --text or --receipt content"}))
        raise typer.Exit(2)
    report = classify(signal, layer or None)
    actions: dict[str, Any] = {}
    if report["ambiguous"]:
        if update_catalog:
            actions["catalog"] = _upsert_catalog_entry(report, signal)
        if ticket:
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
