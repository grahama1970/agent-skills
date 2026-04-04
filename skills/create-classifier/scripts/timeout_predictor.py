#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.12.3",
#   "loguru>=0.7.0",
#   "scikit-learn>=1.3.0",
#   "joblib>=1.3.0",
# ]
# ///
"""Train and serve a timeout-risk classifier for PDF extraction.

Purpose:
- learn timeout risk from review-pdf extraction events.
- provide fast inference for review-pdf timeout adaptation.

Inputs:
- review-pdf aggregate reports with extraction_events.

Outputs:
- model artifact and JSON prediction payload.

Failure modes:
- deterministic non-zero exits for missing model/data.
"""

from __future__ import annotations
import os

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Tuple

import joblib
from loguru import logger
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_REPORTS_ROOT = _SKILLS_DIR / "review-pdf" / "reports"
DEFAULT_LEARN_DATALAKE_RUN_LOGS = _SKILLS_DIR / "learn-datalake" / "state" / "runs"
DEFAULT_MODEL_DIR = _SKILLS_DIR / "create-classifier" / "models" / "timeout_predictor"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "model.joblib"
CLASSIFIER_LAB_DIR = _SKILLS_DIR / "classifier-lab"
DEFAULT_BASELINE_TIMEOUT_SECONDS = 7200
DEFAULT_TIMEOUT_SOURCE = "unknown"

