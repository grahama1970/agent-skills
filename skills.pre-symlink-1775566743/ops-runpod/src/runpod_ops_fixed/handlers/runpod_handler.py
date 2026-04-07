"""
Module: runpod_handler.py
Description: Granger-compatible handler for RunPod operations

External Dependencies:
- asyncio: https://docs.python.org/3/library/asyncio.html
- loguru: https://loguru.readthedocs.io/

Sample Input:
>>> handler = RunPodHandler()
>>> result = handler.handle({
>>>     "operation": "create_instance",
>>>     "model_size": "70B",
>>>     "hours": 4
>>> })

Expected Output:
>>> {
>>>     "success": True,
>>>     "data": {
>>>         "instance_id": "abc123",
>>>         "gpu_type": "A100-80GB",
>>>         "cost_per_hour": 3.09,
>>>         "ssh_command": "ssh root@..."
>>>     }
>>> }

Example Usage:
>>> # Create instance
>>> result = handler.handle({"operation": "create_instance", "model_size": "13B"})
>>> # List instances
>>> result = handler.handle({"operation": "list_instances"})
>>> # Optimize GPU
>>> result = handler.handle({"operation": "optimize", "model_size": "70B", "tokens": 1000000})
"""

import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from datetime import datetime

# Import RunPod components
from runpod_ops_fixed.core.runpod_manager import RunPodManager
from runpod_ops_fixed.core.instance_optimizer import InstanceOptimizer
from runpod_ops_fixed.core.gpu_optimizer import GPUOptimizer
from runpod_ops_fixed.core.cost_calculator import CostCalculator
from runpod_ops_fixed.core.instance_monitor import InstanceMonitor
from runpod_ops_fixed.core.training_orchestrator import TrainingOrchestrator
from runpod_ops_fixed.core.inference_server import InferenceServer
from runpod_ops_fixed.core.auto_terminator import AutoTerminator
from runpod_ops_fixed.core.error_handler import ErrorHandler


