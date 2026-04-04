#!/usr/bin/env python3
"""CLI entry points for SPARTA QRA Reality Check.

Provides the main() function and orchestration logic for running checks,
iteration loops, convergence analysis, and client report generation.
"""

import typer
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

from config import SPARTA_WEBSITE
from data_loader import get_db_copy
from statistical_tests import (
    check_qra_stats,
    check_sparta_alignment,
    check_qra_structure,
    check_marginal_qra_analysis,
    check_coverage_gaps,
    check_sparta_source_fidelity,
)
from adversarial import (
    check_url_file_alignment,
    check_url_knowledge_contamination,
    check_qra_verbatim_grounding,
    run_fresh_verification,
)
from loguru import logger
from brandon_review import (
    check_brandon_bailey_review,
    check_persona_stratified_validation,
)
from convergence import (
    track_convergence,
    analyze_convergence,
    suggest_fixes,
)
from reporting import (
    print_report,
    print_fix_suggestions,
    generate_client_report,
    store_findings_in_memory,
    run_status,
)

# Import classifier validation (optional, graceful fallback)
try:
    from classifier_validation import (
        check_qra_space_specificity,
        classifier_status,
        CLASSIFIER_AVAILABLE,
    )
except ImportError:
    CLASSIFIER_AVAILABLE = False
    check_qra_space_specificity = None
    classifier_status = None


def _determine_overall_status(findings: dict) -> str:
    """Determine overall status from individual check results."""
    statuses = [v.get("status", "PASS") for v in findings.values() if isinstance(v, dict)]
    fail_count = sum(1 for s in statuses if s == "FAIL")
    warn_count = sum(1 for s in statuses if s == "WARN")

    if fail_count > 0:
        return "FAIL"
    elif warn_count >= 3:
        return "FAIL"
    elif warn_count > 0:
        return "WARN"
    else:
        return "PASS"


def _collect_all_issues(findings: dict) -> list:
    """Collect all issues from all checks."""
    all_issues = []
    for check_name, check_data in findings.items():
        if isinstance(check_data, dict) and "issues" in check_data:
            all_issues.extend(check_data["issues"])
    return all_issues


def suggest_fixes_for_findings(findings: dict) -> list:
    """Wrapper for suggest_fixes with proper naming."""
    return suggest_fixes(findings)


def run_check(db_path: Path, run_id: str, samples: int, full: bool,
              store: bool, json_output: bool, suggest_fixes_flag: bool = True) -> int:
    """Run the adversarial reality check with fresh verification techniques."""
    import duckdb

    monitor = TaskClient("reality-check-sparta", total=1) if TaskClient else None

    print("=" * 60, file=sys.stderr)
    print("SPARTA ADVERSARIAL REALITY CHECK", file=sys.stderr)
    print("Looking for flaws. A PASS is hard to earn.", file=sys.stderr)
    print("Using multiple verification techniques for robustness.", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # Copy DB to avoid locks
    db_copy = get_db_copy(db_path)

    try:
        conn = duckdb.connect(str(db_copy), read_only=True)
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}", file=sys.stderr)
        return 1

    # Standard checks
    findings = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "client": "The Aerospace Corporation SPARTA Framework",
        "client_url": SPARTA_WEBSITE,
        "qra_stats": check_qra_stats(conn),
        "sparta_source_fidelity": check_sparta_source_fidelity(conn),
        "sparta_alignment": check_sparta_alignment(conn),
        "url_file_alignment": check_url_file_alignment(conn, full=full),
        "contamination_check": check_url_knowledge_contamination(conn, n_samples=samples),
        "verbatim_grounding": check_qra_verbatim_grounding(conn, n_samples=samples),
        "qra_structure": check_qra_structure(conn),
        "marginal_analysis": check_marginal_qra_analysis(conn),
        "coverage_gaps": check_coverage_gaps(conn),
        "brandon_bailey_review": check_brandon_bailey_review(conn, n_samples=samples),
        "persona_validation": check_persona_stratified_validation(conn, samples_per_persona=100),
    }

    # ML-BASED CLASSIFIER CHECK (if available)
    if CLASSIFIER_AVAILABLE and check_qra_space_specificity:
        print("Running ML classifier validation...", file=sys.stderr)
        try:
            findings["classifier_validation"] = check_qra_space_specificity(
                conn, sample_size=samples, threshold=0.7
            )
        except Exception as e:
            findings["classifier_validation"] = {
                "status": "ERROR",
                "issues": [f"Classifier validation failed: {e}"],
            }
    else:
        findings["classifier_validation"] = {
            "status": "SKIP",
            "issues": [],
            "reason": "ML classifier not available",
        }

    # FRESH VERIFICATION - use alternative techniques
    print("Running fresh verification...", file=sys.stderr)
    try:
        findings["fresh_verification"] = run_fresh_verification(conn, n_samples=min(samples, 5))
    except Exception as e:
        findings["fresh_verification"] = {
            "status": "ERROR",
            "issues": [f"Fresh verification failed: {e}"],
        }

    conn.close()

    # Clean up copy
    if db_copy != db_path and db_copy.exists():
        try:
            db_copy.unlink()
        except Exception as e:
            logger.debug("db_copy failed: {}", e)

    # Determine overall status
    findings["overall_status"] = _determine_overall_status(findings)

    # Collect all issues
    all_issues = _collect_all_issues(findings)
    findings["total_issues_found"] = len(all_issues)
    findings["all_issues"] = all_issues

    # Track convergence
    track_convergence(findings, run_id)

    # Output
    if json_output:
        print(json.dumps(findings, indent=2))
    else:
        print_report(findings)

        # Show fix suggestions if requested or if there are failures
        if suggest_fixes_flag and findings["overall_status"] != "PASS":
            suggestions = suggest_fixes_for_findings(findings)
            print_fix_suggestions(suggestions)

            # Show convergence trend
            convergence = analyze_convergence()
            print(f"\nConvergence Status: {convergence['status']} - {convergence['message']}")

    # Store in memory if requested
    if store:
        if store_findings_in_memory(findings, run_id):
            print("\n[Findings stored in /memory]")
        else:
            print("\n[WARNING: Could not store in /memory]")

    if monitor:
        monitor.finish()

    # Return failure if any issues
    return 0 if findings["overall_status"] == "PASS" else 1


