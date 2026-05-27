"""Escalation planning and execution for review-pdf.

Purpose:
- map issue signatures to helper-skill commands and optional auto-execution.

Inputs:
- issue list plus run/pdf paths.

Outputs:
- deduplicated escalation jobs and optional execution traces.

Failure modes:
- subprocess failures are captured in results and do not crash audit by default.
"""
from __future__ import annotations
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()



import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Set

from .models import EscalationJob, Issue

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent


def escalation_jobs(
    issues: List[Issue],
    pdf_path: Path | None,
    run_dir: Path,
    estimates: Dict[str, Any] | None = None,
) -> List[EscalationJob]:
    """Generate helper-skill escalation jobs from issue signatures.

    Args:
        estimates: Optional S00 profile estimates dict (domain, layout_columns,
            table_count, has_tables, has_formulas, etc.) for S00-aware routing.
    """
    issue_codes: Set[str] = {issue.code for issue in issues}
    jobs: List[EscalationJob] = []
    quoted_pdf = f'"{pdf_path}"' if pdf_path else '""'
    quoted_run = f'"{run_dir}"'
    est = estimates or {}
    # pdf-lab question book for deferred human-in-the-loop (set by learn-datalake)
    qbook = os.environ.get("PDF_LAB_QUESTION_BOOK", "")
    qbook_flag = f' --question-book "{qbook}"' if qbook else ""

    # S00 hints for table-lab: table_pages and layout_columns help the skill
    # choose better Camelot strategies (lattice for ruled pages, stream for
    # multi-column layouts).
    _table_pages = est.get("table_pages", 0)
    _layout_cols = est.get("layout_columns", 1)
    _table_hints = ""
    if _table_pages > 0:
        _table_hints += f" --table-pages {_table_pages}"
    if _layout_cols >= 2:
        _table_hints += " --multi-column"

    # Pass preset and category so table-lab saves hints AND stores them in
    # /memory for S05 to recall on future extractions of similar PDFs.
    _preset = est.get("preset_match", {}).get("matched", "") or est.get("detected_preset", "")
    _domain = est.get("domain", "")
    _preset_flag = f" --preset {_preset}" if _preset else ""
    _category_flag = f" --category {_domain}" if _domain else ""

    if {"table_recall_critical", "table_recall_low"} & issue_codes:
        # Skip table-lab when S00 has_tables is False — the table_recall issue
        # is from S00 estimator noise (e.g. counting ruled lines as tables), not
        # a genuine table extraction failure.
        _skip_table_lab = est.get("has_tables") is False and est.get("estimated_table_count", 0) > 0
        if not _skip_table_lab:
            jobs.append(
                EscalationJob(
                    skill="table-lab",
                    command=(
                        f"cd {_SKILLS_DIR}/table-lab && "
                        f"./run.sh tune {quoted_pdf} --converge --json{_preset_flag}{_category_flag}{qbook_flag}{_table_hints}"
                    ),
                    reason="table recall issues require strategy tuning",
                    auto_executable=bool(pdf_path),
                )
            )
        jobs.append(
            EscalationJob(
                skill="create-table-classifier",
                command=(
                    f"cd {_SKILLS_DIR}/create-table-classifier && "
                    "./run.sh self-improve"
                ),
                reason="table failures persisted; trigger classifier self-improvement",
                auto_executable=True,
            )
        )

    # Section estimation drift → /debug-pdf for structural analysis.
    # Covers both S00 overestimation (ratio < 0.5) and underestimation
    # (ratio > 3.0).  /debug-pdf diagnoses whether the issue is S00
    # calibration or S04 over/under-segmentation.
    if {"section_alignment_critical", "section_alignment_low", "section_oversegmentation"} & issue_codes:
        jobs.append(
            EscalationJob(
                skill="debug-pdf",
                command=(
                    f"cd {_SKILLS_DIR}/debug-pdf && "
                    f"./run.sh analyze {quoted_pdf} --output {quoted_run}/review_debug_pdf.json"
                ),
                reason="section alignment issues require PDF structural analysis via /debug-pdf",
                auto_executable=bool(pdf_path),
            )
        )

    if {
        "section_alignment_critical",
        "section_alignment_low",
        "section_oversegmentation",
        "unknown_element_type",
        "equation_recall_critical",
        "math_symbol_loss",
    } & issue_codes:
        jobs.append(
            EscalationJob(
                skill="create-classifier",
                command=(
                    f"cd {_SKILLS_DIR}/create-classifier && "
                    "./run.sh train-iterative "
                    "--task structural_elements "
                    "--model efficientnet_b0 "
                    "--labels data/labels/structural.jsonl "
                    "--output-dir models/structural_elements/latest "
                    "--benchmark-first "
                    "--classifier-lab-first "
                    "--require-classifier-lab "
                    "--require-selection-pass "
                    "--run-preflight-assess "
                    "--dogpile-when-uncertain "
                    "--auto-hf-augment "
                    "--run-hp-search"
                ),
                reason="section/equation/type errors suggest classifier drift",
                auto_executable=True,
            )
        )
        jobs.append(
            EscalationJob(
                skill="classifier-lab",
                command=(
                    f"cd {_SKILLS_DIR}/classifier-lab && "
                    "./run.sh benchmark "
                    f"--labels-jsonl {_SKILLS_DIR}/create-classifier/data/labels/structural.jsonl "
                    "--backbones 'efficientnet_b0,convnextv2_nano.fcmae_ft_in22k_in1k,mobilenetv3_large_100,resnet50' "
                    f"--output-json {quoted_run}/classifier_lab_benchmark.json"
                ),
                reason="backbone benchmark needed for next classifier iteration",
                auto_executable=True,
            )
        )

    if {"content_coverage_critical", "content_coverage_low"} & issue_codes:
        jobs.append(
            EscalationJob(
                skill="debug-pdf",
                command=(
                    f"cd {_SKILLS_DIR}/debug-pdf && "
                    f"./run.sh analyze {quoted_pdf} --output {quoted_run}/review_debug_pdf.json"
                ),
                reason="content coverage loss requires PDF failure diagnostics",
                auto_executable=bool(pdf_path),
            )
        )
        jobs.append(
            EscalationJob(
                skill="create-pdf-fixture",
                command=(
                    f"cd {_SKILLS_DIR}/create-pdf-fixture && "
                    f"./run.sh --source {quoted_pdf} --out {quoted_run}/fixture_repro.pdf"
                ),
                reason="generate targeted reproduction fixture for persistent extraction loss",
                auto_executable=False,
            )
        )
        jobs.append(
            EscalationJob(
                skill="fixture-tricky",
                command=(
                    f"cd {_SKILLS_DIR}/fixture-tricky && "
                    f"./run.sh gauntlet --output {quoted_run}/fixture_gauntlet.pdf"
                ),
                reason="augment regression coverage with adversarial fixture variants",
                auto_executable=False,
            )
        )

    if {"bbox_order_violation", "sort_order_violation"} & issue_codes:
        jobs.append(
            EscalationJob(
                skill="pdf-screenshot",
                command=(
                    f"cd {_SKILLS_DIR}/pdf-screenshot && "
                    f"./run.sh {quoted_pdf} --page 0 --output {quoted_run}/review_page0.png"
                ),
                reason="ordering failures require visual layout inspection",
                auto_executable=bool(pdf_path),
            )
        )

    if {"math_symbol_loss", "equation_recall_critical"} & issue_codes:
        jobs.append(
            EscalationJob(
                skill="prompt-lab",
                command=(
                    f"cd {_SKILLS_DIR}/prompt-lab && "
                    "./run.sh eval --prompt equation_v1 --model deepseek --max-corrections 2"
                ),
                reason="math extraction quality indicates prompt evaluation is needed",
                auto_executable=True,
            )
        )
        jobs.append(
            EscalationJob(
                skill="create-intent-map",
                command=(
                    f"cd {_SKILLS_DIR}/create-intent-map && "
                    "./run.sh variations --limit 500"
                ),
                reason="refresh classifier/prompt intent variations for math/equation classes",
                auto_executable=False,
            )
        )

    if {"empty_elements_high", "duplicate_content_high", "unknown_element_type"} & issue_codes:
        jobs.append(
            EscalationJob(
                skill="normalize",
                command=(
                    f"cd {_SKILLS_DIR}/normalize && "
                    f"./run.sh {quoted_pdf} --output {quoted_run}/normalized_preview.txt"
                ),
                reason="probe unicode/encoding artifacts causing empty or duplicated blocks",
                auto_executable=bool(pdf_path),
            )
        )

    if {"section_alignment_critical", "content_coverage_critical", "bbox_order_violation"} & issue_codes:
        jobs.append(
            EscalationJob(
                skill="fetcher",
                command=(
                    f"cd {_SKILLS_DIR}/fetcher && "
                    "./run.sh health"
                ),
                reason="ensure source retrieval path is healthy before extraction debugging",
                auto_executable=False,
            )
        )
        jobs.append(
            EscalationJob(
                skill="extractor",
                command=(
                    f"cd {_SKILLS_DIR}/extractor && "
                    f"./run.sh {quoted_pdf} --offline --learn --out {quoted_run}/extractor_rerun"
                ),
                reason="rerun extractor in deterministic mode to confirm reproducibility",
                auto_executable=bool(pdf_path),
            )
        )

    if {"table_recall_critical", "content_coverage_critical"} & issue_codes:
        jobs.append(
            EscalationJob(
                skill="create-table",
                command=(
                    f"cd {_SKILLS_DIR}/create-table && "
                    f"./run.sh --rows 20 --cols 6 --output {quoted_run}/synthetic_table.pdf"
                ),
                reason="produce controlled table fixtures for extraction regression tests",
                auto_executable=False,
            )
        )

    dedup: Dict[str, EscalationJob] = {}
    for job in jobs:
        dedup[job.command] = job
    return list(dedup.values())


def run_jobs(jobs: List[EscalationJob], max_jobs: int = 3) -> List[Dict[str, Any]]:
    """Execute auto-executable jobs with bounded fanout."""
    results: List[Dict[str, Any]] = []
    executed = 0
    for job in jobs:
        if not job.auto_executable:
            results.append(
                {"command": job.command, "status": "skipped", "reason": "not_auto_executable"}
            )
            continue
        if executed >= max_jobs:
            results.append({"command": job.command, "status": "skipped", "reason": "max_jobs_reached"})
            continue
        proc = subprocess.run(
            ["bash", "-lc", job.command],
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        executed += 1
        results.append(
            {
                "command": job.command,
                "status": "ok" if proc.returncode == 0 else "failed",
                "returncode": proc.returncode,
                "stdout_tail": "\n".join(proc.stdout.splitlines()[-12:]),
                "stderr_tail": "\n".join(proc.stderr.splitlines()[-12:]),
            }
        )
    return results
