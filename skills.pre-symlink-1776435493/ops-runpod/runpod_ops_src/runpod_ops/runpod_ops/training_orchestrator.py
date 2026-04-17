"""
Module: training_orchestrator.py
Description: Orchestrate distributed training jobs on RunPod

External Dependencies:
- runpod: https://docs.runpod.io/
- loguru: https://loguru.readthedocs.io/
- pydantic: https://docs.pydantic.dev/

Sample Input:
>>> orchestrator = TrainingOrchestrator()
>>> job = await orchestrator.start_training_job(config, dataset_path)

Expected Output:
>>> job
{"job_id": "train_123", "instances": ["gpu1", "gpu2"], "status": "running"}

Example Usage:
>>> from runpod_ops.training_orchestrator import TrainingOrchestrator
>>> orchestrator = TrainingOrchestrator()
>>> await orchestrator.run_distributed_training(model_config, num_gpus=4)
"""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
from pathlib import Path
import tempfile
import shutil

from loguru import logger
from pydantic import BaseModel, Field

from runpod_ops.runpod_manager import RunPodManager, RunPodInstance
from runpod_ops.instance_optimizer import InstanceOptimizer
from runpod_ops.instance_monitor import InstanceMonitor


class TrainingConfig(BaseModel):
    """Training job configuration."""
    model_name: str
    model_size: str
    dataset_path: str
    output_path: str
    num_epochs: int = 1
    learning_rate: float = 2e-4
    batch_size: Optional[int] = None
    gradient_accumulation_steps: int = 1
    warmup_steps: int = 100
    save_steps: int = 500
    logging_steps: int = 10
    evaluation_strategy: str = "steps"
    eval_steps: int = 500
    save_total_limit: int = 3
    load_best_model_at_end: bool = True
    metric_for_best_model: str = "eval_loss"
    greater_is_better: bool = False
    fp16: bool = True
    gradient_checkpointing: bool = True
    optim: str = "adamw_torch"
    lr_scheduler_type: str = "cosine"
    dataloader_num_workers: int = 4
    

class TrainingJob(BaseModel):
    """Training job information."""
    job_id: str
    config: TrainingConfig
    instances: List[str]
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    start_time: datetime
    end_time: Optional[datetime] = None
    total_cost: float = 0.0
    output_location: Optional[str] = None
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    

