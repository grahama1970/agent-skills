#!/usr/bin/env python3
"""Bayesian hyperparameter search using Optuna for LoRA training.

Adapted from create-classifier/scripts/iterative_train.py Phase 1.

Sweeps: learning_rate, weight_decay, lora_r, batch_size, temperature.
Objective: minimize validation loss.
Persists Optuna study to SQLite for resumability.

Usage:
    python hp_search.py search --task qra-validator --trials 15
    python hp_search.py search --task qra-validator --trials 10 --resume
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, MODELS_DIR

app = typer.Typer(add_completion=False)


def objective(trial, spec, train_file: Path, val_file: Path, mock: bool = False) -> float:
    """Optuna objective: train with sampled HPs, return validation loss.

    Returns negative accuracy for minimization (Optuna minimizes by default,
    but we use direction="maximize" so we return accuracy directly).
    """
    # Sample hyperparameters
    lr = trial.suggest_float("learning_rate", 1e-6, 1e-3, log=True)
    weight_decay = trial.suggest_float("weight_decay", 0.0, 0.1)
    lora_r = trial.suggest_categorical("lora_r", [8, 16, 32, 64])
    lora_alpha = trial.suggest_categorical("lora_alpha", [16, 32, 64, 128])
    batch_size = trial.suggest_categorical("batch_size", [2, 4, 8])

    logger.info(
        f"Trial {trial.number}: lr={lr:.2e}, wd={weight_decay:.4f}, "
        f"lora_r={lora_r}, lora_alpha={lora_alpha}, bs={batch_size}"
    )

    if mock:
        # Mock objective for testing
        import random
        accuracy = 0.6 + random.random() * 0.3 + (0.05 if lora_r >= 16 else 0)
        logger.info(f"Trial {trial.number}: mock accuracy={accuracy:.4f}")
        return accuracy

    # Real training
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import Dataset
    from trl import SFTTrainer, SFTConfig

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(spec.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        spec.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )
    model = get_peft_model(model, lora_config)

    # Load data
    with open(train_file) as f:
        train_data = [json.loads(line) for line in f if line.strip()]

    formatted = []
    for item in train_data:
        messages = item.get("messages", [])
        if messages:
            text = tokenizer.apply_chat_template(messages, tokenize=False)
            formatted.append({"text": text})

    dataset = Dataset.from_list(formatted)

    output_dir = MODELS_DIR / spec.name / "hp_search" / f"trial_{trial.number}"
    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=1,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=max(1, 16 // batch_size),
        learning_rate=lr,
        weight_decay=weight_decay,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=50,
        save_strategy="no",
        bf16=torch.cuda.is_available(),
        optim="adamw_8bit",
        gradient_checkpointing=True,
        report_to="none",
        dataset_text_field="text",
        max_length=spec.max_seq_length,
        max_steps=300,  # Quick search
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    trainer.train()

    # Evaluate on validation set
    val_data = []
    with open(val_file) as f:
        val_data = [json.loads(line) for line in f if line.strip()]

    if not val_data:
        return 0.0

    # Quick eval: measure format validity on a sample
    from evaluate import _real_evaluate, compute_metrics
    predictions = _real_evaluate(spec, val_data[:50], output_dir)
    references = []
    for item in val_data[:50]:
        out = item.get("output", {})
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except json.JSONDecodeError:
                out = {}
        references.append({"input": item.get("input", ""), "output": out})

    metrics = compute_metrics(predictions, references, spec.output_schema)
    accuracy = metrics.get("accuracy", 0.0)

    # Cleanup GPU
    del model, trainer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    logger.info(f"Trial {trial.number}: accuracy={accuracy:.4f}")
    return accuracy


@app.command("search")
def search(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    trials: int = typer.Option(15, "--trials", "-n"),
    resume: bool = typer.Option(False, "--resume", help="Resume previous study"),
    mock: bool = typer.Option(False, "--mock", help="Mock HP search"),
    train_file: Optional[Path] = typer.Option(None, "--train-file"),
    val_file: Optional[Path] = typer.Option(None, "--val-file"),
):
    """Run Bayesian hyperparameter search with Optuna."""
    import optuna

    spec = load_task_spec(task)

    from task_spec import DATA_DIR
    if train_file is None:
        train_file = DATA_DIR / spec.name / "sft" / "train.jsonl"
    if val_file is None:
        val_file = DATA_DIR / spec.name / "sft" / "val.jsonl"

    if not train_file.exists():
        logger.error(f"Train file not found: {train_file}")
        raise typer.Exit(code=1)

    logger.info("=" * 60)
    logger.info("PHASE 1: Bayesian Hyperparameter Search")
    logger.info("=" * 60)
    logger.info(f"Task: {spec.name}")
    logger.info(f"Trials: {trials}")
    logger.info(f"Base model: {spec.base_model}")

    study_path = MODELS_DIR / spec.name / "optuna_study.db"
    study_path.parent.mkdir(parents=True, exist_ok=True)

    study = optuna.create_study(
        study_name=f"{spec.name}_hp_search",
        storage=f"sqlite:///{study_path}",
        direction="maximize",
        load_if_exists=resume,
    )

    study.optimize(
        lambda trial: objective(trial, spec, train_file, val_file, mock=mock),
        n_trials=trials,
        show_progress_bar=True,
    )

    best_params = study.best_params
    best_value = study.best_value

    logger.info("\nBest hyperparameters found:")
    logger.info(f"  Accuracy: {best_value:.4f}")
    for key, value in best_params.items():
        logger.info(f"  {key}: {value}")

    # Save best params
    config_path = MODELS_DIR / spec.name / "best_hyperparams.json"
    config_path.write_text(json.dumps({
        "best_accuracy": best_value,
        "hyperparameters": best_params,
        "model": spec.base_model,
        "n_trials": trials,
    }, indent=2))

    logger.info(f"\nSaved to: {config_path}")


if __name__ == "__main__":
    app()
