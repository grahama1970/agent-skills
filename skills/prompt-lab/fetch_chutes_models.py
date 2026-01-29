#!/usr/bin/env python3
"""
Fetch available Chutes models and update models.json.

This script scrapes the Chutes catalog to get the current list of available
LLM models, filtering for text generation models suitable for taxonomy extraction.
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import httpx
except ImportError:
    print("httpx required: pip install httpx")
    sys.exit(1)


CHUTES_CATALOG_URL = "https://api.chutes.ai/chutes/"
CHUTES_BROWSE_URL = "https://chutes.ai/app/browse"
SKILL_DIR = Path(__file__).parent
MODELS_FILE = SKILL_DIR / "models.json"


def get_api_key() -> Optional[str]:
    """Get Chutes API key from environment."""
    return os.environ.get("CHUTES_API_KEY", "").strip('"\'') or None


def fetch_catalog_api(api_key: str) -> List[Dict[str, Any]]:
    """Fetch models from Chutes catalog API."""
    headers = {"x-api-key": api_key, "Accept": "application/json"}

    try:
        with httpx.Client(timeout=30) as client:
            # Try the public catalog endpoint
            resp = client.get(CHUTES_CATALOG_URL, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                return data.get("chutes", data.get("data", []))
    except Exception as e:
        print(f"API fetch failed: {e}")
    return []


def parse_model_entry(chute: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse a chute entry into a model config entry."""
    name = chute.get("name", "")
    slug = chute.get("slug", "")

    # Filter for LLM text models (skip image, audio, embedding models)
    if not name:
        return None

    # Skip non-text models
    skip_patterns = [
        "flux", "stable-diffusion", "whisper", "tts", "embedding",
        "rerank", "vision-only", "image", "audio", "speech"
    ]
    name_lower = name.lower()
    if any(p in name_lower for p in skip_patterns):
        return None

    # Generate a short alias
    alias = name.split("/")[-1].lower()
    alias = re.sub(r"[^a-z0-9-]", "-", alias)
    alias = re.sub(r"-+", "-", alias).strip("-")

    # Truncate very long names
    if len(alias) > 30:
        alias = alias[:30].rstrip("-")

    return {
        "alias": alias,
        "model_id": name,
        "slug": slug,
        "notes": f"From Chutes catalog"
    }


def load_existing_models() -> Dict[str, Any]:
    """Load existing models.json."""
    if MODELS_FILE.exists():
        return json.loads(MODELS_FILE.read_text())
    return {}


