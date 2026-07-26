"""Run repeated live mixed-provider roundtable and competition evaluations.

Inputs are browser-oracle project bindings, an iteration count, and an output
root. Outputs are the native Ask/Tau run directories plus a campaign-level JSON
receipt. Any missing, mocked, degraded, or failed lane fails the evaluation.
The runner calls real browser and SciLLM providers and may take several hours.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv
from loguru import logger


load_dotenv()

ASK_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ASK_ROOT.parent
ASK_RUN = ASK_ROOT / "run.sh"
BROWSER_ORACLE_RUN = SKILLS_ROOT / "browser-oracle" / "run.sh"
SURF_RUN = SKILLS_ROOT / "surf" / "run.sh"
DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/ask/outputs/live-mixed-dag-e2e")
HANDLERS = ("webgpt", "webclaude", "webkimi", "webgrok", "webgemini", "gpt-5.5")
BROWSER_HANDLERS = HANDLERS[:-1]
DEFAULT_PROJECTS = {
    "webgpt": "ask-e2e-webgpt",
    "webclaude": "ask-e2e-webclaude",
    "webkimi": "ask-e2e-webkimi",
    "webgrok": "ask-e2e-webgrok",
    "webgemini": "ask-e2e-webgemini",
}
FRESH_URLS = {
    "webgpt": "https://chatgpt.com/",
    "webclaude": "https://claude.ai/new",
    "webkimi": "https://www.kimi.com/",
    "webgrok": "https://grok.com/",
    "webgemini": "https://gemini.google.com/app",
}
app = typer.Typer(add_completion=False)


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


async def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run a subprocess without blocking the event loop."""
    started = asyncio.get_running_loop().time()
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout_seconds)
    except TimeoutError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 10)
        except TimeoutError:
            proc.kill()
            await proc.wait()
        raise RuntimeError(f"command timed out after {timeout_seconds}s: {command!r}")
    return CommandResult(
        command=command,
        returncode=int(proc.returncode or 0),
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
        duration_seconds=round(asyncio.get_running_loop().time() - started, 3),
    )


def parse_project_overrides(values: list[str]) -> dict[str, str]:
    """Parse repeatable handler=browser-oracle-project overrides."""
    projects = dict(DEFAULT_PROJECTS)
    for value in values:
        handler, separator, project = value.partition("=")
        if not separator or handler not in BROWSER_HANDLERS or not project.strip():
            raise typer.BadParameter(
                f"invalid --handler-project {value!r}; expected one of "
                f"{', '.join(BROWSER_HANDLERS)}=PROJECT"
            )
        projects[handler] = project.strip()
    return projects


def load_json(path: Path) -> dict[str, Any]:
    """Load a required JSON object."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


async def reset_browser_tabs(projects: dict[str, str]) -> list[dict[str, Any]]:
    """Resolve every browser project and navigate its exact tab to a fresh chat."""
    receipts: list[dict[str, Any]] = []
    env = os.environ.copy()
    env.setdefault("SURF_LOCK_TIMEOUT_MS", "1800000")
    for handler in BROWSER_HANDLERS:
        resolve = await run_command(
            [
                str(BROWSER_ORACLE_RUN),
                "resolve",
                "--backend",
                handler,
                "--project",
                projects[handler],
                "--json",
            ],
            cwd=BROWSER_ORACLE_RUN.parent,
            timeout_seconds=960,
            env=env,
        )
        if resolve.returncode != 0:
            raise RuntimeError(
                f"{handler} browser binding failed: {resolve.stderr or resolve.stdout}"
            )
        binding = json.loads(resolve.stdout)
        tab_id = str(binding.get("tab_id") or "")
        if not tab_id:
            raise RuntimeError(f"{handler} binding returned no tab_id: {binding}")
        reset = await run_command(
            [
                str(SURF_RUN),
                "go",
                FRESH_URLS[handler],
                "--tab-id",
                tab_id,
                "--json",
            ],
            cwd=SURF_RUN.parent,
            timeout_seconds=960,
            env=env,
        )
        if reset.returncode != 0:
            raise RuntimeError(f"{handler} fresh-chat reset failed: {reset.stderr or reset.stdout}")
        receipts.append(
            {
                "handler": handler,
                "project": projects[handler],
                "tab_id": tab_id,
                "fresh_url": FRESH_URLS[handler],
                "resolve_duration_seconds": resolve.duration_seconds,
                "reset_duration_seconds": reset.duration_seconds,
            }
        )
    return receipts


def handler_node_id(handler: str) -> str:
    """Return Ask's stable node id for a handler label."""
    return "handler-" + "".join(character if character.isalnum() else "-" for character in handler).strip("-")


