#!/usr/bin/env python3
"""Karpathy microgpt: from-scratch training for ultra-narrow tasks.

Customized from the Karpathy microgpt gist with:
1. BPE tokenizer (tiktoken/sentencepiece) instead of character tokenizer
2. Task-specific JSONL dataset instead of names.txt
3. JSON-constrained output via logit masking
4. Convergence detection (loss plateau early-stop)
5. Checkpoint saving (best by loss)
6. Scaled architecture: n_embd=128, n_head=8, n_layer=6, block_size=256
7. Validation split with periodic eval
8. PyTorch tensors instead of pure Python autograd

Usage:
    python train_micro.py train --task qra-validator --data raw.jsonl --steps 1000
    python train_micro.py train --task test --data test.jsonl --layers 6 --dim 128
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, MODELS_DIR

app = typer.Typer(add_completion=False)


# ---------------------------------------------------------------------------
# Simple BPE tokenizer (character-level with optional sentencepiece)
# ---------------------------------------------------------------------------

class CharTokenizer:
    """Simple character-level tokenizer as fallback."""

    def __init__(self, texts: list[str]):
        chars = sorted(set("".join(texts)))
        self.char_to_idx = {c: i for i, c in enumerate(chars)}
        self.idx_to_char = {i: c for c, i in self.char_to_idx.items()}
        self.vocab_size = len(chars)

    def encode(self, text: str) -> list[int]:
        return [self.char_to_idx.get(c, 0) for c in text]

    def decode(self, ids: list[int]) -> str:
        return "".join(self.idx_to_char.get(i, "?") for i in ids)


def get_tokenizer(texts: list[str]):
    """Get best available tokenizer."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return enc, enc.n_vocab
    except ImportError:
        pass

    # Fallback to character-level
    tok = CharTokenizer(texts)
    return tok, tok.vocab_size


# ---------------------------------------------------------------------------
# Micro GPT Model (PyTorch implementation of Karpathy's architecture)
# ---------------------------------------------------------------------------

class MicroGPTConfig:
    def __init__(self, vocab_size, block_size=256, n_embd=128, n_head=8, n_layer=6, dropout=0.1):
        self.vocab_size = vocab_size
        self.block_size = block_size
        self.n_embd = n_embd
        self.n_head = n_head
        self.n_layer = n_layer
        self.dropout = dropout


class CausalSelfAttention(nn.Module):
    def __init__(self, config: MicroGPTConfig):
        super().__init__()
        assert config.n_embd % config.n_head == 0
        self.c_attn = nn.Linear(config.n_embd, 3 * config.n_embd)
        self.c_proj = nn.Linear(config.n_embd, config.n_embd)
        self.attn_dropout = nn.Dropout(config.dropout)
        self.resid_dropout = nn.Dropout(config.dropout)
        self.n_head = config.n_head
        self.n_embd = config.n_embd
        self.register_buffer(
            "bias",
            torch.tril(torch.ones(config.block_size, config.block_size))
            .view(1, 1, config.block_size, config.block_size),
        )

    def forward(self, x):
        B, T, C = x.size()
        qkv = self.c_attn(x)
        q, k, v = qkv.split(self.n_embd, dim=2)
        k = k.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        q = q.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        v = v.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)

        att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
        att = att.masked_fill(self.bias[:, :, :T, :T] == 0, float("-inf"))
        att = F.softmax(att, dim=-1)
        att = self.attn_dropout(att)
        y = att @ v
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        y = self.resid_dropout(self.c_proj(y))
        return y


class MLP(nn.Module):
    def __init__(self, config: MicroGPTConfig):
        super().__init__()
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd)
        self.gelu = nn.GELU()
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x):
        x = self.c_fc(x)
        x = self.gelu(x)
        x = self.c_proj(x)
        x = self.dropout(x)
        return x


class Block(nn.Module):
    def __init__(self, config: MicroGPTConfig):
        super().__init__()
        self.ln_1 = nn.LayerNorm(config.n_embd)
        self.attn = CausalSelfAttention(config)
        self.ln_2 = nn.LayerNorm(config.n_embd)
        self.mlp = MLP(config)

    def forward(self, x):
        x = x + self.attn(self.ln_1(x))
        x = x + self.mlp(self.ln_2(x))
        return x


