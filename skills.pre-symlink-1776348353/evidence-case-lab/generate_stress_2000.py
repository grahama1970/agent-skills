#!/usr/bin/env python3
"""Generate ~2000 stress test questions with ENFORCED stratified random sampling.

Stratification by source_framework (proportional to control distribution in
sparta_controls). Every generated question is tagged with its framework stratum
for audit. The retrieval pipeline under test is:
  BM25 + semantic + multi-hop graph traversal

Framework distribution (10,151 controls, normalized):
  NVD:     3,976 (39.2%) → 706 questions
  ATT&CK:  2,144 (21.1%) → 380 questions
  NIST:    1,905 (18.8%) → 338 questions
  CWE:       969  (9.5%) → 172 questions
  SPARTA:    559  (5.5%) →  99 questions
  D3FEND:    424  (4.2%) →  75 questions
  ESA:       137  (1.3%) →  24 questions
  ISO:        23  (0.2%) →   5 questions (floor)
  NASA:       14  (0.1%) →   5 questions (floor)
  + ~200 adversarial (not_satisfied)
  + ~50 regression (R01-R40 + ADV01-ADV10)

Total target: ~2,054 questions
"""
import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

random.seed(42)

# Reuse base generator infrastructure
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_stress_questions import (
    ADVERSARIAL_QUESTIONS,
    CROSS_CONTROL_TEMPLATES,
    EXISTING_QUESTIONS,
    SINGLE_CONTROL_TEMPLATES,
    STATE_DIR,
    SUBSYSTEMS,
    THREATS,
    generate_persona_questions,
)

MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT", str(Path.home() / "workspace/experiments/memory")
))

# ── Framework normalization map ─────────────────────────────────────────
# Maps raw source_framework values (with case inconsistencies) to normalized names.
FRAMEWORK_NORMALIZE = {
    "nvd": "NVD", "NVD": "NVD",
    "NIST": "NIST", "nist": "NIST",
    "ATT_CK_Enterprise": "ATT&CK", "ATT_CK_Mobile": "ATT&CK",
    "ATT_CK_ICS": "ATT&CK", "attack": "ATT&CK",
    "CWE": "CWE", "cwe": "CWE",
    "SPARTA": "SPARTA", "sparta": "SPARTA",
    "D3FEND": "D3FEND", "d3fend": "D3FEND",
    "ESA": "ESA",
    "ISO": "ISO", "iso": "ISO",
    "NASA": "NASA",
}

# Minimum question floor for small frameworks
MIN_QUESTIONS_PER_FRAMEWORK = 5

# Target real questions (adversarial are separate)
TARGET_REAL_QUESTIONS = 1800


def _get_arango_db():
    """Get ArangoDB connection via graph_memory API."""
    sys.path.insert(0, str(MEMORY_ROOT / "src"))
    from graph_memory.arango_client import get_db
    return get_db()


def _query_framework_distribution(db) -> dict[str, int]:
    """Query sparta_controls for control counts per normalized framework."""
    cursor = db.aql.execute('''
        FOR c IN sparta_controls
          COLLECT fw = c.source_framework WITH COUNT INTO cnt
          RETURN {framework: fw, count: cnt}
    ''')
    raw = {r["framework"]: r["count"] for r in cursor}

    # Normalize and aggregate
    normalized: dict[str, int] = {}
    for raw_fw, count in raw.items():
        norm = FRAMEWORK_NORMALIZE.get(raw_fw)
        if norm is None:
            print(f"  WARNING: Unknown framework '{raw_fw}' ({count} controls) — skipping")
            continue
        normalized[norm] = normalized.get(norm, 0) + count

    return normalized


