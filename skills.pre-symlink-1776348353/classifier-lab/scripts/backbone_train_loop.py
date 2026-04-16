#!/usr/bin/env python3
"""Single-backbone self-improving training loop for Switchboard execution.

90% deterministic code, 10% bounded LLM (/scillm) for HP suggestions.
This is what each Switchboard manifest step runs — one backbone, one loop.

Config JSON (argv[1]):
    name:             HuggingFace model name or sklearn model name
    modality:         vision | text | tabular
    task:             Task description for /scillm context
    data_dir:         Path to data directory or JSONL file
    lr:               Initial learning rate
    batch_size:       Initial batch size
    epochs:           Epochs per round
    gate:             F1 threshold to pass
    max_rounds:       Max self-improvement rounds
    max_train_samples: Max training samples (0 = all)
    log_dir:          Directory for logs, metrics, checkpoints
    project_id:       Project identifier for UX notifications

Outputs:
    {log_dir}/progress.jsonl  — structured events per step
    {log_dir}/result.json     — final result with all rounds
    {log_dir}/metrics.json    — {f1, accuracy} for Switchboard check_metrics

Design pattern: This is the *-lab training loop template.
All *-lab skills that need concurrent backbone racing use this pattern:
    1. Standalone script, one backbone per invocation
    2. Self-improvement loop with /scillm HP suggestions
    3. Writes metrics.json for Switchboard gate check
    4. Sends UX events via httpx for live leaderboard updates
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from loguru import logger

CONFIG = json.loads(sys.argv[1])
LOG_DIR = Path(CONFIG["log_dir"])
LOG_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS = LOG_DIR / "progress.jsonl"
RESULT = LOG_DIR / "result.json"
METRICS = LOG_DIR / "metrics.json"
EVAL_DETAILS = LOG_DIR / "eval_details.json"
TUNE_RESULTS = LOG_DIR / "tune-results.json"

MODALITY = CONFIG.get("modality", "text")
TASK = CONFIG.get("task", "classification")
PROJECT_ID = CONFIG.get("project_id", "unknown")


def log(event: dict) -> None:
    """Append structured event to progress.jsonl and stdout."""
    event["ts"] = time.time()
    with PROGRESS.open("a") as f:
        f.write(json.dumps(event) + "\n")
    print(json.dumps(event), flush=True)


def notify_ux(phase: str, payload: dict) -> None:
    """Best-effort UX notification via agent bus."""
    try:
        import httpx
        httpx.post(
            "http://localhost:3001/api/agent-bus",
            json={"type": "training-update", "payload": {
                "projectId": PROJECT_ID, "phase": phase, **payload,
            }},
            timeout=2,
        )
    except Exception:
        pass


def write_eval_details(payload: dict) -> None:
    """Persist detailed eval payload for EvaluateTab consumption."""
    EVAL_DETAILS.write_text(json.dumps(payload, indent=2))


def build_eval_details(
    *,
    model_name: str,
    macro_f1: float,
    accuracy: float,
    holdout_passed: bool,
    classes: list[str],
    confusion_matrix: list[list[int]],
    per_class: dict[str, dict],
) -> dict:
    supports = [int(metrics.get("support", 0)) for metrics in per_class.values()]
    test_samples = int(sum(supports)) if supports else int(sum(sum(row) for row in confusion_matrix))
    return {
        "model": model_name,
        "macro_f1": float(macro_f1),
        "accuracy": float(accuracy),
        "test_samples": test_samples,
        "holdout_passed": bool(holdout_passed),
        "classes": classes,
        "confusion_matrix": confusion_matrix,
        "per_class": per_class,
    }


def build_tune_results(
    *,
    rounds_history: list[dict],
    model_name: str,
    strategy: str,
    gate: float,
) -> dict:
    trials: list[dict] = []
    for round_metrics in rounds_history:
        f1 = float(round_metrics.get("f1", 0.0))
        trial = int(round_metrics.get("round", len(trials) + 1))
        trials.append({
            "trial": trial,
            "backbone": model_name,
            "epochs": int(round_metrics.get("epochs", 0)),
            "lr": float(round_metrics.get("lr", 0.0)),
            "augment": bool(round_metrics.get("augment", False)),
            "valF1": float(round_metrics.get("val_f1", f1)),
            "testF1": float(round_metrics.get("test_f1", f1)),
            "status": str(round_metrics.get("status", "completed")),
            "passed": bool(round_metrics.get("passed", f1 >= gate)),
        })

    winning_round = 0
    if trials:
        winning_round = max(trials, key=lambda row: (row["testF1"], -row["trial"]))["trial"]

    return {
        "trials": trials,
        "strategy": strategy,
        "winningRound": winning_round,
    }


def ask_scillm_for_hps(model_name: str, rounds_history: list, gate: float) -> dict:
    """Call /scillm for structured HP suggestion with full round history context."""
    import httpx

    history_text = "\n".join(
        f"  Round {r['round']}: lr={r['lr']}, batch={r['batch_size']}, "
        f"epochs={r['epochs']}, dropout={r.get('dropout', 0.1)} "
        f"→ f1={r['f1']:.4f}, accuracy={r['accuracy']:.4f}"
        for r in rounds_history
    )

    prompt = (
        f"Classifier training: {TASK}\n"
        f"Model: {model_name} ({MODALITY} modality)\n"
        f"Target: F1 >= {gate}\n\n"
        f"Full training history (ALL rounds, settings, and results):\n{history_text}\n\n"
        f"Based on the trajectory above, what specific hyperparameters would improve F1?\n"
        f"Consider: learning rate schedule, batch size effects, regularization, "
        f"augmentation if vision, warmup steps, weight decay.\n"
        f"Return ONLY valid JSON:\n"
        f'{{"learning_rate": float, "batch_size": int, "epochs": int, '
        f'"dropout": float, "weight_decay": float, "reasoning": "string"}}'
    )

    try:
        resp = httpx.post(
            "http://localhost:4001/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ.get('SCILLM_KEY', 'sk-dev-proxy-123')}"},
            json={
                "model": "text",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": 400,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        suggestion = json.loads(content)
        log({"event": "scillm_suggestion", "suggestion": suggestion})
        return suggestion
    except Exception as e:
        log({"event": "scillm_error", "error": str(e)})
        last = rounds_history[-1] if rounds_history else {}
        return {
            "learning_rate": last.get("lr", 2e-5) * 0.5,
            "batch_size": last.get("batch_size", 32),
            "epochs": max(last.get("epochs", 2), 2) + 1,
            "dropout": min(last.get("dropout", 0.1) + 0.05, 0.5),
            "weight_decay": 1e-4,
            "reasoning": "Heuristic fallback: halve LR, add epoch, increase dropout",
        }


# ── Modality-specific trainers ───────────────────────────────────────


def train_text_round(model_name: str, lr: float, batch_size: int, epochs: int,
                     dropout: float, weight_decay: float, max_samples: int,
                     round_num: int) -> dict:
    """Train one round of a text classifier via HuggingFace Transformers."""
    import numpy as np
    import torch
    from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

    log({"event": "round_start", "round": round_num, "model": model_name,
         "lr": lr, "batch_size": batch_size, "epochs": epochs,
         "dropout": dropout, "gpu": torch.cuda.is_available()})

    notify_ux("round-start", {
        "round": round_num, "backbone": model_name,
        "lr": lr, "batch_size": batch_size, "epochs": epochs,
    })

    from transformers import (
        AutoModelForSequenceClassification, AutoTokenizer,
        Trainer, TrainingArguments, TrainerCallback,
    )

    data_path = Path(CONFIG["data_dir"])

    class_names: list[str] = []

    # Load data — JSONL or HuggingFace dataset
    if data_path.exists() and data_path.suffix == ".jsonl":
        from datasets import Dataset as HFDataset
        rows = []
        for line in data_path.open():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if max_samples > 0:
            rows = rows[:max_samples]
        labels = sorted(set(r["label"] for r in rows))
        label2id = {l: i for i, l in enumerate(labels)}
        for r in rows:
            r["label"] = label2id[r["label"]]
        ds = HFDataset.from_list(rows)
        split = ds.train_test_split(test_size=0.2, seed=42)
        train_ds, test_ds = split["train"], split["test"]
        num_labels = len(labels)
        class_names = [str(label) for label in labels]
    else:
        from datasets import load_dataset
        dataset_name = CONFIG.get("dataset", "ag_news")
        sample_slice = f"[:{max_samples}]" if max_samples > 0 else ""
        train_ds = load_dataset(dataset_name, split=f"train{sample_slice}")
        test_ds = load_dataset(dataset_name, split="test[:1000]")
        num_labels = len(set(train_ds["label"]))
        label_feature = train_ds.features.get("label")
        if label_feature is not None and hasattr(label_feature, "names") and label_feature.names:
            class_names = [str(name) for name in label_feature.names]
        else:
            class_names = [str(i) for i in range(num_labels)]

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Different model families use different dropout kwargs
    from transformers import AutoConfig
    config = AutoConfig.from_pretrained(model_name, num_labels=num_labels)
    if hasattr(config, "hidden_dropout_prob"):
        config.hidden_dropout_prob = dropout
        config.attention_probs_dropout_prob = dropout
    elif hasattr(config, "seq_classif_dropout"):
        config.seq_classif_dropout = dropout
        config.dropout = dropout
    elif hasattr(config, "dropout"):
        config.dropout = dropout
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, config=config,
    )

    def tokenize(batch):
        return tokenizer(batch["text"], padding="max_length", truncation=True, max_length=128)

    train_tok = train_ds.map(tokenize, batched=True, batch_size=1000)
    test_tok = test_ds.map(tokenize, batched=True, batch_size=1000)
    train_tok.set_format("torch", columns=["input_ids", "attention_mask", "label"])
    test_tok.set_format("torch", columns=["input_ids", "attention_mask", "label"])

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {
            "accuracy": float((preds == labels).mean()),
            "f1": float(f1_score(labels, preds, average="macro")),
        }

    class ProgressCallback(TrainerCallback):
        def on_evaluate(self, args, state, control, metrics=None, **kwargs):
            if metrics:
                log({"event": "eval", "round": round_num, "epoch": state.epoch,
                     "accuracy": metrics.get("eval_accuracy", 0),
                     "f1": metrics.get("eval_f1", 0)})
                notify_ux("eval", {
                    "round": round_num, "backbone": model_name,
                    "epoch": state.epoch,
                    "accuracy": metrics.get("eval_accuracy", 0),
                    "f1": metrics.get("eval_f1", 0),
                })

    out_dir = str(LOG_DIR / f"checkpoints_r{round_num}")
    training_args = TrainingArguments(
        output_dir=out_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=64,
        learning_rate=lr,
        weight_decay=weight_decay,
        eval_strategy="epoch",
        save_strategy="no",
        logging_dir=str(LOG_DIR / "tb_logs"),
        logging_steps=50,
        load_best_model_at_end=False,
        report_to=["tensorboard"],
        fp16=torch.cuda.is_available(),
        dataloader_num_workers=0,
        warmup_ratio=0.1,
    )

    trainer = Trainer(
        model=model, args=training_args,
        train_dataset=train_tok, eval_dataset=test_tok,
        compute_metrics=compute_metrics, callbacks=[ProgressCallback()],
    )
    trainer.train()

    eval_result = trainer.evaluate()
    f1 = eval_result.get("eval_f1", 0)
    accuracy = eval_result.get("eval_accuracy", 0)

    pred_output = trainer.predict(test_tok)
    pred_logits = pred_output.predictions
    pred_labels = pred_output.label_ids
    preds = np.argmax(pred_logits, axis=-1).tolist()
    y_true = pred_labels.tolist() if hasattr(pred_labels, "tolist") else list(pred_labels)

    labels_order = list(range(num_labels))
    cm = confusion_matrix(y_true, preds, labels=labels_order).tolist()
    precision, recall, f1_per_class, support = precision_recall_fscore_support(
        y_true, preds, labels=labels_order, zero_division=0,
    )
    per_class: dict[str, dict] = {}
    for idx in labels_order:
        class_name = class_names[idx] if idx < len(class_names) else str(idx)
        per_class[class_name] = {
            "precision": float(precision[idx]),
            "recall": float(recall[idx]),
            "f1": float(f1_per_class[idx]),
            "support": int(support[idx]),
        }

    eval_details = build_eval_details(
        model_name=model_name,
        macro_f1=float(f1),
        accuracy=float(accuracy),
        holdout_passed=float(f1) >= float(CONFIG.get("gate", 0.90)),
        classes=class_names,
        confusion_matrix=cm,
        per_class=per_class,
    )
    write_eval_details(eval_details)

    log({"event": "round_end", "round": round_num, "accuracy": accuracy, "f1": f1})

    del trainer, model, tokenizer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {"accuracy": accuracy, "f1": f1, "round": round_num,
            "lr": lr, "batch_size": batch_size, "epochs": epochs,
            "dropout": dropout, "weight_decay": weight_decay,
            "val_f1": float(f1), "test_f1": float(f1),
            "augment": bool(CONFIG.get("augment", False)),
            "status": "completed", "passed": float(f1) >= float(CONFIG.get("gate", 0.90))}


def train_vision_round(model_name: str, lr: float, batch_size: int, epochs: int,
                       dropout: float, weight_decay: float, max_samples: int,
                       round_num: int) -> dict:
    """Train one round of a vision classifier via timm + torchvision."""
    import numpy as np
    import torch
    from torch import nn, optim
    from torch.utils.data import DataLoader
    from sklearn.metrics import f1_score

    log({"event": "round_start", "round": round_num, "model": model_name,
         "lr": lr, "batch_size": batch_size, "epochs": epochs,
         "dropout": dropout, "gpu": torch.cuda.is_available()})

    notify_ux("round-start", {
        "round": round_num, "backbone": model_name,
        "lr": lr, "batch_size": batch_size, "epochs": epochs,
    })

    # Delegate to existing benchmark.py which handles all vision data loading
    import subprocess
    skill_dir = Path(__file__).resolve().parent.parent
    output_file = str(LOG_DIR / f"bench_r{round_num}.json")

    cmd = (
        f"cd {skill_dir} && source .venv/bin/activate && "
        f"python scripts/benchmark.py benchmark "
        f"--data-dir {CONFIG['data_dir']} "
        f"--backbones {model_name} "
        f"--epochs {epochs} --lr {lr} --batch-size {batch_size} "
        f"--weight-decay {weight_decay} --dropout {dropout} "
        f"--output-json {output_file}"
    )
    proc = subprocess.run(
        ["bash", "-lc", cmd], capture_output=True, text=True,
        timeout=3600, check=False,
        env={**os.environ, "VIRTUAL_ENV": "", "PYTORCH_ALLOC_CONF": "expandable_segments:True"},
    )

    f1 = 0.0
    accuracy = 0.0
    classes: list[str] = []
    confusion: list[list[int]] = []
    per_class: dict[str, dict] = {}
    if Path(output_file).exists():
        try:
            results = json.loads(Path(output_file).read_text())
            f1 = results.get("selected_metrics", {}).get("macro_f1", 0)
            accuracy = results.get("selected_metrics", {}).get("accuracy", 0)

            winner_name = results.get("selected_backbone", model_name)
            winner = None
            for row in results.get("results", []):
                if row.get("backbone") == winner_name:
                    winner = row
                    break

            selected_metrics = results.get("selected_metrics", {})
            metrics_sources = [selected_metrics, winner or {}]

            for source in metrics_sources:
                maybe_classes = source.get("classes")
                if isinstance(maybe_classes, list) and maybe_classes:
                    classes = [str(item) for item in maybe_classes]
                    break
            for source in metrics_sources:
                maybe_cm = source.get("confusion_matrix")
                if isinstance(maybe_cm, list):
                    confusion = [[int(v) for v in row] for row in maybe_cm if isinstance(row, list)]
                    if confusion:
                        break
            for source in metrics_sources:
                maybe_pc = source.get("per_class")
                if isinstance(maybe_pc, dict):
                    parsed: dict[str, dict] = {}
                    for cls_name, cls_metrics in maybe_pc.items():
                        if not isinstance(cls_metrics, dict):
                            continue
                        parsed[str(cls_name)] = {
                            "precision": float(cls_metrics.get("precision", 0.0)),
                            "recall": float(cls_metrics.get("recall", 0.0)),
                            "f1": float(cls_metrics.get("f1", 0.0)),
                            "support": int(cls_metrics.get("support", 0)),
                        }
                    if parsed:
                        per_class = parsed
                        break

            if not classes and per_class:
                classes = list(per_class.keys())
            if not classes and confusion:
                classes = [str(i) for i in range(len(confusion))]

            eval_details = build_eval_details(
                model_name=model_name,
                macro_f1=float(f1),
                accuracy=float(accuracy),
                holdout_passed=float(f1) >= float(CONFIG.get("gate", 0.90)),
                classes=classes,
                confusion_matrix=confusion,
                per_class=per_class,
            )
            write_eval_details(eval_details)
        except (json.JSONDecodeError, KeyError) as e:
            log({"event": "parse_error", "round": round_num, "error": str(e)})
    else:
        log({"event": "training_failed", "round": round_num,
             "rc": proc.returncode, "stderr": proc.stderr[-500:]})

    log({"event": "round_end", "round": round_num, "accuracy": accuracy, "f1": f1})

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {"accuracy": accuracy, "f1": f1, "round": round_num,
            "lr": lr, "batch_size": batch_size, "epochs": epochs,
            "dropout": dropout, "weight_decay": weight_decay,
            "val_f1": float(f1), "test_f1": float(f1),
            "augment": bool(CONFIG.get("augment", False)),
            "status": "completed", "passed": float(f1) >= float(CONFIG.get("gate", 0.90))}


def train_tabular_round(model_name: str, lr: float, batch_size: int, epochs: int,
                        dropout: float, weight_decay: float, max_samples: int,
                        round_num: int) -> dict:
    """Train one round of a tabular classifier via sklearn."""
    import subprocess

    log({"event": "round_start", "round": round_num, "model": model_name,
         "lr": lr, "batch_size": batch_size, "epochs": epochs})

    notify_ux("round-start", {
        "round": round_num, "backbone": model_name,
    })

    skill_dir = Path(__file__).resolve().parent.parent
    output_file = str(LOG_DIR / f"bench_r{round_num}.json")

    cmd = (
        f"cd {skill_dir} && source .venv/bin/activate && "
        f"python scripts/benchmark.py benchmark "
        f"--labels-jsonl {CONFIG['data_dir']} "
        f"--modality tabular --backbones {model_name} "
        f"--output-json {output_file}"
    )
    proc = subprocess.run(
        ["bash", "-lc", cmd], capture_output=True, text=True,
        timeout=600, check=False,
        env={**os.environ, "VIRTUAL_ENV": ""},
    )

    f1 = 0.0
    accuracy = 0.0
    if Path(output_file).exists():
        try:
            results = json.loads(Path(output_file).read_text())
            f1 = results.get("selected_metrics", {}).get("macro_f1", 0)
            accuracy = results.get("selected_metrics", {}).get("accuracy", 0)
        except (json.JSONDecodeError, KeyError) as e:
            log({"event": "parse_error", "round": round_num, "error": str(e)})

    log({"event": "round_end", "round": round_num, "accuracy": accuracy, "f1": f1})

    return {"accuracy": accuracy, "f1": f1, "round": round_num,
            "lr": lr, "batch_size": batch_size, "epochs": epochs,
            "dropout": dropout, "weight_decay": weight_decay}


# ── Trainer dispatch ─────────────────────────────────────────────────

TRAINERS = {
    "text": train_text_round,
    "vision": train_vision_round,
    "tabular": train_tabular_round,
}


# ── Main loop ────────────────────────────────────────────────────────


def main() -> None:
    model_name = CONFIG["name"]
    lr = CONFIG["lr"]
    batch_size = CONFIG["batch_size"]
    epochs = CONFIG["epochs"]
    gate = CONFIG.get("gate", 0.90)
    max_rounds = CONFIG.get("max_rounds", 5)
    max_samples = CONFIG.get("max_train_samples", 10000)
    dropout = CONFIG.get("dropout", 0.1)
    weight_decay = CONFIG.get("weight_decay", 1e-4)
    strategy = CONFIG.get("strategy", "self-improvement")

    trainer_fn = TRAINERS.get(MODALITY, train_text_round)

    log({"event": "start", "model": model_name, "modality": MODALITY,
         "task": TASK, "gate": gate, "max_rounds": max_rounds})

    notify_ux("backbone-start", {
        "backbone": model_name, "modality": MODALITY,
        "gate": gate, "maxRounds": max_rounds,
    })

    rounds_history: list[dict] = []
    best_f1 = 0.0
    best_accuracy = 0.0

    for round_num in range(1, max_rounds + 1):
        try:
            metrics = trainer_fn(
                model_name, lr, batch_size, epochs,
                dropout, weight_decay, max_samples, round_num,
            )
        except Exception as e:
            log({"event": "error", "round": round_num,
                 "error": str(e), "tb": traceback.format_exc()})
            notify_ux("backbone-error", {
                "backbone": model_name, "round": round_num, "error": str(e),
            })
            RESULT.write_text(json.dumps({"status": "failed", "error": str(e)}))
            METRICS.write_text(json.dumps({"f1": best_f1, "accuracy": best_accuracy}))
            tune_results = build_tune_results(
                rounds_history=rounds_history,
                model_name=model_name,
                strategy=strategy,
                gate=gate,
            )
            TUNE_RESULTS.write_text(json.dumps(tune_results, indent=2))
            sys.exit(1)

        rounds_history.append(metrics)
        best_f1 = max(best_f1, metrics["f1"])
        best_accuracy = max(best_accuracy, metrics["accuracy"])

        notify_ux("round-complete", {
            "backbone": model_name, "round": round_num,
            "f1": metrics["f1"], "accuracy": metrics["accuracy"],
            "bestF1": best_f1, "gatePassed": metrics["f1"] >= gate,
        })

        if metrics["f1"] >= gate:
            log({"event": "gate_passed", "round": round_num, "f1": metrics["f1"]})
            break

        # Below gate — ask /scillm with full history context
        if round_num < max_rounds:
            log({"event": "below_gate", "round": round_num,
                 "f1": metrics["f1"], "gap": gate - metrics["f1"]})

            suggestion = ask_scillm_for_hps(model_name, rounds_history, gate)

            lr = max(1e-6, min(1e-3, float(suggestion.get("learning_rate", lr))))
            batch_size = max(8, min(128, int(suggestion.get("batch_size", batch_size))))
            epochs = max(1, min(20, int(suggestion.get("epochs", epochs))))
            dropout = max(0.0, min(0.5, float(suggestion.get("dropout", dropout))))
            weight_decay = max(1e-6, min(0.1, float(suggestion.get("weight_decay", weight_decay))))

    # Final result
    result = {
        "status": "completed",
        "model": model_name,
        "modality": MODALITY,
        "task": TASK,
        "best_f1": best_f1,
        "best_accuracy": best_accuracy,
        "gate": gate,
        "gate_passed": best_f1 >= gate,
        "rounds_completed": len(rounds_history),
        "rounds_history": rounds_history,
    }
    log({"event": "done", **result})
    RESULT.write_text(json.dumps(result, indent=2))
    METRICS.write_text(json.dumps({"f1": best_f1, "accuracy": best_accuracy}))
    tune_results = build_tune_results(
        rounds_history=rounds_history,
        model_name=model_name,
        strategy=strategy,
        gate=gate,
    )
    TUNE_RESULTS.write_text(json.dumps(tune_results, indent=2))

    notify_ux("backbone-done", {
        "backbone": model_name, "f1": best_f1, "accuracy": best_accuracy,
        "gatePassed": best_f1 >= gate, "rounds": len(rounds_history),
    })


if __name__ == "__main__":
    main()
