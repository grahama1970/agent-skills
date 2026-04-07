#!/usr/bin/env python3
"""
Deepseek V3 FP8 Configuration for RunPod Deployment.

This module provides optimized configuration for deploying Deepseek V3 (671B MoE)
with FP8 quantization on RunPod GPU instances.

Key Requirements:
- 8x H100 80GB or 8x A100 80GB (minimum 640GB total VRAM for FP8)
- ~350GB disk space for FP8 model weights
- SGLang inference server with FP8 support
- Tensor parallelism TP=8
"""

from dataclasses import dataclass
from typing import Literal, Optional
import os

DEFAULT_TARGET_TOKENS = int(os.getenv("DEEPSEEK_V3_TARGET_TOKENS", "90000000"))


@dataclass
class DeepseekV3Config:
    """Deepseek V3 FP8 deployment configuration."""

    # Model specifications
    model_id: str = "deepseek-ai/DeepSeek-V3"
    model_size_params: str = "671B"  # 671B parameters (MoE architecture)
    model_size_fp8_gb: int = 350  # ~350GB for FP8 weights
    active_params: str = "37B"  # Only 37B active per forward pass (MoE)

    # GPU requirements
    min_gpu_count: int = 8
    min_vram_per_gpu_gb: int = 80
    recommended_gpu: str = "A100_80GB"  # Cost-effective choice
    premium_gpu: str = "H100"  # Faster but more expensive
    tensor_parallel: int = 8  # TP=8 for 8 GPUs

    # Disk/volume requirements
    min_volume_gb: int = 500  # For model + cache + checkpoints
    recommended_volume_gb: int = 750  # Extra headroom

    # Docker configuration
    docker_image: str = "lmsysorg/sglang:latest"  # SGLang with FP8 support
    alternative_image: str = "vllm/vllm-openai:latest"  # vLLM alternative

    # Server configuration
    port: int = 8000
    max_model_len: int = 32768  # 32K context
    max_batch_tokens: int = 65536

    # Cost optimization (overnight preferred)
    priority: Literal["cost", "speed", "balanced"] = "cost"
    use_spot: bool = True  # Spot instances for cost savings

    def get_gpu_config(self, prefer_speed: bool = False) -> dict:
        """Get optimal GPU configuration."""
        gpu_type = self.premium_gpu if prefer_speed else self.recommended_gpu

        # Spot pricing (approximate, varies by region)
        spot_rates = {
            "A100_80GB": 1.89,  # ~$1.89/hr per GPU on spot
            "H100": 2.99,  # ~$2.99/hr per GPU on spot
        }

        hourly_cost = spot_rates.get(gpu_type, 2.0) * self.min_gpu_count

        return {
            "gpu_type": gpu_type,
            "gpu_count": self.min_gpu_count,
            "tensor_parallel": self.tensor_parallel,
            "estimated_hourly_cost": hourly_cost,
            "nvlink_required": True,
            "spot_instance": self.use_spot,
        }

    def get_volume_config(self) -> dict:
        """Get volume configuration for model storage."""
        return {
            "volume_size_gb": self.recommended_volume_gb,
            "mount_path": "/models",
            "model_path": "/models/deepseek-v3-fp8",
            "persistent": True,  # Keep volume for reuse
        }

    def get_docker_command(self) -> str:
        """Generate SGLang server launch command."""
        return f"""python -m sglang.launch_server \\
    --model-path {self.model_id} \\
    --host 0.0.0.0 \\
    --port {self.port} \\
    --tp {self.tensor_parallel} \\
    --dtype fp8 \\
    --max-model-len {self.max_model_len} \\
    --max-total-tokens {self.max_batch_tokens} \\
    --trust-remote-code \\
    --disable-flashinfer-sampling \\
    --download-dir /models"""

    def get_runpod_template(self) -> dict:
        """Get RunPod pod template configuration."""
        gpu_config = self.get_gpu_config()
        volume_config = self.get_volume_config()

        return {
            "name": "deepseek-v3-fp8-inference",
            "image": self.docker_image,
            "gpu_type": gpu_config["gpu_type"],
            "gpu_count": gpu_config["gpu_count"],
            "volume_size_gb": volume_config["volume_size_gb"],
            "volume_mount_path": volume_config["mount_path"],
            "ports": f"{self.port}/http",
            "env": {
                "MODEL_ID": self.model_id,
                "TP_SIZE": str(self.tensor_parallel),
                "DTYPE": "fp8",
                "MAX_MODEL_LEN": str(self.max_model_len),
                "HF_HOME": "/models",
                "TRANSFORMERS_CACHE": "/models",
            },
            "docker_command": self.get_docker_command(),
            "spot_instance": self.use_spot,
        }

    def estimate_cost(self, hours: float, prefer_speed: bool = False) -> dict:
        """Estimate deployment cost."""
        gpu_config = self.get_gpu_config(prefer_speed)
        hourly = gpu_config["estimated_hourly_cost"]

        return {
            "gpu_type": gpu_config["gpu_type"],
            "gpu_count": gpu_config["gpu_count"],
            "hours": hours,
            "hourly_cost": hourly,
            "total_cost": hourly * hours,
            "is_spot": self.use_spot,
            "note": "Spot pricing varies; actual cost may differ",
        }

    def estimate_throughput(self) -> dict:
        """Estimate inference throughput."""
        # Based on benchmarks from Deepseek team
        return {
            "tokens_per_second": 150,  # Approximate for 8x A100
            "tokens_per_second_h100": 250,  # Approximate for 8x H100
            "requests_per_hour_1k_tokens": 540,  # ~9 req/min at 1K tokens
            "note": "Actual throughput depends on input/output length distribution",
        }

    def get_overnight_config(self, target_tokens: int = DEFAULT_TARGET_TOKENS) -> dict:
        """Get configuration optimized for overnight batch processing."""
        throughput = self.estimate_throughput()
        tps = throughput["tokens_per_second"]

        # Calculate time needed
        hours_needed = target_tokens / (tps * 3600)

        # Add buffer for startup, model download, etc.
        total_hours = hours_needed * 1.2 + 1  # 20% buffer + 1hr setup

        cost = self.estimate_cost(total_hours, prefer_speed=False)

        return {
            "target_tokens": target_tokens,
            "estimated_hours": round(total_hours, 1),
            "estimated_cost": round(cost["total_cost"], 2),
            "recommendation": "overnight" if total_hours > 6 else "daytime",
            "gpu_type": cost["gpu_type"],
            "gpu_count": cost["gpu_count"],
            "model_download_time_min": 45,  # First-time download ~45 min
            "is_spot": self.use_spot,
        }


