# SPARTA QRA Sampling Guide

## Statistical Sampling for Quality Validation

This guide provides recommendations for sampling SPARTA-generated QRAs for quality validation with statistical confidence.

## Recommended Strata

### Primary Stratification

Stratify by **framework** to ensure coverage across knowledge sources:

- `SPARTA` - SPARTA framework controls
- `D3FEND` - D3FEND defensive techniques
- `CWE` - Common Weakness Enumeration
- `CAPEC` - Common Attack Pattern Enumeration and Classification
- `ATT&CK` - MITRE ATT&CK tactics and techniques

### Secondary Stratification

Within each framework, stratify by **control_type**:

- `technique` - Specific technical controls
- `tactic` - Strategic approaches
- `control` - Broad control categories
- `weakness` - Vulnerability patterns
- `pattern` - Attack patterns

### Optional Tertiary Strata

For deeper analysis:

- `question_type`: simple, medium, complex, reversal_curse
- `confidence`: strong, partial, inference

## Sample Sizes for 95% Confidence Intervals

### General Population Confidence Intervals

For overall validation (all strata combined):

| Sample Size | Margin of Error | Use Case                  |
| ----------- | --------------- | ------------------------- |
| 30          | ±18%            | Quick check               |
| 100         | ±10%            | Standard validation       |
| 385         | ±5%             | Rigorous validation       |
| 1000        | ±3%             | High-precision validation |

### Per-Stratum Sample Sizes

For validating each stratum independently:

| Sample Size per Stratum | Margin of Error | Recommendation             |
| ----------------------- | --------------- | -------------------------- |
| 10                      | ±31%            | Minimum (exploratory only) |
| 30                      | ±18%            | **Recommended minimum**    |
| 50                      | ±14%            | Better precision           |
| 100                     | ±10%            | High confidence            |

## Sampling Strategy

### 1. Proportional Stratified Sampling

Sample proportionally from each stratum based on population size:

```python
# Example: 385 total samples, 5 frameworks
# Framework distribution: SPARTA=40%, D3FEND=30%, CWE=20%, CAPEC=5%, ATT&CK=5%

samples = {
    "SPARTA": int(385 * 0.40),    # 154
    "D3FEND": int(385 * 0.30),    # 116
    "CWE": int(385 * 0.20),       # 77
    "CAPEC": int(385 * 0.05),     # 19
    "ATT&CK": int(385 * 0.05),    # 19
}
```

### 2. Equal Allocation (When Strata Importance is Equal)

Sample equally from each stratum regardless of size:

```python
# Example: 100 samples total, 5 frameworks
samples_per_framework = 100 // 5  # 20 samples each
```

### 3. Optimal Allocation (When Variance Differs)

Allocate more samples to strata with higher variance:

```python
# Example: If CWE shows 50% pass rate (high variance),
# allocate more samples there than to SPARTA with 95% pass rate
```

## Confidence Interval Formulas

### For Proportions (Pass/Fail Rates)

```
CI = p ± z * sqrt((p * (1-p)) / n)

where:
  p = observed proportion
  z = 1.96 for 95% confidence
  n = sample size
```

### Margin of Error

```
ME = z * sqrt((p * (1-p)) / n)

For worst case (p=0.5):
  n=30  → ME = 1.96 * sqrt(0.25/30)  = ±0.18 (±18%)
  n=100 → ME = 1.96 * sqrt(0.25/100) = ±0.10 (±10%)
  n=385 → ME = 1.96 * sqrt(0.25/385) = ±0.05 (±5%)
```

## Practical Recommendations

### Quick Validation (1-2 hours)

- **Total samples**: 100
- **Strategy**: Proportional stratified by framework
- **Result**: ±10% ME overall, directional per-stratum insights

### Standard Validation (4-8 hours)

- **Total samples**: 385
- **Strategy**: Proportional stratified by framework + control_type
- **Result**: ±5% ME overall, ±14-18% per stratum (n=30-50)

### Rigorous Validation (1-2 days)

- **Total samples**: 1000+
- **Strategy**: Proportional stratified with n≥100 per major stratum
- **Result**: ±3% ME overall, ±10% per stratum

## Validation Metrics to Track

For each stratum, measure:

1. **Ambiguity Gate Pass Rate** - Questions are clear and specific
2. **Entity Anchoring Pass Rate** - Questions reference context entities
3. **Citation Grounding Rate** - Answers cite source text (fuzzy match ≥0.85)
4. **Duplicate Rate** - Near-duplicate answers (≥90% similarity)
5. **Diversity Score** - Coverage of question types, personas, confidence levels

## Example Sampling Plan

### Scenario: Validate SPARTA Stage 12 QRA Generation

**Population**: 10,000 QRAs across 5 frameworks

**Goal**: 95% CI with ±5% ME

**Sampling Plan**:

1. **Total samples**: 385
2. **Stratification**:
   - Primary: Framework (5 strata)
   - Secondary: Control type (3 strata per framework)
3. **Allocation**: Proportional
   - SPARTA: 154 samples (40% of pop)
     - technique: 62, tactic: 46, control: 46
   - D 3FEND: 116 samples (30% of pop)
     - technique: 46, tactic: 35, control: 35
   - CWE: 77 samples (20% of pop)
     - weakness: 77
   - CAPEC: 19 samples (5% of pop)
     - pattern: 19
   - ATT&CK: 19 samples (5% of pop)
     - tactic: 10, technique: 9

4. **Selection**: Random sampling within each stratum
5. **Validation**: Manual review of all quality gates
6. **Analysis**: Report overall + per-stratum pass rates with CIs

## Tools

Use `quality_audit.py` to:

- Generate stratified samples
- Calculate confidence intervals
- Report per-stratum metrics

```bash
cd .pi/skills/quality-audit
./run.sh sample --run-id run-recovery-verify --n 385 --strategy proportional
./run.sh validate --samples samples.jsonl
./run.sh report --samples samples.jsonl --ci 0.95
```

## References

- Cochran, W.G. (1977). _Sampling Techniques_ (3rd ed.). Wiley.
- NIST 800-53 Rev. 5 - Security and Privacy Controls (Sampling for audit)
- ISO 19011:2018 - Guidelines for auditing management systems
