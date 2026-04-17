"""Prompt-lab evaluation module for Heart taxonomy classification.

Evaluates BDI emotional posture (Heart) classification prompts against
ground truth with optional dual-model comparison via Cohen's kappa.
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_HEART: Set[str] = {"anger", "fear", "joy", "neutral", "sadness", "trust"}

USER_MSG_TEMPLATE = "Classify the following text:\n\n{text}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_heart_ground_truth(path: Path) -> List[dict]:
    """Load ground truth cases from heart_tagger.json."""
    gt_file = path / "heart_tagger.json"
    if not gt_file.exists():
        raise typer.BadParameter(f"Ground truth not found: {gt_file}")
    data = json.loads(gt_file.read_text())
    return data.get("cases", [])


def _load_heart_prompt(path: Path) -> str:
    """Load system prompt from prompts/heart_tagger_v1.txt."""
    prompt_file = path / "heart_tagger_v1.txt"
    if not prompt_file.exists():
        raise typer.BadParameter(f"Prompt not found: {prompt_file}")
    return prompt_file.read_text().strip()


def _call_llm(system_prompt: str, user_msg: str, model: str) -> Tuple[dict, float]:
    """Call scillm and return (parsed_json, latency_ms)."""
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
    # Parse JSON from content (handle markdown wrapping)
    raw = content
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]
    parsed = json.loads(raw.strip())
    return parsed, latency_ms


def _validate_heart_tags(raw_tags: list) -> Tuple[List[str], List[str]]:
    """Validate tags against VALID_HEART. Returns (valid, rejected)."""
    if not isinstance(raw_tags, list):
        raw_tags = [raw_tags] if raw_tags else []
    valid = [t for t in raw_tags if t in VALID_HEART]
    rejected = [t for t in raw_tags if t not in VALID_HEART]
    return valid, rejected


def _set_metrics(predicted: Set[str], expected: Set[str]) -> Tuple[float, float, float]:
    """Compute precision, recall, F1 for a single case (set-based)."""
    if not predicted and not expected:
        return 1.0, 1.0, 1.0
    if not predicted or not expected:
        return 0.0, 0.0, 0.0
    tp = len(predicted & expected)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _per_class_metrics(
    all_predicted: List[Set[str]], all_expected: List[Set[str]]
) -> Dict[str, Dict[str, float]]:
    """Compute per-class precision, recall, F1 across all cases."""
    metrics: Dict[str, Dict[str, float]] = {}
    for tag in sorted(VALID_HEART):
        tp = sum(1 for p, e in zip(all_predicted, all_expected) if tag in p and tag in e)
        fp = sum(1 for p, e in zip(all_predicted, all_expected) if tag in p and tag not in e)
        fn = sum(1 for p, e in zip(all_predicted, all_expected) if tag not in p and tag in e)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        metrics[tag] = {"precision": prec, "recall": rec, "f1": f1}
    return metrics


def _run_model(
    cases: List[dict], system_prompt: str, model: str
) -> Tuple[List[Set[str]], List[float], int]:
    """Run all cases through a model. Returns (predictions, latencies, rejected_count)."""
    predictions: List[Set[str]] = []
    latencies: List[float] = []
    total_rejected = 0

    for case in cases:
        text = case["input"]["text"]
        user_msg = USER_MSG_TEMPLATE.format(text=text)
        try:
            parsed, latency_ms = _call_llm(system_prompt, user_msg, model)
            raw_heart = parsed.get("heart", [])
            valid, rejected = _validate_heart_tags(raw_heart)
            total_rejected += len(rejected)
            predictions.append(set(valid))
            latencies.append(latency_ms)
        except Exception as e:
            console.print(f"[red]Error on case {case.get('id', '?')}: {e}[/red]")
            predictions.append(set())
            latencies.append(0.0)
            total_rejected += 1

    return predictions, latencies, total_rejected


def _compute_kappa(preds_a: List[Set[str]], preds_b: List[Set[str]]) -> float:
    """Compute Cohen's kappa between two model outputs (multi-label binarized)."""
    from sklearn.metrics import cohen_kappa_score
    import numpy as np

    tags = sorted(VALID_HEART)
    # Binarize predictions into label vectors
    vec_a = []
    vec_b = []
    for pa, pb in zip(preds_a, preds_b):
        for tag in tags:
            vec_a.append(1 if tag in pa else 0)
            vec_b.append(1 if tag in pb else 0)
    return float(cohen_kappa_score(np.array(vec_a), np.array(vec_b)))