def validate_run(run_dir: Path, *, mode: str) -> dict[str, Any]:
    """Validate live execution, every handler lane, and the mode-specific join."""
    errors: list[str] = []
    execution_path = run_dir / "execution-status.json"
    if not execution_path.is_file():
        return {"status": "FAIL", "errors": [f"missing {execution_path}"], "run_dir": str(run_dir)}
    execution = load_json(execution_path)
    expected_execution = {
        "ok": True,
        "status": "PASS",
        "mocked": False,
        "live": True,
        "provider_live": True,
        "dag_run_returncode": 0,
    }
    for key, expected in expected_execution.items():
        if execution.get(key) != expected:
            errors.append(f"execution.{key}={execution.get(key)!r}, expected {expected!r}")

    lanes: list[dict[str, Any]] = []
    for handler in HANDLERS:
        node_id = handler_node_id(handler)
        receipt_path = run_dir / "node-artifacts" / node_id / "node-receipt.json"
        if not receipt_path.is_file():
            errors.append(f"missing lane receipt: {receipt_path}")
            continue
        receipt = load_json(receipt_path)
        lane = {
            "handler": handler,
            "receipt": str(receipt_path),
            "status": receipt.get("status"),
            "ok": receipt.get("ok"),
            "mocked": receipt.get("mocked"),
            "live": receipt.get("live"),
            "provider_live": receipt.get("provider_live"),
            "failure_code": receipt.get("failure_code"),
            "response_chars": receipt.get("response_chars"),
        }
        lanes.append(lane)
        for key, expected in {
            "status": "PASS",
            "ok": True,
            "mocked": False,
            "live": True,
            "provider_live": True,
            "failure_code": None,
        }.items():
            if lane.get(key) != expected:
                errors.append(f"{handler}.{key}={lane.get(key)!r}, expected {expected!r}")
        response_path = Path(str(receipt.get("response_path") or ""))
        response = response_path.read_text(encoding="utf-8", errors="replace") if response_path.is_file() else ""
        if "RESULT: 4" not in response:
            errors.append(f"{handler} response omitted RESULT: 4")

    join_path = run_dir / "node-artifacts" / "join" / "node-receipt.json"
    if not join_path.is_file():
        errors.append(f"missing join receipt: {join_path}")
        join: dict[str, Any] = {}
    else:
        join = load_json(join_path)
        for key, expected in {
            "status": "PASS",
            "ok": True,
            "mocked": False,
            "live": True,
            "provider_live": True,
        }.items():
            if join.get(key) != expected:
                errors.append(f"join.{key}={join.get(key)!r}, expected {expected!r}")
        degradation = join.get("degradation_analysis") or {}
        if mode == "roundtable":
            if degradation.get("usable_response_count") != len(HANDLERS):
                errors.append(
                    f"join usable_response_count={degradation.get('usable_response_count')!r}"
                )
            if degradation.get("failed_seat_count") != 0:
                errors.append(f"join failed_seat_count={degradation.get('failed_seat_count')!r}")
        else:
            scorecard_path = Path(str(join.get("scorecard_path") or ""))
            if not scorecard_path.is_file():
                errors.append(f"missing competition scorecard: {scorecard_path}")
            else:
                scorecard = load_json(scorecard_path)
                if scorecard.get("status") != "PASS" or scorecard.get("ok") is not True:
                    errors.append(f"competition scorecard status={scorecard.get('status')!r}")
                if not scorecard.get("winner_handler"):
                    errors.append("competition scorecard has no winner_handler")
                if scorecard.get("transport_blockers"):
                    errors.append(
                        f"competition transport blockers={scorecard.get('transport_blockers')!r}"
                    )
                if scorecard.get("blockers"):
                    errors.append(f"competition blockers={scorecard.get('blockers')!r}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "mode": mode,
        "run_dir": str(run_dir),
        "execution_status": str(execution_path),
        "join_receipt": str(join_path),
        "lanes": lanes,
        "errors": errors,
        "mocked": False,
        "live": True,
    }


def dag_command(
    *,
    mode: str,
    ask_id: str,
    output_root: Path,
    projects: dict[str, str],
) -> list[str]:
    """Build one real mixed-provider Ask/Tau command."""
    if mode == "roundtable":
        request = "Return your handler name and RESULT: 4. Keep the response concise."
        goal = (
            "All six named handlers return a receipt-backed RESULT: 4 response; "
            "the join reports six usable responses and zero failed seats."
        )
    else:
        request = (
            "Return RESULT: 4. Then emit exactly the number of distinct lines beginning "
            "VERIFIED_FEATURE: assigned to your handler: webgpt=1, webclaude=2, "
            "webkimi=3, webgrok=4, webgemini=5, gpt-5.5=6. Each feature line must "
            "state a concrete arithmetic check that 2+2=4 and include its 1-based "
            "feature number. Do not emit extra VERIFIED_FEATURE lines."
        )
        goal = (
            "All six isolated competitors return RESULT: 4; every lane passes live "
            "without transport blockers; and the scorecard selects one clear winner."
        )
    command = [
        str(ASK_RUN),
        "tau-dag",
        request,
        "--repo",
        "local/agent-skills",
        "--target",
        ask_id,
        "--immutable-goal",
        goal,
        "--topology",
        "concurrent",
        "--workflow-mode",
        mode,
        "--ask-id",
        ask_id,
        "--run-output-root",
        str(output_root),
        "--execute",
        "--poll-timeout-seconds",
        "7200",
        "--json",
    ]
    if mode == "compete":
        command.extend(
            [
                "--dag-template",
                "compete",
                "--criterion",
                "Correct RESULT: 4",
                "--criterion",
                "Exact handler-specific VERIFIED_FEATURE count",
            ]
        )
    for handler in HANDLERS:
        command.extend(["--handler", handler])
    for handler in BROWSER_HANDLERS:
        command.extend(["--handler-project", f"{handler}={projects[handler]}"])
    return command