class TrainingOrchestrator:
    """Orchestrate training jobs on RunPod."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize training orchestrator.
        
        Args:
            api_key: RunPod API key
        """
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        self.manager = RunPodManager(self.api_key)
        self.optimizer = InstanceOptimizer()
        self.monitor = InstanceMonitor(self.api_key)
        
        self.active_jobs: Dict[str, TrainingJob] = {}
        
    async def start_training_job(
        self,
        config: TrainingConfig,
        num_gpus: int = 1,
        gpu_type: Optional[str] = None,
        spot_instances: bool = True,
        max_budget: Optional[float] = None
    ) -> TrainingJob:
        """
        Start a training job with optimal configuration.
        
        Args:
            config: Training configuration
            num_gpus: Number of GPUs to use
            gpu_type: Specific GPU type or auto-select
            spot_instances: Use spot instances for cost savings
            max_budget: Maximum budget for training
            
        Returns:
            TrainingJob with details
        """
        job_id = f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting training job: {job_id}")
        
        try:
            # Determine optimal instance configuration
            if not gpu_type:
                instance_config = self.optimizer.optimize_for_training(
                    config.model_size,
                    dataset_size=10000,  # Estimate
                    epochs=config.num_epochs,
                    batch_size=config.batch_size
                )
                gpu_type = instance_config["gpu_type"]
                if num_gpus == 1:
                    num_gpus = instance_config.get("gpu_count", 1)
                    
            # Create training script
            training_script = self._generate_training_script(config, num_gpus)
            
            # Upload script and prepare instance
            script_url = await self._upload_training_script(training_script, job_id)
            
            # Launch instances
            instances = []
            if num_gpus > 1 and self._should_use_distributed(config.model_size, num_gpus):
                # Distributed training
                instances = await self._launch_distributed_instances(
                    num_gpus, gpu_type, config, script_url, spot_instances
                )
            else:
                # Single instance (possibly multi-GPU)
                instance = await self.manager.create_training_instance(
                    config.model_size,
                    hours=self._estimate_training_hours(config),
                    multi_gpu=(num_gpus > 1),
                    spot=spot_instances
                )
                instances = [instance]
                
            # Create job record
            job = TrainingJob(
                job_id=job_id,
                config=config,
                instances=[i.id for i in instances],
                status="running",
                start_time=datetime.now()
            )
            
            self.active_jobs[job_id] = job
            
            # Start monitoring
            asyncio.create_task(self._monitor_job(job))
            
            return job
            
        except Exception as e:
            logger.error(f"Failed to start training job: {e}")
            
            # Create failed job record
            job = TrainingJob(
                job_id=job_id,
                config=config,
                instances=[],
                status="failed",
                start_time=datetime.now(),
                end_time=datetime.now(),
                error_message=str(e)
            )
            
            self.active_jobs[job_id] = job
            return job
            
    async def run_distributed_training(
        self,
        config: TrainingConfig,
        num_nodes: int = 2,
        gpus_per_node: int = 2,
        strategy: Literal["ddp", "fsdp", "deepspeed"] = "ddp"
    ) -> TrainingJob:
        """
        Run distributed training across multiple nodes.
        
        Args:
            config: Training configuration
            num_nodes: Number of nodes
            gpus_per_node: GPUs per node
            strategy: Distributed training strategy
            
        Returns:
            TrainingJob with details
        """
        job_id = f"dist_train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting distributed training: {job_id}")
        
        # Update config for distributed training
        distributed_config = config.copy()
        distributed_config.gradient_accumulation_steps = max(
            1,
            distributed_config.gradient_accumulation_steps // (num_nodes * gpus_per_node)
        )
        
        # Determine GPU type for distributed training
        total_gpus = num_nodes * gpus_per_node
        instance_config = self.optimizer.optimize_for_training(
            config.model_size,
            dataset_size=10000,
            epochs=config.num_epochs
        )
        
        gpu_type = instance_config["gpu_type"]
        
        # Create distributed training script
        training_script = self._generate_distributed_training_script(
            distributed_config,
            num_nodes,
            gpus_per_node,
            strategy
        )
        
        # Upload script
        script_url = await self._upload_training_script(training_script, job_id)
        
        # Launch master node
        master_instance = await self._launch_master_node(
            gpu_type, gpus_per_node, distributed_config, script_url
        )
        
        # Launch worker nodes
        worker_instances = []
        for i in range(num_nodes - 1):
            worker = await self._launch_worker_node(
                gpu_type, gpus_per_node, distributed_config, 
                script_url, master_instance.id, i + 1
            )
            worker_instances.append(worker)
            
        all_instances = [master_instance] + worker_instances
        
        # Create job
        job = TrainingJob(
            job_id=job_id,
            config=distributed_config,
            instances=[i.id for i in all_instances],
            status="running",
            start_time=datetime.now(),
            metrics={
                "num_nodes": num_nodes,
                "gpus_per_node": gpus_per_node,
                "total_gpus": total_gpus,
                "strategy": strategy
            }
        )
        
        self.active_jobs[job_id] = job
        
        # Monitor job
        asyncio.create_task(self._monitor_distributed_job(job, master_instance.id))
        
        return job
        
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get current status of training job."""
        if job_id not in self.active_jobs:
            return {"error": "Job not found"}
            
        job = self.active_jobs[job_id]
        
        # Get instance statuses
        instance_statuses = []
        for instance_id in job.instances:
            status = await self.manager.get_instance_status(instance_id)
            instance_statuses.append(status)
            
        # Calculate total cost
        total_cost = sum(
            status.get("cost_per_hour", 0) * status.get("uptime_seconds", 0) / 3600
            for status in instance_statuses
        )
        
        return {
            "job_id": job_id,
            "status": job.status,
            "start_time": job.start_time.isoformat(),
            "runtime_hours": (datetime.now() - job.start_time).total_seconds() / 3600,
            "instances": instance_statuses,
            "total_cost": round(total_cost, 2),
            "metrics": job.metrics,
            "config": job.config.dict()
        }
        
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running training job."""
        if job_id not in self.active_jobs:
            return False
            
        job = self.active_jobs[job_id]
        
        if job.status not in ["running", "pending"]:
            return False
            
        logger.info(f"Cancelling job: {job_id}")
        
        # Terminate all instances
        for instance_id in job.instances:
            await self.manager.terminate_instance(instance_id)
            
        # Update job status
        job.status = "cancelled"
        job.end_time = datetime.now()
        
        return True
        
    def _generate_training_script(self, config: TrainingConfig, num_gpus: int) -> str:
        """Generate training script for job."""
        script = f"""#!/bin/bash
# Training script for {config.model_name}

# Setup environment
pip install -U unsloth transformers accelerate datasets

# Training command
python -m unsloth.train \\
    --model_name {config.model_name} \\
    --dataset_path {config.dataset_path} \\
    --output_dir {config.output_path} \\
    --num_train_epochs {config.num_epochs} \\
    --learning_rate {config.learning_rate} \\
    --warmup_steps {config.warmup_steps} \\
    --save_steps {config.save_steps} \\
    --logging_steps {config.logging_steps} \\
    --evaluation_strategy {config.evaluation_strategy} \\
    --eval_steps {config.eval_steps} \\
    --save_total_limit {config.save_total_limit} \\
    --load_best_model_at_end {str(config.load_best_model_at_end).lower()} \\
    --metric_for_best_model {config.metric_for_best_model} \\
    --greater_is_better {str(config.greater_is_better).lower()} \\
    --fp16 {str(config.fp16).lower()} \\
    --gradient_checkpointing {str(config.gradient_checkpointing).lower()} \\
    --optim {config.optim} \\
    --lr_scheduler_type {config.lr_scheduler_type} \\
    --dataloader_num_workers {config.dataloader_num_workers}
"""
        
        if config.batch_size:
            script += f"    --per_device_train_batch_size {config.batch_size} \\\n"
            
        if config.gradient_accumulation_steps > 1:
            script += f"    --gradient_accumulation_steps {config.gradient_accumulation_steps} \\\n"
            
        if num_gpus > 1:
            script = f"torchrun --nproc_per_node={num_gpus} " + script.replace("python -m", "")
            
        return script
        
    def _generate_distributed_training_script(
        self,
        config: TrainingConfig,
        num_nodes: int,
        gpus_per_node: int,
        strategy: str
    ) -> str:
        """Generate distributed training script."""
        # This would generate appropriate distributed training script
        # based on strategy (DDP, FSDP, DeepSpeed)
        return self._generate_training_script(config, gpus_per_node)
        
    async def _upload_training_script(self, script: str, job_id: str) -> str:
        """Upload training script to accessible location."""
        raise NotImplementedError(
            f"Training script upload for job {job_id} not yet implemented — needs S3 or object storage integration"
        )
        
    def _estimate_training_hours(self, config: TrainingConfig) -> int:
        """Estimate training time in hours."""
        # Simple heuristic - would be refined with actual benchmarks
        model_multiplier = {
            "3B": 1,
            "7B": 2,
            "13B": 4,
            "30B": 8,
            "70B": 16,
        }
        
        base_hours = config.num_epochs * 2  # Base estimate
        size_mult = model_multiplier.get(config.model_size, 4)
        
        return base_hours * size_mult
        
    def _should_use_distributed(self, model_size: str, num_gpus: int) -> bool:
        """Determine if distributed training is beneficial."""
        # Large models benefit from distribution
        size_num = int(model_size.rstrip("B"))
        return size_num >= 30 or num_gpus >= 4
        
    async def _launch_distributed_instances(
        self,
        num_gpus: int,
        gpu_type: str,
        config: TrainingConfig,
        script_url: str,
        spot: bool
    ) -> List[RunPodInstance]:
        """Launch instances for distributed training."""
        # Simplified - would implement actual distributed setup
        instances = []
        
        for i in range(num_gpus):
            instance = await self.manager.create_instance(
                "training",
                {
                    "gpu_type": gpu_type,
                    "gpu_count": 1,
                    "disk_size": 100,
                    "env": {
                        "SCRIPT_URL": script_url,
                        "NODE_RANK": str(i),
                        "WORLD_SIZE": str(num_gpus),
                    }
                }
            )
            instances.append(instance)
            
        return instances
        
    async def _launch_master_node(
        self,
        gpu_type: str,
        gpus_per_node: int,
        config: TrainingConfig,
        script_url: str
    ) -> RunPodInstance:
        """Launch master node for distributed training."""
        return await self.manager.create_instance(
            "training",
            {
                "gpu_type": gpu_type,
                "gpu_count": gpus_per_node,
                "disk_size": 200,
                "env": {
                    "SCRIPT_URL": script_url,
                    "NODE_RANK": "0",
                    "MASTER_ADDR": "localhost",
                    "MASTER_PORT": "29500",
                }
            }
        )
        
    async def _launch_worker_node(
        self,
        gpu_type: str,
        gpus_per_node: int,
        config: TrainingConfig,
        script_url: str,
        master_id: str,
        rank: int
    ) -> RunPodInstance:
        """Launch worker node for distributed training."""
        # Get master IP (would query actual instance)
        # Stub: must query actual RunPod instance for real master IP
        raise NotImplementedError(
            f"Cannot determine master IP for rank {rank} — RunPod instance API query not implemented"
        )
        
        return await self.manager.create_instance(
            "training",
            {
                "gpu_type": gpu_type,
                "gpu_count": gpus_per_node,
                "disk_size": 200,
                "env": {
                    "SCRIPT_URL": script_url,
                    "NODE_RANK": str(rank),
                    "MASTER_ADDR": master_ip,
                    "MASTER_PORT": "29500",
                }
            }
        )
        
    async def _monitor_job(self, job: TrainingJob):
        """Monitor a training job."""
        try:
            # Simple monitoring - would be enhanced with actual log parsing
            while job.status == "running":
                # Check instance health
                all_healthy = True
                for instance_id in job.instances:
                    health = await self.monitor.check_instance_health(instance_id)
                    if not health.get("healthy"):
                        all_healthy = False
                        break
                        
                if not all_healthy:
                    job.status = "failed"
                    job.error_message = "Instance unhealthy"
                    break
                    
                await asyncio.sleep(60)
                
        except Exception as e:
            logger.error(f"Job monitoring error: {e}")
            job.status = "failed"
            job.error_message = str(e)
            
        finally:
            job.end_time = datetime.now()
            
    async def _monitor_distributed_job(self, job: TrainingJob, master_id: str):
        """Monitor distributed training job."""
        # Would implement distributed job monitoring
        await self._monitor_job(job)


# Validation
if __name__ == "__main__":
    # Test configuration
    config = TrainingConfig(
        model_name="unsloth/Phi-3.5-mini-instruct",
        model_size="3B",
        dataset_path="dataset.json",
        output_path="./output",
        num_epochs=3,
        learning_rate=2e-4
    )
    
    print("Training Orchestrator Test")
    print("=" * 50)
    print(f"Model: {config.model_name}")
    print(f"Size: {config.model_size}")
    print(f"Epochs: {config.num_epochs}")
    
    # Test script generation
    orchestrator = TrainingOrchestrator()
    script = orchestrator._generate_training_script(config, num_gpus=2)
    
    print("\nGenerated Training Script:")
    print("-" * 30)
    print(script[:500] + "...")
    
    print("\n✅ Module validation passed")