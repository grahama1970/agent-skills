"""Prompt-lab evaluation module for Mind rationale generation prompts.

Evaluates the GPT rationale system prompt (gpt_mind-rationale.txt) which
explains WHY a text relates to a given SPARTA tactical posture. This is the
T1.5 GPT prompt for the Mind (tactical) dimension of the Sensei Cascade.

Quality gates:
  - JSON parse rate >= 95%
  - Label echo accuracy >= 95%  (model echoes back the given label)
  - Confidence validity >= 95%  (high/medium/low only)
  - Rationale grounding >= 80%  (cites words from input text)
  - Avg rationale length >= 20 chars
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Set, Tuple

import httpx
import typer
from rich.table import Table

from config import (
    GROUND_TRUTH_DIR,
    PROMPTS_DIR,
    RESULTS_DIR,
    SCILLM_API_BASE,
    SCILLM_PROXY_KEY,
    ensure_dirs,
)
from pl_app import app, console

VALID_LABELS: Set[str] = {
    "Detect", "Evade", "Exploit", "Harden",
    "Isolate", "Model", "Persist", "Restore",
}
VALID_CONFIDENCES: Set[str] = {"high", "medium", "low"}

USER_MSG_TEMPLATE = "Text: {text}\nLabel: {label}"


def _load_rationale_ground_truth(path: Path) -> List[dict]:
    gt_file = path / "mind_rationale.json"
    if not gt_file.exists():
        raise typer.BadParameter(f"Ground truth not found: {gt_file}")
    data = json.loads(gt_file.read_text())
    return data.get("cases", [])


def _load_rationale_prompt(path: Path) -> str:
    prompt_file = path / "gpt_mind-rationale.txt"
    if not prompt_file.exists():
        raise typer.BadParameter(f"Prompt not found: {prompt_file}")
    return prompt_file.read_text().strip()


def _call_llm(system_prompt: str, user_msg: str, model: str) -> Tuple[dict, float]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": 512,
        "temperature": 0,
    }
    start = time.perf_counter()
    resp = httpx.post(
        f"{SCILLM_API_BASE}/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {SCILLM_PROXY_KEY}"},
        timeout=60.0,
    )
    latency_ms = (time.perf_counter() - start) * 1000
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    parsed = json.loads(raw)
    return parsed, latency_ms


def _check_grounding(rationale: str, source_text: str) -> bool:
    """Check if the rationale cites words from the source text."""
    if not rationale or not source_text:
        return False
    source_words = set(re.findall(r'\b\w{4,}\b', source_text.lower()))
    rationale_words = set(re.findall(r'\b\w{4,}\b', rationale.lower()))
    overlap = source_words & rationale_words
    return len(overlap) >= 2


@app.command("eval-mind-rationale")
def eval_mind_rationale(
    model: str = typer.Option("text", "--model", "-m", help="scillm model name"),
    cases_limit: int = typer.Option(0, "--cases", "-n", help="Limit cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Evaluate Mind rationale generation prompt (gpt_mind-rationale.txt).

    Tests whether the system prompt produces valid rationale JSON with
    correct label echo, valid confidence, grounded citations, and
    sufficient rationale length.
    """
    ensure_dirs()

    system_prompt = _load_rationale_prompt(PROMPTS_DIR)
    cases = _load_rationale_ground_truth(GROUND_TRUTH_DIR)
    if cases_limit > 0:
        cases = cases[:cases_limit]

    console.print(
        f"[bold]Mind Rationale Eval[/bold]  model={model}  "
        f"cases={len(cases)}  prompt=gpt_mind-rationale.txt"
    )
    console.print()

    results = []
    total_json_ok = 0
    total_label_ok = 0
    total_conf_ok = 0
    total_grounded = 0
    total_rationale_len = 0
    latencies = []

    for case in cases:
        text = case["input"]["text"]
        label = case["input"]["label"]
        user_msg = USER_MSG_TEMPLATE.format(text=text, label=label)
        case_result = {"id": case.get("id", "?"), "expected_label": label}

        try:
            parsed, latency_ms = _call_llm(system_prompt, user_msg, model)
            latencies.append(latency_ms)
            case_result["json_ok"] = True
            total_json_ok += 1

            pred_label = parsed.get("label", "")
            rationale = parsed.get("rationale", "")
            confidence = parsed.get("confidence", "")

            case_result["pred_label"] = pred_label
            case_result["rationale"] = rationale
            case_result["confidence"] = confidence

            label_ok = pred_label == label
            conf_ok = confidence in VALID_CONFIDENCES
            grounded = _check_grounding(rationale, text)
            rat_len = len(rationale)

            case_result["label_ok"] = label_ok
            case_result["conf_ok"] = conf_ok
            case_result["grounded"] = grounded
            case_result["rationale_len"] = rat_len

            if label_ok:
                total_label_ok += 1
            if conf_ok:
                total_conf_ok += 1
            if grounded:
                total_grounded += 1
            total_rationale_len += rat_len

        except Exception as e:
            console.print(f"[red]Error on {case.get('id', '?')}: {e}[/red]")
            case_result["json_ok"] = False
            case_result["error"] = str(e)
            latencies.append(0.0)

        results.append(case_result)

    n = len(cases)
    json_rate = total_json_ok / n if n else 0
    label_rate = total_label_ok / n if n else 0
    conf_rate = total_conf_ok / n if n else 0
    ground_rate = total_grounded / n if n else 0
    avg_len = total_rationale_len / n if n else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    # Summary table
    summary = Table(title=f"Mind Rationale Eval Summary ({model})")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="green")
    summary.add_column("Gate", style="yellow")
    summary.add_column("Status")

    def _gate(val: float, threshold: float) -> str:
        return "[green]PASS[/green]" if val >= threshold else "[red]FAIL[/red]"

    summary.add_row("JSON Parse Rate", f"{json_rate:.1%}", ">=95%", _gate(json_rate, 0.95))
    summary.add_row("Label Echo Accuracy", f"{label_rate:.1%}", ">=95%", _gate(label_rate, 0.95))
    summary.add_row("Confidence Validity", f"{conf_rate:.1%}", ">=95%", _gate(conf_rate, 0.95))
    summary.add_row("Rationale Grounding", f"{ground_rate:.1%}", ">=80%", _gate(ground_rate, 0.80))
    summary.add_row("Avg Rationale Length", f"{avg_len:.0f} chars", ">=20", _gate(avg_len / 20, 1.0))
    summary.add_row("Avg Latency", f"{avg_latency:.0f}ms", "", "")
    console.print(summary)

    # Per-class breakdown
    by_label = {}
    for r in results:
        lbl = r["expected_label"]
        by_label.setdefault(lbl, []).append(r)

    breakdown = Table(title="Per-Class Breakdown")
    breakdown.add_column("Label", style="cyan")
    breakdown.add_column("Cases", justify="right")
    breakdown.add_column("JSON%", justify="right")
    breakdown.add_column("Label%", justify="right")
    breakdown.add_column("Ground%", justify="right")
    for lbl in sorted(by_label):
        rs = by_label[lbl]
        cnt = len(rs)
        j = sum(1 for r in rs if r.get("json_ok")) / cnt
        l_acc = sum(1 for r in rs if r.get("label_ok")) / cnt
        g = sum(1 for r in rs if r.get("grounded")) / cnt
        breakdown.add_row(lbl, str(cnt), f"{j:.0%}", f"{l_acc:.0%}", f"{g:.0%}")
    console.print(breakdown)

    # Verbose per-case
    if verbose:
        console.print("\n[bold]Per-Case Details[/bold]")
        detail = Table()
        detail.add_column("ID", style="dim")
        detail.add_column("Label")
        detail.add_column("JSON")
        detail.add_column("Echo")
        detail.add_column("Conf")
        detail.add_column("Grnd")
        detail.add_column("Rationale", max_width=60)
        for r in results:
            if not r.get("json_ok"):
                detail.add_row(
                    r["id"], r["expected_label"],
                    "[red]FAIL[/red]", "", "", "", r.get("error", "")[:60],
                )
                continue
            detail.add_row(
                r["id"],
                r["expected_label"],
                "[green]OK[/green]",
                "[green]OK[/green]" if r.get("label_ok") else f"[red]{r.get('pred_label')}[/red]",
                "[green]OK[/green]" if r.get("conf_ok") else f"[red]{r.get('confidence')}[/red]",
                "[green]OK[/green]" if r.get("grounded") else "[red]NO[/red]",
                (r.get("rationale", "")[:60] + "...") if len(r.get("rationale", "")) > 60 else r.get("rationale", ""),
            )
        console.print(detail)

    # Save results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"mind_rationale_{model.replace('/', '_')}_{ts}.json"
    out_data = {
        "model": model,
        "prompt": "gpt_mind-rationale.txt",
        "ground_truth": "mind_rationale.json",
        "cases": len(cases),
        "metrics": {
            "json_parse_rate": round(json_rate, 4),
            "label_echo_accuracy": round(label_rate, 4),
            "confidence_validity": round(conf_rate, 4),
            "rationale_grounding": round(ground_rate, 4),
            "avg_rationale_length": round(avg_len, 1),
            "avg_latency_ms": round(avg_latency, 1),
        },
        "gates": {
            "json_parse": json_rate >= 0.95,
            "label_echo": label_rate >= 0.95,
            "confidence": conf_rate >= 0.95,
            "grounding": ground_rate >= 0.80,
        },
        "passed": all([
            json_rate >= 0.95,
            label_rate >= 0.95,
            conf_rate >= 0.95,
            ground_rate >= 0.80,
        ]),
        "results": results,
    }
    out_path.write_text(json.dumps(out_data, indent=2, default=str))
    console.print(f"\nResults saved: {out_path}")

    passed = out_data["passed"]
    if passed:
        console.print("[bold green]ALL GATES PASSED[/bold green]")
    else:
        failed = [k for k, v in out_data["gates"].items() if not v]
        console.print(f"[bold red]GATES FAILED: {', '.join(failed)}[/bold red]")

    raise typer.Exit(code=0 if passed else 1)