def _save_results(
    model: str,
    cases: List[dict],
    predictions: List[Set[str]],
    per_class: Dict[str, Dict[str, float]],
    macro_f1: float,
    avg_latency: float,
    kappa: Optional[float] = None,
    compare_model: Optional[str] = None,
) -> Path:
    """Save evaluation results to results/ directory."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"heart_tagger_{model.replace('/', '_')}_{ts}.json"
    per_case = []
    for case, pred in zip(cases, predictions):
        expected = set(case["expected"]["heart"])
        _, _, f1 = _set_metrics(pred, expected)
        per_case.append({
            "id": case.get("id", ""),
            "predicted": sorted(pred),
            "expected": sorted(expected),
            "f1": round(f1, 4),
        })
    result = {
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "macro_f1": round(macro_f1, 4),
        "avg_latency_ms": round(avg_latency, 1),
        "per_class": {k: {mk: round(mv, 4) for mk, mv in v.items()} for k, v in per_class.items()},
        "per_case": per_case,
    }
    if kappa is not None:
        result["cohen_kappa"] = round(kappa, 4)
        result["compare_model"] = compare_model
    out_path.write_text(json.dumps(result, indent=2))
    return out_path


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@app.command("eval-heart")
def eval_heart(
    model: str = typer.Option("text", "--model", "-m", help="scillm model name"),
    cases_limit: int = typer.Option(0, "--cases", "-n", help="Limit cases (0=all)"),
    compare: str = typer.Option("", "--compare", "-c", help="Second model for Cohen's kappa"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
):
    """Evaluate Heart (BDI emotional posture) classification prompts.

    Runs ground truth cases through scillm, computes per-class P/R/F1
    and macro-averaged F1.  With --compare, runs a second model and
    reports Cohen's kappa for inter-model agreement.
    """
    ensure_dirs()

    system_prompt = _load_heart_prompt(PROMPTS_DIR)
    cases = _load_heart_ground_truth(GROUND_TRUTH_DIR)
    if cases_limit > 0:
        cases = cases[:cases_limit]

    console.print(f"[bold]Heart Taxonomy Eval[/bold]  model={model}  cases={len(cases)}")
    if compare:
        console.print(f"[bold]Compare model:[/bold] {compare}")
    console.print()

    # --- Primary model ---
    predictions, latencies, rejected = _run_model(cases, system_prompt, model)
    expected_sets = [set(c["expected"]["heart"]) for c in cases]

    per_class = _per_class_metrics(predictions, expected_sets)
    class_f1s = [v["f1"] for v in per_class.values()]
    macro_f1 = sum(class_f1s) / len(class_f1s) if class_f1s else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    # --- Per-class table ---
    table = Table(title=f"Per-Class Metrics ({model})")
    table.add_column("Tag", style="cyan")
    table.add_column("Precision", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("F1", justify="right")
    for tag, m in per_class.items():
        table.add_row(tag, f"{m['precision']:.3f}", f"{m['recall']:.3f}", f"{m['f1']:.3f}")
    console.print(table)

    # --- Summary table ---
    summary = Table(title="Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="green")
    summary.add_row("Macro F1", f"{macro_f1:.3f}")
    summary.add_row("Avg Latency", f"{avg_latency:.0f}ms")
    summary.add_row("Rejected Tags", str(rejected))

    # --- Optional comparison ---
    kappa: Optional[float] = None
    compare_model: Optional[str] = None
    if compare:
        console.print(f"\n[bold]Running comparison model: {compare}[/bold]")
        preds_b, lats_b, rej_b = _run_model(cases, system_prompt, compare)
        pc_b = _per_class_metrics(preds_b, expected_sets)
        cf1_b = [v["f1"] for v in pc_b.values()]
        mf1_b = sum(cf1_b) / len(cf1_b) if cf1_b else 0.0

        table_b = Table(title=f"Per-Class Metrics ({compare})")
        table_b.add_column("Tag", style="cyan")
        table_b.add_column("Precision", justify="right")
        table_b.add_column("Recall", justify="right")
        table_b.add_column("F1", justify="right")
        for tag, m in pc_b.items():
            table_b.add_row(tag, f"{m['precision']:.3f}", f"{m['recall']:.3f}", f"{m['f1']:.3f}")
        console.print(table_b)

        kappa = _compute_kappa(predictions, preds_b)
        compare_model = compare
        summary.add_row("---", "---")
        summary.add_row(f"Compare Macro F1 ({compare})", f"{mf1_b:.3f}")
        summary.add_row("Cohen's Kappa", f"{kappa:.3f}")

    console.print(summary)

    # --- Verbose per-case output ---
    if verbose:
        console.print("\n[bold]Per-Case Details[/bold]")
        detail = Table()
        detail.add_column("ID", style="dim")
        detail.add_column("Expected")
        detail.add_column("Predicted")
        detail.add_column("F1", justify="right")
        for case, pred in zip(cases, predictions):
            exp = set(case["expected"]["heart"])
            _, _, f1 = _set_metrics(pred, exp)
            style = "green" if f1 >= 0.8 else ("yellow" if f1 >= 0.5 else "red")
            detail.add_row(
                case.get("id", "?"),
                ", ".join(sorted(exp)),
                ", ".join(sorted(pred)),
                f"[{style}]{f1:.3f}[/{style}]",
            )
        console.print(detail)

    # --- Save ---
    out = _save_results(
        model=model,
        cases=cases,
        predictions=predictions,
        per_class=per_class,
        macro_f1=macro_f1,
        avg_latency=avg_latency,
        kappa=kappa,
        compare_model=compare_model,
    )
    console.print(f"\nResults saved to: {out}")

    if macro_f1 < 0.8:
        console.print(f"\n[red]QUALITY GATE FAILED: Macro F1 {macro_f1:.3f} < 0.80[/red]")
        raise typer.Exit(1)
    else:
        console.print(f"\n[green]QUALITY GATE PASSED: Macro F1 {macro_f1:.3f}[/green]")