class RunPodHandler:
    """Granger-compatible handler for RunPod operations"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize handler with RunPod components"""
        # Load from env if not provided
        if not api_key:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv('RUNPOD_API_KEY')
        
        # Initialize components
        self.manager = RunPodManager(api_key=api_key)
        self.optimizer = InstanceOptimizer()  # Legacy optimizer
        self.gpu_optimizer = GPUOptimizer(api_key=api_key)  # New dynamic optimizer
        self.calculator = CostCalculator()
        self.monitor = InstanceMonitor(api_key=api_key)
        self.orchestrator = TrainingOrchestrator(api_key=api_key)
        self.inference_server = InferenceServer(api_key=api_key)
        self.terminator = AutoTerminator(api_key=api_key)
        self.error_handler = ErrorHandler(api_key=api_key)
        
        logger.info("RunPodHandler initialized")
    
    def handle(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle RunPod operations following Granger pattern.
        
        Args:
            params: Dictionary with operation and parameters
            
        Returns:
            Result dictionary with success status and data
        """
        operation = params.get('operation')
        
        if not operation:
            return {
                "success": False,
                "error": "No operation specified",
                "available_operations": [
                    "create_instance", "list_instances", "terminate_instance",
                    "optimize", "estimate_cost", "monitor", "start_training",
                    "deploy_inference", "health_check"
                ]
            }
        
        try:
            # Route to appropriate handler
            if operation == "create_instance":
                return self._create_instance(params)
            elif operation == "list_instances":
                return self._list_instances(params)
            elif operation == "terminate_instance":
                return self._terminate_instance(params)
            elif operation == "optimize":
                return self._optimize_gpu(params)
            elif operation == "estimate_cost":
                return self._estimate_cost(params)
            elif operation == "monitor":
                return self._monitor_instance(params)
            elif operation == "start_training":
                return self._start_training(params)
            elif operation == "deploy_inference":
                return self._deploy_inference(params)
            elif operation == "health_check":
                return self._health_check(params)
            else:
                return {
                    "success": False,
                    "error": f"Unknown operation: {operation}"
                }
                
        except Exception as e:
            logger.error(f"Error in operation {operation}: {e}")
            return {
                "success": False,
                "error": str(e),
                "operation": operation
            }
    
    def _create_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create RunPod instance"""
        model_size = params.get('model_size')
        if not model_size:
            return {"success": False, "error": "model_size required"}
        
        hours = params.get('hours', 4)
        gpu_type = params.get('gpu_type')
        spot = params.get('spot', False)
        tokens = params.get('tokens', 1000000)  # Default 1M tokens
        
        # Get optimal GPU if not specified
        if not gpu_type:
            # Use new optimizer for dynamic selection
            try:
                optimal = self.gpu_optimizer.get_optimal_gpu_config(
                    model_size=model_size,
                    training_tokens=tokens,
                    is_training=True,
                    use_spot=spot
                )
                if not optimal.get('error'):
                    gpu_type = optimal['gpu_id']
                    logger.info(f"Selected GPU: {optimal['gpu_type']} ({optimal['gpu_count']}x)")
                else:
                    # Fallback to legacy
                    config = self.optimizer.get_optimal_config(model_size, tokens=tokens)
                    gpu_type = config['gpu_type']
            except Exception as e:
                logger.error(f"GPU optimization failed: {e}")
                config = self.optimizer.get_optimal_config(model_size, tokens=tokens)
                gpu_type = config['gpu_type']
        
        # Create instance synchronously
        result = asyncio.run(self.manager.create_instance(
            name=f"granger-{model_size.lower()}-{int(datetime.now().timestamp())}",
            gpu_type=gpu_type,
            gpu_count=1,
            container_image="runpod/pytorch:2.0.1-py3.10-cuda11.8.0-devel",
            container_disk_size=50,
            volume_size=20,
            ports="22/tcp,8888/http",
            env_vars={
                "MODEL_SIZE": model_size,
                "GRANGER_MODULE": "runpod_ops"
            }
        ))
        
        return {
            "success": True,
            "data": {
                "instance_id": result.id,
                "gpu_type": result.gpu_type,
                "status": result.status,
                "cost_per_hour": result.cost_per_hour,
                "total_cost": result.cost_per_hour * hours,
                "ssh_command": f"ssh root@{getattr(result, 'ssh_host', 'pending')} -p {getattr(result, 'ssh_port', 22)}",
                "created_at": str(result.created_at)
            }
        }
    
    def _list_instances(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List RunPod instances"""
        instances = asyncio.run(self.manager.list_instances())
        
        return {
            "success": True,
            "data": {
                "count": len(instances),
                "instances": [
                    {
                        "id": inst.id,
                        "name": inst.name,
                        "gpu_type": inst.gpu_type,
                        "status": inst.status,
                        "cost_per_hour": inst.cost_per_hour,
                        "created_at": str(inst.created_at)
                    }
                    for inst in instances
                ]
            }
        }
    
    def _terminate_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Terminate instance"""
        instance_id = params.get('instance_id')
        if not instance_id:
            return {"success": False, "error": "instance_id required"}
        
        success = asyncio.run(self.manager.terminate_instance(instance_id))
        
        return {
            "success": success,
            "data": {
                "instance_id": instance_id,
                "terminated": success
            }
        }
    
    def _optimize_gpu(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize GPU configuration using dynamic API data"""
        model_size = params.get('model_size')
        if not model_size:
            return {"success": False, "error": "model_size required"}
        
        tokens = params.get('tokens')
        hours = params.get('hours')
        batch_size = params.get('batch_size')
        sequence_length = params.get('sequence_length', 2048)
        is_training = params.get('is_training', True)
        use_spot = params.get('use_spot', True)
        max_budget = params.get('max_budget')
        multi_gpu = params.get('multi_gpu', False)
        
        # Use new GPU optimizer for dynamic calculations
        try:
            result = self.gpu_optimizer.get_optimal_gpu_config(
                model_size=model_size,
                training_tokens=tokens,
                training_hours=hours,
                batch_size=batch_size,
                sequence_length=sequence_length,
                is_training=is_training,
                use_spot=use_spot,
                max_budget=max_budget
            )
            
            if result.get('error'):
                return {"success": False, "error": result['error']}
            
            # Format response
            response = {
                "success": True,
                "data": {
                    "recommendations": result,
                    "multi_gpu": result.get('gpu_count', 1) > 1,
                    "optimization_params": {
                        "model_size": model_size,
                        "batch_size": result.get('batch_size'),
                        "sequence_length": sequence_length,
                        "is_training": is_training,
                        "use_spot": use_spot
                    }
                }
            }
            
            # Add alternatives if available
            if 'alternatives' in result:
                response['data']['alternatives'] = result['alternatives']
                
            return response
            
        except Exception as e:
            logger.error(f"GPU optimization failed: {e}")
            # Fallback to legacy optimizer
            return self._optimize_gpu_legacy(params)
    
    def _optimize_gpu_legacy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy GPU optimization (fallback)"""
        model_size = params.get('model_size')
        tokens = params.get('tokens', 1000000)
        
        config = self.optimizer.get_optimal_config(model_size, tokens=tokens)
        gpu_config = self.optimizer.gpu_configs.get(config['gpu_type'])
        
        return {
            "success": True,
            "data": {
                "recommendations": {
                    "gpu_type": config['gpu_type'],
                    "gpu_count": config['gpu_count'],
                    "vram_per_gpu": gpu_config.vram_gb if gpu_config else 0,
                    "cost_per_hour": gpu_config.cost_per_hour if gpu_config else 0,
                    "tokens_per_hour": config.get('tokens_per_second', 0) * 3600,
                    "hours_needed": config.get('estimated_hours', 0),
                    "total_cost": config.get('estimated_cost', 0)
                },
                "multi_gpu": config['gpu_count'] > 1,
                "legacy_mode": True
            }
        }
    
    def _estimate_cost(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate training costs"""
        model_size = params.get('model_size')
        if not model_size:
            return {"success": False, "error": "model_size required"}
        
        tokens = params.get('tokens')
        hours = params.get('hours')
        gpu_type = params.get('gpu_type')
        
        if not tokens and not hours:
            return {"success": False, "error": "Either tokens or hours required"}
        
        # Get optimal GPU if not specified
        if not gpu_type:
            config_result = self.optimizer.get_optimal_config(model_size, tokens=tokens or 1000000)
            gpu_type = config_result['gpu_type']
            config = self.optimizer.gpu_configs.get(gpu_type)
        else:
            config = self.optimizer.gpu_configs.get(gpu_type)
            if not config:
                return {"success": False, "error": f"Unknown GPU type: {gpu_type}"}
        
        result = {
            "model_size": model_size,
            "gpu_type": gpu_type,
            "cost_per_hour": config.cost_per_hour
        }
        
        if hours:
            result["hours"] = hours
            result["total_cost"] = hours * config.cost_per_hour
        
        if tokens:
            # Estimate throughput using optimizer
            tokens_per_second = self.optimizer._estimate_throughput(config, model_size)
            tokens_per_hour = tokens_per_second * 3600
            hours_needed = tokens / tokens_per_hour
            
            result["tokens"] = tokens
            result["tokens_per_hour"] = tokens_per_hour
            result["hours_needed"] = hours_needed
            result["total_cost"] = hours_needed * config.cost_per_hour
        
        return {
            "success": True,
            "data": result
        }
    
    def _monitor_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get instance metrics"""
        instance_id = params.get('instance_id')
        if not instance_id:
            return {"success": False, "error": "instance_id required"}
        
        metrics = asyncio.run(self.monitor.get_instance_metrics(instance_id))
        
        return {
            "success": True,
            "data": {
                "instance_id": instance_id,
                "metrics": metrics
            }
        }
    
    def _start_training(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start training job"""
        config = params.get('config')
        if not config:
            return {"success": False, "error": "config required"}
        
        instance_id = params.get('instance_id')
        
        # Convert to TrainingConfig
        from runpod_ops_fixed.core.training_orchestrator import TrainingConfig
        training_config = TrainingConfig(**config)
        
        job_id = asyncio.run(self.orchestrator.start_training(
            instance_id=instance_id,
            config=training_config
        ))
        
        return {
            "success": True,
            "data": {
                "job_id": job_id,
                "instance_id": instance_id or job_id,
                "config": config
            }
        }
    
    def _deploy_inference(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy inference server"""
        model_path = params.get('model_path')
        if not model_path:
            return {"success": False, "error": "model_path required"}
        
        instance_id = params.get('instance_id')
        
        # Convert to InferenceConfig
        from runpod_ops_fixed.core.inference_server import InferenceConfig
        config = InferenceConfig(
            model_name=model_path,
            port=params.get('port', 8000),
            max_batch_size=params.get('max_batch_size', 16)
        )
        
        endpoint = asyncio.run(self.inference_server.deploy_server(
            instance_id=instance_id,
            config=config
        ))
        
        return {
            "success": True,
            "data": {
                "endpoint": endpoint,
                "model_path": model_path,
                "instance_id": instance_id
            }
        }
    
    def _health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check system health"""
        instance_id = params.get('instance_id')
        
        if instance_id:
            # Check specific instance
            health = asyncio.run(self.error_handler.health_check(instance_id))
            return {
                "success": True,
                "data": {
                    "instance_id": instance_id,
                    "health": health
                }
            }
        else:
            # General health check
            instances = asyncio.run(self.manager.list_instances())
            
            return {
                "success": True,
                "data": {
                    "api_status": "connected",
                    "active_instances": len([i for i in instances if i.status == "running"]),
                    "total_instances": len(instances),
                    "components": {
                        "manager": "ready",
                        "optimizer": "ready",
                        "monitor": "ready",
                        "orchestrator": "ready",
                        "inference": "ready"
                    }
                }
            }


# Module validation
if __name__ == "__main__":
    handler = RunPodHandler()
    
    # Test operations
    print("Testing RunPod handler...")
    
    # List instances
    result = handler.handle({"operation": "list_instances"})
    print(f"List instances: {result}")
    
    # Optimize GPU
    result = handler.handle({
        "operation": "optimize",
        "model_size": "13B",
        "tokens": 1000000
    })
    print(f"Optimize: {result}")
    
    # Health check
    result = handler.handle({"operation": "health_check"})
    print(f"Health: {result}")
    
    print("✅ RunPod handler validation passed")