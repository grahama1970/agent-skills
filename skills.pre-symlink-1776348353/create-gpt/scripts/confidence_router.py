#!/usr/bin/env python3
"""Confidence routing: thin wrapper over router.py for backward compatibility.

Usage:
    python confidence_router.py route '{"question": "test?"}' --task qra-assessor
    python confidence_router.py route '{"question": "test?"}' --task qra-assessor --threshold 0.90
    python confidence_router.py route '{"q": "x"}' --task qra-assessor --threshold 0.85 --timeout 30
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from router import Router, RouterConfig

app = typer.Typer(add_completion=False)


def route(
    input_text: str,
    task_name: str,
    threshold: float = 0.85,
    model_path: Optional[Path] = None,
    timeout: int = 30,
) -> dict:
    """Route input through local GPT, escalating to /scillm if confidence is low.

    Backward-compatible wrapper around Router.route().
    """
    config = RouterConfig(
        task_name=task_name,
        confidence_threshold=threshold,
        model_path=model_path,
        scillm_timeout=timeout,
    )
    r = Router(config)

    try:
        input_data = json.loads(input_text)
    except json.JSONDecodeError:
        input_data = {"text": input_text}

    result = r.route(input_data)

    # Map TierResult to legacy format
    source_map = {"local_gpt": "local", "scillm": "scillm", "heuristic": "local"}
    source = source_map.get(result.source, result.source)
    if result.tier == 1 and result.confidence < threshold:
        source = "local_fallback"

    return {
        "source": source,
        "result": result.result,
        "confidence": result.confidence,
        "latency_ms": result.latency_ms,
        "routing": {
            "threshold": threshold,
            "decision": "local" if result.tier <= 1 else "escalated",
            "tier": result.tier,
            "cached": result.cached,
        },
    }


@app.command()
def route_cmd(
    input_text: str = typer.Argument(..., help="Input text or JSON"),
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    threshold: float = typer.Option(0.85, "--threshold"),
    model_path: Optional[Path] = typer.Option(None, "--model"),
    timeout: int = typer.Option(30, "--timeout", help="Tier-2 timeout seconds"),
):
    """Route input through local GPT with /scillm escalation."""
    result = route(input_text, task, threshold, model_path, timeout)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    app()
