"""F-36 structured safety artifact evaluation CLI command."""
import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import typer
from rich.table import Table

from config import SKILL_DIR, ensure_dirs
from llm import call_llm
from evaluation import load_prompt, load_models_config

from pl_app import app, console


# ---------------------------------------------------------------------------
# Persona-to-context mapping for prompt template
# ---------------------------------------------------------------------------
PERSONA_CONTEXT = {
    "noah_evans": "You are Noah Evans, a formal verification and safety assurance specialist. "
        "You produce rigorous, structured safety artifacts for aerospace systems.",
    "brandon_bailey": "You are Brandon Bailey, a compliance and regulatory specialist. "
        "You ensure safety artifacts meet DO-178C, ARP4754A, and MIL-STD-882E standards.",
    "jennifer_cheung": "You are Jennifer Cheung, a cybersecurity and safety integration specialist. "
        "You analyze safety-security interactions in aerospace control systems.",
    "margaret_chen": "You are Margaret Chen, a document extraction and knowledge engineering specialist. "
        "You produce structured data from unstructured engineering documents.",
}

# ---------------------------------------------------------------------------
# Valid enum sets for structural validation
# ---------------------------------------------------------------------------
VALID_UCA_TYPES = {
    "not-providing", "providing", "too-early", "too-late",
    "stopped-too-soon", "applied-too-long", "out-of-order",
    "wrong-direction",
}

VALID_ASSURANCE_NODE_TYPES = {
    "goal", "strategy", "solution", "context", "assumption", "justification",
}

VALID_ASSURANCE_STATUSES = {
    "supported", "unsupported", "partial", "undeveloped",
}

VALID_PO_STATUSES = {
    "proved", "unproved", "partial", "timeout", "error", "pending",
}

KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# Domain-specific validators
# ---------------------------------------------------------------------------

def _validate_stpa(data: Dict[str, Any]) -> List[str]:
    """Validate STPAControlStructure artifact. Returns list of error strings."""
    errors: List[str] = []

    # Required top-level arrays
    for key in ("controllers", "unsafeActions", "losses", "constraints"):
        if key not in data:
            errors.append(f"missing required array: {key}")
        elif not isinstance(data[key], list):
            errors.append(f"{key} must be an array")

    if errors:
        return errors  # can't validate further without structure

    # Controller IDs must be kebab-case
    controller_ids = set()
    for ctrl in data["controllers"]:
        cid = ctrl.get("id", "")
        controller_ids.add(cid)
        if not KEBAB_CASE_RE.match(cid):
            errors.append(f"controller id '{cid}' is not kebab-case")

    # UCA validation
    for uca in data["unsafeActions"]:
        uca_type = uca.get("type", "")
        if uca_type and uca_type not in VALID_UCA_TYPES:
            errors.append(f"invalid UCA type: '{uca_type}'")

        # controllerIds must reference existing controllers
        for ref in uca.get("controllerIds", []):
            if ref not in controller_ids:
                errors.append(f"UCA references unknown controller: '{ref}'")

    return errors


def _validate_assurance(data: Dict[str, Any]) -> List[str]:
    """Validate AssuranceCaseData artifact. Returns list of error strings."""
    errors: List[str] = []

    if "nodes" not in data:
        errors.append("missing required array: nodes")
    elif not isinstance(data["nodes"], list):
        errors.append("nodes must be an array")

    if "rootId" not in data:
        errors.append("missing required field: rootId")

    if errors:
        return errors

    node_ids = set()
    for node in data["nodes"]:
        nid = node.get("id", "")
        node_ids.add(nid)

        ntype = node.get("type", "")
        if ntype and ntype not in VALID_ASSURANCE_NODE_TYPES:
            errors.append(f"invalid node type: '{ntype}'")

        status = node.get("status", "")
        if status and status not in VALID_ASSURANCE_STATUSES:
            errors.append(f"invalid node status: '{status}'")

    # Children references
    for node in data["nodes"]:
        for child in node.get("children", []):
            if child not in node_ids:
                errors.append(f"node '{node.get('id')}' references unknown child: '{child}'")

    # Root must exist
    root_id = data.get("rootId", "")
    if root_id and root_id not in node_ids:
        errors.append(f"rootId '{root_id}' not found in nodes")

    return errors


def _validate_verification(data: Dict[str, Any]) -> List[str]:
    """Validate VerificationStatusData artifact. Returns list of error strings."""
    errors: List[str] = []

    for key in ("proofObligations", "tools", "coveragePct"):
        if key not in data:
            errors.append(f"missing required field: {key}")

    if errors:
        return errors

    if not isinstance(data["proofObligations"], list):
        errors.append("proofObligations must be an array")
        return errors

    if not isinstance(data["tools"], list):
        errors.append("tools must be an array")
        return errors

    tool_names = {t.get("name", "") if isinstance(t, dict) else str(t) for t in data["tools"]}

    for po in data["proofObligations"]:
        status = po.get("status", "")
        if status and status not in VALID_PO_STATUSES:
            errors.append(f"invalid PO status: '{status}'")

        prover = po.get("prover", "")
        if prover and prover not in tool_names:
            errors.append(f"PO prover '{prover}' not found in tools list")

    return errors


