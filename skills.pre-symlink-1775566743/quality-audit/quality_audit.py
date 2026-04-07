#!/usr/bin/env python3
"""
Quality Audit: Stratified sampling and statistical validation for LLM outputs.

Works with ANY project's extraction results. Provides:
- Stratified sampling by any dimension
- 95% confidence intervals
- Chi-square agreement tests
- UltraThink mode for difficult cases
"""
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import math

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

try:
    from scipy import stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# Memory integration (graceful degradation)
_HAS_MEMORY_INTEGRATION = False
try:
    from memory_integration import recall_prior_audits, learn_audit
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    pass


def load_input(input_source: Union[str, Path, List[Dict]]) -> List[Dict[str, Any]]:
    """Load extraction results from JSON, JSONL, or list."""
    if isinstance(input_source, list):
        return input_source

    path = Path(input_source)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    content = path.read_text()

    # Try JSONL first
    if path.suffix == '.jsonl' or '\n{' in content:
        records = []
        for line in content.strip().split('\n'):
            if line.strip():
                records.append(json.loads(line))
        return records

    # Try JSON
    data = json.loads(content)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and 'records' in data:
        return data['records']
    if isinstance(data, dict) and 'results' in data:
        return data['results']

    raise ValueError(f"Cannot parse input: expected list or dict with 'records'/'results' key")


def get_nested_value(record: Dict, field_path: str, default: Any = None) -> Any:
    """Get nested value from dict using dot notation (e.g., 'metadata.framework')."""
    parts = field_path.split('.')
    value = record
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default
    return value


def categorize_confidence(confidence: float) -> str:
    """Categorize confidence into low/med/high."""
    if confidence < 0.5:
        return "low"
    elif confidence < 0.8:
        return "medium"
    else:
        return "high"


def stratified_sample(
    records: List[Dict[str, Any]],
    stratify_by: str = "framework",
    samples_per_stratum: int = 5,
    seed: int = 42,
    confidence_field: str = "metadata.confidence",
) -> Dict[str, Any]:
    """
    Sample records stratified by a given dimension.

    Args:
        records: List of extraction result records
        stratify_by: Field to stratify by (supports dot notation)
        samples_per_stratum: Number of samples per stratum
        seed: Random seed for reproducibility
        confidence_field: Field containing confidence score (for confidence stratification)

    Returns:
        Dict with sampling metadata and stratified samples
    """
    random.seed(seed)

    # Group by stratification dimension
    strata = {}
    for record in records:
        if stratify_by == "confidence":
            # Special handling for confidence stratification
            conf = get_nested_value(record, confidence_field, 0.5)
            stratum = categorize_confidence(conf)
        else:
            stratum = get_nested_value(record, stratify_by, "Unknown")
            if stratum is None:
                stratum = "Unknown"
            stratum = str(stratum)

        if stratum not in strata:
            strata[stratum] = []
        strata[stratum].append(record)

    # Sample from each stratum
    sampled = {}
    for stratum, stratum_records in strata.items():
        shuffled = stratum_records.copy()
        random.shuffle(shuffled)
        sampled[stratum] = shuffled[:samples_per_stratum]

    return {
        "created": datetime.utcnow().isoformat() + "Z",
        "seed": seed,
        "stratify_by": stratify_by,
        "samples_per_stratum": samples_per_stratum,
        "total_records": len(records),
        "total_sampled": sum(len(s) for s in sampled.values()),
        "strata_counts": {k: len(v) for k, v in strata.items()},
        "strata": sampled,
    }


def confidence_interval_95(accuracy: float, n: int) -> str:
    """Calculate 95% confidence interval for accuracy estimate."""
    if n == 0:
        return "N/A"

    # Wilson score interval is more robust for small samples
    # But standard normal approximation is simpler and often sufficient
    if accuracy == 0 or accuracy == 1:
        # Edge cases
        margin = 1.96 * math.sqrt(0.25 / n)  # Use 0.5 as conservative estimate
    else:
        margin = 1.96 * math.sqrt(accuracy * (1 - accuracy) / n)

    return f"{accuracy:.1%} +/- {margin:.1%}"