# Pre-configured instances
DEEPSEEK_V3_FP8 = DeepseekV3Config()

# Cost-optimized overnight configuration
DEEPSEEK_V3_OVERNIGHT = DeepseekV3Config(
    priority="cost",
    use_spot=True,
)

# Speed-optimized configuration (uses H100)
DEEPSEEK_V3_FAST = DeepseekV3Config(
    recommended_gpu="H100",
    priority="speed",
    use_spot=True,
)


def print_deployment_plan(target_tokens: int = DEFAULT_TARGET_TOKENS):
    """Print deployment plan for specified token count."""
    config = DEEPSEEK_V3_OVERNIGHT
    plan = config.get_overnight_config(target_tokens)
    template = config.get_runpod_template()

    print("=" * 60)
    print("DEEPSEEK V3 FP8 DEPLOYMENT PLAN")
    print("=" * 60)
    print()
    print(f"Target: {target_tokens:,} tokens")
    print(f"Model: {config.model_id} ({config.model_size_params} MoE, {config.active_params} active)")
    print()
    print("GPU Configuration:")
    print(f"  Type: {template['gpu_type']}")
    print(f"  Count: {template['gpu_count']}x")
    print(f"  Tensor Parallel: TP={config.tensor_parallel}")
    print(f"  NVLink: Required")
    print()
    print("Storage:")
    print(f"  Volume: {template['volume_size_gb']} GB")
    print(f"  Model Size: ~{config.model_size_fp8_gb} GB (FP8)")
    print()
    print("Time Estimates:")
    print(f"  Model Download: ~{plan['model_download_time_min']} min (first time)")
    print(f"  Processing: ~{plan['estimated_hours']:.1f} hours")
    print(f"  Recommendation: {plan['recommendation'].upper()}")
    print()
    print("Cost Estimates (spot pricing):")
    print(f"  Hourly: ~${plan['estimated_cost'] / plan['estimated_hours']:.2f}/hr")
    print(f"  Total: ~${plan['estimated_cost']:.2f}")
    print()
    print("Docker:")
    print(f"  Image: {template['image']}")
    print(f"  Port: {config.port}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    import sys

    tokens = DEFAULT_TARGET_TOKENS  # Default: 90M tokens for 90K QRAs
    if len(sys.argv) > 1:
        tokens = int(sys.argv[1])

    print_deployment_plan(tokens)
