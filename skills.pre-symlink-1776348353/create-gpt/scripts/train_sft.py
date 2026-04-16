#!/usr/bin/env python3
"""QLoRA SFT training for task-specific small GPTs.

Adapted from create-intent-map/scripts/train_grpo.py warmup command.

Usage:
    python train_sft.py train --task qra-validator --sft-only --mock
    python train_sft.py train --task qra-validator
    python train_sft.py train --task qra-validator --target flash
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, DATA_DIR, MODELS_DIR

app = typer.Typer(add_completion=False)


def _extract_model_size_b(model_name: str) -> float:
    """Extract parameter count in billions from model name string."""
    import re
    m = re.search(r'(\d+(?:\.\d+)?)[bB]', model_name)
    return float(m.group(1)) if m else 1.7  # default to 1.7B if unparseable


def _mock_train(spec, train_data: list[dict], output_dir: Path) -> dict:
    """Mock training for testing without GPU."""
    import random

    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = {
        "accuracy": 0.80 + random.random() * 0.15,
        "format_valid": 0.90 + random.random() * 0.10,
        "loss": 0.5 + random.random() * 0.5,
        "train_samples": len(train_data),
        "mock": True,
    }

    # Save mock model marker
    (output_dir / "mock_model.json").write_text(
        json.dumps({"task": spec.name, "base_model": spec.base_model, **metrics}, indent=2)
    )

    logger.info(f"Mock training complete: accuracy={metrics['accuracy']:.3f}")
    return metrics


def _real_sft_train(spec, train_file: Path, output_dir: Path, epochs: int) -> dict:
    """Real QLoRA SFT training."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import Dataset
    from trl import SFTTrainer, SFTConfig

    lora_r = spec.get_training_param("lora_r", 16)
    lora_alpha = spec.get_training_param("lora_alpha", 32)

    logger.info(f"Loading base model: {spec.base_model}")

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

    # Load training data
    with open(train_file) as f:
        data = [json.loads(line) for line in f if line.strip()]

    # Format for SFT - apply chat template
    formatted = []
    for item in data:
        messages = item.get("messages", [])
        if not messages:
            continue
        text = tokenizer.apply_chat_template(messages, tokenize=False)
        formatted.append({"text": text})

    dataset = Dataset.from_list(formatted)

    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=10,
        save_strategy="epoch",
        bf16=torch.cuda.is_available(),
        optim="adamw_8bit",
        gradient_checkpointing=True,
        report_to="tensorboard",
        dataset_text_field="text",
        max_length=spec.max_seq_length,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    trainer.train()
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    logger.info(f"SFT training complete. Model saved to {output_dir}")
    return {"train_samples": len(formatted), "epochs": epochs, "mock": False}


def _flash_submit_sft(
    task: str,
    sft_only: bool,
    mock: bool,
    epochs: int,
    train_file: Optional[Path],
    output_dir: Optional[Path],
    grpo_steps: int,
    use_wandb: bool,
) -> Path:
    """Package train_sft.py and submit it to RunPod via FlashTrainer.

    Polls until the pod reaches a terminal state, then downloads the
    checkpoint to ``output_dir`` (or a temp directory).

    Returns the local path where the checkpoint was written.
    """
    skills_root = Path.home() / ".pi" / "skills"
    if str(skills_root) not in sys.path:
        sys.path.insert(0, str(skills_root))

    from common.flash_trainer import FlashTrainer, estimate_gpu  # type: ignore[import]

    # Reconstruct CLI args for the remote invocation (--target local is the default)
    remote_args: list[str] = ["train", f"--task={task}", f"--epochs={epochs}",
                               f"--grpo-steps={grpo_steps}"]
    if sft_only:
        remote_args.append("--sft-only")
    if mock:
        remote_args.append("--mock")
    if train_file:
        remote_args.append(f"--train-file={train_file}")
    if use_wandb:
        remote_args.append("--wandb")
    # Checkpoint output on the pod's network volume
    remote_output = "/runpod-volume/checkpoints"
    remote_args.append(f"--output={remote_output}")

    # Extract model size from task spec for GPU estimation
    from task_spec import load_task_spec
    spec = load_task_spec(task)
    model_size = _extract_model_size_b(spec.base_model)
    gpu_type = estimate_gpu(model_size, method="lora")
    trainer = FlashTrainer()

    script_path = Path(__file__).resolve()
    # Try estimated GPU, fall back to alternatives if unavailable
    gpu_fallbacks = [gpu_type, "NVIDIA RTX A6000", "NVIDIA L40S",
                     "NVIDIA GeForce RTX 3090", "NVIDIA A40"]
    job_id = None
    for gpu in gpu_fallbacks:
        try:
            job_id = trainer.submit_training_job(
                script_path=script_path,
                args=remote_args,
                gpu_type=gpu,
            )
            logger.info(f"Pod created on {gpu}")
            break
        except Exception as exc:
            logger.warning(f"GPU {gpu} unavailable: {exc}")
            continue
    if job_id is None:
        raise RuntimeError("All RunPod GPU types unavailable. Try again later or use --target local.")
    logger.info(f"Flash job submitted: {job_id}")

    terminal_states = {"EXITED", "TERMINATED", "FAILED", "DEAD"}
    while True:
        status = trainer.poll_status(job_id)
        state = status.get("state", "").upper()
        logger.info(f"Job {job_id} state: {state}")
        if state in terminal_states:
            logger.info(f"Job {job_id} finished with state: {state}")
            break
        time.sleep(30)

    local_ckpt = output_dir if output_dir else Path(f"/tmp/flash-sft-{job_id}")
    trainer.download_checkpoint(job_id, local_ckpt, remote_checkpoint_dir=remote_output)
    logger.success(f"SFT checkpoint downloaded to {local_ckpt}")
    return local_ckpt


