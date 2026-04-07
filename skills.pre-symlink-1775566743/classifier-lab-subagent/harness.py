#!/usr/bin/env python3
"""Thin training harness — no Docker, no agent layer, just asyncio + subprocess.

Runs 3 classifier training jobs concurrently. Each job:
1. Loads ag_news dataset
2. Fine-tunes a HuggingFace model
3. Evaluates on test set
4. Logs structured progress to JSONL
5. If below gate: calls /scillm for structured HP suggestions
6. Retrains with new HPs
7. Repeats until gate or max rounds

The "subagent" is a Python subprocess. The "intelligence" is /scillm structured JSON.
No agent reasoning. No prompt interpretation. Just code.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
CLASSIFIER_LAB = SKILLS_DIR / "classifier-lab"
LOG_BASE = Path("/tmp/clf-harness")

# ── Configuration ─────────────────────────────────────────────────────

DATASET = "ag_news"
GATE_ACCURACY = 0.95
MAX_ROUNDS = 3
POLL_INTERVAL = 5

# Timeout is estimated per task, not hardcoded.
# Formula: (dataset_size / batch_size) * epochs * seconds_per_step * safety_margin
# CPU: ~0.5s/step, GPU: ~0.05s/step, safety_margin: 2x
DEFAULT_SECONDS_PER_STEP_CPU = 0.5
DEFAULT_SECONDS_PER_STEP_GPU = 0.05
SAFETY_MARGIN = 2.0
FALLBACK_TIMEOUT = 7200  # 2 hours absolute max

MODELS = [
    {"id": "m0", "name": "distilbert-base-uncased", "lr": 2e-5, "batch_size": 32, "epochs": 3, "dropout": 0.1},
    {"id": "m1", "name": "bert-base-uncased", "lr": 2e-5, "batch_size": 16, "epochs": 3, "dropout": 0.1},
    {"id": "m2", "name": "sentence-transformers/all-MiniLM-L6-v2", "lr": 3e-5, "batch_size": 32, "epochs": 4, "dropout": 0.1},
]


def estimate_timeout(dataset_size: int, batch_size: int, epochs: int, gpu: bool = False) -> int:
    """Estimate training timeout based on task parameters.

    The project agent sets these — the harness doesn't guess.
    """
    steps = (dataset_size / batch_size) * epochs
    sps = DEFAULT_SECONDS_PER_STEP_GPU if gpu else DEFAULT_SECONDS_PER_STEP_CPU
    estimated = steps * sps * SAFETY_MARGIN
    timeout = min(int(estimated), FALLBACK_TIMEOUT)
    logger.info(f"Estimated timeout: {timeout}s ({timeout/60:.0f}min) "
                f"[{dataset_size} samples, batch={batch_size}, epochs={epochs}, "
                f"{'GPU' if gpu else 'CPU'}, {sps}s/step, {SAFETY_MARGIN}x margin]")
    return timeout


@dataclass
class RunResult:
    model_id: str
    model_name: str
    status: str = "pending"
    rounds: list[dict] = field(default_factory=list)
    best_accuracy: float = 0.0
    best_f1: float = 0.0
    gate_passed: bool = False
    total_duration: float = 0.0
    error: str = ""


# ── Training Script (written to disk, run as subprocess) ──────────────

TRAIN_SCRIPT = '''#!/usr/bin/env python3
"""Single training + eval run. Writes structured output to result.json."""
import json, os, sys, time, traceback
from pathlib import Path

LOG_DIR = Path(sys.argv[1])
CONFIG = json.loads(sys.argv[2])

PROGRESS = LOG_DIR / "progress.jsonl"
RESULT = LOG_DIR / "result.json"

def log(event: dict):
    event["ts"] = time.time()
    with PROGRESS.open("a") as f:
        f.write(json.dumps(event) + "\\n")
    print(json.dumps(event), flush=True)

def main():
    model_name = CONFIG["name"]
    lr = CONFIG["lr"]
    batch_size = CONFIG["batch_size"]
    epochs = CONFIG["epochs"]
    round_num = CONFIG.get("round", 1)

    log({"event": "start", "model": model_name, "round": round_num, "config": CONFIG})

    try:
        from datasets import load_dataset
        log({"event": "loading_dataset"})
        train_ds = load_dataset("ag_news", split="train")
        test_ds = load_dataset("ag_news", split="test")
        log({"event": "dataset_loaded", "train": len(train_ds), "test": len(test_ds)})
    except Exception as e:
        log({"event": "error", "step": "dataset", "error": str(e)})
        RESULT.write_text(json.dumps({"status": "failed", "error": str(e)}))
        sys.exit(1)

    try:
        import numpy as np
        import torch
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
            TrainerCallback,
        )
        from sklearn.metrics import f1_score

        log({"event": "loading_model", "model": model_name})
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=4)

        def tokenize(batch):
            return tokenizer(batch["text"], padding="max_length", truncation=True, max_length=128)

        log({"event": "tokenizing"})
        train_tok = train_ds.map(tokenize, batched=True, batch_size=1000)
        test_tok = test_ds.map(tokenize, batched=True, batch_size=1000)
        train_tok.set_format("torch", columns=["input_ids", "attention_mask", "label"])
        test_tok.set_format("torch", columns=["input_ids", "attention_mask", "label"])

        def compute_metrics(eval_pred):
            logits, labels = eval_pred
            preds = np.argmax(logits, axis=-1)
            acc = float((preds == labels).mean())
            f1 = float(f1_score(labels, preds, average="macro"))
            return {"accuracy": acc, "f1": f1}

        class LogCallback(TrainerCallback):
            def on_evaluate(self, args, state, control, metrics=None, **kwargs):
                if metrics:
                    log({
                        "event": "eval",
                        "epoch": state.epoch,
                        "accuracy": metrics.get("eval_accuracy", 0),
                        "f1": metrics.get("eval_f1", 0),
                        "loss": metrics.get("eval_loss", 0),
                    })

            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs and "loss" in logs:
                    log({"event": "train_step", "step": state.global_step, "loss": logs["loss"]})

        out_dir = str(LOG_DIR / f"checkpoints_r{round_num}")
        training_args = TrainingArguments(
            output_dir=out_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=64,
            learning_rate=lr,
            eval_strategy="epoch",
            save_strategy="no",
            logging_dir=str(LOG_DIR / "tb_logs"),
            logging_steps=200,
            load_best_model_at_end=False,
            report_to=["tensorboard"],
            fp16=torch.cuda.is_available(),
            dataloader_num_workers=2,
        )

        log({"event": "training_start", "epochs": epochs, "lr": lr, "batch_size": batch_size})

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_tok,
            eval_dataset=test_tok,
            compute_metrics=compute_metrics,
            callbacks=[LogCallback()],
        )
        trainer.train()

        log({"event": "training_complete"})
        eval_result = trainer.evaluate()
        f1 = eval_result.get("eval_f1", 0)
        accuracy = eval_result.get("eval_accuracy", 0)

        result = {
            "status": "completed",
            "model": model_name,
            "round": round_num,
            "f1": f1,
            "accuracy": accuracy,
            "gate_passed": accuracy >= {gate},
            "config": CONFIG,
        }
        log({"event": "done", **result})
        RESULT.write_text(json.dumps(result, indent=2))

    except Exception as e:
        log({"event": "error", "step": "training", "error": str(e), "tb": traceback.format_exc()})
        RESULT.write_text(json.dumps({"status": "failed", "error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
'''


# ── scillm HP Suggestion ─────────────────────────────────────────────

async def suggest_hps(
    model_name: str,
    rounds_history: list[dict],
    gate: float,
) -> dict:
    """Ask /scillm for next HPs. Returns structured JSON. Falls back to heuristic."""
    history = "\n".join(
        f"  Round {r['round']}: lr={r['config']['lr']}, batch={r['config']['batch_size']}, "
        f"epochs={r['config']['epochs']} → accuracy={r.get('accuracy', 0):.4f}, f1={r.get('f1', 0):.4f}"
        for r in rounds_history
    )

    prompt = (
        f"Text classifier ({model_name}) on AG News (4 classes, 120K train).\n"
        f"Target: accuracy >= {gate}\n\nHistory:\n{history}\n\n"
        f"Suggest next hyperparameters. Return ONLY JSON:\n"
        f'{{"learning_rate": float, "batch_size": int, "epochs": int, '
        f'"dropout": float, "reasoning": "string"}}'
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "http://localhost:4001/v1/chat/completions",
                headers={"Authorization": "Bearer sk-dev-proxy-123"},
                json={
                    "model": "text",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,
                    "max_tokens": 300,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            suggestion = json.loads(content)
            logger.info(f"scillm suggests: {suggestion}")
            return suggestion
    except Exception as e:
        logger.warning(f"scillm failed: {e} — heuristic fallback")
        last = rounds_history[-1]["config"] if rounds_history else {}
        return {
            "learning_rate": last.get("lr", 2e-5) * 0.5,
            "batch_size": last.get("batch_size", 32),
            "epochs": last.get("epochs", 3) + 2,
            "dropout": 0.15,
            "reasoning": "Heuristic: halve LR, add epochs",
        }


# ── Single Model Training Loop ───────────────────────────────────────

async def train_model(model_config: dict, result: RunResult) -> None:
    """Run training loop for one model with self-improvement via /scillm."""
    model_id = model_config["id"]
    model_name = model_config["name"]
    log_dir = LOG_BASE / model_id
    log_dir.mkdir(parents=True, exist_ok=True)

    result.status = "running"
    start = time.time()

    # Write training script
    script_path = log_dir / "train.py"
    script_content = TRAIN_SCRIPT.replace("{gate}", str(GATE_ACCURACY))
    script_path.write_text(script_content)

    current_config = dict(model_config)

    # Detect GPU availability via classifier-lab's python
    import subprocess as _sp
    clf_python = str(CLASSIFIER_LAB / ".venv" / "bin" / "python")
    try:
        gpu_check = _sp.run(
            [clf_python, "-c", "import torch; print(torch.cuda.is_available())"],
            capture_output=True, text=True, timeout=10,
        )
        has_gpu = gpu_check.stdout.strip() == "True"
    except Exception:
        has_gpu = False
    logger.info(f"[{model_id}] GPU available: {has_gpu}")

    for round_num in range(1, MAX_ROUNDS + 1):
        current_config["round"] = round_num
        logger.info(f"[{model_id}] Round {round_num}/{MAX_ROUNDS}: {model_name} lr={current_config['lr']} batch={current_config['batch_size']} epochs={current_config['epochs']}")

        # Clean previous result
        result_file = log_dir / "result.json"
        if result_file.exists():
            result_file.unlink()

        # Run training as subprocess
        config_json = json.dumps(current_config)
        clf_python = CLASSIFIER_LAB / ".venv" / "bin" / "python"
        cmd = [str(clf_python), str(script_path), str(log_dir), config_json]

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={**os.environ, "VIRTUAL_ENV": "", "TOKENIZERS_PARALLELISM": "false"},
                    cwd=str(CLASSIFIER_LAB),
                ),
                timeout=10,
            )

            # Stream stdout in real-time
            async def read_stream(stream, label):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode().strip()
                    if text:
                        try:
                            event = json.loads(text)
                            evt = event.get("event", "")
                            if evt == "eval":
                                logger.info(f"[{model_id}] EVAL epoch={event.get('epoch')} accuracy={event.get('accuracy', 0):.4f} f1={event.get('f1', 0):.4f}")
                            elif evt == "done":
                                logger.info(f"[{model_id}] DONE accuracy={event.get('accuracy', 0):.4f} f1={event.get('f1', 0):.4f}")
                            elif evt in ("train_step",):
                                pass  # quiet
                            else:
                                logger.info(f"[{model_id}] {evt}: {text[:150]}")
                        except json.JSONDecodeError:
                            logger.debug(f"[{model_id}] {label}: {text[:200]}")

            stdout_task = asyncio.create_task(read_stream(proc.stdout, "stdout"))
            stderr_task = asyncio.create_task(read_stream(proc.stderr, "stderr"))

            train_timeout = estimate_timeout(
                dataset_size=120000, batch_size=current_config["batch_size"],
                epochs=current_config["epochs"], gpu=has_gpu,
            )
            try:
                returncode = await asyncio.wait_for(proc.wait(), timeout=train_timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                logger.error(f"[{model_id}] Training timed out after {train_timeout}s")
                result.error = f"Training timeout round {round_num}"
                result.status = "timeout"
                return

            await stdout_task
            await stderr_task

        except Exception as e:
            logger.error(f"[{model_id}] Subprocess error: {e}")
            result.error = str(e)
            result.status = "failed"
            return

        # Read result
        if not result_file.exists():
            logger.error(f"[{model_id}] No result.json after round {round_num}")
            result.error = f"No result.json round {round_num}"
            result.status = "failed"
            return

        round_result = json.loads(result_file.read_text())
        accuracy = round_result.get("accuracy", 0)
        f1 = round_result.get("f1", 0)
        gate_passed = round_result.get("gate_passed", False)

        round_data = {
            "round": round_num,
            "accuracy": accuracy,
            "f1": f1,
            "gate_passed": gate_passed,
            "config": dict(current_config),
        }
        result.rounds.append(round_data)
        result.best_accuracy = max(result.best_accuracy, accuracy)
        result.best_f1 = max(result.best_f1, f1)

        logger.info(f"[{model_id}] Round {round_num} result: accuracy={accuracy:.4f} f1={f1:.4f} gate={'PASS' if gate_passed else 'FAIL'}")

        if gate_passed:
            result.gate_passed = True
            result.status = "completed"
            result.total_duration = time.time() - start
            logger.info(f"[{model_id}] GATE PASSED in round {round_num}!")
            return

        if round_num < MAX_ROUNDS:
            # Ask /scillm for next HPs
            logger.info(f"[{model_id}] Below gate — asking /scillm for HP suggestions")
            suggestion = await suggest_hps(model_name, result.rounds, GATE_ACCURACY)
            current_config["lr"] = suggestion.get("learning_rate", current_config["lr"])
            current_config["batch_size"] = suggestion.get("batch_size", current_config["batch_size"])
            current_config["epochs"] = suggestion.get("epochs", current_config["epochs"])
            logger.info(f"[{model_id}] Next round: lr={current_config['lr']} batch={current_config['batch_size']} epochs={current_config['epochs']} reason={suggestion.get('reasoning', 'N/A')}")

    # Exhausted rounds
    result.status = "completed"
    result.total_duration = time.time() - start
    logger.info(f"[{model_id}] Finished {MAX_ROUNDS} rounds. Best accuracy: {result.best_accuracy:.4f}")


# ── Experiment ────────────────────────────────────────────────────────

async def run_experiment() -> dict:
    """Run 3 concurrent training loops. No agents. Just code."""
    logger.info("═══ HARNESS EXPERIMENT: 3 concurrent training loops ═══")
    logger.info(f"Dataset: {DATASET} | Gate: {GATE_ACCURACY} | Max rounds: {MAX_ROUNDS}")

    LOG_BASE.mkdir(parents=True, exist_ok=True)

    results = [RunResult(model_id=m["id"], model_name=m["name"]) for m in MODELS]

    for m in MODELS:
        logger.info(f"  [{m['id']}] {m['name']}: lr={m['lr']} batch={m['batch_size']} epochs={m['epochs']}")

    start = time.time()

    # Launch all 3 concurrently
    tasks = [
        asyncio.create_task(train_model(m, r), name=f"train-{m['id']}")
        for m, r in zip(MODELS, results)
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

    duration = time.time() - start

    # Report
    completed = sum(1 for r in results if r.status == "completed")
    failed = sum(1 for r in results if r.status == "failed")
    timed_out = sum(1 for r in results if r.status == "timeout")
    gate_passed = sum(1 for r in results if r.gate_passed)

    logger.info("═══ RESULTS ═══")
    logger.info(f"  Duration: {duration:.0f}s ({duration/60:.1f}min)")
    logger.info(f"  Completed: {completed}/3 | Failed: {failed} | Timeout: {timed_out}")
    logger.info(f"  Gate passed: {gate_passed}/3")

    for r in results:
        logger.info(
            f"  [{r.model_id}] {r.model_name}: {r.status} "
            f"accuracy={r.best_accuracy:.4f} f1={r.best_f1:.4f} "
            f"rounds={len(r.rounds)} duration={r.total_duration:.0f}s"
        )
        for rd in r.rounds:
            logger.info(f"    round {rd['round']}: accuracy={rd['accuracy']:.4f} f1={rd['f1']:.4f}")

    report = {
        "experiment": "harness-v1",
        "dataset": DATASET,
        "gate": GATE_ACCURACY,
        "max_rounds": MAX_ROUNDS,
        "duration_seconds": duration,
        "completed": completed,
        "failed": failed,
        "timed_out": timed_out,
        "gate_passed": gate_passed,
        "models": [
            {
                "model_id": r.model_id,
                "model_name": r.model_name,
                "status": r.status,
                "best_accuracy": r.best_accuracy,
                "best_f1": r.best_f1,
                "gate_passed": r.gate_passed,
                "duration_seconds": r.total_duration,
                "rounds": r.rounds,
                "error": r.error,
            }
            for r in results
        ],
    }

    print(json.dumps(report, indent=2))
    results_path = SKILL_DIR / "harness_results.json"
    results_path.write_text(json.dumps(report, indent=2))
    logger.info(f"Saved to {results_path}")
    return report


# ── CLI ──────────────────────────────────────────────────────────────

@app.command()
def experiment():
    """Run 3 concurrent training loops — no agents, just code."""
    asyncio.run(run_experiment())


@app.command()
def logs(model_id: str = typer.Option("m0")):
    """Read progress log for a model."""
    progress = LOG_BASE / model_id / "progress.jsonl"
    if progress.exists():
        for line in progress.read_text().splitlines():
            print(line)
    result = LOG_BASE / model_id / "result.json"
    if result.exists():
        print(f"\n=== RESULT ===\n{result.read_text()}")


@app.command()
def results():
    """Show last experiment results."""
    path = SKILL_DIR / "harness_results.json"
    if path.exists():
        print(path.read_text())
    else:
        print("No results. Run 'experiment' first.")


if __name__ == "__main__":
    app()
