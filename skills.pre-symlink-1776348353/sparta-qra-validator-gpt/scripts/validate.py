"""SPARTA QRA Validator GPT — Automated quality validation with teacher-student learning.

Brandon (persona via /scillm) does the FULL semantic assessment:
- Reasoning quality, taxonomy correctness, relevance/usefulness
- Question paraphrasing (similar questions), answer paraphrasing
- Structural checks (anchoring, grounding, citations, space terms)

The GPT learns from ALL of Brandon's output. For "maybe" grey areas
(low confidence from GPT), we escalate to /scillm with Brandon persona.

Usage:
    python validate.py heuristic --run-id run-recovery-verify [--limit 1000]
    python validate.py validate --run-id run-recovery-verify [--limit 1000]
    python validate.py validate-loop --run-id run-recovery-verify [--sample-rate 0.05]
    python validate.py status
    python validate.py export-disagreements [--output disagreements.jsonl]
"""
from __future__ import annotations

import json
import os
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

import duckdb
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

# Add memory project to path for graph_memory imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
MEMORY_ROOT = _PROJECT_ROOT / "memory" / "src"
if str(MEMORY_ROOT) not in sys.path:
    sys.path.insert(0, str(MEMORY_ROOT))

SKILLS_DIR = Path(__file__).parent.parent.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

app = typer.Typer(help="SPARTA QRA Validator GPT")
console = Console()

SPARTA_BASE = _PROJECT_ROOT / "sparta" / "data" / "runs"
STATE_DIR = Path(__file__).parent.parent / "data" / "state" / "qra-assessor"
MODEL_PATH = _EMBRY_STORAGE / "media/agents/shared/create-gpt/models/qra-assessor/model.gguf"

# Confidence threshold for "maybe" escalation to /scillm Brandon
MAYBE_THRESHOLD = float(os.environ.get("QRA_VALIDATOR_THRESHOLD", "0.85"))

# Framework-specific grounding thresholds (from 12_qra.py)
GROUNDING_THRESHOLDS = {
    "D3FEND": {"fail": 0.60, "warn": 0.70},
    "CWE": {"fail": 0.55, "warn": 0.65},
    "ATT&CK": {"fail": 0.60, "warn": 0.70},
    "NIST": {"fail": 0.55, "warn": 0.65},
    "SPARTA": {"fail": 0.55, "warn": 0.65},
    "ESA": {"fail": 0.55, "warn": 0.65},
}
DEFAULT_THRESHOLD = {"fail": 0.55, "warn": 0.65}


def _safe_json_parse(val: str | None) -> list:
    if val is None:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _detect_framework(control_id: str) -> str:
    cid = control_id or ""
    if cid.startswith("CWE"):
        return "CWE"
    elif cid.startswith("D3"):
        return "D3FEND"
    elif cid.startswith("T") and "." in cid:
        return "ATT&CK"
    elif any(cid.startswith(p) for p in ["AC-", "AU-", "SC-", "SA-", "PE-", "PM-", "IA-"]):
        return "NIST"
    elif cid.startswith("CM") or cid.startswith("REC"):
        return "SPARTA"
    elif cid.startswith("ESA"):
        return "ESA"
    return "OTHER"


def _load_qras(run_id: str, limit: int = 0) -> list[dict]:
    """Load QRAs from DuckDB."""
    db_path = SPARTA_BASE / run_id / "sparta.duckdb"
    if not db_path.exists():
        logger.error(f"DuckDB not found: {db_path}")
        raise typer.Exit(1)

    db = duckdb.connect(str(db_path), read_only=True)
    query = "SELECT qra_id, control_id, question, answer, citations, grounding_score, conceptual_tags, tactical_tags FROM qra ORDER BY RANDOM()"
    if limit > 0:
        query += f" LIMIT {limit}"

    rows = db.execute(query).fetchall()
    db.close()

    items = []
    for row in rows:
        qra_id, control_id, question, answer, citations, gs, ct, tt = row
        items.append({
            "qra_id": qra_id,
            "question": question or "",
            "answer": answer or "",
            "citations": _safe_json_parse(citations),
            "grounding_score": round(gs, 3) if gs else 0.0,
            "framework": _detect_framework(control_id),
            "conceptual_tags": _safe_json_parse(ct),
            "tactical_tags": _safe_json_parse(tt),
            "control_id": control_id or "",
        })

    return items


