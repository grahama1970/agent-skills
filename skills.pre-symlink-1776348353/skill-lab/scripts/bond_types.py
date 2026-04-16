"""Bond types, feature extraction, and shared utilities for bond prediction.

Defines the BondFeatures dataclass, BOND_TYPES constants, feature extraction
from AFFINITIES/PRECEDES/graph/traces, and the append_jsonl file-locking helper.
All tiers and the chain predictor depend on this module.
"""
from __future__ import annotations

import fcntl
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from composer import AFFINITIES, PRECEDES, get_affinities
from energy_model import estimate_skill_energy

# ---------------------------------------------------------------------------
# Directory constants
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPTS_DIR.parent.parent

STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

METRICS_FILE = STATE_DIR / "bond_metrics.jsonl"
SHADOW_FILE = STATE_DIR / "bond_shadow.jsonl"
TRACES_FILE = STATE_DIR / "execution_traces.jsonl"
CLASSIFIER_MODEL = STATE_DIR / "bond_classifier.pkl"
GPT_MODEL = STATE_DIR / "bond_gpt.gguf"


# ---------------------------------------------------------------------------
# JSONL file locking -- safe concurrent appends
# ---------------------------------------------------------------------------

def append_jsonl(filepath: Path, entries: list[dict]) -> None:
    """Append JSONL entries with exclusive file locking.

    Prevents corruption when multiple processes (warm pond, nightly harvest,
    production traces) write to the same JSONL file concurrently.
    """
    if not entries:
        return
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Bond types -- the periodic table of skill bonds
# ---------------------------------------------------------------------------

BOND_TYPES = {
    "covalent": "Strong bond -- skills share state/data and produce joint output",
    "ionic": "Weak bond -- skills pass messages but run independently",
    "van_der_waals": "Incidental -- skills can coexist but don't directly interact",
    "none": "No meaningful bond -- skills are unrelated",
}


# ---------------------------------------------------------------------------
# Feature extraction -- shared by all tiers
# ---------------------------------------------------------------------------

@dataclass
class BondFeatures:
    """Feature vector for bond prediction between two skills."""
    skill_a: str
    skill_b: str
    # From AFFINITIES
    affinity_weight: float = 0.0
    reverse_affinity_weight: float = 0.0
    # From PRECEDES
    a_precedes_b: bool = False
    b_precedes_a: bool = False
    # From frontmatter
    a_composes_b: bool = False
    b_composes_a: bool = False
    shared_taxonomy_tags: int = 0
    shared_capabilities: int = 0
    # From execution traces
    co_occurrence_count: int = 0
    success_rate: float = -1.0  # -1 = no data
    avg_latency_ms: float = 0.0
    # Energy model (ATP units)
    energy_a: float = 0.0
    energy_b: float = 0.0

    def to_vector(self) -> list[float]:
        """Convert to numeric vector for classifier."""
        return [
            self.affinity_weight,
            self.reverse_affinity_weight,
            1.0 if self.a_precedes_b else 0.0,
            1.0 if self.b_precedes_a else 0.0,
            1.0 if self.a_composes_b else 0.0,
            1.0 if self.b_composes_a else 0.0,
            float(self.shared_taxonomy_tags),
            float(self.shared_capabilities),
            float(self.co_occurrence_count),
            self.success_rate if self.success_rate >= 0 else 0.0,
            self.avg_latency_ms / 10000.0,  # normalize
            self.energy_a / 15.0,  # normalize (max ~15 ATP)
            self.energy_b / 15.0,
        ]


def extract_features(skill_a: str, skill_b: str, graph: dict | None = None) -> BondFeatures:
    """Extract bond features between two skills."""
    features = BondFeatures(skill_a=skill_a, skill_b=skill_b)

    # AFFINITIES lookup (learned affinities overlay static ones)
    _affinities = get_affinities()
    for partner, weight in _affinities.get(skill_a, []):
        if partner == skill_b:
            features.affinity_weight = weight
            break
    for partner, weight in _affinities.get(skill_b, []):
        if partner == skill_a:
            features.reverse_affinity_weight = weight
            break

    # PRECEDES lookup
    features.a_precedes_b = skill_b in PRECEDES.get(skill_a, [])
    features.b_precedes_a = skill_a in PRECEDES.get(skill_b, [])

    # Graph-based features (if available)
    if graph:
        info_a = graph.get("skills", {}).get(skill_a, {})
        info_b = graph.get("skills", {}).get(skill_b, {})

        features.a_composes_b = skill_b in info_a.get("composes", [])
        features.b_composes_a = skill_a in info_b.get("composes", [])

        tax_a = set(info_a.get("taxonomy", []))
        tax_b = set(info_b.get("taxonomy", []))
        features.shared_taxonomy_tags = len(tax_a & tax_b)

        caps_a = set(info_a.get("provides", []))
        caps_b = set(info_b.get("provides", []))
        features.shared_capabilities = len(caps_a & caps_b)

    # Execution trace features
    traces = _load_traces(skill_a, skill_b)
    if traces:
        features.co_occurrence_count = len(traces)
        successes = sum(1 for t in traces if t.get("success"))
        features.success_rate = successes / len(traces) if traces else -1.0
        latencies = [t.get("latency_ms", 0) for t in traces]
        features.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

    # Energy model features
    features.energy_a = estimate_skill_energy(skill_a, graph)
    features.energy_b = estimate_skill_energy(skill_b, graph)

    return features


def _load_traces(skill_a: str, skill_b: str) -> list[dict]:
    """Load execution traces for a skill pair."""
    if not TRACES_FILE.exists():
        return []
    pair_key = f"{skill_a}+{skill_b}"
    reverse_key = f"{skill_b}+{skill_a}"
    traces = []
    for line in TRACES_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            pair = entry.get("pair", "")
            if pair == pair_key or pair == reverse_key:
                traces.append(entry)
        except json.JSONDecodeError:
            continue
    return traces
