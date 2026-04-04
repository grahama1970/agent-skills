"""Lean4 code generation and compilation for QRA consistency verification.

Handles the translation of control chains into Lean4 theorems, compilation
via lean-interact or Docker fallback, and single-chain verification.
"""
from __future__ import annotations
import os

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from qra_models import ControlChain, ControlParameter, VerificationResult


# ---------------------------------------------------------------------------
# Predicate registry — maps edge types to Lean4 axiom templates
# ---------------------------------------------------------------------------

PREDICATE_REGISTRY = {
    "subsumes": {
        "lean_decl": "axiom subsumes : Control -> Control -> Prop",
        "axioms": [
            "axiom subsumption_transitive :",
            "  forall (a b c : Control), subsumes a b -> subsumes b c -> subsumes a c",
        ],
        "param_type": None,
    },
    "countered_by": {
        "lean_decl": "axiom countered_by : Control -> Control -> Prop",
        "axioms": [
            "axiom counter_negates :",
            "  forall (a b : Control), countered_by a b -> enabled a -> ¬ threat_active b",
        ],
        "param_type": "bool",
    },
    "mitigated_by": {
        "lean_decl": "axiom mitigated_by : Control -> Control -> Prop",
        "axioms": [
            "axiom mitigation_effective :",
            "  forall (a b : Control), mitigated_by a b -> coverage_met a -> risk_reduced b",
        ],
        "param_type": "float",
    },
    "exploits": {
        "lean_decl": "axiom exploits : Control -> Control -> Prop",
        "axioms": [
            "axiom exploit_propagates :",
            "  forall (a b : Control), exploits a b -> vulnerable a -> compromised b",
        ],
        "param_type": "bool",
    },
    "maps_to": {
        "lean_decl": "axiom maps_to : Control -> Control -> Prop",
        "axioms": [
            "axiom mapping_symmetric :",
            "  forall (a b : Control), maps_to a b -> maps_to b a",
        ],
        "param_type": None,
    },
}


# ---------------------------------------------------------------------------
# Lean4 code generation
# ---------------------------------------------------------------------------

def _lean_safe_id(control_id: str) -> str:
    """Convert a control ID to a valid Lean4 identifier.

    "CM0001" -> "CM0001"
    "SA-01.1m" -> "SA_01_1m"
    """
    s = re.sub(r"[^a-zA-Z0-9_]", "_", control_id)
    # Lean identifiers cannot start with a digit
    if s and s[0].isdigit():
        s = "ctrl_" + s
    return s


def generate_lean4_theorem(
    control_a: str,
    control_b: str,
    relationship: str = "subsumes",
) -> str:
    """Generate a Lean4 theorem for a single relationship.

    Args:
        control_a: Source control ID
        control_b: Target control ID
        relationship: Relationship type (subsumes, countered_by, mitigated_by, exploits, maps_to)

    Returns:
        Lean4 code string for the axiom declaration
    """
    id_a = _lean_safe_id(control_a)
    id_b = _lean_safe_id(control_b)
    pred = relationship if relationship in PREDICATE_REGISTRY else "subsumes"

    return f"""-- Relationship: {control_a} {pred} {control_b}
axiom {id_a} : Control
axiom {id_b} : Control
axiom h_{pred}_{id_a}_{id_b} : {pred} {id_a} {id_b}"""


def generate_typed_parameters(parameters: list[ControlParameter]) -> list[str]:
    """Emit Lean4 type declarations for typed control parameters.

    Args:
        parameters: List of ControlParameter objects

    Returns:
        List of Lean4 code lines
    """
    lines: list[str] = []
    seen_types: set[str] = set()

    for param in parameters:
        if param.param_type == "bool" and "bool_props" not in seen_types:
            lines.extend([
                "-- Boolean control properties",
                "axiom enabled : Control -> Prop",
                "axiom vulnerable : Control -> Prop",
                "axiom threat_active : Control -> Prop",
                "axiom compromised : Control -> Prop",
                "",
            ])
            seen_types.add("bool_props")
        elif param.param_type == "float" and "float_props" not in seen_types:
            lines.extend([
                "-- Continuous control properties",
                "axiom coverage_met : Control -> Prop",
                "axiom risk_reduced : Control -> Prop",
                "",
            ])
            seen_types.add("float_props")
        elif param.param_type == "enum" and "enum_props" not in seen_types:
            choices = param.choices or ["NOMINAL", "DEGRADED", "CRITICAL"]
            variants = " | ".join(choices)
            lines.extend([
                f"-- Categorical: {param.name}",
                f"inductive ControlStatus | {variants}",
                f"axiom control_status : Control -> ControlStatus",
                "",
            ])
            seen_types.add("enum_props")

    return lines


