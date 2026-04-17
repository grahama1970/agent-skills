"""
Pricing data models and static pricing cache.

Contains dataclasses and the PRICING_CACHE with verified provider pricing.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Add skill paths for imports
SKILLS_DIR = Path(__file__).resolve().parents[1]
OPS_CHUTES_DIR = SKILLS_DIR / "ops-chutes"
OPS_RUNPOD_DIR = SKILLS_DIR / "ops-runpod" / "src"
# Alternative RunPod path
OPS_RUNPOD_ALT = SKILLS_DIR / "ops-runpod" / "runpod_ops_src" / "runpod_ops"

for path in [str(OPS_CHUTES_DIR), str(OPS_RUNPOD_DIR), str(OPS_RUNPOD_ALT)]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Try to import from ops-chutes
ChutesClient = None
CHUTES_AVAILABLE = False
try:
    from util import ChutesClient
    CHUTES_AVAILABLE = True
except ImportError:
    pass

# Try to import from ops-runpod (multiple possible paths)
RunPodCalculator = None
RUNPOD_AVAILABLE = False
try:
    from runpod_ops_fixed.core.cost_calculator import CostCalculator as RunPodCalculator
    RUNPOD_AVAILABLE = True
except ImportError:
    try:
        from runpod_ops.cost_calculator import CostCalculator as RunPodCalculator
        RUNPOD_AVAILABLE = True
    except ImportError:
        pass


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


# Batch-optimized pricing cache
# Prices as of Feb 2026
# Key metrics for large batches:
#   - concurrent_connections: Max parallel requests (critical for throughput)
#   - tokens_per_sec: Realistic generation throughput
#   - batch_discount: Discount for async batch API (if available)
#   - reliability: 1-5 scale for overnight stability

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
