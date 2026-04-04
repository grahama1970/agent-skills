## Architecture Details

### Vision Classifier Template

```python
import timm
import torch.nn as nn

class VisionClassifier(nn.Module):
    def __init__(self, num_classes, backbone="efficientnet_b0"):
        super().__init__()
        self.backbone = timm.create_model(
            backbone,
            pretrained=True,
            num_classes=0
        )
        self.classifier = nn.Linear(
            self.backbone.num_features,
            num_classes
        )
        self.confidence_head = nn.Sequential(
            nn.Linear(self.backbone.num_features, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        features = self.backbone(x)
        logits = self.classifier(features)
        confidence = self.confidence_head(features)
        return logits, confidence
```

### Confidence-Based Routing

```python
class ConfidenceRouter:
    def __init__(self, classifier, heuristic_fn, threshold=0.8):
        self.classifier = classifier
        self.heuristic = heuristic_fn
        self.threshold = threshold

    def predict(self, input_data):
        pred, confidence = self.classifier(input_data)

        if confidence >= self.threshold:
            return {"prediction": pred, "source": "classifier"}
        else:

## Data Collection Strategy

### Automatic Labeling

Mine labels from successful pipeline outputs:

**S00 (Document Type)**:

- Extract preset from `00_profile.json` → label
- Extract first 3 pages as images → input

**S05 (Table Strategy)**:

- Extract strategy from `05_tables.json` → label
- Extract table region image → input
- Use success/failure as GRPO reward

**S08 (Requirements)**:

- Bootstrap with regex-matched sentences → positive examples
- Random sentences without modal verbs → negative examples
- Manual review of edge cases

### Label Validation

```python
def validate_labels(labels_path, sample_size=100):
    """Manual review of random sample for quality check."""
    labels = load_jsonl(labels_path)
    sample = random.sample(labels, sample_size)

    correct = 0
    for item in sample:
        print(f"Input: {item['input']}")
        print(f"Predicted label: {item['label']}")
        response = input("Correct? (y/n): ")
        if response.lower() == 'y':
            correct += 1

    accuracy = correct / sample_size
    print(f"Label quality: {accuracy:.1%}")
    return accuracy >= 0.95  # Threshold for good labels
```

---

## GRPO Training (Execution Feedback)

### Reward Functions

**S00 Document Type**:

```python
def reward_preset_accuracy(predicted_preset, pdf_path):
    """Reward = 1.0 if pipeline succeeds, 0.0 if fails."""
    result = run_pipeline(pdf_path, preset=predicted_preset)
    return 1.0 if result.success else 0.0
```

**S08 Requirements**:

```python
def reward_requirement_extraction(predicted_requirements, ground_truth):
    """Reward = F1 score vs ground truth."""
    precision = len(predicted & ground_truth) / len(predicted)
    recall = len(predicted & ground_truth) / len(ground_truth)
    f1 = 2 * (precision * recall) / (precision + recall)
    return f1
```

### Training Loop

```python
from trl import GRPOTrainer

trainer = GRPOTrainer(
    model=classifier,
    reward_fn=reward_preset_accuracy,
    baseline_fn=heuristic_preset_detection,
    num_iterations=100,
    batch_size=16
)

trainer.train()
```

---

## Integration Example: S00 Document Type

### Before (Heuristics Only)

```python
def detect_preset(pdf_path):

## Observability

### Metrics Logged

```json
{
  "timestamp": "2026-02-08T10:53:00Z",
  "task": "document_type",
  "input_id": "doc_abc123",
  "classifier_prediction": "arxiv_scientific",
  "classifier_confidence": 0.92,
  "heuristic_prediction": "general",
  "heuristic_confidence": 0.65,
  "source_used": "classifier",
  "execution_result": "success",
  "inference_time_ms": 45
}
```

### Monitoring Dashboard

Track over time:

- Classifier usage rate (% using classifier vs fallback)
- Accuracy comparison (classifier vs heuristic)
- Inference latency (p50, p95, p99)
- Fallback rate (low confidence → heuristic)

---

## Troubleshooting

### Low Accuracy (<90%)

**Causes**:

- Insufficient training data (need >1000 examples per class)
- Class imbalance (e.g., 90% arxiv, 10% legal)
- Poor label quality

**Solutions**:

- Collect more data from corpus
- Apply class balancing (oversample minority, undersample majority)
- Manual review and relabeling of subset

### Slow Inference (>100ms)

**Causes**:

- Large model (DiT is 85M params)
- CPU inference (no GPU available)

**Solutions**:

- Use smaller model (EfficientNet-B0 is 5M params)
- Quantize to ONNX (2-3x speedup)
- Batch inference (process multiple pages together)
- Cache predictions (don't re-classify same document)

### High Fallback Rate (>30%)

**Causes**:

- Classifier not confident on edge cases
- Threshold too high (>0.9)

**Solutions**:

- Lower confidence threshold (try 0.7)
- Add more diverse training data
- Ensemble multiple models (vote on prediction)

---

## Next Steps

1. **Collect data** for S00 document type classifier
2. **Train baseline** EfficientNet-B0 model
3. **Shadow deploy** for 1 week, compare vs heuristics
4. **Deploy** if accuracy >90%
5. **Repeat** for S08 requirements classifier

---

## References

- [Table Classifier Context](/home/graham/workspace/experiments/extractor/local/docs/CONTEXT.md)
- [S00 Profile Detector](/home/graham/workspace/experiments/extractor/src/extractor/pipeline/steps/s00_profile_detector.py)
- [GRPO Paper](https://arxiv.org/abs/2402.03300)
- [DiT Model](https://huggingface.co/microsoft/dit-base)
