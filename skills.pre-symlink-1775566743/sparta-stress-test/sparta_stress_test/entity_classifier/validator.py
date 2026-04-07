"""Entity ID validator — deterministic lookup + structural validation.

For entity IDs found by the trie extractor, validates:
  1. Known: Is the ID in ArangoDB? (trie lookup — instant)
  2. Structural: Does the ID follow valid patterns for its category?
  3. QRA coverage: Does the ID have QRA content? (useful for stress test)

This is the fast, deterministic layer. The classifier (classifier.py)
handles the harder case of "looks valid but doesn't exist — hallucination?"
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set


# Structural validators per category
VALIDATORS = {
    'SPARTA': re.compile(r'^SV-[A-Z]{2,3}-\d+$'),
    'NIST': re.compile(r'^[A-Z]{2}-\d+(?:\(\d+\))?$'),
    'CWE': re.compile(r'^CWE-\d+$'),
    'ATTACK': re.compile(r'^T[01]\d{3}(?:\.\d{3})?$'),
    'D3FEND': re.compile(r'^(?:D3-[A-Z]+|d3f:\w+)$'),
    'COUNTERMEASURE': re.compile(r'^CM\d{4}$'),
    'ESA': re.compile(r'^ESA-T\d+$'),
    'AEROSPACE_STD': re.compile(r'^[A-Z]{2,4}-\d+$'),
}

# NIST SP 800-53 valid family prefixes
NIST_FAMILIES = {
    'AC', 'AT', 'AU', 'CA', 'CM', 'CP', 'IA', 'IR', 'MA', 'MP',
    'PE', 'PL', 'PM', 'PS', 'PT', 'RA', 'SA', 'SC', 'SI', 'SR',
}

# SPARTA tactic prefixes
SPARTA_TACTICS = {
    'REC', 'RD', 'IA', 'EX', 'PER', 'DE', 'LM', 'EXF', 'IMP', 'SV',
}


class EntityValidator:
    """Deterministic entity ID validator."""

    def __init__(
        self,
        known_ids: Optional[Set[str]] = None,
        qra_ids: Optional[Set[str]] = None,
    ):
        self._known_ids = known_ids or set()
        self._qra_ids = qra_ids or set()

    def load_from_arango(self) -> None:
        """Load validation sets from ArangoDB."""
        import sys
        from pathlib import Path
        _src = str(Path(__file__).resolve().parents[5] / "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)

        from graph_memory.arango_client import get_db
        db = get_db()

        # All known control IDs (skip sentence noise)
        controls = list(db.aql.execute("FOR doc IN controls RETURN doc.control_id"))
        self._known_ids = {str(c) for c in controls if c and len(str(c)) < 50}

        # QRA-covered IDs
        qra = list(db.aql.execute(
            "FOR doc IN sparta_qra COLLECT ctrl = doc.control_id RETURN ctrl"
        ))
        self._qra_ids = {str(c) for c in qra if c}

        # QRA IDs are also known
        self._known_ids |= self._qra_ids

    def validate(self, entity_id: str, category: str = '') -> Dict[str, Any]:
        """Validate a single entity ID.

        Returns dict with:
          - valid: bool (structurally correct + exists in graph)
          - exists: bool (in controls/QRA collections)
          - has_qra: bool (has QRA content)
          - structural: bool (matches expected pattern)
          - confidence: float (0-1)
          - reason: str
        """
        result = {
            'entity_id': entity_id,
            'category': category,
            'exists': entity_id in self._known_ids,
            'has_qra': entity_id in self._qra_ids,
            'structural': self._check_structural(entity_id, category),
        }

        # Determine validity
        if result['exists']:
            result['valid'] = True
            result['confidence'] = 1.0
            result['reason'] = 'known_entity'
        elif result['structural']:
            # Structurally valid but not in graph — needs classifier
            result['valid'] = None  # Unknown, defer to classifier
            result['confidence'] = 0.5
            result['reason'] = 'structural_match_not_in_graph'
        else:
            result['valid'] = False
            result['confidence'] = 0.9
            result['reason'] = 'invalid_structure'

        return result

    def validate_batch(self, entities: List[Dict]) -> List[Dict]:
        """Validate a batch of extracted entities."""
        return [
            {**e, **self.validate(e['entity_id'], e.get('category', ''))}
            for e in entities
        ]

    def _check_structural(self, entity_id: str, category: str) -> bool:
        """Check if entity ID follows structural rules for its category."""
        if category and category in VALIDATORS:
            return bool(VALIDATORS[category].match(entity_id))

        # Try all validators
        for cat, pat in VALIDATORS.items():
            if pat.match(entity_id):
                return True

        # Additional structural checks
        if entity_id.startswith('SV-'):
            parts = entity_id.split('-')
            return len(parts) == 3 and parts[2].isdigit()

        # NIST family check
        prefix = entity_id.split('-')[0] if '-' in entity_id else ''
        if prefix in NIST_FAMILIES:
            return bool(re.match(r'^[A-Z]{2}-\d+(?:\(\d+\))?$', entity_id))

        return False
