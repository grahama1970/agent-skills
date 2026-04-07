#!/usr/bin/env python3
"""Space Classifier - Pre-filter for Brandon/Embry persona.

Classifies queries as space_cybersecurity or generic_it to route appropriately.
Uses the trained DistilBERT model for fast inference.

Usage:
    from space_classifier import SpaceClassifier

    classifier = SpaceClassifier()
    result = classifier.classify("How do I detect RF jamming?")
    # {'label': 'space_cybersecurity', 'confidence': 0.98, 'is_space': True}
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

# Default model path - can be overridden
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "create-classifier" / "models" / "space_classifier_distilbert" / "best_model"


class SpaceClassifier:
    """Classifies queries as space_cybersecurity or generic_it."""

    def __init__(self, model_path: Path | str | None = None):
        """Initialize classifier.

        Args:
            model_path: Path to trained model directory. Uses default if None.
        """
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.model = None
        self.tokenizer = None
        self.label_map = None
        self._loaded = False

    def _load_model(self) -> None:
        """Lazy-load the model on first use."""
        if self._loaded:
            return

        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            import torch

            logger.info(f"Loading space classifier from {self.model_path}")

            self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(self.model_path))
            self.model.eval()

            # Load label mapping
            label_map_path = self.model_path / "label_map.json"
            if label_map_path.exists():
                with open(label_map_path) as f:
                    self.label_map = json.load(f)
            else:
                # Default mapping
                self.label_map = {
                    "id2label": {"0": "space_cybersecurity", "1": "generic_it"},
                    "label2id": {"space_cybersecurity": 0, "generic_it": 1}
                }

            self._loaded = True
            logger.info("Space classifier loaded successfully")

        except ImportError as e:
            logger.error(f"Missing dependencies for classifier: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load classifier: {e}")
            raise

    def classify(self, text: str) -> dict[str, Any]:
        """Classify a query as space_cybersecurity or generic_it.

        Args:
            text: Query text to classify

        Returns:
            Dict with label, confidence, and is_space flag
        """
        self._load_model()

        import torch

        # Tokenize
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )

        # Remove token_type_ids if present (DistilBERT doesn't use them)
        if "token_type_ids" in inputs:
            del inputs["token_type_ids"]

        # Inference
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
            predicted_id = torch.argmax(probs, dim=-1).item()
            confidence = probs[0][predicted_id].item()

        # Map to label
        label = self.label_map["id2label"][str(predicted_id)]

        return {
            "label": label,
            "confidence": confidence,
            "is_space": label == "space_cybersecurity",
            "all_probs": {
                self.label_map["id2label"][str(i)]: probs[0][i].item()
                for i in range(probs.shape[1])
            }
        }

    def is_space_query(self, text: str, threshold: float = 0.5) -> bool:
        """Quick check if query is space-related.

        Args:
            text: Query text
            threshold: Confidence threshold for space classification

        Returns:
            True if query is classified as space_cybersecurity above threshold
        """
        result = self.classify(text)
        return result["is_space"] and result["confidence"] >= threshold


# Singleton instance for reuse
_classifier_instance: SpaceClassifier | None = None


def get_classifier() -> SpaceClassifier:
    """Get singleton classifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = SpaceClassifier()
    return _classifier_instance


def classify_query(text: str) -> dict[str, Any]:
    """Convenience function to classify a query.

    Args:
        text: Query text

    Returns:
        Classification result
    """
    return get_classifier().classify(text)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python space_classifier.py 'query text'")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    classifier = SpaceClassifier()
    result = classifier.classify(query)
    print(json.dumps(result, indent=2))