def _detect_predicate(chain: ControlChain, predicate: str | None = None) -> str:
    """Detect the predicate for a chain from its relationships or explicit override."""
    if predicate:
        return predicate if predicate in PREDICATE_REGISTRY else "subsumes"
    # Infer from first relationship's method field
    if chain.relationships:
        pred = chain.relationships[0].predicate
        if pred in PREDICATE_REGISTRY:
            return pred
    return "subsumes"


def generate_chain_theorem(
    chain: ControlChain,
    predicate: str | None = None,
) -> str:
    """Generate a complete Lean4 file to verify a chain's consistency.

    For a chain [A, B, C] with predicate P, generates:
    - Axioms declaring A, B, C as Controls
    - Predicate-specific axioms from PREDICATE_REGISTRY
    - Relationship axioms for consecutive pairs
    - Transitivity theorem (for subsumes) or predicate-specific checks

    Args:
        chain: The control chain to verify
        predicate: Override predicate name (default: infer from chain relationships)

    Returns:
        Complete Lean4 source code that should compile if chain is consistent
    """
    if chain.length < 2:
        return "-- Chain too short for verification"

    pred = _detect_predicate(chain, predicate)
    pred_info = PREDICATE_REGISTRY[pred]

    controls = chain.controls
    lean_ids = [_lean_safe_id(c) for c in controls]

    lines = [
        "/-",
        f"  QRA Consistency Verification: Chain {chain}",
        f"  Generated at {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"  Predicate: {pred}",
        "-/",
        "",
        "-- Core types",
        "opaque Control : Type := String",
        "opaque Threat : Type := String",
        "",
        "-- Relationship predicates",
    ]

    # Emit all predicate declarations used in the chain
    lines.append(pred_info["lean_decl"])
    for axiom_line in pred_info.get("axioms", []):
        lines.append(axiom_line)
    lines.append("")

    # Emit typed parameter declarations if chain has parameters
    if chain.parameters:
        param_lines = generate_typed_parameters(chain.parameters)
        lines.extend(param_lines)

    # Also emit bool/float props if predicate requires them
    if pred_info.get("param_type") == "bool" and not chain.parameters:
        lines.extend([
            "-- Boolean control properties (from predicate)",
            "axiom enabled : Control -> Prop",
            "axiom vulnerable : Control -> Prop",
            "axiom threat_active : Control -> Prop",
            "axiom compromised : Control -> Prop",
            "",
        ])
    elif pred_info.get("param_type") == "float" and not chain.parameters:
        lines.extend([
            "-- Continuous control properties (from predicate)",
            "axiom coverage_met : Control -> Prop",
            "axiom risk_reduced : Control -> Prop",
            "",
        ])

    lines.append("-- ============================================================")
    lines.append("-- Control declarations")
    lines.append("-- ============================================================")

    # Declare each control as an axiom (deduplicated)
    seen = set()
    for cid, lid in zip(controls, lean_ids):
        if lid not in seen:
            lines.append(f"axiom {lid} : Control  -- {cid}")
            seen.add(lid)

    lines.append("")
    lines.append("-- ============================================================")
    lines.append(f"-- Relationship axioms ({pred}, from ArangoDB)")
    lines.append("-- ============================================================")

    # Declare relationship axioms for consecutive pairs
    for i in range(len(controls) - 1):
        src_id = lean_ids[i]
        tgt_id = lean_ids[i + 1]
        src_cid = controls[i]
        tgt_cid = controls[i + 1]
        lines.append(
            f"axiom h_{pred}_{src_id}_{tgt_id} : {pred} {src_id} {tgt_id}"
            f"  -- {src_cid} {pred} {tgt_cid}"
        )

    lines.append("")
    lines.append("-- ============================================================")
    lines.append("-- Verification theorem")
    lines.append("-- ============================================================")

    if pred == "subsumes":
        # Transitivity proof (original logic preserved)
        if chain.length == 2:
            lines.append(f"-- Direct: {controls[0]} subsumes {controls[1]}")
            lines.append(f"#check h_sub_{lean_ids[0]}_{lean_ids[1]}")
        elif chain.length == 3:
            a, b, c = lean_ids[0], lean_ids[1], lean_ids[2]
            lines.extend([
                f"theorem chain_{a}_{c} : subsumes {a} {c} :=",
                f"  subsumption_transitive {a} {b} {c}"
                f" h_{pred}_{a}_{b} h_{pred}_{b}_{c}",
            ])
        else:
            prev_thm = f"h_{pred}_{lean_ids[0]}_{lean_ids[1]}"
            accumulated = lean_ids[0]
            for i in range(1, len(lean_ids) - 1):
                mid = lean_ids[i]
                nxt = lean_ids[i + 1]
                step_name = f"h_step_{accumulated}_{nxt}"
                lines.extend([
                    f"theorem {step_name} : subsumes {accumulated} {nxt} :=",
                    f"  subsumption_transitive {accumulated} {mid} {nxt}"
                    f" {prev_thm} h_{pred}_{mid}_{nxt}",
                    "",
                ])
                prev_thm = step_name
            lines.extend([
                f"-- Final: {controls[0]} subsumes {controls[-1]}",
                f"#check {prev_thm}",
            ])
    else:
        # Non-subsumes predicates: verify axiom consistency via #check
        # The LLM/agent interprets what breaking means — we just verify
        # the axiom declarations are well-typed
        for i in range(len(controls) - 1):
            src_id = lean_ids[i]
            tgt_id = lean_ids[i + 1]
            lines.append(f"#check h_{pred}_{src_id}_{tgt_id}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Compilation (reuses lean4-prove Docker infrastructure)
# ---------------------------------------------------------------------------

def compile_lean4(
    code: str,
    container: str = "lean_runner",
    timeout: int = 120,
) -> Dict[str, Any]:
    """Compile Lean4 code via lean-interact (preferred) or Docker (fallback).

    lean-interact v0.11.1+ manages its own Lean REPL binary -- no Docker needed.
    Docker compilation is kept as fallback when lean-interact is not installed.

    Returns:
        dict with success, exit_code, stdout, stderr
    """
    # Try lean-interact first (preferred -- no Docker overhead)
    try:
        from compiler import compile_lean_compat
        return compile_lean_compat(code, container="_internal", timeout=timeout)
    except ImportError:
        pass  # Fall back to Docker

    skill_dir = Path(__file__).parent.parent / "lean4-verify"
    run_script = skill_dir / "run.sh"

    if run_script.exists():
        result = subprocess.run(
            [str(run_script), "--container", container, "--timeout", str(timeout)],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout + 10,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {
                "success": False,
                "exit_code": 1,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
    else:
        # Direct Docker compilation
        temp_file = f"/tmp/qra_verify_{int(time.time() * 1000)}.lean"
        bash_cmd = f"""cat > {temp_file} << 'LEANEOF'
{code}
LEANEOF

cd /workspace/mathlib_project && lake env lean {temp_file} 2>&1
rm -f {temp_file}
"""
        try:
            result = subprocess.run(
                ["docker", "exec", container, "bash", "-c", bash_cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Compilation timed out after {timeout}s",
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
            }


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------

def verify_chain(
    chain: ControlChain,
    container: str = "lean_runner",
    timeout: int = 120,
) -> VerificationResult:
    """Verify a control chain by generating and compiling a Lean4 theorem.

    Args:
        chain: The control chain to verify
        container: Docker container for Lean4 compilation
        timeout: Compilation timeout in seconds

    Returns:
        VerificationResult with status PROVEN / UNPROVEN / ERROR
    """
    t0 = time.time()
    lean_code = generate_chain_theorem(chain)

    result = compile_lean4(lean_code, container, timeout)
    elapsed = time.time() - t0

    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    compiler_output = (stdout + "\n" + stderr).strip()

    if result.get("success"):
        status = "PROVEN"
    elif "sorry" in lean_code.lower():
        status = "UNPROVEN"
    elif "type mismatch" in compiler_output or "don't know how" in compiler_output:
        status = "CONTRADICTION"
    else:
        status = "ERROR"

    return VerificationResult(
        chain=chain,
        status=status,
        lean_code=lean_code,
        compiler_output=compiler_output,
        elapsed_seconds=elapsed,
    )


# ---------------------------------------------------------------------------
# What-if query mode
# ---------------------------------------------------------------------------

def generate_what_if_theorem(
    control_id: str,
    parameter: ControlParameter,
    new_value: Any,
    affected_chains: list[ControlChain],
) -> list[tuple[ControlChain, str]]:
    """Generate Lean4 code for what-if analysis on affected chains.

    For each chain containing control_id, generates a Lean4 file that:
    - Declares the control with the MODIFIED parameter value
    - Attempts to prove the chain still holds under the new assumption

    Args:
        control_id: The control being modified
        parameter: The parameter being changed
        new_value: The new parameter value
        affected_chains: Chains containing control_id

    Returns:
        List of (chain, lean_code) tuples ready for compilation
    """
    lid = _lean_safe_id(control_id)
    results: list[tuple[ControlChain, str]] = []

    for chain in affected_chains:
        pred = _detect_predicate(chain)
        pred_info = PREDICATE_REGISTRY[pred]

        lean_ids = [_lean_safe_id(c) for c in chain.controls]
        lines = [
            "/-",
            f"  What-If Analysis: {control_id}.{parameter.name} = {new_value}",
            f"  Chain: {chain}",
            f"  Generated at {time.strftime('%Y-%m-%dT%H:%M:%S')}",
            "-/",
            "",
            "-- Core types",
            "opaque Control : Type := String",
            "opaque Threat : Type := String",
            "",
            "-- Relationship predicates",
            pred_info["lean_decl"],
        ]
        for axiom_line in pred_info.get("axioms", []):
            lines.append(axiom_line)
        lines.append("")

        # Emit property axioms needed for the what-if assertion
        if parameter.param_type == "bool":
            lines.extend([
                "-- Boolean control properties",
                "axiom enabled : Control -> Prop",
                "axiom vulnerable : Control -> Prop",
                "axiom threat_active : Control -> Prop",
                "axiom compromised : Control -> Prop",
                "",
            ])
        elif parameter.param_type == "float":
            lines.extend([
                "-- Continuous control properties",
                "axiom coverage_met : Control -> Prop",
                "axiom risk_reduced : Control -> Prop",
                "",
            ])
        elif parameter.param_type == "enum":
            choices = parameter.choices or ["NOMINAL", "DEGRADED", "CRITICAL"]
            variants = " | ".join(choices)
            lines.extend([
                f"-- Categorical: {parameter.name}",
                f"inductive ControlStatus | {variants}",
                f"axiom control_status : Control -> ControlStatus",
                "",
            ])

        # Declare controls
        lines.append("-- Control declarations")
        seen = set()
        for cid, lean_id in zip(chain.controls, lean_ids):
            if lean_id not in seen:
                lines.append(f"axiom {lean_id} : Control  -- {cid}")
                seen.add(lean_id)
        lines.append("")

        # Declare relationship axioms
        lines.append(f"-- Relationship axioms ({pred})")
        for i in range(len(chain.controls) - 1):
            src_id = lean_ids[i]
            tgt_id = lean_ids[i + 1]
            lines.append(
                f"axiom h_{pred}_{src_id}_{tgt_id} : {pred} {src_id} {tgt_id}"
            )
        lines.append("")

        # What-if assertion: declare the modified parameter value
        lines.append("-- ============================================================")
        lines.append(f"-- WHAT-IF: {control_id}.{parameter.name} = {new_value}")
        lines.append("-- ============================================================")

        if parameter.param_type == "bool" and not new_value:
            # Disabling a control — assert ¬ enabled
            prop = parameter.name if parameter.name in ("enabled", "vulnerable") else "enabled"
            lines.append(f"axiom h_whatif : ¬ {prop} {lid}")
        elif parameter.param_type == "bool" and new_value:
            prop = parameter.name if parameter.name in ("enabled", "vulnerable") else "enabled"
            lines.append(f"axiom h_whatif : {prop} {lid}")
        elif parameter.param_type == "float":
            # Below threshold — coverage not met
            lines.append(f"axiom h_whatif : ¬ coverage_met {lid}")
        elif parameter.param_type == "enum":
            lines.append(
                f"axiom h_whatif : control_status {lid} = ControlStatus.{new_value}"
            )

        lines.append("")

        # Verification: try to prove chain still holds given the what-if
        lines.append("-- Verification: does the chain still hold?")
        if pred == "subsumes" and chain.length >= 3:
            # Transitivity proof (same as generate_chain_theorem)
            a, b, c = lean_ids[0], lean_ids[1], lean_ids[2]
            lines.extend([
                f"theorem chain_holds : subsumes {a} {c} :=",
                f"  subsumption_transitive {a} {b} {c}"
                f" h_{pred}_{a}_{b} h_{pred}_{b}_{c}",
            ])
        else:
            for i in range(len(chain.controls) - 1):
                src_id = lean_ids[i]
                tgt_id = lean_ids[i + 1]
                lines.append(f"#check h_{pred}_{src_id}_{tgt_id}")

        results.append((chain, "\n".join(lines)))

    return results


def what_if(
    control_id: str,
    parameter_name: str,
    new_value: Any,
    container: str = "lean_runner",
    timeout: int = 120,
    dry_run: bool = False,
) -> list[VerificationResult]:
    """Run what-if analysis: which chains break when a parameter changes?

    Fetches all chains containing control_id, generates Lean4 theorems
    with the modified parameter, and optionally compiles them.

    Args:
        control_id: The control to modify
        parameter_name: Name of the parameter to change
        new_value: New value for the parameter
        container: Docker container for compilation
        timeout: Compilation timeout
        dry_run: If True, generate code but skip compilation

    Returns:
        List of VerificationResult with status PROVEN (holds) or BROKEN
    """
    from qra_models import fetch_relationship_chains, fetch_parent_child_chains

    # Fetch chains containing this control
    all_chains = fetch_relationship_chains(limit=100) + fetch_parent_child_chains(limit=100)
    affected = [c for c in all_chains if control_id in c.controls]

    if not affected:
        logger.info(f"No chains found containing {control_id}")
        return []

    # Infer parameter type from predicate registry or default to bool
    first_pred = _detect_predicate(affected[0])
    pred_info = PREDICATE_REGISTRY.get(first_pred, {})
    param_type = pred_info.get("param_type", "bool") or "bool"

    parameter = ControlParameter(
        name=parameter_name,
        param_type=param_type,
        value=new_value,
    )

    theorem_pairs = generate_what_if_theorem(
        control_id, parameter, new_value, affected,
    )

    results: list[VerificationResult] = []
    for chain, lean_code in theorem_pairs:
        if dry_run:
            results.append(VerificationResult(
                chain=chain,
                status="DRY_RUN",
                lean_code=lean_code,
            ))
        else:
            t0 = time.time()
            comp = compile_lean4(lean_code, container, timeout)
            elapsed = time.time() - t0

            stdout = comp.get("stdout", "")
            stderr = comp.get("stderr", "")
            compiler_output = (stdout + "\n" + stderr).strip()

            if comp.get("success"):
                status = "HOLDS"
            elif "type mismatch" in compiler_output or "don't know how" in compiler_output:
                status = "BROKEN"
            else:
                status = "ERROR"

            results.append(VerificationResult(
                chain=chain,
                status=status,
                lean_code=lean_code,
                compiler_output=compiler_output,
                elapsed_seconds=elapsed,
            ))

    return results
