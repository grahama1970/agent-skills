"""
Module: instance_optimizer.py
Description: Optimize RunPod instance selection for cost and performance

External Dependencies:
- pydantic: https://docs.pydantic.dev/
- loguru: https://loguru.readthedocs.io/

Sample Input:
>>> optimizer = InstanceOptimizer()
>>> config = optimizer.get_optimal_config("70B", tokens=1000000, priority="cost")

Expected Output:
>>> config
{"gpu_type": "A100_80GB", "gpu_count": 1, "estimated_cost": 12.36, "estimated_hours": 4.0}

Example Usage:
>>> from runpod_ops.instance_optimizer import InstanceOptimizer
>>> optimizer = InstanceOptimizer()
>>> config = optimizer.optimize_for_inference("13B", requests_per_hour=1000)
"""

from typing import Dict, Any, List, Literal, Optional, Tuple
from dataclasses import dataclass
from loguru import logger
import math


@dataclass
class GPUConfig:
    """GPU configuration with performance characteristics."""
    name: str
    vram_gb: int
    cost_per_hour: float
    fp16_tflops: float
    memory_bandwidth_gb: float
    nvlink: bool = False
    max_model_size_gb: int = 0  # Will be calculated
    tokens_per_second_7b: int = 0  # Benchmark for 7B model
    

