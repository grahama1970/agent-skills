"""Multi-trial eval runner: deterministic-first grading, INFRA isolation.

Each (model, item) runs up to N trials through the same /ask -> tau -> scillm
flow the rest of the lab uses. Grading tries the deterministic evaluator first
(execute code / parse JSON) and falls back to the LLM judge only when the item
has no deterministic spec. Operational failures (empty response = timeout, or
VRAM guard refusal for local models) are recorded as status INFRA_BLOCKED and
kept OUT of accuracy averages, so a CPU-offload timeout never looks like a 0.

Every trial keeps the model's answer text and the on-disk /ask run_dir so the
report can cite a response.md receipt for each score.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import typer

from eval_app import app, console


def _read_control(output: Path) -> dict[str, Any]:
    """Read the sidecar control file (<output>.control): {paused, stop}.

    The control server writes this; the runner honours it at cell boundaries
    (clean pause between cells -- no in-flight /ask call is frozen).
    """
    cpath = Path(str(output) + ".control")
    if not cpath.exists():
        return {}
    try:
        return json.loads(cpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _await_resume(output: Path) -> bool:
    """Block while paused. Returns False if a stop was requested, else True."""
    while True:
        ctrl = _read_control(output)
        if ctrl.get("stop"):
            return False
        if not ctrl.get("paused"):
            return True
        time.sleep(0.5)
from evaluators import evaluate_output
import judge_grid
import vram_guard

LOCAL_MODELS = {"local-glm", "local-text"}
JUDGE_SYSTEM = judge_grid.JUDGE_SYSTEM
CANDIDATE_SYSTEM = judge_grid.CANDIDATE_SYSTEM


class InfraBlocked(Exception):
    """Raised when a call fails for operational (not accuracy) reasons."""


def call_model_proxy(model: str, prompt: str, timeout: int = 120) -> tuple[str, str]:
    """One model call via /ask. Returns (text, run_dir).

    Raises InfraBlocked when the pipeline returns no text (timeout / provider
    failure) -- every bank item requires a non-empty answer, so empty is an
    operational failure, not a wrong answer.
    """
    text, run_dir = judge_grid._ask_call(model, prompt, timeout)
    if not text.strip():
        raise InfraBlocked(f"empty response from {model} (timeout/provider failure)")
    return text, run_dir


def _llm_judge(item: dict[str, Any], answer: str, judge_handler: str, timeout: int) -> tuple[int, str]:
    """Fallback LLM-judge grading for items without a deterministic evaluator."""
    judge_prompt = (
        f"{JUDGE_SYSTEM}\n\nQUESTION:\n{item['input']}\n\n"
        f"REFERENCE ANSWER:\n{item['expected']}\n\n"
        f"GRADING CRITERION:\n{item['grading']}\n\n"
        f"CANDIDATE ANSWER:\n{answer}\n\n"
        'Return ONLY valid JSON: {"score": 0|1|2|3, "reason": "one sentence"}.'
    )
    text, _ = judge_grid._ask_call(judge_handler, judge_prompt, timeout)
    verdict = judge_grid._extract_json_object(text)
    if verdict is None:
        return 0, "judge returned no JSON"
    try:
        score = int(verdict.get("score"))
    except (TypeError, ValueError):
        score = 0
    score = score if score in (0, 1, 2, 3) else 0
    return score, str(verdict.get("reason", ""))


def grade(item: dict[str, Any], answer: str, judge_handler: str, timeout: int) -> tuple[int, str, str]:
    """Grade one answer. Returns (score, reason, method) -- deterministic first."""
    score, reason = evaluate_output(item, answer)
    if score is not None:
        return score, reason, item["eval"]["method"]
    score, reason = _llm_judge(item, answer, judge_handler, timeout)
    return score, reason, "llm-judge"


def run_eval_item(
    model: str,
    item: dict[str, Any],
    judge_handler: str,
    trials: int = 3,
    timeout: int = 120,
    min_free_gb: float = 6.0,
) -> dict[str, Any]:
    """Run one (model, item) across up to `trials`, aggregating pass@1/pass@3."""
    # VRAM guard for local models: refuse up front rather than time out.
    if model in LOCAL_MODELS and not vram_guard.check_vram_headroom(min_free_gb):
        return {
            "id": item["id"], "model": model, "status": "INFRA_BLOCKED",
            "pass_at_1": None, "pass_at_3": None, "method": None,
            "trials": [{"trial": 1, "score": None,
                        "reason": "VRAM guard refused (insufficient free VRAM)",
                        "answer": "", "run_dir": ""}],
        }

    results: list[dict[str, Any]] = []
    status = "SUCCESS"
    prompt = f"{CANDIDATE_SYSTEM}\n\nTASK:\n{item['input']}"
    for trial in range(1, trials + 1):
        try:
            answer, run_dir = call_model_proxy(model, prompt, timeout)
        except InfraBlocked as err:
            status = "INFRA_BLOCKED"
            results.append({"trial": trial, "score": None, "reason": f"Infrastructure failure: {err}",
                            "answer": "", "run_dir": ""})
            break
        score, reason, method = grade(item, answer, judge_handler, timeout)
        results.append({"trial": trial, "score": score, "reason": reason,
                        "method": method, "answer": answer, "run_dir": run_dir})

    scored = [r["score"] for r in results if r["score"] is not None]
    pass_at_1 = results[0]["score"] if results and results[0]["score"] is not None else None
    pass_at_3 = max(scored) if scored else None
    return {
        "id": item["id"], "model": model, "category": item.get("category"),
        "status": status, "pass_at_1": pass_at_1, "pass_at_3": pass_at_3,
        "method": results[-1].get("method") if results else None,
        "trials": results,
    }


@app.command(name="run-matrix")
def run_matrix(
    ground_truth: Path = typer.Option(..., "--ground-truth", "-g", exists=True),
    models: str = typer.Option("", "--models", "-m", help="Comma-separated; default: bank 'models'."),
    judge_model: str = typer.Option("", "--judge", help="LLM judge for non-deterministic items."),
    trials: int = typer.Option(3, "--trials", help="Trials per (model,item) for pass@k."),
    timeout: int = typer.Option(120, "--timeout"),
    min_free_gb: float = typer.Option(6.0, "--min-free-gb", help="VRAM floor for local models."),
    output: Path = typer.Option(..., "--output", "-o"),
) -> None:
    """Run every model x item with N trials; deterministic-first grading; INFRA isolation."""
    gt = json.loads(Path(ground_truth).read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = gt["questions"]
    candidates = [m.strip() for m in models.split(",") if m.strip()] or list(gt.get("models", []))
    judge_handler = judge_model or gt.get("judge", "")
    if not candidates:
        console.print("[red]need at least one model[/red]"); raise typer.Exit(2)

    console.print(f"[bold]run-matrix[/bold]: {len(items)} items x {len(candidates)} models x "
                  f"{trials} trials, judge={judge_handler or 'none'}\n")
    total = len(candidates) * len(items)
    rows: list[dict[str, Any]] = []

    def _flush(state: str) -> None:
        """Write the current results atomically so a live report can poll it."""
        out = {
            "title": gt.get("title"), "models": candidates, "judge": judge_handler,
            "trials": trials, "status": state,
            "progress": {"done": len(rows), "total": total},
            "results": rows,
        }
        tmp = Path(str(output) + ".tmp")
        tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
        tmp.replace(output)

    _flush("running")  # empty shell so the live page renders immediately
    stopped = False
    for m in candidates:
        for it in items:
            # Clean pause / stop between cells (never mid /ask call).
            if not _await_resume(output):
                stopped = True
                break
            r = run_eval_item(m, it, judge_handler, trials=trials, timeout=timeout, min_free_gb=min_free_gb)
            rows.append(r)
            _flush("running")  # incremental: each cell appears in the live report
            p1 = "INFRA" if r["status"] == "INFRA_BLOCKED" else f"{r['pass_at_1']}"
            console.print(f"[dim]  {len(rows)}/{total}  q{r['id']:<2} {m:<16} pass@1={p1} "
                          f"pass@3={r['pass_at_3']} ({r['method']})[/dim]")
        if stopped:
            break

    _flush("stopped" if stopped else "complete")
    console.print(f"[dim]wrote {output}[/dim]")
    console.print("RUN_MATRIX_COMPLETE")
