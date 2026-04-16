#!/usr/bin/env python3
"""LoRA Training for SPARTA Intent Mapper.

Trains a LoRA adapter on DeepSeek-R1-Distill-Qwen-7B to convert
natural language queries into QuerySpec JSON.

Usage:
    python train.py --train-file data/sft/train.jsonl --output models/intent-mapper-lora
"""

import json
import os
from pathlib import Path
from typing import Optional

import torch
import typer
from datasets import Dataset
from loguru import logger
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from trl import SFTTrainer

app = typer.Typer()

# Default config
DEFAULT_BASE_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
DEFAULT_OUTPUT_DIR = "models/intent-mapper-lora"


def load_training_data(train_file: str) -> Dataset:
    """Load and format training data for SFT."""
    logger.info(f"Loading training data from {train_file}")

    with open(train_file) as f:
        if train_file.endswith(".json"):
            data = json.load(f)
        else:  # jsonl
            data = [json.loads(line) for line in f]

    logger.info(f"Loaded {len(data)} examples")

    # Format as chat messages
    formatted = []
    system_prompt = """You are a SPARTA QuerySpec generator. Convert user questions about space cybersecurity into structured JSON queries.

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

    for item in data:
        user_query = item["input"]
        output = item["output"]

        # Format output as JSON string
        if isinstance(output, dict):
            output_str = json.dumps(output, indent=2)
        else:
            output_str = output

        formatted.append({
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": output_str},
            ]
        })

    return Dataset.from_list(formatted)


def format_chat(example: dict, tokenizer) -> dict:
    """Format chat messages for the model."""
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


@app.command()
def train(
    train_file: str = typer.Option("data/sft/train.jsonl", "--train-file", "-t"),
    val_file: Optional[str] = typer.Option(None, "--val-file", "-v"),
    output_dir: str = typer.Option(DEFAULT_OUTPUT_DIR, "--output", "-o"),
    base_model: str = typer.Option(DEFAULT_BASE_MODEL, "--base-model", "-m"),
    epochs: int = typer.Option(3, "--epochs", "-e"),
    batch_size: int = typer.Option(4, "--batch-size", "-b"),
    gradient_accumulation: int = typer.Option(4, "--gradient-accumulation", "-g"),
    learning_rate: float = typer.Option(2e-4, "--learning-rate", "-lr"),
    lora_r: int = typer.Option(16, "--lora-r"),
    lora_alpha: int = typer.Option(32, "--lora-alpha"),
    lora_dropout: float = typer.Option(0.05, "--lora-dropout"),
    max_length: int = typer.Option(512, "--max-length"),
    use_4bit: bool = typer.Option(True, "--use-4bit/--no-4bit"),
    use_wandb: bool = typer.Option(False, "--wandb/--no-wandb"),
):
    """Train LoRA adapter for intent mapping."""
    logger.info(f"Starting training with base model: {base_model}")
    logger.info(f"Output directory: {output_dir}")

    # Setup device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device}")

    if device == "cuda":
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
        logger.info(f"Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    # Load tokenizer
    logger.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Quantization config
    if use_4bit and device == "cuda":
        logger.info("Using 4-bit quantization")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
    else:
        bnb_config = None

    # Load model
    logger.info("Loading base model...")
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
    )

    if use_4bit:
        model = prepare_model_for_kbit_training(model)

    # LoRA config
    logger.info(f"Configuring LoRA (r={lora_r}, alpha={lora_alpha})")
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Load data
    train_dataset = load_training_data(train_file)
    train_dataset = train_dataset.map(
        lambda x: format_chat(x, tokenizer),
        remove_columns=["messages"],
    )

    eval_dataset = None
    if val_file:
        eval_dataset = load_training_data(val_file)
        eval_dataset = eval_dataset.map(
            lambda x: format_chat(x, tokenizer),
            remove_columns=["messages"],
        )

    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=10,
        save_strategy="epoch",
        evaluation_strategy="epoch" if eval_dataset else "no",
        bf16=device == "cuda",
        optim="paged_adamw_8bit" if use_4bit else "adamw_torch",
        gradient_checkpointing=True,
        max_grad_norm=0.3,
        report_to="wandb" if use_wandb else "none",
        run_name=f"intent-mapper-{epochs}ep" if use_wandb else None,
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=tokenizer,
        dataset_text_field="text",
        max_seq_length=max_length,
        packing=False,
    )

    # Train
    logger.info("Starting training...")
    trainer.train()

    # Save
    logger.info(f"Saving model to {output_dir}")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Save training config
    config = {
        "base_model": base_model,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "max_length": max_length,
        "train_file": train_file,
    }
    with open(Path(output_dir) / "training_config.json", "w") as f:
        json.dump(config, f, indent=2)

    logger.info("Training complete!")


@app.command()
def prepare(
    input_file: str = typer.Option(..., "--input", "-i", help="Input JSON file"),
    output_file: str = typer.Option(..., "--output", "-o", help="Output JSONL file"),
):
    """Prepare training data from QRA format to SFT format."""
    logger.info(f"Converting {input_file} to {output_file}")

    with open(input_file) as f:
        data = json.load(f)

    with open(output_file, "w") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")

    logger.info(f"Wrote {len(data)} examples to {output_file}")


@app.command()
def merge(
    lora_path: str = typer.Option(DEFAULT_OUTPUT_DIR, "--lora", "-l"),
    base_model: str = typer.Option(DEFAULT_BASE_MODEL, "--base-model", "-m"),
    output_dir: str = typer.Option("models/intent-mapper-merged", "--output", "-o"),
):
    """Merge LoRA adapter into base model."""
    from peft import PeftModel

    logger.info(f"Merging LoRA from {lora_path} into {base_model}")

    # Load base model
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    # Load and merge LoRA
    model = PeftModel.from_pretrained(model, lora_path)
    model = model.merge_and_unload()

    # Save merged model
    logger.info(f"Saving merged model to {output_dir}")
    model.save_pretrained(output_dir)

    # Save tokenizer
    tokenizer = AutoTokenizer.from_pretrained(lora_path)
    tokenizer.save_pretrained(output_dir)

    logger.info("Merge complete!")


@app.command()
def infer(
    query: str = typer.Argument(..., help="Query to test"),
    model_path: str = typer.Option(DEFAULT_OUTPUT_DIR, "--model", "-m"),
    base_model: str = typer.Option(DEFAULT_BASE_MODEL, "--base-model"),
):
    """Test inference with trained model."""
    from peft import PeftModel

    logger.info(f"Loading model from {model_path}")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    # Load model with LoRA
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, model_path)
    model.eval()

    # Format prompt
    system_prompt = "You are a SPARTA QuerySpec generator. Convert user questions about space cybersecurity into structured JSON queries."
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    # Generate
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.1,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Extract assistant response
    if "<|assistant|>" in response:
        response = response.split("<|assistant|>")[-1].strip()

    print(f"\nQuery: {query}")
    print(f"\nResponse:\n{response}")


if __name__ == "__main__":
    app()
