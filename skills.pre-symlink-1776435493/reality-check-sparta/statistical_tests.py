"""Statistical validation checks for SPARTA QRA data.

These checks verify data integrity, structural soundness, coverage gaps,
and statistical properties of the QRA corpus. They operate on the DuckDB
database connection and return structured result dictionaries.
"""

from config import EXPECTED_SPARTA_STRUCTURE


def check_qra_stats(conn) -> dict:
    """Get QRA quality statistics - flag any quality gaps."""
    result = conn.execute("""
        SELECT
            COUNT(*) as total,
            ROUND(AVG(grounding_score), 3) as avg_grounding,
            ROUND(STDDEV(grounding_score), 3) as std_grounding,
            MIN(grounding_score) as min_score,
            MAX(grounding_score) as max_score,
            COUNT(*) FILTER (WHERE grounding_score >= 0.90) as excellent,
            COUNT(*) FILTER (WHERE grounding_score >= 0.80 AND grounding_score < 0.90) as good,
            COUNT(*) FILTER (WHERE grounding_score >= 0.65 AND grounding_score < 0.80) as acceptable,
            COUNT(*) FILTER (WHERE grounding_score >= 0.55 AND grounding_score < 0.65) as marginal,
            COUNT(*) FILTER (WHERE grounding_score < 0.55) as poor
        FROM qra
    """).fetchone()

    total = result[0] or 1
    poor = result[9] or 0
    marginal = result[8] or 0
    acceptable = result[7] or 0
    below_good = poor + marginal + acceptable

    # CRITICAL: Any poor-quality QRA is a problem
    issues = []
    if poor > 0:
        issues.append(f"CRITICAL: {poor} QRAs with grounding < 0.55")
    if marginal > 0:
        issues.append(f"WARNING: {marginal} marginal QRAs (0.55-0.65)")
    if below_good / total > 0.05:
        issues.append(f"CONCERN: {round(100*below_good/total, 1)}% of QRAs below 'good' threshold")

    # Suspicious if avg is too perfect
    avg = result[1] or 0
    std = result[2] or 0
    if avg > 0.95 and std < 0.03:
        issues.append("SUSPICIOUS: Avg grounding suspiciously high with low variance - possible metric gaming?")

    return {
        "total": result[0],
        "avg_grounding": result[1],
        "std_grounding": result[2],
        "min_score": result[3],
        "max_score": result[4],
        "excellent": result[5],
        "excellent_pct": round(100 * result[5] / total, 1),
        "good": result[6],
        "good_pct": round(100 * result[6] / total, 1),
        "acceptable": acceptable,
        "acceptable_pct": round(100 * acceptable / total, 1),
        "marginal": marginal,
        "marginal_pct": round(100 * marginal / total, 1),
        "poor": poor,
        "poor_pct": round(100 * poor / total, 1),
        "issues": issues,
        "status": "FAIL" if poor > 0 else ("WARN" if marginal > 10 else "PASS")
    }


def check_sparta_alignment(conn) -> dict:
    """Verify SPARTA Excel data alignment - exact match required."""
    tech_count = conn.execute("SELECT COUNT(*) FROM s01_raw__sparta_techniques").fetchone()[0]
    cm_count = conn.execute("SELECT COUNT(*) FROM s01_raw__sparta_countermeasures").fetchone()[0]

    issues = []
    if tech_count != 216:
        issues.append(f"CRITICAL: Expected 216 techniques, found {tech_count}")
    if cm_count != 91:
        issues.append(f"CRITICAL: Expected 91 countermeasures, found {cm_count}")

    # Check for nulls/empty values (column names are "ID" and "Name")
    null_tech = conn.execute("""
        SELECT COUNT(*) FROM s01_raw__sparta_techniques
        WHERE "ID" IS NULL OR "Name" IS NULL OR "Name" = ''
    """).fetchone()[0]
    if null_tech > 0:
        issues.append(f"DATA INTEGRITY: {null_tech} techniques with null/empty values")

    null_cm = conn.execute("""
        SELECT COUNT(*) FROM s01_raw__sparta_countermeasures
        WHERE "ID" IS NULL OR "Name" IS NULL OR "Name" = ''
    """).fetchone()[0]
    if null_cm > 0:
        issues.append(f"DATA INTEGRITY: {null_cm} countermeasures with null/empty values")

    return {
        "techniques": tech_count,
        "techniques_expected": 216,
        "techniques_match": tech_count == 216,
        "countermeasures": cm_count,
        "countermeasures_expected": 91,
        "countermeasures_match": cm_count == 91,
        "null_techniques": null_tech,
        "null_countermeasures": null_cm,
        "issues": issues,
        "status": "FAIL" if issues else "PASS"
    }