def chi_square_agreement(
    results: List[Dict[str, Any]],
    llm_field: str = "output",
    deterministic_field: str = "deterministic_output",
) -> Dict[str, Any]:
    """
    Chi-square test for LLM vs deterministic agreement.

    Tests whether the agreement between LLM and deterministic methods
    is better than random chance.
    """
    if not HAS_SCIPY:
        return {
            "error": "scipy not installed - cannot compute chi-square test",
            "install": "pip install scipy"
        }

    # Build contingency table
    # Rows: LLM correct/incorrect
    # Cols: Deterministic correct/incorrect
    agree = 0
    disagree = 0

    for record in results:
        llm_output = get_nested_value(record, llm_field)
        det_output = get_nested_value(record, deterministic_field)

        if llm_output is None or det_output is None:
            continue

        if llm_output == det_output:
            agree += 1
        else:
            disagree += 1

    total = agree + disagree
    if total == 0:
        return {"error": "No comparable records found"}

    # Simple agreement test using binomial/chi-square
    # H0: Agreement is random (50%)
    expected_agree = total * 0.5
    expected_disagree = total * 0.5

    observed = [agree, disagree]
    expected = [expected_agree, expected_disagree]

    chi2, p_value = stats.chisquare(observed, expected)

    agreement_rate = agree / total

    if p_value < 0.001:
        conclusion = "Strong agreement (highly significant)"
    elif p_value < 0.05:
        conclusion = "Significant agreement"
    else:
        conclusion = "Agreement not statistically significant"

    return {
        "agree": agree,
        "disagree": disagree,
        "total": total,
        "agreement_rate": agreement_rate,
        "chi_square_statistic": chi2,
        "p_value": p_value,
        "conclusion": conclusion,
    }


def calculate_accuracy_metrics(
    verified: List[Dict[str, Any]],
    correct_field: str = "is_correct",
) -> Dict[str, Any]:
    """Calculate accuracy metrics from verified samples."""
    total = len(verified)
    correct = sum(1 for v in verified if get_nested_value(v, correct_field, False))

    accuracy = correct / total if total > 0 else 0

    return {
        "total_sampled": total,
        "total_correct": correct,
        "accuracy": accuracy,
        "confidence_interval_95": confidence_interval_95(accuracy, total),
    }


def format_human_review(samples: Dict[str, Any], id_field: str = "id") -> str:
    """Format samples for human review."""
    lines = ["# Quality Audit Review\n"]
    lines.append("Review each case and mark as CORRECT or INCORRECT.\n")
    lines.append(f"Stratified by: {samples['stratify_by']}")
    lines.append(f"Samples per stratum: {samples['samples_per_stratum']}")
    lines.append(f"Total samples: {samples['total_sampled']}\n")

    for stratum, stratum_samples in samples['strata'].items():
        lines.append(f"\n## {stratum} ({len(stratum_samples)} samples)\n")

        for i, record in enumerate(stratum_samples, 1):
            record_id = get_nested_value(record, id_field, f"record_{i}")

            # Try to get display fields
            name = get_nested_value(record, "input.name",
                   get_nested_value(record, "name", ""))
            desc = get_nested_value(record, "input.description",
                   get_nested_value(record, "description", ""))[:200]
            output = get_nested_value(record, "output", {})
            confidence = get_nested_value(record, "metadata.confidence",
                        get_nested_value(record, "confidence", "N/A"))
            source = get_nested_value(record, "metadata.source",
                     get_nested_value(record, "source", "N/A"))

            lines.append(f"### {record_id}: {name}")
            if desc:
                lines.append(f"**Description:** {desc}...")
            lines.append(f"**Output:** {json.dumps(output, indent=2)}")
            lines.append(f"**Confidence:** {confidence} | **Source:** {source}")
            lines.append(f"**Correct?** [ ] Yes  [ ] No")
            lines.append(f"**Notes:** _________________\n")

    lines.append("\n---")
    lines.append("Quality Score = (Correct / Total) * 100%")

    return "\n".join(lines)


