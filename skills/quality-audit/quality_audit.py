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
    from scipy import stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


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


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Quality Audit - Stratified sampling and statistical validation")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Sample command
    sample_parser = subparsers.add_parser("sample", help="Stratified sampling")
    sample_parser.add_argument("--input", "-i", required=True, help="Input JSON/JSONL file")
    sample_parser.add_argument("--stratify", "-s", default="framework", help="Field to stratify by")
    sample_parser.add_argument("--samples-per-stratum", "-n", type=int, default=5, help="Samples per stratum")
    sample_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    sample_parser.add_argument("--output", "-o", default="samples.json", help="Output file")
    sample_parser.add_argument("--human", action="store_true", help="Generate human review document")

    # Audit command
    audit_parser = subparsers.add_parser("audit", help="Audit sampled cases")
    audit_parser.add_argument("--samples", required=True, help="Samples JSON file")
    audit_parser.add_argument("--threshold", type=float, default=0.85, help="Quality threshold")
    audit_parser.add_argument("--output", "-o", default="audit_results.json", help="Output file")
    audit_parser.add_argument("--ultrathink", action="store_true", help="Enable UltraThink mode")
    audit_parser.add_argument("--human", action="store_true", help="Generate human review instead of LLM")

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate quality report")
    report_parser.add_argument("--input", "-i", required=True, help="Input JSON/JSONL or samples file")
    report_parser.add_argument("--output", "-o", default="quality_report.md", help="Output file")
    report_parser.add_argument("--include-chi-square", action="store_true", help="Include chi-square test")

    # Sample-size command
    size_parser = subparsers.add_parser("sample-size", help="Calculate required sample size")
    size_parser.add_argument("--target-precision", type=float, default=0.05, help="Target precision (e.g., 0.05 for +/-5%)")
    size_parser.add_argument("--expected-accuracy", type=float, default=0.85, help="Expected accuracy")

    args = parser.parse_args()

    if args.command == "sample":
        records = load_input(args.input)
        samples = stratified_sample(
            records,
            stratify_by=args.stratify,
            samples_per_stratum=args.samples_per_stratum,
            seed=args.seed,
        )

        Path(args.output).write_text(json.dumps(samples, indent=2))
        print(f"Sampled {samples['total_sampled']} records stratified by '{args.stratify}'")
        print(f"Strata: {list(samples['strata'].keys())}")
        print(f"Output: {args.output}")

        if args.human:
            review_doc = format_human_review(samples)
            review_path = Path(args.output).with_suffix('.review.md')
            review_path.write_text(review_doc)
            print(f"Human review document: {review_path}")

        return 0

    elif args.command == "audit":
        samples = json.loads(Path(args.samples).read_text())

        if args.human:
            review_doc = format_human_review(samples)
            review_path = Path(args.output).with_suffix('.review.md')
            review_path.write_text(review_doc)
            print(f"Human review document: {review_path}")
            print("Complete the review document and re-run with --results flag")
            return 0

        # For now, output UltraThink prompts if requested
        if args.ultrathink:
            print("UltraThink mode enabled - generating verification prompts...")
            prompts = []
            for stratum, stratum_samples in samples['strata'].items():
                for record in stratum_samples:
                    prompt = generate_ultrathink_prompt(record, f"Stratum: {stratum}")
                    prompts.append({
                        "id": get_nested_value(record, "id", "unknown"),
                        "stratum": stratum,
                        "prompt": prompt,
                    })

            prompts_path = Path(args.output).with_suffix('.prompts.json')
            prompts_path.write_text(json.dumps(prompts, indent=2))
            print(f"UltraThink prompts saved to: {prompts_path}")
            print("Run these prompts through your LLM and collect results")
            return 0

        print("Audit requires either --human or --ultrathink mode")
        print("Or implement LLM integration for automated verification")
        return 1

    elif args.command == "report":
        # Check if input is samples or raw records
        input_path = Path(args.input)
        data = json.loads(input_path.read_text())

        if 'strata' in data:
            # Already sampled
            samples = data
        else:
            # Raw records - sample first
            records = load_input(args.input)
            samples = stratified_sample(records, samples_per_stratum=10)

        report = generate_report(
            samples,
            include_chi_square=args.include_chi_square,
        )

        Path(args.output).write_text(report)
        print(f"Report saved to: {args.output}")
        return 0

    elif args.command == "sample-size":
        n = required_sample_size(args.target_precision, args.expected_accuracy)
        print(f"Required sample size: {n}")
        print(f"For +/- {args.target_precision:.1%} precision at {args.expected_accuracy:.0%} expected accuracy")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
