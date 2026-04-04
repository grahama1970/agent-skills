#!/usr/bin/env python3
"""Generate a HuggingFace model card from eval-results.json.

Usage:
    python generate_model_card.py /path/to/project-dir [--output stdout|file]

Reads eval-results.json, meta.json, tune-config.json from the project dir.
Outputs the model card markdown to stdout (default) or writes README.md.
"""
import json
import sys
from pathlib import Path

from huggingface_hub import EvalResult, ModelCard, ModelCardData


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def generate_card(project_dir: str) -> str:
    """Generate model card markdown from project data files."""
    pdir = Path(project_dir)

    eval_data = load_json(pdir / "eval-results.json")
    meta = load_json(pdir / "meta.json")
    tune = load_json(pdir / "tune-config.json")

    if not eval_data:
        return "# Model Card\n\nNo evaluation data available."

    model_name = eval_data.get("model", meta.get("backbone", "unknown"))
    task_name = meta.get("name", pdir.name.replace("-", " "))
    modality = meta.get("modality", "text")
    macro_f1 = eval_data.get("macro_f1", 0)
    accuracy = eval_data.get("accuracy", 0)
    test_samples = eval_data.get("test_samples", 0)
    classes = eval_data.get("classes", [])
    per_class = eval_data.get("per_class", {})
    holdout_passed = eval_data.get("holdout_passed", False)

    # Build eval results for HF metadata
    eval_results = [
        EvalResult(
            task_type="text-classification",
            dataset_type=pdir.name,
            dataset_name=task_name,
            metric_type="f1",
            metric_value=round(macro_f1, 4),
            metric_name="Macro F1",
            dataset_split="test",
        ),
        EvalResult(
            task_type="text-classification",
            dataset_type=pdir.name,
            dataset_name=task_name,
            metric_type="accuracy",
            metric_value=round(accuracy, 4),
            metric_name="Accuracy",
            dataset_split="test",
        ),
    ]

    card_data = ModelCardData(
        model_name=f"{task_name} ({model_name})",
        base_model=model_name,
        pipeline_tag="text-classification",
        language="en",
        tags=["text-classification", "classifier-lab", modality],
        eval_results=eval_results,
        metrics=["f1", "accuracy"],
    )

    # Build the card content from real data
    per_class_rows = ""
    weak_classes = []
    for cls in classes:
        m = per_class.get(cls, {})
        f1 = m.get("f1", 0)
        prec = m.get("precision", 0)
        rec = m.get("recall", 0)
        sup = m.get("support", 0)
        per_class_rows += f"| {cls} | {prec:.3f} | {rec:.3f} | {f1:.3f} | {sup} |\n"
        if f1 < macro_f1 - 0.05:
            weak_classes.append(cls)

    # Training config from tune-config
    lr = tune.get("lr", "—")
    epochs = tune.get("epochs", "—")
    train_samples = meta.get("samples", "—")

    # Limitations from actual eval weaknesses
    limitations = ""
    if weak_classes:
        limitations += f"- Classes with below-average F1: **{', '.join(weak_classes)}**\n"
    confusion = eval_data.get("confusion_matrix", [])
    if confusion and classes:
        worst_pair = {"count": 0, "from": "", "to": ""}
        for i, row in enumerate(confusion):
            for j, count in enumerate(row):
                if i != j and count > worst_pair["count"]:
                    worst_pair = {"count": count, "from": classes[i], "to": classes[j]}
        if worst_pair["count"] > 0:
            limitations += (
                f"- Most common confusion: **{worst_pair['from']}** misclassified as "
                f"**{worst_pair['to']}** ({worst_pair['count']} times in {test_samples} test samples)\n"
            )
    if not holdout_passed:
        limitations += f"- **Model did not pass holdout gate** (F1 {macro_f1:.3f})\n"

    # Usage example from real model name and classes
    classes_str = ", ".join(f'"{c}"' for c in classes)
    usage = f'''```python
from transformers import pipeline

clf = pipeline("text-classification", model="{model_name}")
result = clf("Your text here")
print(result)
# Classes: {classes_str}
```'''

    content = f"""---
{card_data.to_yaml()}
---

# {task_name}

Fine-tuned **{model_name}** for {task_name} ({len(classes)} classes).

## Model Details

| | |
|---|---|
| **Base model** | {model_name} |
| **Task** | {task_name} |
| **Modality** | {modality} |
| **Classes** | {', '.join(classes)} |
| **Training samples** | {train_samples} |
| **Learning rate** | {lr} |
| **Epochs** | {epochs} |

## Evaluation Results

Evaluated on **{test_samples}** held-out test samples.

| Metric | Value |
|--------|-------|
| **Macro F1** | {macro_f1:.4f} |
| **Accuracy** | {accuracy:.4f} |
| **Holdout gate** | {'PASSED' if holdout_passed else 'FAILED'} |

### Per-Class Performance

| Class | Precision | Recall | F1 | Support |
|-------|-----------|--------|-----|---------|
{per_class_rows}
## Usage

{usage}

## Known Limitations

{limitations if limitations else "No significant limitations identified."}

## Training Infrastructure

Trained with [Classifier Lab](https://github.com/embry-os/classifier-lab) self-improvement pipeline.
"""
    return content


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: generate_model_card.py <project-dir> [--output file]")
        sys.exit(1)

    project_dir = sys.argv[1]
    output_mode = "stdout"
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_mode = sys.argv[idx + 1]

    card_md = generate_card(project_dir)

    if output_mode == "file":
        out_path = Path(project_dir) / "README.md"
        out_path.write_text(card_md)
        print(f"Written to {out_path}")
    else:
        print(card_md)
