#!/usr/bin/env python3
"""DEPRECATED (2026-02-13): Brandon's framework checks are now INLINE in 12_qra.py.

The assess_qra(), detect_framework(), FRAMEWORK_TERMS, and FRAMEWORK_GROUNDING
have been merged into the pipeline itself (sparta/pipeline_duckdb/12_qra.py).
Every QRA is now assessed at generation time with PASS/WARN/FAIL gating.

This file is kept as reference only. Do NOT run as a daemon alongside the pipeline.
The /sparta-review skill (converge.py) remains the CHECKPOINT assessment tool.

--- Original description ---
Brandon Continuous Reviewer — Stratified random sampling with grade persistence.

Runs continuously, sampling unreviewed QRAs from the live pipeline DB,
assessing quality, and writing grades to a separate reviews DB.

Key Design:
- Reads from SNAPSHOT of pipeline DB (avoids write lock)
- Writes to SEPARATE reviews DB (no lock conflict with pipeline)
- Samples only QRAs not already reviewed
- Stratified by category to ensure coverage
- Writes grade + notes per QRA

Usage:
    python brandon_reviewer.py --run-id run-recovery-verify --batch-size 10 --interval 300
"""

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import duckdb
except ImportError:
    print("ERROR: duckdb not installed", file=sys.stderr)
    sys.exit(1)

# Paths
SPARTA_DIR = Path(os.environ.get("SPARTA_DIR", str(Path.home() / "workspace/experiments/sparta")))
REVIEWS_DIR = SPARTA_DIR / "data" / "runs"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_db_path(run_id: str) -> Path:
    return SPARTA_DIR / "data" / "runs" / run_id / "sparta.duckdb"


def get_reviews_db_path(run_id: str) -> Path:
    return SPARTA_DIR / "data" / "runs" / run_id / "brandon_reviews.duckdb"


def init_reviews_db(run_id: str) -> None:
    """Create the reviews DB and table if they don't exist."""
    reviews_path = get_reviews_db_path(run_id)
    con = duckdb.connect(str(reviews_path))
    con.execute("""
        CREATE TABLE IF NOT EXISTS qra_reviews (
            qra_id INTEGER PRIMARY KEY,
            grade VARCHAR NOT NULL,       -- PASS, WARN, FAIL
            grounding_check FLOAT,        -- verified grounding score
            anchoring_ok BOOLEAN,         -- technique/tactic properly anchored
            space_terms_ok BOOLEAN,       -- contains space-specific terminology
            notes VARCHAR,                -- Brandon's comments
            category VARCHAR,             -- control category (for stratification tracking)
            reviewer VARCHAR DEFAULT 'brandon_v1',
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS review_sessions (
            session_id INTEGER PRIMARY KEY,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            qras_reviewed INTEGER DEFAULT 0,
            pass_count INTEGER DEFAULT 0,
            warn_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            avg_grounding FLOAT,
            notes VARCHAR
        )
    """)
    con.close()
    log(f"Reviews DB initialized: {reviews_path}")


def snapshot_db(run_id: str) -> Optional[Path]:
    """Take a snapshot of the pipeline DB for reading."""
    db_path = get_db_path(run_id)
    wal_path = Path(str(db_path) + ".wal")
    snapshot = Path(f"/tmp/brandon_review_snapshot_{run_id}.duckdb")
    snapshot_wal = Path(str(snapshot) + ".wal")

    try:
        shutil.copy2(db_path, snapshot)
        if wal_path.exists():
            shutil.copy2(wal_path, snapshot_wal)
        return snapshot
    except Exception as e:
        log(f"ERROR: Could not snapshot DB: {e}")
        return None


def cleanup_snapshot(snapshot: Path) -> None:
    snapshot.unlink(missing_ok=True)
    Path(str(snapshot) + ".wal").unlink(missing_ok=True)


