#!/usr/bin/env python3
"""Check for warm Chutes model variants and recommend proxy config updates.

Wraps /ops-chutes recommend to find hot model variants in the same family.
Run via: ./run.sh warm-check [model_id]

Usage:
    ./run.sh warm-check                           # Check current text model
    ./run.sh warm-check deepseek-ai/DeepSeek-V3.1-TEE  # Check specific model
    ./run.sh warm-check --json                    # JSON output
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

OPS_CHUTES_DIR = Path.home() / ".pi" / "skills" / "ops-chutes"
PROXY_CONFIG = Path.home() / "workspace" / "experiments" / "scillm" / "local" / "proxy_server_config.yaml"
DEFAULT_TEXT_MODEL_NAMES = ("chutes-deepseek", "text")


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def get_current_text_model() -> str | None:
    """Extract the configured default Chutes text deployment from proxy config."""
    if not PROXY_CONFIG.exists():
        return None
    content = PROXY_CONFIG.read_text()
    # Current configs use the public provider-family profile chutes-deepseek.
    # Older configs used text. Accept both so warm-check keeps working across
    # config generations.
    lines = content.splitlines()
    in_target_block = False
    target_indent: int | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- model_name:"):
            model_name = stripped.split(":", 1)[1].strip()
            in_target_block = model_name in DEFAULT_TEXT_MODEL_NAMES
            target_indent = _line_indent(line) if in_target_block else None
            continue
        if not in_target_block:
            continue
        if target_indent is not None and stripped.startswith("- ") and _line_indent(line) <= target_indent:
            in_target_block = False
            target_indent = None
            continue
        if stripped.startswith("model:") and "model_name:" not in stripped:
            model = stripped.split(":", 1)[1].strip()
            return model
    return None


def check_warm_variants(model_id: str, json_output: bool = False) -> dict:
    """Call ops-chutes recommend to find warm variants."""
    if not OPS_CHUTES_DIR.exists():
        return {"error": "ops-chutes skill not found", "model": model_id}

    run_sh = OPS_CHUTES_DIR / "run.sh"
    if not run_sh.exists():
        return {"error": "ops-chutes run.sh not found", "model": model_id}

    try:
        result = subprocess.run(
            [str(run_sh), "recommend", model_id, "--json"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(OPS_CHUTES_DIR),
        )
        if result.returncode != 0:
            # Try without --json for error message
            result_text = subprocess.run(
                [str(run_sh), "recommend", model_id, "--skip-ping"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(OPS_CHUTES_DIR),
            )
            return {
                "model": model_id,
                "error": result.stderr.strip() or "recommend failed",
                "raw_output": result_text.stdout,
            }

        # Parse JSON output
        data = json.loads(result.stdout)
        return {
            "model": model_id,
            "current_hot": data.get("current_hot", False),
            "recommendation": data.get("recommendation"),
            "variants": data.get("variants", []),
            "switch_needed": data.get("recommendation") is not None,
        }

    except subprocess.TimeoutExpired:
        return {"error": "timeout querying ops-chutes", "model": model_id}
    except json.JSONDecodeError:
        # Fallback: parse text output
        result = subprocess.run(
            [str(run_sh), "recommend", model_id, "--skip-ping"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(OPS_CHUTES_DIR),
        )
        output = result.stdout

        # Parse recommendation from output
        recommendation = None
        if ">>> SWITCH to" in output:
            for line in output.splitlines():
                if ">>> SWITCH to" in line:
                    recommendation = line.split(">>> SWITCH to")[-1].strip()
                    break

        return {
            "model": model_id,
            "current_hot": ">>> BEST" not in output or "current" in output.lower(),
            "recommendation": recommendation,
            "raw_output": output if not json_output else None,
            "switch_needed": recommendation is not None,
        }
    except Exception as e:
        return {"error": str(e), "model": model_id}


def format_human(result: dict) -> str:
    """Format result for human reading."""
    lines = [f"\n=== Warm variant check: {result.get('model', 'unknown')} ===\n"]

    if "error" in result:
        lines.append(f"  [!!] Error: {result['error']}")
        if result.get("raw_output"):
            lines.append(f"\n{result['raw_output']}")
        return "\n".join(lines)

    if result.get("current_hot"):
        lines.append("  [OK] Current model is HOT")
    else:
        lines.append("  [!!] Current model is COLD")

    if result.get("recommendation"):
        lines.append(f"\n  [>>] SWITCH TO: {result['recommendation']}")
        lines.append("\n  To apply:")
        lines.append(f"    1. Edit {PROXY_CONFIG}")
        lines.append(f"       Change model to: {result['recommendation']}")
        lines.append("    2. Rebuild proxy:")
        lines.append("       docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d --build scillm-proxy")
    else:
        lines.append("\n  [OK] No switch needed")

    if result.get("raw_output"):
        lines.append(f"\n{result['raw_output']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check for warm Chutes model variants")
    parser.add_argument("model", nargs="?", help="Model ID to check (default: current text model)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    # Get model to check
    model_id = args.model
    if not model_id:
        model_id = get_current_text_model()
        if not model_id:
            print("Could not determine current text model from proxy config", file=sys.stderr)
            sys.exit(1)

    result = check_warm_variants(model_id, json_output=args.json)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_human(result))

    # Exit code: 1 if switch needed, 0 if current model is hot
    if result.get("switch_needed") or "error" in result:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
