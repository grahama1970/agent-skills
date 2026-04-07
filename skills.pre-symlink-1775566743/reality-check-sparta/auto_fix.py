#!/usr/bin/env python3
"""SPARTA QRA Auto-Fix Module - Self-Improvement Loop Implementation.

This module implements the auto-fix capability for reality-check-sparta,
closing the self-improvement loop:

    CHECK → IDENTIFY BAD QRAs → DELETE → REGENERATE → RE-CHECK

Usage:
    python auto_fix.py --db path/to/sparta.duckdb --run-id my-run

Flow:
    1. Identify marginal QRAs (grounding 0.55-0.65)
    2. Identify duplicate questions
    3. Delete bad QRAs
    4. Track which controls/relationships need regeneration
    5. Trigger regeneration with improved prompts
    6. Re-run reality check
"""

import typer
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Paths
SPARTA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "sparta"
SCRIPT_DIR = Path(__file__).parent
MEMORY_DIR = Path(__file__).resolve().parent.parent.parent.parent / "memory"


def log(msg: str) -> None:
    """Log with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_db_copy(db_path: Path) -> Path:
    """Create a writable copy of the database."""
    copy_path = db_path.parent / f"{db_path.stem}_autofix_copy.duckdb"
    if copy_path.exists():
        copy_path.unlink()
    shutil.copy2(db_path, copy_path)
    return copy_path


def identify_marginal_qras(conn, threshold_low: float = 0.55, threshold_high: float = 0.65) -> List[dict]:
    """Find QRAs with marginal grounding scores."""
    result = conn.execute(f"""
        SELECT qra_id, control_id, relationship_id, question, grounding_score
        FROM qra
        WHERE grounding_score >= {threshold_low} AND grounding_score < {threshold_high}
    """).fetchall()

    return [
        {
            "qra_id": r[0],
            "control_id": r[1],
            "relationship_id": r[2],
            "question": r[3],
            "grounding_score": r[4],
            "reason": "marginal_grounding"
        }
        for r in result
    ]


def identify_duplicate_questions(conn) -> List[dict]:
    """Find duplicate questions (keep highest grounding score)."""
    # Find all duplicates
    result = conn.execute("""
        WITH ranked AS (
            SELECT
                qra_id,
                question,
                grounding_score,
                control_id,
                relationship_id,
                ROW_NUMBER() OVER (PARTITION BY question ORDER BY grounding_score DESC) as rn
            FROM qra
        )
        SELECT qra_id, control_id, relationship_id, question, grounding_score
        FROM ranked
        WHERE rn > 1
    """).fetchall()

    return [
        {
            "qra_id": r[0],
            "control_id": r[1],
            "relationship_id": r[2],
            "question": r[3],
            "grounding_score": r[4],
            "reason": "duplicate_question"
        }
        for r in result
    ]


def identify_unanchored_qras(conn, samples: int = 200) -> List[dict]:
    """Find QRAs lacking technique-tactic anchoring (Brandon's NON-NEGOTIABLE criterion).

    A QRA MUST:
    - Reference the technique by name or ID
    - Reflect the parent tactic context (keywords)
    """
    # SPARTA technique categories
    SPARTA_TECHNIQUE_CATEGORIES = {
        "REC": "Reconnaissance",
        "IA": "Initial Access",
        "EX": "Execution",
        "PER": "Persistence",
        "PE": "Privilege Escalation",
        "DE": "Defense Evasion",
        "LM": "Lateral Movement",
        "EXF": "Exfiltration",
        "IMP": "Impact",
        "RD": "Resource Development",
    }

    TACTIC_KEYWORDS = {
        "REC": ["reconnaissance", "gather", "discover", "enumerate", "scan"],
        "IA": ["initial access", "entry", "intrusion", "compromise", "foothold"],
        "EX": ["execution", "execute", "run", "inject", "command"],
        "PER": ["persistence", "persist", "maintain", "backdoor", "implant"],
        "PE": ["privilege", "escalation", "elevate", "root", "admin"],
        "DE": ["evasion", "evade", "hide", "obfuscate", "bypass"],
        "LM": ["lateral", "movement", "pivot", "spread", "propagate"],
        "EXF": ["exfiltration", "exfiltrate", "steal", "extract", "transfer"],
        "IMP": ["impact", "disrupt", "destroy", "deny", "degrade"],
        "RD": ["resource", "development", "acquire", "obtain", "establish"],
    }

    # Sample QRAs with high grounding (so anchoring is the only issue)
    result = conn.execute(f"""
        SELECT
            q.qra_id, q.control_id, q.relationship_id, q.question, q.answer, q.grounding_score,
            t."ID" as technique_id, t."Name" as technique_name
        FROM qra q
        JOIN relationships r ON q.relationship_id = r.relationship_id
        JOIN s01_raw__sparta_techniques t ON r.technique_id = t."ID"
        WHERE q.grounding_score >= 0.80
        ORDER BY RANDOM()
        LIMIT {samples}
    """).fetchall()

    bad_qras = []
    for r in result:
        qra_id, control_id, rel_id, question, answer, score, tech_id, tech_name = r
        combined_text = f"{question} {answer}".lower()

        # Check technique anchoring
        tech_name_lower = (tech_name or "").lower()
        tech_id_lower = (tech_id or "").lower()
        technique_anchored = tech_name_lower in combined_text or tech_id_lower in combined_text

        # Check tactic anchoring
        tech_category = tech_id.split("-")[0] if tech_id else ""
        tactic_name = SPARTA_TECHNIQUE_CATEGORIES.get(tech_category, "")
        tactic_anchored = False

        if tactic_name and tactic_name.lower() in combined_text:
            tactic_anchored = True
        if tech_category.lower() in combined_text:
            tactic_anchored = True

        if not tactic_anchored:
            keywords = TACTIC_KEYWORDS.get(tech_category, [])
            if any(kw in combined_text for kw in keywords):
                tactic_anchored = True

        # Flag if either check fails
        if not technique_anchored or not tactic_anchored:
            reasons = []
            if not technique_anchored:
                reasons.append("NOT_TECHNIQUE_ANCHORED")
            if not tactic_anchored:
                reasons.append("NOT_TACTIC_ANCHORED")

            bad_qras.append({
                "qra_id": qra_id,
                "control_id": control_id,
                "relationship_id": rel_id,
                "question": question,
                "grounding_score": score,
                "reason": "+".join(reasons),
                "technique_name": tech_name,
                "technique_id": tech_id,
            })

    return bad_qras


def identify_low_space_terminology(conn, samples: int = 100) -> List[dict]:
    """Find QRAs lacking space-specific terminology (Brandon's criterion)."""
    SPACE_TERMS = {
        "satellite", "spacecraft", "payload", "bus", "orbit", "orbital",
        "leo", "meo", "geo", "heo", "constellation",
        "ground station", "ground segment", "mission control", "tt&c",
        "telemetry", "tracking", "command", "uplink", "downlink",
        "rf", "radio frequency", "satcom", "transponder", "antenna",
        "signal", "jamming", "spoofing", "interference",
        "ccsds", "spacewire", "mil-std", "space packet",
        "asat", "anti-satellite", "kinetic", "directed energy",
    }

    # Sample QRAs and check for space terminology
    result = conn.execute(f"""
        SELECT qra_id, control_id, relationship_id, question, answer, grounding_score
        FROM qra
        WHERE grounding_score >= 0.65 AND grounding_score < 0.80
        ORDER BY RANDOM()
        LIMIT {samples}
    """).fetchall()

    bad_qras = []
    for r in result:
        combined_text = f"{r[3]} {r[4]}".lower()
        has_space_term = any(term in combined_text for term in SPACE_TERMS)

        if not has_space_term:
            bad_qras.append({
                "qra_id": r[0],
                "control_id": r[1],
                "relationship_id": r[2],
                "question": r[3],
                "grounding_score": r[5],
                "reason": "missing_space_terminology"
            })

    return bad_qras


def delete_bad_qras(conn, qra_ids: List[int]) -> int:
    """Delete QRAs by ID."""
    if not qra_ids:
        return 0

    placeholders = ",".join(str(qid) for qid in qra_ids)
    conn.execute(f"DELETE FROM qra WHERE qra_id IN ({placeholders})")
    return len(qra_ids)


def get_regeneration_targets(bad_qras: List[dict]) -> Tuple[Set[str], Set[int]]:
    """Extract unique control_ids and relationship_ids for regeneration."""
    control_ids = set()
    relationship_ids = set()

    for qra in bad_qras:
        if qra.get("control_id"):
            control_ids.add(qra["control_id"])
        if qra.get("relationship_id"):
            relationship_ids.add(qra["relationship_id"])

    return control_ids, relationship_ids


def save_regeneration_manifest(
    bad_qras: List[dict],
    control_ids: Set[str],
    relationship_ids: Set[int],
    output_path: Path
) -> None:
    """Save a manifest of what needs regeneration."""
    manifest = {
        "timestamp": datetime.now().isoformat(),
        "bad_qra_count": len(bad_qras),
        "controls_to_regenerate": sorted(control_ids),
        "relationships_to_regenerate": sorted(relationship_ids),
        "by_reason": {},
        "details": bad_qras
    }

    # Count by reason
    for qra in bad_qras:
        reason = qra.get("reason", "unknown")
        manifest["by_reason"][reason] = manifest["by_reason"].get(reason, 0) + 1

    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)

    log(f"Saved regeneration manifest to {output_path}")


def trigger_regeneration(
    db_path: Path,
    run_id: str,
    control_ids: Set[str],
    relationship_ids: Set[int],
    improved_prompt: bool = True
) -> bool:
    """Trigger QRA regeneration for specific controls/relationships.

    Since --exhaustive mode skips relationships with existing QRAs,
    after deleting bad QRAs the pipeline will naturally regenerate them
    on restart. This function restarts Stage 12 in exhaustive mode.

    For targeted single-control regeneration, uses --control-id flag.
    For bulk regeneration (>10 controls), restarts full exhaustive run.
    """
    qra_script = SPARTA_DIR / "src" / "sparta" / "pipeline_duckdb" / "12_qra.py"
    python_bin = SPARTA_DIR / ".venv" / "bin" / "python"

    if not qra_script.exists():
        log(f"WARNING: QRA script not found at {qra_script}")
        return False

    if not python_bin.exists():
        log(f"WARNING: Python venv not found at {python_bin}")
        return False

    log(f"Regeneration targets: {len(control_ids)} controls, {len(relationship_ids)} relationships")

    # Save manifest for audit trail
    manifest = {
        "timestamp": datetime.now().isoformat(),
        "run_id": run_id,
        "control_ids": sorted(control_ids),
        "relationship_ids": sorted(relationship_ids),
        "improved_prompt": improved_prompt,
    }
    manifest_path = SPARTA_DIR / "data" / "runs" / run_id / "regeneration_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    log(f"Saved regeneration manifest: {manifest_path}")

    if len(control_ids) <= 10:
        # Targeted regeneration: one control at a time
        for cid in control_ids:
            log(f"Regenerating QRAs for control {cid}...")
            cmd = [
                str(python_bin), "-m", "sparta.pipeline_duckdb.12_qra",
                "--run-id", run_id,
                "--max-pairs", "500",
                "--control-id", cid,
                "--skip-sanity",
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600,
                    cwd=str(SPARTA_DIR),
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
                if result.returncode != 0:
                    log(f"  WARNING: Regeneration for {cid} returned {result.returncode}")
                    log(f"  stderr: {result.stderr[:200]}")
                else:
                    log(f"  Regeneration for {cid} complete")
            except subprocess.TimeoutExpired:
                log(f"  WARNING: Regeneration for {cid} timed out")
            except Exception as e:
                log(f"  ERROR: Regeneration for {cid} failed: {e}")
    else:
        # Bulk regeneration: restart full exhaustive run
        # Bad QRAs were already deleted, so --exhaustive will regenerate them
        log(f"Bulk regeneration: restarting exhaustive run for {len(control_ids)} controls")
        log("(Deleted QRAs will be regenerated on restart since --exhaustive skips existing)")

        log_path = SPARTA_DIR / "data" / "runs" / run_id / "logs" / "12_qra.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(python_bin), "-m", "sparta.pipeline_duckdb.12_qra",
            "--run-id", run_id,
            "--max-pairs", "1000000000",
            "--exhaustive",
            "--skip-sanity",
        ]

        with open(log_path, "a") as lf:
            proc = subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(SPARTA_DIR),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                start_new_session=True,
            )

        log(f"Stage 12 restarted (PID {proc.pid})")

    return True