def _heuristic_grade(item: dict) -> dict:
    """Tier 0: Deterministic structural checks only.

    NOTE: This only checks FORMAT. Semantic quality (reasoning, taxonomy,
    relevance) requires the trained GPT (Tier 1.5) or Brandon via /scillm
    (Tier 2). Heuristic PASS does NOT mean the QRA is good — it just means
    it passes structural minimums.
    """
    issues = []
    framework = item.get("framework", "OTHER")
    thresholds = GROUNDING_THRESHOLDS.get(framework, DEFAULT_THRESHOLD)
    gs = item.get("grounding_score", 0.0)
    answer = item.get("answer", "")
    citations = item.get("citations", [])
    ct = item.get("conceptual_tags", [])
    tt = item.get("tactical_tags", [])
    control_id = item.get("control_id", "")

    # Check 1: Grounding score
    if gs < thresholds["fail"]:
        issues.append(f"grounding {gs:.3f} below fail threshold {thresholds['fail']}")
    elif gs < thresholds["warn"]:
        issues.append(f"grounding {gs:.3f} below warn threshold {thresholds['warn']}")

    # Check 2: Answer length
    if len(answer) < 50:
        issues.append(f"answer too short ({len(answer)} chars, min 50)")
    elif len(answer) < 150:
        issues.append(f"answer short ({len(answer)} chars, prefer 150+)")

    # Check 3: Citations present
    if not citations or len(citations) == 0:
        issues.append("no citations")

    # Check 4: Taxonomy tags present (existence only — correctness needs LLM)
    if not ct:
        issues.append("missing conceptual tags")
    if not tt:
        issues.append("missing tactical tags")

    # Check 5: Anchoring — does answer mention control_id?
    anchoring_ok = control_id.lower() in answer.lower() if control_id else False
    if not anchoring_ok and control_id:
        anchoring_ok = any(part in answer for part in control_id.split("-") if len(part) > 2)

    if not anchoring_ok:
        issues.append(f"answer doesn't reference control {control_id}")

    # Grade (structural only — semantic quality unknown at this tier)
    fail_issues = [i for i in issues if "below fail" in i or "too short" in i or "no citations" in i]
    if fail_issues:
        grade = "FAIL"
    elif issues:
        grade = "WARN"
    else:
        grade = "PASS"

    return {
        "grade": grade,
        "anchoring_ok": anchoring_ok,
        "space_terms_ok": len(ct) >= 1 and len(tt) >= 1,
        # Semantic fields set to None — heuristic can't assess these
        "reasoning_sound": None,
        "taxonomy_correct": None,
        "relevance_score": None,
        "issues": issues,
        "confidence": 1.0 if grade == "FAIL" else (0.8 if grade == "PASS" and not issues else 0.6),
        "tier": "heuristic",
    }


def _escalate_to_brandon(item: dict) -> dict | None:
    """Escalate a 'maybe' grey-area QRA to /scillm with Brandon persona.

    Called when the GPT produces a low-confidence result. Brandon (via SciLLM)
    gives the definitive assessment including semantic quality checks.
    """
    try:
        from graph_memory.llm.teacher_student import QRA_TEACHER_PROMPT
        from graph_memory.llm.client import call_llm_json
    except ImportError:
        logger.warning("Cannot escalate to Brandon — graph_memory.llm not available")
        return None

    input_json = json.dumps(item, ensure_ascii=False, indent=2)
    prompt = f"{QRA_TEACHER_PROMPT}\n\nInput:\n{input_json}"

    try:
        payload, model = call_llm_json(
            prompt,
            profile="accurate",
            max_tokens=1500,  # Longer for paraphrasing output
        )
        logger.info(f"Brandon escalation for {item.get('qra_id', '?')}: grade={payload.get('grade')}")
        payload["tier"] = "brandon_escalation"
        payload["confidence"] = 1.0  # Brandon is authoritative
        return payload
    except Exception as e:
        logger.error(f"Brandon escalation failed: {e}")
        return None


