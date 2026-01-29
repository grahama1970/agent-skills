---
name: quality-audit
description: >
  Stratified quality sampling and statistical validation for LLM outputs.
  Works with ANY project's extraction results. Calculates confidence intervals,
  chi-square tests, and stratified sampling by configurable dimensions.
allowed-tools: ["Bash", "Read", "Write"]
triggers:
  - quality-audit
  - quality audit
  - audit quality
  - stratified sample
  - statistical validation
  - llm quality check
  - extraction quality
metadata:
  short-description: Statistical quality validation for LLM extraction results
---

# Quality Audit Skill

Stratified quality sampling and statistical validation for LLM extraction results.
Works with **any project** - not tied to specific extraction tasks.

## Key Features

1. **Stratified Sampling**: Sample by any dimension (framework, source, confidence)
2. **Statistical Rigor**: Chi-square tests, 95% confidence intervals
3. **Generic Interface**: Works with any JSON/JSONL extraction results
4. **UltraThink Mode**: High-token reasoning for difficult edge cases
5. **Quality Gates**: Configurable thresholds for pass/fail

## Quick Start

```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/quality-audit

# Sample from extraction results
./run.sh sample --input results.jsonl --stratify framework --samples-per-stratum 5

# Audit samples with LLM verification
./run.sh audit --samples samples.json --threshold 0.85

# Generate full quality report
./run.sh report --input results.jsonl --output quality_report.md

# UltraThink mode for difficult cases (uses more tokens)
./run.sh audit --samples samples.json --ultrathink
```

## Commands

### sample - Stratified Sampling

```bash
./run.sh sample --input results.jsonl --stratify framework --samples-per-stratum 5

# Options:
#   --input FILE            Input JSON/JSONL with extraction results
#   --stratify DIMENSION    Dimension to stratify by (framework, source, confidence)
#   --samples-per-stratum N Number of samples per stratum (default: 5)
#   --seed INT              Random seed for reproducibility (default: 42)
#   --output FILE           Output file for samples (default: samples.json)
```

### audit - Quality Verification

```bash
./run.sh audit --samples samples.json --threshold 0.85

# Options:
#   --samples FILE          Sampled cases to audit
#   --threshold FLOAT       Minimum accuracy to pass (default: 0.85)
#   --model NAME            LLM model for verification (default: from env)
#   --ultrathink            Enable UltraThink mode (more tokens, deeper reasoning)
#   --human                 Generate review document for human verification
#   --output FILE           Output audit results
```

### report - Full Quality Report

```bash
./run.sh report --input results.jsonl --output quality_report.md

# Options:
#   --input FILE            Full extraction results
#   --output FILE           Report output path
#   --samples-per-stratum N Samples for statistical estimation (default: 10)
#   --include-chi-square    Include chi-square agreement test
```

## Stratification Dimensions

The skill supports stratifying by any field in your data. Common dimensions:

| Dimension    | Example Values                      | Use Case                           |
|--------------|-------------------------------------|-------------------------------------|
| `framework`  | D3FEND, ATT&CK, NIST, CWE          | Validate coverage across frameworks |
| `source`     | deterministic, llm, keyword_fallback| Compare extraction methods          |
| `confidence` | low (0-0.5), med (0.5-0.8), high   | Focus on uncertain cases            |
| `collection` | controls, techniques, mitigations   | Multi-collection validation         |

### Custom Stratification

For custom fields:

```bash
./run.sh sample --input results.jsonl --stratify "metadata.worksheet_type" --samples-per-stratum 3
```

## Statistical Tests

### 95% Confidence Intervals

For each stratum and overall:

```
Overall Accuracy: 87.5% +/- 4.2% (95% CI)
```

Calculated as: `p +/- 1.96 * sqrt(p * (1-p) / n)`

### Chi-Square Agreement Test

Compare LLM results vs deterministic mappings:

```bash
./run.sh report --input results.jsonl --include-chi-square
```

Output:
```
Chi-Square Agreement Test:
  - Null hypothesis: LLM and deterministic agree at random
  - Chi-square statistic: 45.2
  - p-value: < 0.001
  - Interpretation: Strong agreement (not random)
```

### Sample Size Calculation

Calculate required samples for target precision:

```bash
./run.sh sample-size --target-precision 0.05 --expected-accuracy 0.85
# Output: Need 196 samples for +/- 5% precision at 85% expected accuracy
```

## UltraThink Mode

For difficult edge cases, enable UltraThink mode which:

