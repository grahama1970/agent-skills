#!/usr/bin/env python3
"""GRPO training with pluggable task rewards for task-specific GPTs.

Adapted from create-intent-map/scripts/train_grpo.py.

Supports prompt annealing (ICRL-inspired): inject few-shot examples into
rollout prompts and gradually remove them across training stages.
See: arXiv:2603.08068 "In-Context Reinforcement Learning for Tool Use"

Usage:
    python train_grpo.py grpo --task qra-validator --query-file data/queries.txt
    python train_grpo.py grpo --task qra-validator --query-file data/queries.txt \
        --prompt-anneal data/few_shot_examples.jsonl --anneal-schedule 3,2,0
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, DATA_DIR, MODELS_DIR

app = typer.Typer(add_completion=False)

# Retry adjustments (from create-intent-map pattern)
RETRY_ADJUSTMENTS = [
    {"learning_rate": 2e-6, "beta": 0.02},
    {"learning_rate": 1e-5, "beta": 0.005},
    {"num_generations": 4, "temperature": 0.5},
]


def load_few_shot_examples(path: Path) -> list[dict]:
    """Load few-shot examples from JSONL. Each line: {input, output}."""
    examples = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def build_anneal_schedule(schedule_str: str, total_steps: int) -> list[tuple[int, int]]:
    """Parse '3,2,0' into [(n_examples, steps_for_stage), ...].

    Steps are divided equally across stages.
    """
    counts = [int(x) for x in schedule_str.split(",")]
    steps_per_stage = total_steps // len(counts)
    stages = []
    for i, n in enumerate(counts):
        s = steps_per_stage if i < len(counts) - 1 else total_steps - steps_per_stage * (len(counts) - 1)
        stages.append((n, s))
    return stages


def format_prompt_with_examples(
    query: str, system_prompt: str | None, few_shot: list[dict], n_examples: int
) -> list[dict]:
    """Build chat messages with n few-shot examples prepended."""
    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})

    # Inject up to n_examples as user/assistant turns
    for ex in few_shot[:n_examples]:
        inp = ex["input"] if isinstance(ex["input"], str) else json.dumps(ex["input"])
        out = ex["output"] if isinstance(ex["output"], str) else json.dumps(ex["output"])
        msgs.append({"role": "user", "content": inp})
        msgs.append({"role": "assistant", "content": out})

    msgs.append({"role": "user", "content": query})
    return msgs


def directional_critique_advantage(
    completions: list[str],
    ground_truth_skills: list[list[str]],
    known_skills: set[str] | None = None,
    alpha: float = 0.3,
) -> list[float]:
    """AReW directional critique for chain-reasoning advantage shaping.

    Implements arXiv 2603.12109 binary directional critique:
      +1  completion matches ground truth skills (informative)
      -1  completion hallucinates skills or produces malformed JSON (uninformative)
       0  neutral (valid JSON, partial match)

    Then applies zero-sum reallocation within the batch so the total
    advantage adjustment sums to zero — probability mass moves from
    negatively-critiqued to positively-critiqued completions.

    Args:
        completions: Raw model output strings.
        ground_truth_skills: Parallel list of expected skill lists.
        known_skills: Set of valid skill names. If None, skip hallucination check.
        alpha: Scaling factor for the advantage adjustment (default 0.3).

    Returns:
        List of advantage adjustments (same length as completions).
    """
    critiques: list[int] = []
    for completion, gt_skills in zip(completions, ground_truth_skills):
        # Try to parse JSON and extract skills
        try:
            parsed = json.loads(completion.strip()) if isinstance(completion, str) else completion
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
        except (json.JSONDecodeError, TypeError):
            critiques.append(-1)  # malformed JSON
            continue

        pred_skills = parsed.get("skills", []) if isinstance(parsed, dict) else []
        if not isinstance(pred_skills, list):
            critiques.append(-1)
            continue

        # Check for hallucinated skills
        if known_skills and any(s not in known_skills for s in pred_skills if isinstance(s, str)):
            critiques.append(-1)
            continue

        # Compute set overlap with ground truth
        gt_set = set(gt_skills)
        pred_set = set(s for s in pred_skills if isinstance(s, str))

        if not pred_set:
            critiques.append(-1)
            continue

        overlap = len(gt_set & pred_set)
        total = len(gt_set | pred_set)
        jaccard = overlap / total if total > 0 else 0.0

        if jaccard >= 0.5:
            critiques.append(1)   # informative
        elif jaccard > 0:
            critiques.append(0)   # neutral — partial match
        else:
            critiques.append(-1)  # no overlap

    # Zero-sum reallocation: redistribute so sum of adjustments = 0
    n = len(critiques)
    if n == 0:
        return []

    mean_critique = sum(critiques) / n
    adjustments = [alpha * (c - mean_critique) for c in critiques]
    return adjustments


class WandbRewardCallback:
    """Callback to log reward metrics to W&B."""

    def __init__(self):
        self.step = 0
        self.reward_history: dict[str, list] = {
            "format": [],
            "task": [],
            "combined": [],
        }

    def log_rewards(self, format_scores, task_scores, combined_scores):
        try:
            import wandb
            if wandb.run is None:
                return
            self.step += 1
            metrics = {
                "rewards/format_mean": sum(format_scores) / len(format_scores) if format_scores else 0,
                "rewards/task_mean": sum(task_scores) / len(task_scores) if task_scores else 0,
                "rewards/combined_mean": sum(combined_scores) / len(combined_scores) if combined_scores else 0,
            }
            wandb.log(metrics, step=self.step)
            self.reward_history["format"].extend(format_scores)
            self.reward_history["task"].extend(task_scores)
            self.reward_history["combined"].extend(combined_scores)
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
            try:
                data = json.loads(line)
                if isinstance(data, dict) and "input" in data:
                    queries.append(data["input"] if isinstance(data["input"], str)
                                   else json.dumps(data["input"]))
                elif isinstance(data, str):
                    queries.append(data)
                else:
                    queries.append(json.dumps(data))
            except json.JSONDecodeError:
                queries.append(line)
    return queries


def _flash_submit_grpo(
    task: str,
    query_file: Path,
    warmup_model: Optional[Path],
    output_dir: Optional[Path],
    steps: int,
    num_generations: int,
    batch_size: int,
    learning_rate: float,
    beta: float,
    temperature: float,
    mock: bool,
    use_wandb: bool,
    reward_file: Optional[Path],
    prompt_anneal: Optional[Path],
    anneal_schedule: str,
) -> Path:
    """Package train_grpo.py and submit it to RunPod via FlashTrainer.

    Polls until the pod reaches a terminal state, then downloads the
    checkpoint to ``output_dir`` (or a temp directory).

    Returns the local path where the checkpoint was written.
    """
    skills_root = Path.home() / ".pi" / "skills"
    if str(skills_root) not in sys.path:
        sys.path.insert(0, str(skills_root))

    from common.flash_trainer import FlashTrainer, estimate_gpu  # type: ignore[import]

    # Reconstruct CLI args for the remote invocation (--target local is the default)
    remote_args: list[str] = [
        "grpo",
        f"--task={task}",
        f"--query-file={query_file}",
        f"--steps={steps}",
        f"--num-generations={num_generations}",
        f"--batch-size={batch_size}",
        f"--learning-rate={learning_rate}",
        f"--beta={beta}",
        f"--temperature={temperature}",
        f"--anneal-schedule={anneal_schedule}",
    ]
    if warmup_model:
        remote_args.append(f"--warmup-model={warmup_model}")
    if mock:
        remote_args.append("--mock")
    if use_wandb:
        remote_args.append("--wandb")
    if reward_file:
        remote_args.append(f"--reward-file={reward_file}")
    if prompt_anneal:
        remote_args.append(f"--prompt-anneal={prompt_anneal}")
    # Checkpoint output on the pod's network volume
    remote_output = "/runpod-volume/checkpoints"
    remote_args.append(f"--output={remote_output}")

    gpu_type = estimate_gpu(1.7, method="lora")  # create-gpt range: 0.5B–1.7B
    trainer = FlashTrainer()

    script_path = Path(__file__).resolve()
    job_id = trainer.submit_training_job(
        script_path=script_path,
        args=remote_args,
        gpu_type=gpu_type,
    )
    logger.info(f"Flash GRPO job submitted: {job_id}")

    terminal_states = {"EXITED", "TERMINATED", "FAILED", "DEAD"}
    while True:
        status = trainer.poll_status(job_id)
        state = status.get("state", "").upper()
        logger.info(f"Job {job_id} state: {state}")
        if state in terminal_states:
            logger.info(f"Job {job_id} finished with state: {state}")
            break
        time.sleep(30)

    local_ckpt = output_dir if output_dir else Path(f"/tmp/flash-grpo-{job_id}")
    trainer.download_checkpoint(job_id, local_ckpt, remote_checkpoint_dir=remote_output)
    logger.success(f"GRPO checkpoint downloaded to {local_ckpt}")
    return local_ckpt


@app.command()
def grpo(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    query_file: Path = typer.Option(..., "--query-file", "-q"),
    warmup_model: Optional[Path] = typer.Option(None, "--warmup-model", "-w"),
    eval_file: Optional[Path] = typer.Option(None, "--eval-file", "-e"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    steps: int = typer.Option(2000, "--steps", "-s"),
    num_generations: int = typer.Option(8, "--num-generations", "-g"),
    batch_size: int = typer.Option(1, "--batch-size", "-b"),
    learning_rate: float = typer.Option(5e-6, "--learning-rate", "-lr"),
    beta: float = typer.Option(0.01, "--beta"),
    temperature: float = typer.Option(0.7, "--temperature"),
    mock: bool = typer.Option(False, "--mock"),
    use_wandb: bool = typer.Option(False, "--wandb/--no-wandb"),
    reward_file: Optional[Path] = typer.Option(None, "--reward-file"),
    prompt_anneal: Optional[Path] = typer.Option(
        None, "--prompt-anneal",
        help="JSONL file with few-shot examples ({input, output}) for ICRL-style prompt annealing",
    ),
    anneal_schedule: str = typer.Option(
        "3,2,0", "--anneal-schedule",
        help="Comma-separated example counts per stage (e.g. '3,2,0'). Steps divided equally.",
    ),
    target: str = typer.Option("local", "--target", help="Training target: local or flash (RunPod GPU)"),
) -> bool:
    """GRPO training with pluggable task rewards.

    Use --target flash to submit the job to RunPod (requires RUNPOD_API_KEY).
    """
    if target == "flash":
        _flash_submit_grpo(
            task=task,
            query_file=query_file,
            warmup_model=warmup_model,
            output_dir=output_dir,
            steps=steps,
            num_generations=num_generations,
            batch_size=batch_size,
            learning_rate=learning_rate,
            beta=beta,
            temperature=temperature,
            mock=mock,
            use_wandb=use_wandb,
            reward_file=reward_file,
            prompt_anneal=prompt_anneal,
            anneal_schedule=anneal_schedule,
        )
        return True

    spec = load_task_spec(task)

    if output_dir is None:
        output_dir = MODELS_DIR / spec.name / "grpo"

    lora_r = spec.get_training_param("lora_r", 16)
    lora_alpha = spec.get_training_param("lora_alpha", 32)

    logger.info(f"Starting GRPO training for {steps} steps")
    logger.info(f"Task: {spec.name}")
    logger.info(f"Base model: {spec.base_model}")

    if warmup_model is None:
        warmup_model = MODELS_DIR / spec.name / "sft"
        if not warmup_model.exists():
            warmup_model = None

    # Load reward functions
    from rewards.format import format_reward
    task_reward_fn = None
    if reward_file and reward_file.exists():
        from rewards.task_reward import load_task_reward
        task_reward_fn = load_task_reward(reward_file)

    # Auto-load chain-rationale reward if task matches and no explicit reward file
    gt_lookup: dict[str, list[str]] = {}
    if spec.name == "chain-rationale" and not reward_file:
        gt_file = DATA_DIR / spec.name / "grpo" / "queries.jsonl"
        if gt_file.exists():
            from rewards.chain_rationale_reward import init_ground_truth, compute_reward as cr_reward
            init_ground_truth(gt_file)
            task_reward_fn = cr_reward
            # Load GT lookup for AReW
            with open(gt_file) as _f:
                for _line in _f:
                    _rec = json.loads(_line.strip())
                    gt_lookup[_rec["input"][:200]] = _rec["ground_truth_skills"]
            logger.info(f"Loaded chain-rationale reward with {len(gt_lookup)} GT entries + AReW")

    if mock:
        from rewards.mock import mock_reward
        task_reward_fn = lambda output, input_dict, ref: mock_reward(
            [[{"content": json.dumps(output)}]], spec.output_schema
        )[0]

    # Mock GRPO
    if mock:
        import random
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics = {
            "accuracy": 0.80 + random.random() * 0.15,
            "format_valid": 0.92 + random.random() * 0.08,
            "mock": True,
            "steps": steps,
        }
        (output_dir / "grpo_config.json").write_text(json.dumps({
            "task": spec.name,
            "steps": steps,
            "metrics": metrics,
        }, indent=2))
        logger.info(f"Mock GRPO complete: {metrics}")
        return metrics["accuracy"] >= spec.eval_thresholds.get("accuracy", 0.85)

    # Real GRPO training
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel, LoraConfig, get_peft_model
    from datasets import Dataset
    from trl import GRPOConfig, GRPOTrainer

    tokenizer = AutoTokenizer.from_pretrained(
        warmup_model or spec.base_model, trust_remote_code=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Use 4-bit quantization to match SFT training config
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        spec.base_model,
        quantization_config=bnb_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    if warmup_model and warmup_model.exists():
        model = PeftModel.from_pretrained(model, str(warmup_model))
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

    queries = load_queries(query_file)
    logger.info(f"Loaded {len(queries)} queries")

    # Load few-shot examples for prompt annealing (ICRL-style)
    few_shot_examples: list[dict] = []
    anneal_stages: list[tuple[int, int]] | None = None
    if prompt_anneal and prompt_anneal.exists():
        few_shot_examples = load_few_shot_examples(prompt_anneal)
        anneal_stages = build_anneal_schedule(anneal_schedule, steps)
        logger.info(f"Prompt annealing enabled: {len(few_shot_examples)} examples, schedule={anneal_schedule}")
        logger.info(f"Stages: {anneal_stages}")

    def build_dataset(n_examples: int = 0) -> Dataset:
        """Build dataset with optional few-shot examples in prompts."""
        prompts = []
        for q in queries:
            msgs = format_prompt_with_examples(q, spec.system_prompt, few_shot_examples, n_examples)
            prompts.append(tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True))
        return Dataset.from_dict({"query": queries, "prompt": prompts})

    # Reward weights from TaskSpec
    weights = spec.reward_weights
    w_format = weights.get("format", 0.3)
    w_task = 1.0 - w_format

    wandb_callback = WandbRewardCallback() if use_wandb else None

    def combined_reward(completions, **kwargs):
        format_scores = format_reward(completions, output_schema=spec.output_schema)

        if task_reward_fn:
            from rewards.task_reward import task_reward
            task_scores = task_reward(completions, reward_fn=task_reward_fn)
        else:
            task_scores = [0.5] * len(completions)

        combined = []
        for f_score, t_score in zip(format_scores, task_scores):
            score = w_format * max(0, f_score) + w_task * t_score
            combined.append(float(max(0.0, min(1.0, score))))

        # Apply AReW directional critique if ground truth is available
        if gt_lookup:
            # Extract completion strings for AReW
            comp_strs = []
            gt_skills_list = []
            for c in completions:
                if isinstance(c, list) and len(c) > 0:
                    comp_strs.append(c[0].get("content", ""))
                elif isinstance(c, dict):
                    comp_strs.append(c.get("content", ""))
                elif isinstance(c, str):
                    comp_strs.append(c)
                else:
                    comp_strs.append("")
                # Use first GT match available (queries cycle)
                gt_skills_list.append(list(gt_lookup.values())[0] if gt_lookup else [])

            arew_adjustments = directional_critique_advantage(
                comp_strs, gt_skills_list, alpha=0.3
            )
            combined = [
                float(max(0.0, min(1.0, c + adj)))
                for c, adj in zip(combined, arew_adjustments)
            ]

        if wandb_callback:
            wandb_callback.log_rewards(format_scores, task_scores, combined)

        return torch.tensor(combined, dtype=torch.float32)

    def reward_fn(**kwargs):
        completions = kwargs.pop("completions", [])
        return combined_reward(completions)

    def run_stage(stage_steps: int, n_examples: int, stage_idx: int):
        """Run one annealing stage with n few-shot examples for stage_steps."""
        stage_label = f"stage_{stage_idx}_{n_examples}shot"
        stage_dir = output_dir / stage_label if anneal_stages else output_dir
        logger.info(f"GRPO {stage_label}: {stage_steps} steps, {n_examples} few-shot examples")

        ds = build_dataset(n_examples)

        grpo_config = GRPOConfig(
            output_dir=str(stage_dir),
            learning_rate=learning_rate,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=4,
            num_generations=num_generations,
            max_completion_length=spec.max_seq_length,
            temperature=temperature,
            beta=beta,
            max_steps=stage_steps,
            save_steps=200,
            logging_steps=10,
            optim="adamw_8bit",
            warmup_ratio=0.1,
            lr_scheduler_type="cosine",
            report_to="wandb" if use_wandb else "none",
        )

        trainer = GRPOTrainer(
            model=model,
            processing_class=tokenizer,
            reward_funcs=reward_fn,
            args=grpo_config,
            train_dataset=ds,
        )
        trainer.train()

    try:
        if anneal_stages:
            # ICRL-style staged training: gradually reduce few-shot examples
            for stage_idx, (n_examples, stage_steps) in enumerate(anneal_stages):
                run_stage(stage_steps, n_examples, stage_idx)
        else:
            # Standard single-stage GRPO (backward compatible)
            run_stage(steps, 0, 0)
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # Copy final checkpoint to output_dir for export compatibility
    # TRL auto-saves checkpoints; find the latest one
    checkpoints = sorted(output_dir.glob("**/checkpoint-*"), key=lambda p: p.stat().st_mtime)
    if checkpoints:
        latest_ckpt = checkpoints[-1]
        logger.info(f"Copying final checkpoint {latest_ckpt.name} to {output_dir}")
        for f in latest_ckpt.iterdir():
            if f.is_file():
                import shutil
                shutil.copy2(f, output_dir / f.name)
    else:
        logger.warning("No checkpoints found — model may not have been saved")

    tokenizer.save_pretrained(str(output_dir))

    config = {
        "task": spec.name,
        "base_model": spec.base_model,
        "steps": steps,
        "learning_rate": learning_rate,
        "beta": beta,
        "temperature": temperature,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "reward_weights": spec.reward_weights,
        "prompt_anneal": str(prompt_anneal) if prompt_anneal else None,
        "anneal_schedule": anneal_schedule if anneal_stages else None,
    }
    (Path(output_dir) / "grpo_config.json").write_text(json.dumps(config, indent=2))

    logger.info("GRPO training complete!")
    return True


if __name__ == "__main__":
    app()
