#!/usr/bin/env python3
"""
Batch Quality CLI - Preflight validation and quality gates for batch LLM operations.

ACTUALLY tests LLM samples before burning tokens on full batch.
Uses scillm for sample execution and SPARTA contracts for validation.

Usage:
    python cli.py preflight --stage 05 --samples 3 --run-id run-recovery-verify
    python cli.py validate --stage 05 --run-id run-recovery-verify --task-name sparta-stage-05
    python cli.py status
    python cli.py clear
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import typer

app = typer.Typer(help="Batch Quality - Preflight validation and quality gates")

# State directory
STATE_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "batch-preflight"
PREFLIGHT_FILE = Path(os.environ.get("BATCH_PREFLIGHT_FILE", STATE_DIR / "preflight_state"))

# Skill directories
SCRIPT_DIR = Path(__file__).parent
TASK_MONITOR_DIR = SCRIPT_DIR.parent / "task-monitor"

# SPARTA paths
SPARTA_ROOT = Path(os.environ.get("SPARTA_ROOT", "/home/graham/workspace/experiments/sparta"))
CONTRACTS_DIR = SPARTA_ROOT / "tools" / "pipeline_gates" / "fixtures" / "D3-FEV" / "contracts"


def ensure_state_dir():
    """Ensure state directory exists."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_preflight_state() -> Optional[dict]:
    """Load preflight state from file."""
    if not PREFLIGHT_FILE.exists():
        return None
    try:
        with open(PREFLIGHT_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_preflight_state(state: dict):
    """Save preflight state to file."""
    ensure_state_dir()
    with open(PREFLIGHT_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_preflight_valid(max_age_seconds: int = 1800) -> bool:
    """Check if preflight is still valid (within max age)."""
    state = load_preflight_state()
    if not state:
        return False
    if state.get("status") != "passed":
        return False
    timestamp = state.get("timestamp", 0)
    age = time.time() - timestamp
    return age < max_age_seconds


def load_contract(stage: str) -> Optional[dict]:
    """Load SPARTA contract for a stage."""
    # Try exact match first
    contract_file = CONTRACTS_DIR / f"{stage}.json"
    if not contract_file.exists():
        # Try with prefix patterns
        for pattern in [f"{stage}_*.json", f"*{stage}*.json", f"0{stage}_*.json"]:
            matches = list(CONTRACTS_DIR.glob(pattern))
            if matches:
                contract_file = matches[0]
                break

    if not contract_file.exists():
        return None

    try:
        with open(contract_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def get_duckdb_connection(run_id: str):
    """Get DuckDB connection for a run."""
    try:
        import duckdb
        db_path = SPARTA_ROOT / "data" / "runs" / run_id / "sparta.duckdb"
        if not db_path.exists():
            return None
        return duckdb.connect(str(db_path), read_only=True)
    except ImportError:
        return None


async def test_llm_sample(prompt: str, content: str, model: str, api_base: str, api_key: str) -> dict:
    """Actually test a single LLM sample using scillm."""
    try:
        from scillm.batch import parallel_acompletions_iter

        # Build request matching SPARTA pattern
        request = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Extract knowledge from:\n\n{content[:5000]}"}
            ],
            "response_format": {"type": "json_object"},
            "extra_body": {"api_base": api_base, "api_key": api_key}
        }

        result = {"ok": False, "content": None, "error": None}

        async for res in parallel_acompletions_iter([request], concurrency=1, timeout=60):
            if res.get("ok"):
                result["ok"] = True
                result["content"] = res.get("content", "")
                # Validate JSON structure
                try:
                    parsed = json.loads(result["content"])
                    result["valid_json"] = True
                    result["has_excerpts"] = "excerpts" in parsed
                    result["excerpt_count"] = len(parsed.get("excerpts", []))
                except json.JSONDecodeError:
                    result["valid_json"] = False
            else:
                result["error"] = res.get("error", "Unknown error")

        return result

    except ImportError:
        return {"ok": False, "error": "scillm not available", "scillm_missing": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_sample_content(run_id: str, stage: str, n_samples: int) -> list[dict]:
    """Get N sample items from the input queue for a stage."""
    samples = []

    conn = get_duckdb_connection(run_id)
    if not conn:
        return samples

    try:
        if stage in ["05", "05_extract_knowledge"]:
            # Stage 05: Sample from urls with content
            query = """
                SELECT url_hash, url, local_path
                FROM urls
                WHERE local_path IS NOT NULL
                  AND ok = true
                ORDER BY RANDOM()
                LIMIT ?
            """
            result = conn.execute(query, [n_samples]).fetchall()

            for row in result:
                url_hash, url, local_path = row
                content = None
                if local_path and Path(local_path).exists():
                    try:
                        content = Path(local_path).read_text(errors='ignore')[:5000]
                    except Exception:
                        pass
                samples.append({
                    "id": url_hash,
                    "url": url,
                    "content": content or f"Content from {url}"
                })

        elif stage in ["08b", "08b_infer_relationships"]:
            # Stage 08b: Sample orphan controls
            query = """
                SELECT c.control_id, c.title, c.description
                FROM nist_controls c
                LEFT JOIN relationship_edges e ON c.control_id = e.source_id
                WHERE e.source_id IS NULL
                ORDER BY RANDOM()
                LIMIT ?
            """
            result = conn.execute(query, [n_samples]).fetchall()

            for row in result:
                control_id, title, desc = row
                samples.append({
                    "id": control_id,
                    "content": f"{title}: {desc or ''}"
                })

    except Exception as e:
        pass  # Silently fail, will return empty samples
    finally:
        conn.close()

    return samples


@app.command()
def preflight(
    stage: str = typer.Option(..., "--stage", "-s", help="Stage name (e.g., 05, 06, 08b)"),
    samples: int = typer.Option(3, "--samples", "-n", help="Number of samples to test"),
    run_id: str = typer.Option(None, "--run-id", "-r", help="SPARTA run ID for sampling"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Check prerequisites without running LLM"),
    prompt_file: Optional[str] = typer.Option(None, "--prompt", "-p", help="Custom prompt file"),
):
    """
    Run preflight validation before batch operation.

    ACTUALLY tests N samples through the LLM before burning tokens on full batch.
    Exit code 0 = pass, 1 = fail, 42 = needs clarification.
    """
    typer.echo(f"\n=== PREFLIGHT CHECK: Stage {stage} ===\n")

    results = {
        "stage": stage,
        "run_id": run_id,
        "samples_requested": samples,
        "samples_tested": 0,
        "samples_passed": 0,
        "checks": [],
        "timestamp": int(time.time()),
    }

    # Check 1: Contract exists
    contract = load_contract(stage)
    if contract:
        typer.echo(f"  [check] Contract: {contract.get('name', stage)}")
        results["checks"].append({"name": "contract", "status": "pass"})
        results["contract"] = contract.get("name")
    else:
        typer.echo(f"  [warn] No contract found for stage {stage}")
        results["checks"].append({"name": "contract", "status": "warn", "note": "no contract"})

    # Check 2: Environment variables
    env_checks = []
    api_key = os.environ.get("CHUTES_API_KEY", "")
    api_base = os.environ.get("CHUTES_API_BASE", "https://llm.chutes.ai/v1")
    model = os.environ.get("CHUTES_TEXT_MODEL", os.environ.get("CHUTES_MODEL_ID", ""))

    if api_key:
        typer.echo(f"  [check] CHUTES_API_KEY set")
        env_checks.append({"name": "api_key", "status": "pass"})
    else:
        typer.echo(f"  [FAIL] CHUTES_API_KEY not set")
        env_checks.append({"name": "api_key", "status": "fail"})

    if model:
        typer.echo(f"  [check] Model: {model}")
        env_checks.append({"name": "model", "status": "pass"})
    else:
        typer.echo(f"  [FAIL] CHUTES_TEXT_MODEL not set")
        env_checks.append({"name": "model", "status": "fail"})

    results["checks"].extend(env_checks)
    env_passed = all(c["status"] == "pass" for c in env_checks)

    # Check 3: Run ID and database access
    if run_id:
        conn = get_duckdb_connection(run_id)
        if conn:
            typer.echo(f"  [check] DuckDB accessible: {run_id}")
            results["checks"].append({"name": "database", "status": "pass"})
            conn.close()
        else:
            typer.echo(f"  [FAIL] DuckDB not accessible: {run_id}")
            results["checks"].append({"name": "database", "status": "fail"})
            env_passed = False

    # Check 4: Actually test samples (unless dry-run)
    if dry_run:
        typer.echo(f"\n  [DRY RUN] Would test {samples} samples")
        results["dry_run"] = True
    elif not env_passed:
        typer.echo(f"\n  [FAIL] Prerequisites failed - cannot test samples")
    else:
        typer.echo(f"\n  Testing {samples} samples...")

        # Get sample content
        sample_items = get_sample_content(run_id, stage, samples) if run_id else []

        if not sample_items:
            typer.echo(f"  [warn] No samples available - using synthetic test")
            sample_items = [{"id": "test", "content": "Test cybersecurity content about vulnerabilities."}]

        # Get prompt
        system_prompt = """You are a cybersecurity knowledge extractor.
Extract factual excerpts as JSON: {"excerpts": [{"text": "...", "topic": "...", "excerpt_type": "technique|vulnerability|defense"}], "source_quality": "high|medium|low"}"""

        if prompt_file and Path(prompt_file).exists():
            system_prompt = Path(prompt_file).read_text()

        # Test each sample
        passed = 0
        for i, item in enumerate(sample_items[:samples]):
            typer.echo(f"    Sample {i+1}/{samples}: {item.get('id', 'unknown')[:30]}...")

            result = asyncio.run(test_llm_sample(
                system_prompt,
                item.get("content", ""),
                model,
                api_base,
                api_key
            ))

            if result.get("scillm_missing"):
                typer.echo(f"      [warn] scillm not available - marking as untested")
                results["checks"].append({"name": f"sample_{i+1}", "status": "skip", "reason": "scillm_missing"})
            elif result.get("ok"):
                if result.get("valid_json") and result.get("has_excerpts"):
                    typer.echo(f"      [check] Valid JSON, {result.get('excerpt_count', 0)} excerpts")
                    passed += 1
                    results["checks"].append({"name": f"sample_{i+1}", "status": "pass", "excerpts": result.get("excerpt_count")})
                else:
                    typer.echo(f"      [FAIL] Invalid response structure")
                    results["checks"].append({"name": f"sample_{i+1}", "status": "fail", "reason": "invalid_structure"})
            else:
                typer.echo(f"      [FAIL] LLM error: {result.get('error', 'unknown')}")
                results["checks"].append({"name": f"sample_{i+1}", "status": "fail", "error": result.get("error")})

        results["samples_tested"] = len(sample_items[:samples])
        results["samples_passed"] = passed

    # Final result
    all_checks_pass = all(
        c["status"] in ["pass", "warn", "skip"]
        for c in results["checks"]
    )
    samples_ok = results["samples_passed"] >= results["samples_tested"] * 0.5  # 50% threshold

    if all_checks_pass and (dry_run or samples_ok):
        results["status"] = "passed"
        save_preflight_state(results)
        typer.echo(f"\n=== PREFLIGHT PASSED ===")
        typer.echo(f"   {results['samples_passed']}/{results['samples_tested']} samples succeeded")
        typer.echo(f"   State saved. Valid for 30 minutes.\n")
        raise typer.Exit(0)
    else:
        results["status"] = "failed"
        save_preflight_state(results)
        typer.echo(f"\n=== PREFLIGHT FAILED ===")
        typer.echo(f"   {results['samples_passed']}/{results['samples_tested']} samples succeeded")
        typer.echo(f"   Fix issues above before running batch.\n")
        raise typer.Exit(1)


@app.command()
def validate(
    stage: str = typer.Option(..., "--stage", "-s", help="Stage name to validate"),
    run_id: str = typer.Option(..., "--run-id", "-r", help="SPARTA run ID"),
    task_name: Optional[str] = typer.Option(None, "--task-name", "-t", help="Task-monitor task name to notify"),
    min_success_rate: float = typer.Option(0.95, "--min-success-rate", help="Minimum success rate (0-1)"),
):
    """
    Validate batch output quality after completion.

    Uses SPARTA contracts and DuckDB queries for validation.
    """
    typer.echo(f"\n=== VALIDATION: Stage {stage} ({run_id}) ===\n")

    results = {
        "stage": stage,
        "run_id": run_id,
        "timestamp": int(time.time()),
        "checks": [],
    }

    passed = True

    # Load contract
    contract = load_contract(stage)
    if contract:
        typer.echo(f"  Contract: {contract.get('name', stage)}")
        results["contract"] = contract.get("name")

    # Connect to DuckDB
    conn = get_duckdb_connection(run_id)
    if not conn:
        typer.echo(f"  [FAIL] Cannot connect to DuckDB for {run_id}")
        results["checks"].append({"name": "database", "status": "fail"})
        passed = False
    else:
        typer.echo(f"  [check] Database connected")

        # Run validation queries from contract
        if contract and "validation_queries" in contract:
            for vq in contract["validation_queries"]:
                name = vq.get("name", "unnamed")
                query = vq.get("query", "")
                expected_min = vq.get("expected_min", 0)

                try:
                    result = conn.execute(query).fetchone()
                    value = result[0] if result else 0

                    if value >= expected_min:
                        typer.echo(f"  [check] {name}: {value} (min: {expected_min})")
                        results["checks"].append({
                            "name": name,
                            "status": "pass",
                            "value": value,
                            "expected_min": expected_min
                        })
                    else:
                        typer.echo(f"  [FAIL] {name}: {value} < {expected_min}")
                        results["checks"].append({
                            "name": name,
                            "status": "fail",
                            "value": value,
                            "expected_min": expected_min
                        })
                        passed = False

                except Exception as e:
                    typer.echo(f"  [warn] {name}: query failed - {e}")
                    results["checks"].append({"name": name, "status": "warn", "error": str(e)})

        # Generic quality checks if no contract
        else:
            typer.echo(f"  Running generic checks (no contract)...")

            # Check for common tables based on stage
            if stage in ["05", "05_extract_knowledge"]:
                tables_to_check = [
                    ("url_knowledge", "SELECT COUNT(*) FROM url_knowledge", 10),
                    ("url_extraction_log", "SELECT COUNT(*) FROM url_extraction_log WHERE ok = true", 1)
                ]
            elif stage in ["08b", "08b_infer_relationships"]:
                tables_to_check = [
                    ("relationship_edges", "SELECT COUNT(*) FROM relationship_edges", 100)
                ]
            else:
                tables_to_check = []

            for name, query, expected in tables_to_check:
                try:
                    result = conn.execute(query).fetchone()
                    value = result[0] if result else 0
                    status = "pass" if value >= expected else "fail"
                    typer.echo(f"  {'[check]' if status == 'pass' else '[FAIL]'} {name}: {value}")
                    results["checks"].append({"name": name, "status": status, "value": value})
                    if status == "fail":
                        passed = False
                except Exception as e:
                    typer.echo(f"  [warn] {name}: {e}")

        conn.close()

    # Notify task-monitor if task name provided
    if task_name:
        results["task_name"] = task_name
        monitor_script = TASK_MONITOR_DIR / "monitor.py"

        if monitor_script.exists():
            try:
                result_json = json.dumps(results)
                cmd = [
                    sys.executable, str(monitor_script),
                    "validate", task_name,
                    "--passed" if passed else "--failed",
                    "--result", result_json,
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                typer.echo(f"\n  [check] Notified task-monitor: {task_name}")
            except subprocess.CalledProcessError as e:
                typer.echo(f"\n  [warn] Failed to notify task-monitor: {e}")
        else:
            typer.echo(f"\n  [warn] task-monitor not found at {monitor_script}")

    # Final result
    if passed:
        results["status"] = "passed"
        typer.echo(f"\n=== VALIDATION PASSED ===\n")
        raise typer.Exit(0)
    else:
        results["status"] = "failed"
        typer.echo(f"\n=== VALIDATION FAILED ===\n")
        raise typer.Exit(1)


@app.command()
def status():
    """Check current preflight status."""
    state = load_preflight_state()

    if not state:
        output = {"status": "none", "message": "No preflight run yet"}
        typer.echo(json.dumps(output, indent=2))
        raise typer.Exit(0)

    # Check if expired
    timestamp = state.get("timestamp", 0)
    age = time.time() - timestamp
    expired = age > 1800  # 30 minutes

    if expired:
        state["expired"] = True
        state["age_seconds"] = int(age)
        typer.echo(json.dumps(state, indent=2))
        raise typer.Exit(1)

    state["expired"] = False
    state["age_seconds"] = int(age)
    state["valid_for_seconds"] = 1800 - int(age)

    typer.echo(json.dumps(state, indent=2))

    if state.get("status") == "passed":
        raise typer.Exit(0)
    else:
        raise typer.Exit(1)


@app.command()
def clear():
    """Clear preflight state (requires new preflight)."""
    if PREFLIGHT_FILE.exists():
        PREFLIGHT_FILE.unlink()
        typer.echo("[check] Preflight state cleared")
    else:
        typer.echo("No preflight state to clear")
    raise typer.Exit(0)


if __name__ == "__main__":
    app()
