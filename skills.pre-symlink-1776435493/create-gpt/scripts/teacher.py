#!/usr/bin/env python3
"""Teacher data generation: label raw inputs via scillm (Tier 2).

Generates labeled training data by running inputs through scillm,
producing JSONL ready for prepare_data.py → train_sft.py.

Usage:
    python teacher.py --task qra-assessor --input raw_qras.jsonl --limit 500 [--strict] [--invalid-out FILE] [--retries 2] [--backoff 0.5]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from loguru import logger

try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, DATA_DIR

app = typer.Typer(add_completion=False)


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file."""
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def save_jsonl(data: list[dict], path: Path) -> None:
    """Save to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _get_quick_completion():
    """Import quick_completion from scillm."""
    scillm_dir = Path(__file__).resolve().parents[2] / "scillm"
    sys.path.insert(0, str(scillm_dir))
    from batch import quick_completion
    return quick_completion


def _validate_label(label: Any, output_schema: Dict[str, Any]) -> bool:
    """Validate teacher output against task spec schema."""
    if not isinstance(label, dict):
        return False
    if not output_schema:
        return True
    if _HAS_JSONSCHEMA:
        try:
            jsonschema.validate(label, output_schema)
            return True
        except jsonschema.ValidationError:
            return False
    # Fallback: check required fields only
    required = output_schema.get("required", [])
    return all(f in label for f in required)


def _label_one(
    input_dict: dict,
    system_prompt: str,
    output_schema: Dict[str, Any],
    quick_completion,
    timeout: int = 30,
    max_retries: int = 2,
    backoff_sec: float = 0.5,
) -> Optional[dict]:
    """Call quick_completion for one input, parse JSON output.

    Returns the parsed label dict, or None on failure.
    Retries up to max_retries times with exponential backoff.
    """
    prompt_parts = []
    if system_prompt:
        prompt_parts.append(system_prompt)

    input_text = input_dict.get("input", "")
    if isinstance(input_text, dict):
        input_text = json.dumps(input_text, ensure_ascii=False)
    prompt_parts.append(f"\nInput:\n{input_text}")

    if output_schema:
        prompt_parts.append(
            f"\nRespond with JSON matching this schema:\n"
            f"{json.dumps(output_schema, indent=2)}"
        )

    prompt = "\n".join(prompt_parts)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result_text = quick_completion(
                prompt=prompt,
                json_mode=True,
                timeout=timeout,
            )
            label = json.loads(result_text)
            return label
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"Failed to parse teacher output (attempt {attempt + 1}): {e}")
            last_error = e
        except Exception as e:
            logger.debug(f"Teacher call failed (attempt {attempt + 1}): {e}")
            last_error = e

        if attempt < max_retries:
            wait = backoff_sec * (2 ** attempt)
            time.sleep(wait)

    logger.warning(f"Teacher labeling exhausted {max_retries + 1} attempts: {last_error}")
    return None


def generate_labels(
    task_name: str,
    input_file: Path,
    output_file: Optional[Path] = None,
    limit: Optional[int] = None,
    timeout: int = 30,
    strict: bool = True,
    invalid_output_file: Optional[Path] = None,
    max_retries: int = 2,
    backoff_sec: float = 0.5,
) -> Path:
    """Generate labeled training data by running inputs through scillm.

    Args:
        task_name: Task name for spec lookup
        input_file: JSONL with {"input": "..."} per line
        output_file: Output JSONL path (default: data/{task}/teacher/labeled.jsonl)
        limit: Max examples to label
        timeout: Per-request timeout seconds
        strict: If True, reject invalid labels; if False, include them with a warning
        invalid_output_file: Path to write invalid labels for audit (optional)
        max_retries: Max retries per teacher call
        backoff_sec: Exponential backoff base seconds

    Returns:
        Path to the output JSONL file.
    """
    spec = load_task_spec(task_name)
    quick_completion = _get_quick_completion()

    raw_data = load_jsonl(input_file)
    logger.info(f"Loaded {len(raw_data)} inputs from {input_file}")

    if limit:
        raw_data = raw_data[:limit]
        logger.info(f"Limited to {len(raw_data)} examples")

    if output_file is None:
        output_file = DATA_DIR / task_name / "teacher" / "labeled.jsonl"

    success, fail, skip = 0, 0, 0
    labeled = []
    invalid_labels = []
    start = time.time()

    for i, item in enumerate(raw_data):
        label = _label_one(
            item, spec.system_prompt, spec.output_schema,
            quick_completion, timeout,
            max_retries=max_retries, backoff_sec=backoff_sec,
        )

        if label is None:
            fail += 1
            continue

        if not _validate_label(label, spec.output_schema):
            invalid_labels.append({"index": i, "input": item.get("input", ""), "label": label})
            if strict:
                skip += 1
                logger.debug(f"[{i}] Label failed validation, skipping (strict)")
                continue
            else:
                logger.debug(f"[{i}] Label failed validation, keeping (non-strict)")

        labeled.append({"input": item.get("input", ""), "output": label})
        success += 1

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            logger.info(f"Progress: {i + 1}/{len(raw_data)} ({rate:.1f}/s)")

    save_jsonl(labeled, output_file)

    # Persist invalid labels for audit
    if invalid_labels and invalid_output_file:
        save_jsonl(invalid_labels, invalid_output_file)
        logger.info(f"Wrote {len(invalid_labels)} invalid labels to {invalid_output_file}")

    elapsed = time.time() - start
    logger.info(
        f"Teacher labeling complete: {success} success, {fail} fail, {skip} skip "
        f"({elapsed:.1f}s)"
    )
    logger.info(f"Output: {output_file}")

    return output_file


@app.command()
def label_cmd(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    input_file: Path = typer.Option(..., "--input", "-i", help="Raw JSONL input"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output path"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max examples"),
    timeout: int = typer.Option(30, "--timeout", help="Per-request timeout (seconds)"),
    strict: bool = typer.Option(True, "--strict", help="Reject invalid labels when True"),
    invalid_out: Optional[Path] = typer.Option(None, "--invalid-out", help="Write invalid labels here for audit"),
    retries: int = typer.Option(2, "--retries", help="Max retries per teacher call"),
    backoff: float = typer.Option(0.5, "--backoff", help="Exponential backoff base seconds"),
):
    """Generate teacher labels for raw inputs via scillm."""
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        raise typer.Exit(code=1)

    if input_file.stat().st_size == 0:
        logger.info("Empty input file, nothing to label")
        raise typer.Exit(code=0)

    output = generate_labels(
        task, input_file, output_file, limit, timeout,
        strict=strict, invalid_output_file=invalid_out,
        max_retries=retries, backoff_sec=backoff,
    )
    logger.info(f"Done. Output: {output}")


if __name__ == "__main__":
    app()
