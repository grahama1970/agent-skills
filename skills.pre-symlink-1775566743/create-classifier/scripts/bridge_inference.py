#!/usr/bin/env python3
"""Fast bridge inference for persona routing.

Usage:
    python bridge_inference.py "Evaluate the UI for accessibility"

    # As module
    from bridge_inference import BridgeClassifier
    classifier = BridgeClassifier()
    bridges = classifier.predict("How does typography affect readability?")
    # Returns: {"Precision": 0.92, "Fragility": 0.31}
"""

import typer
import json
import sys
import time
from pathlib import Path
from typing import Optional

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class BridgeClassifier:
    """Fast multi-label bridge classifier for Federated Taxonomy."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        threshold: float = 0.5,
        device: Optional[str] = None,
    ):
        if model_path is None:
            # Default to the trained model
            model_path = str(
                Path(__file__).parent.parent / "models" / "bridge_classifier" / "best_model"
            )

        self.threshold = threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # Load model and tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()

        # Load config
        config_path = Path(model_path) / "bridge_config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                self.labels = config.get("labels", [])
                self.id2label = {int(k): v for k, v in config.get("id2label", {}).items()}
        else:
            # Fallback to default bridges
            self.labels = [
                "Corruption", "Precision", "Resilience",
                "Fragility", "Loyalty", "Stealth"
            ]
            self.id2label = {i: label for i, label in enumerate(self.labels)}

    @torch.no_grad()
    def predict(self, text: str) -> dict[str, float]:
        """Predict bridge labels for text.

        Returns dict of bridge -> confidence score for bridges above threshold.
        """
        # Tokenize
        inputs = self.tokenizer(
            text,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        ).to(self.device)

        # Forward pass
        outputs = self.model(**inputs)
        logits = outputs.logits[0]

        # Apply sigmoid for probabilities
        probs = torch.sigmoid(logits).cpu().numpy()

        # Return bridges above threshold
        result = {}
        for i, prob in enumerate(probs):
            if prob >= self.threshold:
                label = self.id2label.get(i, f"label_{i}")
                result[label] = round(float(prob), 3)

        return result

    @torch.no_grad()
    def predict_all(self, text: str) -> dict[str, float]:
        """Predict all bridge probabilities (no threshold filtering)."""
        inputs = self.tokenizer(
            text,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        ).to(self.device)

        outputs = self.model(**inputs)
        logits = outputs.logits[0]
        probs = torch.sigmoid(logits).cpu().numpy()

        return {
            self.id2label.get(i, f"label_{i}"): round(float(prob), 3)
            for i, prob in enumerate(probs)
        }

    def predict_batch(self, texts: list[str]) -> list[dict[str, float]]:
        """Batch prediction for multiple texts."""
        inputs = self.tokenizer(
            texts,
            truncation=True,
            max_length=256,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.sigmoid(outputs.logits).cpu().numpy()

        results = []
        for row in probs:
            result = {}
            for i, prob in enumerate(row):
                if prob >= self.threshold:
                    label = self.id2label.get(i, f"label_{i}")
                    result[label] = round(float(prob), 3)
            results.append(result)

        return results


app = typer.Typer(help="Bridge classifier inference")


@app.command()
def main(
    text: str = typer.Argument(None, help="Text to classify"),
    model: str = typer.Option(None, help="Model path"),
    threshold: float = typer.Option(0.5, help="Prediction threshold"),
    all: bool = typer.Option(False, help="Show all probabilities"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    benchmark: bool = typer.Option(False, help="Run latency benchmark"),
):
    # Read from stdin if no text provided
    if text is None:
        text = sys.stdin.read().strip()

    if not text:
        print("Error: No text provided", file=sys.stderr)
        sys.exit(1)

    # Load classifier
    classifier = BridgeClassifier(model_path=model, threshold=threshold)

    # Benchmark mode
    if benchmark:
        # Warmup
        for _ in range(5):
            classifier.predict(text)

        # Time 100 iterations
        start = time.perf_counter()
        n_iter = 100
        for _ in range(n_iter):
            classifier.predict(text)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / n_iter) * 1000
        print(f"Average latency: {avg_ms:.2f}ms ({n_iter} iterations)")
        return

    # Predict
    if all:
        result = classifier.predict_all(text)
    else:
        result = classifier.predict(text)

    # Output
    if json:
        print(json.dumps(result))
    else:
        if result:
            print("Detected bridges:")
            for bridge, score in sorted(result.items(), key=lambda x: -x[1]):
                print(f"  {bridge}: {score:.3f}")
        else:
            print("No bridges detected above threshold")


if __name__ == "__main__":
    app()
