"""
Module: auto_terminator.py
Description: Automatic instance termination based on various conditions

External Dependencies:
- runpod: https://docs.runpod.io/
- loguru: https://loguru.readthedocs.io/
- asyncio: https://docs.python.org/3/library/asyncio.html

Sample Input:
>>> terminator = AutoTerminator()
>>> policy = await terminator.create_policy("pod_id", idle_minutes=30, gpu_threshold=10)

Expected Output:
>>> policy
{"policy_id": "term_123", "status": "active", "conditions": {...}}

Example Usage:
>>> from runpod_ops_fixed.core.auto_terminator import AutoTerminator
>>> terminator = AutoTerminator()
>>> await terminator.enable_cost_limit("pod_id", max_cost=50.0)
"""

import os
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

import runpod
from loguru import logger

from runpod_ops_fixed.core.instance_monitor import InstanceMonitor
from runpod_ops_fixed.core.ssh_manager import SSHManager


class TerminationReason(Enum):
    """Reasons for instance termination."""
    IDLE = "idle"
    COST_LIMIT = "cost_limit"
    TIME_LIMIT = "time_limit"
    TRAINING_COMPLETE = "training_complete"
    ERROR_THRESHOLD = "error_threshold"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


@dataclass
class TerminationPolicy:
    """Termination policy configuration."""
    policy_id: str
    pod_id: str
    created_at: datetime
    
    # Idle termination
    idle_enabled: bool = False
    idle_threshold_minutes: int = 30
    gpu_threshold_percent: int = 10
    
    # Cost termination
    cost_limit_enabled: bool = False
    max_cost: float = 0.0
    
    # Time termination
    time_limit_enabled: bool = False
    max_runtime_hours: int = 0
    scheduled_termination: Optional[datetime] = None
    
    # Training termination
    training_complete_enabled: bool = False
    completion_markers: List[str] = field(default_factory=list)
    
    # Error termination
    error_threshold_enabled: bool = False
    max_consecutive_errors: int = 5
    error_count: int = 0
    
    # State
    is_active: bool = True
    last_check: Optional[datetime] = None
    idle_start: Optional[datetime] = None
    warnings_sent: int = 0


@dataclass
class TerminationEvent:
    """Record of termination event."""
    event_id: str
    pod_id: str
    policy_id: str
    reason: TerminationReason
    timestamp: datetime
    details: Dict[str, Any]
    cost_saved: float = 0.0


