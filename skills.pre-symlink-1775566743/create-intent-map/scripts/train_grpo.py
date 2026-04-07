#!/usr/bin/env python3
"""GRPO Training for SPARTA Intent Mapper with Execution Feedback.

Trains a LoRA adapter using Group Relative Policy Optimization (GRPO)
with reward signals from actual ArangoDB query execution.

This implements the DeepSeek R1 training paradigm:
- No value network (memory efficient)
- Group-relative advantage estimation
- Execution feedback as ground truth reward

Usage:
    # With SFT warmup (recommended)
    python train_grpo.py warmup --train-file data/sft/train.jsonl --epochs 1
    python train_grpo.py grpo --query-file data/queries.txt --steps 2000

    # Direct GRPO (if model already has some capability)
    python train_grpo.py grpo --query-file data/queries.txt --steps 2000
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import torch
import typer
from loguru import logger

app = typer.Typer()

# Evaluation thresholds for pass/fail
EVAL_THRESHOLDS = {
    "accuracy": 0.80,
    "entity_f1": 0.70,
    "avg_grounding": 0.75,
    "format_valid": 0.95,
}

# Hyperparameter adjustments for retry attempts
RETRY_ADJUSTMENTS = [
    {"learning_rate": 2e-6, "beta": 0.02},   # Retry 1: Lower LR, higher KL penalty
    {"learning_rate": 1e-5, "beta": 0.005},  # Retry 2: Medium LR, lower KL
    {"num_generations": 4, "temperature": 0.5},  # Retry 3: Same generations (must divide batch), less exploration
]

# Default config
DEFAULT_BASE_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
DEFAULT_OUTPUT_DIR = "models/intent-mapper-grpo"

# System prompt for QuerySpec generation
SYSTEM_PROMPT = """You are a SPARTA QuerySpec generator. Convert user questions about space cybersecurity into structured JSON queries.

Output format:
{
  "action": "QUERY" | "CLARIFY" | "NO_MATCH",
  "scope": "sparta",
  "lanes": ["bm25", "dense"] | ["entity", "bm25"],
  "entities": ["T1071", "CWE-787", ...],
  "tier0": ["Precision", "Resilience", ...],
  "tier1": ["Detect", "Mitigate", ...],
  "keywords": [...],
  "min_grounding": 0.7,
  "k": 12
}

Rules:
- Use "QUERY" for valid SPARTA questions
- Use "NO_MATCH" for out-of-scope questions (weather, recipes, general IT)
- Use "CLARIFY" for ambiguous or vague questions
- Extract entity IDs (T-xxxx, CWE-xxx, CM-xxxx) when present
- Infer tier1 tags from action words (detect, mitigate, prevent, etc.)"""


class WandbRewardCallback:
    """Callback to log detailed reward metrics to W&B."""

    def __init__(self, executor, judge):
        self.executor = executor
        self.judge = judge
        self.step = 0
        self.reward_history = {
            "grounding": [],
            "relevance": [],
            "format": [],
            "combined": [],
        }

    def log_rewards(self, grounding_scores, relevance_scores, format_scores, combined_scores):
        """Log reward breakdown to W&B."""
        try:
            import wandb
            if wandb.run is None:
                return

            self.step += 1

            # Log current batch metrics
            metrics = {
                "rewards/grounding_mean": sum(grounding_scores) / len(grounding_scores) if grounding_scores else 0,
                "rewards/relevance_mean": sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0,
                "rewards/format_mean": sum(format_scores) / len(format_scores) if format_scores else 0,
                "rewards/combined_mean": sum(combined_scores) / len(combined_scores) if combined_scores else 0,
                "rewards/grounding_min": min(grounding_scores) if grounding_scores else 0,
                "rewards/grounding_max": max(grounding_scores) if grounding_scores else 0,
                "rewards/combined_std": torch.tensor(combined_scores).std().item() if len(combined_scores) > 1 else 0,
            }

            wandb.log(metrics, step=self.step)

            # Track history for trend analysis
            self.reward_history["grounding"].extend(grounding_scores)
            self.reward_history["relevance"].extend(relevance_scores)
            self.reward_history["format"].extend(format_scores)
            self.reward_history["combined"].extend(combined_scores)

        except ImportError:
            pass

    def log_summary(self):
        """Log final summary metrics."""
        try:
            import wandb
            if wandb.run is None:
                return

            # Compute overall statistics
            for key, values in self.reward_history.items():
                if values:
                    wandb.run.summary[f"rewards/{key}_overall_mean"] = sum(values) / len(values)
                    wandb.run.summary[f"rewards/{key}_overall_std"] = torch.tensor(values).std().item()

        except ImportError:
            pass


def load_queries(query_file: Path) -> list[str]:
    """Load queries from file (one per line or JSONL)."""
    queries = []
    with open(query_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Try JSONL format
            try:
                data = json.loads(line)
                if isinstance(data, dict) and "input" in data:
                    queries.append(data["input"])
                elif isinstance(data, str):
                    queries.append(data)
            except json.JSONDecodeError:
                # Plain text
                queries.append(line)
    return queries


def format_prompt(query: str) -> list[dict]:
    """Format query as chat messages."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]