def merge_models(existing: Dict[str, Any], new_models: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge new models into existing config, preserving manual entries."""
    result = dict(existing)

    # Track which aliases are already defined
    existing_model_ids = {
        v.get("model", "").lower()
        for v in existing.values()
        if isinstance(v, dict) and v.get("model")
    }

    added = 0
    for entry in new_models:
        model_id = entry.get("model_id", "")
        alias = entry.get("alias", "")

        if not model_id or not alias:
            continue

        # Skip if model already exists
        if model_id.lower() in existing_model_ids:
            continue

        # Make alias unique
        base_alias = alias
        counter = 1
        while alias in result:
            alias = f"{base_alias}-{counter}"
            counter += 1

        result[alias] = {
            "provider": "chutes",
            "model": model_id,
            "notes": entry.get("notes", "Auto-discovered from Chutes catalog")
        }
        added += 1

    return result, added


def fetch_known_models() -> List[Dict[str, Any]]:
    """Return known Chutes models with full metadata as fallback when API unavailable."""
    # These are models known to be available on Chutes as of 2026-01
    # Includes parameter counts, context length, and capabilities
    return [
        # DeepSeek family - 671B MoE with 37B active
        {"alias": "deepseek-v3", "model_id": "deepseek-ai/DeepSeek-V3-0324-TEE",
         "params_b": 671, "active_params_b": 37, "context_k": 128, "arch": "MoE",
         "json_mode": True, "taxonomy_f1": 0.95, "notes": "Original V3, proven for taxonomy"},
        {"alias": "deepseek-v3.1", "model_id": "deepseek-ai/DeepSeek-V3.1-TEE",
         "params_b": 671, "active_params_b": 37, "context_k": 128, "arch": "MoE",
         "json_mode": True, "thinking_mode": True, "notes": "V3.1 with thinking modes"},
        {"alias": "deepseek-v3.2", "model_id": "deepseek-ai/DeepSeek-V3.2-TEE",
         "params_b": 671, "active_params_b": 37, "context_k": 128, "arch": "MoE",
         "json_mode": True, "thinking_mode": True, "notes": "Latest V3.2"},
        {"alias": "deepseek-v3.2-speciale", "model_id": "deepseek-ai/DeepSeek-V3.2-Speciale-TEE",
         "params_b": 671, "active_params_b": 37, "context_k": 128, "arch": "MoE",
         "json_mode": True, "notes": "V3.2 Speciale variant"},
        {"alias": "deepseek-terminus", "model_id": "deepseek-ai/DeepSeek-V3.1-Terminus-TEE",
         "params_b": 671, "active_params_b": 37, "context_k": 128, "arch": "MoE",
         "json_mode": True, "thinking_mode": True, "agentic": True,
         "notes": "V3.1 Terminus - optimized for reasoning, coding, agentic tool use"},
        {"alias": "deepseek-r1", "model_id": "deepseek-ai/DeepSeek-R1-TEE",
         "params_b": 671, "active_params_b": 37, "context_k": 128, "arch": "MoE",
         "json_mode": True, "reasoning": True, "notes": "R1 reasoning model"},
        {"alias": "deepseek-r1-0528", "model_id": "deepseek-ai/DeepSeek-R1-0528-TEE",
         "params_b": 671, "active_params_b": 37, "context_k": 128, "arch": "MoE",
         "json_mode": True, "reasoning": True, "notes": "R1 May 2028 release"},

        # Qwen family
        {"alias": "qwen3-235b", "model_id": "Qwen/Qwen3-235B-A22B-Instruct-2507-TEE",
         "params_b": 235, "active_params_b": 22, "context_k": 128, "arch": "MoE",
         "json_mode": True, "notes": "Qwen3 235B MoE"},
        {"alias": "qwen3-coder-480b", "model_id": "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8-TEE",
         "params_b": 480, "active_params_b": 35, "context_k": 128, "arch": "MoE",
         "json_mode": True, "coding": True, "notes": "Qwen3 Coder 480B - largest Qwen"},
        {"alias": "qwen2.5-72b", "model_id": "Qwen/Qwen2.5-72B-Instruct",
         "params_b": 72, "context_k": 128, "arch": "Dense",
         "json_mode": True, "notes": "Qwen 2.5 72B dense"},
        {"alias": "qwen3-32b", "model_id": "Qwen/Qwen3-32B",
         "params_b": 32, "context_k": 128, "arch": "Dense",
         "json_mode": True, "notes": "Qwen3 32B dense"},

        # Kimi family - 1T MoE with 32B active
        {"alias": "kimi-k2.5", "model_id": "moonshotai/Kimi-K2.5-TEE",
         "params_b": 1000, "active_params_b": 32, "context_k": 128, "arch": "MoE",
         "json_mode": False, "notes": "Kimi K2.5 - FAILS JSON mode"},
        {"alias": "kimi-thinking", "model_id": "moonshotai/Kimi-K2-Thinking-TEE",
         "params_b": 1000, "active_params_b": 32, "context_k": 128, "arch": "MoE",
         "json_mode": True, "reasoning": True, "notes": "Kimi K2 Thinking - reasoning variant"},
        {"alias": "kimi-instruct", "model_id": "moonshotai/Kimi-K2-Instruct-0905",
         "params_b": 1000, "active_params_b": 32, "context_k": 128, "arch": "MoE",
         "json_mode": True, "notes": "Kimi K2 Instruct - September 2025"},

        # Hermes (Llama-based)
        {"alias": "hermes-405b", "model_id": "NousResearch/Hermes-4-405B-FP8-TEE",
         "params_b": 405, "context_k": 128, "arch": "Dense",
         "json_mode": True, "notes": "Hermes 4 405B dense (Llama base)"},
        {"alias": "hermes-70b", "model_id": "NousResearch/Hermes-4-70B",
         "params_b": 70, "context_k": 128, "arch": "Dense",
         "json_mode": True, "notes": "Hermes 4 70B dense"},

        # Others
        {"alias": "glm-4.7", "model_id": "zai-org/GLM-4.7-TEE",
         "params_b": 9, "context_k": 128, "arch": "Dense",
         "json_mode": True, "notes": "GLM 4.7 - efficient"},
        {"alias": "minimax", "model_id": "MiniMaxAI/MiniMax-M2.1-TEE",
         "params_b": 456, "active_params_b": 45.9, "context_k": 1000, "arch": "MoE",
         "json_mode": True, "notes": "MiniMax M2.1 - 1M context"},
    ]


def list_models_by_capability(capability: str = "json_mode") -> None:
    """List models filtered by capability."""
    existing = load_existing_models()

    print(f"\nModels with {capability}=True:")
    print("-" * 60)

    for alias, config in existing.items():
        if alias.startswith("_"):
            continue
        if not isinstance(config, dict):
            continue
        if config.get(capability):
            params = config.get("params_b", "?")
            active = config.get("active_params_b")
            arch = config.get("architecture", "?")
            ctx = config.get("context_k", "?")
            param_str = f"{params}B" if not active else f"{params}B/{active}B active"
            print(f"  {alias:25} {param_str:20} {arch:6} {ctx}K ctx")


def list_all_models() -> None:
    """List all models with key metrics."""
    existing = load_existing_models()

    print("\nAll Chutes Models:")
    print("-" * 100)
    print(f"{'Alias':<22} {'Params':<15} {'Quant':<6} {'Arch':<6} {'Experts':<10} {'Ctx':<7} {'JSON':<5} {'Caps'}")
    print("-" * 100)

    for alias, config in existing.items():
        if alias.startswith("_"):
            continue
        if not isinstance(config, dict):
            continue

        params = config.get("params_b", "?")
        active = config.get("active_params_b")
        quant = config.get("quantization", "?")
        arch = config.get("architecture", "?")
        experts = config.get("experts")
        experts_active = config.get("experts_active")
        ctx = config.get("context_k", "?")
        json_mode = "✓" if config.get("json_mode") else "✗"

        caps = []
        if config.get("reasoning"):
            caps.append("reason")
        if config.get("thinking_mode"):
            caps.append("think")
        if config.get("agentic"):
            caps.append("agent")
        if config.get("coding"):
            caps.append("code")
        if config.get("taxonomy_f1"):
            caps.append(f"F1:{config['taxonomy_f1']}")

        param_str = f"{params}B" if not active else f"{params}B/{active}B"
        expert_str = f"{experts_active}/{experts}" if experts else "-"
        ctx_str = f"{ctx}K" if ctx != "?" else "?"
        caps_str = ", ".join(caps) if caps else ""

        print(f"{alias:<22} {param_str:<15} {quant:<6} {arch:<6} {expert_str:<10} {ctx_str:<7} {json_mode:<5} {caps_str}")


def update_models():
    """Fetch and update models from Chutes catalog."""
    api_key = get_api_key()

    print("Fetching Chutes model catalog...")

    # Try API first
    chutes = []
    if api_key:
        chutes = fetch_catalog_api(api_key)

    if chutes:
        print(f"Found {len(chutes)} chutes from API")
        new_models = [parse_model_entry(c) for c in chutes]
        new_models = [m for m in new_models if m is not None]
    else:
        print("API unavailable, using known models list")
        new_models = fetch_known_models()

    print(f"Parsed {len(new_models)} text models")

    # Load and merge
    existing = load_existing_models()
    merged, added = merge_models(existing, new_models)

    # Preserve comment and add timestamp
    from datetime import date
    if "_comment" not in merged:
        merged = {"_comment": "Models available on Chutes.ai - auto-updated", **merged}
    merged["_updated"] = str(date.today())

    # Save
    MODELS_FILE.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"Updated {MODELS_FILE}")
    print(f"  Added {added} new models")
    print(f"  Total models: {len([k for k in merged if not k.startswith('_')])}")


def main():
    """Main entry point with CLI."""
    import argparse
    parser = argparse.ArgumentParser(description="Manage Chutes model catalog")
    parser.add_argument("command", nargs="?", default="update",
                        choices=["update", "list", "json", "reasoning", "agentic"],
                        help="Command: update, list, json, reasoning, agentic")
    args = parser.parse_args()

    if args.command == "update":
        update_models()
    elif args.command == "list":
        list_all_models()
    elif args.command == "json":
        list_models_by_capability("json_mode")
    elif args.command == "reasoning":
        list_models_by_capability("reasoning")
    elif args.command == "agentic":
        list_models_by_capability("agentic")


if __name__ == "__main__":
    main()
