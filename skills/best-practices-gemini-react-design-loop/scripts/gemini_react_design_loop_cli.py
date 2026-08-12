#!/usr/bin/env python3
"""Artifact helper for Gemini-driven React design-loop workflows.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(gemini_react_design_loop_cli.cpython-314.pyc) after the .py source was lost
(never tracked in git, no disk copy survived). Reconstructed faithfully from the
Python 3.14 disassembly (pycdc does not support 3.14; reconstructed op-by-op with
python3.14's own dis). Now TRACKED.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    no_args_is_help=True,
    help="Artifact helper for Gemini-driven React design-loop workflows.",
)

SURF = "/home/graham/workspace/experiments/agent-skills/skills/surf/run.sh"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json_print(payload: dict) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("make-request")
def make_request(
    app_purpose: str = typer.Option(..., help="Target user, primary object, workflow, and hard constraints."),
    constraints: str = typer.Option("", help="Project-local design, token, component, or best-practice constraints."),
    verification_context: str = typer.Option("", help="Screenshot path, viewport, reviewed state, and known limitations."),
    output_dir: Path = typer.Option(Path("/tmp/gemini-react-design-loop"), help="Artifact directory."),
    extra_question: str = typer.Option("", help="Optional focused design question for Gemini."),
) -> None:
    request = (
        "You are the designer for this modern React app. Codex is the code runner.\n"
        "Do not approve or rubber-stamp the current implementation.\n\n"
        "App purpose:\n"
        f"{app_purpose}"
        "\n\nProject-local design constraints:\n"
        f"{constraints or 'Not provided. If missing, say what design source-of-truth is needed.'}"
        "\n\nCurrent verification context:\n"
        f"{verification_context or 'No screenshot context was provided. If visual review is required, return insufficient evidence.'}"
        "\n\nReview the currently shared/rendered surface and return:\n"
        "1. Top 3 visible UX defects, one sentence each.\n"
        "2. Exact React/TypeScript component changes.\n"
        "3. Exact CSS/style/token changes.\n"
        "4. Exact interaction/state changes.\n"
        "5. Accessibility or contrast concerns.\n"
        "6. Responsive/state coverage concerns.\n"
        "7. One focused clarifying question with recommended default.\n\n"
        "Be concise. Prefer code or directly implementable instructions. Do not provide long design philosophy.\n"
        "Do not ask if I want approval.\n"
    )
    if extra_question:
        request += f"\nFocused question:\n{extra_question}\n"
    output = output_dir / "request.md"
    _write(output, request)
    _json_print({"status": "created", "request": str(output), "output_dir": str(output_dir)})


@app.command("goal-contract")
def goal_contract(
    surface: str = typer.Option(..., help="React surface or route under design."),
    user_job: str = typer.Option(..., help="One-sentence user job."),
    outcome: str = typer.Option(..., help="Concrete design outcome for Gemini to finish."),
    output_dir: Path = typer.Option(Path("/tmp/gemini-react-design-loop"), help="Artifact directory."),
) -> None:
    text = (
        "# Gemini React Design Loop Goal Contract\n\nSurface:\n"
        f"{surface}"
        "\n\nUser job:\n"
        f"{user_job}"
        "\n\nDesign outcome:\n"
        f"{outcome}"
        "\n\nHard gate:\n"
        "- Create or resume an explicit goal before the first Gemini prompt.\n"
        "- Continue implementation, verification, and Gemini review rounds until Gemini says the rendered "
        "design meets the app purpose, the human accepts, or a real blocked condition is reached.\n"
        "- Do not mark the goal complete from Gemini prose alone.\n\n"
        "Required closure evidence:\n"
        "- Gemini iteration count and artifacts\n"
        "- local verification commands and exit statuses\n"
        "- fresh CDP screenshot path\n"
        "- implemented React/CSS changes\n"
        "- unresolved gaps or tickets\n"
    )
    output = output_dir / "goal-contract.md"
    _write(output, text)
    _json_print({"status": "created", "goal_contract": str(output), "surface": surface})


@app.command("surf-commands")
def surf_commands(
    request: Path = typer.Option(..., exists=True, readable=True, help="Request markdown produced by make-request."),
    output_dir: Path = typer.Option(Path("/tmp/gemini-react-design-loop"), help="Artifact directory for Surf outputs."),
    tab_id: Optional[str] = typer.Option(None, help="Explicit Gemini tab id."),
    url: Optional[str] = typer.Option(None, help="Open Gemini tab URL to resolve."),
    no_activate: bool = typer.Option(True, help="Use Surf background mode when possible."),
    timeout: int = typer.Option(300, min=1, help="Surf Gemini timeout seconds."),
) -> None:
    if not tab_id and not url:
        raise typer.BadParameter("Provide --tab-id or --url. Do not let Surf guess the Gemini tab.")
    output_dir.mkdir(parents=True, exist_ok=True)
    response = output_dir / "response.md"
    raw = output_dir / "response.raw.md"
    meta = output_dir / "response.meta.json"
    target = f"--tab-id {tab_id}" if tab_id else f"--url {url!r}"
    no_act = " --no-activate" if no_activate else ""
    typer.echo(
        "# Submit to the exact Gemini tab\n"
        f"{SURF} gemini.submit \\\n"
        f"  --input {request} \\\n"
        f"  --output {response} \\\n"
        f"  --raw-output {raw} \\\n"
        f"  --meta-output {meta} \\\n"
        f"  {target} \\\n"
        f"  --timeout {timeout}{no_act}"
        "\n\n# Inspect proof metadata before using the response\n"
        "jq '{status, proof_status, controlled_tab_id, requested_tab_id, raw_contains_sentinel, "
        "clean_contains_sentinel, focus_changed}' "
        f"{meta}"
        "\n\n# If interrupted after Gemini visibly answered, recover with the exact sentinel from "
        "metadata/submitted prompt\n"
        f"{SURF} gemini.extract \\\n"
        f"  {target} \\\n"
        f"  --sentinel '<EXACT_SENTINEL>' \\\n"
        f"  --output {output_dir / 'recovered.md'} \\\n"
        f"  --raw-output {output_dir / 'recovered.raw.md'} \\\n"
        f"  --meta-output {output_dir / 'recovered.meta.json'}\n"
    )


@app.command("check-proof")
def check_proof(
    meta: Path = typer.Option(..., help="Surf Gemini metadata JSON."),
    response: Path = typer.Option(..., help="Clean Gemini response markdown."),
    screenshot: Optional[Path] = typer.Option(None, help="Fresh local UI screenshot path."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    missing = []
    for label, path in (("meta", meta), ("response", response)):
        if not path.exists() or path.stat().st_size == 0:
            missing.append(label)
    if screenshot and (not screenshot.exists() or screenshot.stat().st_size == 0):
        missing.append("screenshot")

    meta_payload = {}
    if meta.exists() and meta.stat().st_size:
        try:
            meta_payload = json.loads(meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            missing.append("valid_meta_json")

    status = "missing_evidence" if missing else "evidence_present"
    payload = {
        "status": status,
        "missing": missing,
        "meta": str(meta),
        "response": str(response),
        "screenshot": str(screenshot) if screenshot else None,
        "controlled_tab_id": meta_payload.get("controlled_tab_id"),
        "requested_tab_id": meta_payload.get("requested_tab_id"),
        "raw_contains_sentinel": meta_payload.get("raw_contains_sentinel"),
        "focus_changed": meta_payload.get("focus_changed"),
    }
    if json_output:
        _json_print(payload)
    else:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if missing:
        raise typer.Exit(1)


@app.command("final-report")
def final_report(
    outcome: str = typer.Option(..., help="accepted, human-accepted, blocked, or partially complete."),
    iterations: int = typer.Option(..., min=0, help="Gemini iteration count."),
    changes: str = typer.Option(..., help="Short summary of implemented UX/design changes."),
    verification: str = typer.Option(..., help="Commands and exit statuses."),
    screenshot: Path = typer.Option(..., help="Fresh CDP screenshot path."),
    gaps: str = typer.Option("", help="Unresolved gaps."),
    tickets: str = typer.Option("", help="Tickets filed, if any."),
) -> None:
    typer.echo(
        "**Design Outcome**\n"
        f"{outcome}"
        "\n\n**Gemini Iterations**\n"
        f"{iterations}"
        "\n\n**Changes**\n"
        f"{changes}"
        "\n\n**Verification**\n"
        f"{verification}"
        "\n\n**Fresh CDP Screenshot**\n"
        f"{screenshot}"
        "\n\n**Unresolved Gaps**\n"
        f"{gaps or 'None stated.'}"
        "\n\n**Tickets Filed**\n"
        f"{tickets or 'None.'}"
        "\n"
    )


if __name__ == "__main__":
    app()