def run_iteration_loop(db_path: Path, run_id: str, max_iterations: int = 10,
                       store: bool = True) -> int:
    """Run reality check in a loop until clean or max iterations."""
    import duckdb

    print("=" * 70)
    print("SPARTA REALITY CHECK - ITERATION LOOP")
    print(f"Will run up to {max_iterations} iterations until all checks pass")
    print("=" * 70)
    print()

    monitor = TaskClient("reality-check-sparta-loop", total=max_iterations) if TaskClient else None

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*70}")
        print(f"ITERATION {iteration}/{max_iterations}")
        print(f"{'='*70}\n")

        db_copy = get_db_copy(db_path)

        try:
            conn = duckdb.connect(str(db_copy), read_only=True)
        except Exception as e:
            print(f"ERROR: Could not connect to database: {e}")
            return 1

        findings = {
            "run_id": f"{run_id}-iter{iteration}",
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "qra_stats": check_qra_stats(conn),
            "sparta_source_fidelity": check_sparta_source_fidelity(conn),
            "sparta_alignment": check_sparta_alignment(conn),
            "url_file_alignment": check_url_file_alignment(conn, full=False),
            "contamination_check": check_url_knowledge_contamination(conn, n_samples=20),
            "verbatim_grounding": check_qra_verbatim_grounding(conn, n_samples=20),
            "qra_structure": check_qra_structure(conn),
            "marginal_analysis": check_marginal_qra_analysis(conn),
            "coverage_gaps": check_coverage_gaps(conn),
            "brandon_bailey_review": check_brandon_bailey_review(conn, n_samples=20),
            "persona_validation": check_persona_stratified_validation(conn, samples_per_persona=50),
        }

        conn.close()

        if db_copy != db_path and db_copy.exists():
            try:
                db_copy.unlink()
            except Exception as e:
                logger.debug("db_copy failed: {}", e)

        findings["overall_status"] = _determine_overall_status(findings)

        all_issues = _collect_all_issues(findings)
        findings["total_issues_found"] = len(all_issues)
        findings["all_issues"] = all_issues

        track_convergence(findings, f"{run_id}-iter{iteration}")

        print(f"Issues found: {len(all_issues)}")
        print(f"Overall status: {findings['overall_status']}")

        if findings["overall_status"] == "PASS":
            print("\n" + "="*70)
            print("ALL CHECKS PASSED!")
            print("="*70)

            report = generate_client_report(findings)
            print("\n" + report)

            if store:
                store_findings_in_memory(findings, f"{run_id}-final")

            if monitor:
                monitor.finish()
            return 0

        if all_issues:
            print("\nIssues requiring attention:")
            for issue in all_issues[:10]:
                print(f"  - {issue}")
            if len(all_issues) > 10:
                print(f"  ... and {len(all_issues) - 10} more")

        suggestions = suggest_fixes(findings)
        if suggestions:
            print("\nSuggested fixes for next iteration:")
            for s in suggestions[:3]:
                print(f"  [{s['severity']}] {s['check']}: {s['fixes'][0] if s['fixes'] else 'See documentation'}")

        convergence = analyze_convergence()
        print(f"\nConvergence: {convergence['status']} - {convergence['message']}")

        if convergence["status"] == "REGRESSING":
            print("\nWARNING: Issues are INCREASING. Check if fixes are being applied correctly.")

        if store and iteration % 3 == 0:
            store_findings_in_memory(findings, f"{run_id}-iter{iteration}")

        if monitor:
            monitor.update(item=f"iter-{iteration}")

        if iteration < max_iterations and findings["overall_status"] != "PASS":
            import time
            print(f"\nWaiting 2 seconds before next iteration...")
            time.sleep(2)

    # Max iterations reached
    print("\n" + "="*70)
    print(f"MAX ITERATIONS ({max_iterations}) REACHED")
    print("="*70)
    print("Not all issues resolved. Manual intervention may be required.")

    report = generate_client_report(findings)
    print("\n" + report)

    if monitor:
        monitor.finish()
    return 1


