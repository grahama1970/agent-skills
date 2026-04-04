"""Trie-based entity ID extractor.

Uses an Aho-Corasick automaton built from all known entity IDs to extract
candidate entities from natural language text. This replaces brittle regex
patterns and handles compound IDs (SV-SP-1) correctly without sub-matching.

Key advantages over regex:
  - No sub-pattern extraction (SP-1 from SV-SP-1)
  - Handles all ID formats uniformly
  - O(n) text scanning regardless of pattern count
  - Easy to update: just rebuild the trie with new IDs
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple


class EntityExtractor:
    """Trie-based entity extractor with longest-match semantics."""

    # Category patterns for classifying extracted entities
    CATEGORY_PATTERNS = [
        (re.compile(r'^SV-[A-Z]{2,3}-\d+$'), 'SPARTA'),
        (re.compile(r'^(REC|RD|IA|EX|PER|DE|LM|EXF|IMP)-\d{4}'), 'SPARTA'),
        (re.compile(r'^(AC|AT|AU|CA|CM|CP|IA|IR|MA|MP|PE|PL|PM|PS|PT|RA|SA|SC|SI|SR)-\d'), 'NIST'),
        (re.compile(r'^CWE-\d+$'), 'CWE'),
        (re.compile(r'^T[01]\d{3}'), 'ATTACK'),
        (re.compile(r'^D3-[A-Z]+$'), 'D3FEND'),
        (re.compile(r'^d3f:\w+$'), 'D3FEND'),
        (re.compile(r'^CM\d{4}$'), 'COUNTERMEASURE'),
        (re.compile(r'^ESA-T\d+$'), 'ESA'),
        (re.compile(r'^(ARFS|CSNE|DISE|GNTM|MIRE|SIUU|SMSR|UACE|UCEB|WTRE)-\d+$'), 'AEROSPACE_STD'),
    ]

    def __init__(self, known_ids: Optional[Set[str]] = None):
        """Initialize extractor with known entity IDs.

        Args:
            known_ids: Set of all valid entity IDs. If None, loads from ArangoDB.
        """
        self._known_ids: Set[str] = known_ids or set()
        self._trie: Dict[str, Any] = {}
        self._built = False

        if self._known_ids:
            self._build_trie()

    def load_from_arango(self) -> int:
        """Load known entity IDs from ArangoDB."""
        import sys
        from pathlib import Path
        _src = str(Path(__file__).resolve().parents[5] / "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)

        from graph_memory.arango_client import get_db
        db = get_db()

        # Load from controls (skip sentence-length noise)
        controls = list(db.aql.execute(
            "FOR doc IN controls RETURN doc.control_id"
        ))
        for cid in controls:
            if cid and isinstance(cid, str) and len(cid) < 50:
                self._known_ids.add(cid)

        # Load from QRAs (these are definitely real — they have content)
        qra_ids = list(db.aql.execute(
            "FOR doc IN sparta_qra COLLECT ctrl = doc.control_id RETURN ctrl"
        ))
        for cid in qra_ids:
            if cid and isinstance(cid, str):
                self._known_ids.add(cid)

        self._build_trie()
        return len(self._known_ids)

    def _build_trie(self) -> None:
        """Build Aho-Corasick-style trie from known IDs.

        We use a simple dict-based trie with longest-match semantics.
        For ~4000 IDs this is fast enough without pyahocorasick.
        """
        self._trie = {}
        for entity_id in self._known_ids:
            node = self._trie
            for char in entity_id:
                node = node.setdefault(char, {})
            node['$'] = entity_id  # Terminal marker with full ID
        self._built = True

    def extract(self, text: str) -> List[Dict[str, Any]]:
        """Extract entity IDs from text using trie longest-match.

        Returns list of dicts: {entity_id, category, start, end, known}
        """
        if not self._built:
            if not self._known_ids:
                self.load_from_arango()
            else:
                self._build_trie()

        results = []
        seen = set()
        i = 0

        while i < len(text):
            # Check for word boundary: entity IDs start after space, paren, etc.
            if i > 0 and text[i - 1].isalnum() and text[i - 1] != '-':
                i += 1
                continue

            # Try longest match from position i
            match = self._longest_match(text, i)
            if match:
                entity_id, end_pos = match
                # Verify word boundary at end — if more alphanums follow,
                # this trie match is a prefix of a longer (unknown) ID.
                # Fall through to regex to capture the full ID.
                if end_pos < len(text) and (text[end_pos].isdigit() or text[end_pos] == '('):
                    # Trie matched a prefix (e.g. AC-9) but text has AC-99
                    candidate = self._regex_candidate(text, i)
                    if candidate:
                        cid, cend = candidate
                        if cid not in seen:
                            seen.add(cid)
                            results.append({
                                'entity_id': cid,
                                'category': self._categorize(cid),
                                'start': i,
                                'end': cend,
                                'known': cid in self._known_ids,
                            })
                        i = cend
                        continue
                    # Regex also failed — skip
                    i += 1
                    continue
                elif end_pos < len(text) and text[end_pos].isalpha():
                    # e.g. "ACME" — not an entity, skip
                    i += 1
                    continue

                if entity_id not in seen:
                    seen.add(entity_id)
                    results.append({
                        'entity_id': entity_id,
                        'category': self._categorize(entity_id),
                        'start': i,
                        'end': end_pos,
                        'known': True,
                    })
                i = end_pos
            else:
                # Try regex fallback for unknown IDs (potential hallucinations)
                candidate = self._regex_candidate(text, i)
                if candidate:
                    cid, end_pos = candidate
                    if cid not in seen and cid not in self._known_ids:
                        seen.add(cid)
                        results.append({
                            'entity_id': cid,
                            'category': self._categorize(cid),
                            'start': i,
                            'end': end_pos,
                            'known': False,  # Not in trie = possibly hallucinated
                        })
                    i = end_pos
                else:
                    i += 1

        return results

    def _longest_match(self, text: str, start: int) -> Optional[Tuple[str, int]]:
        """Find longest trie match starting at position."""
        node = self._trie
        best = None
        pos = start

        while pos < len(text):
            char = text[pos]
            if char not in node:
                break
            node = node[char]
            pos += 1
            if '$' in node:
                best = (node['$'], pos)

        return best

    def _regex_candidate(self, text: str, start: int) -> Optional[Tuple[str, int]]:
        """Fallback regex extraction for IDs not in trie (potential hallucinations).

        Only matches structured ID patterns — not arbitrary text.
        """
        patterns = [
            re.compile(r'SV-[A-Z]{2,3}-\d+'),
            re.compile(r'(?:REC|RD|IA|EX|PER|DE|LM|EXF|IMP)-\d{4}(?:\.\d{2})?'),
            re.compile(r'(?:AC|AT|AU|CA|CM|CP|IR|MA|MP|PE|PL|PM|PS|PT|RA|SA|SC|SI|SR)-\d+(?:\(\d+\))?'),
            re.compile(r'CWE-\d+'),
            re.compile(r'T[01]\d{3}(?:\.\d{3})?'),
            re.compile(r'D3-[A-Z]+'),
            re.compile(r'd3f:\w+'),
            re.compile(r'CM\d{4}'),
            re.compile(r'ESA-T\d+'),
        ]
        for pat in patterns:
            m = pat.match(text, start)
            if m:
                return (m.group(0), m.end())
        return None

    def _categorize(self, entity_id: str) -> str:
        """Classify entity ID into category."""
        for pattern, category in self.CATEGORY_PATTERNS:
            if pattern.match(entity_id):
                return category
        return 'UNKNOWN'

    def is_known(self, entity_id: str) -> bool:
        """Check if entity ID exists in the knowledge graph."""
        return entity_id in self._known_ids
