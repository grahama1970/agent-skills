#!/usr/bin/env python3
"""Concurrent subagent classifier training orchestrator — v2.

Round 1 showed: SSE stream carries agent text tokens, not training metrics.
Subagents were alive (100% heartbeat) but we got zero data back.

v2 fix: Subagents write structured progress to log files AND /memory learn.
Orchestrator reads log files directly. SSE is heartbeat only.

Each subagent step is deterministic:
  Step 1: Run classifier-lab/run.sh e2e --config X
  Step 2: Script writes to /tmp/clf-{id}/progress.jsonl (one JSON line per event)
  Step 3: Orchestrator polls the log file for metrics
  Step 4: If script crashes, subagent reads error, fixes, retries
  Step 5: Final report read from /tmp/clf-{id}/result.json
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

# ── Experiment Configuration ──────────────────────────────────────────

DATASET = "ag_news"
TASK = "AG News topic classification"
GATE_ACCURACY = 0.95
MAX_ROUNDS = 5
LOG_POLL_INTERVAL = 5  # seconds between log file checks
HEARTBEAT_TIMEOUT = 180  # seconds with no new log line → consider dead
WALL_CLOCK_TIMEOUT = 1800  # 30 minutes max per subagent
LOG_BASE = Path("/tmp/clf-experiment")

MODELS = [
    {
        "id": "model-0",
        "name": "distilbert-base-uncased",
        "lr": 2e-5,
        "batch_size": 32,
        "epochs": 3,
    },
    {
        "id": "model-1",
        "name": "prajjwal1/bert-tiny",
        "lr": 5e-5,
        "batch_size": 64,
        "epochs": 5,
    },
    {
        "id": "model-2",
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "lr": 3e-5,
        "batch_size": 32,
        "epochs": 4,
    },
]


# ── Data Classes ──────────────────────────────────────────────────────

@dataclass
class SubagentResult:
    """Result from a single subagent run."""
    model_id: str
    model_name: str
    status: str = "pending"  # pending | running | completed | failed | blocked | timeout
    final_f1: float = 0.0
    final_accuracy: float = 0.0
    rounds_completed: int = 0
    gate_passed: bool = False
    error: str = ""
    duration_seconds: float = 0.0
    log_lines_read: int = 0
    last_log_ts: float = 0.0
    round_history: list[dict] = field(default_factory=list)


@dataclass
class ExperimentResult:
    """Aggregate result from the full experiment."""
    total_subagents: int = 3
    completed: int = 0
    failed: int = 0
    blocked: int = 0
    timed_out: int = 0
    gate_passed: int = 0
    reliability_rate: float = 0.0
    results: list[SubagentResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0


# ── Log File Protocol ─────────────────────────────────────────────────
#
# The subagent prompt tells the agent to ensure the training script writes to:
#   /tmp/clf-experiment/{model_id}/progress.jsonl  — one JSON line per event
#   /tmp/clf-experiment/{model_id}/result.json     — final result
#
# progress.jsonl line format:
#   {"event": "round_start|round_end|error|blocked|done", "round": N, ...metrics}
#
# result.json format:
#   {"f1": float, "accuracy": float, "rounds": int, "holdout_passed": bool, ...}


def get_log_dir(model_id: str) -> Path:
    """Return the log directory for a model."""
    return LOG_BASE / model_id


def read_progress(model_id: str, after_line: int = 0) -> list[dict]:
    """Read new lines from progress.jsonl starting after line N."""
    progress_file = get_log_dir(model_id) / "progress.jsonl"
    if not progress_file.exists():
        return []
    lines = []
    try:
        with progress_file.open() as f:
            for i, raw in enumerate(f):
                if i < after_line:
                    continue
                raw = raw.strip()
                if raw:
                    try:
                        lines.append(json.loads(raw))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return lines


def read_result(model_id: str) -> dict | None:
    """Read the final result.json if it exists."""
    result_file = get_log_dir(model_id) / "result.json"
    if not result_file.exists():
        return None
    try:
        return json.loads(result_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ── Subagent Prompt ───────────────────────────────────────────────────

def build_subagent_prompt(model_config: dict) -> str:
    """Build deterministic step-by-step prompt for the subagent."""
    model_id = model_config["id"]
    model_name = model_config["name"]
    log_dir = get_log_dir(model_id)

    return f"""You are running a classifier training experiment. Follow these steps EXACTLY.