@app.command()
def heuristic(
    run_id: str = typer.Option(..., "--run-id", "-r"),
    limit: int = typer.Option(0, "--limit", "-n"),
):
    """Run heuristic-only validation (Tier 0, structural checks only).

    NOTE: This only checks FORMAT (length, citations, tags exist, anchoring).
    It does NOT assess reasoning quality, taxonomy correctness, or relevance.
    Use 'validate' or 'validate-loop' for full semantic assessment.
    """
    items = _load_qras(run_id, limit)
    logger.info(f"Loaded {len(items)} QRAs from {run_id}")

    monitor = TaskClient("qra-validator-heuristic", total=len(items)) if TaskClient else None

    grades = {"PASS": 0, "WARN": 0, "FAIL": 0}
    issue_counts: dict[str, int] = {}

    for item in items:
        result = _heuristic_grade(item)
        grades[result["grade"]] += 1
        for issue in result["issues"]:
            key = issue.split("(")[0].strip()
            issue_counts[key] = issue_counts.get(key, 0) + 1
        if monitor:
            monitor.update(item=str(item.get("qra_id", "")))

    if monitor:
        monitor.finish()

    total = len(items)
    table = Table(title=f"Heuristic Validation: {run_id} ({total} QRAs) [STRUCTURAL ONLY]")
    table.add_column("Grade", style="bold")
    table.add_column("Count")
    table.add_column("Pct")

    for grade, count in sorted(grades.items()):
        color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}[grade]
        table.add_row(f"[{color}]{grade}[/{color}]", str(count), f"{100*count/total:.1f}%")

    console.print(table)
    console.print("[dim]Note: Heuristic only checks structure. Use 'validate' for semantic quality.[/dim]")

    if issue_counts:
        issue_table = Table(title="Top Issues")
        issue_table.add_column("Issue")
        issue_table.add_column("Count")
        for issue, count in sorted(issue_counts.items(), key=lambda x: -x[1])[:10]:
            issue_table.add_row(issue, str(count))
        console.print(issue_table)