class AutoTerminator:
    """Manages automatic instance termination policies."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize auto terminator.
        
        Args:
            api_key: RunPod API key
        """
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        runpod.api_key = self.api_key
        
        self.monitor = InstanceMonitor(self.api_key)
        self.ssh_manager = SSHManager(self.api_key)
        
        # Active policies
        self.policies: Dict[str, TerminationPolicy] = {}
        self.termination_events: List[TerminationEvent] = []
        
        # Monitoring tasks
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        
        # Callbacks
        self.termination_callbacks: List[Callable] = []
        
    async def create_policy(
        self,
        pod_id: str,
        idle_minutes: Optional[int] = None,
        gpu_threshold: Optional[int] = None,
        max_cost: Optional[float] = None,
        max_hours: Optional[int] = None,
        scheduled_time: Optional[datetime] = None,
        completion_markers: Optional[List[str]] = None,
        error_threshold: Optional[int] = None
    ) -> TerminationPolicy:
        """
        Create comprehensive termination policy.
        
        Args:
            pod_id: Pod to monitor
            idle_minutes: Terminate after N minutes of idle
            gpu_threshold: GPU utilization threshold for idle
            max_cost: Maximum cost before termination
            max_hours: Maximum runtime hours
            scheduled_time: Specific termination time
            completion_markers: Log patterns indicating completion
            error_threshold: Max consecutive errors
            
        Returns:
            TerminationPolicy object
        """
        policy_id = f"term_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{pod_id[:8]}"
        
        policy = TerminationPolicy(
            policy_id=policy_id,
            pod_id=pod_id,
            created_at=datetime.now()
        )
        
        # Configure idle termination
        if idle_minutes is not None:
            policy.idle_enabled = True
            policy.idle_threshold_minutes = idle_minutes
            if gpu_threshold is not None:
                policy.gpu_threshold_percent = gpu_threshold
                
        # Configure cost limit
        if max_cost is not None:
            policy.cost_limit_enabled = True
            policy.max_cost = max_cost
            
        # Configure time limit
        if max_hours is not None:
            policy.time_limit_enabled = True
            policy.max_runtime_hours = max_hours
        if scheduled_time is not None:
            policy.time_limit_enabled = True
            policy.scheduled_termination = scheduled_time
            
        # Configure training completion
        if completion_markers:
            policy.training_complete_enabled = True
            policy.completion_markers = completion_markers
            
        # Configure error threshold
        if error_threshold is not None:
            policy.error_threshold_enabled = True
            policy.max_consecutive_errors = error_threshold
            
        # Store policy
        self.policies[policy_id] = policy
        
        # Start monitoring
        task = asyncio.create_task(self._monitor_policy(policy))
        self.monitoring_tasks[policy_id] = task
        
        logger.info(f"Created termination policy {policy_id} for pod {pod_id}")
        return policy
        
    async def enable_idle_termination(
        self,
        pod_id: str,
        idle_minutes: int = 30,
        gpu_threshold: int = 10
    ) -> TerminationPolicy:
        """Enable idle-based termination."""
        return await self.create_policy(
            pod_id,
            idle_minutes=idle_minutes,
            gpu_threshold=gpu_threshold
        )
        
    async def enable_cost_limit(
        self,
        pod_id: str,
        max_cost: float
    ) -> TerminationPolicy:
        """Enable cost-based termination."""
        return await self.create_policy(pod_id, max_cost=max_cost)
        
    async def enable_time_limit(
        self,
        pod_id: str,
        max_hours: Optional[int] = None,
        scheduled_time: Optional[datetime] = None
    ) -> TerminationPolicy:
        """Enable time-based termination."""
        return await self.create_policy(
            pod_id,
            max_hours=max_hours,
            scheduled_time=scheduled_time
        )
        
    async def enable_training_completion(
        self,
        pod_id: str,
        completion_markers: List[str]
    ) -> TerminationPolicy:
        """Enable training completion termination."""
        return await self.create_policy(
            pod_id,
            completion_markers=completion_markers
        )
        
    def add_termination_callback(self, callback: Callable):
        """Add callback for termination events."""
        self.termination_callbacks.append(callback)
        
    async def _monitor_policy(self, policy: TerminationPolicy):
        """Monitor and enforce termination policy."""
        logger.info(f"Starting policy monitor for {policy.pod_id}")
        
        check_interval = 60  # Check every minute
        warning_threshold = 5  # Warn 5 minutes before termination
        
        while policy.is_active:
            try:
                policy.last_check = datetime.now()
                
                # Get instance health
                health = await self.monitor.check_instance_health(policy.pod_id)
                
                if not health.get("healthy"):
                    # Instance already terminated or unhealthy
                    policy.is_active = False
                    break
                    
                # Check each termination condition
                terminate = False
                reason = None
                details = {}
                
                # 1. Check idle termination
                if policy.idle_enabled:
                    gpu_util = health.get("gpu_utilization", 0)
                    
                    if gpu_util < policy.gpu_threshold_percent:
                        if policy.idle_start is None:
                            policy.idle_start = datetime.now()
                            logger.info(f"Pod {policy.pod_id} idle detected (GPU: {gpu_util}%)")
                        else:
                            idle_duration = (datetime.now() - policy.idle_start).total_seconds() / 60
                            
                            # Send warning if approaching threshold
                            if idle_duration >= policy.idle_threshold_minutes - warning_threshold and policy.warnings_sent == 0:
                                await self._send_idle_warning(policy, idle_duration)
                                policy.warnings_sent += 1
                                
                            if idle_duration >= policy.idle_threshold_minutes:
                                terminate = True
                                reason = TerminationReason.IDLE
                                details = {
                                    "idle_minutes": round(idle_duration, 1),
                                    "gpu_utilization": gpu_util
                                }
                    else:
                        # Reset idle timer if active again
                        if policy.idle_start is not None:
                            logger.info(f"Pod {policy.pod_id} active again (GPU: {gpu_util}%)")
                            policy.idle_start = None
                            policy.warnings_sent = 0
                            
                # 2. Check cost limit
                if policy.cost_limit_enabled and not terminate:
                    cost_so_far = health.get("cost_so_far", 0)
                    
                    if cost_so_far >= policy.max_cost:
                        terminate = True
                        reason = TerminationReason.COST_LIMIT
                        details = {
                            "cost": cost_so_far,
                            "limit": policy.max_cost
                        }
                        
                # 3. Check time limit
                if policy.time_limit_enabled and not terminate:
                    runtime_hours = health.get("uptime_seconds", 0) / 3600
                    
                    if policy.max_runtime_hours > 0 and runtime_hours >= policy.max_runtime_hours:
                        terminate = True
                        reason = TerminationReason.TIME_LIMIT
                        details = {
                            "runtime_hours": round(runtime_hours, 2),
                            "limit_hours": policy.max_runtime_hours
                        }
                        
                    if policy.scheduled_termination and datetime.now() >= policy.scheduled_termination:
                        terminate = True
                        reason = TerminationReason.SCHEDULED
                        details = {
                            "scheduled_time": policy.scheduled_termination.isoformat()
                        }
                        
                # 4. Check training completion
                if policy.training_complete_enabled and not terminate:
                    logs = await self._get_recent_logs(policy.pod_id)
                    
                    if logs:
                        for marker in policy.completion_markers:
                            if marker in logs:
                                terminate = True
                                reason = TerminationReason.TRAINING_COMPLETE
                                details = {
                                    "marker": marker,
                                    "runtime_hours": round(health.get("uptime_seconds", 0) / 3600, 2)
                                }
                                break
                                
                # 5. Check error threshold
                if policy.error_threshold_enabled and not terminate:
                    # Check for errors in logs
                    if await self._check_for_errors(policy.pod_id):
                        policy.error_count += 1
                        
                        if policy.error_count >= policy.max_consecutive_errors:
                            terminate = True
                            reason = TerminationReason.ERROR_THRESHOLD
                            details = {
                                "error_count": policy.error_count,
                                "threshold": policy.max_consecutive_errors
                            }
                    else:
                        # Reset error count if healthy
                        policy.error_count = 0
                        
                # Execute termination if needed
                if terminate and reason:
                    await self._terminate_instance(policy, reason, details)
                    break
                    
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Policy monitor error: {e}")
                await asyncio.sleep(check_interval)
                
        logger.info(f"Policy monitor stopped for {policy.pod_id}")
        
    async def _terminate_instance(
        self,
        policy: TerminationPolicy,
        reason: TerminationReason,
        details: Dict[str, Any]
    ):
        """Terminate instance and record event."""
        logger.warning(f"Terminating pod {policy.pod_id} due to {reason.value}")
        
        try:
            # Get final metrics
            health = await self.monitor.check_instance_health(policy.pod_id)
            final_cost = health.get("cost_so_far", 0)
            
            # Calculate potential cost saved
            cost_per_hour = health.get("cost_per_hour", 0)
            
            if reason == TerminationReason.IDLE:
                # Estimate savings based on typical remaining runtime
                estimated_remaining_hours = 2  # Conservative estimate
                cost_saved = cost_per_hour * estimated_remaining_hours
            else:
                cost_saved = 0
                
            # Create termination event
            event = TerminationEvent(
                event_id=f"evt_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                pod_id=policy.pod_id,
                policy_id=policy.policy_id,
                reason=reason,
                timestamp=datetime.now(),
                details=details,
                cost_saved=cost_saved
            )
            
            self.termination_events.append(event)
            
            # Execute callbacks
            for callback in self.termination_callbacks:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
                    
            # Terminate pod
            success = runpod.terminate_pod(policy.pod_id)
            
            if success:
                logger.info(f"Pod {policy.pod_id} terminated successfully")
                policy.is_active = False
                
                # Log termination details
                self._log_termination_event(event, final_cost)
            else:
                logger.error(f"Failed to terminate pod {policy.pod_id}")
                
        except Exception as e:
            logger.error(f"Termination error: {e}")
            
    async def _send_idle_warning(self, policy: TerminationPolicy, idle_minutes: float):
        """Send warning about impending idle termination."""
        remaining = policy.idle_threshold_minutes - idle_minutes
        
        logger.warning(
            f"Pod {policy.pod_id} will be terminated in {remaining:.1f} minutes due to idle "
            f"(GPU < {policy.gpu_threshold_percent}%)"
        )
        
        # Could also send notifications via webhook, email, etc.
        
    async def _get_recent_logs(self, pod_id: str, lines: int = 100) -> Optional[str]:
        """Get recent logs from pod."""
        try:
            result = await self.ssh_manager.execute_on_pod(
                pod_id,
                f"tail -n {lines} /workspace/training.log 2>/dev/null || " + 
                f"tail -n {lines} /workspace/logs/*.log 2>/dev/null || echo ''"
            )
            
            if result["success"]:
                return result["stdout"]
                
        except Exception as e:
            logger.debug(f"Could not get logs: {e}")
            
        return None
        
    async def _check_for_errors(self, pod_id: str) -> bool:
        """Check if pod has errors."""
        logs = await self._get_recent_logs(pod_id, lines=50)
        
        if logs:
            error_indicators = [
                "error",
                "exception",
                "failed",
                "cuda out of memory",
                "killed",
                "segmentation fault"
            ]
            
            logs_lower = logs.lower()
            return any(indicator in logs_lower for indicator in error_indicators)
            
        return False
        
    def _log_termination_event(self, event: TerminationEvent, final_cost: float):
        """Log termination event to file."""
        log_dir = Path("logs/terminations")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"terminations_{datetime.now().strftime('%Y%m')}.jsonl"
        
        log_entry = {
            "event_id": event.event_id,
            "pod_id": event.pod_id,
            "policy_id": event.policy_id,
            "reason": event.reason.value,
            "timestamp": event.timestamp.isoformat(),
            "details": event.details,
            "final_cost": final_cost,
            "cost_saved": event.cost_saved
        }
        
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    def get_active_policies(self) -> List[TerminationPolicy]:
        """Get all active termination policies."""
        return [p for p in self.policies.values() if p.is_active]
        
    def get_termination_history(
        self,
        pod_id: Optional[str] = None,
        reason: Optional[TerminationReason] = None,
        since: Optional[datetime] = None
    ) -> List[TerminationEvent]:
        """Get termination event history."""
        events = self.termination_events
        
        if pod_id:
            events = [e for e in events if e.pod_id == pod_id]
            
        if reason:
            events = [e for e in events if e.reason == reason]
            
        if since:
            events = [e for e in events if e.timestamp >= since]
            
        return events
        
    def calculate_total_savings(self, since: Optional[datetime] = None) -> float:
        """Calculate total cost savings from auto-termination."""
        events = self.get_termination_history(since=since)
        return sum(e.cost_saved for e in events)
        
    async def disable_policy(self, policy_id: str):
        """Disable a termination policy."""
        if policy_id in self.policies:
            self.policies[policy_id].is_active = False
            
            # Cancel monitoring task
            if policy_id in self.monitoring_tasks:
                self.monitoring_tasks[policy_id].cancel()
                del self.monitoring_tasks[policy_id]
                
            logger.info(f"Disabled termination policy {policy_id}")
            
    async def disable_all_policies(self):
        """Disable all termination policies."""
        for policy_id in list(self.policies.keys()):
            await self.disable_policy(policy_id)


