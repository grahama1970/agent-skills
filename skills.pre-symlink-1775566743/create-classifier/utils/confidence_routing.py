#!/usr/bin/env python3
"""
Confidence-Based Routing - Route predictions to classifier or heuristic fallback

Usage:
    from confidence_routing import ConfidenceRouter
    
    router = ConfidenceRouter(classifier, heuristic_fn, threshold=0.8)
    result = router.predict(input_data)
"""

from typing import Any, Callable, Dict, Optional
from loguru import logger
import time


class ConfidenceRouter:
    """Routes predictions based on classifier confidence."""
    
    def __init__(
        self,
        classifier: Any,
        heuristic_fallback: Callable,
        threshold: float = 0.8,
        log_path: Optional[str] = None
    ):
        """
        Args:
            classifier: Trained classifier with predict() method returning (prediction, confidence)
            heuristic_fallback: Function that takes same input and returns prediction
            threshold: Confidence threshold below which to use heuristic (0-1)
            log_path: Optional path to log routing decisions (JSONL)
        """
        self.classifier = classifier
        self.heuristic = heuristic_fallback
        self.threshold = threshold
        self.log_path = log_path
        
        # Statistics
        self.stats = {
            "total": 0,
            "classifier_used": 0,
            "heuristic_used": 0,
            "classifier_time_ms": [],
            "heuristic_time_ms": []
        }
    
    def predict(self, input_data: Any, log_metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a prediction using classifier or heuristic fallback.
        
        Args:
            input_data: Input to classify
            log_metadata: Optional metadata to include in logs
        
        Returns:
            Dict with keys: prediction, confidence, source, metadata
        """
        self.stats["total"] += 1
        
        # Try classifier first
        t0 = time.time()
        try:
            prediction, confidence = self.classifier.predict(input_data)
            classifier_time_ms = (time.time() - t0) * 1000
            self.stats["classifier_time_ms"].append(classifier_time_ms)
        except Exception as e:
            logger.warning(f"Classifier prediction failed: {e}, using heuristic fallback")
            confidence = 0.0
            prediction = None
        
        # Route based on confidence
        if confidence >= self.threshold and prediction is not None:
            # Use classifier prediction
            self.stats["classifier_used"] += 1
            result = {
                "prediction": prediction,
                "confidence": confidence,
                "source": "classifier",
                "inference_time_ms": classifier_time_ms
            }
        else:
            # Fallback to heuristic
            t0 = time.time()
            heuristic_prediction = self.heuristic(input_data)
            heuristic_time_ms = (time.time() - t0) * 1000
            
            self.stats["heuristic_used"] += 1
            self.stats["heuristic_time_ms"].append(heuristic_time_ms)
            
            result = {
                "prediction": heuristic_prediction,
                "confidence": confidence,  # Log classifier confidence anyway for analysis
                "source": "heuristic_fallback",
                "classifier_confidence": confidence,
                "inference_time_ms": heuristic_time_ms
            }
        
        # Add metadata
        if log_metadata:
            result["metadata"] = log_metadata
        
        # Log decision
        if self.log_path:
            self._log_decision(input_data, result)
        
        return result
    
    def _log_decision(self, input_data: Any, result: Dict[str, Any]):
        """Log routing decision to JSONL file."""
        import json
        from pathlib import Path
        
        log_entry = {
            "timestamp": time.time(),
            "input_id": getattr(input_data, "id", str(input_data)[:50]),
            **result
        }
        
        log_path = Path(self.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        import statistics
        
        avg_classifier_time = statistics.mean(self.stats["classifier_time_ms"]) if self.stats["classifier_time_ms"] else 0
        avg_heuristic_time = statistics.mean(self.stats["heuristic_time_ms"]) if self.stats["heuristic_time_ms"] else 0
        
        return {
            "total_predictions": self.stats["total"],
            "classifier_used": self.stats["classifier_used"],
            "heuristic_used": self.stats["heuristic_used"],
            "classifier_usage_rate": self.stats["classifier_used"] / max(1, self.stats["total"]),
            "avg_classifier_time_ms": avg_classifier_time,
            "avg_heuristic_time_ms": avg_heuristic_time,
        }
    
    def print_stats(self):
        """Print routing statistics."""
        stats = self.get_stats()
        
        logger.info("\n=== Confidence Router Statistics ===")
        logger.info(f"Total predictions: {stats['total_predictions']}")
        logger.info(f"Classifier used: {stats['classifier_used']} ({stats['classifier_usage_rate']*100:.1f}%)")
        logger.info(f"Heuristic used: {stats['heuristic_used']} ({(1-stats['classifier_usage_rate'])*100:.1f}%)")
        logger.info(f"Avg classifier time: {stats['avg_classifier_time_ms']:.1f}ms")
        logger.info(f"Avg heuristic time: {stats['avg_heuristic_time_ms']:.1f}ms")


class ShadowRouter(ConfidenceRouter):
    """Router that runs both classifier and heuristic, compares results."""
    
    def predict(self, input_data: Any, log_metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Run both classifier and heuristic, log comparison."""
        self.stats["total"] += 1
        
        # Run classifier
        t0 = time.time()
        try:
            classifier_prediction, classifier_confidence = self.classifier.predict(input_data)
            classifier_time_ms = (time.time() - t0) * 1000
        except Exception as e:
            logger.warning(f"Classifier failed: {e}")
            classifier_prediction = None
            classifier_confidence = 0.0
            classifier_time_ms = 0
        
        # Run heuristic
        t0 = time.time()
        heuristic_prediction = self.heuristic(input_data)
        heuristic_time_ms = (time.time() - t0) * 1000
        
        # Compare
        agreement = (classifier_prediction == heuristic_prediction)
        
        # Always use heuristic in shadow mode (no production impact)
        result = {
            "prediction": heuristic_prediction,
            "source": "heuristic",
            "shadow_mode": True,
            "classifier_prediction": classifier_prediction,
            "classifier_confidence": classifier_confidence,
            "agreement": agreement,
            "classifier_time_ms": classifier_time_ms,
            "heuristic_time_ms": heuristic_time_ms
        }
        
        if log_metadata:
            result["metadata"] = log_metadata
        
        # Log for analysis
        if self.log_path:
            self._log_decision(input_data, result)
        
        # Track disagreements
        if not agreement:
            logger.debug(
                f"Shadow disagreement: classifier={classifier_prediction} "
                f"(conf={classifier_confidence:.2f}), heuristic={heuristic_prediction}"
            )
        
        return result