class InstanceOptimizer:
    """Optimize RunPod instance selection."""
    
    def __init__(self):
        """Initialize with GPU configurations."""
        self.gpu_configs = self._initialize_gpu_configs()
        self._calculate_model_capacities()
        
    def get_optimal_config(
        self,
        model_size: str,
        tokens: int,
        priority: Literal["cost", "speed", "balanced"] = "balanced",
        max_budget: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get optimal GPU configuration for workload.
        
        Args:
            model_size: Model size (e.g., "7B", "70B")
            tokens: Total tokens to process
            priority: Optimization priority
            max_budget: Maximum budget in USD
            
        Returns:
            Optimal configuration with cost/time estimates
        """
        model_gb = self._get_model_memory_requirement(model_size)
        
        # Filter GPUs that can handle the model
        capable_gpus = [
            gpu for gpu in self.gpu_configs.values()
            if gpu.max_model_size_gb >= model_gb
        ]
        
        if not capable_gpus:
            # Need multi-GPU setup
            return self._get_multi_gpu_config(model_size, tokens, priority, max_budget)
            
        # Calculate scores for each GPU
        configs = []
        for gpu in capable_gpus:
            throughput = self._estimate_throughput(gpu, model_size)
            hours = tokens / (throughput * 3600)
            cost = hours * gpu.cost_per_hour
            
            # Skip if over budget
            if max_budget and cost > max_budget:
                continue
                
            # Calculate priority score
            if priority == "cost":
                score = 1 / cost
            elif priority == "speed":
                score = throughput
            else:  # balanced
                score = throughput / cost
                
            configs.append({
                "gpu_type": gpu.name,
                "gpu_count": 1,
                "estimated_hours": round(hours, 2),
                "estimated_cost": round(cost, 2),
                "tokens_per_second": throughput,
                "score": score,
                "vram_usage_gb": model_gb,
                "vram_available_gb": gpu.vram_gb
            })
            
        # Sort by score
        configs.sort(key=lambda x: x["score"], reverse=True)
        
        if not configs:
            return {
                "error": "No configuration within budget",
                "min_budget_required": min(
                    self._calculate_cost(gpu, model_size, tokens)
                    for gpu in self.gpu_configs.values()
                )
            }
            
        # Return best configuration
        best = configs[0]
        del best["score"]  # Remove internal scoring
        
        logger.info(f"Optimal config for {model_size} ({tokens:,} tokens): {best['gpu_type']}")
        return best
        
    def optimize_for_training(
        self,
        model_size: str,
        dataset_size: int,
        epochs: int = 1,
        batch_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Optimize configuration for training.
        
        Args:
            model_size: Model size to train
            dataset_size: Number of training examples
            epochs: Training epochs
            batch_size: Batch size (auto-determined if None)
            
        Returns:
            Optimal training configuration
        """
        # Training requires more VRAM for gradients and optimizer states
        model_gb = self._get_model_memory_requirement(model_size)
        training_gb = model_gb * 3.5  # Rule of thumb for training memory
        
        # Consider gradient accumulation for large models
        capable_configs = []
        
        for gpu in self.gpu_configs.values():
            if gpu.vram_gb >= training_gb:
                # Can fit without gradient accumulation
                effective_batch = batch_size or self._get_optimal_batch_size(gpu, model_size)
                grad_accum_steps = 1
            elif gpu.vram_gb >= model_gb * 2:
                # Need gradient accumulation
                effective_batch = batch_size or max(1, gpu.vram_gb // (model_gb * 2))
                target_batch = self._get_optimal_batch_size(gpu, model_size)
                grad_accum_steps = max(1, target_batch // effective_batch)
            else:
                continue  # GPU too small
                
            # Estimate training time
            throughput = self._estimate_training_throughput(
                gpu, model_size, effective_batch, grad_accum_steps
            )
            
            total_steps = (dataset_size * epochs) // (effective_batch * grad_accum_steps)
            hours = total_steps / (throughput * 3600)
            cost = hours * gpu.cost_per_hour
            
            capable_configs.append({
                "gpu_type": gpu.name,
                "gpu_count": 1,
                "batch_size": effective_batch,
                "gradient_accumulation_steps": grad_accum_steps,
                "effective_batch_size": effective_batch * grad_accum_steps,
                "estimated_hours": round(hours, 2),
                "estimated_cost": round(cost, 2),
                "steps_per_second": throughput,
                "total_steps": total_steps,
                "vram_usage_gb": training_gb if grad_accum_steps == 1 else model_gb * 2
            })
            
        if not capable_configs:
            # Need multi-GPU
            return self._get_multi_gpu_training_config(
                model_size, dataset_size, epochs, batch_size
            )
            
        # Sort by cost-effectiveness
        capable_configs.sort(key=lambda x: x["estimated_cost"])
        
        best = capable_configs[0]
        logger.info(f"Optimal training config for {model_size}: {best['gpu_type']}")
        
        return best
        
    def optimize_for_inference(
        self,
        model_size: str,
        requests_per_hour: int,
        avg_input_tokens: int = 512,
        avg_output_tokens: int = 128,
        target_latency_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Optimize configuration for inference serving.
        
        Args:
            model_size: Model size to serve
            requests_per_hour: Expected request rate
            avg_input_tokens: Average input length
            avg_output_tokens: Average output length
            target_latency_ms: Target latency in milliseconds
            
        Returns:
            Optimal inference configuration
        """
        model_gb = self._get_model_memory_requirement(model_size)
        
        # For inference, we need to consider batching
        total_tokens_per_hour = requests_per_hour * (avg_input_tokens + avg_output_tokens)
        
        configs = []
        for gpu in self.gpu_configs.values():
            if gpu.vram_gb < model_gb * 1.2:  # Need 20% headroom for KV cache
                continue
                
            # Calculate max batch size for KV cache
            kv_cache_gb_per_token = 0.0001 * int(model_size.rstrip("B"))  # Rough estimate
            max_concurrent = int((gpu.vram_gb - model_gb * 1.2) / 
                               (kv_cache_gb_per_token * avg_output_tokens))
            max_concurrent = max(1, min(max_concurrent, 32))  # Practical limits
            
            # Estimate throughput with batching
            base_throughput = self._estimate_throughput(gpu, model_size)
            batch_efficiency = min(1.0, math.log2(max_concurrent + 1) / 3)  # Diminishing returns
            effective_throughput = base_throughput * (1 + batch_efficiency)
            
            # Check if meets latency requirements
            if target_latency_ms:
                latency = (avg_output_tokens / effective_throughput) * 1000
                if latency > target_latency_ms:
                    continue
                    
            # Calculate utilization and cost
            required_throughput = total_tokens_per_hour / 3600
            utilization = required_throughput / effective_throughput
            
            if utilization > 0.9:  # Need multiple instances
                instance_count = math.ceil(utilization / 0.8)  # Target 80% utilization
                cost_per_hour = gpu.cost_per_hour * instance_count
            else:
                instance_count = 1
                cost_per_hour = gpu.cost_per_hour
                
            configs.append({
                "gpu_type": gpu.name,
                "instance_count": instance_count,
                "max_batch_size": max_concurrent,
                "cost_per_hour": round(cost_per_hour, 2),
                "cost_per_1k_requests": round(cost_per_hour * 1000 / requests_per_hour, 3),
                "throughput_tokens_per_second": round(effective_throughput, 0),
                "utilization": round(utilization * 100, 1),
                "avg_latency_ms": round((avg_output_tokens / effective_throughput) * 1000, 0)
            })
            
        if not configs:
            return {"error": "No GPU can meet requirements"}
            
        # Sort by cost per request
        configs.sort(key=lambda x: x["cost_per_1k_requests"])
        
        return configs[0]
        
    def _initialize_gpu_configs(self) -> Dict[str, GPUConfig]:
        """Initialize GPU configuration database."""
        configs = {
            "RTX_4090": GPUConfig(
                name="RTX_4090",
                vram_gb=24,
                cost_per_hour=0.69,
                fp16_tflops=83,
                memory_bandwidth_gb=1008,
                tokens_per_second_7b=1500
            ),
            "RTX_A6000": GPUConfig(
                name="RTX_A6000",
                vram_gb=48,
                cost_per_hour=0.79,
                fp16_tflops=77,
                memory_bandwidth_gb=768,
                tokens_per_second_7b=1400
            ),
            "A40": GPUConfig(
                name="A40",
                vram_gb=48,
                cost_per_hour=0.59,
                fp16_tflops=75,
                memory_bandwidth_gb=696,
                tokens_per_second_7b=1300
            ),
            "A100_40GB": GPUConfig(
                name="A100_40GB",
                vram_gb=40,
                cost_per_hour=1.64,
                fp16_tflops=156,
                memory_bandwidth_gb=1555,
                nvlink=True,
                tokens_per_second_7b=2800
            ),
            "A100_80GB": GPUConfig(
                name="A100_80GB",
                vram_gb=80,
                cost_per_hour=3.09,
                fp16_tflops=156,
                memory_bandwidth_gb=2039,
                nvlink=True,
                tokens_per_second_7b=2800
            ),
            "H100": GPUConfig(
                name="H100",
                vram_gb=80,
                cost_per_hour=4.89,
                fp16_tflops=378,
                memory_bandwidth_gb=3350,
                nvlink=True,
                tokens_per_second_7b=5000
            ),
        }
        
        return configs
        
    def _calculate_model_capacities(self):
        """Calculate maximum model sizes for each GPU."""
        for gpu in self.gpu_configs.values():
            # Conservative estimate: 70% of VRAM for model, rest for activations
            gpu.max_model_size_gb = int(gpu.vram_gb * 0.7)
            
    def _get_model_memory_requirement(self, model_size: str) -> int:
        """Get memory requirement for model size."""
        # FP16 weights + some overhead
        size_map = {
            "3B": 6,
            "7B": 14,
            "13B": 26,
            "30B": 60,
            "70B": 140,
            "180B": 360,
        }
        
        # Find closest match
        size_num = int(model_size.rstrip("B"))
        for size_str, mem_gb in size_map.items():
            if abs(int(size_str.rstrip("B")) - size_num) < 2:
                return mem_gb
                
        # Fallback: 2GB per billion parameters
        return size_num * 2
        
    def _estimate_throughput(self, gpu: GPUConfig, model_size: str) -> int:
        """Estimate tokens/second for model on GPU."""
        # Scale from 7B baseline
        size_num = int(model_size.rstrip("B"))
        scale_factor = 7 / size_num
        
        # Adjust for memory bandwidth limitations
        if size_num > 30:
            scale_factor *= 0.8  # Large models are more memory bound
            
        return int(gpu.tokens_per_second_7b * scale_factor)
        
    def _estimate_training_throughput(
        self,
        gpu: GPUConfig,
        model_size: str,
        batch_size: int,
        grad_accum: int
    ) -> float:
        """Estimate training steps/second."""
        # Training is roughly 3x slower than inference
        inference_throughput = self._estimate_throughput(gpu, model_size)
        
        # Adjust for batch size efficiency
        batch_efficiency = min(1.0, math.log2(batch_size + 1) / 4)
        
        # Gradient accumulation overhead
        grad_overhead = 1.0 if grad_accum == 1 else 0.9
        
        tokens_per_step = batch_size * 512  # Assume 512 token sequences
        steps_per_second = (inference_throughput / tokens_per_step) / 3 * batch_efficiency * grad_overhead
        
        return steps_per_second
        
    def _get_optimal_batch_size(self, gpu: GPUConfig, model_size: str) -> int:
        """Get optimal batch size for GPU and model."""
        model_gb = self._get_model_memory_requirement(model_size)
        
        # Available memory for batching (after model and optimizer)
        available_gb = gpu.vram_gb - (model_gb * 3)
        
        # Rough estimate: 0.5GB per batch for 7B model
        gb_per_batch = 0.5 * (int(model_size.rstrip("B")) / 7)
        
        optimal_batch = max(1, int(available_gb / gb_per_batch))
        
        # Practical limits
        return min(optimal_batch, 16)
        
    def _calculate_cost(self, gpu: GPUConfig, model_size: str, tokens: int) -> float:
        """Calculate cost for processing tokens."""
        throughput = self._estimate_throughput(gpu, model_size)
        hours = tokens / (throughput * 3600)
        return hours * gpu.cost_per_hour
        
    def _get_multi_gpu_config(
        self,
        model_size: str,
        tokens: int,
        priority: str,
        max_budget: Optional[float]
    ) -> Dict[str, Any]:
        """Get multi-GPU configuration for large models."""
        model_gb = self._get_model_memory_requirement(model_size)
        
        # Find GPU combinations
        configs = []
        
        for gpu in self.gpu_configs.values():
            # Calculate how many GPUs needed
            gpus_needed = math.ceil(model_gb / (gpu.vram_gb * 0.7))
            
            if gpus_needed > 8:  # Practical limit
                continue
                
            # Estimate multi-GPU efficiency
            if gpu.nvlink:
                efficiency = 0.85 if gpus_needed <= 4 else 0.75
            else:
                efficiency = 0.65 if gpus_needed <= 4 else 0.55
                
            # Calculate performance
            throughput = self._estimate_throughput(gpu, model_size) * gpus_needed * efficiency
            hours = tokens / (throughput * 3600)
            cost = hours * gpu.cost_per_hour * gpus_needed
            
            if max_budget and cost > max_budget:
                continue
                
            configs.append({
                "gpu_type": gpu.name,
                "gpu_count": gpus_needed,
                "estimated_hours": round(hours, 2),
                "estimated_cost": round(cost, 2),
                "tokens_per_second": round(throughput, 0),
                "multi_gpu_efficiency": round(efficiency * 100, 1),
                "interconnect": "NVLink" if gpu.nvlink else "PCIe"
            })
            
        if not configs:
            return {"error": "Model too large for available GPUs"}
            
        # Sort by priority
        if priority == "cost":
            configs.sort(key=lambda x: x["estimated_cost"])
        elif priority == "speed":
            configs.sort(key=lambda x: x["tokens_per_second"], reverse=True)
        else:
            configs.sort(key=lambda x: x["tokens_per_second"] / x["estimated_cost"], reverse=True)
            
        return configs[0]
        
    def _get_multi_gpu_training_config(
        self,
        model_size: str,
        dataset_size: int,
        epochs: int,
        batch_size: Optional[int]
    ) -> Dict[str, Any]:
        """Get multi-GPU training configuration."""
        model_gb = self._get_model_memory_requirement(model_size)
        training_gb = model_gb * 3.5
        
        configs = []
        
        for gpu in self.gpu_configs.values():
            # Calculate GPUs needed for training
            gpus_needed = math.ceil(training_gb / (gpu.vram_gb * 0.8))
            
            if gpus_needed > 8:
                continue
                
            # Can use model parallelism or data parallelism
            if gpus_needed * gpu.vram_gb >= training_gb * 1.5:
                # Data parallelism possible
                strategy = "data_parallel"
                effective_batch = (batch_size or self._get_optimal_batch_size(gpu, model_size)) * gpus_needed
                efficiency = 0.9 if gpu.nvlink else 0.75
            else:
                # Need model parallelism
                strategy = "model_parallel"
                effective_batch = batch_size or max(1, gpu.vram_gb // (model_gb * 2))
                efficiency = 0.7 if gpu.nvlink else 0.5
                
            # Calculate training time
            throughput = self._estimate_training_throughput(
                gpu, model_size, effective_batch // gpus_needed, 1
            ) * gpus_needed * efficiency
            
            total_steps = (dataset_size * epochs) // effective_batch
            hours = total_steps / (throughput * 3600)
            cost = hours * gpu.cost_per_hour * gpus_needed
            
            configs.append({
                "gpu_type": gpu.name,
                "gpu_count": gpus_needed,
                "strategy": strategy,
                "batch_size_per_gpu": effective_batch // gpus_needed,
                "global_batch_size": effective_batch,
                "estimated_hours": round(hours, 2),
                "estimated_cost": round(cost, 2),
                "steps_per_second": round(throughput, 2),
                "total_steps": total_steps,
                "multi_gpu_efficiency": round(efficiency * 100, 1),
                "interconnect": "NVLink" if gpu.nvlink else "PCIe"
            })
            
        if not configs:
            return {"error": "Model too large for training on available GPUs"}
            
        # Sort by cost
        configs.sort(key=lambda x: x["estimated_cost"])
        
        return configs[0]


# Validation
if __name__ == "__main__":
    optimizer = InstanceOptimizer()
    
    print("GPU Instance Optimization Examples")
    print("=" * 60)
    
    # Test inference optimization
    print("\n1. Inference Optimization (13B model, 1000 req/hour):")
    inference_config = optimizer.optimize_for_inference(
        "13B", 
        requests_per_hour=1000,
        target_latency_ms=500
    )
    for k, v in inference_config.items():
        print(f"  {k}: {v}")
        
    # Test training optimization
    print("\n2. Training Optimization (7B model, 50k examples):")
    training_config = optimizer.optimize_for_training("7B", 50000, epochs=3)
    for k, v in training_config.items():
        print(f"  {k}: {v}")
        
    # Test cost vs speed optimization
    print("\n3. Cost vs Speed Comparison (70B model):")
    for priority in ["cost", "speed", "balanced"]:
        config = optimizer.get_optimal_config("70B", tokens=1000000, priority=priority)
        print(f"\n  Priority: {priority}")
        print(f"  GPU: {config.get('gpu_count', 1)}x {config.get('gpu_type', 'N/A')}")
        print(f"  Cost: ${config.get('estimated_cost', 0):.2f}")
        print(f"  Time: {config.get('estimated_hours', 0):.1f} hours")
        
    print("\n✅ Module validation passed")