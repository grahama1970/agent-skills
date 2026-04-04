"""Brandon Bailey persona-based domain expert review.

Implements the Brandon Bailey (SPARTA Creator) and Dr. James Pavur
persona-based semantic validation of QRA content. Includes both the
comprehensive space-awareness review and per-persona stratified validation.
"""

from config import (
    SPACE_TERMINOLOGY,
    SUSPICIOUS_GENERIC_PATTERNS,
    EXPECTED_MITRE_ALIGNMENT,
    SPARTA_TECHNIQUE_CATEGORIES,
    TACTIC_KEYWORDS,
    LAYPERSON_INDICATORS,
    PROJECT_MANAGER_INDICATORS,
    EXPERT_INDICATORS,
    TECHNICAL_JARGON,
)
from annealing import get_annealing_thresholds, should_continue_generation


def check_brandon_bailey_review(conn, n_samples: int = 20) -> dict:
    """
    BRANDON BAILEY PERSONA: Domain Expert Semantic Validation

    Brandon Bailey created SPARTA and knows exactly what a proper space
    cybersecurity QRA should look like. This check applies his expertise.

    ANNEALING: Thresholds are DYNAMIC based on corpus size.
    """
    issues = []

    # Get total QRA count for annealing schedule
    total_qra_count = conn.execute("SELECT COUNT(*) FROM qra").fetchone()[0]
    annealing = get_annealing_thresholds(total_qra_count)

    # PHASE 1: Analyze ALL high-grounding QRAs for space-awareness
    all_qras = conn.execute("""
        SELECT
            q.qra_id,
            q.question,
            q.answer,
            q.grounding_score,
            t."ID" as technique_id,
            t."Name" as technique_name,
            t."Related MITRE ATT&CK" as mitre_mapping
        FROM qra q
        JOIN relationships r ON q.relationship_id = r.relationship_id
        JOIN s01_raw__sparta_techniques t ON r.technique_id = t."ID"
        WHERE q.grounding_score >= 0.80
    """).fetchall()

    # For detailed concern tracking, sample a subset
    samples = conn.execute(f"""
        SELECT
            q.qra_id,
            q.question,
            q.answer,
            q.grounding_score,
            t."ID" as technique_id,
            t."Name" as technique_name,
            t."Related MITRE ATT&CK" as mitre_mapping
        FROM qra q
        JOIN relationships r ON q.relationship_id = r.relationship_id
        JOIN s01_raw__sparta_techniques t ON r.technique_id = t."ID"
        WHERE q.grounding_score >= 0.85
        ORDER BY RANDOM()
        LIMIT {n_samples}
    """).fetchall()

    space_aware = 0
    generic_it = 0
    good_mitre_mapping = 0
    questionable_mitre = 0
    brandon_concerns = []

    for qra_id, question, answer, score, tech_id, tech_name, mitre in samples:
        answer_lower = (answer or "").lower()
        tech_category = tech_id.split("-")[0] if tech_id else ""

        # CHECK 1: Does answer contain space-specific terminology?
        space_terms_found = sum(1 for term in SPACE_TERMINOLOGY if term.lower() in answer_lower)

        if space_terms_found >= 2:
            space_aware += 1
        else:
            generic_it += 1
            if space_terms_found == 0:
                brandon_concerns.append({
                    "qra_id": qra_id,
                    "concern": "GENERIC_IT",
                    "detail": f"No space terminology in answer for {tech_name}",
                    "brandon_says": "This reads like a generic IT security answer. Where's the space context?"
                })

        # CHECK 2: Suspicious generic patterns Brandon would catch
        for pattern in SUSPICIOUS_GENERIC_PATTERNS:
            if pattern in answer_lower:
                brandon_concerns.append({
                    "qra_id": qra_id,
                    "concern": "SUSPICIOUS_PATTERN",
                    "detail": f"Found '{pattern}' in answer",
                    "brandon_says": f"'{pattern}'? This isn't a 'typical' anything - it's a spacecraft!"
                })
                break

        # CHECK 3: MITRE mapping sanity (if available)
        if mitre and tech_category:
            expected_tactics = EXPECTED_MITRE_ALIGNMENT.get(tech_category, [])
            if expected_tactics:
                mapping_makes_sense = any(
                    tactic in (mitre or "") for tactic in expected_tactics
                ) or "T1" in (mitre or "")
                if mapping_makes_sense:
                    good_mitre_mapping += 1
                else:
                    questionable_mitre += 1

        # CHECK 4: For high-impact techniques, verify space realism
        if tech_category == "IMP" and "collision" not in answer_lower and "debris" not in answer_lower:
            if "denial" in answer_lower or "disrupt" in answer_lower:
                pass  # Acceptable
            else:
                brandon_concerns.append({
                    "qra_id": qra_id,
                    "concern": "MISSING_SPACE_IMPACT",
                    "detail": f"Impact technique {tech_name} doesn't discuss space-specific consequences",
                    "brandon_says": "Impact in space isn't just data loss - what about debris? Mission degradation?"
                })

        # CHECK 5: CRITICAL - Technique-Tactic Anchoring (NON-NEGOTIABLE)
        question_lower = (question or "").lower()
        tech_name_lower = (tech_name or "").lower()
        tech_id_lower = (tech_id or "").lower()

        tech_referenced = (
            tech_name_lower in question_lower or
            tech_name_lower in answer_lower or
            tech_id_lower in question_lower or
            tech_id_lower in answer_lower
        )

        if not tech_referenced and tech_name:
            brandon_concerns.append({
                "qra_id": qra_id,
                "concern": "NOT_TECHNIQUE_ANCHORED",
                "detail": f"QRA doesn't explicitly reference technique '{tech_name}' ({tech_id})",
                "brandon_says": f"This QRA is supposed to be about {tech_name} but doesn't mention it! Where's the technique-tactic anchoring?"
            })

        # CHECK 6: CRITICAL - Parent Tactic Context Anchoring (NON-NEGOTIABLE)
        tactic_name_from_id = SPARTA_TECHNIQUE_CATEGORIES.get(tech_category, "")
        if tactic_name_from_id:
            tactic_referenced = (
                tactic_name_from_id.lower() in question_lower or
                tactic_name_from_id.lower() in answer_lower or
                tech_category.lower() in question_lower or
                tech_category.lower() in answer_lower
            )

            related_terms = TACTIC_KEYWORDS.get(tech_category, [])
            tactic_context_present = tactic_referenced or any(
                term in question_lower or term in answer_lower
                for term in related_terms
            )

            if not tactic_context_present:
                brandon_concerns.append({
                    "qra_id": qra_id,
                    "concern": "NOT_TACTIC_ANCHORED",
                    "detail": f"QRA doesn't reflect parent tactic '{tactic_name_from_id}' ({tech_category}) context",
                    "brandon_says": f"This is a {tactic_name_from_id} technique but the QRA doesn't discuss {tactic_name_from_id.lower()} concepts. It needs tactic anchoring!"
                })

    # Calculate sample total
    sample_total = len(samples)

    # Count anchoring issues (NON-NEGOTIABLE criteria)
    not_technique_anchored = sum(1 for c in brandon_concerns if c.get("concern") == "NOT_TECHNIQUE_ANCHORED")
    not_tactic_anchored = sum(1 for c in brandon_concerns if c.get("concern") == "NOT_TACTIC_ANCHORED")
    total_anchoring_issues = not_technique_anchored + not_tactic_anchored
    anchoring_issue_pct = round(100 * total_anchoring_issues / max(sample_total, 1), 1) if sample_total > 0 else 0

    # Calculate stats from sampled detailed review
    space_aware_pct = round(100 * space_aware / max(sample_total, 1), 1)
    generic_pct = round(100 * generic_it / max(sample_total, 1), 1)

    # PHASE 2: Comprehensive ALL QRAs analysis for space terminology
    all_space_aware = 0
    all_generic = 0
    for qra_id, question, answer, score, tech_id, tech_name, mitre in all_qras:
        answer_lower = (answer or "").lower()
        terms_found = sum(1 for term in SPACE_TERMINOLOGY if term.lower() in answer_lower)
        if terms_found >= 2:
            all_space_aware += 1
        else:
            all_generic += 1

    total_analyzed = len(all_qras)
    all_space_pct = round(100 * all_space_aware / max(total_analyzed, 1), 1)
    all_generic_pct = round(100 * all_generic / max(total_analyzed, 1), 1)

    # PHASE 3: Check url_knowledge quality
    url_knowledge_stats = conn.execute("""
        SELECT
            COUNT(*) as total_chunks,
            AVG(LENGTH(text)) as avg_length,
            COUNT(*) FILTER (WHERE LENGTH(text) < 500) as short_chunks,
            COUNT(*) FILTER (WHERE text LIKE '%404%' OR text LIKE '%not found%' OR text LIKE '%error%') as error_chunks
        FROM url_knowledge
    """).fetchone()

    uk_total, uk_avg_len, uk_short, uk_errors = url_knowledge_stats or (0, 0, 0, 0)
    uk_quality_issues = []

    if uk_short and uk_total and (100 * uk_short / uk_total) > 20:
        uk_quality_issues.append(f"{uk_short} url_knowledge chunks are too short (<500 chars)")

    if uk_errors and uk_errors > 10:
        uk_quality_issues.append(f"{uk_errors} url_knowledge chunks contain error messages")

    # Brandon's verdict - using DYNAMIC ANNEALING thresholds
    anchoring_threshold = annealing["anchoring_fail_pct"]
    generic_threshold = annealing["generic_fail_pct"]
    phase_name = annealing["phase_name"]

    if all_generic_pct > generic_threshold:
        issues.append(f"BRANDON CONCERN ({phase_name}): {all_generic_pct}% of ALL {total_analyzed} QRAs lack space-specific terminology (threshold: {generic_threshold}%)")
        issues.append(f"Brandon says: '{annealing['brandon_says']}'")

    if anchoring_issue_pct > anchoring_threshold:
        issues.append(f"ANCHORING FAILURE ({phase_name}): {anchoring_issue_pct}% of sampled QRAs lack technique-tactic anchoring (threshold: {anchoring_threshold}%)")
        issues.append(f"  - NOT_TECHNIQUE_ANCHORED: {not_technique_anchored} QRAs don't mention their source technique")
        issues.append(f"  - NOT_TACTIC_ANCHORED: {not_tactic_anchored} QRAs don't reflect parent tactic context")
        issues.append(f"Brandon says: 'At {total_qra_count:,} QRAs ({phase_name} phase), I expect better anchoring. Fix this!'")

    if len(brandon_concerns) > 5:
        issues.append(f"DOMAIN EXPERT: {len(brandon_concerns)} QRAs flagged for semantic issues (sampled)")
        for concern in brandon_concerns[:3]:
            issues.append(f"  - QRA {concern['qra_id']}: {concern['brandon_says']}")

    if uk_quality_issues:
        issues.append("URL KNOWLEDGE QUALITY:")
        for qi in uk_quality_issues:
            issues.append(f"  - {qi}")

    return {
        # Comprehensive analysis (ALL high-quality QRAs)
        "total_qras_analyzed": total_analyzed,
        "all_space_aware": all_space_aware,
        "all_space_aware_pct": all_space_pct,
        "all_generic": all_generic,
        "all_generic_pct": all_generic_pct,
        # Detailed sample analysis
        "samples_reviewed": sample_total,
        "space_aware_qras": space_aware,
        "space_aware_pct": space_aware_pct,
        "generic_it_qras": generic_it,
        "generic_pct": generic_pct,
        "good_mitre_mappings": good_mitre_mapping,
        "questionable_mitre": questionable_mitre,
        "brandon_concerns": len(brandon_concerns),
        "concern_details": brandon_concerns[:5],
        # URL Knowledge quality
        "url_knowledge_total": uk_total,
        "url_knowledge_avg_length": round(uk_avg_len or 0, 0),
        "url_knowledge_short": uk_short,
        "url_knowledge_errors": uk_errors,
        "issues": issues,
        # ANNEALING: Dynamic thresholds based on corpus size
        "annealing": {
            "phase": phase_name,
            "qra_count": total_qra_count,
            "phase_range": annealing["phase_range"],
            "anchoring_threshold": anchoring_threshold,
            "generic_threshold": generic_threshold,
            "grounding_min": annealing["grounding_min"],
            "brandon_says": annealing["brandon_says"],
        },
        # Status uses DYNAMIC thresholds from annealing schedule
        "status": "FAIL" if (all_generic_pct > generic_threshold or anchoring_issue_pct > anchoring_threshold) else ("WARN" if (all_generic_pct > generic_threshold * 0.7 or anchoring_issue_pct > anchoring_threshold * 0.5) else "PASS"),
        "brandon_verdict": (
            f"F FAIL - ANCHORING ({phase_name})" if anchoring_issue_pct > anchoring_threshold else
            f"F FAIL - GENERIC ({phase_name})" if all_generic_pct > generic_threshold else
            f"A+ EXCELLENT ({phase_name})" if all_generic_pct < 20 and anchoring_issue_pct < 5 else
            f"A GOOD ({phase_name})" if all_generic_pct < 30 and anchoring_issue_pct < 10 else
            f"B ACCEPTABLE ({phase_name})" if all_generic_pct < 50 and anchoring_issue_pct < 15 else
            f"C NEEDS WORK ({phase_name})" if all_generic_pct < generic_threshold else
            f"PASS ({phase_name})"
        ),
        # Convergence decision
        "continue_decision": should_continue_generation(total_qra_count, {
            "anchoring_issue_pct": anchoring_issue_pct,
            "all_generic_pct": all_generic_pct,
        }),
        # Anchoring metrics
        "anchoring_issues_total": total_anchoring_issues,
        "anchoring_issue_pct": anchoring_issue_pct,
        "not_technique_anchored": not_technique_anchored,
        "not_tactic_anchored": not_tactic_anchored,
        # Prompt optimization recommendations
        "prompt_optimization_needed": all_generic_pct > (generic_threshold * 0.6) or anchoring_issue_pct > (anchoring_threshold * 0.5),
        "prompt_recommendations": (
            ([
                "CRITICAL: Require explicit technique reference (name AND ID) in every QRA",
                "CRITICAL: Ground all QRAs in parent tactic context and terminology",
                "CRITICAL: Frame control comparisons AS THEY APPLY TO the specific technique",
                "CRITICAL: Every CWE/control relationship must reference the worksheet's technique",
            ] if anchoring_issue_pct > 10 else []) +
            ([
                "Add explicit requirement for space-specific terminology",
                "Include space segment context (ground/link/space) in every answer",
                "Reference satellite/spacecraft architecture",
                "Mention RF/SATCOM for communication techniques",
                "Include orbital mechanics constraints where applicable",
                "Reference specific space systems (GPS III, Starlink, ISS)",
            ] if all_generic_pct > 30 else [])
        ),
    }


