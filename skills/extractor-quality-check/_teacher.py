"""Persona autonomous loop — teacher evaluation pipeline.

Handles chunk evaluation via three paths:
  1. /assistant 4-tier cascade (when a trained model exists)
  2. /assistant gateway (shadow mode routing)
  3. Direct scillm teacher evaluation (async, parallel)

Also manages teacher label storage and training trigger logic
for the /create-gpt feedback loop.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger as log

from _config import (
    ASSISTANT_DIR,
    CREATE_GPT_DATA,
    CREATE_GPT_DIR,
    EVIDENCE_CASE_DIR,
    EVIDENCE_CASE_TIMEOUT,
    LEAN4_PROVE_DIR,
    LEAN4_VERIFY_LABELS,
    SKILLS_DIR,
    TASK_MAP,
    TEACHER_LABELS_DIR,
    TRAINING_TRIGGER_THRESHOLD,
    VERIFY_TEACHER_LABELS,
    gateway_available,
    gw_validate,
)


def _get_task_spec_for_persona(persona_config: dict) -> dict | None:
    """Load the /create-gpt task spec YAML for this persona's evaluator task."""
    import yaml

    task_name = TASK_MAP.get(persona_config["scope"])
    if not task_name:
        return None

    spec_path = CREATE_GPT_DATA / "tasks" / f"{task_name}.yaml"
    if not spec_path.exists():
        log.warning("Task spec not found: {}", spec_path)
        return None

    with open(spec_path) as f:
        spec = yaml.safe_load(f)
    spec["_task_name"] = task_name
    return spec


def _assistant_available(task_name: str) -> bool:
    """Check if /assistant has a trained model registered for this task.

    Returns True if:
    1. model_registry.json exists and has the task
    2. The GPT model file actually exists on disk
    3. Enough teacher labels exist (training has happened)

    When True, the persona can route through assistant.validate()
    instead of calling scillm directly -- getting fast local inference
    with shadow mode comparison against the teacher.
    """
    registry_path = ASSISTANT_DIR / "model_registry.json"
    if not registry_path.exists():
        return False

    try:
        with open(registry_path) as f:
            registry = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    validator_cfg = registry.get("validators", {}).get(task_name)
    if not validator_cfg:
        return False

    model_path = Path(validator_cfg.get("gpt_model_path", "")).expanduser()
    if not model_path.exists():
        log.debug("Assistant model registered but not found: {}", model_path)
        return False

    # Only use assistant after we've accumulated meaningful teacher data
    label_count = count_teacher_labels(task_name)
    if label_count < TRAINING_TRIGGER_THRESHOLD:
        log.debug(
            "Assistant model exists but only {}/{} teacher labels -- "
            "staying in teacher-only mode",
            label_count, TRAINING_TRIGGER_THRESHOLD,
        )
        return False

    return True


def _evaluate_chunk_via_assistant(
    chunk: dict,
    task_name: str,
    scope: str,
) -> dict | None:
    """Evaluate a single chunk via /assistant's 4-tier cascade.

    Uses assistant.validate() which routes through:
      Tier 0:   Heuristic
      Tier 0.5: Classifier
      Tier 1.5: Trained GPT (fast, free, ~200ms)
      Tier 2:   scillm (authoritative fallback)

    In shadow mode, the local GPT runs alongside scillm to measure
    agreement. This lets the persona verify the student's quality.

    Still writes teacher labels so the training data continues to grow.
    """
    sys.path.insert(0, str(ASSISTANT_DIR))
    try:
        from assistant import validate as assistant_validate
    except ImportError:
        log.debug("assistant module not importable, falling back to teacher mode")
        return None

    text = chunk.get("text", chunk.get("solution", ""))
    asset_type = chunk.get("asset_type", chunk.get("type", "section"))

    if not text or len(text.strip()) < 10:
        return None

    input_data = {
        "text": text[:2000],
        "asset_type": asset_type,
        "doc_id": chunk.get("doc_id", ""),
        "content_type": chunk.get("content_type", "text"),
    }

    try:
        result = assistant_validate(
            input_data=input_data,
            task=task_name,
            scope=scope,
        )

        evaluation = {
            "grade": result.result.get("grade", "UNKNOWN"),
            "confidence": result.confidence,
            "tier": result.tier,
            "source": result.source,
            "error_types": result.result.get("error_types", []),
            "fidelity_score": result.result.get(
                "fidelity_score",
                result.result.get("security_fidelity_score", 0.0),
            ),
            "issues": result.result.get("issues", []),
            "remediation": result.result.get("remediation", ""),
        }

        # Still write teacher labels for ongoing retraining
        write_teacher_label(
            task_name=task_name,
            input_data=input_data,
            output_data=result.result,
            scope=scope,
        )

        return evaluation
    except Exception as e:
        log.warning("Assistant evaluation failed: {}: {}", type(e).__name__, e)
        return None


