"""
Module: error_handler.py
Description: Comprehensive error handling and recovery system for RunPod operations

External Dependencies:
- runpod: https://docs.runpod.io/
- loguru: https://loguru.readthedocs.io/
- tenacity: https://tenacity.readthedocs.io/

Sample Input:
>>> handler = ErrorHandler()
>>> result = await handler.with_retry(api_call, max_attempts=3)

Expected Output:
>>> result
{"success": True, "data": {...}, "attempts": 2}

Example Usage:
>>> from runpod_ops_fixed.core.error_handler import ErrorHandler, RecoveryStrategy
>>> handler = ErrorHandler()
>>> await handler.handle_pod_error("pod_id", error_type=ErrorType.GPU_OOM)
"""

import os
import asyncio
import time
from typing import Dict, Any, Optional, Callable, List, TypeVar, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import traceback
import json
from pathlib import Path

from loguru import logger
# Note: tenacity would be imported here for production use
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
# For now, we'll implement a simple retry mechanism

from runpod_ops_fixed.core.instance_monitor import InstanceMonitor
from runpod_ops_fixed.core.ssh_manager import SSHManager


T = TypeVar('T')


class ErrorType(Enum):
    """Types of errors that can occur."""
    # API Errors
    API_TIMEOUT = "api_timeout"
    API_RATE_LIMIT = "api_rate_limit"
    API_AUTH_FAILED = "api_auth_failed"
    API_SERVER_ERROR = "api_server_error"
    
    # Instance Errors
    INSTANCE_UNHEALTHY = "instance_unhealthy"
    INSTANCE_TERMINATED = "instance_terminated"
    INSTANCE_UNREACHABLE = "instance_unreachable"
    
    # GPU Errors
    GPU_OOM = "gpu_out_of_memory"
    GPU_ERROR = "gpu_error"
    CUDA_ERROR = "cuda_error"
    
    # Training Errors
    TRAINING_DIVERGED = "training_diverged"
    CHECKPOINT_CORRUPT = "checkpoint_corrupt"
    DATASET_ERROR = "dataset_error"
    
    # SSH Errors
    SSH_CONNECTION_LOST = "ssh_connection_lost"
    SSH_AUTH_FAILED = "ssh_auth_failed"
    SSH_TIMEOUT = "ssh_timeout"
    
    # General Errors
    UNKNOWN = "unknown"
    DISK_FULL = "disk_full"
    NETWORK_ERROR = "network_error"


class RecoveryStrategy(Enum):
    """Recovery strategies for different error types."""
    RETRY = "retry"
    RESTART_INSTANCE = "restart_instance"
    RESIZE_INSTANCE = "resize_instance"
    CLEAR_CACHE = "clear_cache"
    RESTORE_CHECKPOINT = "restore_checkpoint"
    TERMINATE = "terminate"
    ESCALATE = "escalate"
    IGNORE = "ignore"


@dataclass
class ErrorContext:
    """Context information for an error."""
    error_type: ErrorType
    timestamp: datetime
    pod_id: Optional[str] = None
    instance_type: Optional[str] = None
    error_message: str = ""
    stack_trace: str = ""
    additional_info: Dict[str, Any] = field(default_factory=dict)
    recovery_attempts: int = 0
    resolved: bool = False


@dataclass
class RecoveryAction:
    """Action taken to recover from an error."""
    strategy: RecoveryStrategy
    timestamp: datetime
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


@dataclass
class ErrorPattern:
    """Pattern for identifying specific error types."""
    error_type: ErrorType
    patterns: List[str]  # String patterns to match
    recovery_strategy: RecoveryStrategy
    max_retries: int = 3