def get_reviewed_ids(run_id: str) -> set:
    """Get set of already-reviewed QRA IDs."""
    reviews_path = get_reviews_db_path(run_id)
    if not reviews_path.exists():
        return set()
    try:
        con = duckdb.connect(str(reviews_path), read_only=True)
        ids = con.execute("SELECT qra_id FROM qra_reviews").fetchall()
        con.close()
        return {row[0] for row in ids}
    except Exception:
        return set()


def sample_unreviewed_qras(snapshot: Path, reviewed_ids: set, batch_size: int = 10) -> list:
    """Sample stratified unreviewed QRAs from the snapshot."""
    con = duckdb.connect(str(snapshot), read_only=True)

    # Get category distribution for stratification
    cats = con.execute("""
        SELECT SPLIT_PART(control_id, '-', 1) as cat, COUNT(*) as cnt
        FROM qra
        GROUP BY cat
        ORDER BY cnt DESC
    """).fetchall()

    total_cats = len(cats)
    if total_cats == 0:
        con.close()
        return []

    # Stratified sampling: pick proportionally from each category
    # But ensure at least 1 from each category if possible
    samples_per_cat = max(1, batch_size // min(total_cats, batch_size))
    all_samples = []

    # Build exclusion list as a SQL-safe string
    if reviewed_ids:
        # For large sets, use a temp table approach
        exclude_list = ",".join(str(i) for i in reviewed_ids)
        exclude_clause = f"AND qra_id NOT IN ({exclude_list})"
    else:
        exclude_clause = ""

    for cat, cnt in cats:
        if len(all_samples) >= batch_size:
            break

        remaining = min(samples_per_cat, batch_size - len(all_samples))
        try:
            rows = con.execute(f"""
                SELECT qra_id, control_id, relationship_id, question, question_type,
                       reasoning, answer, citations, grounding_score,
                       conceptual_tags, tactical_tags
                FROM qra
                WHERE SPLIT_PART(control_id, '-', 1) = ?
                {exclude_clause}
                ORDER BY RANDOM()
                LIMIT ?
            """, [cat, remaining]).fetchall()

            for row in rows:
                all_samples.append({
                    "qra_id": row[0],
                    "control_id": row[1],
                    "relationship_id": row[2],
                    "question": row[3],
                    "question_type": row[4],
                    "reasoning": row[5],
                    "answer": row[6],
                    "citations": row[7],
                    "grounding_score": row[8],
                    "conceptual_tags": row[9],
                    "tactical_tags": row[10],
                    "category": cat,
                })
        except Exception as e:
            log(f"  Sampling error for {cat}: {e}")
            continue

    con.close()
    return all_samples


def detect_framework(control_id: str) -> str:
    """Detect framework from control ID prefix."""
    cid = (control_id or "").upper()
    if cid.startswith("D3-") or cid.startswith("D3F"):
        return "D3FEND"
    if cid.startswith("CWE"):
        return "CWE"
    if cid.startswith("ESA"):
        return "ESA"
    if cid.startswith("T1") or cid.startswith("T0"):
        return "ATT&CK"
    # NIST: AC-1, PE-2(3), SI-7, etc.
    if len(cid) >= 3 and cid[:2].isalpha() and cid[2] == "-":
        return "NIST"
    # SPARTA native categories
    prefix = cid.split("-")[0] if "-" in cid else ""
    if prefix in {"REC", "DE", "EX", "IA", "IMP", "EXF", "RD", "SV"}:
        return "SPARTA"
    return "UNKNOWN"


# Framework-specific term lists for more targeted quality checks
FRAMEWORK_TERMS = {
    "D3FEND": [
        # D3FEND defensive vocabulary
        "detect", "isolat", "harden", "evict", "monitor",
        "defensive", "countermeasure", "mitigation", "protect",
        # Space-adapted D3FEND
        "spacecraft", "satellite", "ground station", "telemetry",
        "flight software", "onboard", "uplink", "downlink",
    ],
    "CWE": [
        # CWE weakness vocabulary
        "vulnerability", "weakness", "exploit", "buffer", "overflow",
        "injection", "validation", "sanitiz", "input",
        # Space-adapted CWE
        "embedded", "firmware", "rtos", "radiation", "hardened",
        "flight computer", "spacecraft", "onboard", "real-time",
    ],
    "ESA": [
        # ESA controls are already space-native
        "spacecraft", "satellite", "ground station", "telemetry",
        "uplink", "downlink", "orbit", "payload", "rf",
        "ccsds", "space", "mission", "esa",
    ],
    "ATT&CK": [
        # ATT&CK offensive vocabulary
        "adversar", "attack", "technique", "tactic", "exploit",
        "compromise", "lateral", "persistence", "exfiltrat",
        # Space-adapted ATT&CK
        "spacecraft", "satellite", "ground station", "command",
        "telemetry", "uplink", "rf", "mission",
    ],
    "NIST": [
        # NIST compliance vocabulary
        "control", "policy", "procedure", "compliance",
        "authorization", "audit", "assessment",
        # Space-adapted NIST
        "mission", "ground station", "spacecraft", "operator",
        "facility", "space system", "satellite",
    ],
    "SPARTA": [
        # SPARTA native
        "spacecraft", "satellite", "ground station", "telemetry",
        "uplink", "downlink", "orbit", "payload", "rf",
        "space segment", "ground segment", "mission", "ccsds",
    ],
}

# Framework-specific grounding thresholds (some frameworks are harder to ground)
FRAMEWORK_GROUNDING = {
    "D3FEND": {"fail": 0.55, "warn": 0.65},   # D3FEND artifacts are abstract
    "CWE": {"fail": 0.55, "warn": 0.65},       # CWE descriptions are generic
    "ESA": {"fail": 0.60, "warn": 0.70},       # ESA has rich source material
    "ATT&CK": {"fail": 0.55, "warn": 0.65},    # ATT&CK is generic IT, harder to ground in space
    "NIST": {"fail": 0.50, "warn": 0.60},      # NIST policy controls have least grounding material
    "SPARTA": {"fail": 0.60, "warn": 0.70},    # SPARTA native should ground well
    "UNKNOWN": {"fail": 0.60, "warn": 0.70},
}


def assess_qra(qra: dict) -> dict:
    """Brandon's per-QRA quality assessment (local, no LLM calls).

    Framework-aware: uses different term lists and grounding thresholds
    per framework (D3FEND, CWE, ATT&CK, ESA, NIST, SPARTA).

    Checks:
    1. Grounding score >= framework-specific threshold
    2. Answer contains framework-appropriate terms
    3. Anchoring: answer references the control
    4. Not too short / not empty
    5. Citations present
    """
    grade = "PASS"
    notes = []
    grounding = qra.get("grounding_score", 0.0) or 0.0
    control_id = (qra.get("control_id") or "")

    # Detect framework for targeted assessment
    framework = detect_framework(control_id)
    thresholds = FRAMEWORK_GROUNDING.get(framework, FRAMEWORK_GROUNDING["UNKNOWN"])

    # 1. Framework-specific grounding check
    if grounding < thresholds["fail"]:
        grade = "FAIL"
        notes.append(f"Grounding {grounding:.3f} < {thresholds['fail']} ({framework} FAIL threshold)")
    elif grounding < thresholds["warn"]:
        grade = "WARN"
        notes.append(f"Grounding {grounding:.3f} < {thresholds['warn']} ({framework} WARN threshold)")

    # 2. Framework-specific terms check
    answer = (qra.get("answer") or "").lower()
    fw_terms = FRAMEWORK_TERMS.get(framework, FRAMEWORK_TERMS.get("SPARTA", []))
    term_count = sum(1 for t in fw_terms if t in answer)
    space_terms_ok = term_count >= 2  # Need at least 2 framework-relevant terms

    if not space_terms_ok:
        if grade == "PASS":
            grade = "WARN"
        notes.append(f"Insufficient {framework} terms ({term_count}/2 needed)")

    # 3. Anchoring check - answer should reference the control
    anchoring_ok = True
    if control_id and control_id.lower() not in answer:
        # Check if control name parts appear
        parts = control_id.replace("-", " ").replace(":", " ").split()
        if not any(p.lower() in answer for p in parts if len(p) > 2):
            anchoring_ok = False
            if grade == "PASS":
                grade = "WARN"
            notes.append(f"Answer doesn't reference control {control_id}")

    # 4. Answer quality
    if len(answer) < 50:
        grade = "FAIL"
        notes.append(f"Answer too short ({len(answer)} chars)")
    elif len(answer) < 150:
        if grade == "PASS":
            grade = "WARN"
        notes.append(f"Answer relatively short ({len(answer)} chars)")

    # 5. Citations
    citations = qra.get("citations") or ""
    if not citations or citations.strip() in ("", "[]", "null", "None"):
        if grade == "PASS":
            grade = "WARN"
        notes.append("No citations provided")

    return {
        "qra_id": qra["qra_id"],
        "grade": grade,
        "grounding_check": grounding,
        "anchoring_ok": anchoring_ok,
        "space_terms_ok": space_terms_ok,
        "notes": "; ".join(notes) if notes else f"All checks passed ({framework})",
        "category": qra.get("category", ""),
    }


def write_reviews(run_id: str, reviews: list) -> None:
    """Write review results to the reviews DB."""
    reviews_path = get_reviews_db_path(run_id)
    con = duckdb.connect(str(reviews_path))

    for r in reviews:
        try:
            con.execute("""
                INSERT OR REPLACE INTO qra_reviews
                (qra_id, grade, grounding_check, anchoring_ok, space_terms_ok, notes, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                r["qra_id"], r["grade"], r["grounding_check"],
                r["anchoring_ok"], r["space_terms_ok"], r["notes"], r["category"]
            ])
        except Exception as e:
            log(f"  Write error for QRA {r['qra_id']}: {e}")

    con.close()


def get_review_stats(run_id: str) -> dict:
    """Get aggregate review statistics."""
    reviews_path = get_reviews_db_path(run_id)
    if not reviews_path.exists():
        return {}
    try:
        con = duckdb.connect(str(reviews_path), read_only=True)
        total = con.execute("SELECT COUNT(*) FROM qra_reviews").fetchone()[0]
        grades = con.execute("""
            SELECT grade, COUNT(*) as cnt
            FROM qra_reviews
            GROUP BY grade
        """).fetchall()
        avg_ground = con.execute("""
            SELECT ROUND(AVG(grounding_check), 4) FROM qra_reviews
        """).fetchone()[0]

        # Category coverage
        cats_reviewed = con.execute("""
            SELECT category, COUNT(*) as cnt,
                   SUM(CASE WHEN grade='PASS' THEN 1 ELSE 0 END) as pass_cnt,
                   SUM(CASE WHEN grade='FAIL' THEN 1 ELSE 0 END) as fail_cnt
            FROM qra_reviews
            GROUP BY category ORDER BY cnt DESC LIMIT 20
        """).fetchall()

        con.close()
        return {
            "total_reviewed": total,
            "grades": {g: c for g, c in grades},
            "avg_grounding": avg_ground,
            "categories": cats_reviewed,
        }
    except Exception:
        return {}


def continuous_review_loop(
    run_id: str,
    batch_size: int = 10,
    interval: int = 300,
    max_reviews: int = 100000,
) -> None:
    """Main continuous review loop.

    Every `interval` seconds:
    1. Snapshot the pipeline DB
    2. Sample `batch_size` unreviewed QRAs (stratified)
    3. Assess each one locally
    4. Write grades to reviews DB
    5. Print summary
    """
    log("=" * 70)
    log("BRANDON CONTINUOUS REVIEWER")
    log("=" * 70)
    log(f"Run ID:       {run_id}")
    log(f"Batch size:   {batch_size}")
    log(f"Interval:     {interval}s")
    log(f"Max reviews:  {max_reviews}")
    log("")

    init_reviews_db(run_id)

    total_reviewed = 0
    total_pass = 0
    total_warn = 0
    total_fail = 0
    cycle = 0

    while total_reviewed < max_reviews:
        cycle += 1
        log(f"\n--- Cycle {cycle} ---")

        # 1. Snapshot
        snapshot = snapshot_db(run_id)
        if not snapshot:
            log("Could not snapshot DB — waiting...")
            time.sleep(interval)
            continue

        # 2. Get already reviewed IDs
        reviewed_ids = get_reviewed_ids(run_id)

        # Get total QRA count
        try:
            snap_con = duckdb.connect(str(snapshot), read_only=True)
            total_qras = snap_con.execute("SELECT COUNT(*) FROM qra").fetchone()[0]
            snap_con.close()
        except Exception:
            total_qras = 0

        log(f"Total QRAs: {total_qras} | Already reviewed: {len(reviewed_ids)} | Unreviewed: {total_qras - len(reviewed_ids)}")

        if len(reviewed_ids) >= total_qras:
            log("All QRAs reviewed! Waiting for new ones...")
            cleanup_snapshot(snapshot)
            time.sleep(interval)
            continue

        # 3. Sample unreviewed
        samples = sample_unreviewed_qras(snapshot, reviewed_ids, batch_size)
        cleanup_snapshot(snapshot)

        if not samples:
            log("No unreviewed samples found — waiting...")
            time.sleep(interval)
            continue

        log(f"Sampled {len(samples)} unreviewed QRAs")

        # 4. Assess each
        reviews = []
        batch_pass = 0
        batch_warn = 0
        batch_fail = 0

        for qra in samples:
            result = assess_qra(qra)
            reviews.append(result)

            if result["grade"] == "PASS":
                batch_pass += 1
            elif result["grade"] == "WARN":
                batch_warn += 1
            else:
                batch_fail += 1

        # 5. Write grades
        write_reviews(run_id, reviews)

        total_reviewed += len(reviews)
        total_pass += batch_pass
        total_warn += batch_warn
        total_fail += batch_fail

        # 6. Report
        log(f"Batch: PASS={batch_pass} WARN={batch_warn} FAIL={batch_fail}")
        log(f"Total reviewed: {total_reviewed}/{total_qras} ({total_reviewed/total_qras*100:.1f}%)")
        log(f"Overall: PASS={total_pass} ({total_pass/total_reviewed*100:.0f}%) WARN={total_warn} ({total_warn/total_reviewed*100:.0f}%) FAIL={total_fail} ({total_fail/total_reviewed*100:.0f}%)")

        # Show failures
        for r in reviews:
            if r["grade"] == "FAIL":
                log(f"  FAIL qra_id={r['qra_id']}: {r['notes']}")

        # Alert on high failure rate
        if total_reviewed >= 20:
            fail_rate = total_fail / total_reviewed
            if fail_rate > 0.20:
                log(f"*** ALERT: Failure rate {fail_rate:.0%} > 20%! Consider stopping pipeline. ***")
            elif fail_rate > 0.10:
                log(f"*** WARNING: Failure rate {fail_rate:.0%} > 10% ***")

        # Print periodic full stats
        if cycle % 5 == 0:
            stats = get_review_stats(run_id)
            if stats.get("categories"):
                log("\nCategory Review Status:")
                for cat, cnt, p, f in stats["categories"][:15]:
                    log(f"  {cat:8s}: {cnt:4d} reviewed, {p} PASS, {f} FAIL")

        time.sleep(interval)

    log(f"\nMax reviews reached ({max_reviews}). Final stats:")
    stats = get_review_stats(run_id)
    log(json.dumps(stats, indent=2, default=str))


def _cli(
    run_id: str = typer.Option("run-recovery-verify", help="Pipeline run ID"),
    batch_size: int = typer.Option(10, help="QRAs to review per cycle"),
    interval: int = typer.Option(300, help="Seconds between review cycles"),
    max_reviews: int = typer.Option(100000, help="Stop after this many reviews"),
) -> None:
    """Brandon Continuous Reviewer."""
    continuous_review_loop(
        run_id=run_id,
        batch_size=batch_size,
        interval=interval,
        max_reviews=max_reviews,
    )


if __name__ == "__main__":
    import typer
    typer.run(_cli)
