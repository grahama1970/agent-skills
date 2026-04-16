# Research: News Topic Classification

## Task Summary
Text classification of news articles into 4 topic categories (World, Sports, Sci/Tech, Business) using the AG News dataset subset. 2,000 samples, balanced classes (~500/class).

## Recommended Backbones (ranked by expected F1)

### 1. bert-base-uncased (110M params)
- **Expected F1**: 0.92-0.94 on AG News
- **Why**: Full BERT consistently outperforms DistilBERT by 2-4% on nuanced multi-class tasks. The additional capacity handles topic boundary cases (e.g., tech-business overlap).
- **HPs**: lr=2e-5, batch_size=16, epochs=3, warmup_ratio=0.1, weight_decay=0.01
- **Tradeoff**: 2x slower than DistilBERT, but well within A5000 24GB budget

### 2. distilbert-base-uncased (66M params) — current best
- **Expected F1**: 0.88-0.91 (observed: 0.890)
- **Why**: 97% of BERT performance at 60% size. Good baseline but capacity-limited on edge cases.
- **HPs**: lr=2e-5, batch_size=16, epochs=2-4, weight_decay=1e-4
- **Note**: Current run hit 0.890 — within 0.010 of gate. Diminishing returns with more epochs.

### 3. roberta-base (125M params)
- **Expected F1**: 0.93-0.95
- **Why**: Trained on 10x more data than BERT with dynamic masking. Strongest for short text classification.
- **HPs**: lr=1e-5, batch_size=16, epochs=3, warmup_steps=500

### 4. sentence-transformers/all-MiniLM-L6-v2 (22M params)
- **Expected F1**: 0.89-0.92
- **Why**: Sentence-level embeddings + classification head. Fast inference, good generalization.
- **HPs**: lr=2e-5, batch_size=32, epochs=5, pooling=mean

## Techniques to Close the 0.010 Gap

### Label Smoothing (alpha=0.1)
At F1=0.890, the model is likely overconfident on boundary samples. Label smoothing regularizes decision boundaries and improves calibration on ambiguous articles.

### Learning Rate Warmup + Cosine Decay
Transformers are sensitive to early LR — warmup prevents catastrophic forgetting of pretrained features. Cosine decay finds flatter minima. Use 10% warmup steps.

### Weighted Sampling
AG News has slight imbalance. Macro F1 penalizes weak classes — if any class has fewer samples, weighted sampling ensures equal representation per batch.

### Focal Loss
Reduces contribution of easy examples, focusing training on hard boundary cases between topics (e.g., Sci/Tech vs Business articles about AI companies).

## Data Augmentation for Text
- **Back-translation** (en→de→en): Creates paraphrases while preserving meaning
- **Synonym replacement**: Replace 10-15% of words with WordNet synonyms
- **Random insertion/deletion**: Light noise for regularization
- **NOT recommended**: Mixup for text (degrades semantic content at this dataset size)

## Key References
- Devlin et al. (2019) — BERT: Pre-training of Deep Bidirectional Transformers
- Liu et al. (2019) — RoBERTa: A Robustly Optimized BERT Pretraining Approach
- Sun et al. (2019) — How to Fine-Tune BERT for Text Classification
- HuggingFace AG News benchmark: https://huggingface.co/datasets/ag_news

## Gate Assessment
With bert-base-uncased or roberta-base and the recommended HPs, F1 ≥ 0.90 is achievable. The current DistilBERT result (0.890) is within striking distance — a larger model or label smoothing alone should close the gap.

---
*Generated via /dogpile research — 2026-03-29*
