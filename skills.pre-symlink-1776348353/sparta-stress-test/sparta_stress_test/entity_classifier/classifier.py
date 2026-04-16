"""Entity ID hallucination classifier.

For entity IDs that pass structural validation but aren't found in the
knowledge graph, this classifier determines if they're:
  - PLAUSIBLE: Follows real patterns, could be a valid ID we haven't seen
  - HALLUCINATED: LLM-invented ID that doesn't match real naming conventions

Architecture: Feature-based gradient boosting (fast, interpretable, no GPU needed)
Features extracted from the entity ID string itself:
  1. Prefix similarity to known prefixes
  2. Numeric suffix range validity
  3. Sub-technique pattern compliance
  4. Category-specific structural features
  5. Character-level n-gram overlap with known IDs

Training data: Real IDs from ArangoDB + synthetic hallucinated IDs.
"""

from __future__ import annotations

import json
import os
import pickle
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger


# Feature extraction
def _extract_features(entity_id: str, known_prefixes: Set[str]) -> Dict[str, float]:
    """Extract classification features from an entity ID string."""
    features = {}

    # Basic string features
    features['length'] = len(entity_id)
    features['num_dashes'] = entity_id.count('-')
    features['num_dots'] = entity_id.count('.')
    features['num_parens'] = entity_id.count('(')
    features['has_colon'] = 1.0 if ':' in entity_id else 0.0

    # Prefix features
    prefix = entity_id.split('-')[0] if '-' in entity_id else entity_id[:2]
    features['prefix_known'] = 1.0 if prefix in known_prefixes else 0.0
    features['prefix_len'] = len(prefix)

    # Numeric suffix features
    nums = re.findall(r'\d+', entity_id)
    if nums:
        max_num = max(int(n) for n in nums)
        features['max_number'] = min(max_num, 10000)  # Cap
        features['num_count'] = len(nums)
        # Most real NIST controls: 1-99. SPARTA: 0001-9999. CWE: 1-9999.
        features['number_in_nist_range'] = 1.0 if max_num <= 99 else 0.0
        features['number_in_sparta_range'] = 1.0 if 1 <= max_num <= 9999 else 0.0
    else:
        features['max_number'] = 0
        features['num_count'] = 0
        features['number_in_nist_range'] = 0.0
        features['number_in_sparta_range'] = 0.0

    # Sub-technique pattern (e.g., .01, .003, (12))
    features['has_subtechnique'] = 1.0 if re.search(r'\.\d{2,3}$|\(\d+\)$', entity_id) else 0.0

    # Category-specific patterns
    features['is_sv_pattern'] = 1.0 if re.match(r'^SV-[A-Z]{2,3}-\d+$', entity_id) else 0.0
    features['is_nist_pattern'] = 1.0 if re.match(r'^[A-Z]{2}-\d+(?:\(\d+\))?$', entity_id) else 0.0
    features['is_cwe_pattern'] = 1.0 if re.match(r'^CWE-\d+$', entity_id) else 0.0
    features['is_attack_pattern'] = 1.0 if re.match(r'^T[01]\d{3}', entity_id) else 0.0
    features['is_d3fend_pattern'] = 1.0 if re.match(r'^(D3-[A-Z]+|d3f:\w+)$', entity_id) else 0.0

    # Unusual character patterns (hallucination signals)
    features['has_double_letter_suffix'] = 1.0 if re.search(r'[A-Z]{2,}-[A-Z]{2,}-', entity_id) else 0.0
    features['consecutive_zeros'] = max(len(m) for m in re.findall(r'0+', entity_id)) if '0' in entity_id else 0
    # Very high numbers are suspicious for NIST (AU-99, AC-99)
    if re.match(r'^[A-Z]{2}-\d+$', entity_id):
        num = int(re.search(r'\d+', entity_id).group())
        features['nist_num_suspicious'] = 1.0 if num > 50 else 0.0
    else:
        features['nist_num_suspicious'] = 0.0

    return features