def generate_ultrathink_prompt(record: Dict[str, Any], context: str = "") -> str:
    """Generate UltraThink verification prompt for difficult cases."""
    record_id = get_nested_value(record, "id", "unknown")
    name = get_nested_value(record, "input.name", get_nested_value(record, "name", ""))
    desc = get_nested_value(record, "input.description", get_nested_value(record, "description", ""))
    output = get_nested_value(record, "output", {})

    prompt = f"""You are a quality auditor verifying LLM extraction results.

## UltraThink Mode - Deep Reasoning Required

Take your time and think through this CAREFULLY. This is a quality audit where accuracy matters more than speed.

{context}

## Record to Verify

**ID:** {record_id}
**Name:** {name}
**Description:** {desc}

**LLM Output:**
```json
{json.dumps(output, indent=2)}
```

## Your Task

Verify whether the LLM's output is CORRECT for this input.

Think through each step:
1. What is the primary function/purpose of this item?
2. Do the extracted tags/categories accurately capture its essence?
3. Are there any obvious errors or hallucinations?
4. Are there edge cases or ambiguities that might explain any issues?
5. What is your confidence in the correctness assessment?

## Response Format

Provide your analysis in this exact JSON format:
```json
{{
  "reasoning": "Your detailed step-by-step reasoning here...",
  "is_correct": true/false,
  "confidence": 0.0-1.0,
  "issues": ["list of specific issues if any"],
  "suggested_fix": "suggested correction if incorrect"
}}
```

Remember: Quality over speed. Reason carefully before answering."""

    return prompt


