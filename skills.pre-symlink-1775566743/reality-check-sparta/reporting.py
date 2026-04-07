"""Report generation for SPARTA Reality Check.

Handles both the adversarial console report and the client-facing
assessment report. Also includes fix suggestion printing.
"""

import os
import subprocess
import sys
from typing import List

from config import MEMORY_DIR, SPARTA_WEBSITE


def print_report(findings: dict):
    """Print adversarial report - lead with problems."""
    print()
    print("=" * 70)
    print(f"SPARTA ADVERSARIAL REALITY CHECK: {findings['run_id']}")
    print("=" * 70)
    print(f"Timestamp: {findings['timestamp']}")
    print()

    # LEAD WITH ISSUES
    all_issues = findings.get("all_issues", [])
    if all_issues:
        print("!" * 70)
        print(f"ISSUES FOUND: {len(all_issues)}")
        print("!" * 70)
        for issue in all_issues:
            print(f"  - {issue}")
        print()

    # QRA Stats
    qs = findings["qra_stats"]
    print("-" * 70)
    print(f"QRA Statistics: {qs['status']}")
    print("-" * 70)
    print(f"  Total QRAs: {qs['total']:,}")
    print(f"  Avg Grounding: {qs['avg_grounding']} (std: {qs['std_grounding']})")
    print(f"  Range: {qs['min_score']} - {qs['max_score']}")
    print(f"  Quality Distribution:")
    print(f"    Excellent (>=0.90): {qs['excellent']:,} ({qs['excellent_pct']}%)")
    print(f"    Good (0.80-0.90): {qs['good']:,} ({qs['good_pct']}%)")
    print(f"    Acceptable (0.65-0.80): {qs['acceptable']:,} ({qs['acceptable_pct']}%)")
    if qs['marginal'] > 0:
        print(f"    Marginal (0.55-0.65): {qs['marginal']:,} ({qs['marginal_pct']}%) WARNING")
    else:
        print(f"    Marginal (0.55-0.65): 0")
    if qs['poor'] > 0:
        print(f"    Poor (<0.55): {qs['poor']:,} ({qs['poor_pct']}%) FAIL")
    else:
        print(f"    Poor (<0.55): 0")
    print()

    # SPARTA Alignment
    sa = findings["sparta_alignment"]
    print("-" * 70)
    print(f"SPARTA Excel Alignment: {sa['status']}")
    print("-" * 70)
    tech_mark = "OK" if sa['techniques_match'] else "FAIL"
    cm_mark = "OK" if sa['countermeasures_match'] else "FAIL"
    print(f"  Techniques: {sa['techniques']}/{sa['techniques_expected']} [{tech_mark}]")
    print(f"  Countermeasures: {sa['countermeasures']}/{sa['countermeasures_expected']} [{cm_mark}]")
    print()

    # URL/File Alignment - CRITICAL
    ufa = findings["url_file_alignment"]
    print("-" * 70)
    print(f"URL/File Integrity: {ufa['status']}")
    print("-" * 70)
    print(f"  Checked: {ufa['total_checked']}")
    print(f"  Matches: {ufa['matches']} ({ufa['match_pct']}%)")
    mismatch_label = " DATA CORRUPTION" if ufa['mismatches'] > 0 else ""
    print(f"  MISMATCHES: {ufa['mismatches']} ({ufa['mismatch_pct']}%){mismatch_label}")
    if ufa["mismatch_examples"]:
        print(f"  Mismatch Examples (files contain WRONG content):")
        for ex in ufa["mismatch_examples"][:5]:
            print(f"    URL wanted: {ex['expected_tech']} -> File has: {ex['actual_tech']}")
    print()

    # Hallucination Check
    vg = findings["verbatim_grounding"]
    print("-" * 70)
    print(f"Hallucination Check: {vg['status']}")
    print("-" * 70)
    print(f"  Samples checked: {vg['samples_checked']}")
    hall_mark = "FAIL" if vg['hallucinations_found'] > 0 else "OK"
    print(f"  Hallucinations found: {vg['hallucinations_found']} [{hall_mark}]")
    if vg.get("note"):
        print(f"  Note: {vg['note']}")
    print()

    # QRA Structure
    struct = findings["qra_structure"]
    print("-" * 70)
    print(f"QRA Structure Integrity: {struct['status']}")
    print("-" * 70)
    empty_mark = "FAIL" if struct['empty_answers'] > 0 else "OK"
    print(f"  Empty answers: {struct['empty_answers']} [{empty_mark}]")
    if struct['short_answers'] > 0:
        print(f"  Short answers: {struct['short_answers']} WARNING")
    else:
        print(f"  Short answers: {struct['short_answers']}")
    print(f"  Duplicate questions: {struct['duplicate_questions']}")
    orphan_mark = "FAIL" if struct['orphan_qras'] > 0 else "OK"
    print(f"  Orphan QRAs: {struct['orphan_qras']} [{orphan_mark}]")
    print()

    # Marginal Analysis
    ma = findings["marginal_analysis"]
    print("-" * 70)
    print(f"Marginal QRA Analysis: {ma['status']}")
    print("-" * 70)
    print(f"  Total marginal: {ma['total_marginal']}")
    print(f"  Correct negatives: {ma['correct_negatives']} ({ma['correct_negative_pct']}%)")
    quality_mark = "FAIL" if ma['true_quality_issues'] > 0 else ""
    print(f"  TRUE QUALITY ISSUES: {ma['true_quality_issues']} ({ma['quality_issue_pct']}%) {quality_mark}")
    print(f"  Needs investigation: {ma['needs_investigation']}")
    print()

    # Coverage
    cov = findings["coverage_gaps"]
    print("-" * 70)
    print(f"Coverage Analysis: {cov['status']}")
    print("-" * 70)
    print(f"  Relationship coverage: {cov['relationships_with_qras']}/{cov['total_relationships']} ({cov['coverage_pct']}%)")
    if cov["weak_frameworks"]:
        print(f"  Weak frameworks:")
        for wf in cov["weak_frameworks"]:
            print(f"    {wf['framework']}: {wf['avg']} avg grounding ({wf['count']} QRAs)")
    print()

    # Brandon Bailey Domain Expert Review
    if "brandon_bailey_review" in findings:
        bb = findings["brandon_bailey_review"]
        print("-" * 70)
        print(f"BRANDON BAILEY REVIEW (SPARTA Creator): {bb['status']}")
        print("-" * 70)
        print(f"  COMPREHENSIVE ANALYSIS (ALL {bb.get('total_qras_analyzed', 0):,} high-quality QRAs):")
        print(f"    Space-aware: {bb.get('all_space_aware', 0):,} ({bb.get('all_space_aware_pct', 0)}%)")
        generic_warn = " WARNING" if bb.get('all_generic_pct', 0) > 30 else ""
        print(f"    Generic IT:  {bb.get('all_generic', 0):,} ({bb.get('all_generic_pct', 0)}%){generic_warn}")
        print(f"  URL Knowledge Quality:")
        print(f"    Total chunks: {bb.get('url_knowledge_total', 0):,}")
        print(f"    Avg length: {bb.get('url_knowledge_avg_length', 0):,.0f} chars")
        short_warn = " WARNING" if bb.get('url_knowledge_short', 0) > 100 else ""
        print(f"    Short (<500): {bb.get('url_knowledge_short', 0)}{short_warn}")
        error_mark = " FAIL" if bb.get('url_knowledge_errors', 0) > 10 else ""
        print(f"    Errors: {bb.get('url_knowledge_errors', 0)}{error_mark}")
        print(f"  Brandon's Verdict: {bb['brandon_verdict']}")
        if bb.get("concern_details"):
            print(f"  Sample Domain Expert Concerns ({bb['brandon_concerns']} in sample):")
            for concern in bb.get("concern_details", [])[:3]:
                print(f"    - QRA {concern['qra_id']}: {concern['brandon_says']}")
        print(f"  Grading Scale: A+ (<20% generic) | A (<30%) | B (<50%) | C (<70%) | F (>70%)")
        if bb.get('prompt_optimization_needed'):
            print()
            print("  BRANDON'S PROMPT OPTIMIZATION RECOMMENDATIONS (for /prompt-lab):")
            for rec in bb.get('prompt_recommendations', [])[:4]:
                print(f"     - {rec}")
            print()
            print("  ITERATION LOOP: Run /prompt-lab -> Re-run pipeline -> Re-check until A+")
        print()

    # Persona Stratified Validation
    if "persona_validation" in findings:
        pv = findings["persona_validation"]
        print("-" * 70)
        print(f"PERSONA STRATIFIED VALIDATION: {pv['status']}")
        print("-" * 70)
        print(f"  Total Sampled: {pv['total_sampled']} ({pv['total_sampled']//3} per persona)")
        print(f"  Overall Appropriate: {pv['total_appropriate']} ({pv['overall_appropriate_pct']}%)")
        print()
        for persona, results in pv.get("persona_results", {}).items():
            pct = results.get("appropriate_pct", 0)
            icon = "OK" if pct >= 80 else ("WARNING" if pct >= 60 else "FAIL")
            print(f"  [{icon}] {persona}:")
            print(f"      Sampled: {results['sampled']}")
            print(f"      Appropriate: {results['appropriate']} ({pct}%)")
            if results.get("issues"):
                print(f"      Issues: {results['inappropriate']} - Example: {results['issues'][0].get('brandon_says', '')[:60]}...")
        print(f"  Brandon's Verdict: {pv['brandon_verdict']}")
        print()

    # Overall
    print("=" * 70)
    status = findings['overall_status']
    if status == "FAIL":
        print(f"OVERALL STATUS: FAIL - {status}")
        print("ACTION REQUIRED: Fix issues before continuing")
    elif status == "WARN":
        print(f"OVERALL STATUS: WARNING - {status}")
        print("CAUTION: Issues detected that may affect quality")
    else:
        print(f"OVERALL STATUS: PASS - {status}")
        print("No critical issues detected (continue monitoring)")
    print("=" * 70)