@app.command()
def validate(
    run_id: str = typer.Option(..., "--run-id", "-r"),
    limit: int = typer.Option(1000, "--limit", "-n"),
    threshold: float = typer.Option(0.85, "--threshold"),
):
    """Validate QRAs using trained GPT with Brandon escalation for grey areas.

    Flow:
    1. GPT (Tier 1.5) assesses each QRA for structural + semantic quality
    2. If GPT confidence < threshold → escalate to Brandon via /scillm
    3. Brandon gives definitive grade including reasoning, taxonomy, relevance
    """
    try:
        from graph_memory.llm.router import qra_assess_router, Tier
    except ImportError:
        logger.error("graph_memory.llm.router not available — run from memory project venv")
        raise typer.Exit(1)

    items = _load_qras(run_id, limit)
    logger.info(f"Loaded {len(items)} QRAs, routing through InferenceRouter...")

    router = qra_assess_router()

    if MODEL_PATH.exists():
        for tier_cfg in router.tiers:
            if tier_cfg.tier == Tier.SMALL_GPT:
                tier_cfg.model_path = str(MODEL_PATH)
                logger.info(f"Using trained model: {MODEL_PATH}")
                break
    else:
        logger.warning(f"No trained model at {MODEL_PATH} — using heuristic + Brandon only")

    monitor = TaskClient("qra-validator-validate", total=len(items)) if TaskClient else None

    grades = {"PASS": 0, "WARN": 0, "FAIL": 0}
    tier_counts = {"heuristic": 0, "small_gpt": 0, "scillm": 0, "brandon_escalation": 0}
    semantic_stats = {"reasoning_sound": 0, "taxonomy_correct": 0, "total_semantic": 0}
    t0 = time.time()

    for item in items:
        result = router.route(item)
        payload = result.payload or {}
        confidence = result.confidence or 0.0

        # "Maybe" escalation: low confidence → ask Brandon via /scillm
        if confidence < threshold and confidence > 0:
            brandon_result = _escalate_to_brandon(item)
            if brandon_result:
                payload = brandon_result
                tier_counts["brandon_escalation"] += 1
            else:
                tier_name = result.tier.name.lower() if result.tier else "unknown"
                tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1
        else:
            tier_name = result.tier.name.lower() if result.tier else "unknown"
            tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1

        grade = payload.get("grade", "UNKNOWN")
        if grade in grades:
            grades[grade] += 1

        if monitor:
            monitor.update(item=str(item.get("qra_id", "")))

        # Track semantic assessment coverage
        if payload.get("reasoning_sound") is not None:
            semantic_stats["total_semantic"] += 1
            if payload.get("reasoning_sound"):
                semantic_stats["reasoning_sound"] += 1
            if payload.get("taxonomy_correct"):
                semantic_stats["taxonomy_correct"] += 1

    if monitor:
        monitor.finish()

    elapsed = time.time() - t0
    total = len(items)

    table = Table(title=f"GPT + Brandon Validation: {run_id} ({total} QRAs in {elapsed:.1f}s)")
    table.add_column("Grade", style="bold")
    table.add_column("Count")
    table.add_column("Pct")

    for grade, count in sorted(grades.items()):
        color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}[grade]
        table.add_row(f"[{color}]{grade}[/{color}]", str(count), f"{100*count/total:.1f}%")

    console.print(table)

    tier_table = Table(title="Tier Distribution")
    tier_table.add_column("Tier")
    tier_table.add_column("Count")
    for tier, count in sorted(tier_counts.items()):
        if count > 0:
            tier_table.add_row(tier, str(count))
    console.print(tier_table)

    if semantic_stats["total_semantic"] > 0:
        sem_table = Table(title="Semantic Quality (from GPT + Brandon)")
        sem_table.add_column("Metric")
        sem_table.add_column("Value")
        sem_n = semantic_stats["total_semantic"]
        sem_table.add_row("Assessed semantically", str(sem_n))
        sem_table.add_row("Reasoning sound", f"{semantic_stats['reasoning_sound']}/{sem_n} ({100*semantic_stats['reasoning_sound']/sem_n:.0f}%)")
        sem_table.add_row("Taxonomy correct", f"{semantic_stats['taxonomy_correct']}/{sem_n} ({100*semantic_stats['taxonomy_correct']/sem_n:.0f}%)")
        console.print(sem_table)

    console.print(f"\nThroughput: {total/elapsed:.0f} QRAs/sec")
    console.print(f"Brandon escalations: {tier_counts['brandon_escalation']} (threshold={threshold})")


