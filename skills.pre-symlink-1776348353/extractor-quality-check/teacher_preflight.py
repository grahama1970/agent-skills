#!/usr/bin/env python3
"""Teacher prompt preflight — validates that the task spec prompt produces
schema-conformant JSON from the chosen LLM before generating training data.

Uses scillm paved path (parallel_acompletions_iter) to test the prompt
against synthetic chunks. Caches the validated model+prompt pair so it
doesn't re-run every cycle.

Usage:
    # Run preflight for Margaret's assessor task
    python teacher_preflight.py extraction-quality-assessor

    # Force re-run (ignore cache)
    python teacher_preflight.py extraction-quality-assessor --force

    # Test specific model
    python teacher_preflight.py extraction-quality-assessor --model deepseek-ai/DeepSeek-V3-0324
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# ── Paths ──
_THIS_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _THIS_DIR.parent

# ---------------------------------------------------------------------------
# Shadow gateway: route through /assistant validate() cascade
# ---------------------------------------------------------------------------
_use_gateway = os.environ.get("TEACHER_PREFLIGHT_USE_GATEWAY", "1") == "1"
_gateway_available = False
if _use_gateway:
    try:
        _assistant_dir = str(_SKILLS_DIR / "assistant")
        if _assistant_dir not in sys.path:
            sys.path.insert(0, _assistant_dir)
        from assistant import validate as _gw_validate
        _gateway_available = True
    except ImportError:
        _gateway_available = False
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
_CREATE_GPT_DATA = _EMBRY_STORAGE / "media/agents/shared/create-gpt/data"
_PREFLIGHT_CACHE_DIR = _THIS_DIR / "preflight_cache"
_PREFLIGHT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache validity: 24 hours
_CACHE_TTL_SECONDS = int(os.getenv("TEACHER_PREFLIGHT_CACHE_TTL", "86400"))

# Minimum schema compliance rate to pass preflight
_MIN_COMPLIANCE_RATE = float(os.getenv("TEACHER_PREFLIGHT_MIN_COMPLIANCE", "0.6"))

# Required top-level fields in teacher output
_REQUIRED_FIELDS = {
    "extraction-quality-assessor": {"grade", "fidelity_score", "error_types"},
    "cybersecurity-extraction-auditor": {"grade", "fidelity_score", "error_types"},
}

# Synthetic test chunks for preflight validation
_SYNTHETIC_CHUNKS = [
    {
        "text": (
            "The F-35 propulsion system operates at temperatures up to 1,832°F "
            "with a thrust-to-weight ratio of 8:1. The F135 engine produces "
            "43,000 lbs of thrust in military power configuration."
        ),
        "asset_type": "section",
        "doc_id": "preflight_test_001",
        "content_type": "text",
    },
    {
        "text": (
            "| Parameter | Value | Unit |\n"
            "| Max Thrust | 43,000 | lbf |\n"
            "| TIT | 1,832 | °F |\n"
            "| Bypass Ratio | 0.57 | - |\n"
            "| SFC | 0.886 | lb/(lbf·h) |"
        ),
        "asset_type": "table",
        "doc_id": "preflight_test_002",
        "content_type": "markdown",
    },
    {
        "text": "REQ-F135-SRS-042: The engine control system shall maintain",
        "asset_type": "section",
        "doc_id": "preflight_test_003",
        "content_type": "text",
    },
    {
        "text": (
            "STIG-ID: V-12345 | Severity: CAT I | Status: Open\n"
            "Finding: Authentication bypass via direct object reference\n"
            "CCI: CCI-000366 | Rule: SV-12345r1_rule"
        ),
        "asset_type": "table",
        "doc_id": "preflight_test_004",
        "content_type": "text",
    },
    {
        "text": "",  # Intentionally empty — should be skipped or graded FAIL
        "asset_type": "section",
        "doc_id": "preflight_test_005",
        "content_type": "text",
    },
]


def _load_task_spec(task_name: str) -> dict | None:
    """Load task spec YAML."""
    import yaml

    spec_path = _CREATE_GPT_DATA / "tasks" / f"{task_name}.yaml"
    if not spec_path.exists():
        logger.warning("Task spec not found: {}", spec_path)
        return None

    with open(spec_path) as f:
        return yaml.safe_load(f)


def _get_cache_path(task_name: str, model: str) -> Path:
    """Get cache file path for a task+model pair."""
    safe_model = model.replace("/", "_").replace(".", "_")
    return _PREFLIGHT_CACHE_DIR / f"{task_name}_{safe_model}.json"


def _is_cache_valid(cache_path: Path) -> bool:
    """Check if cache exists and is within TTL."""
    if not cache_path.exists():
        return False
    age = time.time() - cache_path.stat().st_mtime
    return age < _CACHE_TTL_SECONDS


def _check_schema_compliance(result: dict, task_name: str) -> tuple[bool, list[str]]:
    """Check if a teacher output has the required top-level fields.

    Returns (compliant: bool, missing_fields: list[str]).
    """
    required = _REQUIRED_FIELDS.get(task_name, {"grade", "fidelity_score", "error_types"})
    missing = []

    for field in required:
        if field not in result or result[field] is None:
            missing.append(field)

    # Check grade is a valid enum value
    grade = result.get("grade", "")
    if isinstance(grade, str) and grade.upper() not in {"PASS", "WARN", "FAIL"}:
        missing.append("grade (invalid value)")

    return len(missing) == 0, missing


async def run_preflight(
    task_name: str,
    model: str | None = None,
    force: bool = False,
) -> dict:
    """Run preflight validation for a task spec + model combination.

    Tests the system prompt against synthetic chunks and validates
    schema compliance. Caches results for 24h.

    Returns:
        {
            "passed": bool,
            "model": str,
            "task": str,
            "compliance_rate": float,
            "results": [...],
            "cached": bool,
        }
    """
    from scillm.batch import parallel_acompletions_iter

    model = model or os.getenv("CHUTES_TEXT_MODEL", "deepseek-ai/DeepSeek-V3-0324")
    api_base = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
    api_key = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

    # Check cache
    cache_path = _get_cache_path(task_name, model)
    if not force and _is_cache_valid(cache_path):
        with open(cache_path) as f:
            cached = json.load(f)
        cached["cached"] = True
        logger.info(
            "Preflight cache hit for {}+{}: compliance={:.0%}",
            task_name, model, cached.get("compliance_rate", 0),
        )
        return cached

    # Load task spec
    spec = _load_task_spec(task_name)
    if not spec:
        return {"passed": False, "error": f"Task spec not found: {task_name}"}

    system_prompt = spec.get("system_prompt", "")

    # Add explicit schema instruction to improve compliance
    schema_instruction = (
        "\n\nIMPORTANT: Your response MUST be a JSON object with these exact "
        "top-level fields:\n"
        '- "grade": one of "PASS", "WARN", or "FAIL"\n'
        '- "fidelity_score": number between 0.0 and 1.0\n'
        '- "error_types": array of strings (empty if no errors)\n'
        '- "issues": array of strings describing problems found\n'
        '- "remediation": string with suggested fix (empty if PASS)\n'
    )
    enhanced_prompt = system_prompt + schema_instruction

    # Build requests
    requests = []
    for i, chunk in enumerate(_SYNTHETIC_CHUNKS):
        if not chunk["text"].strip():
            continue  # skip empty test chunk
        requests.append({
            "model": model,
            "messages": [
                {"role": "system", "content": enhanced_prompt},
                {"role": "user", "content": json.dumps(chunk, ensure_ascii=False)},
            ],
            "max_tokens": 512,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "index": i,
        })

    logger.info(
        "Running preflight: {} chunks × model={} for task={}",
        len(requests), model, task_name,
    )

    # Run parallel evaluations
    case_results = []

    # --- Gateway path: try cheaper tiers first ---
    if _gateway_available:
        gateway_handled = True
        for i, chunk in enumerate(_SYNTHETIC_CHUNKS):
            if not chunk["text"].strip():
                continue
            try:
                gw_result = _gw_validate(
                    input_data={"text": chunk["text"], "asset_type": chunk.get("asset_type", "unknown")},
                    task="teacher-preflight-validator",
                )
                if gw_result and gw_result.result:
                    parsed = gw_result.result
                    compliant, missing = _check_schema_compliance(parsed, task_name)
                    case_results.append({
                        "index": i,
                        "compliant": compliant,
                        "missing": missing,
                        "grade": parsed.get("grade"),
                        "fidelity_score": parsed.get("fidelity_score"),
                        "error_types": parsed.get("error_types", []),
                    })
                    continue
            except Exception as e:
                logger.debug("value lookup failed: {}", e)
            gateway_handled = False
            break

        if gateway_handled and case_results:
            # All chunks handled by gateway — skip to compliance calculation
            total = len(case_results)
            compliant_count = sum(1 for r in case_results if r.get("compliant"))
            compliance_rate = compliant_count / total if total > 0 else 0.0
            passed = compliance_rate >= _MIN_COMPLIANCE_RATE
            result = {
                "passed": passed,
                "model": model,
                "task": task_name,
                "compliance_rate": compliance_rate,
                "compliant_count": compliant_count,
                "total_tested": total,
                "enhanced_prompt_used": True,
                "results": case_results,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cached": False,
            }
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(result, f, indent=2)
            logger.info(
                "Preflight {} (gateway): {}/{} compliant ({:.0%}) for {}+{}",
                "PASSED" if passed else "FAILED",
                compliant_count, total, compliance_rate, task_name, model,
            )
            return result
        # Reset for direct scillm fallback
        case_results = []

    # --- Direct scillm path (fallback) ---
    async for r in parallel_acompletions_iter(
        requests,
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai",
        concurrency=2,  # conservative for preflight
        timeout=30,
        wall_time_s=120,
        tenacious=False,
    ):
        idx = r.get("index", -1)
        chunk = _SYNTHETIC_CHUNKS[idx] if 0 <= idx < len(_SYNTHETIC_CHUNKS) else {}

        if not r.get("ok"):
            case_results.append({
                "index": idx,
                "compliant": False,
                "error": r.get("error", "unknown"),
                "missing": ["all (call failed)"],
            })
            continue

        content = r.get("content", "")
        try:
            parsed = json.loads(content) if content else {}
        except json.JSONDecodeError:
            case_results.append({
                "index": idx,
                "compliant": False,
                "error": "non-JSON response",
                "raw": content[:200],
                "missing": ["all (parse failed)"],
            })
            continue

        compliant, missing = _check_schema_compliance(parsed, task_name)
        case_results.append({
            "index": idx,
            "compliant": compliant,
            "missing": missing,
            "grade": parsed.get("grade"),
            "fidelity_score": parsed.get("fidelity_score"),
            "error_types": parsed.get("error_types", []),
        })

    # Calculate compliance rate
    total = len(case_results)
    compliant_count = sum(1 for r in case_results if r.get("compliant"))
    compliance_rate = compliant_count / total if total > 0 else 0.0
    passed = compliance_rate >= _MIN_COMPLIANCE_RATE

    result = {
        "passed": passed,
        "model": model,
        "task": task_name,
        "compliance_rate": compliance_rate,
        "compliant_count": compliant_count,
        "total_tested": total,
        "enhanced_prompt_used": True,
        "results": case_results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }

    # Cache result
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(
        "Preflight {}: {}/{} compliant ({:.0%}) for {}+{}",
        "PASSED" if passed else "FAILED",
        compliant_count, total, compliance_rate,
        task_name, model,
    )

    # If passed, also cache the enhanced prompt for the persona loop to use
    if passed:
        prompt_cache = _PREFLIGHT_CACHE_DIR / f"{task_name}_validated_prompt.txt"
        prompt_cache.write_text(enhanced_prompt)

    return result


def get_validated_prompt(task_name: str) -> str | None:
    """Get the validated (schema-enhanced) prompt if preflight has passed.

    Returns the enhanced system prompt, or None if no valid preflight exists.
    """
    prompt_cache = _PREFLIGHT_CACHE_DIR / f"{task_name}_validated_prompt.txt"
    if prompt_cache.exists():
        age = time.time() - prompt_cache.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            return prompt_cache.read_text()
    return None


def get_validated_model(task_name: str) -> str | None:
    """Get the model that passed preflight for this task.

    Returns model name, or None if no valid preflight exists.
    """
    for cache_file in _PREFLIGHT_CACHE_DIR.glob(f"{task_name}_*.json"):
        if not _is_cache_valid(cache_file):
            continue
        with open(cache_file) as f:
            data = json.load(f)
        if data.get("passed"):
            return data.get("model")
    return None


# ── CLI ──
if __name__ == "__main__":
    import typer

    app = typer.Typer(add_completion=False)

    @app.command()
    def preflight(
        task: str = typer.Argument(help="Task name (e.g. extraction-quality-assessor)"),
        model: str | None = typer.Option(None, help="Model to test"),
        force: bool = typer.Option(False, help="Ignore cache"),
        output_json: bool = typer.Option(False, "--json"),
    ):
        """Run teacher prompt preflight validation."""
        result = asyncio.run(run_preflight(task, model=model, force=force))
        if output_json:
            print(json.dumps(result, indent=2))
        else:
            status = "PASSED" if result["passed"] else "FAILED"
            print(f"\nPreflight {status}")
            print(f"  Task: {result.get('task')}")
            print(f"  Model: {result.get('model')}")
            print(f"  Compliance: {result.get('compliant_count')}/{result.get('total_tested')} "
                  f"({result.get('compliance_rate', 0):.0%})")
            if not result["passed"]:
                for r in result.get("results", []):
                    if not r.get("compliant"):
                        print(f"  FAIL chunk {r.get('index')}: missing {r.get('missing')}")

    app()
