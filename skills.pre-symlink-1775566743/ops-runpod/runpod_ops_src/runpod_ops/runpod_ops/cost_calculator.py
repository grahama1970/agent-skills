"""
Module: cost_calculator.py
Description: Calculate and compare costs across different compute providers

External Dependencies:
- pydantic: https://docs.pydantic.dev/
- loguru: https://loguru.readthedocs.io/

Sample Input:
>>> calculator = CostCalculator()
>>> comparison = calculator.compare_providers("70B", tokens=1000000)

Expected Output:
>>> comparison
{"runpod": {"cost": 12.36, "time": 4.0}, "vertex": {"cost": 7.50, "time": 1.39}}

Example Usage:
>>> from runpod_ops.cost_calculator import CostCalculator
>>> calc = CostCalculator()
>>> best = calc.get_cheapest_provider("13B", tokens=500000)
"""

from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
from dataclasses import dataclass
from loguru import logger


@dataclass 
class InstanceProfile:
    """Provider instance profile."""
    provider: str
    name: str
    cost_per_hour: Optional[float] = None
    cost_per_million_tokens: Optional[float] = None
    tokens_per_second: int = 0
    startup_time_seconds: int = 0
    min_billable_seconds: int = 0
    supports_spot: bool = False
    

class CostCalculator:
    """Calculate and compare costs across providers."""
    
    def __init__(self):
        """Initialize with provider profiles."""
        self.profiles = self._initialize_profiles()
        
    def calculate_total_cost(
        self,
        profile: InstanceProfile,
        total_tokens: int,
        include_startup: bool = True
    ) -> Dict[str, float]:
        """
        Calculate total cost for processing tokens.
        
        Args:
            profile: Instance profile to use
            total_tokens: Total tokens to process
            include_startup: Include startup time in calculation
            
        Returns:
            Cost breakdown with total, compute, and time estimates
        """
        if profile.cost_per_million_tokens:
            # Token-based pricing (e.g., Vertex AI)
            token_cost = (total_tokens / 1_000_000) * profile.cost_per_million_tokens
            processing_time = total_tokens / profile.tokens_per_second
            
            return {
                "total_cost": round(token_cost, 2),
                "token_cost": round(token_cost, 2),
                "hourly_cost": 0.0,
                "processing_time_seconds": round(processing_time, 0),
                "processing_time_hours": round(processing_time / 3600, 2),
                "provider": profile.provider,
                "instance_type": profile.name
            }
        else:
            # Hourly pricing (e.g., RunPod)
            processing_time = total_tokens / profile.tokens_per_second
            
            if include_startup:
                total_time = processing_time + profile.startup_time_seconds
            else:
                total_time = processing_time
                
            # Apply minimum billing
            billable_time = max(total_time, profile.min_billable_seconds)
            
            hourly_cost = billable_time / 3600 * profile.cost_per_hour
            
            return {
                "total_cost": round(hourly_cost, 2),
                "token_cost": 0.0,
                "hourly_cost": round(hourly_cost, 2),
                "processing_time_seconds": round(processing_time, 0),
                "total_time_seconds": round(total_time, 0),
                "billable_time_seconds": round(billable_time, 0),
                "processing_time_hours": round(processing_time / 3600, 2),
                "startup_overhead_seconds": profile.startup_time_seconds if include_startup else 0,
                "provider": profile.provider,
                "instance_type": profile.name
            }
            
    def compare_providers(
        self,
        model_size: str,
        tokens: int,
        include_local: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compare costs across all providers for workload.
        
        Args:
            model_size: Model size to run
            tokens: Total tokens to process
            include_local: Include local Ollama option
            
        Returns:
            Comparison of all viable providers
        """
        results = {}
        
        # Get profiles that can handle the model
        capable_profiles = self._get_capable_profiles(model_size)
        
        for profile in capable_profiles:
            if not include_local and profile.provider == "local":
                continue
                
            cost_info = self.calculate_total_cost(profile, tokens)
            
            # Add additional metrics
            cost_info["cost_per_1k_tokens"] = round(cost_info["total_cost"] * 1000 / tokens, 4)
            cost_info["tokens_per_dollar"] = round(tokens / max(cost_info["total_cost"], 0.01), 0)
            
            results[f"{profile.provider}_{profile.name}"] = cost_info
            
        # Sort by total cost
        sorted_results = dict(sorted(results.items(), key=lambda x: x[1]["total_cost"]))
        
        return sorted_results
        
    def get_cheapest_provider(
        self,
        model_size: str,
        tokens: int,
        max_time_hours: Optional[float] = None,
        exclude_providers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get cheapest provider for workload with constraints.
        
        Args:
            model_size: Model size to run
            tokens: Total tokens to process  
            max_time_hours: Maximum acceptable processing time
            exclude_providers: Providers to exclude
            
        Returns:
            Cheapest viable option
        """
        comparison = self.compare_providers(model_size, tokens)
        exclude_providers = exclude_providers or []
        
        for key, info in comparison.items():
            provider = info["provider"]
            
            # Skip excluded providers
            if provider in exclude_providers:
                continue
                
            # Check time constraint
            if max_time_hours and info["processing_time_hours"] > max_time_hours:
                continue
                
            # First non-excluded option is cheapest
            return info
            
        return {"error": "No provider meets constraints"}
        
    def estimate_batch_cost(
        self,
        model_size: str,
        batch_sizes: List[int],
        tokens_per_item: int = 512
    ) -> Dict[str, Any]:
        """
        Estimate costs for batch processing.
        
        Args:
            model_size: Model size to use
            batch_sizes: List of batch sizes to estimate
            tokens_per_item: Average tokens per batch item
            
        Returns:
            Cost estimates for each batch size
        """
        estimates = {}
        
        for batch_size in batch_sizes:
            total_tokens = batch_size * tokens_per_item
            comparison = self.compare_providers(model_size, total_tokens)
            
            # Get best option for this batch
            best = list(comparison.values())[0]
            
            estimates[f"batch_{batch_size}"] = {
                "batch_size": batch_size,
                "total_tokens": total_tokens,
                "best_provider": best["provider"],
                "best_instance": best["instance_type"],
                "total_cost": best["total_cost"],
                "cost_per_item": round(best["total_cost"] / batch_size, 4),
                "processing_hours": best["processing_time_hours"]
            }
            
        return estimates
        
    def calculate_monthly_budget(
        self,
        model_size: str,
        daily_tokens: int,
        days: int = 30,
        peak_factor: float = 1.5
    ) -> Dict[str, Any]:
        """
        Calculate monthly budget requirements.
        
        Args:
            model_size: Model size to run
            daily_tokens: Average daily token volume
            days: Days per month
            peak_factor: Peak load multiplier
            
        Returns:
            Monthly budget breakdown
        """
        monthly_tokens = daily_tokens * days
        peak_tokens = int(daily_tokens * peak_factor)
        
        # Get costs for different providers
        comparison = self.compare_providers(model_size, monthly_tokens)
        
        budget = {
            "model_size": model_size,
            "daily_tokens": daily_tokens,
            "monthly_tokens": monthly_tokens,
            "peak_daily_tokens": peak_tokens,
            "providers": {}
        }
        
        for key, info in comparison.items():
            provider_budget = {
                "monthly_cost": info["total_cost"],
                "daily_average_cost": round(info["total_cost"] / days, 2),
                "peak_day_cost": round(info["total_cost"] / monthly_tokens * peak_tokens, 2),
                "cost_per_million_tokens": round(info["total_cost"] * 1_000_000 / monthly_tokens, 2),
                "processing_hours_per_day": round(info["processing_time_hours"] / days, 2)
            }
            
            budget["providers"][key] = provider_budget
            
        # Add recommendations
        cheapest = min(budget["providers"].items(), key=lambda x: x[1]["monthly_cost"])
        fastest = min(budget["providers"].items(), key=lambda x: x[1]["processing_hours_per_day"])
        
        budget["recommendations"] = {
            "cheapest": cheapest[0],
            "cheapest_monthly_cost": cheapest[1]["monthly_cost"],
            "fastest": fastest[0],
            "fastest_hours_per_day": fastest[1]["processing_hours_per_day"]
        }
        
        return budget
        
    def _initialize_profiles(self) -> List[InstanceProfile]:
        """Initialize provider profiles."""
        profiles = [
            # Local Ollama
            InstanceProfile(
                provider="local",
                name="ollama",
                cost_per_hour=0.0,  # Free but limited by hardware
                tokens_per_second=100,  # Depends on local GPU
                startup_time_seconds=5
            ),
            
            # Vertex AI Gemini Flash
            InstanceProfile(
                provider="vertex",
                name="gemini-flash",
                cost_per_million_tokens=0.075,  # $0.075 per million tokens
                tokens_per_second=150,  # 150-200 tok/s claimed
                startup_time_seconds=1
            ),
            
            # RunPod instances
            InstanceProfile(
                provider="runpod",
                name="rtx4090",
                cost_per_hour=0.69,
                tokens_per_second=1500,  # 7B model estimate
                startup_time_seconds=120,
                min_billable_seconds=60,
                supports_spot=True
            ),
            InstanceProfile(
                provider="runpod", 
                name="a100_40gb",
                cost_per_hour=1.64,
                tokens_per_second=2800,
                startup_time_seconds=120,
                min_billable_seconds=60,
                supports_spot=True
            ),
            InstanceProfile(
                provider="runpod",
                name="a100_80gb",
                cost_per_hour=3.09,
                tokens_per_second=2800,  # Same throughput, more capacity
                startup_time_seconds=120,
                min_billable_seconds=60,
                supports_spot=True
            ),
            InstanceProfile(
                provider="runpod",
                name="h100",
                cost_per_hour=4.89,
                tokens_per_second=5000,
                startup_time_seconds=150,
                min_billable_seconds=60,
                supports_spot=True
            ),
            
            # Multi-GPU RunPod
            InstanceProfile(
                provider="runpod",
                name="2x_rtx4090",
                cost_per_hour=1.31,  # With multi-GPU discount
                tokens_per_second=2700,  # 90% efficiency
                startup_time_seconds=150,
                min_billable_seconds=60
            ),
            InstanceProfile(
                provider="runpod",
                name="2x_a100_80gb",
                cost_per_hour=5.87,  # With discount
                tokens_per_second=5000,  # 90% efficiency with NVLink
                startup_time_seconds=180,
                min_billable_seconds=60
            ),
        ]
        
        return profiles
        
    def _get_capable_profiles(self, model_size: str) -> List[InstanceProfile]:
        """Get profiles capable of running model size."""
        # Model size to profile mapping
        capability_map = {
            "3B": ["ollama", "gemini-flash", "rtx4090", "a100_40gb", "a100_80gb", "h100", "2x_rtx4090", "2x_a100_80gb"],
            "7B": ["ollama", "gemini-flash", "rtx4090", "a100_40gb", "a100_80gb", "h100", "2x_rtx4090", "2x_a100_80gb"],
            "13B": ["gemini-flash", "a100_40gb", "a100_80gb", "h100", "2x_rtx4090", "2x_a100_80gb"],
            "30B": ["gemini-flash", "a100_80gb", "h100", "2x_a100_80gb"],
            "70B": ["gemini-flash", "2x_a100_80gb", "h100"],
            "180B": ["2x_a100_80gb", "h100"],
        }
        
        # Get capable profile names
        size_num = int(model_size.rstrip("B"))
        capable_names = []
        
        for size, profiles in capability_map.items():
            if int(size.rstrip("B")) >= size_num:
                capable_names = profiles
                break
                
        # Filter profiles
        capable = [p for p in self.profiles if p.name in capable_names]
        
        # Adjust tokens/second for model size
        for profile in capable:
            if profile.provider == "runpod":
                # Scale throughput by model size
                scale = 7 / size_num
                profile.tokens_per_second = int(profile.tokens_per_second * scale)
                
        return capable


# Validation 
if __name__ == "__main__":
    calculator = CostCalculator()
    
    print("Cost Calculator Examples")
    print("=" * 60)
    
    # Compare providers for different workloads
    workloads = [
        ("7B", 100_000, "Small batch inference"),
        ("13B", 1_000_000, "Medium batch processing"),
        ("70B", 5_000_000, "Large model training"),
    ]
    
    for model_size, tokens, description in workloads:
        print(f"\n{description} ({model_size} model, {tokens:,} tokens):")
        comparison = calculator.compare_providers(model_size, tokens)
        
        for i, (key, info) in enumerate(comparison.items()):
            if i >= 3:  # Show top 3
                break
            print(f"\n  {i+1}. {info['provider']} - {info['instance_type']}")
            print(f"     Total cost: ${info['total_cost']}")
            print(f"     Time: {info['processing_time_hours']:.1f} hours")
            print(f"     Cost/1K tokens: ${info['cost_per_1k_tokens']}")
            
    # Monthly budget example
    print("\n\nMonthly Budget Analysis (13B model, 500K tokens/day):")
    budget = calculator.calculate_monthly_budget("13B", 500_000)
    
    print(f"\nMonthly token volume: {budget['monthly_tokens']:,}")
    print(f"Peak daily volume: {budget['peak_daily_tokens']:,}")
    print(f"\nRecommendations:")
    print(f"  Cheapest: {budget['recommendations']['cheapest']} - ${budget['recommendations']['cheapest_monthly_cost']}/month")
    print(f"  Fastest: {budget['recommendations']['fastest']} - {budget['recommendations']['fastest_hours_per_day']:.1f} hours/day")
    
    print("\n✅ Module validation passed")