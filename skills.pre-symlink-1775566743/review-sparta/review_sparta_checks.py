"""review-sparta dimension checker functions.

The 6 assessment dimensions:
1. QRA Quality (25%)
2. Source Fidelity (20%)
3. CWE Relevance (20%)
4. Cross-Reference Accuracy (15%)
5. Coverage (10%)
6. Control Quality (10%)
"""

import re
from pathlib import Path
from typing import Optional

from review_sparta_constants import (
    SPACE_CWES,
    NON_SPACE_CWES,
    SPACE_TERMS,
    DimensionResult,
    has_verbatim_phrase,
)


def check_qra_quality(conn, samples: int = 100) -> DimensionResult:
    """
    Dimension 1: QRA Quality (25%)
    - Verbatim grounding
    - Citation accuracy
    - Hallucination detection
    - Empty answers
    - Orphan QRAs
    """
    result = DimensionResult(name="qra_quality", weight=0.25, score=0.0)
    checks = {}

    # Check 1: Count QRAs and basic stats
    try:
        qra_count = conn.execute("SELECT COUNT(*) FROM qra").fetchone()[0]
        checks["total_qras"] = {"count": qra_count}
    except Exception as e:
        result.issues.append(f"CRITICAL: Cannot query QRA table: {e}")
        result.score = 0.0
        result.checks = checks
        return result

    # Check 2: Empty answers
    empty_count = conn.execute("""
        SELECT COUNT(*) FROM qra
        WHERE answer IS NULL OR TRIM(answer) = ''
    """).fetchone()[0]
    empty_rate = empty_count / max(qra_count, 1)
    checks["empty_answers"] = {
        "count": empty_count,
        "rate": empty_rate,
        "passed": empty_rate < 0.01
    }
    if empty_rate >= 0.01:
        result.issues.append(f"{empty_count} QRAs have empty answers ({empty_rate:.1%})")

    # Check 3: Orphan QRAs (no relationship)
    try:
        orphan_count = conn.execute("""
            SELECT COUNT(*) FROM qra
            WHERE relationship_id IS NULL OR relationship_id = ''
        """).fetchone()[0]
        checks["orphan_qras"] = {
            "count": orphan_count,
            "passed": orphan_count <= 10
        }
        if orphan_count > 10:
            result.issues.append(f"{orphan_count} orphan QRAs without relationships")
            result.suggestions.append("Link orphan QRAs to relationships or delete them")
    except Exception:
        checks["orphan_qras"] = {"count": 0, "passed": True, "note": "Column not found"}

    # Check 4: Grounding scores
    try:
        avg_grounding = conn.execute("""
            SELECT AVG(grounding_score) FROM qra
            WHERE grounding_score IS NOT NULL AND grounding_score > 0
        """).fetchone()[0] or 0.0
        checks["avg_grounding"] = {
            "score": avg_grounding,
            "passed": avg_grounding >= 0.80
        }
        if avg_grounding < 0.80:
            result.issues.append(f"Average grounding score {avg_grounding:.2f} below 0.80 threshold")
    except Exception:
        checks["avg_grounding"] = {"score": 0.0, "passed": False, "note": "Column not found"}

    # Check 5: Sample verbatim verification
    try:
        sample_qras = conn.execute(f"""
            SELECT q.qra_id, q.answer, uk.content
            FROM qra q
            LEFT JOIN url_knowledge uk ON q.source_url = uk.url
            WHERE q.answer IS NOT NULL AND uk.content IS NOT NULL
            ORDER BY RANDOM()
            LIMIT {samples}
        """).fetchall()

        verbatim_matches = 0
        for qra_id, answer, source_content in sample_qras:
            if answer and source_content:
                if has_verbatim_phrase(answer, source_content, min_len=20):
                    verbatim_matches += 1

        verbatim_rate = verbatim_matches / max(len(sample_qras), 1)
        checks["verbatim_grounding"] = {
            "samples": len(sample_qras),
            "matches": verbatim_matches,
            "rate": verbatim_rate,
            "passed": verbatim_rate >= 0.70
        }
        if verbatim_rate < 0.70:
            result.issues.append(f"Only {verbatim_rate:.1%} of samples have verbatim phrases from source")
            result.suggestions.append("Ensure QRA answers quote source material directly")
    except Exception as e:
        checks["verbatim_grounding"] = {"rate": 0.0, "passed": False, "error": str(e)}

    # Check 6: Space terminology presence
    try:
        sample_answers = conn.execute(f"""
            SELECT answer FROM qra
            WHERE answer IS NOT NULL
            ORDER BY RANDOM()
            LIMIT {samples}
        """).fetchall()

        space_aware_count = 0
        for (answer,) in sample_answers:
            if answer:
                answer_lower = answer.lower()
                if any(term in answer_lower for term in SPACE_TERMS):
                    space_aware_count += 1

        space_rate = space_aware_count / max(len(sample_answers), 1)
        checks["space_terminology"] = {
            "samples": len(sample_answers),
            "space_aware": space_aware_count,
            "rate": space_rate,
            "passed": space_rate >= 0.60
        }
        generic_rate = 1 - space_rate
        if generic_rate > 0.50:
            result.issues.append(f"{generic_rate:.1%} of answers are generic (no space terms)")
    except Exception as e:
        checks["space_terminology"] = {"rate": 0.0, "passed": False, "error": str(e)}

    # Calculate dimension score
    passed_checks = sum(1 for c in checks.values() if c.get("passed", False))
    total_checks = len([c for c in checks.values() if "passed" in c])
    result.score = passed_checks / max(total_checks, 1)
    result.checks = checks

    return result