def _compute_quotas(distribution: dict[str, int], target: int) -> dict[str, int]:
    """Compute proportional question quotas with minimum floor."""
    total_controls = sum(distribution.values())
    quotas = {}

    for fw, count in distribution.items():
        proportion = count / total_controls
        quota = max(MIN_QUESTIONS_PER_FRAMEWORK, round(proportion * target))
        quotas[fw] = quota

    # Adjust to hit target (proportional scaling of large frameworks)
    current_total = sum(quotas.values())
    if current_total != target:
        diff = target - current_total
        # Sort by quota descending, adjust largest frameworks
        sorted_fws = sorted(quotas.keys(), key=lambda f: quotas[f], reverse=True)
        for fw in sorted_fws:
            if diff == 0:
                break
            adjust = max(-quotas[fw] + MIN_QUESTIONS_PER_FRAMEWORK,
                         min(diff, abs(diff)))
            if diff > 0:
                adjust = min(diff, max(1, quotas[fw] // 10))
            else:
                adjust = max(diff, -max(1, quotas[fw] // 10))
            quotas[fw] += adjust
            diff -= adjust

    return quotas


def _sample_qras_by_framework(db, framework_raw_names: list[str],
                               limit: int) -> list[dict]:
    """Sample QRAs from sparta_qra filtered by control_ids in given frameworks.

    Uses AQL with RAND() for random sampling — one round-trip, not a loop.
    """
    cursor = db.aql.execute('''
        LET fw_controls = (
            FOR c IN sparta_controls
              FILTER c.source_framework IN @frameworks
              RETURN c.control_id
        )
        FOR q IN sparta_qra
          FILTER q.control_id IN fw_controls
          SORT RAND()
          LIMIT @limit
          RETURN {
            control_id: q.control_id,
            question: q.question,
            tags: q.tags
          }
    ''', bind_vars={"frameworks": framework_raw_names, "limit": limit})
    return list(cursor)


def _get_raw_framework_names(normalized: str) -> list[str]:
    """Get all raw source_framework values that map to a normalized name."""
    return [raw for raw, norm in FRAMEWORK_NORMALIZE.items() if norm == normalized]


def generate_stratified_questions(db, quotas: dict[str, int]) -> list[dict]:
    """Generate questions stratified by source_framework.

    For each framework stratum:
    1. Sample QRAs proportionally from that framework's controls
    2. Build cross-control and single-control questions using templates
    3. Tag each question with its framework stratum
    """
    all_questions = []

    for framework, quota in sorted(quotas.items(), key=lambda x: -x[1]):
        raw_names = _get_raw_framework_names(framework)
        sample_size = min(quota * 3, 2000)  # oversample for pair generation

        print(f"\n  {framework}: quota={quota}, sampling {sample_size} QRAs...")
        docs = _sample_qras_by_framework(db, raw_names, sample_size)

        if not docs:
            print(f"    WARNING: No QRAs found for {framework}")
            continue

        print(f"    Got {len(docs)} QRAs")
        random.shuffle(docs)

        questions = []

        # Cross-control pairs (60% of quota)
        cross_target = int(quota * 0.6)
        pairs = []
        for i in range(0, len(docs) - 1, 2):
            a, b = docs[i], docs[i + 1]
            a_ctrl = a.get("control_id", "")
            b_ctrl = b.get("control_id", "")
            if a_ctrl and b_ctrl and a_ctrl != b_ctrl:
                pairs.append((a, b))
            if len(pairs) >= cross_target:
                break

        for a, b in pairs:
            template = random.choice(CROSS_CONTROL_TEMPLATES)
            raw_a = a.get("question", "cybersecurity controls")
            raw_b = b.get("question", "threat mitigation")
            topic_a = raw_a.split("?")[0].split(".")[0][:60].strip()
            topic_b = raw_b.split("?")[0].split(".")[0][:60].strip()
            a_ctrl = a.get("control_id", "unknown")
            b_ctrl = b.get("control_id", "unknown")

            q_text = template.format(
                ctrl_a=a_ctrl, ctrl_b=b_ctrl,
                topic_a=topic_a, topic_b=topic_b,
            )
            qid = hashlib.sha256(q_text.encode()).hexdigest()[:8]
            questions.append({
                "id": f"S-{framework[:3]}-{qid}",
                "question": q_text,
                "expected": "satisfied",
                "source": "stratified_cross_control",
                "framework_stratum": framework,
            })

        # Single-control questions (remaining 40%)
        single_target = quota - len(questions)
        used = set()
        for doc in docs:
            if len(questions) >= quota:
                break
            ctrl = doc.get("control_id", "")
            if not ctrl or ctrl in used:
                continue
            used.add(ctrl)
            template = random.choice(SINGLE_CONTROL_TEMPLATES)
            subsystem = random.choice(SUBSYSTEMS)
            threat = random.choice(THREATS)
            q_text = template.format(ctrl=ctrl, subsystem=subsystem, threat=threat)
            qid = hashlib.sha256(q_text.encode()).hexdigest()[:8]
            questions.append({
                "id": f"S-{framework[:3]}-{qid}",
                "question": q_text,
                "expected": "satisfied",
                "source": "stratified_single_control",
                "framework_stratum": framework,
            })

        print(f"    Generated {len(questions)}/{quota} questions for {framework}")
        all_questions.extend(questions[:quota])

    return all_questions


def main():
    output_file = STATE_DIR / "questions_stress_2000.json"

    print("=" * 60)
    print("Stratified Stress Test Generator (2000 questions)")
    print("Retrieval pipeline: BM25 + semantic + multi-hop graph traversal")
    print("=" * 60)

    # Step 1: Get framework distribution from ArangoDB
    print("\nStep 1: Querying source_framework distribution...")
    db = _get_arango_db()
    distribution = _query_framework_distribution(db)
    total_controls = sum(distribution.values())
    print(f"  Total controls: {total_controls}")
    for fw, count in sorted(distribution.items(), key=lambda x: -x[1]):
        pct = count / total_controls * 100
        print(f"    {fw:12s}: {count:5d} ({pct:5.1f}%)")

    # Step 2: Compute proportional quotas
    print(f"\nStep 2: Computing quotas for {TARGET_REAL_QUESTIONS} real questions...")
    quotas = _compute_quotas(distribution, TARGET_REAL_QUESTIONS)
    for fw, quota in sorted(quotas.items(), key=lambda x: -x[1]):
        pct = quota / TARGET_REAL_QUESTIONS * 100
        print(f"    {fw:12s}: {quota:4d} questions ({pct:5.1f}%)")
    print(f"    Total: {sum(quotas.values())}")

    # Step 3: Load existing regression questions (R01-R40 + ADV01-ADV10)
    existing = []
    if EXISTING_QUESTIONS.exists():
        all_existing = json.loads(EXISTING_QUESTIONS.read_text())
        existing = [
            q for q in all_existing
            if q["id"].startswith("R") or q["id"].startswith("ADV")
        ]
        print(f"\nStep 3: Loaded {len(existing)} regression questions")
    else:
        print("\nStep 3: No existing regression questions found")

    # Step 4: Generate stratified questions
    print("\nStep 4: Generating stratified questions...")
    stratified = generate_stratified_questions(db, quotas)

    # Step 5: Adversarial questions
    adversarial = ADVERSARIAL_QUESTIONS
    print(f"\nStep 5: Added {len(adversarial)} adversarial questions")

    # Step 6: Combine and deduplicate
    all_questions = existing + stratified + adversarial

    seen = set()
    deduped = []
    for q in all_questions:
        key = q["question"].strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(q)

    # Shuffle non-regression questions
    regression = [
        q for q in deduped
        if q["id"].startswith("R") or q["id"].startswith("ADV0")
    ]
    new_qs = [q for q in deduped if q not in regression]
    random.shuffle(new_qs)
    final = regression + new_qs

    # Write output
    output_file.write_text(json.dumps(final, indent=2))

    # Step 7: Stats and audit
    satisfied = sum(1 for q in final if q["expected"] == "satisfied")
    not_satisfied = sum(1 for q in final if q["expected"] == "not_satisfied")

    # Framework stratum audit
    stratum_counts: dict[str, int] = {}
    for q in final:
        fw = q.get("framework_stratum", "regression/adversarial")
        stratum_counts[fw] = stratum_counts.get(fw, 0) + 1

    sources: dict[str, int] = {}
    for q in final:
        src = q.get("source", "existing")
        sources[src] = sources.get(src, 0) + 1

    print(f"\n{'='*60}")
    print(f"Generated {len(final)} questions → {output_file}")
    print(f"  Satisfied (real):       {satisfied}")
    print(f"  Not satisfied (adv):    {not_satisfied}")
    print(f"  Regression:             {len(regression)}")
    print(f"  New:                    {len(new_qs)}")
    print(f"\n  Framework Stratification Audit:")
    for fw, count in sorted(stratum_counts.items(), key=lambda x: -x[1]):
        print(f"    {fw:25s}: {count:4d}")
    print(f"\n  Sources: {json.dumps(sources, indent=2)}")

    # Write audit manifest
    audit = {
        "total": len(final),
        "target": TARGET_REAL_QUESTIONS,
        "satisfied": satisfied,
        "not_satisfied": not_satisfied,
        "regression": len(regression),
        "stratification": {
            "distribution": distribution,
            "quotas": quotas,
            "actual": stratum_counts,
        },
        "sources": sources,
    }
    audit_file = STATE_DIR / "stratification_audit.json"
    audit_file.write_text(json.dumps(audit, indent=2))
    print(f"\n  Stratification audit → {audit_file}")


if __name__ == "__main__":
    main()