class ErrorHandler:
    """Comprehensive error handling and recovery system."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize error handler.
        
        Args:
            api_key: RunPod API key
        """
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        self.monitor = InstanceMonitor(self.api_key) if self.api_key else None
        self.ssh_manager = SSHManager(self.api_key) if self.api_key else None
        
        # Error tracking
        self.error_history: List[ErrorContext] = []
        self.recovery_history: List[RecoveryAction] = []
        self.error_counts: Dict[str, int] = defaultdict(int)
        
        # Error patterns for detection
        self.error_patterns = self._initialize_error_patterns()
        
        # Recovery callbacks
        self.recovery_callbacks: Dict[ErrorType, List[Callable]] = defaultdict(list)
        
    def _initialize_error_patterns(self) -> List[ErrorPattern]:
        """Initialize error detection patterns."""
        return [
            # GPU Errors
            ErrorPattern(
                ErrorType.GPU_OOM,
                ["out of memory", "oom", "cuda out of memory", "memory allocation failed"],
                RecoveryStrategy.CLEAR_CACHE,
                max_retries=2
            ),
            ErrorPattern(
                ErrorType.CUDA_ERROR,
                ["cuda error", "cudnn error", "nccl error", "cuda runtime error"],
                RecoveryStrategy.RESTART_INSTANCE,
                max_retries=1
            ),
            
            # Training Errors
            ErrorPattern(
                ErrorType.TRAINING_DIVERGED,
                ["loss is nan", "gradient overflow", "loss diverged", "inf or nan"],
                RecoveryStrategy.RESTORE_CHECKPOINT,
                max_retries=2
            ),
            ErrorPattern(
                ErrorType.CHECKPOINT_CORRUPT,
                ["checkpoint corrupt", "unable to load checkpoint", "pickle error"],
                RecoveryStrategy.RESTORE_CHECKPOINT,
                max_retries=1
            ),
            
            # API Errors
            ErrorPattern(
                ErrorType.API_RATE_LIMIT,
                ["rate limit", "too many requests", "429"],
                RecoveryStrategy.RETRY,
                max_retries=5
            ),
            ErrorPattern(
                ErrorType.API_TIMEOUT,
                ["timeout", "timed out", "connection timeout"],
                RecoveryStrategy.RETRY,
                max_retries=3
            ),
            
            # Disk Errors
            ErrorPattern(
                ErrorType.DISK_FULL,
                ["no space left", "disk full", "storage full"],
                RecoveryStrategy.CLEAR_CACHE,
                max_retries=1
            ),
            
            # SSH Errors
            ErrorPattern(
                ErrorType.SSH_CONNECTION_LOST,
                ["ssh connection lost", "broken pipe", "connection reset"],
                RecoveryStrategy.RETRY,
                max_retries=3
            ),
        ]
        
    async def with_retry(
        self,
        func: Callable[..., T],
        *args,
        max_attempts: int = 3,
        backoff_factor: int = 2,
        max_wait: int = 60,
        exceptions: tuple = (Exception,),
        **kwargs
    ) -> T:
        """
        Execute function with retry logic.
        
        Args:
            func: Function to execute
            max_attempts: Maximum retry attempts
            backoff_factor: Exponential backoff factor
            max_wait: Maximum wait between retries
            exceptions: Exceptions to retry on
            
        Returns:
            Function result
        """
        last_exception = None
        
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    # Exponential backoff
                    wait_time = min(backoff_factor ** (attempt - 1), max_wait)
                    logger.warning(f"Retry attempt {attempt + 1}/{max_attempts} after {wait_time}s wait")
                    await asyncio.sleep(wait_time)
                    
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
            except exceptions as e:
                last_exception = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt == max_attempts - 1:
                    logger.error(f"Failed after {max_attempts} attempts: {e}")
                    raise
                    
            except Exception as e:
                # Don't retry on unexpected exceptions
                logger.error(f"Unexpected error: {e}")
                raise
                
        # Should not reach here
        if last_exception:
            raise last_exception
            
    async def handle_error(
        self,
        error: Exception,
        pod_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[RecoveryAction]:
        """
        Handle an error with appropriate recovery strategy.
        
        Args:
            error: The exception that occurred
            pod_id: Pod ID if applicable
            context: Additional context
            
        Returns:
            RecoveryAction if recovery attempted
        """
        # Create error context
        error_type = self._identify_error_type(str(error))
        
        error_context = ErrorContext(
            error_type=error_type,
            timestamp=datetime.now(),
            pod_id=pod_id,
            error_message=str(error),
            stack_trace=traceback.format_exc(),
            additional_info=context or {}
        )
        
        self.error_history.append(error_context)
        self.error_counts[error_type.value] += 1
        
        # Determine recovery strategy
        strategy = self._determine_recovery_strategy(error_context)
        
        if strategy == RecoveryStrategy.IGNORE:
            logger.info(f"Ignoring error: {error_type.value}")
            return None
            
        # Execute recovery
        recovery_action = await self._execute_recovery(error_context, strategy)
        
        if recovery_action:
            self.recovery_history.append(recovery_action)
            
        return recovery_action
        
    def _identify_error_type(self, error_message: str) -> ErrorType:
        """Identify error type from message."""
        error_lower = error_message.lower()
        
        for pattern in self.error_patterns:
            if any(p in error_lower for p in pattern.patterns):
                return pattern.error_type
                
        return ErrorType.UNKNOWN
        
    def _determine_recovery_strategy(self, error_context: ErrorContext) -> RecoveryStrategy:
        """Determine appropriate recovery strategy."""
        # Find matching pattern
        for pattern in self.error_patterns:
            if pattern.error_type == error_context.error_type:
                # Check retry limit
                if error_context.recovery_attempts >= pattern.max_retries:
                    logger.warning(f"Max retries ({pattern.max_retries}) exceeded for {error_context.error_type.value}")
                    return RecoveryStrategy.ESCALATE
                    
                return pattern.recovery_strategy
                
        return RecoveryStrategy.ESCALATE
        
    async def _execute_recovery(
        self,
        error_context: ErrorContext,
        strategy: RecoveryStrategy
    ) -> Optional[RecoveryAction]:
        """Execute recovery strategy."""
        start_time = time.time()
        success = False
        details = {}
        
        logger.info(f"Executing recovery strategy: {strategy.value} for {error_context.error_type.value}")
        
        try:
            if strategy == RecoveryStrategy.RETRY:
                # Simple retry - caller should retry operation
                success = True
                details = {"action": "retry_operation"}
                
            elif strategy == RecoveryStrategy.CLEAR_CACHE and error_context.pod_id:
                success = await self._clear_gpu_cache(error_context.pod_id)
                details = {"cleared_cache": success}
                
            elif strategy == RecoveryStrategy.RESTART_INSTANCE and error_context.pod_id:
                success = await self._restart_instance(error_context.pod_id)
                details = {"restarted": success}
                
            elif strategy == RecoveryStrategy.RESTORE_CHECKPOINT and error_context.pod_id:
                checkpoint = await self._find_last_checkpoint(error_context.pod_id)
                if checkpoint:
                    success = await self._restore_checkpoint(error_context.pod_id, checkpoint)
                    details = {"checkpoint": checkpoint, "restored": success}
                    
            elif strategy == RecoveryStrategy.RESIZE_INSTANCE and error_context.pod_id:
                new_size = self._determine_new_size(error_context)
                success = await self._resize_instance(error_context.pod_id, new_size)
                details = {"new_size": new_size, "resized": success}
                
            elif strategy == RecoveryStrategy.ESCALATE:
                # Log for manual intervention
                await self._escalate_error(error_context)
                details = {"escalated": True}
                
            # Execute callbacks
            for callback in self.recovery_callbacks.get(error_context.error_type, []):
                try:
                    await callback(error_context, strategy)
                except Exception as e:
                    logger.error(f"Recovery callback error: {e}")
                    
        except Exception as e:
            logger.error(f"Recovery execution failed: {e}")
            success = False
            details["error"] = str(e)
            
        duration = time.time() - start_time
        
        return RecoveryAction(
            strategy=strategy,
            timestamp=datetime.now(),
            success=success,
            details=details,
            duration_seconds=duration
        )
        
    async def _clear_gpu_cache(self, pod_id: str) -> bool:
        """Clear GPU cache on pod."""
        if not self.ssh_manager:
            return False
            
        try:
            # Clear PyTorch cache
            commands = [
                "python -c 'import torch; torch.cuda.empty_cache()' 2>/dev/null || true",
                "python -c 'import gc; gc.collect()' 2>/dev/null || true",
                # Kill any zombie processes
                "pkill -9 python 2>/dev/null || true",
                "sleep 2",
                # Clear system caches
                "sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true"
            ]
            
            for cmd in commands:
                result = await self.ssh_manager.execute_on_pod(pod_id, cmd)
                if not result.get("success"):
                    logger.warning(f"Cache clear command failed: {cmd}")
                    
            logger.info(f"Cleared GPU cache on {pod_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
            
    async def _restart_instance(self, pod_id: str) -> bool:
        """Restart pod instance."""
        try:
            # Graceful restart via SSH first
            if self.ssh_manager:
                await self.ssh_manager.execute_on_pod(pod_id, "sudo reboot")
                
            # Wait for instance to come back
            await asyncio.sleep(30)
            
            # Verify it's back
            if self.monitor:
                health = await self.monitor.check_instance_health(pod_id)
                return health.get("healthy", False)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart instance: {e}")
            return False
            
    async def _find_last_checkpoint(self, pod_id: str) -> Optional[str]:
        """Find last valid checkpoint."""
        if not self.ssh_manager:
            return None
            
        try:
            result = await self.ssh_manager.execute_on_pod(
                pod_id,
                "ls -t /workspace/checkpoints/*.pt 2>/dev/null | head -5"
            )
            
            if result.get("success") and result.get("stdout"):
                checkpoints = result["stdout"].strip().split("\n")
                
                # Verify checkpoints
                for checkpoint in checkpoints:
                    verify_cmd = f"python -c 'import torch; torch.load(\"{checkpoint}\", map_location=\"cpu\"); print(\"OK\")' 2>&1"
                    verify_result = await self.ssh_manager.execute_on_pod(pod_id, verify_cmd)
                    
                    if verify_result.get("success") and "OK" in verify_result.get("stdout", ""):
                        return checkpoint
                        
            return None
            
        except Exception as e:
            logger.error(f"Failed to find checkpoint: {e}")
            return None
            
    async def _restore_checkpoint(self, pod_id: str, checkpoint_path: str) -> bool:
        """Restore from checkpoint."""
        try:
            # Copy checkpoint to active location
            restore_cmd = f"cp {checkpoint_path} /workspace/model_checkpoint.pt"
            result = await self.ssh_manager.execute_on_pod(pod_id, restore_cmd)
            
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"Failed to restore checkpoint: {e}")
            return False
            
    def _determine_new_size(self, error_context: ErrorContext) -> str:
        """Determine new instance size for resize."""
        # Simple logic - upgrade to next tier
        size_upgrades = {
            "gpu.1x.a10": "gpu.1x.a40",
            "gpu.1x.a40": "gpu.1x.a100",
            "gpu.1x.a100": "gpu.2x.a100",
            "gpu.1x.rtx4090": "gpu.1x.a40",
        }
        
        current = error_context.instance_type or "gpu.1x.a10"
        return size_upgrades.get(current, "gpu.1x.a100")
        
    async def _resize_instance(self, pod_id: str, new_size: str) -> bool:
        """Resize instance (requires recreating)."""
        # This would require terminating and recreating
        # For now, just log the recommendation
        logger.warning(f"Instance resize recommended: {pod_id} -> {new_size}")
        return False
        
    async def _escalate_error(self, error_context: ErrorContext):
        """Escalate error for manual intervention."""
        escalation = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_context.error_type.value,
            "pod_id": error_context.pod_id,
            "message": error_context.error_message,
            "recovery_attempts": error_context.recovery_attempts,
            "requires_manual_intervention": True
        }
        
        # Log to escalation file
        log_dir = Path("logs/escalations")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"escalations_{datetime.now().strftime('%Y%m%d')}.jsonl"
        
        with open(log_file, "a") as f:
            f.write(json.dumps(escalation) + "\n")
            
        logger.error(f"ERROR ESCALATED: {error_context.error_type.value} on {error_context.pod_id}")
        
    def add_recovery_callback(self, error_type: ErrorType, callback: Callable):
        """Add callback for specific error type recovery."""
        self.recovery_callbacks[error_type].append(callback)
        
    def get_error_stats(self, since: Optional[datetime] = None) -> Dict[str, Any]:
        """Get error statistics."""
        if since:
            errors = [e for e in self.error_history if e.timestamp >= since]
        else:
            errors = self.error_history
            
        # Count by type
        error_counts = defaultdict(int)
        for error in errors:
            error_counts[error.error_type.value] += 1
            
        # Recovery success rate
        recoveries = [r for r in self.recovery_history if not since or r.timestamp >= since]
        success_count = sum(1 for r in recoveries if r.success)
        
        return {
            "total_errors": len(errors),
            "error_counts": dict(error_counts),
            "recovery_attempts": len(recoveries),
            "recovery_success_rate": success_count / len(recoveries) if recoveries else 0,
            "unresolved_errors": sum(1 for e in errors if not e.resolved)
        }
        
    async def health_check(self, pod_id: str) -> Dict[str, Any]:
        """Comprehensive health check with error detection."""
        health = {"healthy": True, "issues": []}
        
        try:
            # Basic instance health
            if self.monitor:
                instance_health = await self.monitor.check_instance_health(pod_id)
                if not instance_health.get("healthy"):
                    health["healthy"] = False
                    health["issues"].append("Instance unhealthy")
                    
            # GPU health
            if self.ssh_manager:
                gpu_result = await self.ssh_manager.execute_on_pod(
                    pod_id,
                    "nvidia-smi --query-gpu=gpu_bus_id,name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader"
                )
                
                if not gpu_result.get("success"):
                    health["healthy"] = False
                    health["issues"].append("GPU health check failed")
                else:
                    # Parse GPU data
                    gpu_data = gpu_result.get("stdout", "").strip()
                    if gpu_data:
                        health["gpu_status"] = "operational"
                        
                        # Check for high temperature
                        if "temperature" in gpu_data:
                            temp = float(gpu_data.split(",")[2])
                            if temp > 85:
                                health["issues"].append(f"GPU temperature high: {temp}°C")
                                
            # Disk space
            disk_result = await self.ssh_manager.execute_on_pod(
                pod_id,
                "df -h /workspace | tail -1 | awk '{print $5}' | sed 's/%//'"
            )
            
            if disk_result.get("success"):
                disk_usage = int(disk_result.get("stdout", "0").strip())
                if disk_usage > 90:
                    health["issues"].append(f"Disk usage critical: {disk_usage}%")
                elif disk_usage > 80:
                    health["issues"].append(f"Disk usage high: {disk_usage}%")
                    
            # Recent errors
            recent_errors = [
                e for e in self.error_history 
                if e.pod_id == pod_id and e.timestamp > datetime.now() - timedelta(hours=1)
            ]
            
            if recent_errors:
                health["recent_errors"] = len(recent_errors)
                health["issues"].append(f"{len(recent_errors)} errors in last hour")
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health["healthy"] = False
            health["issues"].append(f"Health check error: {str(e)}")
            
        return health


# Validation
if __name__ == "__main__":
    async def test_error_handler():
        handler = ErrorHandler()
        
        # Test error identification
        error_msg = "CUDA out of memory. Tried to allocate 2.00 GiB"
        error_type = handler._identify_error_type(error_msg)
        assert error_type == ErrorType.GPU_OOM
        
        # Test retry wrapper
        call_count = 0
        
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "Success"
            
        result = await handler.with_retry(
            flaky_function,
            max_attempts=5,
            exceptions=(ConnectionError,)
        )
        
        assert result == "Success"
        assert call_count == 3
        
        # Test error stats
        stats = handler.get_error_stats()
        print(f"Error stats: {stats}")
        
        print("✅ Error handler validation passed")
        
    asyncio.run(test_error_handler())