@app.command("validate-loop")
def validate_loop(
    run_id: str = typer.Option(..., "--run-id", "-r"),
    limit: int = typer.Option(1000, "--limit", "-n"),
    sample_rate: Optional[float] = typer.Option(None, "--sample-rate"),
):
    """Validate with teacher-student loop (recommended for production).

    Brandon (via /scillm) grades a stratified random sample.
    The GPT learns from Brandon's grades on the rest.
    Grey areas ("maybe") escalate to Brandon for a definitive answer.
    """
    try:
        from graph_memory.llm.teacher_student import TeacherStudentLoop, QRA_TEACHER_PROMPT
    except ImportError:
        logger.error("graph_memory.llm.teacher_student not available")
        raise typer.Exit(1)

    items = _load_qras(run_id, limit)
    logger.info(f"Loaded {len(items)} QRAs for teacher-student validation")

    monitor = TaskClient("qra-validator-loop", total=len(items)) if TaskClient else None

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    model_path = str(MODEL_PATH) if MODEL_PATH.exists() else None
    loop = TeacherStudentLoop(
        task_id="qra-assessor",
        teacher_prompt=QRA_TEACHER_PROMPT,
        state_dir=str(STATE_DIR),
        student_model_path=model_path,
        stratify_key="framework",
        # Agreement checked on both structural AND semantic fields
        agreement_fields=["grade", "reasoning_sound", "taxonomy_correct"],
    )

    logger.info(f"State: phase={loop.state.phase}, agreement={loop.state.agreement_rate:.2f}")

    if loop.state.phase in ("bootstrap", "bootstrap_complete") and not model_path:
        # No model yet — Brandon grades everything (bootstrap mode)
        logger.info("No trained model — running in bootstrap mode (Brandon labels only)")
        labels = loop.bootstrap(items)
        logger.info(f"Collected {len(labels)} Brandon labels")
        count = loop.export_training_data(
            str(STATE_DIR / "bootstrap_labels.jsonl")
        )
        logger.info(f"Exported {count} training records")
        console.print(f"\n[bold]Bootstrap complete.[/bold] {count} labels ready for /create-gpt training.")
        console.print("Labels include: grade, reasoning_sound, taxonomy_correct, relevance_score,")
        console.print("similar_questions, paraphrased_answer — GPT learns ALL of these from Brandon.")
        if monitor:
            monitor.finish()
        return

    # Full validation with teacher spot-checks
    results = loop.run_with_validation(items, sample_rate=sample_rate)

    grades = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for r in results:
        if r:
            grade = r.get("result", {}).get("grade", "UNKNOWN")
            if grade in grades:
                grades[grade] += 1

    total = len([r for r in results if r])
    table = Table(title=f"Teacher-Student Validation: {run_id} ({total} QRAs)")
    table.add_column("Grade", style="bold")
    table.add_column("Count")
    table.add_column("Pct")

    for grade, count in sorted(grades.items()):
        color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}[grade]
        pct = f"{100*count/total:.1f}%" if total > 0 else "0%"
        table.add_row(f"[{color}]{grade}[/{color}]", str(count), pct)

    console.print(table)
    if monitor:
        monitor.finish()

    console.print(f"\nAgreement rate: {loop.state.agreement_rate:.1%}")
    console.print(f"Sample rate: {loop.state.current_sample_rate:.1%}")
    console.print(f"Needs retraining: {loop.needs_retraining()}")


@app.command()
def status():
    """Show teacher-student loop status."""
    try:
        from graph_memory.llm.teacher_student import TeacherStudentState
    except ImportError:
        logger.error("graph_memory.llm.teacher_student not available")
        raise typer.Exit(1)

    state = TeacherStudentState.load(STATE_DIR / "state.json", "qra-assessor")

    table = Table(title="QRA Assessor Teacher-Student Status")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Phase", state.phase)
    table.add_row("Teacher labels", str(state.total_teacher_labels))
    table.add_row("Student predictions", str(state.total_student_predictions))
    table.add_row("Validations", str(state.total_validations))
    table.add_row("Agreements", str(state.agreements))
    table.add_row("Disagreements", str(state.disagreements))
    table.add_row("Agreement rate", f"{state.agreement_rate:.1%}")
    table.add_row("Current sample rate", f"{state.current_sample_rate:.1%}")
    table.add_row("Retrain count", str(state.retrain_count))
    table.add_row("Model available", "YES" if MODEL_PATH.exists() else "NO")
    table.add_row("Maybe threshold", str(MAYBE_THRESHOLD))

    console.print(table)

    if state.needs_retraining:
        console.print("\n[bold red]RETRAINING NEEDED[/bold red] — disagreement rate too high")
        console.print("Run: /create-gpt iterate --task qra-assessor")


@app.command("export-disagreements")
def export_disagreements(
    output: Path = typer.Option(STATE_DIR / "disagreements.jsonl", "--output", "-o"),
):
    """Export teacher-student disagreements for analysis or retraining."""
    try:
        from graph_memory.llm.teacher_student import TeacherStudentState
    except ImportError:
        raise typer.Exit(1)

    state = TeacherStudentState.load(STATE_DIR / "state.json", "qra-assessor")

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for correction in state.corrections:
            f.write(json.dumps(correction, ensure_ascii=False) + "\n")

    console.print(f"Exported {len(state.corrections)} disagreements to {output}")


if __name__ == "__main__":
    app()