async def _ensure_preflight(task_name: str, model: str) -> tuple[str, str]:
    """Run preflight if no cached validated prompt exists.

    Returns (system_prompt, model) -- using validated versions if available.
    """
    from teacher_preflight import get_validated_prompt, get_validated_model, run_preflight

    system_prompt = get_validated_prompt(task_name)
    validated_model = get_validated_model(task_name)

    if system_prompt is None:
        log.info("No validated prompt for {} -- running preflight...", task_name)
        try:
            preflight_result = await run_preflight(task_name, model=model)
            if preflight_result.get("passed"):
                system_prompt = get_validated_prompt(task_name)
                validated_model = get_validated_model(task_name)
                log.info(
                    "Preflight passed: {:.0%} compliance with {}",
                    preflight_result["compliance_rate"], model,
                )
            else:
                log.warning(
                    "Preflight FAILED for {} ({:.0%} compliance) -- "
                    "teacher evaluations may produce non-conformant labels",
                    task_name, preflight_result.get("compliance_rate", 0),
                )
        except Exception as e:
            log.warning("Preflight failed: {} -- using raw prompt", e)

    return system_prompt or "", validated_model or model


async def _evaluate_chunks_as_teacher_async(
    chunks: list[dict],
    persona_config: dict,
) -> list[dict | None]:
    """Evaluate datalake chunks in parallel using the persona as teacher (via scillm).

    Async implementation -- called from the single asyncio.run() in run_cycle().
    Uses scillm paved-path: acompletion with semaphore concurrency control.

    Runs preflight on first call to validate schema compliance.

    Returns list of evaluation dicts (None for failed/skipped chunks).
    """
    from scillm import acompletion

    spec = _get_task_spec_for_persona(persona_config)
    if not spec:
        return [None] * len(chunks)

    task_name = spec["_task_name"]
    model = os.getenv("CHUTES_TEXT_MODEL", "deepseek-ai/DeepSeek-V3-0324")
    api_base = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
    api_key = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

    if not api_key:
        log.warning("SCILLM_PROXY_KEY not set -- skipping teacher evaluation")
        return [None] * len(chunks)

    # Ensure preflight has validated the prompt (async, no nested asyncio.run)
    system_prompt, model = await _ensure_preflight(task_name, model)

    # Build requests
    requests: list[dict] = []
    chunk_map: dict[int, dict] = {}

    for i, chunk in enumerate(chunks):
        text = chunk.get("text", chunk.get("solution", ""))
        asset_type = chunk.get("asset_type", chunk.get("type", "section"))

        if not text or len(text.strip()) < 10:
            continue

        user_msg = json.dumps({
            "text": text[:2000],
            "asset_type": asset_type,
            "doc_id": chunk.get("doc_id", ""),
            "content_type": chunk.get("content_type", "text"),
        }, ensure_ascii=False)

        requests.append({
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "model": model,
            "max_tokens": 512,
            "temperature": 0.1,
            "index": i,
        })
        chunk_map[i] = chunk

    if not requests:
        return [None] * len(chunks)

    # Run parallel evaluations using scillm acompletion + semaphore
    results: list[dict | None] = [None] * len(chunks)
    sem = asyncio.Semaphore(3)

    async def _call_one(req: dict) -> dict:
        async with sem:
            try:
                resp = await acompletion(
                    model=req["model"],
                    api_base=api_base,
                    api_key=api_key,
                    custom_llm_provider="openai",
                    messages=req["messages"],
                    max_tokens=req["max_tokens"],
                    temperature=req["temperature"],
                    response_format={"type": "json_object"},
                    timeout=30,
                )
                content = resp.choices[0].message.content
                return {"index": req["index"], "content": content, "ok": True}
            except Exception as e:
                return {"index": req["index"], "error": str(e), "ok": False}

    completed = await asyncio.gather(*[_call_one(r) for r in requests])

    for r in completed:
        idx = r.get("index", -1)
        if idx < 0 or idx not in chunk_map:
            continue

        if not r.get("ok"):
            log.warning(
                "Teacher evaluation failed for chunk {}: {}",
                idx, r.get("error", "unknown"),
            )
            continue

        content = r.get("content", "")
        try:
            result = json.loads(content) if content else {}
        except json.JSONDecodeError:
            log.warning("Teacher returned non-JSON for chunk {}: {}", idx, content[:100])
            continue

        chunk = chunk_map[idx]
        text = chunk.get("text", chunk.get("solution", ""))
        asset_type = chunk.get("asset_type", chunk.get("type", "section"))

        evaluation = {
            "grade": result.get("grade", "UNKNOWN"),
            "confidence": 1.0,
            "tier": 2,
            "source": "teacher_scillm",
            "error_types": result.get("error_types", []),
            "fidelity_score": result.get(
                "fidelity_score",
                result.get("security_fidelity_score", 0.0),
            ),
            "issues": result.get("issues", []),
            "remediation": result.get("remediation", ""),
        }

        write_teacher_label(
            task_name=spec["_task_name"],
            input_data={
                "text": text[:2000],
                "asset_type": asset_type,
                "doc_id": chunk.get("doc_id", ""),
                "source_meta": chunk.get("source_meta", {}),
                "content_type": chunk.get("content_type", "text"),
            },
            output_data=result,
            scope=persona_config["scope"],
        )

        results[idx] = evaluation

    evaluated = sum(1 for r in results if r is not None)
    log.info("Teacher evaluated {}/{} chunks for {}", evaluated, len(chunks), spec["_task_name"])
    return results