def _generate_training_data(
    real_ids: Set[str],
    n_hallucinated: int = 5000,
) -> Tuple[List[Dict[str, float]], List[int]]:
    """Generate training data: features + labels (1=real, 0=hallucinated).

    Synthetic hallucinated IDs are created by:
    1. Mutating real IDs (swap digits, change prefix letters)
    2. Generating out-of-range numbers
    3. Mixing prefix/suffix from different categories
    4. Creating plausible-looking but non-existent IDs
    """
    random.seed(42)
    known_prefixes = {eid.split('-')[0] for eid in real_ids if '-' in eid}

    # Positive examples: all real IDs
    X, y = [], []
    for eid in real_ids:
        X.append(_extract_features(eid, known_prefixes))
        y.append(1)

    # Negative examples: synthetic hallucinations
    hallucinated = set()

    # Type 1: Out-of-range numbers for NIST
    nist_prefixes = ['AC', 'AT', 'AU', 'CA', 'CM', 'CP', 'IA', 'IR', 'MA',
                     'MP', 'PE', 'PL', 'PM', 'PS', 'PT', 'RA', 'SA', 'SC', 'SI', 'SR']
    for prefix in nist_prefixes:
        for num in [77, 88, 99, 100, 150, 200, 999]:
            cid = f'{prefix}-{num}'
            if cid not in real_ids:
                hallucinated.add(cid)
        # Fake sub-controls
        for num in [50, 60, 70]:
            for sub in [10, 15, 20, 25]:
                cid = f'{prefix}-{num}({sub})'
                if cid not in real_ids:
                    hallucinated.add(cid)

    # Type 2: Fake SPARTA controls
    sparta_prefixes = ['REC', 'RD', 'IA', 'EX', 'PER', 'DE', 'LM', 'EXF', 'IMP']
    for prefix in sparta_prefixes:
        for num in [9000, 9001, 9999, 5555, 8888]:
            cid = f'{prefix}-{num:04d}'
            if cid not in real_ids:
                hallucinated.add(cid)
        for num in [9000, 9500]:
            for sub in range(1, 10):
                cid = f'{prefix}-{num:04d}.{sub:02d}'
                if cid not in real_ids:
                    hallucinated.add(cid)

    # Type 3: Fake SV controls
    sv_mids = ['AA', 'BB', 'CC', 'ZZ', 'XX', 'YY', 'QQ', 'WW']
    for mid in sv_mids:
        for num in range(1, 20):
            cid = f'SV-{mid}-{num}'
            if cid not in real_ids:
                hallucinated.add(cid)

    # Type 4: Fake CWEs (very high numbers)
    for num in [99999, 88888, 77777, 55555, 12345, 9999, 8888, 7777]:
        cid = f'CWE-{num}'
        if cid not in real_ids:
            hallucinated.add(cid)

    # Type 5: Fake ATT&CK techniques
    for num in [9000, 9100, 9200, 9500, 9900]:
        cid = f'T{num}'
        if cid not in real_ids:
            hallucinated.add(cid)
        for sub in range(1, 10):
            cid = f'T{num}.{sub:03d}'
            if cid not in real_ids:
                hallucinated.add(cid)

    # Type 6: Fake D3FEND
    for suffix in ['ZZZZZ', 'FAKE', 'XXXXX', 'BOGUS', 'HALLUC']:
        hallucinated.add(f'D3-{suffix}')

    # Type 7: Mixed category (NIST prefix + SPARTA numbering)
    for prefix in nist_prefixes[:5]:
        for num in [1000, 2000, 3000]:
            cid = f'{prefix}-{num:04d}'
            if cid not in real_ids:
                hallucinated.add(cid)

    # Trim to target
    hallucinated = list(hallucinated)
    if len(hallucinated) > n_hallucinated:
        hallucinated = random.sample(hallucinated, n_hallucinated)

    for eid in hallucinated:
        X.append(_extract_features(eid, known_prefixes))
        y.append(0)

    logger.info(f"Training data: {sum(y)} real, {len(y) - sum(y)} hallucinated")
    return X, y


