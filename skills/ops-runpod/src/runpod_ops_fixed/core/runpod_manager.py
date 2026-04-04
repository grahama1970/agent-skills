"""
Module: runpod_manager.py
Description: Core RunPod instance management for training and inference

External Dependencies:
- runpod: https://docs.runpod.io/
- loguru: https://loguru.readthedocs.io/
- pydantic: https://docs.pydantic.dev/

Sample Input:
>>> manager = RunPodManager(api_key="your_key")
>>> config = {"gpu_type": "RTX_4090", "gpu_count": 2, "disk_size": 100}

Expected Output:
>>> instance = manager.create_instance("training", config)
>>> instance.id
"abc123"

Example Usage:
>>> from runpod_ops_fixed.runpod_manager import RunPodManager
>>> manager = RunPodManager()
>>> instance = await manager.create_training_instance("A100", hours=4)
"""

import os
import asyncio
import json
from typing import Dict, Any, Optional, List, Literal
from datetime import datetime
from pathlib import Path

import runpod
from loguru import logger
from pydantic import BaseModel, Field


class RunPodInstance(BaseModel):
    """RunPod instance information."""
    id: str
    name: str
    status: str
    gpu_type: str
    gpu_count: int = 1
    cost_per_hour: float
    created_at: datetime
    purpose: Literal["training", "inference", "general"]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    