def print_fix_suggestions(suggestions: List[dict]):
    """Print fix suggestions in a readable format."""
    if not suggestions:
        print("\nNo fix suggestions needed.")
        return

    print()
    print("=" * 70)
    print("FIX SUGGESTIONS (Self-Correction Guidance)")
    print("=" * 70)

    for i, s in enumerate(suggestions, 1):
        severity = s.get("severity", "UNKNOWN")

        print(f"\n[{severity}] {s['check']}: {s['status']}")
        print(f"   Description: {s['description']}")
        print(f"   Root Cause: {s['root_cause']}")
        print(f"   Owner: {s['owner']}")
        print(f"   Issues Found: {s['issues_found']}")
        print("   Suggested Fixes:")
        for fix in s.get("fixes", []):
            print(f"      {fix}")

    print()
    print("-" * 70)
    print("After applying fixes, re-run: ./run.sh check --run-id <run-id> --store")
    print("Track progress: ./run.sh convergence")
    print("-" * 70)


def generate_client_report(findings: dict) -> str:
    """Generate a client-facing /assess-style report."""
    lines = []

    # Executive Summary
    lines.append("=" * 70)
    lines.append("SPARTA QRA PIPELINE - CLIENT ASSESSMENT REPORT")
    lines.append("=" * 70)
    lines.append(f"Client: The Aerospace Corporation SPARTA Framework")
    lines.append(f"Assessment Date: {findings['timestamp'][:10]}")
    lines.append(f"Run ID: {findings['run_id']}")
    lines.append("")

    # Overall Grade
    status = findings['overall_status']
    if status == "PASS":
        grade = "A - Production Ready"
        grade_desc = "All quality checks passed. Pipeline is generating reliable QRAs."
    elif status == "WARN":
        grade = "B - Acceptable with Concerns"
        grade_desc = "Quality is acceptable but some issues need attention."
    else:
        grade = "C - Action Required"
        grade_desc = "Critical issues detected. Do not rely on outputs until resolved."

    lines.append(f"OVERALL GRADE: {grade}")
    lines.append(f"Assessment: {grade_desc}")
    lines.append("")

    # What's Working Well
    lines.append("-" * 70)
    lines.append("WHAT'S WORKING WELL")
    lines.append("-" * 70)

    working_well = []
    qs = findings.get("qra_stats", {})
    if qs.get("avg_grounding", 0) >= 0.85:
        working_well.append(f"Strong average grounding score: {qs['avg_grounding']} (target: >=0.85)")
    if qs.get("excellent", 0) > 0:
        working_well.append(f"High-quality QRAs: {qs['excellent']:,} excellent (>=0.90) + {qs.get('good', 0):,} good (0.80-0.90)")

    sa = findings.get("sparta_alignment", {})
    if sa.get("status") == "PASS":
        working_well.append(f"SPARTA Excel alignment: {sa['techniques']}/216 techniques, {sa['countermeasures']}/91 countermeasures")

    sf = findings.get("sparta_source_fidelity", {})
    if sf.get("status") == "PASS":
        working_well.append("SPARTA source fidelity: Database accurately represents client data")

    cov = findings.get("coverage_gaps", {})
    if cov.get("coverage_pct", 0) > 50:
        working_well.append(f"Relationship coverage: {cov['coverage_pct']}% of relationships have QRAs")

    struct = findings.get("qra_structure", {})
    if struct.get("empty_answers", 0) == 0 and struct.get("orphan_qras", 0) == 0:
        working_well.append("Data integrity: No empty answers or orphan QRAs")

    if not working_well:
        working_well.append("Pipeline is generating QRAs (basic functionality working)")

    for item in working_well:
        lines.append(f"  - {item}")
    lines.append("")

    # What Needs Improvement
    lines.append("-" * 70)
    lines.append("WHAT NEEDS IMPROVEMENT")
    lines.append("-" * 70)

    needs_improvement = []

    ufa = findings.get("url_file_alignment", {})
    if ufa.get("mismatches", 0) > 0:
        needs_improvement.append({
            "issue": f"URL/File Mismatch: {ufa['mismatches']} files ({ufa['mismatch_pct']}%) contain wrong content",
            "impact": "QRAs may be grounded in incorrect source material",
            "priority": "CRITICAL",
            "action": "Re-download mismatched files with validation"
        })

    if struct.get("orphan_qras", 0) > 0:
        needs_improvement.append({
            "issue": f"Orphan QRAs: {struct['orphan_qras']} QRAs have no relationship link",
            "impact": "Cannot trace QRAs back to control-technique relationships",
            "priority": "HIGH",
            "action": "Run backfill_rel_ids.py migration to link orphan QRAs"
        })

    if qs.get("poor", 0) > 0:
        needs_improvement.append({
            "issue": f"Poor Quality: {qs['poor']} QRAs with grounding < 0.55",
            "impact": "Low-confidence answers may mislead users",
            "priority": "HIGH",
            "action": "Review and regenerate low-scoring QRAs"
        })

    ma = findings.get("marginal_analysis", {})
    if ma.get("true_quality_issues", 0) > 0:
        needs_improvement.append({
            "issue": f"Marginal Quality Issues: {ma['true_quality_issues']} marginal QRAs are not legitimate negatives",
            "impact": "Some marginal scores indicate actual quality problems",
            "priority": "MEDIUM",
            "action": "Review marginal QRAs and improve prompt engineering"
        })

    if cov.get("weak_frameworks"):
        fw_names = [wf['framework'] for wf in cov['weak_frameworks'][:3]]
        needs_improvement.append({
            "issue": f"Weak Framework Coverage: {', '.join(fw_names)} have below-average grounding",
            "impact": "Some security frameworks not well represented",
            "priority": "MEDIUM",
            "action": "Improve source material for weak frameworks"
        })

    if not needs_improvement:
        lines.append("  No significant issues found.")
    else:
        for item in needs_improvement:
            lines.append(f"  [{item['priority']}] {item['issue']}")
            lines.append(f"      Impact: {item['impact']}")
            lines.append(f"      Action: {item['action']}")
            lines.append("")
    lines.append("")

    # Metrics Summary
    lines.append("-" * 70)
    lines.append("KEY METRICS")
    lines.append("-" * 70)
    lines.append(f"  Total QRAs Generated:     {qs.get('total', 0):,}")
    lines.append(f"  Average Grounding Score:  {qs.get('avg_grounding', 'N/A')}")
    lines.append(f"  Excellent Quality (>=0.90): {qs.get('excellent_pct', 0)}%")
    lines.append(f"  Good Quality (0.80-0.90):  {qs.get('good_pct', 0)}%")
    lines.append(f"  Acceptable (0.65-0.80):    {qs.get('acceptable_pct', 0)}%")
    lines.append(f"  Below Threshold (<0.65):   {qs.get('marginal_pct', 0) + qs.get('poor_pct', 0)}%")
    lines.append(f"  Relationship Coverage:     {cov.get('coverage_pct', 0)}%")
    lines.append("")

    # Recommendations
    lines.append("-" * 70)
    lines.append("RECOMMENDATIONS")
    lines.append("-" * 70)

    recommendations = []
    if status == "FAIL":
        recommendations.append("1. STOP: Do not use QRA outputs until critical issues are resolved")
        if ufa.get("mismatches", 0) > 0:
            recommendations.append("2. Run fix_mismatched_downloads.py to correct URL/file mismatches")
        if struct.get("orphan_qras", 0) > 0:
            recommendations.append("3. Run backfill_rel_ids.py to link orphan QRAs to relationships")
        recommendations.append("4. Re-run reality check after fixes: ./run.sh iterate --run-id <id>")
    elif status == "WARN":
        recommendations.append("1. Outputs are usable with caution")
        recommendations.append("2. Address improvement items above before production use")
        recommendations.append("3. Monitor convergence: ./run.sh convergence")
    else:
        recommendations.append("1. Pipeline is production-ready")
        recommendations.append("2. Continue periodic monitoring")
        recommendations.append("3. Consider increasing coverage for remaining relationships")

    for rec in recommendations:
        lines.append(f"  {rec}")
    lines.append("")

    lines.append("=" * 70)
    lines.append(f"Report generated by SPARTA Reality Check Skill")
    lines.append(f"For questions: Review 01_SPARTA_REALITY_CHECK_FIXES.md")
    lines.append("=" * 70)

    return "\n".join(lines)


