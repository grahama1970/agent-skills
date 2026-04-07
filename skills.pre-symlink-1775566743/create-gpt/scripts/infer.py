#!/usr/bin/env python3
"""Inference via Ollama (preferred), llama-cpp-python (GGUF), or HuggingFace+PEFT.

Usage:
    python infer.py run '{"question": "test?"}' --task qra-validator
    python infer.py run '{"question": "test?"}' --task qra-validator --mode ollama
    python infer.py run '{"question": "test?"}' --task qra-validator --mode gguf
    python infer.py run '{"question": "test?"}' --task qra-validator --mode hf
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
from task_spec import load_task_spec, MODELS_DIR

app = typer.Typer(add_completion=False)

OLLAMA_BASE = "http://localhost:11434"


def infer_ollama(
    task_name: str,
    input_text: str,
    model_name: Optional[str] = None,
    max_tokens: int = 512,
    temperature: float = 0.1,
) -> dict:
    """Run inference via Ollama API (preferred — model stays loaded in VRAM).

    Returns dict with 'output', 'confidence', 'latency_ms', 'raw'.
    """
    import httpx

    spec = load_task_spec(task_name)

    if model_name is None:
        model_name = f"embry/{task_name}"

    messages = []
    if spec.system_prompt:
        messages.append({"role": "system", "content": spec.system_prompt})
    messages.append({"role": "user", "content": input_text})

    start = time.time()
    resp = httpx.post(
        f"{OLLAMA_BASE}/api/chat",
        json={
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    latency_ms = (time.time() - start) * 1000

    content = data.get("message", {}).get("content", "")
    confidence = _extract_confidence(content, None)

    try:
        output = json.loads(content.strip())
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if match:
            try:
                output = json.loads(match.group())
            except json.JSONDecodeError:
                output = {"raw": content}
        else:
            output = {"raw": content}

    return {
        "output": output,
        "confidence": confidence,
        "latency_ms": latency_ms,
        "raw": content,
    }


def infer_gguf(
    task_name: str,
    input_text: str,
    model_path: Optional[Path] = None,
    max_tokens: int = 512,
    temperature: float = 0.1,
) -> dict:
    """Run inference using llama-cpp-python on a GGUF model.

    Returns dict with 'output', 'confidence', 'latency_ms', 'logprobs'.
    """
    from llama_cpp import Llama

    spec = load_task_spec(task_name)

    if model_path is None:
        gguf_dir = MODELS_DIR / task_name / "gguf"
        # Find first .gguf file
        gguf_files = list(gguf_dir.glob("*.gguf"))
        if not gguf_files:
            raise FileNotFoundError(f"No GGUF files found in {gguf_dir}")
        model_path = gguf_files[0]

    # Check for mock model
    if model_path.suffix == ".gguf":
        try:
            content = model_path.read_text()
            mock_data = json.loads(content)
            if mock_data.get("mock"):
                return _mock_infer(spec, input_text)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # Real GGUF file, proceed

    logger.info(f"Loading GGUF model: {model_path}")
    llm = Llama(
        model_path=str(model_path),
        n_ctx=spec.max_seq_length * 2,
        n_gpu_layers=-1,
        verbose=False,
    )

    # Build prompt
    messages = []
    if spec.system_prompt:
        messages.append({"role": "system", "content": spec.system_prompt})
    messages.append({"role": "user", "content": input_text})

    start = time.time()
    response = llm.create_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        logprobs=True,
    )
    latency_ms = (time.time() - start) * 1000

    content = response["choices"][0]["message"]["content"]

    # Extract confidence from output or logprobs
    confidence = _extract_confidence(content, response)

    # Parse JSON output
    try:
        output = json.loads(content.strip())
    except json.JSONDecodeError:
        output = {"raw": content}

    return {
        "output": output,
        "confidence": confidence,
        "latency_ms": latency_ms,
        "raw": content,
    }


def infer_hf(
    task_name: str,
    input_text: str,
    model_path: Optional[Path] = None,
    max_tokens: int = 512,
    temperature: float = 0.1,
) -> dict:
    """Run inference using HuggingFace transformers + PEFT."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    spec = load_task_spec(task_name)

    if model_path is None:
        model_path = MODELS_DIR / task_name / "sft"

    # Check for mock model
    mock_marker = model_path / "mock_model.json"
    if mock_marker.exists():
        return _mock_infer(spec, input_text)

    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        spec.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    try:
        model = PeftModel.from_pretrained(base, str(model_path))
    except Exception:
        model = base
    model.eval()

    messages = []
    if spec.system_prompt:
        messages.append({"role": "system", "content": spec.system_prompt})
    messages.append({"role": "user", "content": input_text})

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    start = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.pad_token_id,
        )
    latency_ms = (time.time() - start) * 1000

    generated = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
    )

    # Parse JSON output
    try:
        output = json.loads(generated.strip())
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', generated, re.DOTALL)
        if match:
            try:
                output = json.loads(match.group())
            except json.JSONDecodeError:
                output = {"raw": generated}
        else:
            output = {"raw": generated}

    confidence = _extract_confidence(generated, None)

    return {
        "output": output,
        "confidence": confidence,
        "latency_ms": latency_ms,
        "raw": generated,
    }


