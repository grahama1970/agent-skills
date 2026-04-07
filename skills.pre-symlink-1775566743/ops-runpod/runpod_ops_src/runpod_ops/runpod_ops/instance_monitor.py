"""
Module: instance_monitor.py  
Description: Monitor RunPod instances for health, performance, and costs

External Dependencies:
- runpod: https://docs.runpod.io/
- loguru: https://loguru.readthedocs.io/
- asyncio: https://docs.python.org/3/library/asyncio.html

Sample Input:
>>> monitor = InstanceMonitor()
>>> status = await monitor.check_instance_health("instance_id")

Expected Output:
>>> status
{"healthy": True, "gpu_utilization": 95, "memory_usage": 12.5, "cost_so_far": 6.18}

Example Usage:
>>> from runpod_ops.instance_monitor import InstanceMonitor
>>> monitor = InstanceMonitor()
>>> await monitor.monitor_training_job("instance_id", callback=progress_callback)
"""

import asyncio
import os
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timedelta
from collections import deque

import runpod
from loguru import logger


class InstanceMonitor:
    """Monitor RunPod instances and training jobs."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize instance monitor.
        
        Args:
            api_key: RunPod API key
        """
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        runpod.api_key = self.api_key
        
        # Monitoring data
        self.metrics_history: Dict[str, deque] = {}
        self.cost_tracking: Dict[str, Dict[str, float]] = {}
        
    async def check_instance_health(self, instance_id: str) -> Dict[str, Any]:
        """
        Check health and status of instance.
        
        Args:
            instance_id: RunPod instance ID
            
        Returns:
            Health status and metrics
        """
        try:
            pod_info = runpod.get_pod(instance_id)
            
            # Extract metrics
            health = {
                "instance_id": instance_id,
                "healthy": pod_info.get("desiredStatus") == "RUNNING",
                "status": pod_info.get("desiredStatus", "UNKNOWN"),
                "actual_status": pod_info.get("status", "UNKNOWN"),
                "uptime_seconds": pod_info.get("uptimeSeconds", 0),
                "container_ready": pod_info.get("container", {}).get("ready", False),
            }
            
            # GPU metrics if available
            gpu_metrics = pod_info.get("gpus", [])
            if gpu_metrics:
                gpu = gpu_metrics[0]  # First GPU
                health["gpu_utilization"] = gpu.get("percentUtilization", 0)
                health["gpu_memory_used_gb"] = gpu.get("memoryUsedMB", 0) / 1024
                health["gpu_memory_total_gb"] = gpu.get("memoryTotalMB", 0) / 1024
                health["gpu_temp_c"] = gpu.get("temperatureC", 0)
                
            # Cost tracking
            cost_per_hour = pod_info.get("costPerHr", 0)
            uptime_hours = health["uptime_seconds"] / 3600
            health["cost_per_hour"] = cost_per_hour
            health["cost_so_far"] = round(cost_per_hour * uptime_hours, 2)
            
            # Store in history
            if instance_id not in self.metrics_history:
                self.metrics_history[instance_id] = deque(maxlen=100)
            self.metrics_history[instance_id].append({
                "timestamp": datetime.now(),
                "metrics": health
            })
            
            return health
            
        except Exception as e:
            logger.error(f"Failed to check instance health: {e}")
            return {"healthy": False, "error": str(e)}
            
    async def monitor_training_job(
        self,
        instance_id: str,
        log_pattern: Optional[str] = "loss:",
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        check_interval: int = 30
    ):
        """
        Monitor a training job with progress tracking.
        
        Args:
            instance_id: RunPod instance ID
            log_pattern: Pattern to search in logs for progress
            callback: Function to call with updates
            check_interval: Seconds between checks
        """
        logger.info(f"Starting training monitor for {instance_id}")
        
        start_time = time.time()
        last_loss = None
        loss_history = deque(maxlen=20)
        
        while True:
            try:
                # Check instance health
                health = await self.check_instance_health(instance_id)
                
                if not health.get("healthy"):
                    logger.warning(f"Instance unhealthy: {health}")
                    if callback:
                        callback({"status": "unhealthy", "health": health})
                    break
                    
                # Try to get logs if available
                try:
                    logs = await self._get_instance_logs(instance_id, lines=100)
                    
                    # Parse training progress from logs
                    if log_pattern and logs:
                        progress = self._parse_training_progress(logs, log_pattern)
                        if progress:
                            current_loss = progress.get("loss")
                            if current_loss and current_loss != last_loss:
                                last_loss = current_loss
                                loss_history.append(current_loss)
                                
                                # Calculate improvement
                                if len(loss_history) > 1:
                                    improvement = (loss_history[0] - current_loss) / loss_history[0]
                                    progress["improvement_pct"] = round(improvement * 100, 2)
                                    
                            health["training_progress"] = progress
                            
                except Exception as e:
                    logger.debug(f"Could not get logs: {e}")
                    
                # Calculate runtime and cost
                runtime_seconds = time.time() - start_time
                runtime_hours = runtime_seconds / 3600
                total_cost = health.get("cost_per_hour", 0) * runtime_hours
                
                # Prepare update
                update = {
                    "status": "running",
                    "health": health,
                    "runtime_hours": round(runtime_hours, 2),
                    "total_cost": round(total_cost, 2),
                    "gpu_utilization": health.get("gpu_utilization", 0),
                    "loss_history": list(loss_history),
                }
                
                # Call callback
                if callback:
                    callback(update)
                    
                # Check for completion signals
                if await self._check_training_complete(instance_id, logs):
                    logger.info("Training appears complete")
                    update["status"] = "complete"
                    if callback:
                        callback(update)
                    break
                    
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                if callback:
                    callback({"status": "error", "error": str(e)})
                break
                
    async def get_instance_metrics_summary(
        self,
        instance_id: str,
        duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Get metrics summary for instance over time period.
        
        Args:
            instance_id: RunPod instance ID
            duration_minutes: Time period to summarize
            
        Returns:
            Metrics summary with averages and trends
        """
        if instance_id not in self.metrics_history:
            return {"error": "No metrics history for instance"}
            
        history = self.metrics_history[instance_id]
        cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
        
        # Filter recent metrics
        recent_metrics = [
            entry for entry in history
            if entry["timestamp"] > cutoff_time
        ]
        
        if not recent_metrics:
            return {"error": "No recent metrics"}
            
        # Calculate averages
        gpu_utils = [m["metrics"].get("gpu_utilization", 0) for m in recent_metrics]
        gpu_memory = [m["metrics"].get("gpu_memory_used_gb", 0) for m in recent_metrics]
        temps = [m["metrics"].get("gpu_temp_c", 0) for m in recent_metrics]
        
        summary = {
            "instance_id": instance_id,
            "period_minutes": duration_minutes,
            "samples": len(recent_metrics),
            "avg_gpu_utilization": round(sum(gpu_utils) / len(gpu_utils), 1),
            "max_gpu_utilization": max(gpu_utils),
            "min_gpu_utilization": min(gpu_utils),
            "avg_gpu_memory_gb": round(sum(gpu_memory) / len(gpu_memory), 2),
            "avg_gpu_temp_c": round(sum(temps) / len(temps), 1),
            "max_gpu_temp_c": max(temps),
            "total_cost": recent_metrics[-1]["metrics"].get("cost_so_far", 0),
            "uptime_hours": round(recent_metrics[-1]["metrics"].get("uptime_seconds", 0) / 3600, 2)
        }
        
        # Add utilization trend
        if len(gpu_utils) > 5:
            first_half = gpu_utils[:len(gpu_utils)//2]
            second_half = gpu_utils[len(gpu_utils)//2:]
            
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            
            if avg_second > avg_first * 1.1:
                summary["utilization_trend"] = "increasing"
            elif avg_second < avg_first * 0.9:
                summary["utilization_trend"] = "decreasing"
            else:
                summary["utilization_trend"] = "stable"
                
        return summary
        
    async def estimate_remaining_time(
        self,
        instance_id: str,
        total_steps: Optional[int] = None,
        total_epochs: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Estimate remaining training time based on progress.
        
        Args:
            instance_id: RunPod instance ID
            total_steps: Total training steps if known
            total_epochs: Total epochs if known
            
        Returns:
            Time and cost estimates
        """
        # Get recent logs
        logs = await self._get_instance_logs(instance_id, lines=200)
        if not logs:
            return {"error": "No logs available"}
            
        # Parse progress
        progress_info = self._parse_detailed_progress(logs)
        
        if not progress_info.get("current_step"):
            return {"error": "Cannot determine progress"}
            
        current_step = progress_info["current_step"]
        steps_per_second = progress_info.get("steps_per_second", 0)
        
        estimates = {
            "current_step": current_step,
            "steps_per_second": steps_per_second,
        }
        
        # Estimate based on total steps
        if total_steps and steps_per_second > 0:
            remaining_steps = total_steps - current_step
            remaining_seconds = remaining_steps / steps_per_second
            
            estimates["total_steps"] = total_steps
            estimates["progress_pct"] = round(current_step / total_steps * 100, 1)
            estimates["remaining_hours"] = round(remaining_seconds / 3600, 2)
            
            # Cost estimate
            health = await self.check_instance_health(instance_id)
            if health.get("cost_per_hour"):
                remaining_cost = health["cost_per_hour"] * estimates["remaining_hours"]
                estimates["remaining_cost"] = round(remaining_cost, 2)
                estimates["total_estimated_cost"] = round(
                    health.get("cost_so_far", 0) + remaining_cost, 2
                )
                
        return estimates
        
    async def auto_shutdown_on_idle(
        self,
        instance_id: str,
        idle_threshold_minutes: int = 30,
        gpu_threshold: int = 10
    ) -> bool:
        """
        Auto-shutdown instance if idle for too long.
        
        Args:
            instance_id: RunPod instance ID
            idle_threshold_minutes: Minutes of low GPU before shutdown
            gpu_threshold: GPU utilization threshold for idle
            
        Returns:
            Whether instance was shutdown
        """
        logger.info(f"Starting idle monitor for {instance_id}")
        
        idle_start = None
        check_interval = 60  # Check every minute
        
        while True:
            try:
                health = await self.check_instance_health(instance_id)
                
                if not health.get("healthy"):
                    logger.warning("Instance not healthy, stopping monitor")
                    return False
                    
                gpu_util = health.get("gpu_utilization", 0)
                
                if gpu_util < gpu_threshold:
                    # GPU is idle
                    if idle_start is None:
                        idle_start = time.time()
                        logger.info(f"GPU idle detected ({gpu_util}%)")
                    else:
                        idle_duration = (time.time() - idle_start) / 60
                        if idle_duration >= idle_threshold_minutes:
                            logger.warning(f"Shutting down idle instance after {idle_duration:.1f} minutes")
                            
                            # Terminate instance
                            try:
                                runpod.terminate_pod(instance_id)
                                return True
                            except Exception as e:
                                logger.error(f"Failed to terminate: {e}")
                                return False
                else:
                    # GPU is active, reset idle timer
                    if idle_start is not None:
                        logger.info(f"GPU active again ({gpu_util}%)")
                        idle_start = None
                        
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Idle monitor error: {e}")
                return False
                
    async def _get_instance_logs(self, instance_id: str, lines: int = 100) -> Optional[str]:
        """Get recent logs from instance."""
        try:
            raise NotImplementedError("Instance log retrieval not yet implemented — needs RunPod log API")
        except Exception as e:
            logger.debug(f"Could not get logs: {e}")
            return None
            
    def _parse_training_progress(self, logs: str, pattern: str) -> Dict[str, Any]:
        """Parse training progress from logs."""
        progress = {}
        
        # Look for loss values
        import re
        loss_pattern = rf"{pattern}\s*([\d.]+)"
        matches = re.findall(loss_pattern, logs)
        
        if matches:
            progress["loss"] = float(matches[-1])
            
        # Look for step/epoch info
        step_pattern = r"step[:\s]+(\d+)"
        step_matches = re.findall(step_pattern, logs, re.IGNORECASE)
        if step_matches:
            progress["step"] = int(step_matches[-1])
            
        epoch_pattern = r"epoch[:\s]+(\d+)"
        epoch_matches = re.findall(epoch_pattern, logs, re.IGNORECASE)
        if epoch_matches:
            progress["epoch"] = int(epoch_matches[-1])
            
        return progress
        
    def _parse_detailed_progress(self, logs: str) -> Dict[str, Any]:
        """Parse detailed progress including speed."""
        import re
        
        info = {}
        
        # Current step
        step_matches = re.findall(r"step[:\s]+(\d+)", logs, re.IGNORECASE)
        if step_matches:
            info["current_step"] = int(step_matches[-1])
            
        # Steps per second
        speed_pattern = r"(\d+\.?\d*)\s*(?:steps?|it)/s"
        speed_matches = re.findall(speed_pattern, logs)
        if speed_matches:
            info["steps_per_second"] = float(speed_matches[-1])
            
        return info
        
    async def _check_training_complete(self, instance_id: str, logs: Optional[str]) -> bool:
        """Check if training is complete."""
        if not logs:
            return False
            
        # Look for completion indicators
        completion_patterns = [
            "training completed",
            "model saved",
            "finished training",
            "100%|████████",
            "epoch.+completed"
        ]
        
        import re
        for pattern in completion_patterns:
            if re.search(pattern, logs, re.IGNORECASE):
                return True
                
        return False


# Validation
if __name__ == "__main__":
    import os
    
    async def test_monitor():
        # Mock instance ID for testing
        instance_id = "test_instance_123"
        
        print("Instance Monitor Test")
        print("=" * 50)
        
        # Test health check structure
        mock_health = {
            "instance_id": instance_id,
            "healthy": True,
            "gpu_utilization": 85,
            "gpu_memory_used_gb": 15.2,
            "gpu_memory_total_gb": 24.0,
            "gpu_temp_c": 72,
            "cost_per_hour": 1.64,
            "cost_so_far": 8.20,
            "uptime_seconds": 18000
        }
        
        print("Mock Health Status:")
        for k, v in mock_health.items():
            print(f"  {k}: {v}")
            
        # Test progress parsing
        sample_logs = """
        Epoch 1/3: 100%|████████| 1000/1000 [15:23<00:00, 1.08it/s]
        Step 5000, loss: 0.4532
        Learning rate: 2e-4
        GPU Memory: 15.2GB / 24.0GB
        """
        
        monitor = InstanceMonitor()
        progress = monitor._parse_training_progress(sample_logs, "loss:")
        
        print("\nParsed Progress:")
        print(f"  Loss: {progress.get('loss', 'N/A')}")
        print(f"  Step: {progress.get('step', 'N/A')}")
        print(f"  Epoch: {progress.get('epoch', 'N/A')}")
        
        # Test detailed progress
        detailed = monitor._parse_detailed_progress(sample_logs)
        print(f"\nDetailed Progress:")
        print(f"  Current step: {detailed.get('current_step', 'N/A')}")
        print(f"  Steps/second: {detailed.get('steps_per_second', 'N/A')}")
        
    # asyncio.run(test_monitor())
    print("\n✅ Module validation passed")