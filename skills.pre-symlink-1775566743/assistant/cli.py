"""CLI commands for the assistant gateway.

Provides typer subcommands: validate, classify, register, status,
shadow-report, and self-test. Each command delegates to the core
gateway functions in gateway.py.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict

import typer
from loguru import logger

try:
    from .gateway import (
        AssistantRouter,
        classify,
        dispatch,
        load_registry,
        validate,
        METRICS_FILE,
        REGISTRY_PATH,
        SHADOW_FILE,
    )
except ImportError:
    from gateway import (  # type: ignore[no-redef]
        AssistantRouter,
        classify,
        dispatch,
        load_registry,
        validate,
        METRICS_FILE,
        REGISTRY_PATH,
        SHADOW_FILE,
    )

app = typer.Typer(add_completion=False, help="Shared GPT + classifier inference gateway")


@app.command("validate")
def validate_cmd(
    task: str = typer.Option("", "--task", "-t", help="Task name (auto-dispatched if empty)"),
    scope: str = typer.Option("", "--scope", "-s", help="Persona memory scope"),
    input_json: str = typer.Option(..., "--input", "-i", help="Input data as JSON string"),
    threshold: float = typer.Option(0.85, "--threshold", help="Confidence threshold"),
):
    """Validate input through 4-tier cascade."""
    try:
        input_data = json.loads(input_json)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        raise typer.Exit(code=1)

    result = validate(input_data, task=task, scope=scope, confidence_threshold=threshold)
    output = {
        "result": result.result,
        "confidence": result.confidence,
        "tier": result.tier,
        "source": result.source,
        "latency_ms": round(result.latency_ms, 2),
        "cached": result.cached,
        "task": result.task,
        "scope": result.scope,
    }
    typer.echo(json.dumps(output, indent=2, default=str))


@app.command("classify")
def classify_cmd(
    task: str = typer.Option("", "--task", "-t", help="Classifier task name"),
    scope: str = typer.Option("", "--scope", "-s", help="Persona memory scope"),
    text: str = typer.Option(..., "--text", help="Text to classify"),
    threshold: float = typer.Option(0.80, "--threshold", help="Confidence threshold"),
):
    """Classify text through 3-tier cascade."""
    result = classify(text, task=task, scope=scope, confidence_threshold=threshold)
    output = {
        "prediction": result.prediction,
        "confidence": result.confidence,
        "tier": result.tier,
        "source": result.source,
        "latency_ms": round(result.latency_ms, 2),
        "task": result.task,
    }
    typer.echo(json.dumps(output, indent=2, default=str))


@app.command("register")
def register_cmd(
    task: str = typer.Option(..., "--task", help="Task name"),
    model_path: str = typer.Option(..., "--model-path", help="Path to model file/dir"),
    model_type: str = typer.Option(..., "--type", help="Model type: gpt|sklearn|distilbert"),
    threshold: float = typer.Option(0.85, "--threshold", help="Confidence threshold"),
):
    """Register a new model in the registry."""
    registry = load_registry()

    entry = {
        "confidence_threshold": threshold,
    }

    if model_type == "gpt":
        entry["gpt_model_path"] = model_path
        entry["task_spec"] = task
        entry["input_signature"] = {"required_fields": []}
        registry.setdefault("validators", {})[task] = entry
    else:
        entry["model_path"] = model_path
        entry["type"] = model_type
        entry["input_signature"] = {"type": "text"}
        registry.setdefault("classifiers", {})[task] = entry

    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)

    logger.info(f"Registered {model_type} model for task={task}")
    typer.echo(json.dumps({"status": "registered", "task": task, "type": model_type}, indent=2))


@app.command("status")
def status_cmd():
    """Show registered models, hit rates, tier distribution."""
    router = AssistantRouter()
    status = router.status()
    typer.echo(json.dumps(status, indent=2, default=str))

    # Show metrics summary if available
    if METRICS_FILE.exists():
        tiers = {0: 0, 1: 0, 2: 0}
        total = 0
        try:
            with open(METRICS_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        tier = entry.get("tier", -1)
                        tiers[tier] = tiers.get(tier, 0) + 1
                        total += 1
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

        if total > 0:
            typer.echo(f"\nMetrics ({total} total requests):")
            for tier, count in sorted(tiers.items()):
                pct = count / total * 100
                typer.echo(f"  Tier {tier}: {count} ({pct:.1f}%)")


@app.command("shadow-report")
def shadow_report_cmd(
    task: str = typer.Option("", "--task", "-t", help="Filter by task name"),
    since: str = typer.Option("24h", "--since", help="Time window (e.g. 24h, 7d)"),
):
    """Show shadow mode agreement rates between local models and teacher."""
    if not SHADOW_FILE.exists():
        typer.echo("No shadow data yet. Run tasks with shadow_mode=true first.")
        raise typer.Exit(0)

    cutoff = datetime.now(timezone.utc) - _parse_shadow_duration(since)

    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"agree": 0, "disagree": 0, "total": 0})
    disagree_examples: Dict[str, list] = defaultdict(list)

    with open(SHADOW_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["timestamp"])
                if ts < cutoff:
                    continue
                t = entry.get("task", "unknown")
                if task and t != task:
                    continue
                stats[t]["total"] += 1
                if entry.get("agreed"):
                    stats[t]["agree"] += 1
                else:
                    stats[t]["disagree"] += 1
                    if len(disagree_examples[t]) < 3:
                        disagree_examples[t].append(entry)
            except (json.JSONDecodeError, KeyError):
                continue

    if not stats:
        typer.echo(f"No shadow data in last {since}.")
        raise typer.Exit(0)

    typer.echo(f"\n=== Shadow Mode Report (last {since}) ===\n")
    for t, s in sorted(stats.items()):
        rate = s["agree"] / s["total"] * 100 if s["total"] > 0 else 0
        status = "READY" if rate >= 90 else "LEARNING" if rate >= 70 else "EARLY"
        typer.echo(f"  {t}:")
        typer.echo(f"    Total: {s['total']}  Agree: {s['agree']}  Disagree: {s['disagree']}")
        typer.echo(f"    Agreement rate: {rate:.1f}% [{status}]")
        if disagree_examples.get(t):
            typer.echo(f"    Recent disagreements:")
            for ex in disagree_examples[t]:
                typer.echo(
                    f"      local={ex.get('local_grade', '?')} vs "
                    f"teacher={ex.get('teacher_grade', '?')} "
                    f"(confidence={ex.get('local_confidence', 0):.3f})"
                )
        typer.echo()

    typer.echo("Thresholds: READY >= 90% | LEARNING >= 70% | EARLY < 70%")
    typer.echo("When READY, set shadow_mode=false in model_registry.json to promote.")


def _parse_shadow_duration(since: str):
    """Parse duration string for shadow report."""
    since = since.strip().lower()
    if since.endswith("h"):
        return timedelta(hours=int(since[:-1]))
    elif since.endswith("d"):
        return timedelta(days=int(since[:-1]))
    return timedelta(hours=24)


@app.command("self-test")
def self_test_cmd():
    """Run synthetic input through all tiers to verify cascade."""
    typer.echo("=== Assistant Gateway Self-Test ===\n")
    errors = 0

    # Test 1: Validate with auto-dispatch (should hit passthrough -> scillm or low-confidence)
    typer.echo("Test 1: validate() with QRA-like input...")
    try:
        result = validate(
            {"question": "What is CWE-79?", "answer": "Cross-site scripting"},
            task="qra-assessor",
        )
        typer.echo(f"  tier={result.tier}, source={result.source}, confidence={result.confidence:.3f}")
        typer.echo(f"  latency={result.latency_ms:.1f}ms")
        typer.echo("  [OK]")
    except Exception as e:
        typer.echo(f"  [FAIL] {e}")
        errors += 1

    # Test 2: Classify
    typer.echo("\nTest 2: classify() with bridge-tagger...")
    try:
        result = classify("satellite vulnerability assessment", task="bridge-tagger")
        typer.echo(f"  prediction={result.prediction}, tier={result.tier}, source={result.source}")
        typer.echo("  [OK]")
    except Exception as e:
        typer.echo(f"  [FAIL] {e}")
        errors += 1

    # Test 3: Dispatch
    typer.echo("\nTest 3: dispatch() auto-detection...")
    try:
        task = dispatch({"question": "test?", "answer": "test"})
        typer.echo(f"  dispatched to: {task}")
        assert task == "qra-assessor", f"Expected qra-assessor, got {task}"
        typer.echo("  [OK]")
    except Exception as e:
        typer.echo(f"  [FAIL] {e}")
        errors += 1

    # Test 4: Cache
    typer.echo("\nTest 4: Cache hit...")
    try:
        r1 = validate({"question": "cache test", "answer": "x"}, task="qra-assessor")
        r2 = validate({"question": "cache test", "answer": "x"}, task="qra-assessor")
        typer.echo(f"  r1.cached={r1.cached}, r2.cached={r2.cached}")
        assert r2.cached, "Second call should be cached"
        typer.echo("  [OK]")
    except Exception as e:
        typer.echo(f"  [FAIL] {e}")
        errors += 1

    # Test 5: Registry
    typer.echo("\nTest 5: Registry loading...")
    try:
        reg = load_registry()
        v_count = len(reg.get("validators", {}))
        c_count = len(reg.get("classifiers", {}))
        typer.echo(f"  validators={v_count}, classifiers={c_count}")
        assert v_count > 0, "Should have validators"
        typer.echo("  [OK]")
    except Exception as e:
        typer.echo(f"  [FAIL] {e}")
        errors += 1

    typer.echo(f"\n{'PASS' if errors == 0 else 'FAIL'} ({5 - errors}/5 tests passed)")
    raise typer.Exit(code=1 if errors > 0 else 0)
