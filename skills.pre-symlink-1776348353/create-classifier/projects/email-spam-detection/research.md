# Email Spam Detection Research

## Problem
Binary text classification: classify SMS/email messages as spam or ham (not spam).

## Dataset
- **Source**: ucirvine/sms_spam (HuggingFace)
- **Samples**: 5,574 (4,459 train, 557 val, 558 test)
- **Classes**: ham (4,827), spam (747) — imbalanced ~6.5:1
- **Text**: Short SMS messages (avg ~80 chars)

## Approach (from /dogpile)
- Binary text classification — well-studied problem
- Standard approach: fine-tune pre-trained transformer
- Imbalanced classes: use weighted loss or oversample spam

## Backbone Candidates
1. **distilbert-base-uncased** — 66M params, fast, proven on short text
2. **sentence-transformers/all-MiniLM-L6-v2** — 22M params, semantic similarity backbone

## Initial HP Recommendations
- Learning rate: 2e-5
- Epochs: 10 with early stopping patience 3
- Batch size: 16
- Max length: 128 (short SMS messages)
- Warmup ratio: 0.1
- Weight decay: 0.01

## Gate
- Target: F1 ≥ 0.90 (achievable for binary spam detection)