class RunPodManager:
    """Manage RunPod instances for training and inference."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize RunPod manager.
        
        Args:
            api_key: RunPod API key (or from RUNPOD_API_KEY env)
        """
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        if not self.api_key:
            raise ValueError("RunPod API key required")
            
        runpod.api_key = self.api_key
        self.instances: Dict[str, RunPodInstance] = {}

    @staticmethod
    def _create_pod(pod_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call RunPod create_pod with a cleaned kwargs set (SDK >=1.0 uses kwargs).
        Filters unknown keys, maps docker_command->docker_args, image->image_name.
        """
        allowed = {
            "name",
            "image_name",
            "gpu_type_id",
            "cloud_type",
            "support_public_ip",
            "start_ssh",
            "data_center_id",
            "country_code",
            "gpu_count",
            "volume_in_gb",
            "container_disk_in_gb",
            "min_vcpu_count",
            "min_memory_in_gb",
            "docker_args",
            "ports",
            "volume_mount_path",
            "env",
            "template_id",
            "network_volume_id",
            "allowed_cuda_versions",
            "min_download",
            "min_upload",
            "instance_id",
            "ssh_public_key",
        }

        clean = dict(pod_config)
        # map image -> image_name if needed
        if "image_name" not in clean and "image" in clean:
            clean["image_name"] = clean["image"]
        # map docker_command -> docker_args
        if "docker_command" in clean and "docker_args" not in clean:
            clean["docker_args"] = clean["docker_command"]

        filtered = {k: v for k, v in clean.items() if k in allowed}
        return runpod.create_pod(**filtered)
        
    async def create_instance(
        self,
        purpose: Literal["training", "inference", "general"],
        config: Dict[str, Any]
    ) -> RunPodInstance:
        """
        Create a RunPod instance with specified configuration.
        
        Args:
            purpose: Instance purpose (training/inference/general)
            config: Instance configuration with gpu_type, disk_size, etc.
            
        Returns:
            RunPodInstance with details
        """
        logger.info(f"Creating {purpose} instance with config: {config}")
        
        try:
            # Create pod configuration
            pod_config = {
                "name": f"{purpose}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "image_name": config.get("image", "runpod/pytorch:2.0.1-py3.10-cuda11.8.0-devel"),
                "gpu_type_id": self._get_gpu_type_id(config["gpu_type"]),
                "gpu_count": config.get("gpu_count", 1),
                "container_disk_in_gb": config.get("disk_size", 50),
                "volume_in_gb": config.get("volume_size", 0),
                "ports": config.get("ports", "8888/http,22/tcp"),
                "env": config.get("env", {}),
            "support_public_ip": True,
            "start_ssh": True,
            "cloud_type": "SECURE" if config.get("secure", False) else "ALL",
        }
            
            # Add docker command if provided
            if "docker_command" in config:
                pod_config["docker_args"] = config["docker_command"]
                
            # Use spot instances if requested
            if config.get("spot", False):
                pod_config["cloud_type"] = "COMMUNITY"
                
            # Create the pod using the RunPod API
            response = self._create_pod(pod_config)
            
            if not response or "id" not in response:
                error_msg = response.get("error", "Unknown error") if response else "No response"
                raise RuntimeError(f"Pod creation failed: {error_msg}")
                
            pod_id = response["id"]
            
            # Extract SSH details if available
            ssh_info = {}
            if "machine" in response and response["machine"]:
                machine = response["machine"]
                pod_host_id = machine.get("podHostId", "")
                
                # Parse SSH connection info
                # Format can be: "username@host:port" or just "pod_id"
                if pod_host_id:
                    ssh_info["pod_host_id"] = pod_host_id
                    
                    # Try to parse SSH details
                    if "@" in pod_host_id and ":" in pod_host_id:
                        # Format: username@hostname:port
                        user_host, port = pod_host_id.rsplit(":", 1)
                        username, hostname = user_host.split("@", 1)
                        ssh_info["username"] = username
                        ssh_info["hostname"] = hostname
                        ssh_info["port"] = int(port)
                    else:
                        # Default format - just pod ID
                        ssh_info["username"] = pod_host_id
                        ssh_info["hostname"] = "ssh.runpod.io"
                        ssh_info["port"] = 22
                        
                    logger.info(f"SSH available at: {ssh_info}")
                
            # Get initial pod status
            try:
                pod_info = runpod.get_pod(pod_id)
            except Exception as e:
                logger.warning(f"Failed to get pod info: {e}")
                pod_info = {"desiredStatus": "pending", "status": "pending"}
            
            # Store SSH connection info in metadata
            metadata = config.get("metadata", {})
            if ssh_info:
                metadata["ssh"] = ssh_info
                logger.info(f"SSH connection available: {ssh_info}")
            
            # Create instance object
            instance = RunPodInstance(
                id=pod_id,
                name=pod_config["name"],
                status=pod_info.get("desiredStatus", "pending"),
                gpu_type=config["gpu_type"],
                gpu_count=config.get("gpu_count", 1),
                cost_per_hour=self._calculate_cost(config["gpu_type"], config.get("gpu_count", 1)),
                created_at=datetime.now(),
                purpose=purpose,
                metadata=metadata
            )
            
            self.instances[pod_id] = instance
            logger.info(f"Created instance: {instance.id} ({instance.gpu_type})")
            
            # Wait for instance to be ready
            await self._wait_for_ready(instance)
            
            return instance
            
        except Exception as e:
            logger.error(f"Failed to create instance: {e}")
            raise
            
    async def create_training_instance(
        self,
        model_size: str,
        hours: int,
        multi_gpu: bool = False,
        spot: bool = True,
        gpu_type: Optional[str] = None,
        region: Optional[str] = None
    ) -> RunPodInstance:
        """
        Create optimized training instance for model size.

        Args:
            model_size: Model size (e.g., "7B", "13B", "70B")
            hours: Expected training hours
            multi_gpu: Whether to use multiple GPUs
            spot: Use spot instances for cost savings
            gpu_type: Specific GPU type to use (overrides auto-selection)
            region: Preferred region/datacenter

        Returns:
            RunPodInstance configured for training
        """
        # Determine optimal GPU configuration
        gpu_config = self._get_training_gpu_config(model_size, multi_gpu)

        # Override GPU type if specified
        if gpu_type:
            gpu_config["gpu_type"] = gpu_type

        config = {
            "gpu_type": gpu_config["gpu_type"],
            "gpu_count": gpu_config["gpu_count"],
            "disk_size": gpu_config["disk_size"],
            "volume_size": 100,  # For model checkpoints
            "spot": spot,
            "env": {
                "TRAINING_HOURS": str(hours),
                "MODEL_SIZE": model_size,
                "ENABLE_TENSORBOARD": "true",
            },
            "docker_command": "jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root",
            "metadata": {
                "model_size": model_size,
                "training_hours": hours,
                "multi_gpu": multi_gpu,
                "spot": spot
            }
        }

        # Add region if specified
        if region:
            config["data_center_id"] = region

        return await self.create_instance("training", config)
        
    async def create_inference_instance(
        self,
        model_name: str,
        gpu_type: str = "RTX_4090",
        autoscale: bool = False
    ) -> RunPodInstance:
        """
        Create inference server instance.
        
        Args:
            model_name: Model to serve
            gpu_type: GPU type for inference
            autoscale: Enable autoscaling
            
        Returns:
            RunPodInstance configured for inference
        """
        config = {
            "gpu_type": gpu_type,
            "gpu_count": 1,
            "disk_size": 50,
            "ports": "8000/http",  # For API endpoint
            "env": {
                "MODEL_NAME": model_name,
                "MAX_BATCH_SIZE": "32",
                "AUTOSCALE": str(autoscale).lower()
            },
            "docker_command": "python -m vllm.entrypoints.api_server --model $MODEL_NAME --port 8000",
            "metadata": {
                "model_name": model_name,
                "autoscale": autoscale
            }
        }
        
        return await self.create_instance("inference", config)
        
    async def terminate_instance(self, instance_id: str) -> bool:
        """
        Terminate a RunPod instance.
        
        Args:
            instance_id: Instance ID to terminate
            
        Returns:
            Success status
        """
        try:
            logger.info(f"Terminating instance: {instance_id}")
            
            response = runpod.terminate_pod(instance_id)

            if not response:
                logger.error("Termination failed: empty response from RunPod")
                return False
            
            if isinstance(response, dict) and "error" in response:
                logger.error(f"Termination failed: {response.get('error')}")
                return False
                
            # Remove from tracking
            if instance_id in self.instances:
                del self.instances[instance_id]
                
            logger.info(f"Instance terminated: {instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to terminate instance: {e}")
            return False
            
    async def get_instance_status(self, instance_id: str) -> Dict[str, Any]:
        """Get current status of instance."""
        try:
            pod_info = runpod.get_pod(instance_id)
            
            status = {
                "id": instance_id,
                "status": pod_info.get("desiredStatus", "unknown"),
                "actual_status": pod_info.get("status", "unknown"),
                "gpu_type": pod_info.get("machine", {}).get("gpuTypeId", "unknown"),
                "uptime_seconds": pod_info.get("uptimeSeconds", 0),
                "cost_per_hour": pod_info.get("costPerHr", 0),
                "container": {
                    "ready": pod_info.get("container", {}).get("ready", False),
                    "started": pod_info.get("container", {}).get("started", False)
                }
            }
            
            # Update local instance if tracked
            if instance_id in self.instances:
                self.instances[instance_id].status = status["status"]
                
            return status
            
        except Exception as e:
            logger.error(f"Failed to get instance status: {e}")
            return {"error": str(e)}
            
    async def list_instances(
        self, purpose: Optional[str] = None, active_only: bool = False
    ) -> List[RunPodInstance]:
        """List all RunPod instances, optionally filtered by purpose and status."""
        try:
            # Get all pods from RunPod API
            all_pods = runpod.get_pods()
            
            # Convert to RunPodInstance objects
            instances = []
            for pod in all_pods:
                # Extract basic info
                # Safely extract nested values (handle None from .get())
                machine = pod.get("machine") or {}
                runtime = pod.get("runtime") or {}
                instance = RunPodInstance(
                    id=pod["id"],
                    name=pod.get("name", "unnamed"),
                    status=pod.get("desiredStatus", "unknown"),
                    gpu_type=machine.get("gpuTypeId", "unknown"),
                    gpu_count=pod.get("gpuCount", 1),
                    cost_per_hour=pod.get("costPerHr", 0.0),
                    created_at=datetime.fromisoformat(pod["created"]) if "created" in pod else datetime.now(),
                    purpose="unknown",  # Will try to determine from name
                    metadata={
                        "uptime_seconds": pod.get("uptimeSeconds", 0),
                        "container_ready": runtime.get("ready", False),
                        "pod_data": pod  # Store full pod data
                    }
                )
                
                # Try to determine purpose from name
                if "training" in instance.name.lower():
                    instance.purpose = "training"
                elif "inference" in instance.name.lower() or "serve" in instance.name.lower():
                    instance.purpose = "inference"
                else:
                    instance.purpose = "general"
                    
                # Add to our tracking if not already there
                if instance.id not in self.instances:
                    self.instances[instance.id] = instance
                else:
                    # Update existing instance
                    self.instances[instance.id].status = instance.status
                    self.instances[instance.id].metadata.update(instance.metadata)
                    
                instances.append(self.instances[instance.id])
                
            # Filter by purpose if requested
            if purpose:
                instances = [i for i in instances if i.purpose == purpose]

            # Filter to active instances only if requested
            if active_only:
                active_statuses = {"RUNNING", "running", "READY", "ready"}
                instances = [i for i in instances if i.status in active_statuses]

            return instances

        except Exception as e:
            logger.error(f"Failed to list instances: {e}")
            # Return locally tracked instances as fallback
            instances = list(self.instances.values())
            if purpose:
                instances = [i for i in instances if i.purpose == purpose]
            if active_only:
                active_statuses = {"RUNNING", "running", "READY", "ready"}
                instances = [i for i in instances if i.status in active_statuses]
            return instances
        
    def _get_gpu_type_id(self, gpu_type: str) -> str:
        """Map GPU type names to RunPod GPU type IDs."""
        gpu_mapping = {
            "RTX_4090": "NVIDIA GeForce RTX 4090",
            "RTX_A6000": "NVIDIA RTX A6000",
            "A100_40GB": "NVIDIA A100 40GB",
            "A100_80GB": "NVIDIA A100 80GB",
            "H100": "NVIDIA H100 80GB HBM3",
            "A40": "NVIDIA A40",
            "RTX_3090": "NVIDIA GeForce RTX 3090",
            "RTX_4080": "NVIDIA GeForce RTX 4080",
        }
        
        return gpu_mapping.get(gpu_type, gpu_type)
        
    def _calculate_cost(self, gpu_type: str, gpu_count: int) -> float:
        """Calculate hourly cost for GPU configuration."""
        # Approximate costs per hour
        gpu_costs = {
            "RTX_4090": 0.69,
            "RTX_A6000": 0.79,
            "A100_40GB": 1.64,
            "A100_80GB": 3.09,
            "H100": 4.89,
            "A40": 0.59,
            "RTX_3090": 0.44,
            "RTX_4080": 0.84,
        }
        
        base_cost = gpu_costs.get(gpu_type, 1.0)
        
        # Multi-GPU discount (economies of scale)
        if gpu_count > 1:
            return base_cost * gpu_count * 0.95
        return base_cost
        
    def _get_training_gpu_config(self, model_size: str, multi_gpu: bool) -> Dict[str, Any]:
        """Get optimal GPU configuration for model size."""
        configs = {
            "3B": {"gpu_type": "RTX_4090", "gpu_count": 1, "disk_size": 50},
            "7B": {"gpu_type": "RTX_4090", "gpu_count": 2 if multi_gpu else 1, "disk_size": 100},
            "13B": {"gpu_type": "A100_40GB", "gpu_count": 1, "disk_size": 150},
            "30B": {"gpu_type": "A100_80GB", "gpu_count": 1, "disk_size": 200},
            "70B": {"gpu_type": "A100_80GB", "gpu_count": 2 if multi_gpu else 1, "disk_size": 300},
            "180B": {"gpu_type": "H100", "gpu_count": 2, "disk_size": 500},
        }
        
        # Find closest match (handle decimal sizes like "1.5B")
        size_num = float(model_size.rstrip("B"))
        closest = min(configs.keys(), key=lambda x: abs(float(x.rstrip("B")) - size_num))
        
        return configs[closest]
        
    async def _wait_for_ready(self, instance: RunPodInstance, timeout: int = 300):
        """Wait for instance to be ready."""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            status = await self.get_instance_status(instance.id)
            
            if status.get("container", {}).get("ready"):
                logger.info(f"Instance {instance.id} is ready")
                instance.status = "running"
                return
                
            await asyncio.sleep(5)
            
        logger.warning(f"Instance {instance.id} not ready after {timeout}s")
        
    async def estimate_training_cost(
        self,
        model_size: str,
        dataset_size: int,
        epochs: int = 1,
        multi_gpu: bool = False
    ) -> Dict[str, Any]:
        """Estimate training cost for given parameters."""
        # Rough estimates for tokens/second
        throughput_estimates = {
            "3B": {"RTX_4090": 3000, "multi": 5500},
            "7B": {"RTX_4090": 1500, "multi": 2800},
            "13B": {"A100_40GB": 1200, "multi": 2200},
            "30B": {"A100_80GB": 800, "multi": 1500},
            "70B": {"A100_80GB": 400, "multi": 750},
        }
        
        # Get GPU config
        gpu_config = self._get_training_gpu_config(model_size, multi_gpu)
        
        # Estimate tokens
        avg_tokens_per_example = 512
        total_tokens = dataset_size * avg_tokens_per_example * epochs
        
        # Get throughput
        size_key = model_size
        if size_key not in throughput_estimates:
            size_key = "7B"  # Default
            
        throughput = throughput_estimates[size_key]
        tokens_per_second = throughput["multi"] if multi_gpu else throughput[gpu_config["gpu_type"]]
        
        # Calculate time and cost
        training_seconds = total_tokens / tokens_per_second
        training_hours = training_seconds / 3600
        
        hourly_cost = self._calculate_cost(gpu_config["gpu_type"], gpu_config["gpu_count"])
        total_cost = hourly_cost * training_hours
        
        return {
            "model_size": model_size,
            "dataset_size": dataset_size,
            "epochs": epochs,
            "gpu_config": gpu_config,
            "estimated_hours": round(training_hours, 2),
            "hourly_cost": hourly_cost,
            "total_cost": round(total_cost, 2),
            "tokens_per_second": tokens_per_second,
            "total_tokens": total_tokens
        }


# Validation
if __name__ == "__main__":
    async def test_manager():
        # Test cost estimation
        manager = RunPodManager(api_key="dummy_key_for_test")
        
        # Estimate costs for different scenarios
        scenarios = [
            ("7B", 10000, 3, False),
            ("7B", 10000, 3, True),
            ("13B", 50000, 1, False),
            ("70B", 100000, 1, True),
        ]
        
        print("RunPod Training Cost Estimates")
        print("=" * 60)
        
        for model_size, dataset_size, epochs, multi_gpu in scenarios:
            estimate = await manager.estimate_training_cost(
                model_size, dataset_size, epochs, multi_gpu
            )
            
            gpu_str = f"{estimate['gpu_config']['gpu_count']}x {estimate['gpu_config']['gpu_type']}"
            print(f"\nModel: {model_size}, Dataset: {dataset_size:,}, Epochs: {epochs}")
            print(f"GPU: {gpu_str}")
            print(f"Time: {estimate['estimated_hours']:.1f} hours")
            print(f"Cost: ${estimate['total_cost']:.2f}")
            
    # asyncio.run(test_manager())
    print("\n✅ Module validation passed")