class EntityClassifier:
    """Gradient boosting classifier for entity ID hallucination detection.

    Combines trie extraction + deterministic validation + ML classification.
    """

    def __init__(self, model_path: Optional[str] = None):
        self._model = None
        self._known_prefixes: Set[str] = set()
        self._model_path = model_path or str(
            Path(__file__).parent / "model.pkl"
        )
        # Lazy-loaded components
        self._extractor = None
        self._validator = None

    @property
    def extractor(self):
        if self._extractor is None:
            from .extractor import EntityExtractor
            self._extractor = EntityExtractor()
            self._extractor.load_from_arango()
        return self._extractor

    @property
    def validator(self):
        if self._validator is None:
            from .validator import EntityValidator
            self._validator = EntityValidator()
            self._validator.load_from_arango()
        return self._validator

    def train(self, real_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
        """Train the hallucination classifier.

        Args:
            real_ids: Set of known-good entity IDs. If None, loads from ArangoDB.

        Returns:
            Training metrics dict.
        """
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report, accuracy_score

        if real_ids is None:
            real_ids = self.extractor._known_ids

        self._known_prefixes = {eid.split('-')[0] for eid in real_ids if '-' in eid}

        # Generate training data
        X_dicts, y = _generate_training_data(real_ids)

        # Convert to feature arrays
        feature_names = sorted(X_dicts[0].keys())
        X = [[d[f] for f in feature_names] for d in X_dicts]

        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Train gradient boosting
        self._model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        )
        self._model.fit(X_train, y_train)

        # Evaluate
        y_pred = self._model.predict(X_test)
        report = classification_report(y_test, y_pred, output_dict=True)
        acc = accuracy_score(y_test, y_pred)

        # Feature importance
        importances = dict(zip(feature_names, self._model.feature_importances_))
        top_features = sorted(importances.items(), key=lambda x: -x[1])[:10]

        # Save model
        self._save(feature_names)

        metrics = {
            'accuracy': acc,
            'precision_real': report['1']['precision'],
            'recall_real': report['1']['recall'],
            'precision_hallucinated': report['0']['precision'],
            'recall_hallucinated': report['0']['recall'],
            'f1_macro': report['macro avg']['f1-score'],
            'top_features': top_features,
            'train_size': len(X_train),
            'test_size': len(X_test),
        }
        logger.info(
            f"Classifier trained: accuracy={acc:.3f}, "
            f"hallucination_recall={report['0']['recall']:.3f}"
        )
        return metrics

    def _save(self, feature_names: List[str]) -> None:
        """Save model and metadata."""
        data = {
            'model': self._model,
            'feature_names': feature_names,
            'known_prefixes': self._known_prefixes,
        }
        with open(self._model_path, 'wb') as f:
            pickle.dump(data, f)
        logger.info(f"Saved classifier to {self._model_path}")

    def load(self) -> bool:
        """Load trained model from disk."""
        if not os.path.exists(self._model_path):
            return False
        with open(self._model_path, 'rb') as f:
            data = pickle.load(f)
        self._model = data['model']
        self._feature_names = data['feature_names']
        self._known_prefixes = data['known_prefixes']
        return True

    def classify(self, entity_id: str) -> Dict[str, Any]:
        """Classify a single entity ID as real or hallucinated.

        Returns:
            {entity_id, prediction: 'real'|'hallucinated', confidence, features}
        """
        if self._model is None:
            if not self.load():
                raise RuntimeError("No trained model. Call train() first.")

        features = _extract_features(entity_id, self._known_prefixes)
        X = [[features[f] for f in self._feature_names]]

        proba = self._model.predict_proba(X)[0]
        pred_class = self._model.predict(X)[0]

        return {
            'entity_id': entity_id,
            'prediction': 'real' if pred_class == 1 else 'hallucinated',
            'confidence': float(max(proba)),
            'prob_real': float(proba[1]) if len(proba) > 1 else float(proba[0]),
        }

    def extract_and_validate(self, text: str) -> List[Dict[str, Any]]:
        """Full pipeline: extract entities from text, validate, classify unknowns.

        This is the main entry point for the quality gate.
        """
        # Stage 1: Trie extraction
        candidates = self.extractor.extract(text)

        # Stage 2: Deterministic validation
        validated = self.validator.validate_batch(candidates)

        # Stage 3: Classify unknowns
        results = []
        for entity in validated:
            if entity.get('valid') is None:
                # Unknown entity — run classifier
                classification = self.classify(entity['entity_id'])
                entity['valid'] = classification['prediction'] == 'real'
                entity['classifier_confidence'] = classification['confidence']
                entity['classification'] = classification['prediction']
            results.append(entity)

        return results