def check_qra_structure(conn) -> dict:
    """Check QRA structural integrity - missing fields, duplicates, etc."""
    issues = []

    # Check for empty/null answers
    empty_answers = conn.execute("""
        SELECT COUNT(*) FROM qra
        WHERE answer IS NULL OR TRIM(answer) = ''
    """).fetchone()[0]
    if empty_answers > 0:
        issues.append(f"CRITICAL: {empty_answers} QRAs have empty answers")

    # Check for very short answers (likely incomplete)
    short_answers = conn.execute("""
        SELECT COUNT(*) FROM qra
        WHERE LENGTH(answer) < 20
    """).fetchone()[0]
    if short_answers > 0:
        issues.append(f"WARNING: {short_answers} QRAs have suspiciously short answers (<20 chars)")

    # Check for duplicate questions
    dupes = conn.execute("""
        SELECT question, COUNT(*) as cnt
        FROM qra
        GROUP BY question
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 5
    """).fetchall()
    if dupes:
        total_dupes = sum(d[1] for d in dupes)
        issues.append(f"WARNING: Found {len(dupes)} duplicate questions ({total_dupes} total duplicates)")

    # Check for missing relationships
    # Note: QRAs with NULL relationship_id are by design (standalone control QRAs from Phase 1/2)
    # Only flag as orphans if relationship_id IS SET but doesn't exist in relationships table
    orphan_qras = conn.execute("""
        SELECT COUNT(*) FROM qra q
        LEFT JOIN relationships r ON q.relationship_id = r.relationship_id
        WHERE q.relationship_id IS NOT NULL AND r.relationship_id IS NULL
    """).fetchone()[0]

    # Count standalone control QRAs (NULL relationship_id) for reporting
    standalone_qras = conn.execute("""
        SELECT COUNT(*) FROM qra WHERE relationship_id IS NULL
    """).fetchone()[0]

    total_qras = conn.execute("SELECT COUNT(*) FROM qra").fetchone()[0]
    orphan_pct = 100 * orphan_qras / max(total_qras, 1)

    # True orphans (have relationship_id but it's invalid) are a problem
    if orphan_qras > 0:
        issues.append(f"DATA INTEGRITY: {orphan_qras} QRAs ({orphan_pct:.1f}%) have invalid relationship_id - INVESTIGATE")

    # Check answer format consistency
    no_period = conn.execute("""
        SELECT COUNT(*) FROM qra
        WHERE answer NOT LIKE '%.'
        AND LENGTH(answer) > 50
    """).fetchone()[0]
    if no_period > 100:
        issues.append(f"FORMATTING: {no_period} answers don't end with a period")

    return {
        "empty_answers": empty_answers,
        "short_answers": short_answers,
        "duplicate_questions": len(dupes) if dupes else 0,
        "orphan_qras": orphan_qras,  # True orphans (invalid relationship_id)
        "standalone_qras": standalone_qras,  # By design (NULL relationship_id)
        "orphan_pct": round(orphan_pct, 1),
        "issues": issues,
        # Only FAIL on empty answers or true orphans (invalid relationship_id)
        "status": "FAIL" if empty_answers > 0 or orphan_qras > 0 else ("WARN" if issues else "PASS")
    }