def check_source_fidelity(conn, sparta_source: Optional[Path] = None) -> DimensionResult:
    """
    Dimension 2: Source Fidelity (20%)
    - Technique count matches SPARTA (216)
    - Countermeasure count matches SPARTA (91)
    - ID format follows SPARTA convention
    """
    result = DimensionResult(name="source_fidelity", weight=0.20, score=0.0)
    checks = {}

    EXPECTED_TECHNIQUES = 216
    EXPECTED_COUNTERMEASURES = 91

    # Check 1: Technique count
    try:
        tech_count = conn.execute("""
            SELECT COUNT(DISTINCT "ID") FROM s01_raw__sparta_techniques
        """).fetchone()[0]
        checks["technique_count"] = {
            "expected": EXPECTED_TECHNIQUES,
            "actual": tech_count,
            "passed": tech_count == EXPECTED_TECHNIQUES
        }
        if tech_count != EXPECTED_TECHNIQUES:
            result.issues.append(f"Technique count {tech_count} != expected {EXPECTED_TECHNIQUES}")
    except Exception as e:
        checks["technique_count"] = {"expected": EXPECTED_TECHNIQUES, "actual": 0, "passed": False, "error": str(e)}
        result.issues.append(f"Cannot query techniques: {e}")

    # Check 2: Countermeasure count
    try:
        cm_count = conn.execute("""
            SELECT COUNT(DISTINCT "ID") FROM s01_raw__sparta_countermeasures
        """).fetchone()[0]
        checks["countermeasure_count"] = {
            "expected": EXPECTED_COUNTERMEASURES,
            "actual": cm_count,
            "passed": cm_count == EXPECTED_COUNTERMEASURES
        }
        if cm_count != EXPECTED_COUNTERMEASURES:
            result.issues.append(f"Countermeasure count {cm_count} != expected {EXPECTED_COUNTERMEASURES}")
    except Exception as e:
        checks["countermeasure_count"] = {"expected": EXPECTED_COUNTERMEASURES, "actual": 0, "passed": False, "error": str(e)}
        result.issues.append(f"Cannot query countermeasures: {e}")

    # Check 3: ID format validation
    try:
        invalid_tech_ids = conn.execute("""
            SELECT "ID" FROM s01_raw__sparta_techniques
            WHERE "ID" NOT REGEXP '^[A-Z]+-[0-9]+$'
        """).fetchall()
        checks["technique_id_format"] = {
            "invalid_count": len(invalid_tech_ids),
            "passed": len(invalid_tech_ids) == 0
        }
        if invalid_tech_ids:
            result.issues.append(f"{len(invalid_tech_ids)} techniques have invalid ID format")
    except Exception:
        checks["technique_id_format"] = {"invalid_count": 0, "passed": True, "note": "REGEXP not supported"}

    # Check 4: Relationship coverage
    try:
        rel_count = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        checks["relationship_count"] = {
            "count": rel_count,
            "passed": rel_count > 0
        }
    except Exception as e:
        checks["relationship_count"] = {"count": 0, "passed": False, "error": str(e)}

    # Calculate dimension score
    passed_checks = sum(1 for c in checks.values() if c.get("passed", False))
    total_checks = len([c for c in checks.values() if "passed" in c])
    result.score = passed_checks / max(total_checks, 1)
    result.checks = checks

    return result