def generate_report(
    samples: Dict[str, Any],
    audit_results: Optional[Dict[str, Any]] = None,
    include_chi_square: bool = False,
    chi_square_results: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate markdown quality report."""
    lines = ["# Quality Audit Report\n"]
    lines.append(f"**Generated:** {datetime.utcnow().isoformat()}Z\n")

    # Summary
    lines.append("## Summary\n")
    lines.append(f"- **Total Records:** {samples.get('total_records', 'N/A')}")
    lines.append(f"- **Sampled:** {samples.get('total_sampled', 'N/A')}")
    lines.append(f"- **Stratified By:** {samples.get('stratify_by', 'N/A')}")
    lines.append(f"- **Samples Per Stratum:** {samples.get('samples_per_stratum', 'N/A')}")

    if audit_results:
        accuracy = audit_results.get('accuracy', 0)
        ci = audit_results.get('confidence_interval_95', 'N/A')
        threshold = audit_results.get('threshold', 0.85)
        passed = accuracy >= threshold

        lines.append(f"- **Overall Accuracy:** {ci}")
        lines.append(f"- **Quality Gate:** {'PASS' if passed else 'FAIL'} (threshold: {threshold:.0%})")

    lines.append("")

    # Strata distribution
    lines.append("## Strata Distribution\n")
    lines.append("| Stratum | Total Records | Sampled |")
    lines.append("|---------|---------------|---------|")

    strata_counts = samples.get('strata_counts', {})
    strata_samples = samples.get('strata', {})
    for stratum in sorted(strata_counts.keys()):
        total = strata_counts[stratum]
        sampled = len(strata_samples.get(stratum, []))
        lines.append(f"| {stratum} | {total} | {sampled} |")

    lines.append("")

    # Per-stratum results (if audit completed)
    if audit_results and 'per_stratum' in audit_results:
        lines.append("## Per-Stratum Accuracy\n")
        lines.append("| Stratum | Sampled | Correct | Accuracy | 95% CI |")
        lines.append("|---------|---------|---------|----------|--------|")

        for stratum, metrics in audit_results['per_stratum'].items():
            sampled = metrics.get('sampled', 0)
            correct = metrics.get('correct', 0)
            acc = metrics.get('accuracy', 0)
            ci = confidence_interval_95(acc, sampled)
            lines.append(f"| {stratum} | {sampled} | {correct} | {acc:.1%} | {ci.split('+/-')[1] if '+/-' in ci else 'N/A'} |")

        lines.append("")

    # Chi-square results
    if include_chi_square and chi_square_results:
        lines.append("## Chi-Square Agreement Test\n")
        if 'error' in chi_square_results:
            lines.append(f"**Error:** {chi_square_results['error']}")
        else:
            lines.append(f"- **Agreement Rate:** {chi_square_results.get('agreement_rate', 0):.1%}")
            lines.append(f"- **Chi-Square Statistic:** {chi_square_results.get('chi_square_statistic', 0):.2f}")
            lines.append(f"- **P-Value:** {chi_square_results.get('p_value', 1):.4f}")
            lines.append(f"- **Conclusion:** {chi_square_results.get('conclusion', 'N/A')}")
        lines.append("")

    # Recommendations
    lines.append("## Recommendations\n")
    if audit_results:
        accuracy = audit_results.get('accuracy', 0)
        if accuracy >= 0.95:
            lines.append("- Excellent quality. Ready for production use.")
        elif accuracy >= 0.85:
            lines.append("- Good quality. Minor improvements may help edge cases.")
        elif accuracy >= 0.70:
            lines.append("- Moderate quality. Review error patterns and consider prompt improvements.")
        else:
            lines.append("- Quality below acceptable threshold. Significant revision needed.")
            lines.append("- Consider: prompt engineering, additional context, different model.")
    else:
        lines.append("- Run audit to get quality metrics.")

    return "\n".join(lines)


def required_sample_size(target_precision: float = 0.05, expected_accuracy: float = 0.85) -> int:
    """Calculate required sample size for target precision."""
    # n = (z^2 * p * (1-p)) / e^2
    # where z=1.96 for 95% CI, p=expected accuracy, e=target precision
    z = 1.96
    p = expected_accuracy
    e = target_precision

    n = (z ** 2 * p * (1 - p)) / (e ** 2)
    return math.ceil(n)


import typer

app = typer.Typer(help="Quality Audit - Stratified sampling and statistical validation")


@app.command("sample")
def cmd_sample(
    input: str = typer.Option(..., "-i", "--input", help="Input JSON/JSONL file"),
    stratify: str = typer.Option("framework", "-s", "--stratify", help="Field to stratify by"),
    samples_per_stratum: int = typer.Option(5, "-n", "--samples-per-stratum", help="Samples per stratum"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    output: str = typer.Option("samples.json", "-o", "--output", help="Output file"),
    human: bool = typer.Option(False, "--human", help="Generate human review document"),
) -> None:
    """Stratified sampling."""
    records = load_input(input)
    samples = stratified_sample(
        records,
        stratify_by=stratify,
        samples_per_stratum=samples_per_stratum,
        seed=seed,
    )

    Path(output).write_text(json.dumps(samples, indent=2))
    print(f"Sampled {samples['total_sampled']} records stratified by '{stratify}'")
    print(f"Strata: {list(samples['strata'].keys())}")
    print(f"Output: {output}")

    # Pre-hook: Recall prior audits for this stratification
    if _HAS_MEMORY_INTEGRATION:
        prior = recall_prior_audits(stratify)
        if prior:
            print(f"[memory] Found prior audits for '{stratify}'")

    if human:
        review_doc = format_human_review(samples)
        review_path = Path(output).with_suffix('.review.md')
        review_path.write_text(review_doc)
        print(f"Human review document: {review_path}")


@app.command("audit")
def cmd_audit(
    samples_file: str = typer.Option(..., "--samples", help="Samples JSON file"),
    threshold: float = typer.Option(0.85, "--threshold", help="Quality threshold"),
    output: str = typer.Option("audit_results.json", "-o", "--output", help="Output file"),
    ultrathink: bool = typer.Option(False, "--ultrathink", help="Enable UltraThink mode"),
    human: bool = typer.Option(False, "--human", help="Generate human review instead of LLM"),
) -> None:
    """Audit sampled cases."""
    samples = json.loads(Path(samples_file).read_text())

    if human:
        review_doc = format_human_review(samples)
        review_path = Path(output).with_suffix('.review.md')
        review_path.write_text(review_doc)
        print(f"Human review document: {review_path}")
        print("Complete the review document and re-run with --results flag")
        return

    # For now, output UltraThink prompts if requested
    if ultrathink:
        print("UltraThink mode enabled - generating verification prompts...")
        prompts = []
        all_records = [(s, r) for s, recs in samples['strata'].items() for r in recs]
        monitor = TaskClient("quality-audit", total=len(all_records)) if TaskClient else None
        for stratum, stratum_samples in samples['strata'].items():
            for record in stratum_samples:
                prompt = generate_ultrathink_prompt(record, f"Stratum: {stratum}")
                prompts.append({
                    "id": get_nested_value(record, "id", "unknown"),
                    "stratum": stratum,
                    "prompt": prompt,
                })
                if monitor:
                    monitor.update(item=get_nested_value(record, "id", "unknown"))
        if monitor:
            monitor.finish()

        prompts_path = Path(output).with_suffix('.prompts.json')
        prompts_path.write_text(json.dumps(prompts, indent=2))
        print(f"UltraThink prompts saved to: {prompts_path}")
        print("Run these prompts through your LLM and collect results")
        return

    print("Audit requires either --human or --ultrathink mode")
    print("Or implement LLM integration for automated verification")
    raise typer.Exit(1)


@app.command("report")
def cmd_report(
    input: str = typer.Option(..., "-i", "--input", help="Input JSON/JSONL or samples file"),
    output: str = typer.Option("quality_report.md", "-o", "--output", help="Output file"),
    include_chi_square: bool = typer.Option(False, "--include-chi-square", help="Include chi-square test"),
) -> None:
    """Generate quality report."""
    # Check if input is samples or raw records
    input_path = Path(input)
    data = json.loads(input_path.read_text())

    if 'strata' in data:
        # Already sampled
        samples = data
    else:
        # Raw records - sample first
        records = load_input(input)
        samples = stratified_sample(records, samples_per_stratum=10)

    # Pre-hook: Recall prior audits for drift detection
    if _HAS_MEMORY_INTEGRATION:
        prior = recall_prior_audits(str(input_path.stem))
        if prior:
            print(f"[memory] Found prior audits for '{input_path.stem}'")

    report = generate_report(
        samples,
        include_chi_square=include_chi_square,
    )

    Path(output).write_text(report)
    print(f"Report saved to: {output}")

    # Post-hook: Learn audit results to memory
    if _HAS_MEMORY_INTEGRATION:
        try:
            findings = []
            # Extract any per-stratum issues
            strata_info = samples.get("strata", {})
            for stratum_name, stratum_samples in strata_info.items():
                findings.append(f"Stratum '{stratum_name}': {len(stratum_samples)} samples")

            learn_audit(
                project_name=str(input_path.stem),
                pipeline=samples.get("stratify_by", ""),
                sample_size=samples.get("total_sampled", 0),
                pass_rate=None,  # Not yet audited at report stage
                findings=findings,
                stats={
                    "total_records": samples.get("total_records", 0),
                    "strata_counts": samples.get("strata_counts", {}),
                    "stratify_by": samples.get("stratify_by", ""),
                },
            )
            print("[memory] Audit report learned to memory")
        except Exception as e:
            print(f"[memory] Learn skipped: {e}")


@app.command("sample-size")
def cmd_sample_size(
    target_precision: float = typer.Option(0.05, "--target-precision", help="Target precision (e.g., 0.05 for +/-5%)"),
    expected_accuracy: float = typer.Option(0.85, "--expected-accuracy", help="Expected accuracy"),
) -> None:
    """Calculate required sample size."""
    n = required_sample_size(target_precision, expected_accuracy)
    print(f"Required sample size: {n}")
    print(f"For +/- {target_precision:.1%} precision at {expected_accuracy:.0%} expected accuracy")


if __name__ == "__main__":
    app()