@app.command()
def warmup(
    train_file: Path = typer.Option(..., "--train-file", "-t", help="SFT training data"),
    output_dir: Path = typer.Option(Path(DEFAULT_OUTPUT_DIR) / "warmup", "--output", "-o"),
    base_model: str = typer.Option(DEFAULT_BASE_MODEL, "--base-model", "-m"),
    epochs: int = typer.Option(1, "--epochs", "-e"),
    batch_size: int = typer.Option(4, "--batch-size", "-b"),
    lora_r: int = typer.Option(32, "--lora-r"),
    lora_alpha: int = typer.Option(64, "--lora-alpha"),
    use_unsloth: bool = typer.Option(True, "--unsloth/--no-unsloth"),
):
    """SFT warmup before GRPO training.

    Initializes the policy near reasonable outputs to prevent
    wasted exploration during GRPO.
    """
    logger.info(f"Starting SFT warmup with {epochs} epoch(s)")
    logger.info(f"Base model: {base_model}")
    logger.info(f"Output: {output_dir}")

    if use_unsloth:
        from unsloth import FastLanguageModel

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=base_model,
            max_seq_length=1024,
            load_in_4bit=True,
            dtype=None,
        )

        model = FastLanguageModel.get_peft_model(
            model,
            r=lora_r,
            lora_alpha=lora_alpha,
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
            lora_dropout=0.05,
            bias="none",
            use_gradient_checkpointing="unsloth",
        )
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            base_model,
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
    from datasets import Dataset

    with open(train_file) as f:
        if str(train_file).endswith(".json"):
            data = json.load(f)
        else:
            data = [json.loads(line) for line in f]

    # Format for SFT
    formatted = []
    for item in data:
        query = item["input"]
        output = item["output"]
        if isinstance(output, dict):
            output = json.dumps(output, indent=2)

        messages = format_prompt(query)
        messages.append({"role": "assistant", "content": output})

        text = tokenizer.apply_chat_template(messages, tokenize=False)
        formatted.append({"text": text})

    dataset = Dataset.from_list(formatted)

    # Training
    from trl import SFTTrainer, SFTConfig

    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=10,
        save_strategy="epoch",
        bf16=torch.cuda.is_available(),
        optim="adamw_8bit",
        gradient_checkpointing=True,
        report_to="none",
        dataset_text_field="text",
        max_length=1024,
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

    logger.info(f"SFT warmup complete. Model saved to {output_dir}")