def run_reality_check(db_path: Path, run_id: str, samples: int = 50) -> Tuple[bool, dict]:
    """Run reality check and return (passed, results)."""
    cmd = [
        "uv", "run", "python", str(SCRIPT_DIR / "check.py"),
        "--db", str(db_path),
        "--run-id", run_id,
        "--samples", str(samples),
        "--json",
        "--store"
    ]

    try:
        os.chdir(SPARTA_DIR)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        # Parse JSON output
        output = result.stdout
        json_start = output.find("{")
        if json_start >= 0:
            json_str = output[json_start:]
            brace_count = 0
            json_end = 0
            for i, c in enumerate(json_str):
                if c == "{":
                    brace_count += 1
                elif c == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break

            if json_end > 0:
                results = json.loads(json_str[:json_end])
                overall_status = results.get("overall_status", "UNKNOWN")
                passed = overall_status in ("PASS", "WARN")
                return passed, results

        return result.returncode == 0, {"raw_output": output}

    except Exception as e:
        log(f"Reality check error: {e}")
        return False, {"error": str(e)}


def auto_fix_loop(
    db_path: Path,
    run_id: str,
    max_iterations: int = 5,
    delete_marginal: bool = True,
    delete_duplicates: bool = True,
    delete_no_space_terms: bool = False,
    delete_unanchored: bool = True,  # Brandon's NON-NEGOTIABLE
    samples_per_check: int = 50
) -> int:
    """
    Run the auto-fix self-improvement loop.

    Returns:
        0 if all checks pass
        1 if max iterations reached
        2 if error
    """
    log("=" * 70)
    log("SPARTA AUTO-FIX SELF-IMPROVEMENT LOOP")
    log("=" * 70)
    log(f"Database: {db_path}")
    log(f"Run ID: {run_id}")
    log(f"Max iterations: {max_iterations}")
    log("")

    monitor = TaskClient("reality-check-autofix", total=max_iterations) if TaskClient else None

    for iteration in range(1, max_iterations + 1):
        log(f"\n{'='*70}")
        log(f"ITERATION {iteration}/{max_iterations}")
        log(f"{'='*70}")

        # Create writable copy for modifications
        db_copy = get_db_copy(db_path)

        try:
            import duckdb
            conn = duckdb.connect(str(db_copy))

            # Step 1: Identify bad QRAs
            log("\n--- Step 1: Identifying bad QRAs ---")
            bad_qras = []

            if delete_marginal:
                marginal = identify_marginal_qras(conn)
                log(f"Found {len(marginal)} marginal QRAs")
                bad_qras.extend(marginal)

            if delete_duplicates:
                duplicates = identify_duplicate_questions(conn)
                log(f"Found {len(duplicates)} duplicate QRAs")
                bad_qras.extend(duplicates)

            if delete_no_space_terms:
                no_space = identify_low_space_terminology(conn, samples=100)
                log(f"Found {len(no_space)} QRAs lacking space terminology")
                bad_qras.extend(no_space)

            if delete_unanchored:
                unanchored = identify_unanchored_qras(conn, samples=200)
                log(f"Found {len(unanchored)} QRAs lacking technique-tactic anchoring")
                bad_qras.extend(unanchored)

            if not bad_qras:
                log("\n✓ No bad QRAs found! Running final check...")
                conn.close()

                passed, results = run_reality_check(db_path, f"{run_id}-final", samples_per_check)
                if passed:
                    log("\n" + "="*70)
                    log("✓ ALL CHECKS PASSED!")
                    log("="*70)
                    if monitor:
                        monitor.finish()
                    return 0
                else:
                    log("Final check still has issues but no auto-fixable QRAs found")
                    log("Manual intervention may be required")
                    return 1

            # Step 2: Get regeneration targets
            log("\n--- Step 2: Planning regeneration ---")
            control_ids, relationship_ids = get_regeneration_targets(bad_qras)

            # Save manifest
            manifest_path = SPARTA_DIR / "data" / "runs" / run_id / "autofix_manifest.json"
            save_regeneration_manifest(bad_qras, control_ids, relationship_ids, manifest_path)

            # Step 3: Delete bad QRAs
            log("\n--- Step 3: Deleting bad QRAs ---")
            qra_ids = [q["qra_id"] for q in bad_qras]
            deleted = delete_bad_qras(conn, qra_ids)
            log(f"Deleted {deleted} QRAs")

            # Commit changes
            conn.close()

            # Copy back to original
            shutil.copy2(db_copy, db_path)
            log(f"Updated {db_path}")

            # Clean up copy
            db_copy.unlink()

            # Step 4: Run reality check
            log("\n--- Step 4: Running reality check ---")
            passed, results = run_reality_check(db_path, f"{run_id}-iter{iteration}", samples_per_check)

            status = results.get("overall_status", "UNKNOWN")
            issues = results.get("total_issues_found", 0)
            log(f"Check result: {status} ({issues} issues)")

            if monitor:
                monitor.update(item=f"iter-{iteration}")

            if passed:
                log("\n" + "="*70)
                log(f"✓ CHECKS PASSED after iteration {iteration}!")
                log("="*70)
                if monitor:
                    monitor.finish()
                return 0

            # If not passed, continue to next iteration
            log(f"\nContinuing to iteration {iteration + 1}...")

        except Exception as e:
            log(f"ERROR in iteration {iteration}: {e}")
            import traceback
            traceback.print_exc()

            # Clean up
            if db_copy.exists():
                db_copy.unlink()

            return 2

    log("\n" + "="*70)
    log(f"⚠️ MAX ITERATIONS ({max_iterations}) REACHED")
    log("="*70)
    log("Not all issues resolved. Manual intervention required.")

    if monitor:
        monitor.finish()
    return 1


