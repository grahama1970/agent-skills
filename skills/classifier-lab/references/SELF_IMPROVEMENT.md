## Self-Improvement Loop (NON-NEGOTIABLE)

**The self-improvement loop is the core product of Classifier Lab.**
It is NOT optional. Every classifier project MUST run through it.

### The Loop

```
/dogpile research → Data validation → Train round 1 → Evaluate on held-out test
  → If gate PASSES: promote
  → If gate FAILS: diagnose WHY → adjust strategy → retrain
  → Repeat until gate passes or max rounds exhausted
```

### Mandatory Steps on Failure

When a training round fails the holdout gate (F1 < 0.90):

1. **Diagnose** — Check feature importance. Are features dead (all zeros)? Fix data collection.
2. **Normalize** — Apply per-document z-scoring to continuous features. Test with rank features.
3. **Augment** — Cross-document mixup for underrepresented classes. Noise injection for hard positives.
4. **Regularize** — Increase `min_samples_leaf`, decrease `max_depth`, add `subsample` + `max_features`.
5. **Ensemble** — Stack GBR + RF + LR with GroupKFold CV. Calibrate predictions.
6. **Switch modality** — If vision fails, try tabular. If tabular fails, try paired/Siamese. Check if the data has pre-computed features before training vision models.
7. **Research again** — /dogpile with the specific failure mode. "Why does my tabular GBR fail on cross-document generalization?" is a better query than "best classifier for tables."

### What the Loop Must NOT Do

- Stop after 1-3 rounds and declare a "ceiling"
- Ask the human what to try next (the loop should know)
- Skip steps (e.g., jump from basic GBR to "we need more data" without trying normalization)
- Report training validation metrics as evaluation (ALWAYS held-out test set)

### Strategy Escalation Order

| Round | Strategy | When to use |
|-------|----------|-------------|
| 1 | Baseline backbone + default HPs | Always start here |
| 2 | Adjusted LR + more epochs | If loss was still decreasing |
| 3 | Per-document feature normalization | If doc-stratified F1 << random F1 |
| 4 | Feature engineering (ratios, ranks, interactions) | If feature importance is concentrated on 1-2 features |
| 5 | Augmentation (mixup, noise, SMOTE) | If class imbalance or small dataset |
| 6 | Regularized ensemble (GBR+RF+LR stack) | If single models plateau |
| 7 | Different modality (/dogpile for which) | If current modality is fundamentally wrong |
| 8 | Data enrichment (populate dead features, collect more) | If features are missing or sparse |
| 9 | **Data sufficiency check** | When 3+ strategies plateau at same F1 (±0.02) |
| 10 | Escalate to human with data recommendation | After data check confirms bottleneck |

### Data Sufficiency Check (Strategy 9)

When 3+ consecutive strategies produce F1 within ±0.02 of each other, the loop
MUST stop grinding and diagnose the DATA, not the model.

**Trigger conditions** (any 2 of these):
- 3+ strategies plateau within ±0.02 F1
- Feature importance >50% concentrated on 1-2 features
- Dead features exist (all zeros) that should carry signal
- Confusion matrix errors are symmetric (equal false positives and false negatives)

**Output**: A structured recommendation to the human:

```
DATA SUFFICIENCY REPORT
━━━━━━━━━━━━━━━━━━━━━━
Gate target:     F1 ≥ 0.90
Best achieved:   F1 0.80 (stacking ensemble, 8 rounds)
Plateau range:   0.79–0.80 across 3 strategies
Diagnosis:       Insufficient feature discriminability

Missing data that would help:
  1. Text content similarity (actual cell text, not just headers)
  2. More diverse document sources (currently 292 docs, need 500+)
  3. Ruling line / border detection features

Recommendation:
  □ Collect 500+ additional labeled pairs from new document sources
  □ Enrich features with text-content similarity from S05b output
  □ OR lower gate to 0.80 for this task (justify in model card)
```

**The loop MUST NOT**:
- Keep retrying the same strategies hoping for different results
- Declare a "ceiling" without explaining what data would break it
- Skip this check and jump straight to "escalate to human"

### Data Split Rules

- **Vision**: Split by document source, NOT alphabetically by filename
- **Text**: Split by source document or conversation, NOT randomly by sentence
- **Tabular**: Split by group/entity (e.g., document, user, session), NOT randomly by row
- **ALWAYS verify**: val F1 and test F1 should be within 0.10 of each other. If test >> val, you have leakage.

### Research Gate (NON-NEGOTIABLE)

Training tabs are BLOCKED until:
1. **Local data audit** exists as `data_audit.json` in the project dir
2. `/dogpile` research output exists as `research.md` in the project dir
3. Research contains backbone/model recommendations informed by the data audit
4. Research hash is stored in `/memory` for verification

#### Step 1: Local Data Audit (BEFORE /dogpile)

Before searching externally, audit the local data. Output `data_audit.json`:

```json
{
  "formats_found": ["images/train/{class}/*.png", "merge_features.jsonl", "merge_features_tabular.jsonl"],
  "tabular_features": {"count": 9, "dead": ["title_has_continued", "gap_between_tables_px"], "dead_pct": 33},
  "image_resolution": "224x224 (full-page thumbnails — too low for structural detail)",
  "class_balance": {"merge": 1274, "separate": 1161},
  "sample_count": 2435,
  "recommendation": "Tabular features available — try tabular modality first. Vision at 224x224 unlikely to capture table structure."
}
```

This audit determines WHAT to dogpile for:
- If tabular features exist → dogpile for tabular classifiers
- If only images exist → dogpile for vision architectures at the available resolution
- If features are dead → dogpile for how to populate them
- If resolution is too low → dogpile for minimum resolution requirements

#### Step 2: /dogpile (Informed by Data Audit)

The dogpile query must reference the data audit findings:
- BAD: "best classifier for table detection"
- GOOD: "best tabular classifier for 9 structural features (col_count, IoU, width_ratio) with 2K samples and cross-document generalization requirement"

#### Step 3: Verification

Research hash stored in `/memory`. Training blocked unless both `data_audit.json` and `research.md` exist.

### Paired/Siamese Modality

For tasks that compare two inputs (merge/separate, similar/different, match/no-match):

```bash
./run.sh benchmark --data-dir /path/to/paired --modality paired --backbones "efficientnet_b0"
```

Data format: images are side-by-side composites, split at midpoint into left/right inputs.
Uses shared-backbone Siamese with 4-way feature combination: [f_a, f_b, |f_a-f_b|, f_a*f_b].

### Data Collection (from /create-table-classifier)

```bash
./run.sh collect --corpus /mnt/storage12tb/extractor_corpus --skip-images
```

Scans the extractor corpus for table pairs, computes structural features
(col_count_match, width_ratio, IoU, title_similarity, gap, etc.), outputs
`merge_features.jsonl` for tabular training.

## Environment Variables

- `CLASSIFIER_LAB_CACHE`: Model cache directory
- `WANDB_API_KEY`: Weights & Biases logging (optional)
- `CUDA_VISIBLE_DEVICES`: GPU selection