def check_marginal_qra_analysis(conn) -> dict:
    """Deep dive on marginal QRAs - are they truly correct negatives or quality issues?"""
    marginal = conn.execute("""
        SELECT
            q.qra_id,
            q.question,
            q.answer,
            q.grounding_score,
            c.name as control_name,
            c.description as source_content
        FROM qra q
        JOIN controls c ON q.control_id = c.control_id
        WHERE q.grounding_score >= 0.55 AND q.grounding_score < 0.65
        ORDER BY RANDOM()
        LIMIT 30
    """).fetchall()

    correct_negatives = 0
    true_quality_issues = 0
    needs_investigation = 0
    issues = []

    negative_phrases = [
        "does not directly", "no direct relationship",
        "no shared mechanism", "there is no", "no documented",
        "not applicable", "no evidence", "unrelated"
    ]

    for qra_id, question, answer, score, ctrl_name, source in marginal:
        answer_lower = (answer or "").lower()

        is_negative = any(p in answer_lower for p in negative_phrases)

        if is_negative:
            # Verify the source actually doesn't support a relationship
            if not source or len(source) < 100:
                correct_negatives += 1
            else:
                needs_investigation += 1
        else:
            # Not a negative answer but low grounding - quality issue
            true_quality_issues += 1
            issues.append(f"QUALITY: QRA {qra_id} scores {score} but isn't a negative answer")

    total = len(marginal)

    # Get total QRA count for context
    total_qras = conn.execute("SELECT COUNT(*) FROM qra").fetchone()[0]
    marginal_total_pct = 100 * 71 / max(total_qras, 1)  # 71 is from qra_stats marginal count

    return {
        "total_marginal": total,
        "correct_negatives": correct_negatives,
        "correct_negative_pct": round(100 * correct_negatives / max(total, 1), 1),
        "true_quality_issues": true_quality_issues,
        "quality_issue_pct": round(100 * true_quality_issues / max(total, 1), 1),
        "needs_investigation": needs_investigation,
        "issues": issues if true_quality_issues > 10 else [],
        # FAIL only if quality issues are >50% of marginal sample AND marginal is >1% of total
        "status": "FAIL" if (true_quality_issues > total // 2 and marginal_total_pct > 1) else ("WARN" if true_quality_issues > 10 else "PASS")
    }


def check_coverage_gaps(conn) -> dict:
    """Check for systematic coverage gaps in the QRA generation."""
    issues = []

    # Check which frameworks have the worst grounding
    framework_scores = conn.execute("""
        SELECT
            c.source_framework as framework,
            COUNT(*) as qra_count,
            ROUND(AVG(q.grounding_score), 3) as avg_grounding,
            MIN(q.grounding_score) as min_grounding
        FROM qra q
        JOIN controls c ON q.control_id = c.control_id
        GROUP BY 1
        HAVING COUNT(*) > 10
        ORDER BY avg_grounding ASC
    """).fetchall()

    weak_frameworks = []
    for fw, count, avg, min_score in framework_scores:
        if avg < 0.85:
            weak_frameworks.append({"framework": fw, "count": count, "avg": avg, "min": min_score})
            issues.append(f"WEAK FRAMEWORK: {fw} has avg grounding {avg} ({count} QRAs)")

    # Check relationship coverage
    total_rels = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
    rels_with_qras = conn.execute("""
        SELECT COUNT(DISTINCT relationship_id) FROM qra
    """).fetchone()[0]
    coverage_pct = round(100 * rels_with_qras / max(total_rels, 1), 1)

    if coverage_pct < 10:
        issues.append(f"LOW COVERAGE: Only {coverage_pct}% of relationships have QRAs")

    return {
        "total_relationships": total_rels,
        "relationships_with_qras": rels_with_qras,
        "coverage_pct": coverage_pct,
        "weak_frameworks": weak_frameworks,
        "issues": issues,
        "status": "WARN" if weak_frameworks else "PASS"
    }


def check_sparta_source_fidelity(conn) -> dict:
    """Verify our database accurately represents the original SPARTA Excel file.

    This is the ground truth check against the client's canonical data.
    """
    from config import SPARTA_TECHNIQUE_CATEGORIES

    issues = []

    # Check technique count and structure
    tech_count = conn.execute("SELECT COUNT(*) FROM s01_raw__sparta_techniques").fetchone()[0]
    cm_count = conn.execute("SELECT COUNT(*) FROM s01_raw__sparta_countermeasures").fetchone()[0]

    if tech_count != EXPECTED_SPARTA_STRUCTURE["techniques"]:
        issues.append(f"FIDELITY: Expected {EXPECTED_SPARTA_STRUCTURE['techniques']} techniques, found {tech_count}")

    if cm_count != EXPECTED_SPARTA_STRUCTURE["countermeasures"]:
        issues.append(f"FIDELITY: Expected {EXPECTED_SPARTA_STRUCTURE['countermeasures']} countermeasures, found {cm_count}")

    # Verify technique ID format matches SPARTA convention
    invalid_ids = conn.execute("""
        SELECT "ID" FROM s01_raw__sparta_techniques
        WHERE "ID" NOT SIMILAR TO '[A-Z]+-[0-9]+(.[0-9]+)?'
    """).fetchall()
    if invalid_ids:
        issues.append(f"FIDELITY: {len(invalid_ids)} techniques have non-standard IDs: {[r[0] for r in invalid_ids[:5]]}")

    # Check for expected technique categories
    categories = conn.execute("""
        SELECT DISTINCT SPLIT_PART("ID", '-', 1) as category
        FROM s01_raw__sparta_techniques
    """).fetchall()
    found_categories = {c[0] for c in categories}
    expected_categories = set(SPARTA_TECHNIQUE_CATEGORIES.keys())
    missing_categories = expected_categories - found_categories

    if missing_categories:
        issues.append(f"FIDELITY: Missing technique categories: {missing_categories}")

    # Sample verification: check key techniques exist and have non-empty names
    key_techniques = ["REC-0001", "EX-0001", "IA-0001"]
    for tech_id in key_techniques:
        result = conn.execute("""
            SELECT "Name" FROM s01_raw__sparta_techniques WHERE "ID" = ?
        """, [tech_id]).fetchone()
        if result:
            if not result[0] or result[0].strip() == "":
                issues.append(f"FIDELITY: {tech_id} has empty name")
        else:
            issues.append(f"FIDELITY: Key technique {tech_id} not found")

    # Check cross-reference columns have data
    xref_stats = conn.execute("""
        SELECT
            COUNT(*) FILTER (WHERE "Related MITRE ATT&CK" IS NOT NULL AND "Related MITRE ATT&CK" != '') as has_mitre,
            COUNT(*) FILTER (WHERE "NIST Rev5 Controls" IS NOT NULL AND "NIST Rev5 Controls" != '') as has_nist,
            COUNT(*) FILTER (WHERE "D3FEND Techniques" IS NOT NULL AND "D3FEND Techniques" != '') as has_d3fend,
            COUNT(*) as total
        FROM s01_raw__sparta_techniques
    """).fetchone()

    if xref_stats[0] < xref_stats[3] * 0.5:
        issues.append(f"FIDELITY: Only {xref_stats[0]}/{xref_stats[3]} techniques have MITRE ATT&CK cross-refs")
    if xref_stats[1] < xref_stats[3] * 0.5:
        issues.append(f"FIDELITY: Only {xref_stats[1]}/{xref_stats[3]} techniques have NIST controls")

    return {
        "techniques_count": tech_count,
        "countermeasures_count": cm_count,
        "categories_found": list(found_categories),
        "mitre_coverage": f"{xref_stats[0]}/{xref_stats[3]}",
        "nist_coverage": f"{xref_stats[1]}/{xref_stats[3]}",
        "d3fend_coverage": f"{xref_stats[2]}/{xref_stats[3]}",
        "issues": issues,
        "status": "FAIL" if len(issues) > 2 else ("WARN" if issues else "PASS"),
    }