def run_convergence_analysis():
    """Show convergence analysis."""
    analysis = analyze_convergence()

    print()
    print("=" * 60)
    print("CONVERGENCE ANALYSIS")
    print("=" * 60)
    print(f"Status: {analysis['status']}")
    print(f"Message: {analysis['message']}")
    print()

    if analysis.get("history"):
        print("Recent History:")
        for entry in analysis["history"]:
            print(f"  {entry['timestamp'][:19]}: {entry['issues']} issues")

    return 0 if analysis["status"] in ["IMPROVING", "STABLE"] else 1


app = typer.Typer(help="SPARTA QRA Reality Check - ADVERSARIAL quality assessment with self-correction")


@app.command()
def main(
    db: str = typer.Option(None, help="Path to DuckDB file"),
    run_id: str = typer.Option("unknown", help="Run ID"),
    samples: int = typer.Option(20, help="Number of samples per check"),
    full: bool = typer.Option(False, help=""),
    store: bool = typer.Option(False, help="Store findings in memory"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    status_only: bool = typer.Option(False, help="Quick status only"),
    convergence: bool = typer.Option(False, help="Show convergence analysis"),
    suggest_fixes: bool = typer.Option(False, help="Show fix suggestions after check"),
    iterate: bool = typer.Option(False, help="Run iteration loop until clean"),
    max_iterations: int = typer.Option(10, help="Max iterations for loop"),
    client_report: bool = typer.Option(False, help="Generate client-facing report"),
):
    if convergence:
        return run_convergence_analysis()

    if status_only:
        if not db:
            print("ERROR: --db required for status", file=sys.stderr)
            return 1
        return run_status(db)

    if not db:
        print("ERROR: --db required", file=sys.stderr)
        return 1

    if iterate:
        return run_iteration_loop(
            db_path=db,
            run_id=run_id,
            max_iterations=max_iterations,
            store=store,
        )

    result = run_check(
        db_path=db,
        run_id=run_id,
        samples=samples,
        full=full,
        store=store,
        json_output=json,
        suggest_fixes_flag=suggest_fixes,
    )

    # Generate client report if requested
    if client_report and not json:
        import duckdb
        db_copy = get_db_copy(db)
        conn = duckdb.connect(str(db_copy), read_only=True)

        findings = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "qra_stats": check_qra_stats(conn),
            "sparta_source_fidelity": check_sparta_source_fidelity(conn),
            "sparta_alignment": check_sparta_alignment(conn),
            "url_file_alignment": check_url_file_alignment(conn, full=full),
            "qra_structure": check_qra_structure(conn),
            "marginal_analysis": check_marginal_qra_analysis(conn),
            "coverage_gaps": check_coverage_gaps(conn),
        }

        findings["overall_status"] = _determine_overall_status(findings)

        conn.close()

        print("\n" + generate_client_report(findings))

    return result


if __name__ == "__main__":
    app()