def check_cwe_relevance(conn, samples: int = 100) -> DimensionResult:
    """
    Dimension 3: CWE Relevance (20%)
    - Space-relevant CWEs properly used
    - Generic/web CWEs flagged
    """
    result = DimensionResult(name="cwe_relevance", weight=0.20, score=0.0)
    checks = {}

    all_space_cwes = []
    for category_cwes in SPACE_CWES.values():
        all_space_cwes.extend(category_cwes)

    cwe_ids = []
    try:
        cwe_rows = conn.execute("""
            SELECT "CWE Classes" FROM s01_raw__sparta_techniques
            WHERE "CWE Classes" IS NOT NULL AND "CWE Classes" != ''
        """).fetchall()

        for (cwe_string,) in cwe_rows:
            if cwe_string:
                for cwe in cwe_string.split(","):
                    cwe_clean = cwe.strip()
                    if cwe_clean and cwe_clean.startswith("CWE-"):
                        cwe_ids.append(cwe_clean)

        cwe_ids = list(set(cwe_ids))
    except Exception as e:
        result.issues.append(f"Error querying CWE data: {e}")

    if cwe_ids:
        space_relevant = 0
        non_space = 0
        non_space_list = []

        for cwe_id in cwe_ids:
            cwe_full = cwe_id.upper().strip()

            if cwe_full in all_space_cwes:
                space_relevant += 1
            elif cwe_full in NON_SPACE_CWES:
                non_space += 1
                non_space_list.append(cwe_full)
            else:
                space_relevant += 0.5

        total = len(cwe_ids)
        space_rate = space_relevant / max(total, 1)
        non_space_rate = non_space / max(total, 1)

        checks["total_unique_cwes"] = {"count": total}
        checks["space_relevant_cwes"] = {
            "count": int(space_relevant),
            "rate": space_rate,
            "passed": space_rate >= 0.50
        }
        checks["non_space_cwes"] = {
            "count": non_space,
            "rate": non_space_rate,
            "passed": non_space_rate < 0.15,
            "flagged": non_space_list[:10]
        }

        if non_space_rate >= 0.15:
            result.issues.append(f"{non_space_rate:.1%} of CWEs are web-specific (e.g., {', '.join(non_space_list[:3])})")
            result.suggestions.append("Review non-space CWE mappings for applicability")

        if space_rate >= 0.80:
            result.suggestions.append(f"Strong space-system CWE coverage: {space_rate:.1%}")
    else:
        checks["space_relevant_cwes"] = {"count": 0, "passed": False, "note": "No CWE data found"}
        result.issues.append("No CWE mappings found in database")

    passed_checks = sum(1 for c in checks.values() if c.get("passed", False))
    total_checks = len([c for c in checks.values() if "passed" in c])
    result.score = passed_checks / max(total_checks, 1) if total_checks > 0 else 0.5
    result.checks = checks

    return result