@app.command()
def train(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    sft_only: bool = typer.Option(False, "--sft-only", help="Only run SFT (no GRPO)"),
    mock: bool = typer.Option(False, "--mock", help="Mock training (no GPU)"),
    epochs: int = typer.Option(1, "--epochs", "-e"),
    train_file: Optional[Path] = typer.Option(None, "--train-file"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    grpo_steps: int = typer.Option(2000, "--grpo-steps", "-s"),
    use_wandb: bool = typer.Option(False, "--wandb/--no-wandb"),
    target: str = typer.Option("local", "--target", help="Training target: local or flash (RunPod GPU)"),
):
    """Train a task-specific GPT model.

    Supports SFT-only mode (--sft-only) and mock mode (--mock) for testing.
    Without --sft-only, runs SFT warmup followed by GRPO training.
    Use --target flash to submit the job to RunPod (requires RUNPOD_API_KEY).
    """
    if target == "flash":
        _flash_submit_sft(
            task=task,
            sft_only=sft_only,
            mock=mock,
            epochs=epochs,
            train_file=train_file,
            output_dir=output_dir,
            grpo_steps=grpo_steps,
            use_wandb=use_wandb,
        )
        return

    spec = load_task_spec(task)

    if train_file is None:
        train_file = DATA_DIR / spec.name / "sft" / "train.jsonl"
    if output_dir is None:
        output_dir = MODELS_DIR / spec.name / "sft"

    logger.info(f"Training task: {spec.name}")
    logger.info(f"Base model: {spec.base_model}")
    logger.info(f"SFT only: {sft_only}")
    logger.info(f"Mock: {mock}")

    monitor = TaskClient(f"create-gpt/sft/{spec.name}", total=1, description=f"SFT training {spec.name}") if TaskClient else None

    if mock:
        with open(train_file) as f:
            data = [json.loads(line) for line in f if line.strip()]
        metrics = _mock_train(spec, data, output_dir)
    else:
        if not train_file.exists():
            logger.error(f"Training file not found: {train_file}")
            raise typer.Exit(code=1)

        metrics = _real_sft_train(spec, train_file, output_dir, epochs)

    # Save training config
    config = {
        "task": spec.name,
        "base_model": spec.base_model,
        "sft_only": sft_only,
        "mock": mock,
        "epochs": epochs,
        "metrics": metrics,
    }
    config_path = output_dir / "training_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))

    if monitor:
        monitor.update(item=f"done epochs={epochs}")
        monitor.finish()

    if not sft_only and not mock:
        logger.info("SFT warmup complete. Run GRPO next:")
        logger.info(f"  python train_grpo.py grpo --task {task} --warmup-model {output_dir}")

    logger.info("Training complete!")


if __name__ == "__main__":
    app()
