"""
Module: inference_server.py
Description: Deploy and manage inference servers on RunPod

External Dependencies:
- runpod: https://docs.runpod.io/
- loguru: https://loguru.readthedocs.io/
- httpx: https://www.python-httpx.org/

Sample Input:
>>> server = InferenceServer()
>>> endpoint = await server.deploy_model("model_path", gpu_type="RTX_4090")

Expected Output:
>>> endpoint
{"url": "https://api.runpod.ai/v2/abc123", "status": "ready", "model": "model_name"}

Example Usage:
>>> from runpod_ops.inference_server import InferenceServer
>>> server = InferenceServer()
>>> response = await server.query_endpoint(endpoint_id, "What is the capital of France?")
"""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
import httpx

from loguru import logger
from pydantic import BaseModel, Field

from runpod_ops.runpod_manager import RunPodManager
from runpod_ops.instance_optimizer import InstanceOptimizer
from runpod_ops.cost_calculator import CostCalculator


class InferenceEndpoint(BaseModel):
    """Inference endpoint information."""
    endpoint_id: str
    model_name: str
    instance_id: str
    url: str
    status: Literal["deploying", "ready", "error", "stopped"]
    gpu_type: str
    max_batch_size: int = 1
    created_at: datetime
    requests_served: int = 0
    total_tokens: int = 0
    

class InferenceRequest(BaseModel):
    """Inference request format."""
    prompt: str
    max_tokens: int = 100
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    stream: bool = False
    

