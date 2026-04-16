# Skill-Chain Routing Classifier Research

## Problem
Replace brittle regex trigger matching in skill-selector.ts with a trained multi-label classifier.
Given a user prompt, predict which skills (out of 50) should be invoked.

## Approach (from /dogpile)
- **Task type**: Multi-label text classification (each prompt can trigger multiple skills)
- **Loss**: BCEWithLogitsLoss (NOT CrossEntropy — this is multi-label, not multi-class)
- **Activation**: Sigmoid per class (NOT softmax)
- **Threshold**: Tunable per-class on validation set (don't assume 0.5)

## Backbone Candidates
1. **distilbert-base-uncased** — Fast, 66M params, good baseline for short-medium text
2. **microsoft/deberta-v3-small** — 44M params, strong on NLU tasks, disentangled attention
3. **sentence-transformers/all-MiniLM-L6-v2** — 22M params, optimized for semantic similarity

## Key Considerations
- 50 classes with heavy imbalance (memory=551, rare classes <20 samples)
- Use pos_weight in BCEWithLogitsLoss to handle class imbalance
- 1187 samples total — small dataset, risk of overfitting with large models
- Early stopping on validation F1 is critical
- Dropout 0.1-0.3 in classification head

## Initial HP Recommendations
- Learning rate: 2e-5 (standard for fine-tuning transformers)
- Epochs: 10 with early stopping patience 3
- Batch size: 16 (small dataset, don't need large batches)
- Warmup ratio: 0.1
- Weight decay: 0.01
