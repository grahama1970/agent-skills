"""
Prompt Lab Skill - Ground Truth Building
Stratified sampling from SPARTA data sources for ground truth generation.
"""
import csv
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

from config import (
    SKILL_DIR,
    SPARTA_DATA,
    SPARTA_TAXONOMY,
    TIER0_CONCEPTUAL,
    TIER1_TACTICAL,
)


def load_attck_techniques(limit: int = 15) -> List[Dict[str, Any]]:
    """
    Load ATT&CK techniques from enterprise-attack.json.

    Args:
        limit: Maximum number of samples

    Returns:
        List of technique dicts with id, name, description, collection
    """
    attck_file = SPARTA_DATA / "enterprise-attack.json"
    if not attck_file.exists():
        return []

    data = json.loads(attck_file.read_text())

    # Filter for attack-pattern objects (techniques)
    techniques = [
        obj for obj in data.get("objects", [])
        if obj.get("type") == "attack-pattern" and not obj.get("revoked", False)
    ]

    # Stratified sample by kill chain phase
    by_tactic = {}
    for t in techniques:
        phases = t.get("kill_chain_phases", [])
        for phase in phases:
            tactic = phase.get("phase_name", "unknown")
            if tactic not in by_tactic:
                by_tactic[tactic] = []
            by_tactic[tactic].append(t)

    # Sample evenly across tactics
    sampled = []
    tactics = list(by_tactic.keys())
    random.shuffle(tactics)

    per_tactic = max(1, limit // len(tactics))
    for tactic in tactics:
        available = by_tactic[tactic]
        random.shuffle(available)
        sampled.extend(available[:per_tactic])
        if len(sampled) >= limit:
            break

    # Convert to standard format
    results = []
    for t in sampled[:limit]:
        results.append({
            "id": t.get("external_references", [{}])[0].get("external_id", t.get("id", "")),
            "name": t.get("name", ""),
            "description": t.get("description", "")[:500],
            "collection": "ATT&CK",
            "tactic": t.get("kill_chain_phases", [{}])[0].get("phase_name", ""),
        })

    return results


def load_nist_controls(limit: int = 15) -> List[Dict[str, Any]]:
    """
    Load NIST controls from CSV.

    Args:
        limit: Maximum number of samples

    Returns:
        List of control dicts
    """
    nist_file = SPARTA_DATA / "nist_rev4_controls.csv"
    if not nist_file.exists():
        return []

    # Read CSV
    with open(nist_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        controls = list(reader)

    # Group by family
    by_family = {}
    for c in controls:
        family = c.get("FAMILY", "Unknown")
        if family not in by_family:
            by_family[family] = []
        by_family[family].append(c)

    # Sample across families
    sampled = []
    families = list(by_family.keys())
    random.shuffle(families)

    per_family = max(1, limit // len(families))
    for family in families:
        available = by_family[family]
        random.shuffle(available)
        sampled.extend(available[:per_family])
        if len(sampled) >= limit:
            break

    # Convert to standard format
    results = []
    for c in sampled[:limit]:
        results.append({
            "id": c.get("NAME", ""),
            "name": c.get("TITLE", ""),
            "description": c.get("DESCRIPTION", "")[:500],
            "collection": "NIST",
            "family": c.get("FAMILY", ""),
        })

    return results


def load_cwe_weaknesses(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Load CWE weaknesses from CSV.

    Args:
        limit: Maximum number of samples

    Returns:
        List of weakness dicts
    """
    cwe_file = SPARTA_DATA / "cwe.csv"
    if not cwe_file.exists():
        return []

    with open(cwe_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        weaknesses = list(reader)

    # Sample randomly (CWE doesn't have clean hierarchy)
    random.shuffle(weaknesses)

    results = []
    for w in weaknesses[:limit]:
        results.append({
            "id": f"CWE-{w.get('cwe_id', '')}",
            "name": w.get("name", ""),
            "description": w.get("description", "")[:500],
            "collection": "CWE",
            "categories": w.get("categories", ""),
        })

    return results


def load_d3fend_techniques(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Load D3FEND defensive techniques from CSV.

    Args:
        limit: Maximum number of samples

    Returns:
        List of technique dicts
    """
    d3fend_file = SPARTA_DATA / "d3fend_techniques.csv"
    if not d3fend_file.exists():
        return []

    with open(d3fend_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        techniques = list(reader)

    # Group by tactic
    by_tactic = {}
    for t in techniques:
        tactic = t.get("Tactic", "Unknown")
        if tactic not in by_tactic:
            by_tactic[tactic] = []
        by_tactic[tactic].append(t)

    # Sample across tactics
    sampled = []
    tactics = list(by_tactic.keys())
    random.shuffle(tactics)

    per_tactic = max(1, limit // len(tactics))
    for tactic in tactics:
        available = by_tactic[tactic]
        random.shuffle(available)
        sampled.extend(available[:per_tactic])
        if len(sampled) >= limit:
            break

    results = []
    for t in sampled[:limit]:
        results.append({
            "id": f"d3f:{t.get('ID', '')}",
            "name": t.get("Name", ""),
            "description": t.get("Definition", "")[:500],
            "collection": "D3FEND",
            "tactic": t.get("Tactic", ""),
        })

    return results


def run_keyword_scorer(text: str) -> Tuple[List[str], List[str]]:
    """
    Run keyword-based tag extraction.

    Args:
        text: Combined name + description text

    Returns:
        Tuple of (conceptual_tags, tactical_tags)
    """
    try:
        # Try importing from SPARTA
        sys.path.insert(0, str(SPARTA_TAXONOMY.parent.parent))
        from sparta.taxonomy.keyword_extractor import extract_tags_from_text
        return extract_tags_from_text(text, threshold=1)
    except ImportError:
        pass

    # Fallback: simple keyword matching
    text_lower = text.lower()

    conceptual = []
    tactical = []

    # Simple heuristics
    if any(kw in text_lower for kw in ["persistence", "backdoor", "implant", "maintain"]):
        conceptual.append("Corruption")
        tactical.append("Persist")
    if any(kw in text_lower for kw in ["vulnerability", "weakness", "exploit", "injection", "flaw"]):
        conceptual.append("Fragility")
        tactical.append("Exploit")
    if any(kw in text_lower for kw in ["evasion", "obfuscate", "bypass", "hide", "clear"]):
        conceptual.append("Stealth")
        tactical.append("Evade")
    if any(kw in text_lower for kw in ["authenticate", "authorization", "access control", "credential"]):
        conceptual.append("Loyalty")
        tactical.append("Harden")
    if any(kw in text_lower for kw in ["backup", "recover", "restore", "remediate"]):
        conceptual.append("Resilience")
        tactical.append("Restore")
    if any(kw in text_lower for kw in ["harden", "patch", "protect", "defense", "security"]):
        conceptual.append("Resilience")
        tactical.append("Harden")
    if any(kw in text_lower for kw in ["reconnaissance", "scan", "discover", "enumerate"]):
        conceptual.append("Precision")
        tactical.append("Model")
    if any(kw in text_lower for kw in ["isolate", "segment", "quarantine", "contain"]):
        conceptual.append("Resilience")
        tactical.append("Isolate")
    if any(kw in text_lower for kw in ["monitor", "detect", "alert", "log"]):
        conceptual.append("Loyalty")
        tactical.append("Detect")

    # Deduplicate
    conceptual = list(dict.fromkeys(conceptual))
    tactical = list(dict.fromkeys(tactical))

    # Default if nothing found
    if not conceptual:
        conceptual = ["Resilience"]
    if not tactical:
        tactical = ["Harden"]

    return conceptual, tactical


def collect_all_samples(
    attck_count: int = 15,
    nist_count: int = 15,
    cwe_count: int = 10,
    d3fend_count: int = 10,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Collect stratified samples from all SPARTA sources.

    Returns:
        Tuple of (samples, counts_by_source)
    """
    samples = []
    counts = {}

    attck = load_attck_techniques(attck_count)
    samples.extend(attck)
    counts["attck"] = len(attck)

    nist = load_nist_controls(nist_count)
    samples.extend(nist)
    counts["nist"] = len(nist)

    cwe = load_cwe_weaknesses(cwe_count)
    samples.extend(cwe)
    counts["cwe"] = len(cwe)

    d3fend = load_d3fend_techniques(d3fend_count)
    samples.extend(d3fend)
    counts["d3fend"] = len(d3fend)

    return samples, counts


def build_keyword_ground_truth(
    output_name: str,
    samples: List[Dict[str, Any]],
    counts: Dict[str, int],
    seed: int,
    skill_dir: Path = SKILL_DIR,
) -> Path:
    """
    Build ground truth using keyword scorer.

    Args:
        output_name: Name for the output file
        samples: List of sample dicts
        counts: Count by source
        seed: Random seed used
        skill_dir: Skill directory

    Returns:
        Path to saved ground truth file
    """
    cases = []
    for sample in samples:
        text = f"{sample['name']} {sample['description']}"
        conceptual, tactical = run_keyword_scorer(text)

        cases.append({
            "id": sample["id"],
            "input": {
                "name": sample["name"],
                "description": sample["description"],
            },
            "expected": {
                "conceptual": conceptual[:2],  # Limit to top 2
                "tactical": tactical[:2],
            },
            "metadata": {
                "collection": sample["collection"],
                "keyword_scorer_raw": {
                    "conceptual": conceptual,
                    "tactical": tactical,
                },
            },
            "notes": f"Auto-generated from {sample['collection']}",
        })

    gt_data = {
        "name": output_name,
        "description": f"Stratified ground truth from SPARTA data ({len(samples)} samples)",
        "generated": datetime.now().isoformat(),
        "seed": seed,
        "counts": counts,
        "cases": cases,
    }

    gt_file = skill_dir / "ground_truth" / f"{output_name}.json"
    gt_file.parent.mkdir(parents=True, exist_ok=True)
    gt_file.write_text(json.dumps(gt_data, indent=2))

    return gt_file


def build_llm_ground_truth(
    output_name: str,
    cases: List[Dict[str, Any]],
    counts: Dict[str, int],
    seed: int,
    model: str,
    prompt: str,
    confidence_threshold: float,
    flagged_count: int,
    skill_dir: Path = SKILL_DIR,
) -> Path:
    """
    Save LLM-generated ground truth.

    Args:
        output_name: Name for the output file
        cases: List of case dicts with LLM predictions
        counts: Count by source
        seed: Random seed used
        model: Model used for generation
        prompt: Prompt used
        confidence_threshold: Threshold for flagging
        flagged_count: Number of flagged cases
        skill_dir: Skill directory

    Returns:
        Path to saved ground truth file
    """
    gt_data = {
        "name": output_name,
        "description": f"LLM-generated ground truth ({len(cases)} samples, {flagged_count} flagged)",
        "generated": datetime.now().isoformat(),
        "seed": seed,
        "model": model,
        "prompt": prompt,
        "confidence_threshold": confidence_threshold,
        "counts": {
            **counts,
            "total": len(cases),
            "flagged_for_review": flagged_count,
        },
        "cases": cases,
    }

    gt_file = skill_dir / "ground_truth" / f"{output_name}.json"
    gt_file.parent.mkdir(parents=True, exist_ok=True)
    gt_file.write_text(json.dumps(gt_data, indent=2))

    return gt_file