STRUCTURAL_INT_FIELDS = (
    "step00_estimated_sections",
    "step00_estimated_sections_regex",
    "step00_estimated_sections_font",
    "step00_estimated_sections_toc",
    "step00_estimated_table_count",
    "step00_table_pages",
    "step00_image_pages",
    "step00_max_tables_per_page",
    "step00_table_pages_drawing",
)
STRUCTURAL_BOOL_FIELDS = (
    "step00_has_formulas",
    "step00_has_figures",
    "step00_has_requirements",
    "step00_has_tables",
    "step00_has_structure",
)
HISTORY_INT_FIELDS = (
    "history_pdf_attempts",
    "history_pdf_timeout_count",
    "history_pdf_last_timeout_seconds",
    "history_pdf_avg_timeout_seconds",
    "history_page_bucket_attempts",
    "history_page_bucket_timeout_count",
    "history_page_bucket_last_timeout_seconds",
    "history_page_bucket_avg_timeout_seconds",
)
HISTORY_FLOAT_FIELDS = (
    "history_pdf_timeout_rate",
    "history_page_bucket_timeout_rate",
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _file_size_mb(pdf_path: str) -> float:
    if not pdf_path:
        return 0.0
    path = Path(pdf_path)
    if not path.exists():
        return 0.0
    try:
        return round(path.stat().st_size / (1024.0 * 1024.0), 4)
    except OSError:
        return 0.0


def _build_feature_row(
    *,
    page_count: int,
    step00_estimated_timeout_seconds: int,
    baseline_timeout_seconds: int,
    timeout_source: str,
    pdf_path: str,
    extras: Dict[str, Any],
) -> Dict[str, Any]:
    features: Dict[str, Any] = {
        "page_count": max(0, int(page_count)),
        "step00_estimated_timeout_seconds": max(0, int(step00_estimated_timeout_seconds)),
        "baseline_timeout_seconds": max(0, int(baseline_timeout_seconds)),
        "pdf_size_mb": _file_size_mb(pdf_path),
        f"timeout_source={timeout_source or DEFAULT_TIMEOUT_SOURCE}": 1.0,
    }
    for key in STRUCTURAL_INT_FIELDS + HISTORY_INT_FIELDS:
        features[key] = max(0, _safe_int(extras.get(key), 0))
    for key in HISTORY_FLOAT_FIELDS:
        features[key] = max(0.0, _safe_float(extras.get(key), 0.0))
    for key in STRUCTURAL_BOOL_FIELDS:
        features[key] = 1.0 if _safe_bool(extras.get(key), False) else 0.0
    return features


def _event_to_row(event: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, int | None]:
    status = str(event.get("status") or "")
    timed_out = bool(event.get("extract_timed_out"))
    if status not in {"extracted", "extract_failed"}:
        return None, None

    page_count = _safe_int(event.get("step00_page_count"), 0)
    step00_est = _safe_int(event.get("step00_estimated_timeout_seconds"), 0)
    timeout_seconds = _safe_int(event.get("timeout_seconds"), 0)
    timeout_source = str(event.get("step00_timeout_source") or "unknown")
    pdf_path = str(event.get("pdf") or "")
    features = _build_feature_row(
        page_count=page_count,
        step00_estimated_timeout_seconds=step00_est,
        baseline_timeout_seconds=timeout_seconds,
        timeout_source=timeout_source,
        pdf_path=pdf_path,
        extras=event,
    )
    if status == "extracted":
        label = 0
    else:
        label = 1 if timed_out else 0
    return features, label


def _parse_key_value_line(line: str, prefix: str) -> Dict[str, str] | None:
    text = line.strip()
    if not text.startswith(prefix):
        return None
    payload = text[len(prefix) :].strip()
    parsed: Dict[str, str] = {}
    body = payload
    if " pdf=" in payload:
        body, pdf_value = payload.rsplit(" pdf=", 1)
        parsed["pdf"] = pdf_value.strip()
    for token in body.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _load_rows_from_reports(reports_root: Path) -> Tuple[List[Dict[str, Any]], List[int], int]:
    feature_rows: List[Dict[str, Any]] = []
    labels: List[int] = []
    aggregate_files = sorted(reports_root.rglob("aggregate.json"))
    for aggregate_path in aggregate_files:
        try:
            payload = json.loads(aggregate_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        events = payload.get("extraction_events")
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            row, label = _event_to_row(event)
            if row is None or label is None:
                continue
            feature_rows.append(row)
            labels.append(label)
    return feature_rows, labels, len(aggregate_files)


def _load_rows_from_run_logs(
    run_logs_root: Path,
) -> Tuple[List[Dict[str, Any]], List[int], int, int]:
    feature_rows: List[Dict[str, Any]] = []
    labels: List[int] = []
    missing_policy_rows = 0
    log_files = sorted(run_logs_root.glob("learn_datalake_*.log"))
    for log_file in log_files:
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        last_policy_by_pdf: Dict[str, Dict[str, Any]] = {}
        for line in lines:
            policy = _parse_key_value_line(line, "review-pdf extract_timeout ")
            if policy:
                pdf = str(policy.get("pdf") or "").strip()
                if not pdf:
                    continue
                timeout_source = str(policy.get("source") or DEFAULT_TIMEOUT_SOURCE).strip()
                row_policy: Dict[str, Any] = {
                    "page_count": _safe_int(policy.get("page_count"), 0),
                    "step00_estimated_timeout_seconds": _safe_int(
                        policy.get("step00_estimated"), 0
                    ),
                    "baseline_timeout_seconds": _safe_int(policy.get("seconds"), 0),
                    "timeout_source": timeout_source,
                    "pdf_size_mb": _file_size_mb(pdf),
                }
                for key in STRUCTURAL_INT_FIELDS + HISTORY_INT_FIELDS + HISTORY_FLOAT_FIELDS:
                    row_policy[key] = policy.get(key)
                for key in STRUCTURAL_BOOL_FIELDS:
                    row_policy[key] = policy.get(key)
                last_policy_by_pdf[pdf] = row_policy
                continue
            outcome = _parse_key_value_line(line, "review-pdf extract_missing ")
            if not outcome:
                continue
            status = str(outcome.get("status") or "").strip()
            if status not in {"extracted", "extract_failed"}:
                continue
            pdf = str(outcome.get("pdf") or "").strip()
            if not pdf:
                continue
            policy = last_policy_by_pdf.get(pdf)
            if policy is None:
                missing_policy_rows += 1
                policy = {
                    "page_count": 0,
                    "step00_estimated_timeout_seconds": 0,
                    "baseline_timeout_seconds": DEFAULT_BASELINE_TIMEOUT_SECONDS,
                    "timeout_source": DEFAULT_TIMEOUT_SOURCE,
                    "pdf_size_mb": _file_size_mb(pdf),
                }
                for key in STRUCTURAL_INT_FIELDS + HISTORY_INT_FIELDS:
                    policy[key] = 0
                for key in HISTORY_FLOAT_FIELDS:
                    policy[key] = 0.0
                for key in STRUCTURAL_BOOL_FIELDS:
                    policy[key] = False
            timed_out = _safe_bool(outcome.get("timed_out"), False)
            label = 1 if (status == "extract_failed" and timed_out) else 0
            row = _build_feature_row(
                page_count=_safe_int(policy.get("page_count"), 0),
                step00_estimated_timeout_seconds=_safe_int(
                    policy.get("step00_estimated_timeout_seconds"), 0
                ),
                baseline_timeout_seconds=_safe_int(policy.get("baseline_timeout_seconds"), 0),
                timeout_source=str(policy.get("timeout_source") or DEFAULT_TIMEOUT_SOURCE),
                pdf_path=pdf,
                extras=policy,
            )
            feature_rows.append(row)
            labels.append(label)
    return feature_rows, labels, len(log_files), missing_policy_rows


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * q))))
    return float(ordered[index])