def _extract_confidence(content: str, response: Optional[dict]) -> float:
    """Extract confidence from model output or logprobs.

    Sources:
    1. Explicit 'confidence' field in JSON output
    2. Top-1 logprob from llama-cpp-python
    3. Format validation score as fallback
    """
    import math

    # Try explicit confidence field
    try:
        parsed = json.loads(content.strip())
        if isinstance(parsed, dict) and "confidence" in parsed:
            return float(parsed["confidence"])
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Try logprobs from llama.cpp response
    if response and "choices" in response:
        choice = response["choices"][0]
        logprobs = choice.get("logprobs")
        if logprobs and "token_logprobs" in logprobs:
            token_logprobs = logprobs["token_logprobs"]
            valid_logprobs = [lp for lp in token_logprobs if lp is not None]
            if valid_logprobs:
                avg_logprob = sum(valid_logprobs) / len(valid_logprobs)
                return min(1.0, max(0.0, math.exp(avg_logprob)))

    # Fallback: format validation
    try:
        json.loads(content.strip())
        return 0.7  # Valid JSON gets moderate confidence
    except (json.JSONDecodeError, AttributeError):
        return 0.3  # Invalid JSON gets low confidence


def _mock_infer(spec, input_text: str) -> dict:
    """Mock inference for testing."""
    import random

    # Generate a plausible output based on output schema
    output = {}
    if spec.output_schema:
        properties = spec.output_schema.get("properties", {})
        for key, prop in properties.items():
            prop_type = prop.get("type")
            if prop_type == "boolean":
                output[key] = random.choice([True, False])
            elif prop_type == "number":
                output[key] = round(random.random(), 2)
            elif prop_type == "string":
                output[key] = f"mock_{key}"
            elif prop_type == "array":
                output[key] = []
            elif prop_type == "object":
                output[key] = {}
    else:
        output = {"result": "mock", "valid": True, "confidence": 0.85}

    return {
        "output": output,
        "confidence": 0.5 + random.random() * 0.4,
        "latency_ms": 10 + random.random() * 50,
        "raw": json.dumps(output),
        "mock": True,
    }


@app.command("run")
def run_cmd(
    input_text: str = typer.Argument(..., help="Input text or JSON"),
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    mode: str = typer.Option("ollama", "--mode", "-m", help="Inference mode: ollama, gguf, or hf"),
    model_path: Optional[Path] = typer.Option(None, "--model"),
    max_tokens: int = typer.Option(512, "--max-tokens"),
    temperature: float = typer.Option(0.1, "--temperature"),
):
    """Run inference on a single input."""
    if mode == "ollama":
        result = infer_ollama(task, input_text, max_tokens=max_tokens, temperature=temperature)
    elif mode == "gguf":
        result = infer_gguf(task, input_text, model_path, max_tokens, temperature)
    elif mode == "hf":
        result = infer_hf(task, input_text, model_path, max_tokens, temperature)
    else:
        logger.error(f"Unknown mode: {mode}. Use 'ollama', 'gguf', or 'hf'")
        raise typer.Exit(code=1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    app()
