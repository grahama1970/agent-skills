#!/usr/bin/env python3
"""Export trained LoRA models to GGUF format for production inference.

Pipeline: Merge LoRA → Save full model → Convert to GGUF via llama.cpp

Usage:
    python export_gguf.py export --task qra-validator --quantize Q4_K_M
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, MODELS_DIR

app = typer.Typer(add_completion=False)

QUANT_TYPES = ["Q4_K_M", "Q5_K_M", "Q8_0", "F16"]


def merge_lora(base_model: str, lora_path: Path, output_path: Path) -> None:
    """Merge LoRA adapter into base model and save full weights."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logger.info(f"Loading base model: {base_model}")
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True,
    )

    logger.info(f"Loading LoRA from: {lora_path}")
    model = PeftModel.from_pretrained(model, str(lora_path))
    model = model.merge_and_unload()

    output_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Saving merged model to: {output_path}")
    model.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))


def convert_to_gguf(model_path: Path, output_path: Path, quantize: str = "Q4_K_M") -> Path:
    """Convert HF model to GGUF format using llama.cpp's convert script.

    Falls back to manual conversion if llama.cpp is not available.
    """
    gguf_path = output_path / f"model-{quantize}.gguf"
    output_path.mkdir(parents=True, exist_ok=True)

    # Try llama.cpp convert_hf_to_gguf.py
    convert_scripts = [
        Path.home() / "llama.cpp" / "convert_hf_to_gguf.py",
        Path("/usr/local/bin/convert_hf_to_gguf.py"),
        Path.home() / ".local" / "bin" / "convert_hf_to_gguf.py",
    ]

    convert_script = None
    for script in convert_scripts:
        if script.exists():
            convert_script = script
            break

    if convert_script is None:
        # Try pip-installed llama-cpp-python convert
        try:
            result = subprocess.run(
                [sys.executable, "-c", "import llama_cpp; print('ok')"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                logger.info("Using llama-cpp-python for conversion")
                _convert_via_llama_cpp(model_path, gguf_path, quantize)
                return gguf_path
        except Exception as e:
            logger.debug("conversion failed: {}", e)

        logger.warning("llama.cpp convert script not found. Saving in HF format only.")
        logger.warning("Install llama.cpp to enable GGUF export:")
        logger.warning("  git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp")
        logger.warning("  pip install -r ~/llama.cpp/requirements.txt")

        # Save a marker file
        marker = output_path / "NEEDS_GGUF_CONVERT.txt"
        marker.write_text(
            f"Run: python ~/llama.cpp/convert_hf_to_gguf.py {model_path} "
            f"--outfile {gguf_path} --outtype {quantize.lower()}\n"
        )
        return output_path

    # Run llama.cpp conversion
    logger.info(f"Converting to GGUF ({quantize})...")

    # First convert to f16 GGUF
    f16_path = output_path / "model-f16.gguf"
    cmd = [
        sys.executable, str(convert_script),
        str(model_path),
        "--outfile", str(f16_path),
        "--outtype", "f16",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"GGUF conversion failed (rc={result.returncode}): {result.stderr}")
        raise RuntimeError(f"GGUF conversion failed (rc={result.returncode}): {result.stderr[-500:]}")

    # Quantize if not F16
    if quantize != "F16":
        quantize_bin = convert_script.parent / "llama-quantize"
        if not quantize_bin.exists():
            quantize_bin = convert_script.parent / "build" / "bin" / "llama-quantize"

        if quantize_bin.exists():
            cmd = [str(quantize_bin), str(f16_path), str(gguf_path), quantize]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Quantization failed (rc={result.returncode}): {result.stderr}")
                raise RuntimeError(f"Quantization failed (rc={result.returncode}): {result.stderr[-500:]}")
            f16_path.unlink(missing_ok=True)
        else:
            logger.warning("llama-quantize not found, keeping F16 GGUF")
            gguf_path = f16_path

    logger.info(f"GGUF export complete: {gguf_path}")
    return gguf_path


def _convert_via_llama_cpp(model_path: Path, gguf_path: Path, quantize: str) -> None:
    """Fallback conversion using llama-cpp-python if available."""
    raise NotImplementedError(
        f"Direct GGUF conversion via llama-cpp-python not yet implemented. "
        f"Use llama.cpp manually: python convert_hf_to_gguf.py {model_path} --outfile {gguf_path}"
    )


@app.command("export")
def export_cmd(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    lora_path: Optional[Path] = typer.Option(None, "--lora", "-l"),
    quantize: str = typer.Option("Q4_K_M", "--quantize", "-q"),
    skip_merge: bool = typer.Option(False, "--skip-merge"),
):
    """Export trained model to GGUF format.

    Pipeline:
    1. Merge LoRA into base model
    2. Convert to GGUF
    3. Quantize (Q4_K_M, Q5_K_M, Q8_0, or F16)
    """
    spec = load_task_spec(task)

    if quantize not in QUANT_TYPES:
        logger.error(f"Invalid quantization type: {quantize}. Choose from: {QUANT_TYPES}")
        raise typer.Exit(code=1)

    if lora_path is None:
        lora_path = MODELS_DIR / spec.name / "sft"

    if not lora_path.exists():
        logger.error(f"LoRA path not found: {lora_path}")
        raise typer.Exit(code=1)

    merged_path = MODELS_DIR / spec.name / "merged"
    gguf_dir = MODELS_DIR / spec.name / "gguf"

    # Step 1: Merge LoRA
    if not skip_merge:
        # Check for mock model
        mock_marker = lora_path / "mock_model.json"
        if mock_marker.exists():
            logger.info("Mock model detected — creating mock GGUF marker")
            gguf_dir.mkdir(parents=True, exist_ok=True)
            (gguf_dir / "mock_model.gguf").write_text(
                json.dumps({"task": spec.name, "quantize": quantize, "mock": True})
            )
            logger.info(f"Mock GGUF created at {gguf_dir}")
            return

        merge_lora(spec.base_model, lora_path, merged_path)
    else:
        merged_path = lora_path

    # Step 2: Convert to GGUF
    gguf_path = convert_to_gguf(merged_path, gguf_dir, quantize)

    # Save export config
    config = {
        "task": spec.name,
        "base_model": spec.base_model,
        "lora_path": str(lora_path),
        "quantize": quantize,
        "gguf_path": str(gguf_path),
    }
    (gguf_dir / "export_config.json").write_text(json.dumps(config, indent=2))

    logger.info(f"Export complete: {gguf_path}")


if __name__ == "__main__":
    app()