def evaluate_chunks_as_teacher(
    chunks: list[dict],
    persona_config: dict,
) -> list[dict | None]:
    """Evaluate chunks -- using /assistant if trained, else scillm directly.

    Phase 1 (< threshold labels): Call scillm directly as teacher.
      Uses _quick_acompletion with asyncio.gather via asyncio.run().

    Phase 2 (>= threshold labels + trained model): Route through /assistant.
      Uses the 4-tier cascade (heuristic -> classifier -> GPT -> scillm).
      Shadow mode compares local GPT vs scillm for quality measurement.
      Still writes teacher labels for ongoing retraining.

    This is the ONLY asyncio.run() in the persona loop.
    """
    task_name = TASK_MAP.get(persona_config["scope"], "")

    # Phase 2: if assistant has a trained model, use it
    if task_name and _assistant_available(task_name):
        log.info(
            "Assistant available for {} -- using 4-tier cascade (shadow=on)",
            task_name,
        )
        results: list[dict | None] = []
        for chunk in chunks:
            result = _evaluate_chunk_via_assistant(
                chunk, task_name, persona_config["scope"],
            )
            results.append(result)
        evaluated = sum(1 for r in results if r is not None)
        log.info("Assistant evaluated {}/{} chunks for {}", evaluated, len(chunks), task_name)
        return results

    # Phase 1.5: if gateway is available, route teacher calls through /assistant
    if gateway_available and gw_validate is not None:
        log.info("Gateway available for {} -- routing teacher calls through /assistant", task_name)
        results = []
        for chunk in chunks:
            text = chunk.get("text", chunk.get("solution", ""))
            asset_type = chunk.get("asset_type", chunk.get("type", "section"))
            if not text or len(text.strip()) < 10:
                results.append(None)
                continue
            try:
                gw_result = gw_validate(
                    input_data={
                        "text": text[:2000],
                        "asset_type": asset_type,
                    },
                    task="extraction-quality-assessor",
                    scope=persona_config["scope"],
                )
                evaluation = {
                    "grade": gw_result.result.get("grade", "UNKNOWN"),
                    "confidence": gw_result.confidence,
                    "tier": gw_result.tier,
                    "source": gw_result.source,
                    "error_types": gw_result.result.get("error_types", []),
                    "fidelity_score": gw_result.result.get(
                        "fidelity_score",
                        gw_result.result.get("security_fidelity_score", 0.0),
                    ),
                    "issues": gw_result.result.get("issues", []),
                    "remediation": gw_result.result.get("remediation", ""),
                }
                write_teacher_label(
                    task_name=task_name,
                    input_data={
                        "text": text[:2000],
                        "asset_type": asset_type,
                        "doc_id": chunk.get("doc_id", ""),
                        "content_type": chunk.get("content_type", "text"),
                    },
                    output_data=gw_result.result,
                    scope=persona_config["scope"],
                )
                results.append(evaluation)
            except Exception as e:
                log.warning("Gateway evaluation failed for chunk: {}", e)
                results.append(None)
        evaluated = sum(1 for r in results if r is not None)
        log.info("Gateway evaluated {}/{} chunks for {}", evaluated, len(chunks), task_name)
        return results

    # Phase 1: direct scillm teacher evaluation
    try:
        return asyncio.run(_evaluate_chunks_as_teacher_async(chunks, persona_config))
    except Exception as e:
        log.warning("Batch teacher evaluation failed: {}: {}", type(e).__name__, e)
        return [None] * len(chunks)