@app.command()
def grpo(
    query_file: Path = typer.Option(..., "--query-file", "-q", help="File with queries (one per line)"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output", "-o"),
    base_model: str = typer.Option(DEFAULT_BASE_MODEL, "--base-model", "-m"),
    warmup_model: Optional[Path] = typer.Option(None, "--warmup-model", "-w", help="Path to warmup LoRA"),
    eval_file: Optional[Path] = typer.Option(None, "--eval-file", "-e", help="Evaluation JSONL file"),
    steps: int = typer.Option(2000, "--steps", "-s"),
    num_generations: int = typer.Option(8, "--num-generations", "-g"),
    batch_size: int = typer.Option(1, "--batch-size", "-b"),
    learning_rate: float = typer.Option(5e-6, "--learning-rate", "-lr"),
    beta: float = typer.Option(0.01, "--beta", help="KL penalty coefficient"),
    temperature: float = typer.Option(0.7, "--temperature", "-t"),
    lora_r: int = typer.Option(32, "--lora-r"),
    lora_alpha: int = typer.Option(64, "--lora-alpha"),
    use_unsloth: bool = typer.Option(True, "--unsloth/--no-unsloth"),
    mock_rewards: bool = typer.Option(False, "--mock-rewards", help="Use mock rewards for testing"),
    use_wandb: bool = typer.Option(True, "--wandb/--no-wandb"),
    wandb_project: str = typer.Option("sparta-intent-mapper", "--wandb-project"),
) -> bool:
    """GRPO training with execution feedback.

    Generates multiple QuerySpecs per query, executes against ArangoDB,
    and uses grounding/relevance as reward signals.

    Returns True if training + eval passed, False otherwise.
    """
    logger.info(f"Starting GRPO training for {steps} steps")
    logger.info(f"Base model: {base_model}")
    logger.info(f"Warmup model: {warmup_model or 'None'}")
    logger.info(f"Num generations: {num_generations}")

    # Initialize W&B
    if use_wandb:
        try:
            import wandb
            wandb.init(
                project=wandb_project,
                name=f"grpo-{steps}steps-lr{learning_rate}",
                config={
                    "base_model": base_model,
                    "warmup_model": str(warmup_model) if warmup_model else None,
                    "steps": steps,
                    "num_generations": num_generations,
                    "batch_size": batch_size,
                    "learning_rate": learning_rate,
                    "beta": beta,
                    "temperature": temperature,
                    "lora_r": lora_r,
                    "lora_alpha": lora_alpha,
                    "reward_weights": {"grounding": 0.4, "relevance": 0.4, "format": 0.2},
                },
                tags=["grpo", "sparta", "intent-mapper"],
            )
        except ImportError:
            logger.warning("wandb not installed, disabling logging")
            use_wandb = False

    # Import rewards
    from rewards import grounding_reward, relevance_reward, format_reward
    from rewards.execution import get_executor
    from rewards.relevance import get_judge

    # Get executor and judge
    executor = get_executor(mock=mock_rewards)
    judge = get_judge(mock=mock_rewards)

    # Create W&B callback for reward logging
    wandb_callback = WandbRewardCallback(executor, judge) if use_wandb else None

    # Load model
    if use_unsloth:
        from unsloth import FastLanguageModel

        if warmup_model:
            # Load from warmup checkpoint
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=str(warmup_model),
                max_seq_length=1024,
                load_in_4bit=True,
            )
        else:
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=base_model,
                max_seq_length=1024,
                load_in_4bit=True,
            )

            model = FastLanguageModel.get_peft_model(
                model,
                r=lora_r,
                lora_alpha=lora_alpha,
                target_modules=[
                    "q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj",
                ],
                lora_dropout=0.05,
                bias="none",
                use_gradient_checkpointing="unsloth",
            )
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel, LoraConfig, get_peft_model

        tokenizer = AutoTokenizer.from_pretrained(
            warmup_model or base_model,
            trust_remote_code=True,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )

        if warmup_model:
            model = PeftModel.from_pretrained(model, str(warmup_model))
            # Fix for TRL 0.24 + PEFT compatibility: ensure target_modules is a list not set
            # This prevents "TypeError: unhashable type: 'set'" when GRPOTrainer creates ref adapter
            for adapter_name in model.peft_config:
                cfg = model.peft_config[adapter_name]
                if hasattr(cfg, 'target_modules') and isinstance(cfg.target_modules, set):
                    cfg.target_modules = list(cfg.target_modules)
        else:
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

    # Load queries
    queries = load_queries(query_file)
    logger.info(f"Loaded {len(queries)} queries")

    # Create dataset
    from datasets import Dataset

    dataset = Dataset.from_dict({
        "query": queries,
        "prompt": [
            tokenizer.apply_chat_template(format_prompt(q), tokenize=False, add_generation_prompt=True)
            for q in queries
        ],
    })

    # Create combined reward function
    def combined_reward(completions, prompts=None, queries=None, **kwargs):
        """Combined reward from grounding, relevance, and format.

        Returns a torch.Tensor for TRL compatibility.
        """
        # Prefer explicit queries if provided; fallback to parsing prompts
        query_list = queries or []
        if not query_list:
            query_list = []
            for prompt in (prompts or []):
                if isinstance(prompt, str):
                    import re
                    # Try JSON chat template format first
                    m = re.search(r'"role"\s*:\s*"user"\s*,\s*"content"\s*:\s*"(.*?)"', prompt, re.DOTALL)
                    if not m:
                        # Fallback to plain text format
                        m = re.search(r'(?:^|\n)(?:user|human)\s*:\s*(.*?)(?:\n\s*(assistant|system)|$)', prompt, re.IGNORECASE | re.DOTALL)
                    query_list.append(m.group(1).strip() if m else "")
                elif isinstance(prompt, list):
                    user_msg = next((m for m in prompt if m.get("role") == "user"), None)
                    query_list.append(user_msg.get("content", "") if user_msg else "")
                else:
                    query_list.append("")

        # Compute individual rewards
        grounding_scores = grounding_reward(
            completions,
            executor=executor,
        )
        relevance_scores = relevance_reward(
            completions,
            prompts=prompts,
            queries=query_list,
            executor=executor,
            judge=judge,
        )
        format_scores = format_reward(completions)

        # Weighted combination: 40% grounding, 40% relevance, 20% format; clamp to [0, 1]
        combined = []
        for g, r, f in zip(grounding_scores, relevance_scores, format_scores):
            score = 0.4 * g + 0.4 * r + 0.2 * f
            combined.append(float(max(0.0, min(1.0, score))))

        # Log to W&B
        if wandb_callback:
            wandb_callback.log_rewards(grounding_scores, relevance_scores, format_scores, combined)

        return torch.tensor(combined, dtype=torch.float32)

    # GRPO config
    from trl import GRPOConfig, GRPOTrainer

    grpo_config = GRPOConfig(
        output_dir=str(output_dir),
        learning_rate=learning_rate,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        num_generations=num_generations,
        max_prompt_length=512,
        max_completion_length=512,
        temperature=temperature,
        beta=beta,  # KL penalty
        max_steps=steps,
        save_steps=200,
        logging_steps=10,
        optim="adamw_8bit",
        warmup_ratio=0.1,
        lr_scheduler_type="cosine",
        report_to="wandb" if use_wandb else "none",
        run_name=f"grpo-{steps}steps-lr{learning_rate}" if use_wandb else None,
    )

    # Inject raw queries directly into reward via closure to avoid brittle parsing
    # TRL 0.24+ passes all arguments as keyword arguments
    def reward_fn(**kwargs):
        completions = kwargs.pop("completions", [])
        prompts = kwargs.pop("prompts", None)
        # Don't pass duplicate kwargs
        return combined_reward(completions, prompts=prompts, queries=queries)

    # Create trainer
    trainer = GRPOTrainer(
        model=model,
        processing_class=tokenizer,
        reward_funcs=reward_fn,
        args=grpo_config,
        train_dataset=dataset,
    )

    # Train
    logger.info("Starting GRPO training...")
    try:
        trainer.train()
    finally:
        # Ensure GPU/memory cleanup and close external clients
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception as e:
            logger.debug("if failed: {}", e)
        try:
            judge.close()
        except Exception as e:
            logger.debug("judge failed: {}", e)
        try:
            if hasattr(executor, "close"):
                executor.close()
        except Exception as e:
            logger.debug("if failed: {}", e)

    # Save
    logger.info(f"Saving model to {output_dir}")
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # Save training config
    config = {
        "base_model": base_model,
        "warmup_model": str(warmup_model) if warmup_model else None,
        "steps": steps,
        "num_generations": num_generations,
        "learning_rate": learning_rate,
        "beta": beta,
        "temperature": temperature,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "reward_weights": {"grounding": 0.4, "relevance": 0.4, "format": 0.2},
    }
    with open(Path(output_dir) / "grpo_config.json", "w") as f:
        json.dump(config, f, indent=2)

    # Log W&B summary
    if wandb_callback:
        wandb_callback.log_summary()

    logger.info("GRPO training complete!")

    # Run evaluation if eval file provided
    eval_passed = True
    if eval_file and eval_file.exists():
        logger.info(f"Running evaluation on {eval_file}")
        eval_output = Path(output_dir) / "eval_results.json"

        try:
            # Run evaluation as subprocess to get clean metrics
            result = subprocess.run(
                [
                    sys.executable, "evaluate.py", "run",
                    "--model", str(output_dir),
                    "--test-file", str(eval_file),
                    "--output", str(eval_output),
                    "--mock-execution" if mock_rewards else "--execution",
                ],
                cwd=Path(__file__).parent,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(f"Evaluation FAILED")
                logger.error(result.stderr)
                eval_passed = False
            else:
                logger.info("Evaluation PASSED")

                # Log eval metrics to W&B
                if use_wandb and eval_output.exists():
                    try:
                        import wandb
                        with open(eval_output) as f:
                            eval_results = json.load(f)
                        for key, value in eval_results.get("metrics", {}).items():
                            if isinstance(value, (int, float)):
                                wandb.run.summary[f"eval/{key}"] = value
                        wandb.run.summary["eval/passed"] = eval_results.get("passed", False)
                    except Exception as e:
                        logger.warning(f"Failed to log eval to W&B: {e}")

        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            eval_passed = False

    # Finish W&B run
    if use_wandb:
        try:
            import wandb
            wandb.finish()
        except Exception as e:
            logger.debug("import failed: {}", e)

    return eval_passed


@app.command()
def train(
    train_file: Path = typer.Option(..., "--train-file", "-t", help="SFT training data"),
    query_file: Path = typer.Option(..., "--query-file", "-q", help="GRPO queries"),
    eval_file: Path = typer.Option(..., "--eval-file", "-e", help="Evaluation data (holdout)"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output", "-o"),
    base_model: str = typer.Option(DEFAULT_BASE_MODEL, "--base-model", "-m"),
    sft_epochs: int = typer.Option(1, "--sft-epochs"),
    grpo_steps: int = typer.Option(2000, "--grpo-steps", "-s"),
    max_retries: int = typer.Option(3, "--max-retries", "-r"),
    use_unsloth: bool = typer.Option(True, "--unsloth/--no-unsloth"),
    mock_rewards: bool = typer.Option(False, "--mock-rewards"),
    use_wandb: bool = typer.Option(True, "--wandb/--no-wandb"),
    wandb_project: str = typer.Option("sparta-intent-mapper", "--wandb-project"),
):
    """Full training pipeline with iterative improvement.

    1. SFT warmup
    2. GRPO training with execution feedback
    3. Evaluation on holdout set
    4. If eval fails, retry with adjusted hyperparameters

    Example:
        python train_grpo.py train \\
            --train-file data/sft/train.jsonl \\
            --query-file data/queries.txt \\
            --eval-file data/eval/test.jsonl \\
            --grpo-steps 2000 \\
            --max-retries 3
    """
    logger.info("=" * 60)
    logger.info("SPARTA Intent Mapper Training Pipeline")
    logger.info("=" * 60)

    # Step 1: SFT Warmup
    warmup_dir = Path(output_dir) / "warmup"
    warmup_checkpoint = warmup_dir / "adapter_model.safetensors"

    if warmup_checkpoint.exists():
        logger.info(f"\n[Step 1/3] SFT Warmup - SKIPPED (checkpoint exists: {warmup_checkpoint})")
    else:
        logger.info(f"\n[Step 1/3] SFT Warmup ({sft_epochs} epochs)")
        warmup(
            train_file=train_file,
            output_dir=warmup_dir,
            base_model=base_model,
            epochs=sft_epochs,
            batch_size=4,
            lora_r=32,
            lora_alpha=64,
            use_unsloth=use_unsloth,
        )

    # Step 2: GRPO Training with retry loop
    attempt = 0
    passed = False
    best_output_dir = None

    # Default hyperparameters
    hp = {
        "learning_rate": 5e-6,
        "beta": 0.01,
        "temperature": 0.7,
        "num_generations": 4,  # Must divide evenly into batch_size(1) * grad_accum(4) = 4
    }

    while attempt <= max_retries and not passed:
        attempt += 1
        attempt_dir = Path(output_dir) / f"attempt_{attempt}"

        logger.info(f"\n[Step 2/3] GRPO Training (Attempt {attempt}/{max_retries + 1})")
        logger.info(f"  Hyperparameters: {hp}")

        passed = grpo(
            query_file=query_file,
            output_dir=attempt_dir,
            base_model=base_model,
            warmup_model=warmup_dir,
            eval_file=eval_file,
            steps=grpo_steps,
            num_generations=hp["num_generations"],
            batch_size=1,
            learning_rate=hp["learning_rate"],
            beta=hp["beta"],
            temperature=hp["temperature"],
            lora_r=32,
            lora_alpha=64,
            use_unsloth=use_unsloth,
            mock_rewards=mock_rewards,
            use_wandb=use_wandb,
            wandb_project=wandb_project,
        )

        if passed:
            best_output_dir = attempt_dir
            logger.info(f"\n✓ Training PASSED on attempt {attempt}")
        elif attempt <= max_retries:
            # Apply hyperparameter adjustments for next retry
            adjustment = RETRY_ADJUSTMENTS[attempt - 1] if attempt <= len(RETRY_ADJUSTMENTS) else {}
            hp.update(adjustment)
            logger.warning(f"\n✗ Training FAILED on attempt {attempt}, retrying with adjusted hyperparameters...")
        else:
            logger.error(f"\n✗ Training FAILED after {max_retries + 1} attempts")

    # Step 3: Finalize
    if passed and best_output_dir:
        # Copy best model to final location
        final_dir = Path(output_dir) / "final"
        logger.info(f"\n[Step 3/3] Finalizing: {best_output_dir} -> {final_dir}")

        import shutil
        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.copytree(best_output_dir, final_dir)

        # Save training summary
        summary = {
            "status": "PASSED",
            "attempts": attempt,
            "final_hyperparameters": hp,
            "model_path": str(final_dir),
            "eval_file": str(eval_file),
        }
        with open(final_dir / "training_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        logger.info("\n" + "=" * 60)
        logger.info("✓ TRAINING PIPELINE COMPLETE")
        logger.info(f"  Final model: {final_dir}")
        logger.info(f"  Attempts: {attempt}")
        logger.info("=" * 60)

        raise typer.Exit(code=0)
    else:
        # All retries failed
        summary = {
            "status": "FAILED",
            "attempts": attempt,
            "final_hyperparameters": hp,
        }
        with open(Path(output_dir) / "training_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        logger.error("\n" + "=" * 60)
        logger.error("✗ TRAINING PIPELINE FAILED")
        logger.error(f"  Attempts: {attempt}")
        logger.error("  Check W&B for detailed metrics")
        logger.error("=" * 60)

        raise typer.Exit(code=1)


@app.command()
def test_rewards(
    query: str = typer.Argument(..., help="Query to test"),
    spec: str = typer.Argument(..., help="QuerySpec JSON to test"),
    mock: bool = typer.Option(True, "--mock/--real", help="Use mock or real execution"),
):
    """Test reward computation for a single query/spec pair."""
    from rewards import grounding_reward, relevance_reward, format_reward
    from rewards.execution import get_executor
    from rewards.relevance import get_judge

    executor = get_executor(mock=mock)
    judge = get_judge(mock=mock)

    completions = [[{"content": spec}]]

    g = grounding_reward(completions, executor=executor)[0]
    r = relevance_reward(completions, queries=[query], executor=executor, judge=judge)[0]
    f = format_reward(completions)[0]

    combined = 0.4 * g + 0.4 * r + 0.2 * f

    print(f"\nReward Breakdown:")
    print(f"  Grounding:  {g:+.3f} (weight 0.4)")
    print(f"  Relevance:  {r:+.3f} (weight 0.4)")
    print(f"  Format:     {f:+.3f} (weight 0.2)")
    print(f"  Combined:   {combined:+.3f}")


if __name__ == "__main__":
    app()