1. Uses extended thinking budget (more tokens)
2. Requires explicit reasoning chain before verdict
3. Requests multiple verification passes
4. Higher confidence in final verdict

```bash
./run.sh audit --samples samples.json --ultrathink --model deepseek

# UltraThink prompt includes:
# "Take your time and think through this carefully. Consider:
#  1. What is the primary function of this control?
#  2. Which taxonomy tier best captures its essence?
#  3. Are there edge cases or ambiguities?
#  4. Confidence in your assessment?
#  Reason through each step before giving your final answer."
```

## Input Format

The skill accepts JSON or JSONL with extraction results. Required fields:

```json
{
  "id": "D3-FEV",
  "input": {
    "name": "File Eviction",
    "description": "Removes files from system"
  },
  "output": {
    "conceptual": ["Precision", "Resilience"],
    "tactical": ["Evict", "Restore"]
  },
  "metadata": {
    "source": "llm",
    "confidence": 0.9,
    "framework": "D3FEND"
  }
}
```

Flexible field mapping via `--id-field`, `--output-field`, `--metadata-field`.

## Output Format

### Sample Output (samples.json)

```json
{
  "created": "2026-01-29T10:00:00Z",
  "seed": 42,
  "stratify_by": "framework",
  "samples_per_stratum": 5,
  "strata": {
    "D3FEND": [...],
    "ATT&CK": [...],
    "NIST": [...],
    "CWE": [...]
  }
}
```

### Audit Output (audit_results.json)

```json
{
  "timestamp": "2026-01-29T10:00:00Z",
  "model": "deepseek",
  "ultrathink": false,
  "results": {
    "overall_accuracy": 0.875,
    "confidence_interval_95": "87.5% +/- 4.2%",
    "per_stratum": {
      "D3FEND": {"sampled": 5, "correct": 5, "accuracy": 1.0},
      "ATT&CK": {"sampled": 5, "correct": 4, "accuracy": 0.8}
    },
    "chi_square": {
      "statistic": 45.2,
      "p_value": 0.0001,
      "conclusion": "Strong agreement"
    }
  },
  "quality_gate": {
    "threshold": 0.85,
    "passed": true
  }
}
```

### Report Output (quality_report.md)

```markdown
# Quality Audit Report

## Summary
- **Total Records**: 4011
- **Sampled**: 40 (10 per stratum)
- **Overall Accuracy**: 87.5% +/- 4.2%
- **Quality Gate**: PASS (threshold: 85%)

## Per-Stratum Results
| Stratum | Sampled | Correct | Accuracy | 95% CI |
|---------|---------|---------|----------|--------|
| D3FEND  | 10      | 10      | 100%     | +/- 0% |
| ATT&CK  | 10      | 8       | 80%      | +/- 12.5% |
...

## Chi-Square Agreement Test
...

## Recommendations
...
```

## Integration with Projects

### SPARTA Integration

```python
from quality_audit import stratified_sample, audit_samples, quality_report

# Sample from DuckDB results
samples = stratified_sample(
    input_source=conn,  # DuckDB connection
    query="SELECT * FROM bridge_tag_results",
    stratify_by="framework",
    samples_per_stratum=10,
)

# Audit with LLM
results = audit_samples(samples, model="deepseek", ultrathink=True)

# Generate report
report = quality_report(results, threshold=0.85)
```

### Generic JSON/JSONL

```bash
# From any JSON extraction results
./run.sh sample --input extractions.jsonl --stratify source --samples-per-stratum 5
./run.sh audit --samples samples.json --threshold 0.85
```

## Configuration

Environment variables:

```bash
# LLM for verification (optional - uses configured model)
QUALITY_AUDIT_MODEL=deepseek

# Default threshold
QUALITY_AUDIT_THRESHOLD=0.85

# UltraThink token budget
QUALITY_AUDIT_ULTRATHINK_TOKENS=4096
```

## Quality Gates for CI/CD

```bash
# Exit code 0 = pass, 1 = fail
./run.sh audit --samples samples.json --threshold 0.85

# Use in pipelines
if ./run.sh audit --samples samples.json --threshold 0.85; then
    echo "Quality gate passed"
else
    echo "Quality gate failed - accuracy below threshold"
    exit 1
fi
```

## Use Cases

1. **SPARTA Bridge Tags**: Validate taxonomy extraction quality
2. **QRA Generation**: Verify question-answer pairs are accurate
3. **Document Extraction**: Check text extraction quality
4. **Classification Tasks**: Any LLM classification with ground truth
5. **A/B Testing**: Compare extraction approaches statistically