## Step 1: Create log directory

mkdir -p {log_dir}

## Step 2: Create the training wrapper script

Write this file to {log_dir}/train.py:

```python
#!/usr/bin/env python3
\"\"\"Training wrapper that logs structured progress to JSONL.\"\"\"
import json, os, sys, time
from pathlib import Path

LOG_DIR = Path("{log_dir}")
PROGRESS = LOG_DIR / "progress.jsonl"
RESULT = LOG_DIR / "result.json"

def log_event(event: dict):
    event["ts"] = time.time()
    with PROGRESS.open("a") as f:
        f.write(json.dumps(event) + "\\n")

def main():
    log_event({{"event": "start", "model": "{model_name}", "dataset": "ag_news"}})

    # Add classifier-lab to path
    sys.path.insert(0, "{CLASSIFIER_LAB / 'scripts'}")
    os.chdir("{CLASSIFIER_LAB}")

    try:
        from datasets import load_dataset
        log_event({{"event": "loading_dataset"}})
        train_ds = load_dataset("ag_news", split="train")
        test_ds = load_dataset("ag_news", split="test")
        log_event({{"event": "dataset_loaded", "train_size": len(train_ds), "test_size": len(test_ds), "n_classes": 4}})
    except Exception as e:
        log_event({{"event": "error", "step": "dataset", "error": str(e)}})
        RESULT.write_text(json.dumps({{"status": "failed", "error": str(e)}}))
        return

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, TrainingArguments, Trainer
        import numpy as np

        log_event({{"event": "loading_model", "model": "{model_name}"}})
        tokenizer = AutoTokenizer.from_pretrained("{model_name}")
        model = AutoModelForSequenceClassification.from_pretrained("{model_name}", num_labels=4)

        def tokenize(batch):
            return tokenizer(batch["text"], padding="max_length", truncation=True, max_length=128)

        log_event({{"event": "tokenizing"}})
        train_tok = train_ds.map(tokenize, batched=True, batch_size=1000)
        test_tok = test_ds.map(tokenize, batched=True, batch_size=1000)
        train_tok.set_format("torch", columns=["input_ids", "attention_mask", "label"])
        test_tok.set_format("torch", columns=["input_ids", "attention_mask", "label"])

        def compute_metrics(eval_pred):
            logits, labels = eval_pred
            preds = np.argmax(logits, axis=-1)
            acc = (preds == labels).mean()
            # Macro F1
            from sklearn.metrics import f1_score
            f1 = f1_score(labels, preds, average="macro")
            return {{"accuracy": float(acc), "f1": float(f1)}}

        training_args = TrainingArguments(
            output_dir=str(LOG_DIR / "checkpoints"),
            num_train_epochs={model_config['epochs']},
            per_device_train_batch_size={model_config['batch_size']},
            per_device_eval_batch_size=64,
            learning_rate={model_config['lr']},
            eval_strategy="epoch",
            save_strategy="epoch",
            logging_dir=str(LOG_DIR / "tb_logs"),
            logging_steps=100,
            load_best_model_at_end=True,
            metric_for_best_model="f1",
            report_to=["tensorboard"],
            fp16=torch.cuda.is_available(),
        )

        class ProgressCallback:
            def on_epoch_end(self, args, state, control, metrics=None, **kwargs):
                if metrics:
                    log_event({{
                        "event": "epoch_end",
                        "epoch": state.epoch,
                        "loss": metrics.get("train_loss", 0),
                        "eval_accuracy": metrics.get("eval_accuracy", 0),
                        "eval_f1": metrics.get("eval_f1", 0),
                    }})

        log_event({{"event": "training_start", "epochs": {model_config['epochs']}, "lr": {model_config['lr']}, "batch_size": {model_config['batch_size']}}})

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_tok,
            eval_dataset=test_tok,
            compute_metrics=compute_metrics,
            callbacks=[ProgressCallback()],
        )
        trainer.train()

        log_event({{"event": "training_complete"}})

        # Final evaluation
        log_event({{"event": "evaluating"}})
        eval_result = trainer.evaluate()
        f1 = eval_result.get("eval_f1", 0)
        accuracy = eval_result.get("eval_accuracy", 0)
        gate_passed = accuracy >= {GATE_ACCURACY}

        log_event({{
            "event": "eval_complete",
            "f1": f1,
            "accuracy": accuracy,
            "gate_passed": gate_passed,
        }})

        result = {{
            "status": "completed",
            "model": "{model_name}",
            "f1": f1,
            "accuracy": accuracy,
            "rounds": 1,
            "holdout_passed": gate_passed,
            "epochs": {model_config['epochs']},
            "lr": {model_config['lr']},
            "batch_size": {model_config['batch_size']},
        }}
        RESULT.write_text(json.dumps(result, indent=2))
        log_event({{"event": "done", **result}})

    except Exception as e:
        import traceback
        log_event({{"event": "error", "step": "training", "error": str(e), "traceback": traceback.format_exc()}})
        RESULT.write_text(json.dumps({{"status": "failed", "error": str(e)}}))

if __name__ == "__main__":
    main()
```