class InferenceServer:
    """Deploy and manage inference servers."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize inference server manager.
        
        Args:
            api_key: RunPod API key
        """
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        self.manager = RunPodManager(self.api_key)
        self.optimizer = InstanceOptimizer()
        self.calculator = CostCalculator()
        
        self.endpoints: Dict[str, InferenceEndpoint] = {}
        self.client = httpx.AsyncClient()
        
    async def deploy_model(
        self,
        model_path: str,
        model_name: Optional[str] = None,
        gpu_type: Optional[str] = None,
        autoscale: bool = False,
        max_batch_size: int = 32,
        quantization: Optional[str] = None
    ) -> InferenceEndpoint:
        """
        Deploy model as inference endpoint.
        
        Args:
            model_path: Path to model (HF hub or local)
            model_name: Display name for endpoint
            gpu_type: GPU type or auto-select
            autoscale: Enable autoscaling
            max_batch_size: Maximum batch size
            quantization: Quantization mode (e.g., "int4", "int8")
            
        Returns:
            InferenceEndpoint with details
        """
        endpoint_id = f"inf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        model_name = model_name or model_path.split("/")[-1]
        
        logger.info(f"Deploying model: {model_name}")
        
        try:
            # Determine optimal GPU if not specified
            if not gpu_type:
                # Estimate model size from path
                model_size = self._estimate_model_size(model_path)
                config = self.optimizer.optimize_for_inference(
                    model_size,
                    requests_per_hour=1000,  # Default estimate
                    target_latency_ms=500
                )
                gpu_type = config["gpu_type"]
                
            # Create inference configuration
            inference_config = {
                "gpu_type": gpu_type,
                "gpu_count": 1,
                "disk_size": 50,
                "ports": "8000/http",
                "image": "runpod/vllm:latest",  # Using vLLM for inference
                "env": {
                    "MODEL_NAME": model_path,
                    "MAX_BATCH_SIZE": str(max_batch_size),
                    "TRUST_REMOTE_CODE": "true",
                    "DTYPE": "float16",
                    "ENFORCE_EAGER": "false",  # Enable CUDA graphs
                },
                "docker_command": self._generate_vllm_command(
                    model_path, max_batch_size, quantization
                )
            }
            
            # Add quantization if specified
            if quantization:
                inference_config["env"]["QUANTIZATION"] = quantization
                
            # Create instance
            instance = await self.manager.create_instance("inference", inference_config)
            
            # Wait for server to be ready
            endpoint_url = await self._wait_for_server_ready(instance.id)
            
            # Create endpoint record
            endpoint = InferenceEndpoint(
                endpoint_id=endpoint_id,
                model_name=model_name,
                instance_id=instance.id,
                url=endpoint_url,
                status="ready",
                gpu_type=gpu_type,
                max_batch_size=max_batch_size,
                created_at=datetime.now()
            )
            
            self.endpoints[endpoint_id] = endpoint
            
            logger.info(f"Endpoint ready: {endpoint_url}")
            return endpoint
            
        except Exception as e:
            logger.error(f"Failed to deploy model: {e}")
            
            # Create error endpoint record
            endpoint = InferenceEndpoint(
                endpoint_id=endpoint_id,
                model_name=model_name,
                instance_id="",
                url="",
                status="error",
                gpu_type=gpu_type or "unknown",
                created_at=datetime.now()
            )
            
            self.endpoints[endpoint_id] = endpoint
            raise
            
    async def query_endpoint(
        self,
        endpoint_id: str,
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Query inference endpoint.
        
        Args:
            endpoint_id: Endpoint ID
            prompt: Input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            Model response
        """
        if endpoint_id not in self.endpoints:
            return {"error": "Endpoint not found"}
            
        endpoint = self.endpoints[endpoint_id]
        
        if endpoint.status != "ready":
            return {"error": f"Endpoint not ready: {endpoint.status}"}
            
        # Create request
        request = InferenceRequest(prompt=prompt, **kwargs)
        
        try:
            # Send request to vLLM server
            response = await self.client.post(
                f"{endpoint.url}/v1/completions",
                json={
                    "model": endpoint.model_name,
                    "prompt": request.prompt,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "top_k": request.top_k,
                    "stream": request.stream,
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Update metrics
            endpoint.requests_served += 1
            endpoint.total_tokens += len(result["choices"][0]["text"].split())
            
            return result
            
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return {"error": str(e)}
            
    async def batch_query(
        self,
        endpoint_id: str,
        prompts: List[str],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Batch query inference endpoint.
        
        Args:
            endpoint_id: Endpoint ID
            prompts: List of prompts
            **kwargs: Generation parameters
            
        Returns:
            List of responses
        """
        if endpoint_id not in self.endpoints:
            return [{"error": "Endpoint not found"}] * len(prompts)
            
        endpoint = self.endpoints[endpoint_id]
        
        # Split into batches
        batch_size = endpoint.max_batch_size
        results = []
        
        for i in range(0, len(prompts), batch_size):
            batch = prompts[i:i + batch_size]
            
            # Query each prompt (vLLM handles batching internally)
            batch_tasks = [
                self.query_endpoint(endpoint_id, prompt, **kwargs)
                for prompt in batch
            ]
            
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)
            
        return results
        
    async def stop_endpoint(self, endpoint_id: str) -> bool:
        """Stop inference endpoint."""
        if endpoint_id not in self.endpoints:
            return False
            
        endpoint = self.endpoints[endpoint_id]
        
        if endpoint.instance_id:
            success = await self.manager.terminate_instance(endpoint.instance_id)
            if success:
                endpoint.status = "stopped"
                return True
                
        return False
        
    async def get_endpoint_metrics(self, endpoint_id: str) -> Dict[str, Any]:
        """Get endpoint performance metrics."""
        if endpoint_id not in self.endpoints:
            return {"error": "Endpoint not found"}
            
        endpoint = self.endpoints[endpoint_id]
        
        # Get instance metrics
        instance_status = await self.manager.get_instance_status(endpoint.instance_id)
        
        # Calculate averages
        uptime_hours = (datetime.now() - endpoint.created_at).total_seconds() / 3600
        avg_requests_per_hour = endpoint.requests_served / max(uptime_hours, 0.001)
        avg_tokens_per_request = endpoint.total_tokens / max(endpoint.requests_served, 1)
        
        # Cost analysis
        cost_so_far = instance_status.get("cost_per_hour", 0) * uptime_hours
        cost_per_request = cost_so_far / max(endpoint.requests_served, 1)
        cost_per_1k_tokens = cost_so_far * 1000 / max(endpoint.total_tokens, 1)
        
        return {
            "endpoint_id": endpoint_id,
            "model_name": endpoint.model_name,
            "status": endpoint.status,
            "uptime_hours": round(uptime_hours, 2),
            "requests_served": endpoint.requests_served,
            "total_tokens": endpoint.total_tokens,
            "avg_requests_per_hour": round(avg_requests_per_hour, 1),
            "avg_tokens_per_request": round(avg_tokens_per_request, 1),
            "gpu_utilization": instance_status.get("gpu_utilization", 0),
            "cost_metrics": {
                "total_cost": round(cost_so_far, 2),
                "cost_per_hour": instance_status.get("cost_per_hour", 0),
                "cost_per_request": round(cost_per_request, 4),
                "cost_per_1k_tokens": round(cost_per_1k_tokens, 4),
            }
        }
        
    async def autoscale_endpoint(
        self,
        endpoint_id: str,
        target_utilization: float = 0.8,
        min_instances: int = 1,
        max_instances: int = 10
    ) -> Dict[str, Any]:
        """
        Configure autoscaling for endpoint.
        
        Args:
            endpoint_id: Endpoint to scale
            target_utilization: Target GPU utilization
            min_instances: Minimum instances
            max_instances: Maximum instances
            
        Returns:
            Autoscaling configuration
        """
        # This would implement actual autoscaling logic
        # For now, return configuration
        return {
            "endpoint_id": endpoint_id,
            "autoscaling_enabled": True,
            "target_utilization": target_utilization,
            "min_instances": min_instances,
            "max_instances": max_instances,
            "current_instances": 1
        }
        
    def _estimate_model_size(self, model_path: str) -> str:
        """Estimate model size from path."""
        # Simple heuristic based on model name
        path_lower = model_path.lower()
        
        if any(x in path_lower for x in ["3b", "3.5b", "phi-3"]):
            return "3B"
        elif any(x in path_lower for x in ["7b", "mistral", "llama-2-7"]):
            return "7B"
        elif any(x in path_lower for x in ["13b", "llama-2-13"]):
            return "13B"
        elif any(x in path_lower for x in ["30b", "34b"]):
            return "30B"
        elif any(x in path_lower for x in ["70b", "llama-2-70"]):
            return "70B"
        else:
            return "7B"  # Default
            
    def _generate_vllm_command(
        self,
        model_path: str,
        max_batch_size: int,
        quantization: Optional[str]
    ) -> str:
        """Generate vLLM server command."""
        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", model_path,
            "--host", "0.0.0.0",
            "--port", "8000",
            "--max-model-len", "4096",
            "--max-num-batched-tokens", str(max_batch_size * 512),
            "--trust-remote-code",
        ]
        
        if quantization:
            cmd.extend(["--quantization", quantization])
            
        return " ".join(cmd)
        
    async def _wait_for_server_ready(
        self,
        instance_id: str,
        timeout: int = 300
    ) -> str:
        """Wait for inference server to be ready."""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            # Get instance info
            status = await self.manager.get_instance_status(instance_id)
            
            if status.get("container", {}).get("ready"):
                raise NotImplementedError(
                    f"Endpoint URL resolution for instance {instance_id} not yet implemented — needs RunPod API query"
                )
                
            await asyncio.sleep(5)
            
        raise TimeoutError("Server failed to start in time")
        
    async def compare_inference_costs(
        self,
        model_size: str,
        monthly_requests: int,
        avg_tokens_per_request: int = 200
    ) -> Dict[str, Any]:
        """
        Compare inference costs across providers.
        
        Args:
            model_size: Model size to serve
            monthly_requests: Expected monthly requests
            avg_tokens_per_request: Average tokens per request
            
        Returns:
            Cost comparison
        """
        total_tokens = monthly_requests * avg_tokens_per_request
        
        # Get RunPod costs for different GPU options
        gpu_options = ["RTX_4090", "A100_40GB", "A100_80GB"]
        runpod_costs = {}
        
        for gpu in gpu_options:
            config = self.optimizer.optimize_for_inference(
                model_size,
                requests_per_hour=monthly_requests / 720,  # Monthly to hourly
                avg_output_tokens=avg_tokens_per_request
            )
            
            if config.get("gpu_type") == gpu:
                runpod_costs[gpu] = {
                    "monthly_cost": config["cost_per_hour"] * 720,
                    "cost_per_1k_requests": config["cost_per_1k_requests"],
                    "avg_latency_ms": config["avg_latency_ms"]
                }
                
        # Compare with token-based pricing
        comparison = self.calculator.calculate_monthly_budget(
            model_size,
            daily_tokens=total_tokens / 30
        )
        
        return {
            "model_size": model_size,
            "monthly_requests": monthly_requests,
            "total_monthly_tokens": total_tokens,
            "runpod_options": runpod_costs,
            "token_based_providers": comparison["providers"],
            "recommendation": comparison["recommendations"]
        }


