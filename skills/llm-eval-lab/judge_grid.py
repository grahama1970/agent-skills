"""judge-grid: N-model Agent-as-Judge capability grid via the /ask flow.

Runs every candidate model against every question in a ground-truth bank and
has an independent judge model score each answer (0-3) against the reference
answer and grading criterion, then renders a per-category capability table.

Every model call -- candidates AND judge -- goes through the SAME flow the
rest of the stack uses: /ask (tau-dag single-call) -> /tau -> /scillm. No
direct scillm HTTP, no exceptions (operator 2026-08-26). Candidate and judge
aliases must be valid /ask handlers / scillm model names.

Scores come from the judge model's JSON, never from regex/substring matching
of generated text (best-practices-python forbids regex as the first parser
for LLM output).
"""
from __future__ import annotations

import concurrent.futures
import json
import subprocess
import uuid
from enum import IntEnum
from pathlib import Path
from typing import Any

import typer
from rich.table import Table

from eval_app import app, console

ASK_DIR = Path(__file__).resolve().parents[1] / "ask"
ASK_RUN = ASK_DIR / "run.sh"
ASK_RUNS_ROOT = Path("/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs")

CANDIDATE_SYSTEM = (
    "Answer the task directly and concisely. If code is requested, return only "
    "a minimal correct snippet. If a specific JSON shape is requested, return "
    "only that JSON."
)
JUDGE_SYSTEM = (
    "You are a strict, fair grader. Score one candidate answer against a "
    "reference answer and a grading criterion. Ignore style; judge correctness "
    "and whether the criterion is met."
)


class Score(IntEnum):
    WRONG = 0
    PARTIAL = 1
    MOSTLY = 2
    CORRECT = 3


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Return the first top-level JSON object in text, or None.

    Not a regex parse: locate the outermost braces and hand the slice to the
    JSON parser, which is the grammar authority.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _ask_call(handler: str, prompt: str, timeout: int) -> tuple[str, str]:
    """One model call through /ask (tau-dag single-call) -> tau -> scillm.

    Returns (response_text, run_dir) where run_dir is the on-disk /ask run
    directory that holds the handler's response.md receipt. Returns ("", "")
    on any failure (the caller scores an empty answer as WRONG). The run_dir
    is recorded so every score in the grid traces to a file the reader can
    open and verify -- the answer is not re-typed by the grader.
    """
    ask_id = f"llm-eval-{handler}-{uuid.uuid4().hex[:8]}".replace(".", "-")
    run_dir = ASK_RUNS_ROOT / ask_id
    cmd = [
        str(ASK_RUN), "tau-dag", prompt,
        "--repo", "local/agent-skills", "--target", "llm-eval-lab",
        "--immutable-goal", "Answer the task or name a blocker.",
        "--handler", handler, "--dag-template", "single-call",
        "--ask-id", ask_id, "--execute", "--json",
        "--poll-timeout-seconds", str(timeout),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 120, cwd=ASK_DIR)
    except (subprocess.TimeoutExpired, OSError):
        return "", str(run_dir)
    for resp in sorted(run_dir.glob("node-artifacts/handler-*/response.md")):
        try:
            return resp.read_text(encoding="utf-8", errors="replace"), str(run_dir)
        except OSError:
            return "", str(run_dir)
    return "", str(run_dir)


def _grade_one(question: dict[str, Any], handler: str, judge_handler: str, timeout: int) -> dict[str, Any]:
    prompt = f"{CANDIDATE_SYSTEM}\n\nTASK:\n{question['input']}"
    answer, run_dir = _ask_call(handler, prompt, timeout)
    base = {"model": handler, "answer": answer, "run_dir": run_dir, "judge_run_dir": ""}
    if not answer.strip():
        return {**base, "score": Score.WRONG, "reason": "no answer"}
    judge_prompt = (
        f"{JUDGE_SYSTEM}\n\n"
        f"QUESTION:\n{question['input']}\n\n"
        f"REFERENCE ANSWER:\n{question['expected']}\n\n"
        f"GRADING CRITERION:\n{question['grading']}\n\n"
        f"CANDIDATE ANSWER:\n{answer}\n\n"
        'Return ONLY valid JSON: {"score": 0|1|2|3, "reason": "one sentence"} '
        "where 3=fully correct and meets the criterion, 2=mostly correct with a "
        "minor gap, 1=partially correct, 0=wrong or missing."
    )
    judge_text, judge_run_dir = _ask_call(judge_handler, judge_prompt, timeout)
    base["judge_run_dir"] = judge_run_dir
    verdict = _extract_json_object(judge_text)
    if verdict is None:
        return {**base, "score": Score.WRONG, "reason": "judge returned no JSON"}
    raw = verdict.get("score")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 0
    score = Score(value) if value in (0, 1, 2, 3) else Score.WRONG
    return {**base, "score": score, "reason": str(verdict.get("reason", ""))}