## Step 3: Run the training script

```bash
cd {CLASSIFIER_LAB} && source .venv/bin/activate && python {log_dir}/train.py
```

## Step 4: If Step 3 fails

1. Read the error from {log_dir}/progress.jsonl (last line)
2. Fix the issue (missing import, wrong path, etc.)
3. Update train.py with the fix
4. Rerun Step 3
5. If still failing after 3 attempts, write to {log_dir}/result.json:
   {{"status": "blocked", "error": "<description>"}}

## Step 5: Verify completion

Read {log_dir}/result.json and confirm it contains f1 and accuracy values.

## RULES
- Do NOT modify the training logic or hyperparameters
- Do NOT skip writing the log files — they are how the orchestrator tracks you
- Every significant action MUST produce a line in progress.jsonl
- If you are stuck, write {{"event": "blocked", "reason": "..."}} to progress.jsonl
"""


# ── Subagent Lifecycle ────────────────────────────────────────────────

async def start_subagent(
    instance_name: str,
    model_config: dict,
    result: SubagentResult,
) -> None:
    """Start a subagent and monitor via log files (not SSE content)."""
    import subprocess

    model_id = model_config["id"]
    result.status = "running"
    start = time.time()

    # Clean previous log dir
    log_dir = get_log_dir(model_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    for f in log_dir.iterdir():
        if f.suffix in (".jsonl", ".json"):
            f.unlink()

    prompt = build_subagent_prompt(model_config)
    logger.info(f"[{instance_name}] Starting subagent for {model_config['name']}")
    logger.info(f"[{instance_name}] Log dir: {log_dir}")

    # Use scillm API on port 4001 instead of subagent-service containers
    port = 4001
    logger.info(f"[{instance_name}] Using scillm API on port {port}")

    # Send prompt via SSE (fire and forget — we read from log files)
    sse_task = asyncio.create_task(
        _stream_sse(instance_name, port, prompt, result),
        name=f"sse-{instance_name}",
    )

    # Poll log files for progress
    poll_task = asyncio.create_task(
        _poll_logs(instance_name, model_id, result, start),
        name=f"poll-{instance_name}",
    )

    # Wait for either: SSE completes (subagent done) or poll finds result.json
    done, pending = await asyncio.wait(
        [sse_task, poll_task],
        return_when=asyncio.FIRST_COMPLETED,
        timeout=WALL_CLOCK_TIMEOUT,
    )

    # Cancel remaining tasks
    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    # If timeout hit
    if not done:
        result.status = "timeout"
        result.error = f"Wall-clock timeout after {WALL_CLOCK_TIMEOUT}s"
        logger.warning(f"[{instance_name}] {result.error}")

    # Read final result from file
    final = read_result(model_id)
    if final:
        result.final_f1 = final.get("f1", 0.0)
        result.final_accuracy = final.get("accuracy", 0.0)
        result.rounds_completed = final.get("rounds", 0)
        result.gate_passed = final.get("holdout_passed", False)
        if final.get("status") == "blocked":
            result.status = "blocked"
            result.error = final.get("error", "Unknown block")
        elif final.get("status") == "failed":
            result.status = "failed"
            result.error = final.get("error", "Unknown failure")
        elif result.status == "running":
            result.status = "completed"
    elif result.status == "running":
        result.status = "failed"
        result.error = "No result.json produced"

    result.duration_seconds = time.time() - start
    logger.info(
        f"[{instance_name}] DONE: status={result.status} "
        f"accuracy={result.final_accuracy:.4f} F1={result.final_f1:.4f} "
        f"rounds={result.rounds_completed} duration={result.duration_seconds:.0f}s "
        f"log_lines={result.log_lines_read}"
    )


async def _stream_sse(
    instance_name: str,
    port: int,
    prompt: str,
    result: SubagentResult,
) -> None:
    """Stream SSE from subagent. Used as heartbeat only — metrics come from log files."""
    stream_timeout = httpx.Timeout(
        WALL_CLOCK_TIMEOUT + 60,
        connect=10.0,
        read=float(HEARTBEAT_TIMEOUT),
    )
    event_count = 0
    try:
        async with httpx.AsyncClient(timeout=stream_timeout) as client:
            request_body = {
                "model": "text",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are running a classifier training experiment. "
                            "Follow the steps EXACTLY as written. Do not improvise. "
                            "Write the train.py script, run it, and fix any errors. "
                            "The log files are how the orchestrator tracks your progress."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 8192,
                "stream": True,
            }
            async with client.stream(
                "POST",
                f"http://localhost:{port}/v1/chat/completions",
                headers={"Authorization": "Bearer sk-dev-proxy-123"},
                json=request_body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        event_count += 1
                        if event_count % 50 == 0:
                            logger.debug(f"[{instance_name}] SSE heartbeat: {event_count} events")
    except httpx.ReadTimeout:
        logger.warning(f"[{instance_name}] SSE read timeout (heartbeat dead)")
    except httpx.RemoteProtocolError as e:
        logger.warning(f"[{instance_name}] SSE container crashed: {e}")
    except httpx.ConnectError as e:
        logger.warning(f"[{instance_name}] SSE connect failed: {e}")
    except Exception as e:
        logger.warning(f"[{instance_name}] SSE unexpected: {e}")

    logger.info(f"[{instance_name}] SSE stream ended after {event_count} events")


async def _poll_logs(
    instance_name: str,
    model_id: str,
    result: SubagentResult,
    start_time: float,
) -> None:
    """Poll log files for progress. Returns when result.json appears or timeout."""
    last_line_count = 0
    last_new_data_ts = time.time()

    while True:
        await asyncio.sleep(LOG_POLL_INTERVAL)

        # Read new progress lines
        new_lines = read_progress(model_id, after_line=last_line_count)
        if new_lines:
            last_new_data_ts = time.time()
            for line in new_lines:
                last_line_count += 1
                result.log_lines_read = last_line_count
                result.last_log_ts = time.time()

                event = line.get("event", "")
                logger.info(f"[{instance_name}] LOG: {json.dumps(line)[:200]}")

                # Track round history
                if event == "epoch_end":
                    result.round_history.append(line)
                    result.final_f1 = max(result.final_f1, line.get("eval_f1", 0))
                    result.final_accuracy = max(result.final_accuracy, line.get("eval_accuracy", 0))
                elif event == "eval_complete":
                    result.final_f1 = max(result.final_f1, line.get("f1", 0))
                    result.final_accuracy = max(result.final_accuracy, line.get("accuracy", 0))
                    result.gate_passed = line.get("gate_passed", False)
                elif event == "done":
                    result.rounds_completed = line.get("rounds", 1)
                    logger.info(f"[{instance_name}] Training DONE via log file")
                    return  # Signal completion
                elif event == "blocked":
                    result.status = "blocked"
                    result.error = line.get("reason", "Unknown block")
                    return
                elif event == "error":
                    logger.warning(f"[{instance_name}] Error in training: {line.get('error', '')[:200]}")

        # Check if result.json appeared (script finished)
        final = read_result(model_id)
        if final:
            logger.info(f"[{instance_name}] result.json found")
            return

        # Heartbeat check: no new log lines for HEARTBEAT_TIMEOUT
        if time.time() - last_new_data_ts > HEARTBEAT_TIMEOUT:
            logger.warning(f"[{instance_name}] No new log data for {HEARTBEAT_TIMEOUT}s — declaring dead")
            result.status = "timeout"
            result.error = f"No log activity for {HEARTBEAT_TIMEOUT}s"
            return

        # Wall-clock check
        if time.time() - start_time > WALL_CLOCK_TIMEOUT:
            result.status = "timeout"
            result.error = f"Wall-clock timeout after {WALL_CLOCK_TIMEOUT}s"
            return


def _extract_port(stdout: str, instance_name: str) -> int | None:
    """Extract subagent port from run.sh output."""
    import subprocess

    # Try parsing lines
    for line in stdout.splitlines():
        if "port" in line.lower():
            for word in line.split():
                if word.isdigit() and 8620 <= int(word) <= 8650:
                    return int(word)

    # Try JSON
    try:
        data = json.loads(stdout.strip())
        if "port" in data:
            return int(data["port"])
    except (json.JSONDecodeError, AttributeError, ValueError):
        pass

    # Fallback: use scillm default port
    return 4001


# ── Preflight ─────────────────────────────────────────────────────────

async def preflight_check() -> bool:
    """Verify everything works before dispatching subagents."""
    import subprocess

    logger.info("═══ PREFLIGHT CHECK ═══")

    # 1. classifier-lab exists
    if not (CLASSIFIER_LAB / "run.sh").exists():
        logger.error("classifier-lab/run.sh not found")
        return False
    logger.info("classifier-lab: OK")

    # 2. scillm health
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:4001/health/liveliness")
            if resp.status_code == 200:
                logger.info("scillm: OK")
            else:
                logger.warning("scillm: not healthy (heuristic fallback)")
    except Exception:
        logger.warning("scillm: unreachable (heuristic fallback)")

    # 3. Dataset cached (subagent-service removed, using scillm directly)
    clf_python = CLASSIFIER_LAB / ".venv" / "bin" / "python"
    test_script = (
        "import json; from datasets import load_dataset; "
        "ds = load_dataset('ag_news', split='test[:10]'); "
        "print(json.dumps({'n': len(ds), 'labels': ds.features['label'].names}))"
    )
    cmd = [str(clf_python), "-c", test_script] if clf_python.exists() else [
        "uv", "run", "--project", str(CLASSIFIER_LAB), "python", "-c", test_script
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                              env={**os.environ, "VIRTUAL_ENV": ""})
        if proc.returncode != 0:
            logger.error(f"Dataset load failed: {proc.stderr[:300]}")
            return False
        logger.info(f"Dataset: {proc.stdout.strip()}")
    except subprocess.TimeoutExpired:
        logger.error("Dataset load timed out")
        return False

    # 5. Log dir writable
    test_dir = LOG_BASE / "preflight-test"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "test.jsonl"
    test_file.write_text('{"event": "preflight"}\n')
    if not test_file.exists():
        logger.error(f"Cannot write to {LOG_BASE}")
        return False
    test_file.unlink()
    test_dir.rmdir()
    logger.info(f"Log dir: {LOG_BASE} writable")

    logger.info("═══ PREFLIGHT PASSED ═══")
    return True


# ── Main Experiment ──────────────────────────────────────────────────

async def run_experiment() -> ExperimentResult:
    """Run 3 concurrent subagent classifier training loops."""
    experiment = ExperimentResult(start_time=time.time())

    if not await preflight_check():
        logger.error("Preflight failed — aborting")
        experiment.end_time = time.time()
        return experiment

    results = [SubagentResult(model_id=m["id"], model_name=m["name"]) for m in MODELS]
    experiment.results = results

    logger.info("═══ LAUNCHING 3 CONCURRENT SUBAGENTS ═══")
    for m in MODELS:
        logger.info(f"  [{m['id']}] {m['name']}: lr={m['lr']}, batch={m['batch_size']}, epochs={m['epochs']}")

    tasks = []
    for model, result in zip(MODELS, results):
        instance = f"clf-{model['id']}"
        task = asyncio.create_task(
            start_subagent(instance, model, result),
            name=f"subagent-{model['id']}",
        )
        tasks.append(task)

    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=WALL_CLOCK_TIMEOUT + 120,
        )
    except asyncio.TimeoutError:
        logger.error("Overall timeout — cancelling remaining subagents")
        for task in tasks:
            if not task.done():
                task.cancel()

    # Aggregate
    for r in results:
        if r.status == "completed":
            experiment.completed += 1
        elif r.status == "failed":
            experiment.failed += 1
        elif r.status == "blocked":
            experiment.blocked += 1
        elif r.status in ("timeout", "pending"):
            experiment.timed_out += 1
        if r.gate_passed:
            experiment.gate_passed += 1

    experiment.reliability_rate = experiment.completed / max(experiment.total_subagents, 1)
    experiment.end_time = time.time()
    duration = experiment.end_time - experiment.start_time

    # Report
    logger.info("═══ EXPERIMENT RESULTS ═══")
    logger.info(f"  Duration: {duration:.0f}s ({duration/60:.1f}min)")
    logger.info(f"  Completed: {experiment.completed}/{experiment.total_subagents}")
    logger.info(f"  Failed: {experiment.failed}")
    logger.info(f"  Blocked: {experiment.blocked}")
    logger.info(f"  Timed out: {experiment.timed_out}")
    logger.info(f"  Gate passed (>={GATE_ACCURACY}): {experiment.gate_passed}")
    logger.info(f"  RELIABILITY RATE: {experiment.reliability_rate:.0%}")

    for r in results:
        logger.info(
            f"  [{r.model_id}] {r.model_name}: status={r.status} "
            f"accuracy={r.final_accuracy:.4f} F1={r.final_f1:.4f} "
            f"rounds={r.rounds_completed} duration={r.duration_seconds:.0f}s "
            f"log_lines={r.log_lines_read}"
        )
        if r.error:
            logger.info(f"    error: {r.error}")

    report = {
        "experiment": "classifier-lab-subagent-v2",
        "dataset": DATASET,
        "gate": GATE_ACCURACY,
        "duration_seconds": duration,
        "reliability_rate": experiment.reliability_rate,
        "completed": experiment.completed,
        "failed": experiment.failed,
        "blocked": experiment.blocked,
        "timed_out": experiment.timed_out,
        "gate_passed": experiment.gate_passed,
        "models": [
            {
                "model_id": r.model_id,
                "model_name": r.model_name,
                "status": r.status,
                "accuracy": r.final_accuracy,
                "f1": r.final_f1,
                "rounds": r.rounds_completed,
                "gate_passed": r.gate_passed,
                "duration_seconds": r.duration_seconds,
                "log_lines": r.log_lines_read,
                "round_history": r.round_history,
                "error": r.error,
            }
            for r in results
        ],
    }
    print(json.dumps(report, indent=2))

    results_path = SKILL_DIR / "results.json"
    results_path.write_text(json.dumps(report, indent=2))
    logger.info(f"Results saved to {results_path}")

    return experiment


# ── CLI ──────────────────────────────────────────────────────────────

@app.command()
def experiment():
    """Run the full 3-concurrent subagent experiment."""
    asyncio.run(run_experiment())


@app.command()
def preflight():
    """Run preflight checks only."""
    passed = asyncio.run(preflight_check())
    print(f"PREFLIGHT: {'PASS' if passed else 'FAIL'}")
    if not passed:
        raise typer.Exit(1)


@app.command()
def single(model: str = typer.Option("distilbert-base-uncased")):
    """Run a single model locally (no subagent) for testing."""
    import subprocess
    cmd = [
        str(CLASSIFIER_LAB / "run.sh"), "e2e",
        "--task", f"AG News ({model})", "--dataset", DATASET,
        "--modality", "text", "--backbones", model,
        "--gate-f1", str(GATE_ACCURACY), "--max-rounds", str(MAX_ROUNDS),
    ]
    logger.info(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(CLASSIFIER_LAB))


@app.command()
def results():
    """Show results from the last experiment."""
    path = SKILL_DIR / "results.json"
    if not path.exists():
        print("No results. Run 'experiment' first.")
        raise typer.Exit(1)
    print(path.read_text())


@app.command()
def logs(model_id: str = typer.Option("model-0")):
    """Read progress log for a model."""
    lines = read_progress(model_id)
    for line in lines:
        print(json.dumps(line))
    final = read_result(model_id)
    if final:
        print(f"\n=== RESULT ===\n{json.dumps(final, indent=2)}")


if __name__ == "__main__":
    app()