def store_findings_in_memory(findings: dict, run_id: str) -> bool:
    """Store findings in /memory - focus on PROBLEMS not successes."""
    all_issues = []
    for check_name, check_data in findings.items():
        if isinstance(check_data, dict) and "issues" in check_data:
            for issue in check_data["issues"]:
                all_issues.append(f"[{check_name}] {issue}")

    if all_issues:
        problem = f"SPARTA reality check {run_id}: {len(all_issues)} ISSUES FOUND"
        solution = f"""Reality check on {findings['timestamp']}:

ISSUES REQUIRING ATTENTION:
{chr(10).join('- ' + i for i in all_issues[:20])}

Statistics:
- Total QRAs: {findings['qra_stats']['total']:,}
- Avg Grounding: {findings['qra_stats']['avg_grounding']}
- URL/File Mismatches: {findings['url_file_alignment']['mismatch_pct']}% (THIS IS A DATA CORRUPTION PROBLEM)
- Marginal Quality Issues: {findings['marginal_analysis']['quality_issue_pct']}%
- Overall Status: {findings['overall_status']}

ACTION REQUIRED: Investigate root causes before continuing pipeline."""
    else:
        problem = f"SPARTA reality check {run_id}: No critical issues found"
        solution = f"""Reality check on {findings['timestamp']} found no critical issues.
Total QRAs: {findings['qra_stats']['total']:,}, Avg Grounding: {findings['qra_stats']['avg_grounding']}
Continue monitoring - absence of detected issues != absence of issues."""

    try:
        result = subprocess.run(
            [
                "uv", "run", "python", "-m", "graph_memory.agent_cli", "learn",
                "--problem", problem,
                "--solution", solution,
                "--scope", "sparta-qra",
                "--tag", "reality-check",
                "--tag", "data-quality",
                "--tag", "adversarial",
            ],
            cwd=str(MEMORY_DIR),
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except Exception as e:
        print(f"WARNING: Could not store in memory: {e}", file=sys.stderr)
        return False


def run_status(db_path) -> int:
    """Show current pipeline status only."""
    import duckdb
    from data_loader import get_db_copy
    from statistical_tests import check_qra_stats

    db_copy = get_db_copy(db_path)

    try:
        conn = duckdb.connect(str(db_copy), read_only=True)
        stats = check_qra_stats(conn)
        conn.close()

        status_mark = "FAIL" if stats["poor"] > 0 else ("WARNING" if stats["marginal"] > 0 else "OK")
        print(f"[{status_mark}] QRAs: {stats['total']:,} | Avg: {stats['avg_grounding']} | "
              f">=0.80: {stats['excellent_pct'] + stats['good_pct']}% | "
              f"Poor: {stats['poor']} | Marginal: {stats['marginal']}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