# Validation
if __name__ == "__main__":
    from pathlib import Path
    
    async def test_terminator():
        # Test policy creation
        terminator = AutoTerminator()
        
        # Test idle termination policy
        policy1 = await terminator.create_policy(
            "test_pod_1",
            idle_minutes=30,
            gpu_threshold=10
        )
        
        assert policy1.idle_enabled == True
        assert policy1.idle_threshold_minutes == 30
        assert policy1.gpu_threshold_percent == 10
        
        # Test cost limit policy
        policy2 = await terminator.create_policy(
            "test_pod_2",
            max_cost=100.0
        )
        
        assert policy2.cost_limit_enabled == True
        assert policy2.max_cost == 100.0
        
        # Test comprehensive policy
        policy3 = await terminator.create_policy(
            "test_pod_3",
            idle_minutes=60,
            max_cost=50.0,
            max_hours=24,
            completion_markers=["Training complete", "Model saved"],
            error_threshold=5
        )
        
        assert policy3.idle_enabled == True
        assert policy3.cost_limit_enabled == True
        assert policy3.time_limit_enabled == True
        assert policy3.training_complete_enabled == True
        assert policy3.error_threshold_enabled == True
        
        # Test policy listing
        active = terminator.get_active_policies()
        assert len(active) == 3
        
        # Disable all for cleanup
        await terminator.disable_all_policies()
        
        print("✅ Auto terminator validation passed")
        
    asyncio.run(test_terminator())