def check_persona_stratified_validation(conn, samples_per_persona: int = 100) -> dict:
    """
    BRANDON BAILEY PERSONA: Stratified Validation by Questioner Persona

    Validates that QRAs match the expected complexity for each persona:
    - lay_person: Simple questions, accessible explanations, minimal jargon
    - project_manager: Medium complexity, risk/business focus
    - cybersecurity_expert: Complex questions, deep technical detail
    """
    issues = []
    persona_results = {}

    for persona in ["lay_person", "project_manager", "cybersecurity_expert"]:
        samples = conn.execute(f"""
            SELECT
                q.qra_id,
                q.question,
                q.answer,
                q.question_type,
                q.grounding_score,
                q.control_id
            FROM qra q
            WHERE q.questioner_persona = '{persona}'
            ORDER BY RANDOM()
            LIMIT {samples_per_persona}
        """).fetchall()

        if not samples:
            persona_results[persona] = {
                "sampled": 0,
                "appropriate": 0,
                "inappropriate": 0,
                "issues": [f"No QRAs found for persona: {persona}"]
            }
            continue

        appropriate = 0
        inappropriate = 0
        persona_issues = []

        for qra_id, question, answer, q_type, score, control_id in samples:
            question_lower = (question or "").lower()
            answer_lower = (answer or "").lower()

            # Count technical jargon in answer
            jargon_count = sum(1 for term in TECHNICAL_JARGON if term.lower() in answer_lower)

            if persona == "lay_person":
                indicators = LAYPERSON_INDICATORS
                has_bad = any(bad in answer_lower for bad in indicators["bad"])
                too_technical = jargon_count > indicators["answer_max_jargon"]

                if has_bad or too_technical:
                    inappropriate += 1
                    persona_issues.append({
                        "qra_id": qra_id,
                        "issue": "TOO_COMPLEX_FOR_LAYPERSON",
                        "jargon_count": jargon_count,
                        "brandon_says": "A lay person wouldn't understand this. Simplify!"
                    })
                else:
                    appropriate += 1

            elif persona == "project_manager":
                indicators = PROJECT_MANAGER_INDICATORS
                has_bad = any(bad in answer_lower for bad in indicators["bad"])
                has_good = any(good in answer_lower for good in indicators["good"])
                too_technical = jargon_count > indicators["answer_max_jargon"]

                if has_bad or too_technical:
                    inappropriate += 1
                    persona_issues.append({
                        "qra_id": qra_id,
                        "issue": "TOO_TECHNICAL_FOR_PM",
                        "jargon_count": jargon_count,
                        "brandon_says": "A PM needs risk/business context, not exploit details!"
                    })
                elif not has_good:
                    inappropriate += 1
                    persona_issues.append({
                        "qra_id": qra_id,
                        "issue": "MISSING_BUSINESS_CONTEXT",
                        "brandon_says": "Where's the risk/impact framing for the PM?"
                    })
                else:
                    appropriate += 1

            elif persona == "cybersecurity_expert":
                indicators = EXPERT_INDICATORS
                too_simple = jargon_count < indicators.get("answer_min_jargon", 0)

                if too_simple and score >= 0.8:
                    inappropriate += 1
                    persona_issues.append({
                        "qra_id": qra_id,
                        "issue": "TOO_SIMPLE_FOR_EXPERT",
                        "jargon_count": jargon_count,
                        "brandon_says": "An expert expects technical depth. This is too basic!"
                    })
                else:
                    appropriate += 1

        appropriate_pct = round(100 * appropriate / max(len(samples), 1), 1)
        persona_results[persona] = {
            "sampled": len(samples),
            "appropriate": appropriate,
            "inappropriate": inappropriate,
            "appropriate_pct": appropriate_pct,
            "issues": persona_issues[:5],
        }

        if appropriate_pct < 70:
            issues.append(f"PERSONA MISMATCH: {persona} has only {appropriate_pct}% appropriate QRAs")

    # Overall assessment
    total_sampled = sum(p["sampled"] for p in persona_results.values())
    total_appropriate = sum(p["appropriate"] for p in persona_results.values())
    overall_pct = round(100 * total_appropriate / max(total_sampled, 1), 1)

    return {
        "total_sampled": total_sampled,
        "total_appropriate": total_appropriate,
        "overall_appropriate_pct": overall_pct,
        "persona_results": persona_results,
        "issues": issues,
        "status": "FAIL" if overall_pct < 60 else ("WARN" if overall_pct < 80 else "PASS"),
        "brandon_verdict": (
            "A+ EXCELLENT persona targeting" if overall_pct >= 90 else
            "A GOOD persona targeting" if overall_pct >= 80 else
            "B ACCEPTABLE - some persona mismatches" if overall_pct >= 70 else
            "C NEEDS WORK - many persona mismatches" if overall_pct >= 60 else
            "F FAIL - QRAs don't match personas"
        ),
    }
