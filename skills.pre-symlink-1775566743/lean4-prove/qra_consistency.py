#!/usr/bin/env python3
"""
qra_consistency: Translate QRA control relationships from ArangoDB into Lean4
theorems and verify them via the lean4-prove compilation pipeline.

Phase 1 focuses on subsumption transitivity:
  If control A subsumes B and B subsumes C, then A subsumes C.

This catches fabricated frameworks (e.g., "Orion Protocol") that break
transitivity in the SPARTA dataset (8.3% teacher-student agreement).

Usage:
    python qra_consistency.py verify --scope sparta --limit 10
    python qra_consistency.py generate --scope sparta --limit 5
    python qra_consistency.py list-chains --scope sparta

Module layout (split for maintainability):
    qra_models.py    - Data structures and ArangoDB query functions
    qra_codegen.py   - Lean4 theorem generation, compilation, chain verification
    qra_reasoning.py - Gate 6 per-step reasoning chain verification
    qra_consistency.py - CLI commands and public re-exports (this file)
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List

import typer
from loguru import logger

# Re-export public API so existing `from qra_consistency import X` keeps working
from qra_models import (  # noqa: F401
    MEMORY_RUN,
    ControlChain,
    ControlRelationship,
    ERROR_TAXONOMY,
    ReasoningStepResult,
    ReasoningVerifyResult,
    VerificationResult,
    _memory_cmd,
    fetch_control_relationships,
    fetch_parent_child_chains,
    fetch_relationship_chains,
)
from qra_codegen import (  # noqa: F401
    PREDICATE_REGISTRY,
    compile_lean4,
    generate_chain_theorem,
    generate_lean4_theorem,
    generate_what_if_theorem,
    verify_chain,
    what_if,
)
from qra_models import ControlParameter  # noqa: F401
from qra_reasoning import (  # noqa: F401
    verify_qra_reasoning,
)

app = typer.Typer(help="QRA control consistency verification via Lean4 proofs")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@app.command()
def verify(
    scope: str = typer.Option("sparta", help="Dataset scope"),
    limit: int = typer.Option(10, help="Max chains to verify"),
    container: str = typer.Option("lean_runner", help="Docker container"),
    timeout: int = typer.Option(120, help="Compile timeout per chain"),
    source: str = typer.Option(
        "hierarchy",
        help="Chain source: 'hierarchy' (parent_id) or 'relationships' (sparta_relationships)",
    ),
    output_format: str = typer.Option("text", help="Output format: text or json"),
):
    """Verify QRA control chains for subsumption transitivity."""
    import subprocess

    # Fetch chains via /memory
    if source == "hierarchy":
        chains = fetch_parent_child_chains(limit=limit)
    else:
        chains = fetch_relationship_chains(limit=limit)

    if not chains:
        print(json.dumps({"error": "No chains found", "scope": scope, "source": source}))
        raise typer.Exit(1)

    # Check Docker container
    try:
        ps = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True,
        )
        if container not in ps.stdout:
            print(json.dumps({
                "error": f"Container '{container}' not running",
                "hint": "Start it with: docker start lean_runner",
            }))
            raise typer.Exit(1)
    except FileNotFoundError:
        print(json.dumps({"error": "Docker not found"}))
        raise typer.Exit(1)

    # Verify each chain
    results: List[VerificationResult] = []
    for i, chain in enumerate(chains):
        if output_format == "text":
            print(f"\n[{i+1}/{len(chains)}] Verifying: {chain}")

        vr = verify_chain(chain, container, timeout)
        results.append(vr)

        if output_format == "text":
            symbol = {"PROVEN": "+", "UNPROVEN": "?", "CONTRADICTION": "!", "ERROR": "X"}
            print(f"  [{symbol.get(vr.status, '?')}] {vr.status} ({vr.elapsed_seconds:.1f}s)")
            if vr.status not in ("PROVEN",) and vr.compiler_output:
                for line in vr.compiler_output.split("\n")[:3]:
                    print(f"      {line.strip()}")

    # Summary
    proven = sum(1 for r in results if r.status == "PROVEN")
    unproven = sum(1 for r in results if r.status == "UNPROVEN")
    contradiction = sum(1 for r in results if r.status == "CONTRADICTION")
    errors = sum(1 for r in results if r.status == "ERROR")

    summary = {
        "scope": scope,
        "source": source,
        "total_chains": len(results),
        "proven": proven,
        "unproven": unproven,
        "contradiction": contradiction,
        "errors": errors,
        "pass_rate": f"{proven / len(results) * 100:.1f}%" if results else "0%",
    }

    if output_format == "json":
        output = {
            "summary": summary,
            "chains": [
                {
                    "chain": str(r.chain),
                    "controls": r.chain.controls,
                    "status": r.status,
                    "elapsed_seconds": r.elapsed_seconds,
                    "lean_code": r.lean_code,
                    "compiler_output": r.compiler_output[:500] if r.compiler_output else "",
                }
                for r in results
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"QRA Consistency Verification Summary")
        print(f"{'='*60}")
        print(f"  Scope:          {scope}")
        print(f"  Source:          {source}")
        print(f"  Total chains:   {len(results)}")
        print(f"  PROVEN:         {proven}")
        print(f"  UNPROVEN:       {unproven}")
        print(f"  CONTRADICTION:  {contradiction}")
        print(f"  ERRORS:         {errors}")
        print(f"  Pass rate:      {summary['pass_rate']}")

    # Exit with failure if any contradictions
    if contradiction > 0:
        raise typer.Exit(2)
    elif errors > 0:
        raise typer.Exit(1)


@app.command()
def generate(
    scope: str = typer.Option("sparta", help="Dataset scope"),
    limit: int = typer.Option(5, help="Max chains to generate theorems for"),
    source: str = typer.Option(
        "hierarchy",
        help="Chain source: 'hierarchy' or 'relationships'",
    ),
):
    """Generate Lean4 theorems without compiling (dry run)."""
    if source == "hierarchy":
        chains = fetch_parent_child_chains(limit=limit)
    else:
        chains = fetch_relationship_chains(limit=limit)

    if not chains:
        logger.error(f"No chains found for scope={scope} source={source}")
        raise typer.Exit(1)

    for i, chain in enumerate(chains):
        print(f"\n{'='*60}")
        print(f"-- Chain {i+1}: {chain}")
        print(f"{'='*60}")
        code = generate_chain_theorem(chain)
        print(code)


@app.command("list-chains")
def list_chains(
    scope: str = typer.Option("sparta", help="Dataset scope"),
    limit: int = typer.Option(20, help="Max chains to list"),
    source: str = typer.Option(
        "hierarchy",
        help="Chain source: 'hierarchy' or 'relationships'",
    ),
):
    """List available control chains without generating theorems."""
    if source == "hierarchy":
        chains = fetch_parent_child_chains(limit=limit)
    else:
        chains = fetch_relationship_chains(limit=limit)

    if not chains:
        print(f"No chains found for scope={scope} source={source}")
        raise typer.Exit(0)

    print(f"Found {len(chains)} chains (source={source}):\n")
    for i, chain in enumerate(chains):
        print(f"  {i+1:3d}. {chain}  ({chain.length} controls)")


@app.command("verify-reasoning")
def verify_reasoning_cmd(
    scope: str = typer.Option("sparta", help="Dataset scope"),
    limit: int = typer.Option(10, help="Max QRAs to verify"),
    container: str = typer.Option("lean_runner", help="Docker container (deprecated)"),
    timeout: int = typer.Option(120, help="Per-step timeout"),
    output_format: str = typer.Option("text", help="Output format: text or json"),
):
    """Verify per-step reasoning chains in QRA answers."""
    # Fetch QRAs via /memory
    try:
        raw = _memory_cmd([
            "recall", "--q", f"reasoning:* scope:{scope}",
            "--collections", "sparta_qra",
        ], timeout=30)

        if not isinstance(raw, list):
            raw = raw.get("results", [])
    except (RuntimeError, json.JSONDecodeError) as e:
        print(json.dumps({"error": f"Failed to fetch QRAs: {e}"}))
        raise typer.Exit(1)

    if not raw:
        print(json.dumps({"error": "No QRAs found"}))
        raise typer.Exit(1)

    qras = raw[:limit]
    all_results = []

    for i, qra in enumerate(qras):
        if output_format == "text":
            qid = qra.get("_key", qra.get("qra_id", "?"))
            print(f"\n[{i+1}/{len(qras)}] Verifying reasoning for QRA {qid}...")

        vr = verify_qra_reasoning(qra, container, timeout)
        all_results.append(vr)

        if output_format == "text":
            print(f"  Steps: {vr.steps_total} total, {vr.steps_verified} verified, {vr.steps_failed} failed")
            if vr.error_taxonomy:
                print(f"  Errors: {dict(vr.error_taxonomy)}")

    # Summary
    total_steps = sum(r.steps_total for r in all_results)
    verified_steps = sum(r.steps_verified for r in all_results)
    failed_steps = sum(r.steps_failed for r in all_results)

    # Aggregate error taxonomy
    agg_taxonomy: Dict[str, int] = {}
    for r in all_results:
        for err_type, count in r.error_taxonomy.items():
            agg_taxonomy[err_type] = agg_taxonomy.get(err_type, 0) + count

    summary = {
        "qras_checked": len(all_results),
        "total_steps": total_steps,
        "verified_steps": verified_steps,
        "failed_steps": failed_steps,
        "verify_rate": f"{verified_steps / total_steps * 100:.1f}%" if total_steps > 0 else "0%",
        "error_taxonomy": agg_taxonomy,
    }

    if output_format == "json":
        print(json.dumps({
            "summary": summary,
            "results": [
                {
                    "qra_id": r.qra_id,
                    "steps_total": r.steps_total,
                    "steps_verified": r.steps_verified,
                    "steps_failed": r.steps_failed,
                    "error_taxonomy": r.error_taxonomy,
                }
                for r in all_results
            ],
        }, indent=2))
    else:
        print(f"\n{'='*60}")
        print("QRA Reasoning Verification Summary")
        print(f"{'='*60}")
        print(f"  QRAs checked:   {len(all_results)}")
        print(f"  Total steps:    {total_steps}")
        print(f"  Verified:       {verified_steps}")
        print(f"  Failed:         {failed_steps}")
        print(f"  Verify rate:    {summary['verify_rate']}")
        if agg_taxonomy:
            print(f"  Error taxonomy:")
            for err_type, count in sorted(agg_taxonomy.items(), key=lambda x: -x[1]):
                print(f"    {err_type}: {count}")


@app.command("what-if")
def what_if_cmd(
    control: str = typer.Option(..., help="Control ID to modify"),
    param: str = typer.Option(..., help="Parameter name to change"),
    value: str = typer.Option(..., help="New value (true/false for bool, number for float, string for enum)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate Lean4 without compiling"),
    container: str = typer.Option("lean_runner", help="Docker container"),
    timeout: int = typer.Option(120, help="Compile timeout per chain"),
    output_format: str = typer.Option("text", help="Output format: text or json"),
):
    """What-if analysis: which chains break when a parameter changes?"""
    # Parse value based on common types
    parsed_value: object
    if value.lower() in ("true", "1", "yes"):
        parsed_value = True
    elif value.lower() in ("false", "0", "no"):
        parsed_value = False
    else:
        try:
            parsed_value = float(value)
        except ValueError:
            parsed_value = value  # enum string

    results = what_if(
        control_id=control,
        parameter_name=param,
        new_value=parsed_value,
        container=container,
        timeout=timeout,
        dry_run=dry_run,
    )

    if not results:
        msg = {"error": f"No chains found containing {control}"}
        if output_format == "json":
            print(json.dumps(msg, indent=2))
        else:
            print(f"No chains found containing {control}")
        raise typer.Exit(1)

    broken = sum(1 for r in results if r.status == "BROKEN")
    held = sum(1 for r in results if r.status in ("HOLDS", "PROVEN"))
    dry = sum(1 for r in results if r.status == "DRY_RUN")

    if output_format == "json":
        output = {
            "control": control,
            "parameter": param,
            "new_value": parsed_value,
            "affected_chains": [
                {
                    "chain": str(r.chain),
                    "controls": r.chain.controls,
                    "predicate": r.chain.relationships[0].predicate if r.chain.relationships else "subsumes",
                    "status": r.status,
                    "lean_code": r.lean_code if dry_run else "",
                    "compiler_output": r.compiler_output[:500] if r.compiler_output else "",
                }
                for r in results
            ],
            "summary": {
                "total": len(results),
                "broken": broken,
                "held": held,
                "dry_run": dry,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\nWhat-If Analysis: {control}.{param} = {parsed_value}")
        print(f"{'='*60}")
        for i, r in enumerate(results):
            symbol = {"HOLDS": "+", "BROKEN": "!", "DRY_RUN": "~", "ERROR": "X"}.get(r.status, "?")
            print(f"  [{symbol}] {r.status}: {r.chain}")
            if dry_run and r.lean_code:
                # Show first few lines of generated code
                for line in r.lean_code.split("\n")[:5]:
                    print(f"      {line}")
                print(f"      ... ({len(r.lean_code.split(chr(10)))} lines)")

        print(f"\nSummary: {len(results)} chains, {broken} broken, {held} held")
        if dry:
            print(f"  ({dry} dry-run — use without --dry-run to compile)")


if __name__ == "__main__":
    app()