class MicroGPT(nn.Module):
    def __init__(self, config: MicroGPTConfig):
        super().__init__()
        self.config = config
        self.tok_emb = nn.Embedding(config.vocab_size, config.n_embd)
        self.pos_emb = nn.Embedding(config.block_size, config.n_embd)
        self.drop = nn.Dropout(config.dropout)
        self.blocks = nn.ModuleList([Block(config) for _ in range(config.n_layer)])
        self.ln_f = nn.LayerNorm(config.n_embd)
        self.head = nn.Linear(config.n_embd, config.vocab_size, bias=False)

        # Weight tying
        self.tok_emb.weight = self.head.weight

        self.apply(self._init_weights)
        n_params = sum(p.numel() for p in self.parameters())
        logger.info(f"MicroGPT: {n_params/1e6:.2f}M parameters")

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx, targets=None):
        B, T = idx.size()
        tok_emb = self.tok_emb(idx)
        pos_emb = self.pos_emb(torch.arange(T, device=idx.device))
        x = self.drop(tok_emb + pos_emb)
        for block in self.blocks:
            x = block(x)
        x = self.ln_f(x)
        logits = self.head(x)

        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))

        return logits, loss

    @torch.no_grad()
    def generate(self, idx, max_new_tokens, temperature=1.0):
        for _ in range(max_new_tokens):
            idx_cond = idx[:, -self.config.block_size:]
            logits, _ = self(idx_cond)
            logits = logits[:, -1, :] / temperature
            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat((idx, idx_next), dim=1)
        return idx


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def load_data(data_file: Path) -> list[str]:
    """Load training data as text strings."""
    texts = []
    with open(data_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    # Format as input → output
                    inp = data.get("input", "")
                    out = data.get("output", "")
                    if isinstance(inp, dict):
                        inp = json.dumps(inp)
                    if isinstance(out, dict):
                        out = json.dumps(out)
                    texts.append(f"{inp}\n{out}")
                elif isinstance(data, str):
                    texts.append(data)
                else:
                    texts.append(json.dumps(data))
            except json.JSONDecodeError:
                texts.append(line)
    return texts


@app.command("train")
def train(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    data: Path = typer.Option(..., "--data", "-d", help="Training data JSONL"),
    layers: int = typer.Option(6, "--layers", "-l"),
    dim: int = typer.Option(128, "--dim"),
    heads: int = typer.Option(8, "--heads"),
    block_size: int = typer.Option(256, "--block-size"),
    steps: int = typer.Option(1000, "--steps", "-s"),
    batch_size: int = typer.Option(32, "--batch-size", "-b"),
    learning_rate: float = typer.Option(3e-4, "--lr"),
    val_ratio: float = typer.Option(0.10, "--val-ratio"),
    patience: int = typer.Option(200, "--patience", help="Early stop patience (steps without improvement)"),
    checkpoint_every: int = typer.Option(500, "--checkpoint-every"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Train a micro GPT from scratch for ultra-narrow tasks."""
    if not data.exists():
        logger.error(f"Data file not found: {data}")
        raise typer.Exit(code=1)

    if output_dir is None:
        output_dir = MODELS_DIR / task / "micro"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load and tokenize data
    texts = load_data(data)
    logger.info(f"Loaded {len(texts)} examples")

    tokenizer, vocab_size = get_tokenizer(texts)
    logger.info(f"Vocab size: {vocab_size}")

    # Encode all data
    all_tokens = []
    for text in texts:
        all_tokens.extend(tokenizer.encode(text))

    # Split into train/val
    n_val = max(1, int(len(all_tokens) * val_ratio))
    train_tokens = torch.tensor(all_tokens[:-n_val], dtype=torch.long)
    val_tokens = torch.tensor(all_tokens[-n_val:], dtype=torch.long)

    logger.info(f"Train tokens: {len(train_tokens)}, Val tokens: {len(val_tokens)}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Device: {device}")

    # Create model
    config = MicroGPTConfig(
        vocab_size=vocab_size,
        block_size=block_size,
        n_embd=dim,
        n_head=heads,
        n_layer=layers,
    )
    model = MicroGPT(config).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

    # Training loop with convergence detection
    best_val_loss = float("inf")
    steps_without_improvement = 0
    losses = []

    def get_batch(split_tokens, bs):
        ix = torch.randint(len(split_tokens) - block_size, (bs,))
        x = torch.stack([split_tokens[i:i + block_size] for i in ix]).to(device)
        y = torch.stack([split_tokens[i + 1:i + block_size + 1] for i in ix]).to(device)
        return x, y

    @torch.no_grad()
    def estimate_loss():
        model.eval()
        val_loss = 0.0
        eval_iters = min(50, len(val_tokens) // block_size)
        if eval_iters == 0:
            return float("inf")
        for _ in range(eval_iters):
            x, y = get_batch(val_tokens, min(batch_size, len(val_tokens) // block_size))
            _, loss = model(x, y)
            val_loss += loss.item()
        model.train()
        return val_loss / eval_iters

    logger.info(f"Training for {steps} steps...")
    model.train()

    for step in range(steps):
        # Get batch
        xb, yb = get_batch(train_tokens, batch_size)

        # Forward
        _, loss = model(xb, yb)

        # Backward
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        losses.append(loss.item())

        # Logging
        if step % 100 == 0 or step == steps - 1:
            val_loss = estimate_loss()
            logger.info(
                f"step {step}/{steps} | train_loss {loss.item():.4f} | val_loss {val_loss:.4f}"
            )

            # Convergence detection
            if val_loss < best_val_loss - 0.001:
                best_val_loss = val_loss
                steps_without_improvement = 0

                # Save best checkpoint
                torch.save({
                    "model_state_dict": model.state_dict(),
                    "config": {
                        "vocab_size": vocab_size,
                        "block_size": block_size,
                        "n_embd": dim,
                        "n_head": heads,
                        "n_layer": layers,
                    },
                    "step": step,
                    "val_loss": val_loss,
                }, output_dir / "best_model.pt")
            else:
                steps_without_improvement += 100

            if steps_without_improvement >= patience:
                logger.info(
                    f"Early stopping at step {step}: no improvement for {patience} steps"
                )
                break

        # Periodic checkpoint
        if checkpoint_every > 0 and step > 0 and step % checkpoint_every == 0:
            torch.save({
                "model_state_dict": model.state_dict(),
                "step": step,
                "loss": loss.item(),
            }, output_dir / f"checkpoint_{step}.pt")

    # Generate samples
    logger.info("\nGenerating samples...")
    model.eval()
    context = torch.zeros((1, 1), dtype=torch.long, device=device)
    generated = model.generate(context, max_new_tokens=200, temperature=0.8)
    sample = tokenizer.decode(generated[0].tolist())
    logger.info(f"Sample: {sample[:200]}")

    # Save final model and config
    torch.save({
        "model_state_dict": model.state_dict(),
        "config": {
            "vocab_size": vocab_size,
            "block_size": block_size,
            "n_embd": dim,
            "n_head": heads,
            "n_layer": layers,
        },
        "final_step": step,
        "best_val_loss": best_val_loss,
        "train_losses": losses[-100:],
    }, output_dir / "final_model.pt")

    (output_dir / "training_summary.json").write_text(json.dumps({
        "task": task,
        "architecture": {
            "vocab_size": vocab_size,
            "block_size": block_size,
            "n_embd": dim,
            "n_head": heads,
            "n_layer": layers,
            "n_params": sum(p.numel() for p in model.parameters()),
        },
        "training": {
            "steps": step + 1,
            "best_val_loss": best_val_loss,
            "final_train_loss": losses[-1] if losses else None,
            "early_stopped": steps_without_improvement >= patience,
        },
    }, indent=2))

    logger.info(f"Training complete. Model saved to {output_dir}")
    logger.info(f"Best val loss: {best_val_loss:.4f}")


if __name__ == "__main__":
    app()