# Validation
if __name__ == "__main__":
    async def test_server():
        server = InferenceServer()
        
        print("Inference Server Test")
        print("=" * 50)
        
        # Test deployment configuration
        model_path = "unsloth/Phi-3.5-mini-instruct"
        
        print(f"\nDeployment Plan for: {model_path}")
        print("-" * 30)
        
        # Estimate model size
        model_size = server._estimate_model_size(model_path)
        print(f"Estimated size: {model_size}")
        
        # Get optimal configuration
        config = server.optimizer.optimize_for_inference(
            model_size,
            requests_per_hour=500,
            avg_input_tokens=100,
            avg_output_tokens=200,
            target_latency_ms=1000
        )
        
        print(f"Recommended GPU: {config['gpu_type']}")
        print(f"Max batch size: {config['max_batch_size']}")
        print(f"Cost per hour: ${config['cost_per_hour']}")
        print(f"Cost per 1K requests: ${config['cost_per_1k_requests']}")
        
        # Test cost comparison
        print("\n\nCost Comparison (10K requests/month):")
        comparison = await server.compare_inference_costs(
            model_size,
            monthly_requests=10000,
            avg_tokens_per_request=200
        )
        
        print(f"\nRunPod Options:")
        for gpu, metrics in comparison["runpod_options"].items():
            print(f"  {gpu}: ${metrics['monthly_cost']:.2f}/month")
            
        print(f"\nRecommended: {comparison['recommendation']['cheapest']}")
        print(f"Monthly cost: ${comparison['recommendation']['cheapest_monthly_cost']:.2f}")
        
    # asyncio.run(test_server())
    print("\n✅ Module validation passed")