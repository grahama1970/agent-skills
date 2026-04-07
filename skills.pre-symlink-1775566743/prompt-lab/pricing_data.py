"""Provider pricing data models and static pricing cache.

Contains:
- BatchProviderPricing dataclass
- ProviderPricing alias
- PRICING_CACHE static data
- Disk caching helpers
"""
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger


@dataclass
class BatchProviderPricing:
    """Extended pricing info optimized for large batch operations."""
    provider: str
    model_id: str
    input_price_per_m: float  # $ per 1M tokens
    output_price_per_m: float
    context_window: int = 128000
    # Batch-critical fields
    concurrent_connections: int = 1  # Max parallel requests
    tokens_per_sec: float = 50.0  # Realistic output throughput
    batch_api_available: bool = False  # Has async batch API
    batch_discount: float = 0.0  # Discount % for batch API (0.5 = 50% off)
    hourly_cost: Optional[float] = None  # For self-hosted (RunPod)
    reliability_score: int = 3  # 1-5, higher = more stable for overnight
    notes: str = ""


# Legacy ProviderPricing for backward compatibility
ProviderPricing = BatchProviderPricing


PRICING_CACHE = {
    # Chutes pricing - VERIFIED Feb 2026
    "chutes": {
        "deepseek-ai/DeepSeek-V3.2-TEE": BatchProviderPricing(
            provider="chutes",
            model_id="deepseek-ai/DeepSeek-V3.2-TEE",
            input_price_per_m=0.25,
            output_price_per_m=0.38,
            concurrent_connections=6,  # 5-6 concurrent, use 6
            tokens_per_sec=180.0,  # ~30 tok/s per connection x 6
            batch_api_available=False,
            reliability_score=4,
            notes="FP8 quantization, TEE, stable"
        ),
        "deepseek-ai/DeepSeek-V3-0324-TEE": BatchProviderPricing(
            provider="chutes",
            model_id="deepseek-ai/DeepSeek-V3-0324-TEE",
            input_price_per_m=0.19,
            output_price_per_m=0.87,
            concurrent_connections=6,
            tokens_per_sec=180.0,
            reliability_score=4,
            notes="FP8, older version"
        ),
        "deepseek-ai/DeepSeek-V3.1-TEE": BatchProviderPricing(
            provider="chutes",
            model_id="deepseek-ai/DeepSeek-V3.1-TEE",
            input_price_per_m=0.20,
            output_price_per_m=0.80,
            concurrent_connections=6,
            tokens_per_sec=180.0,
            reliability_score=4,
            notes="FP8 quantization, TEE"
        ),
        "deepseek-ai/DeepSeek-R1-0528-TEE": BatchProviderPricing(
            provider="chutes",
            model_id="deepseek-ai/DeepSeek-R1-0528-TEE",
            input_price_per_m=0.40,
            output_price_per_m=1.75,
            concurrent_connections=6,
            tokens_per_sec=60.0,  # Reasoning model is slower
            reliability_score=4,
            notes="Reasoning model, FP8"
        ),
    },
    # OpenRouter - routes to Chutes for DeepSeek, same limits apply
    "openrouter": {
        "deepseek/deepseek-v3.2": BatchProviderPricing(
            provider="openrouter",
            model_id="deepseek/deepseek-v3.2",
            input_price_per_m=0.25,
            output_price_per_m=0.38,
            concurrent_connections=6,  # Backend is Chutes, same limit
            tokens_per_sec=180.0,
            reliability_score=3,  # Extra hop = slightly less reliable
            notes="Routes to Chutes backend - same limits"
        ),
        "deepseek/deepseek-chat-v3-0324": BatchProviderPricing(
            provider="openrouter",
            model_id="deepseek/deepseek-chat-v3-0324",
            input_price_per_m=0.19,
            output_price_per_m=0.87,
            concurrent_connections=6,
            tokens_per_sec=180.0,
            reliability_score=3,
            notes="Routes to Chutes backend"
        ),
        "deepseek/deepseek-chat": BatchProviderPricing(
            provider="openrouter",
            model_id="deepseek/deepseek-chat",
            input_price_per_m=0.28,
            output_price_per_m=0.42,
            concurrent_connections=10,  # Direct DeepSeek has more capacity
            tokens_per_sec=300.0,
            reliability_score=3,
            notes="Routes to DeepSeek direct"
        ),
    },
    # DeepSeek direct API
    "deepseek": {
        "deepseek-chat": BatchProviderPricing(
            provider="deepseek",
            model_id="deepseek-chat",
            input_price_per_m=0.27,
            output_price_per_m=1.10,
            concurrent_connections=20,  # Higher tier limits
            tokens_per_sec=600.0,
            batch_api_available=True,  # Has async batch
            batch_discount=0.25,  # 25% off for batch API
            reliability_score=4,
            notes="Direct API, batch available"
        ),
    },
    # RunPod self-hosted
    "runpod": {
        "8xA100-deepseek-v3": BatchProviderPricing(
            provider="runpod",
            model_id="self-hosted-8xA100",
            input_price_per_m=0.0,
            output_price_per_m=0.0,
            concurrent_connections=32,  # Limited by GPU memory/batch
            tokens_per_sec=150.0,  # Realistic for 8x A100
            hourly_cost=15.0,  # $15/hr for 8x A100-80GB
            reliability_score=5,  # You control it
            notes="Self-hosted, ~$15/hr, full control"
        ),
        "8xH100-deepseek-v3": BatchProviderPricing(
            provider="runpod",
            model_id="self-hosted-8xH100",
            input_price_per_m=0.0,
            output_price_per_m=0.0,
            concurrent_connections=64,
            tokens_per_sec=400.0,  # H100 is much faster
            hourly_cost=32.0,  # ~$32/hr for 8x H100
            reliability_score=5,
            notes="Self-hosted H100, fastest option"
        ),
    },
}


# Cache file for dogpile-researched pricing
PRICING_CACHE_FILE = Path(__file__).parent / ".pricing_cache.json"


def load_cached_pricing() -> dict:
    """Load cached pricing from disk."""
    if PRICING_CACHE_FILE.exists():
        try:
            with open(PRICING_CACHE_FILE) as f:
                data = json.load(f)
                # Check if cache is less than 24 hours old
                cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
                if (datetime.now() - cached_at).total_seconds() < 86400:
                    return data.get("pricing", {})
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
    return {}


def save_cached_pricing(pricing: dict) -> None:
    """Save pricing to disk cache."""
    try:
        with open(PRICING_CACHE_FILE, "w") as f:
            json.dump({
                "cached_at": datetime.now().isoformat(),
                "pricing": pricing,
            }, f, indent=2)
    except Exception as e:
        logger.debug("formatting failed: {}", e)