@app.command(name="judge-grid")
def judge_grid(
    ground_truth: Path = typer.Option(..., "--ground-truth", "-g", exists=True),
    models: str = typer.Option("", "--models", "-m",
                               help="Comma-separated candidate handlers (default: from file)."),
    judge_model: str = typer.Option("", "--judge", help="Judge handler (default: file 'judge' field)."),
    timeout: int = typer.Option(240, "--timeout", help="Per /ask call poll timeout (s)."),
    concurrency: int = typer.Option(4, "--concurrency", help="Max parallel /ask calls."),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Score N candidate models against a ground-truth bank with an LLM judge, all via /ask."""
    gt = json.loads(Path(ground_truth).read_text(encoding="utf-8"))
    questions: list[dict[str, Any]] = gt["questions"]
    candidates = [m.strip() for m in models.split(",") if m.strip()] or list(gt.get("models", []))
    judge_handler = judge_model or gt.get("judge", "")
    if not candidates or not judge_handler:
        console.print("[red]need at least one candidate and a judge[/red]")
        raise typer.Exit(2)

    console.print(f"[bold]judge-grid[/bold] (via /ask->tau->scillm): {len(questions)} questions x "
                  f"{len(candidates)} candidates, judge={judge_handler}\n")

    tasks = [(q, m) for q in questions for m in candidates]
    graded: dict[tuple[int, str], dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(_grade_one, q, m, judge_handler, timeout): (q["id"], m) for q, m in tasks}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            key = futures[fut]
            graded[key] = fut.result()
            done += 1
            console.print(f"[dim]  {done}/{len(tasks)}  q{key[0]} {key[1]} -> "
                          f"{int(graded[key]['score'])}[/dim]")

    rows = [{"question": q, "scores": {m: graded[(q["id"], m)] for m in candidates}} for q in questions]

    table = Table(title="Capability grid (judge score 0-3)")
    table.add_column("#", justify="right")
    table.add_column("category")
    table.add_column("diff")
    for m in candidates:
        table.add_column(m, justify="center")
    for r in rows:
        q = r["question"]
        table.add_row(str(q["id"]), q["category"], q["difficulty"][:4],
                      *[str(int(r["scores"][m]["score"])) for m in candidates])
    console.print(table)

    cats = sorted({r["question"]["category"] for r in rows})
    cat_table = Table(title="Per-category average (0-3), * = best")
    cat_table.add_column("category")
    for m in candidates:
        cat_table.add_column(m, justify="center")
    excels: dict[str, list[str]] = {m: [] for m in candidates}
    for cat in cats:
        crows = [r for r in rows if r["question"]["category"] == cat]
        avgs = {m: sum(int(r["scores"][m]["score"]) for r in crows) / len(crows) for m in candidates}
        best = max(avgs.values())
        cells = []
        for m in candidates:
            is_best = avgs[m] == best and best > 0
            cells.append(f"{avgs[m]:.1f}{' *' if is_best else ''}")
            if is_best:
                excels[m].append(cat)
        cat_table.add_row(cat, *cells)
    console.print(cat_table)

    totals = {m: sum(int(r["scores"][m]["score"]) for r in rows) for m in candidates}
    maxpts = 3 * len(rows)
    console.print("\n[bold]Totals[/bold]: " + ", ".join(f"{m} {totals[m]}/{maxpts}" for m in candidates))
    local = next((m for m in candidates if "glm" in m and "local" in m), candidates[0])
    console.print(f"[bold]{local} leads/ties in[/bold]: {excels.get(local) or 'none'}")

    if output is not None:
        output.write_text(json.dumps({
            "title": gt.get("title"), "candidates": candidates, "judge": judge_handler,
            "totals": totals, "max_points": maxpts, "per_category_best": excels,
            "rows": [{"id": r["question"]["id"], "category": r["question"]["category"],
                      "input": r["question"]["input"], "expected": r["question"]["expected"],
                      "scores": {m: int(r["scores"][m]["score"]) for m in candidates},
                      "reasons": {m: r["scores"][m]["reason"] for m in candidates},
                      "answers": {m: r["scores"][m].get("answer", "") for m in candidates},
                      "run_dirs": {m: r["scores"][m].get("run_dir", "") for m in candidates},
                      "judge_run_dirs": {m: r["scores"][m].get("judge_run_dir", "") for m in candidates}}
                     for r in rows],
        }, indent=2), encoding="utf-8")
        console.print(f"[dim]wrote {output}[/dim]")
    console.print("JUDGE_GRID_COMPLETE")