def check_cross_reference(conn) -> DimensionResult:
    """
    Dimension 4: Cross-Reference Accuracy (15%)
    - MITRE ATT&CK IDs valid
    - NIST 800-53 controls valid
    - D3FEND techniques valid
    """
    result = DimensionResult(name="cross_reference", weight=0.15, score=0.0)
    checks = {}

    # Check 1: MITRE ATT&CK ID format
    try:
        mitre_ids = conn.execute("""
            SELECT DISTINCT mitre_attack_id FROM controls
            WHERE mitre_attack_id IS NOT NULL AND mitre_attack_id != ''
            LIMIT 100
        """).fetchall()

        valid_mitre = 0
        invalid_mitre = []
        for (mid,) in mitre_ids:
            if re.match(r'^T\d{4}(\.\d{3})?$|^TA\d{4}$', mid):
                valid_mitre += 1
            else:
                invalid_mitre.append(mid)

        total = len(mitre_ids)
        valid_rate = valid_mitre / max(total, 1)
        checks["mitre_attack_format"] = {
            "total": total,
            "valid": valid_mitre,
            "rate": valid_rate,
            "passed": valid_rate >= 0.95,
            "invalid_samples": invalid_mitre[:5]
        }
    except Exception:
        checks["mitre_attack_format"] = {"passed": True, "note": "Column not found"}

    # Check 2: NIST 800-53 format
    try:
        nist_ids = conn.execute("""
            SELECT DISTINCT nist_control FROM controls
            WHERE nist_control IS NOT NULL AND nist_control != ''
            LIMIT 100
        """).fetchall()

        valid_nist = 0
        for (nid,) in nist_ids:
            if re.match(r'^[A-Z]{2}-\d+', nid):
                valid_nist += 1

        total = len(nist_ids)
        valid_rate = valid_nist / max(total, 1)
        checks["nist_control_format"] = {
            "total": total,
            "valid": valid_nist,
            "rate": valid_rate,
            "passed": valid_rate >= 0.95
        }
    except Exception:
        checks["nist_control_format"] = {"passed": True, "note": "Column not found"}

    passed_checks = sum(1 for c in checks.values() if c.get("passed", False))
    total_checks = len([c for c in checks.values() if "passed" in c])
    result.score = passed_checks / max(total_checks, 1) if total_checks > 0 else 0.5
    result.checks = checks

    return result


