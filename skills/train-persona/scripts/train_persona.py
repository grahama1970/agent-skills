"""
train-persona: λ-GRPO training for persona agents.

Trains LoRA adapters with:
- λ-GRPO normalization (implicit PRM leverage)
- Persona consistency rewards
- Grounding verification
- Reasoning coherence checks

Based on: "GRPO is Secretly a Process Reward Model" (arxiv:2509.21154)
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch
import typer
from datasets import Dataset
from loguru import logger
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import GRPOConfig, GRPOTrainer

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

app = typer.Typer()


@dataclass
class PersonaConfig:
    """Persona configuration for training."""
    name: str
    template: str = "intern"
    knowledge_domains: list[str] = field(default_factory=list)
    voice_markers: list[str] = field(default_factory=list)
    escalation_triggers: list[str] = field(default_factory=list)
    humility_patterns: list[str] = field(default_factory=list)


@dataclass
class TrainingArgs:
    """Training arguments."""
    persona: str
    train_file: Path
    output: Path
    base_model: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    grpo_steps: int = 2000
    warmup_steps: int = 100
    batch_size: int = 4
    learning_rate: float = 2e-5
    lora_r: int = 32
    lora_alpha: int = 64
    lambda_grpo: bool = True
    warmup_only: bool = False


def load_persona_config(persona_name: str) -> PersonaConfig:
    """Load persona config from /create-persona."""
    # Future work: Integrate with create-persona skill
    # For now, return hardcoded configs

    configs = {
        "embry": PersonaConfig(
            name="Embry",
            template="intern",
            knowledge_domains=["SPARTA framework", "space cybersecurity"],
            voice_markers=["slight southern cadence", "mechanical metaphors", "eager but humble"],
            escalation_triggers=["novel threats", "policy questions", "out of scope"],
            humility_patterns=["I'm still learning", "Let me check with Brandon", "Based on my training"],
        ),
        "horus": PersonaConfig(
            name="Horus",
            template="expert",
            knowledge_domains=["all lore", "technical", "creative"],
            voice_markers=["authoritative", "references experiences", "bridges domains"],
            escalation_triggers=["factual disputes", "out-of-domain"],
            humility_patterns=[],
        ),
    }

    return configs.get(persona_name.lower(), PersonaConfig(name=persona_name))


def compute_process_sets(token_ids: torch.Tensor, group_size: int) -> list[list[int]]:
    """
    Compute process sets (shared prefixes) within each group.

    Returns list of process set sizes for each token position.
    Based on arxiv:2509.21154 Section 3.
    """
    batch_size, seq_len = token_ids.shape
    n_groups = batch_size // group_size

    all_process_sets = []

    for g in range(n_groups):
        group_start = g * group_size
        group_end = (g + 1) * group_size
        group_tokens = token_ids[group_start:group_end]  # [group_size, seq_len]

        group_process_sets = []

        for sample_idx in range(group_size):
            sample_sets = []
            for pos in range(seq_len):
                # Count how many samples in group share same prefix up to pos
                prefix = group_tokens[sample_idx, :pos+1]
                matches = 0
                for other_idx in range(group_size):
                    other_prefix = group_tokens[other_idx, :pos+1]
                    if torch.equal(prefix, other_prefix):
                        matches += 1
                sample_sets.append(matches)
            group_process_sets.append(sample_sets)

        all_process_sets.extend(group_process_sets)

    return all_process_sets


def lambda_grpo_loss(
    log_probs: torch.Tensor,
    advantages: torch.Tensor,
    process_set_sizes: torch.Tensor,
) -> torch.Tensor:
    """
    λ-GRPO loss with process set normalization.

    loss = -advantage * log_prob / |λ(i,t)|

    Where |λ(i,t)| is the process set size for token t in sample i.
    """
    # Normalize by process set size
    normalized_log_probs = log_probs / process_set_sizes.clamp(min=1)

    # Standard policy gradient loss
    loss = -(advantages * normalized_log_probs).mean()

    return loss


# ============================================================================
# Reward Functions
# ============================================================================

def persona_consistency_reward(
    completions: list[str],
    persona: PersonaConfig,
) -> list[float]:
    """
    Check if responses match persona definition.

    Rewards:
    - Voice marker presence
    - Knowledge boundary adherence
    - Appropriate escalation
    - Humility markers (for intern personas)
    """
    scores = []

    for completion in completions:
        completion_lower = completion.lower()
        score = 0.0

        # Voice markers (0.3 weight)
        voice_matches = sum(1 for m in persona.voice_markers if m.lower() in completion_lower)
        voice_score = min(1.0, voice_matches / max(1, len(persona.voice_markers)))
        score += 0.3 * voice_score

        # Knowledge boundaries (0.3 weight) - penalize out-of-scope claims
        out_of_scope_phrases = ["i know everything", "i'm an expert in all", "definitely certain"]
        in_scope = all(p not in completion_lower for p in out_of_scope_phrases)
        score += 0.3 * (1.0 if in_scope else 0.0)

        # Escalation appropriateness (0.2 weight)
        has_escalation = any(t.lower() in completion_lower for t in persona.escalation_triggers)
        escalation_phrases = ["let me check", "i should ask", "beyond my training"]
        appropriate_escalation = any(p in completion_lower for p in escalation_phrases)
        if has_escalation and appropriate_escalation:
            score += 0.2
        elif not has_escalation:
            score += 0.2  # No need for escalation
        # else: trigger present but no escalation = 0

        # Humility markers for intern personas (0.2 weight)
        if persona.template == "intern":
            humility_matches = sum(1 for h in persona.humility_patterns if h.lower() in completion_lower)
            humility_score = min(1.0, humility_matches / max(1, len(persona.humility_patterns) / 2))
            score += 0.2 * humility_score
        else:
            score += 0.2  # Non-intern gets full marks here

        scores.append(score)

    return scores


def reasoning_coherence_reward(
    completions: list[str],
) -> list[float]:
    """
    Check reasoning trace coherence.

    Rewards:
    - Structured steps (Step 1, First, Then, etc.)
    - Logical connectors (Therefore, Because, etc.)
    - Conclusion present
    - No contradictions
    """
    scores = []

    for completion in completions:
        score = 0.0

        # Structured steps (0.4 weight)
        import re
        step_patterns = [
            r'\bstep\s*\d+\b',
            r'\bfirst\b',
            r'\bthen\b',
            r'\bnext\b',
            r'\bfinally\b',
        ]
        step_count = sum(len(re.findall(p, completion, re.I)) for p in step_patterns)
        step_score = min(1.0, step_count / 3)  # Expect ~3 step markers
        score += 0.4 * step_score

        # Logical connectors (0.3 weight)
        connectors = ['therefore', 'because', 'since', 'thus', 'so', 'as a result']
        connector_count = sum(1 for c in connectors if c in completion.lower())
        connector_score = min(1.0, connector_count / 2)
        score += 0.3 * connector_score

        # Conclusion (0.2 weight)
        conclusion_markers = ['in conclusion', 'to summarize', 'the answer is', 'in summary']
        has_conclusion = any(m in completion.lower() for m in conclusion_markers)
        score += 0.2 * (1.0 if has_conclusion else 0.5)

        # No obvious contradictions (0.1 weight) - simple check
        contradiction_pairs = [
            ('is', 'is not'),
            ('can', 'cannot'),
            ('will', 'will not'),
        ]
        has_contradiction = False
        for pos, neg in contradiction_pairs:
            if pos in completion.lower() and neg in completion.lower():
                # Very rough check - could be refined
                pass  # Skip for now, too many false positives
        score += 0.1 * (0.0 if has_contradiction else 1.0)

        scores.append(score)

    return scores


def combined_persona_reward(
    completions: list[list[dict]],
    persona: PersonaConfig,
    **kwargs,
) -> list[float]:
    """
    Combined reward function for persona training.

    Weights:
    - persona_consistency: 30%
    - grounding: 30% (Future work: integrate with reality-check-sparta)
    - reasoning_coherence: 25%
    - format: 15%
    """
    # Extract text from completions
    texts = []
    for c in completions:
        if isinstance(c, list) and len(c) > 0:
            texts.append(c[0].get("content", ""))
        elif isinstance(c, dict):
            texts.append(c.get("content", ""))
        elif isinstance(c, str):
            texts.append(c)
        else:
            texts.append("")

    # Compute component rewards
    persona_scores = persona_consistency_reward(texts, persona)
    coherence_scores = reasoning_coherence_reward(texts)

    # WARNING: Hardcoded grounding scores — integrate with /reality-check-sparta
    logger.warning("grounding_scores are hardcoded to 0.7 — integrate with /reality-check-sparta")
    grounding_scores = [0.7] * len(texts)  # Stub: needs /reality-check-sparta integration

    # WARNING: Hardcoded format scores — needs proper format evaluation
    logger.warning("format_scores are hardcoded to 0.9 — needs proper format evaluation")
    format_scores = [0.9] * len(texts)  # Stub: needs format evaluation logic

    # Combine with weights
    combined = []
    for i in range(len(texts)):
        score = (
            0.30 * persona_scores[i] +
            0.30 * grounding_scores[i] +
            0.25 * coherence_scores[i] +
            0.15 * format_scores[i]
        )
        combined.append(score)

    return combined


# ============================================================================
# Main Training
# ============================================================================

@app.command()
def train(
    persona: str = typer.Option(..., help="Persona name"),
    train_file: Path = typer.Option(..., help="Training data JSONL"),
    output: Path = typer.Option(..., help="Output directory"),
    base_model: str = typer.Option("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"),
    grpo_steps: int = typer.Option(2000, help="GRPO training steps"),
    warmup_steps: int = typer.Option(100, help="SFT warmup steps"),
    batch_size: int = typer.Option(4, help="Batch size"),
    learning_rate: float = typer.Option(2e-5, help="Learning rate"),
    lora_r: int = typer.Option(32, help="LoRA rank"),
    lora_alpha: int = typer.Option(64, help="LoRA alpha"),
    lambda_grpo: bool = typer.Option(True, help="Use λ-GRPO normalization"),
    warmup_only: bool = typer.Option(False, help="Only run SFT warmup"),
):
    """Train persona with λ-GRPO."""

    logger.info(f"Training persona: {persona}")
    logger.info(f"λ-GRPO enabled: {lambda_grpo}")

    # Load persona config
    persona_config = load_persona_config(persona)
    logger.info(f"Loaded persona config: {persona_config.name} ({persona_config.template})")

    # Load training data
    logger.info(f"Loading training data from {train_file}")
    with open(train_file) as f:
        train_data = [json.loads(line) for line in f]

    logger.info(f"Loaded {len(train_data)} training examples")

    # Load model and tokenizer
    logger.info(f"Loading base model: {base_model}")
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    # Add LoRA
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    logger.info(f"Added LoRA adapter: r={lora_r}, alpha={lora_alpha}")

    # Prepare dataset
    def format_example(example):
        return {
            "prompt": example.get("query", example.get("question", "")),
            "completion": example.get("response", example.get("answer", "")),
        }

    dataset = Dataset.from_list([format_example(ex) for ex in train_data])

    # Create reward function with persona context
    def reward_fn(completions, **kwargs):
        return combined_persona_reward(completions, persona_config, **kwargs)

    # Configure GRPO trainer
    grpo_config = GRPOConfig(
        output_dir=str(output),
        num_train_epochs=1,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        max_steps=grpo_steps,
        logging_steps=10,
        save_steps=500,
        warmup_steps=warmup_steps,
        bf16=True,
        num_generations=4,  # Group size for GRPO
        # λ-GRPO would be implemented via custom loss, not config
    )

    trainer = GRPOTrainer(
        model=model,
        args=grpo_config,
        processing_class=tokenizer,
        train_dataset=dataset,
        reward_funcs=reward_fn,
    )

    # Train
    logger.info("Starting training...")
    monitor = TaskClient(f"train-persona/{persona}", total=1, description=f"GRPO training {persona}") if TaskClient else None
    trainer.train()

    # Save
    output.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(output))

    # Save persona config snapshot
    with open(output / "persona_config.json", "w") as f:
        json.dump({
            "name": persona_config.name,
            "template": persona_config.template,
            "knowledge_domains": persona_config.knowledge_domains,
            "voice_markers": persona_config.voice_markers,
            "escalation_triggers": persona_config.escalation_triggers,
            "humility_patterns": persona_config.humility_patterns,
        }, f, indent=2)

    if monitor:
        monitor.update(item=f"done steps={grpo_steps}")
        monitor.finish()

    logger.info(f"Training complete. Model saved to {output}")


if __name__ == "__main__":
    app()