async def run_campaign(
    *,
    output_root: Path,
    iterations: int,
    projects: dict[str, str],
) -> dict[str, Any]:
    """Run both workflow families repeatedly with a three-failure circuit breaker."""
    campaign_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    campaign_dir = output_root / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    family_failures = {"roundtable": 0, "compete": 0}
    env = os.environ.copy()
    env.setdefault("SURF_LOCK_TIMEOUT_MS", "1800000")

    for iteration in range(1, iterations + 1):
        for mode in ("roundtable", "compete"):
            if family_failures[mode] >= 3:
                results.append(
                    {
                        "iteration": iteration,
                        "mode": mode,
                        "status": "blocked_by_systemic_failure",
                        "latest_failure_signature": results[-1].get("errors", []),
                    }
                )
                continue
            ask_id = f"live-mixed-{mode}-{campaign_id}-r{iteration}"
            case_root = campaign_dir / f"{mode}-r{iteration}"
            reset_receipts = await reset_browser_tabs(projects)
            command = dag_command(
                mode=mode,
                ask_id=ask_id,
                output_root=case_root,
                projects=projects,
            )
            logger.info("running {} iteration {}", mode, iteration)
            run = await run_command(
                command,
                cwd=ASK_ROOT,
                timeout_seconds=9000,
                env=env,
            )
            run_dir = case_root / ask_id
            validation = validate_run(run_dir, mode=mode)
            validation.update(
                {
                    "iteration": iteration,
                    "command": command,
                    "command_returncode": run.returncode,
                    "command_duration_seconds": run.duration_seconds,
                    "stdout_path": str(case_root / "ask.stdout.log"),
                    "stderr_path": str(case_root / "ask.stderr.log"),
                    "tab_resets": reset_receipts,
                }
            )
            case_root.mkdir(parents=True, exist_ok=True)
            (case_root / "ask.stdout.log").write_text(run.stdout, encoding="utf-8")
            (case_root / "ask.stderr.log").write_text(run.stderr, encoding="utf-8")
            if run.returncode != 0:
                validation["status"] = "FAIL"
                validation["errors"].append(f"ask command returncode={run.returncode}")
            if validation["status"] == "FAIL":
                family_failures[mode] += 1
            results.append(validation)

    summary = {
        "schema": "ask.live_mixed_dag_e2e.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "campaign_dir": str(campaign_dir),
        "iterations": iterations,
        "handlers": list(HANDLERS),
        "mocked": False,
        "live": True,
        "passed": sum(item.get("status") == "PASS" for item in results),
        "failed": sum(item.get("status") == "FAIL" for item in results),
        "blocked_by_systemic_failure": sum(
            item.get("status") == "blocked_by_systemic_failure" for item in results
        ),
        "not_run": 0,
        "active_family": None,
        "latest_failure_signature": next(
            (item.get("errors") for item in reversed(results) if item.get("status") == "FAIL"),
            None,
        ),
        "status": "PASS" if all(item.get("status") == "PASS" for item in results) else "FAIL",
        "results": results,
    }
    (campaign_dir / "report.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


@app.command()
def main(
    iterations: int = typer.Option(2, min=1, max=5),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT),
    handler_project: list[str] | None = typer.Option(None, "--handler-project"),
    allow_live: bool = typer.Option(False, help="Required acknowledgement for real provider calls."),
) -> None:
    """Execute the live mixed-provider campaign and fail closed on any lane."""
    if not allow_live and os.environ.get("ASK_LIVE_MIXED_DAG_E2E") != "1":
        raise typer.BadParameter(
            "pass --allow-live or set ASK_LIVE_MIXED_DAG_E2E=1; this calls real providers"
        )
    projects = parse_project_overrides(handler_project or [])
    summary = asyncio.run(
        run_campaign(output_root=output_root.expanduser().resolve(), iterations=iterations, projects=projects)
    )
    typer.echo(json.dumps(summary, indent=2))
    raise typer.Exit(0 if summary["status"] == "PASS" else 1)


if __name__ == "__main__":
    app()