app = typer.Typer(help="SPARTA QRA Auto-Fix - Self-Improvement Loop")


@app.command()
def main(
    db: str = typer.Option(..., help="Path to DuckDB file"),
    run_id: str = typer.Option("auto-fix", help="Run ID for tracking"),
    max_iterations: int = typer.Option(5, help="Max fix iterations"),
    samples: int = typer.Option(50, help="Samples per reality check"),
    no_delete_marginal: bool = typer.Option(False, help="Don"),
    no_delete_duplicates: bool = typer.Option(False, help="Don"),
    delete_no_space_terms: bool = typer.Option(False, help="Also delete QRAs lacking space terminology"),
    no_delete_unanchored: bool = typer.Option(False, help="Don"),
    dry_run: bool = typer.Option(False, help="Show what would be fixed"),
):
    if dry_run:
        log("DRY RUN MODE - No changes will be made")
        import duckdb
        conn = duckdb.connect(str(db), read_only=True)

        marginal = identify_marginal_qras(conn)
        duplicates = identify_duplicate_questions(conn)
        no_space = identify_low_space_terminology(conn, samples=100)
        unanchored = identify_unanchored_qras(conn, samples=200)

        log(f"\nWould delete:")
        log(f"  Marginal QRAs: {len(marginal)}")
        log(f"  Duplicate QRAs: {len(duplicates)}")
        log(f"  No space terms (sampled): {len(no_space)}")
        log(f"  Unanchored QRAs (sampled): {len(unanchored)}")

        # Show sample unanchored QRAs
        if unanchored:
            log("\nSample unanchored QRAs:")
            for uq in unanchored[:5]:
                log(f"  - QRA {uq['qra_id']}: {uq['reason']}")
                log(f"    Technique: {uq.get('technique_name', 'N/A')}")
                log(f"    Question: {uq['question'][:60]}...")

        conn.close()
        return 0

    return auto_fix_loop(
        db_path=db,
        run_id=run_id,
        max_iterations=max_iterations,
        delete_marginal=not no_delete_marginal,
        delete_duplicates=not no_delete_duplicates,
        delete_no_space_terms=delete_no_space_terms,
        delete_unanchored=not no_delete_unanchored,  # Brandon's NON-NEGOTIABLE
        samples_per_check=samples
    )


if __name__ == "__main__":
    app()
