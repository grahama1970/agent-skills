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

from classifier import classify, load_catalog, _normalize, _mint_code, _first_error_line, _catalog_entry_for_code  # noqa: F401
from jev_shadow import log_shadow, shadow_classify, shadow_enabled, tier2_enabled

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


def _run_shadow(signal: str, layer: str | None, report: dict[str, Any]) -> dict[str, Any] | None:
    """Shadow Jev alongside the deterministic classifier.

    Shadow tier (JEV_API_KEY): measure-only, logs both verdicts, never changes
    the decision.
    Tier 2 (JEV_API_KEY + JEV_TIER2=1): when the deterministic classifier
    minted an ambiguous code AND Jev ACCEPTED a catalog code, promote that
    entry into the report. Fail-closed: abstain, no_match, or a code missing
    from the live catalog leaves the minted code untouched.
    """
    if not shadow_enabled():
        return None
    shadow = shadow_classify(signal, layer)
    shadow["deterministic_code"] = report.get("code")
    shadow["deterministic_ambiguous"] = report.get("ambiguous")
    shadow["agree"] = (
        (shadow.get("jev_code") == report.get("code"))
        or (report.get("ambiguous") and shadow.get("jev_code") == "no_match")
        if shadow.get("jev_decision") == "accept"
        else None
    )
    promoted = False
    if (
        tier2_enabled()
        and report.get("ambiguous")
        and shadow.get("jev_decision") == "accept"
    ):
        entry = (
            _catalog_entry_for_code(load_catalog(), shadow.get("jev_code"), layer)
            or _catalog_entry_for_code(load_catalog(), shadow.get("jev_code"), None)
        )
        if entry:
            report["minted_code"] = report["code"]
            report.update(
                code=entry["code"],
                layer=entry.get("layer") or report.get("layer"),
                cause=entry.get("cause") or report.get("cause"),
                next_command=entry.get("next_command") or report.get("next_command"),
                recoverable=entry.get("recoverable") if entry.get("recoverable") is not None else report.get("recoverable"),
                not_this=entry.get("not_this") or report.get("not_this", []),
                ambiguous=False,
                matched_tokens=[f"jev_tier2:{shadow.get('jev_code')}"],
                classified_by="jev_tier2",
            )
            promoted = True
    shadow["tier2_promoted"] = promoted
    shadow["final_code"] = report.get("code")
    log_shadow(shadow)
    return shadow


TAU_LAYERS = {"tau", "dag-runtime", "scheduler", "adapter", "worker", "resource", "workspace", "replay", "transition", "correction"}


def _tau_contract_payload(signal: str, layer: str | None, report: dict[str, Any]) -> dict[str, Any]:
    """Emit tau.triage_error_classification.v1 (tau bridge pydantic contract).

    The skill cannot compose Tau scheduler repair args, so it never claims
    KNOWN_REPAIR: canonical catalog codes map to NEEDS_HUMAN (apply the
    code's next_command), minted codes to AMBIGUOUS. Both fail closed with
    requires_human=True, mirroring the bridge's own _mint shape.
    """
    ambiguous = bool(report.get("ambiguous"))
    cause = " ".join(_first_error_line(signal).split())[:512]
    return {
        "schema": "tau.triage_error_classification.v1",
        "code": report["code"],
        "layer": layer if layer in TAU_LAYERS else "tau",
        "cause": cause,
        "repair_family": "triage_unavailable" if ambiguous else "unknown_internal_failure",
        "disposition": "AMBIGUOUS" if ambiguous else "NEEDS_HUMAN",
        "requires_human": True,
        "diagnostics": {"classifier_kind": "SKILL_CATALOG", "ambiguous": ambiguous},
    }


@app.command(name="classify")
def classify_cmd(
    text: str = typer.Option("", "--text", help="Raw error text."),
    receipt: Path = typer.Option(None, "--receipt", help="A lane receipt / *.meta.json to read."),
    layer: str = typer.Option("", "--layer", help="ask|tau|surf|scillm (optional)."),
    contract: str = typer.Option("", "--contract", help="Emit a strict consumer contract (tau) as single-line canonical JSON."),
) -> None:
    """Classify one error signal into a canonical (or minted) code."""
    if contract not in ("", "tau"):
        typer.echo(json.dumps({"error": f"unknown --contract {contract}"}))
        raise typer.Exit(2)
    signal = _read_signal(text, receipt)
    if not signal.strip():
        typer.echo(json.dumps({"error": "no --text or --receipt content"}))
        raise typer.Exit(2)
    report = classify(signal, layer or None)
    if contract == "tau":
        typer.echo(json.dumps(_tau_contract_payload(signal, layer or None, report), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return
    shadow = _run_shadow(signal, layer or None, report)
    typer.echo(json.dumps({"report": report, "jev_shadow": shadow}, indent=2))


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
    shadow = _run_shadow(signal, layer or None, report)
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
    typer.echo(json.dumps({"report": report, "jev_shadow": shadow, "actions": actions}, indent=2))
    typer.echo("TRIAGE_COMPLETE")


if __name__ == "__main__":
    app()