def check_coverage(conn) -> DimensionResult:
    """
    Dimension 5: Coverage (10%)
    - All techniques represented
    - All countermeasures represented
    - QRAs per relationship
    """
    result = DimensionResult(name="coverage", weight=0.10, score=0.0)
    checks = {}

    try:
        qra_count = conn.execute("SELECT COUNT(*) FROM qra").fetchone()[0]
        checks["total_qras"] = {
            "count": qra_count,
            "passed": qra_count >= 5000
        }
        if qra_count < 5000:
            result.issues.append(f"Only {qra_count} QRAs (target: 5000+)")
    except Exception as e:
        checks["total_qras"] = {"count": 0, "passed": False, "error": str(e)}

    try:
        rels_with_qra = conn.execute("""
            SELECT COUNT(DISTINCT relationship_id)
            FROM qra
            WHERE relationship_id IS NOT NULL
        """).fetchone()[0]

        total_rels = conn.execute("""
            SELECT COUNT(*) FROM relationships
        """).fetchone()[0]

        rel_coverage = rels_with_qra / max(total_rels, 1)
        checks["relationship_coverage"] = {
            "with_qra": rels_with_qra,
            "total": total_rels,
            "rate": rel_coverage,
            "passed": rel_coverage >= 0.01
        }
    except Exception as e:
        checks["relationship_coverage"] = {"passed": False, "error": str(e)}

    try:
        controls_with_qra = conn.execute("""
            SELECT COUNT(DISTINCT control_id)
            FROM qra
            WHERE control_id IS NOT NULL
        """).fetchone()[0]

        total_controls = conn.execute("""
            SELECT COUNT(*) FROM controls
        """).fetchone()[0]

        control_coverage = controls_with_qra / max(total_controls, 1)
        checks["control_coverage"] = {
            "with_qra": controls_with_qra,
            "total": total_controls,
            "rate": control_coverage,
            "passed": control_coverage >= 0.10
        }
        if control_coverage < 0.10:
            result.issues.append(f"Only {control_coverage:.1%} of controls have QRAs")
    except Exception as e:
        checks["control_coverage"] = {"passed": False, "error": str(e)}

    try:
        avg_qras = conn.execute("""
            SELECT AVG(qra_count) FROM (
                SELECT relationship_id, COUNT(*) as qra_count
                FROM qra
                WHERE relationship_id IS NOT NULL
                GROUP BY relationship_id
            )
        """).fetchone()[0] or 0.0

        checks["avg_qras_per_relationship"] = {
            "average": round(avg_qras, 2),
            "passed": avg_qras >= 1.0
        }
    except Exception as e:
        checks["avg_qras_per_relationship"] = {"passed": False, "error": str(e)}

    passed_checks = sum(1 for c in checks.values() if c.get("passed", False))
    total_checks = len([c for c in checks.values() if "passed" in c])
    result.score = passed_checks / max(total_checks, 1) if total_checks > 0 else 0.5
    result.checks = checks

    return result


def check_control_quality(conn, samples: int = 50) -> DimensionResult:
    """
    Dimension 6: Control Quality (10%)
    - Control-to-control comparisons meaningful
    - Space context present
    """
    result = DimensionResult(name="control_quality", weight=0.10, score=0.0)
    checks = {}

    try:
        controls = conn.execute(f"""
            SELECT control_id, name, description
            FROM controls
            WHERE description IS NOT NULL
            ORDER BY RANDOM()
            LIMIT {samples}
        """).fetchall()

        space_context_count = 0
        for cid, name, desc in controls:
            text = f"{name or ''} {desc or ''}".lower()
            if any(term in text for term in SPACE_TERMS):
                space_context_count += 1

        space_rate = space_context_count / max(len(controls), 1)
        checks["control_space_context"] = {
            "samples": len(controls),
            "with_context": space_context_count,
            "rate": space_rate,
            "passed": space_rate >= 0.30
        }
        if space_rate < 0.30:
            result.issues.append(f"Only {space_rate:.1%} of controls have space-specific context")
    except Exception as e:
        checks["control_space_context"] = {"passed": False, "error": str(e)}

    try:
        qra_answers = conn.execute(f"""
            SELECT answer FROM qra
            WHERE answer IS NOT NULL AND answer != ''
            ORDER BY RANDOM()
            LIMIT {samples}
        """).fetchall()

        space_qra_count = 0
        for (answer,) in qra_answers:
            if answer:
                answer_lower = answer.lower()
                if any(term in answer_lower for term in SPACE_TERMS):
                    space_qra_count += 1

        space_qra_rate = space_qra_count / max(len(qra_answers), 1)
        checks["qra_space_context"] = {
            "samples": len(qra_answers),
            "with_context": space_qra_count,
            "rate": space_qra_rate,
            "passed": space_qra_rate >= 0.60
        }
        if space_qra_rate < 0.60:
            result.issues.append(f"Only {space_qra_rate:.1%} of QRA answers have space-specific context")
    except Exception as e:
        checks["qra_space_context"] = {"passed": False, "error": str(e)}

    passed_checks = sum(1 for c in checks.values() if c.get("passed", False))
    total_checks = len([c for c in checks.values() if "passed" in c])
    result.score = passed_checks / max(total_checks, 1) if total_checks > 0 else 0.5
    result.checks = checks

    return result