def _label_counts(labels: List[int]) -> Dict[str, int]:
    positives = int(sum(1 for item in labels if int(item) == 1))
    negatives = int(sum(1 for item in labels if int(item) == 0))
    return {
        "sample_count": int(len(labels)),
        "positive_count": positives,
        "negative_count": negatives,
    }


def _run_classifier_lab_benchmark(
    *,
    labels_jsonl: Path,
    backbones: str,
    timeout_seconds: int,
) -> Dict[str, Any]:
    if not CLASSIFIER_LAB_DIR.exists():
        return {"status": "skipped", "reason": "classifier_lab_missing"}
    if not labels_jsonl.exists():
        return {"status": "skipped", "reason": "labels_jsonl_missing"}
    cmd = (
        f"cd {CLASSIFIER_LAB_DIR} && ./run.sh benchmark "
        f"--labels-jsonl {json.dumps(str(labels_jsonl))} "
        f"--backbones {json.dumps(backbones)} "
        "--epochs 1 --max-steps 60 --store-memory --require-memory-store"
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "timeout"}
    status = "ok" if proc.returncode == 0 else "failed"
    return {
        "status": status,
        "returncode": proc.returncode,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-30:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
    }


@app.command("train")
def train_model(
    reports_root: Path = typer.Option(DEFAULT_REPORTS_ROOT, exists=True, file_okay=False),
    run_logs_root: Path = typer.Option(DEFAULT_LEARN_DATALAKE_RUN_LOGS, exists=False, file_okay=False),
    output_dir: Path = typer.Option(DEFAULT_MODEL_DIR),
    min_samples: int = typer.Option(100, min=20),
    test_size: float = typer.Option(0.2, min=0.05, max=0.4),
    classifier_lab_first: bool = typer.Option(
        True, help="Run classifier-lab benchmark first when labels JSONL is provided"
    ),
    classifier_lab_labels_jsonl: Path | None = typer.Option(
        None, help="Optional image-label JSONL for classifier-lab benchmark"
    ),
    classifier_lab_backbones: str = typer.Option(
        "efficientnet_b0,convnextv2_nano.fcmae_ft_in22k_in1k,mobilenetv3_large_100",
        help="Backbones passed to classifier-lab benchmark",
    ),
    classifier_lab_timeout_seconds: int = typer.Option(1200, min=120),
    allow_weak_bootstrap_labels: bool = typer.Option(
        True,
        help="If labels collapse to one class, bootstrap weak labels from high-cost samples",
    ),
) -> None:
    """Train timeout-risk classifier from review-pdf aggregate reports."""
    rows, labels, report_count = _load_rows_from_reports(reports_root)
    run_log_count = 0
    missing_policy_rows = 0
    if run_logs_root.exists():
        log_rows, log_labels, run_log_count, missing_policy_rows = _load_rows_from_run_logs(
            run_logs_root
        )
        rows.extend(log_rows)
        labels.extend(log_labels)
    sample_count = len(rows)
    positives = sum(labels)
    negatives = sample_count - positives
    if sample_count < min_samples:
        raise typer.BadParameter(
            f"insufficient samples: sample_count={sample_count} min_samples={min_samples}"
        )
    weak_labeling_applied = False
    if positives == 0 or negatives == 0:
        if not allow_weak_bootstrap_labels:
            raise typer.BadParameter(
                f"class collapse: positives={positives} negatives={negatives}"
            )
        # Rank-based weak labels: mark top 20% highest-cost samples as timeout-prone.
        ranked = sorted(
            enumerate(rows),
            key=lambda item: (
                _safe_float(item[1].get("baseline_timeout_seconds"), 0.0),
                _safe_float(item[1].get("page_count"), 0.0),
                _safe_float(item[1].get("pdf_size_mb"), 0.0),
                item[0],
            ),
        )
        top_k = max(1, min(len(ranked) - 1, int(round(len(ranked) * 0.20))))
        positive_indices = {index for index, _ in ranked[-top_k:]}
        boot_labels = [1 if idx in positive_indices else 0 for idx in range(len(rows))]
        boot_positives = sum(boot_labels)
        boot_negatives = len(boot_labels) - boot_positives
        if boot_positives == 0 or boot_negatives == 0:
            raise typer.BadParameter(
                "class collapse persists after weak bootstrap labeling "
                f"(positives={boot_positives} negatives={boot_negatives})"
            )
        labels = boot_labels
        positives = boot_positives
        negatives = boot_negatives
        weak_labeling_applied = True

    classifier_lab_result: Dict[str, Any] = {"status": "skipped", "reason": "not_requested"}
    if classifier_lab_first:
        if classifier_lab_labels_jsonl is not None:
            classifier_lab_result = _run_classifier_lab_benchmark(
                labels_jsonl=classifier_lab_labels_jsonl,
                backbones=classifier_lab_backbones,
                timeout_seconds=classifier_lab_timeout_seconds,
            )
        else:
            classifier_lab_result = {
                "status": "skipped",
                "reason": "no_classifier_lab_labels_jsonl",
            }

    vectorizer = DictVectorizer(sparse=True)
    x = vectorizer.fit_transform(rows)
    y = labels
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=test_size,
        random_state=42,
        stratify=y,
    )
    classifier = LogisticRegression(
        max_iter=600,
        class_weight="balanced",
        n_jobs=None,
        random_state=42,
    )
    classifier.fit(x_train, y_train)
    prob = classifier.predict_proba(x_test)[:, 1]
    pred = (prob >= 0.5).astype(int)
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, pred)), 4),
        "f1": round(float(f1_score(y_test, pred)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, prob)), 4),
        "sample_count": sample_count,
        "positive_count": positives,
        "negative_count": negatives,
        "report_files_scanned": report_count,
        "run_logs_scanned": run_log_count,
        "run_logs_missing_policy_rows": missing_policy_rows,
        "weak_labeling_applied": weak_labeling_applied,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.joblib"
    summary_path = output_dir / "training_summary.json"
    model_payload = {
        "vectorizer": vectorizer,
        "classifier": classifier,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "feature_names": list(vectorizer.get_feature_names_out()),
    }
    joblib.dump(model_payload, model_path)
    summary_path.write_text(
        json.dumps(
            {
                "model_path": str(model_path),
                "summary_path": str(summary_path),
                "metrics": metrics,
                "classifier_lab": classifier_lab_result,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(
        "timeout predictor trained "
        f"sample_count={sample_count} positives={positives} "
        f"roc_auc={metrics['roc_auc']}"
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "model_path": str(model_path),
                "summary_path": str(summary_path),
                "metrics": metrics,
                "classifier_lab": classifier_lab_result,
            }
        )
    )


@app.command("stats")
def dataset_stats(
    reports_root: Path = typer.Option(DEFAULT_REPORTS_ROOT, exists=True, file_okay=False),
    run_logs_root: Path = typer.Option(DEFAULT_LEARN_DATALAKE_RUN_LOGS, exists=False, file_okay=False),
) -> None:
    """Report timeout-training label distribution for reports and run logs."""
    report_rows, report_labels, report_files = _load_rows_from_reports(reports_root)
    log_rows: List[Dict[str, Any]] = []
    log_labels: List[int] = []
    log_files = 0
    missing_policy_rows = 0
    if run_logs_root.exists():
        log_rows, log_labels, log_files, missing_policy_rows = _load_rows_from_run_logs(
            run_logs_root
        )
    merged_labels = list(report_labels) + list(log_labels)
    payload = {
        "status": "ok",
        "reports_root": str(reports_root),
        "run_logs_root": str(run_logs_root),
        "reports": {
            "files_scanned": int(report_files),
            **_label_counts(report_labels),
        },
        "run_logs": {
            "files_scanned": int(log_files),
            "missing_policy_rows": int(missing_policy_rows),
            **_label_counts(log_labels),
        },
        "merged": _label_counts(merged_labels),
    }
    print(json.dumps(payload))


@app.command("predict")
def predict_timeout_risk(
    page_count: int = typer.Option(0, min=0),
    step00_estimated_timeout_seconds: int = typer.Option(0, min=0),
    baseline_timeout_seconds: int = typer.Option(0, min=0),
    timeout_source: str = typer.Option("unknown"),
    step00_estimated_sections: int = typer.Option(0, min=0),
    step00_estimated_sections_regex: int = typer.Option(0, min=0),
    step00_estimated_sections_font: int = typer.Option(0, min=0),
    step00_estimated_sections_toc: int = typer.Option(0, min=0),
    step00_estimated_table_count: int = typer.Option(0, min=0),
    step00_table_pages: int = typer.Option(0, min=0),
    step00_image_pages: int = typer.Option(0, min=0),
    step00_max_tables_per_page: int = typer.Option(0, min=0),
    step00_table_pages_drawing: int = typer.Option(0, min=0),
    step00_has_formulas: int = typer.Option(0, min=0, max=1),
    step00_has_figures: int = typer.Option(0, min=0, max=1),
    step00_has_requirements: int = typer.Option(0, min=0, max=1),
    step00_has_tables: int = typer.Option(0, min=0, max=1),
    step00_has_structure: int = typer.Option(0, min=0, max=1),
    history_pdf_attempts: int = typer.Option(0, min=0),
    history_pdf_timeout_count: int = typer.Option(0, min=0),
    history_pdf_timeout_rate: float = typer.Option(0.0, min=0.0),
    history_pdf_last_timeout_seconds: int = typer.Option(0, min=0),
    history_pdf_avg_timeout_seconds: int = typer.Option(0, min=0),
    history_page_bucket_attempts: int = typer.Option(0, min=0),
    history_page_bucket_timeout_count: int = typer.Option(0, min=0),
    history_page_bucket_timeout_rate: float = typer.Option(0.0, min=0.0),
    history_page_bucket_last_timeout_seconds: int = typer.Option(0, min=0),
    history_page_bucket_avg_timeout_seconds: int = typer.Option(0, min=0),
    pdf: Path | None = typer.Option(None),
    model_path: Path = typer.Option(DEFAULT_MODEL_PATH),
) -> None:
    """Predict timeout risk probability from extraction context."""
    if not model_path.exists():
        raise typer.BadParameter(f"model missing: {model_path}")

    model_payload = joblib.load(model_path)
    vectorizer = model_payload["vectorizer"]
    classifier = model_payload["classifier"]
    pdf_path = str(pdf) if pdf else ""
    extras: Dict[str, Any] = {
        "step00_estimated_sections": step00_estimated_sections,
        "step00_estimated_sections_regex": step00_estimated_sections_regex,
        "step00_estimated_sections_font": step00_estimated_sections_font,
        "step00_estimated_sections_toc": step00_estimated_sections_toc,
        "step00_estimated_table_count": step00_estimated_table_count,
        "step00_table_pages": step00_table_pages,
        "step00_image_pages": step00_image_pages,
        "step00_max_tables_per_page": step00_max_tables_per_page,
        "step00_table_pages_drawing": step00_table_pages_drawing,
        "step00_has_formulas": step00_has_formulas,
        "step00_has_figures": step00_has_figures,
        "step00_has_requirements": step00_has_requirements,
        "step00_has_tables": step00_has_tables,
        "step00_has_structure": step00_has_structure,
        "history_pdf_attempts": history_pdf_attempts,
        "history_pdf_timeout_count": history_pdf_timeout_count,
        "history_pdf_timeout_rate": history_pdf_timeout_rate,
        "history_pdf_last_timeout_seconds": history_pdf_last_timeout_seconds,
        "history_pdf_avg_timeout_seconds": history_pdf_avg_timeout_seconds,
        "history_page_bucket_attempts": history_page_bucket_attempts,
        "history_page_bucket_timeout_count": history_page_bucket_timeout_count,
        "history_page_bucket_timeout_rate": history_page_bucket_timeout_rate,
        "history_page_bucket_last_timeout_seconds": history_page_bucket_last_timeout_seconds,
        "history_page_bucket_avg_timeout_seconds": history_page_bucket_avg_timeout_seconds,
    }
    features = _build_feature_row(
        page_count=page_count,
        step00_estimated_timeout_seconds=step00_estimated_timeout_seconds,
        baseline_timeout_seconds=baseline_timeout_seconds,
        timeout_source=timeout_source,
        pdf_path=pdf_path,
        extras=extras,
    )
    x = vectorizer.transform([features])
    risk = float(classifier.predict_proba(x)[0][1])
    payload = {
        "status": "ok",
        "timeout_risk": round(risk, 6),
        "model_path": str(model_path),
        "trained_at": model_payload.get("trained_at"),
        "metrics": model_payload.get("metrics", {}),
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    app()