def verify_teacher_label(
    task_name: str,
    input_data: dict,
    output_data: dict,
    scope: str,
    verdict: str,
    is_negative: bool,
) -> dict[str, Any]:
    """Verify a teacher label using /create-evidence-case and optionally /lean4-prove.

    Builds a formal evidence case for the verdict. If the evidence case
    disagrees with the initial polarity (e.g. evidence says "not_satisfied"
    but verdict was "pass"), this is a CORRECTION signal — flip GRPO polarity.

    Optionally calls /lean4-prove on the reasoning chain when LEAN4_VERIFY_LABELS
    is enabled.

    Returns an enrichment dict with:
      - evidence_case_id, evidence_verdict, lean4_status,
        evidence_confidence, reward_verified, corrected_polarity (if flipped)
    """
    result: dict[str, Any] = {
        "evidence_case_id": "",
        "evidence_verdict": "skipped",
        "lean4_status": "skipped",
        "evidence_confidence": 0.0,
        "reward_verified": False,
    }

    # ── Step 1: Build evidence case via /create-evidence-case ──
    evidence_run_sh = EVIDENCE_CASE_DIR / "run.sh"
    if not evidence_run_sh.exists():
        log.debug("Evidence case skill not found at {}", evidence_run_sh)
        return result

    # Prepare claim payload for evidence case
    claim_payload = json.dumps({
        "claim": f"Teacher verdict '{verdict}' is correct for this extraction",
        "scope": scope,
        "task": task_name,
        "input_summary": json.dumps(input_data, ensure_ascii=False)[:500],
        "output_summary": json.dumps(output_data, ensure_ascii=False)[:500],
        "verdict": verdict,
    }, ensure_ascii=False)

    try:
        ec_proc = subprocess.run(
            [str(evidence_run_sh), "build", "--claim", claim_payload],
            cwd=str(EVIDENCE_CASE_DIR),
            capture_output=True,
            text=True,
            timeout=EVIDENCE_CASE_TIMEOUT,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if ec_proc.returncode != 0:
            log.warning(
                "Evidence case build failed (rc={}): {}",
                ec_proc.returncode, ec_proc.stderr[:200],
            )
            return result

        ec_output = json.loads(ec_proc.stdout)
        result["evidence_case_id"] = ec_output.get("case_id", "")
        result["evidence_verdict"] = ec_output.get("verdict", "inconclusive")
        result["evidence_confidence"] = float(ec_output.get("confidence", 0.0))
        result["reward_verified"] = True

    except subprocess.TimeoutExpired:
        log.warning("Evidence case timed out after {}s", EVIDENCE_CASE_TIMEOUT)
        return result
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("Evidence case returned unparseable output: {}", e)
        return result
    except Exception as e:
        log.warning("Evidence case failed: {}: {}", type(e).__name__, e)
        return result

    # ── Step 2: Check for polarity correction ──
    ev = result["evidence_verdict"]
    if ev == "not_satisfied" and not is_negative:
        # Evidence says the "pass" verdict was wrong — flip to negative
        log.info(
            "Evidence CORRECTION: verdict='{}' but evidence='not_satisfied' — "
            "flipping GRPO polarity to negative for task={}",
            verdict, task_name,
        )
        result["corrected_polarity"] = "negative"
    elif ev == "satisfied" and is_negative:
        # Evidence says the "fail/warn" verdict was wrong — flip to positive
        log.info(
            "Evidence CORRECTION: verdict='{}' but evidence='satisfied' — "
            "flipping GRPO polarity to positive for task={}",
            verdict, task_name,
        )
        result["corrected_polarity"] = "positive"

    # ── Step 3: Optional Lean4 formal verification ──
    if LEAN4_VERIFY_LABELS and result["evidence_case_id"]:
        lean4_run_sh = LEAN4_PROVE_DIR / "run.sh"
        if not lean4_run_sh.exists():
            log.debug("lean4-prove skill not found at {}", lean4_run_sh)
            return result

        try:
            lean_proc = subprocess.run(
                [
                    str(lean4_run_sh), "prove",
                    "--case-id", result["evidence_case_id"],
                ],
                cwd=str(LEAN4_PROVE_DIR),
                capture_output=True,
                text=True,
                timeout=EVIDENCE_CASE_TIMEOUT * 2,  # Lean4 proofs take longer
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if lean_proc.returncode == 0:
                lean_output = json.loads(lean_proc.stdout)
                result["lean4_status"] = lean_output.get("status", "skipped")
            else:
                log.warning(
                    "lean4-prove failed (rc={}): {}",
                    lean_proc.returncode, lean_proc.stderr[:200],
                )
        except subprocess.TimeoutExpired:
            log.warning("lean4-prove timed out after {}s", EVIDENCE_CASE_TIMEOUT * 2)
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("lean4-prove returned unparseable output: {}", e)
        except Exception as e:
            log.warning("lean4-prove failed: {}: {}", type(e).__name__, e)

    return result


def write_teacher_label(
    task_name: str,
    input_data: dict,
    output_data: dict,
    scope: str,
) -> None:
    """Append a teacher label to the task's raw JSONL for /create-gpt.

    GRPO training signal: labels with verdict=pass are positive examples,
    labels with verdict=warn or verdict=fail are NEGATIVE examples (GRPO gold).
    Per memory lesson 48294068: "WARN/bad outputs are GRPO training gold --
    negative examples for /create-gpt. Never discard them."

    When VERIFY_TEACHER_LABELS is enabled, runs /create-evidence-case to
    formally verify the verdict. If evidence disagrees, flips GRPO polarity.
    Optionally runs /lean4-prove for formal verification of the reasoning chain.
    """
    label_dir = TEACHER_LABELS_DIR / task_name
    label_dir.mkdir(parents=True, exist_ok=True)
    label_file = label_dir / "teacher_labels.jsonl"

    # Determine GRPO polarity from verdict
    verdict = ""
    assessment = output_data.get("ASSESSMENT", {})
    if isinstance(assessment, dict):
        verdict = str(assessment.get("verdict", "")).lower()
    is_negative = verdict in ("warn", "fail", "bad")

    # ── Evidence verification (optional, non-blocking) ──
    evidence_enrichment: dict[str, Any] = {
        "evidence_case_id": "",
        "evidence_verdict": "skipped",
        "lean4_status": "skipped",
        "evidence_confidence": 0.0,
        "reward_verified": False,
    }

    if VERIFY_TEACHER_LABELS:
        try:
            evidence_enrichment = verify_teacher_label(
                task_name=task_name,
                input_data=input_data,
                output_data=output_data,
                scope=scope,
                verdict=verdict,
                is_negative=is_negative,
            )
            # Apply polarity correction if evidence disagrees
            if "corrected_polarity" in evidence_enrichment:
                corrected = evidence_enrichment.pop("corrected_polarity")
                is_negative = corrected == "negative"
                log.info(
                    "GRPO polarity corrected by evidence: {} → {} for task={}",
                    "positive" if not is_negative else "negative",
                    corrected, task_name,
                )
        except Exception as e:
            log.warning(
                "Evidence verification failed, falling through to unverified label: {}",
                e,
            )

    label = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task_name,
        "scope": scope,
        "source": "persona_teacher",
        "input": input_data,
        "output": output_data,
        "confidence": 1.0,
        "tier": 2,
        "grpo_polarity": "negative" if is_negative else "positive",
        "verdict": verdict,
        "evidence_case_id": evidence_enrichment["evidence_case_id"],
        "evidence_verdict": evidence_enrichment["evidence_verdict"],
        "lean4_status": evidence_enrichment["lean4_status"],
        "evidence_confidence": evidence_enrichment["evidence_confidence"],
        "reward_verified": evidence_enrichment["reward_verified"],
    }

    with open(label_file, "a") as f:
        f.write(json.dumps(label, ensure_ascii=False) + "\n")


def count_teacher_labels(task_name: str) -> int:
    """Count accumulated teacher labels for a task."""
    label_file = TEACHER_LABELS_DIR / task_name / "teacher_labels.jsonl"
    if not label_file.exists():
        return 0
    with open(label_file) as f:
        return sum(1 for line in f if line.strip())


def maybe_trigger_training(persona_config: dict) -> bool:
    """Probabilistically trigger /create-gpt training when enough labels exist.

    The persona decides when to train based on:
    1. Enough teacher labels accumulated (>= threshold)
    2. Probabilistic: 10% chance per cycle once threshold is met
       (avoids multiple concurrent training runs)

    Returns True if training was triggered.
    """
    task_name = TASK_MAP.get(persona_config["scope"])
    if not task_name:
        return False

    count = count_teacher_labels(task_name)
    if count < TRAINING_TRIGGER_THRESHOLD:
        log.info(
            "Teacher labels: {}/{} for {} -- not enough to train yet",
            count, TRAINING_TRIGGER_THRESHOLD, task_name,
        )
        return False

    # Check if training is already running (lock file)
    lock_file = TEACHER_LABELS_DIR / task_name / ".training_lock"
    trained_marker = TEACHER_LABELS_DIR / task_name / ".first_train_done"

    # First trigger is deterministic -- don't gate on probability
    # Subsequent triggers are probabilistic (10% per cycle) to avoid
    # concurrent training runs while still allowing periodic retraining.
    if trained_marker.exists():
        if random.random() > 0.10:
            log.info(
                "Teacher labels: {}/{} for {} -- threshold met, skipping this cycle (probabilistic retrain)",
                count, TRAINING_TRIGGER_THRESHOLD, task_name,
            )
            return False
    else:
        log.info(
            "Teacher labels: {}/{} for {} -- threshold met, FIRST TRAINING (deterministic trigger)",
            count, TRAINING_TRIGGER_THRESHOLD, task_name,
        )
    if lock_file.exists():
        lock_age = time.time() - lock_file.stat().st_mtime
        if lock_age < 3600:  # training lock valid for 1 hour
            log.info("Training already in progress for {} (lock age: {}s)", task_name, int(lock_age))
            return False
        lock_file.unlink()  # stale lock

    log.info(
        "Triggering /create-gpt training for {} ({} teacher labels)",
        task_name, count,
    )

    # Write lock
    lock_file.write_text(datetime.now(timezone.utc).isoformat())

    # Trigger training via CLI
    create_gpt_run = CREATE_GPT_DIR / "run.sh"
    if not create_gpt_run.exists():
        log.warning("/create-gpt run.sh not found at {}", create_gpt_run)
        lock_file.unlink(missing_ok=True)
        return False

    label_file = TEACHER_LABELS_DIR / task_name / "teacher_labels.jsonl"
    try:
        subprocess.Popen(
            [
                str(create_gpt_run), "train",
                "--task", task_name,
                "--input", str(label_file),
                "--max-rounds", "1",
            ],
            cwd=str(CREATE_GPT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        log.info("Training process spawned for {}", task_name)
        # Mark first training done so subsequent triggers are probabilistic
        trained_marker = TEACHER_LABELS_DIR / task_name / ".first_train_done"
        trained_marker.write_text(datetime.now(timezone.utc).isoformat())
        return True
    except Exception as e:
        log.error("Failed to trigger training: {}", e)
        lock_file.unlink(missing_ok=True)
        return False