# Domain -> (expected type field value, validator function)
DOMAIN_VALIDATORS: Dict[str, Tuple[str, Any]] = {
    "stpa": ("STPAControlStructure", _validate_stpa),
    "assurance": ("AssuranceCaseData", _validate_assurance),
    "verification": ("VerificationStatusData", _validate_verification),
}


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@app.command("eval-f36")
def eval_f36(
    prompt: str = typer.Option("f36_safety_artifact_v1", "--prompt", "-p"),
    model: str = typer.Option("deepseek", "--model", "-m"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Evaluate F-36 structured safety artifact generation quality."""
    # Disable gateway routing to avoid issues during eval
    os.environ["PROMPT_LAB_USE_GATEWAY"] = "0"

    ensure_dirs()
    models_config = load_models_config()

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    # Load prompt template
    system_prompt, user_template = load_prompt(prompt, SKILL_DIR)

    # Load ground truth
    gt_file = SKILL_DIR / "ground_truth" / "f36_structured_safety.json"
    if not gt_file.exists():
        console.print("[red]Ground truth not found: ground_truth/f36_structured_safety.json[/red]")
        raise typer.Exit(1)

    gt_data = json.loads(gt_file.read_text())
    test_cases = gt_data.get("cases", [])

    if not test_cases:
        console.print("[red]No test cases found in ground truth file[/red]")
        raise typer.Exit(1)

    if cases > 0:
        test_cases = test_cases[:cases]

    console.print(f"[bold]Evaluating F-36 safety artifacts: prompt='{prompt}', model='{model}'[/bold]")
    console.print(f"Test cases: {len(test_cases)}")
    console.print()

    results: List[Dict[str, Any]] = []

    async def run_eval():
        for tc in test_cases:
            case_id = tc["id"]
            domain = tc["domain"]
            input_data = tc["input"]
            persona = input_data.get("persona", "noah_evans")

            context = PERSONA_CONTEXT.get(persona, PERSONA_CONTEXT["noah_evans"])

            # Build user message from template
            user_msg = user_template.format(
                source_text=input_data.get("source_text", ""),
                context=context,
                task=input_data.get("task", ""),
            )

            result: Dict[str, Any] = {
                "case_id": case_id,
                "domain": domain,
                "passed": False,
                "errors": [],
                "latency_ms": 0.0,
            }

            try:
                start = time.perf_counter()
                content, _ = await call_llm(system_prompt, user_msg, model_config)
                result["latency_ms"] = (time.perf_counter() - start) * 1000

                # 1. JSON parseable
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError as je:
                    result["errors"].append(f"JSON parse error: {je}")
                    results.append(result)
                    _print_case_result(case_id, result, verbose)
                    continue

                result["raw_output"] = parsed

                # 2. Correct type field
                if domain not in DOMAIN_VALIDATORS:
                    result["errors"].append(f"unknown domain: '{domain}'")
                    results.append(result)
                    _print_case_result(case_id, result, verbose)
                    continue

                expected_type, validator_fn = DOMAIN_VALIDATORS[domain]
                actual_type = parsed.get("type", "")
                if actual_type != expected_type:
                    result["errors"].append(
                        f"type mismatch: expected '{expected_type}', got '{actual_type}'"
                    )

                # 3. Domain-specific structural validation
                domain_errors = validator_fn(parsed)
                result["errors"].extend(domain_errors)

                result["passed"] = len(result["errors"]) == 0

            except Exception as e:
                result["errors"].append(f"LLM call error: {e}")

            results.append(result)
            _print_case_result(case_id, result, verbose)

    asyncio.run(run_eval())

    # --- Summary ---
    if not results:
        console.print("[red]No results collected[/red]")
        raise typer.Exit(1)

    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count
    pass_rate = passed_count / len(results)

    console.print()
    table = Table(title="F-36 Safety Artifact Eval Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total cases", str(len(results)))
    table.add_row("Passed", str(passed_count))
    table.add_row("Failed", str(failed_count))
    table.add_row("Pass rate", f"{pass_rate:.1%}")
    table.add_row("Avg latency", f"{sum(r['latency_ms'] for r in results) / len(results):.0f}ms")
    console.print(table)

    if pass_rate == 1.0:
        console.print("\n[green]F-36 SAFETY ARTIFACT EVAL PASSED[/green]")
    else:
        console.print(f"\n[red]F-36 SAFETY ARTIFACT EVAL: {failed_count} FAILURES[/red]")

    # --- Save results ---
    results_dir = SKILL_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = results_dir / f"f36_{prompt}_{model}_{ts}.json"

    save_data = {
        "prompt": prompt,
        "model": model,
        "timestamp": ts,
        "pass_rate": pass_rate,
        "total": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "cases": [],
    }
    for r in results:
        case_out = {
            "case_id": r["case_id"],
            "domain": r["domain"],
            "passed": r["passed"],
            "errors": r["errors"],
            "latency_ms": r["latency_ms"],
        }
        if "raw_output" in r:
            case_out["raw_output"] = r["raw_output"]
        save_data["cases"].append(case_out)

    out_file.write_text(json.dumps(save_data, indent=2))
    console.print(f"\nResults saved to: {out_file.relative_to(SKILL_DIR)}")

    if pass_rate < 1.0:
        raise typer.Exit(1)


def _print_case_result(case_id: str, result: Dict[str, Any], verbose: bool) -> None:
    """Print a single case result line."""
    if result["passed"]:
        console.print(f"  [green]PASS[/green] {case_id}")
    else:
        console.print(f"  [red]FAIL[/red] {case_id}")
        if verbose:
            for err in result["errors"]:
                console.print(f"       {err}")
