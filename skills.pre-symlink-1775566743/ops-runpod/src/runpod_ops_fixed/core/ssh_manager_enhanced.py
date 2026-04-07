"""
Module: ssh_manager_enhanced.py
Description: Enhanced SSH connection management for RunPod with pooling and retry.

The SSHConnection and ConnectionStats classes live in ssh_connection.py;
this module provides the SSHManager connection-pool layer on top.

External Dependencies:
- paramiko: https://docs.paramiko.org/
- runpod: https://docs.runpod.io/
- loguru: https://loguru.readthedocs.io/

Sample Input:
>>> manager = SSHManager()
>>> result = await manager.execute_on_pod("pod_id", "nvidia-smi")

Expected Output:
>>> result
{"stdout": "GPU 0: NVIDIA RTX 4090...", "stderr": "", "exit_code": 0, "success": True}

Example Usage:
>>> from runpod_ops_fixed.core.ssh_manager_enhanced import SSHManager
>>> ssh = SSHManager(max_connections_per_pod=5)
>>> await ssh.execute_batch_commands("pod_id", ["cd /workspace", "ls", "nvidia-smi"])
"""

import os
import asyncio
import subprocess
import time
from typing import Dict, Any, Optional, List
from pathlib import Path
import tempfile
from datetime import datetime, timedelta
from collections import defaultdict
import threading

import runpod
from loguru import logger

from runpod_ops_fixed.core.ssh_connection import SSHConnection, ConnectionStats


class SSHManager:
    """Manages SSH connections to RunPod instances with connection pooling."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_connections_per_pod: int = 3,
        private_key_path: Optional[str] = None,
        public_key_path: Optional[str] = None,
    ):
        """
        Initialize SSH manager.

        Args:
            api_key: RunPod API key (or from RUNPOD_API_KEY env)
            max_connections_per_pod: Maximum concurrent connections per pod
        """
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        if not self.api_key:
            raise ValueError("RunPod API key required")

        runpod.api_key = self.api_key
        self.connections: Dict[str, List[SSHConnection]] = defaultdict(list)
        self.connection_lock = threading.Lock()
        self.max_connections_per_pod = max_connections_per_pod
        self._cleanup_task = None

        # Connection pool statistics
        self.pool_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "reused_connections": 0,
            "failed_connections": 0
        }

        # Ensure SSH key exists
        self._ensure_ssh_key(private_key_path, public_key_path)

        # Start cleanup task
        self._start_cleanup_task()

    def _ensure_ssh_key(self, private_key_path: Optional[str], public_key_path: Optional[str]):
        """
        Ensure SSH key pair exists, allowing caller/env overrides.
        Prefers ed25519 when generating new keys. If a key path is provided and
        missing, we fail fast instead of silently generating a different key.
        """
        env_private = os.getenv("RUNPOD_SSH_KEY_PATH")
        env_public = os.getenv("RUNPOD_SSH_PUBLIC_KEY_PATH")

        if private_key_path:
            self.private_key_path = Path(private_key_path).expanduser()
            self.public_key_path = (
                Path(public_key_path).expanduser()
                if public_key_path
                else Path(str(self.private_key_path) + ".pub")
            )
            if not self.private_key_path.exists():
                raise FileNotFoundError(
                    f"Private key {self.private_key_path} not found. Provide a valid --ssh-key-path or set RUNPOD_SSH_KEY_PATH."
                )
            if not self.public_key_path.exists():
                raise FileNotFoundError(
                    f"Public key {self.public_key_path} not found. Provide RUNPOD_SSH_PUBLIC_KEY_PATH or place the .pub next to the private key."
                )
        elif env_private:
            self.private_key_path = Path(env_private).expanduser()
            self.public_key_path = (
                Path(env_public).expanduser()
                if env_public
                else Path(str(self.private_key_path) + ".pub")
            )
            if not self.private_key_path.exists():
                raise FileNotFoundError(f"RUNPOD_SSH_KEY_PATH points to missing file: {self.private_key_path}")
            if not self.public_key_path.exists():
                raise FileNotFoundError(f"RUNPOD_SSH_PUBLIC_KEY_PATH missing: {self.public_key_path}")
        else:
            ssh_dir = Path.home() / ".ssh"
            ssh_dir.mkdir(exist_ok=True)
            self.private_key_path = ssh_dir / "runpod_ed25519"
            self.public_key_path = ssh_dir / "runpod_ed25519.pub"
            if not self.private_key_path.exists():
                logger.info(f"Generating SSH key pair at {self.private_key_path} (ed25519)")
                subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(self.private_key_path), "-N", ""], check=True)

        # Read public key
        with open(self.public_key_path, 'r') as f:
            self.public_key = f.read().strip()

    async def connect_to_pod(self, pod_id: str) -> Optional[SSHConnection]:
        """
        Connect to a RunPod instance via SSH.

        Args:
            pod_id: Pod ID to connect to

        Returns:
            SSHConnection object or None
        """
        try:
            lookup_id = pod_id
            # Accept podHostId strings (e.g., "<id>-xxxxx"); strip suffix to recover pod id
            if "-" in pod_id and len(pod_id.split("-")[0]) >= 8:
                lookup_id = pod_id.split("-")[0]

            pod_info = None
            for attempt in range(5):
                pod_info = runpod.get_pod(lookup_id)
                if pod_info:
                    break
                logger.warning(f"Pod {pod_id} not found yet (attempt {attempt+1}/5); retrying...")
                await asyncio.sleep(3)

            if not pod_info:
                logger.error(f"Pod {pod_id} not found after retries")
                return None

            # Extract SSH connection details
            pod_host_id = pod_info.get("machine", {}).get("podHostId")
            if not pod_host_id:
                logger.error(f"No SSH info for pod {pod_id}")
                return None

            # Parse SSH connection string (format: podHostId@ssh.runpod.io:port)
            if "@" in pod_host_id and ":" in pod_host_id:
                username_host, port = pod_host_id.rsplit(":", 1)
                username, hostname = username_host.split("@", 1)
                port = int(port)
            else:
                # Default format
                username = pod_host_id
                hostname = "ssh.runpod.io"
                port = 22

            # Check for existing connections in pool
            with self.connection_lock:
                pool = self.connections[pod_id]

                # Try to reuse existing connection
                for conn in pool:
                    if conn.is_connected():
                        self.pool_stats["reused_connections"] += 1
                        logger.debug(f"Reusing existing connection to {pod_id}")
                        return conn

                # Remove dead connections
                pool[:] = [c for c in pool if c.is_connected()]

                # Check pool limit
                if len(pool) >= self.max_connections_per_pod:
                    # Reuse least recently used connection
                    pool.sort(key=lambda c: c.stats.last_activity or datetime.min)
                    return pool[0]

            # Create new connection
            connection = SSHConnection(
                hostname=hostname,
                port=port,
                username=username,
                private_key_path=str(self.private_key_path),
                pod_id=pod_id
            )

            # Connect
            if connection.connect():
                with self.connection_lock:
                    self.connections[pod_id].append(connection)
                    self.pool_stats["total_connections"] += 1
                    self.pool_stats["active_connections"] = sum(len(pool) for pool in self.connections.values())
                return connection
            else:
                self.pool_stats["failed_connections"] += 1
                return None

        except Exception as e:
            logger.error(f"Failed to connect to pod {pod_id}: {e}")
            return None

    def disconnect_from_pod(self, pod_id: str):
        """Disconnect all connections from a pod."""
        with self.connection_lock:
            if pod_id in self.connections:
                for conn in self.connections[pod_id]:
                    conn.disconnect()
                del self.connections[pod_id]
                self.pool_stats["active_connections"] = sum(len(pool) for pool in self.connections.values())

    def disconnect_all(self):
        """Disconnect all SSH connections."""
        with self.connection_lock:
            for pod_id in list(self.connections.keys()):
                self.disconnect_from_pod(pod_id)

        # Stop cleanup task
        if self._cleanup_task:
            self._cleanup_task = None

    async def execute_on_pod(self, pod_id: str, command: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute command on a pod, connecting if needed.

        Args:
            pod_id: Pod ID
            command: Command to execute
            timeout: Command timeout

        Returns:
            Command result
        """
        # Get or create connection
        connection = await self.connect_to_pod(pod_id)
        if not connection:
            return {"error": "Failed to connect", "exit_code": -1, "success": False}

        return connection.execute_command(command, timeout=timeout)

    async def execute_batch_commands(self, pod_id: str, commands: List[str]) -> List[Dict[str, Any]]:
        """
        Execute multiple commands efficiently.

        Args:
            pod_id: Pod ID
            commands: List of commands

        Returns:
            List of results
        """
        connection = await self.connect_to_pod(pod_id)
        if not connection:
            return [{"error": "Failed to connect", "exit_code": -1, "success": False}] * len(commands)

        results = []
        for cmd in commands:
            result = connection.execute_command(cmd)
            results.append(result)

            # Stop on critical failure
            if not result.get("success") and "command not found" in result.get("stderr", ""):
                logger.warning(f"Stopping batch execution due to error: {result.get('stderr')}")
                break

        return results

    async def setup_training_environment(self, pod_id: str, repo_url: str, requirements_file: str = "requirements.txt") -> bool:
        """
        Setup training environment on a pod.

        Args:
            pod_id: Pod ID
            repo_url: Git repository URL
            requirements_file: Requirements file name

        Returns:
            Success status
        """
        logger.info(f"Setting up training environment on pod {pod_id}")

        commands = [
            # Update system
            "apt-get update -y",

            # Install git if needed
            "which git || apt-get install -y git",

            # Clone repository
            f"cd /workspace && git clone {repo_url} training_repo || true",

            # Install Python requirements
            f"cd /workspace/training_repo && pip install -r {requirements_file}",

            # Install additional tools
            "pip install wandb tensorboard",

            # Setup Jupyter
            "jupyter notebook --generate-config",
            "echo \"c.NotebookApp.allow_root = True\" >> ~/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.ip = '0.0.0.0'\" >> ~/.jupyter/jupyter_notebook_config.py",
        ]

        for cmd in commands:
            result = await self.execute_on_pod(pod_id, cmd)
            if result.get("exit_code", -1) != 0 and "already" not in result.get("stderr", ""):
                logger.error(f"Command failed: {cmd}")
                logger.error(f"Error: {result.get('stderr', result.get('error', ''))}")
                return False

        logger.info("Training environment setup complete")
        return True

    async def monitor_training(self, pod_id: str) -> Dict[str, Any]:
        """
        Monitor training progress on a pod.

        Args:
            pod_id: Pod ID

        Returns:
            Training metrics
        """
        metrics = {}

        # Check GPU utilization
        gpu_result = await self.execute_on_pod(pod_id, "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits")
        if gpu_result["success"]:
            lines = gpu_result["stdout"].strip().split('\n')
            gpu_metrics = []
            for line in lines:
                parts = line.split(', ')
                if len(parts) == 3:
                    gpu_metrics.append({
                        "utilization": float(parts[0]),
                        "memory_used": float(parts[1]),
                        "memory_total": float(parts[2])
                    })
            metrics["gpus"] = gpu_metrics

        # Check training process
        process_result = await self.execute_on_pod(pod_id, "ps aux | grep -E 'python.*train|train.py' | grep -v grep")
        metrics["training_running"] = process_result["success"] and bool(process_result["stdout"].strip())

        # Check disk usage
        disk_result = await self.execute_on_pod(pod_id, "df -h /workspace | tail -1 | awk '{print $5}' | sed 's/%//'")
        if disk_result["success"]:
            metrics["disk_usage_percent"] = float(disk_result["stdout"].strip())

        # Check for latest checkpoint
        checkpoint_result = await self.execute_on_pod(pod_id, "ls -t /workspace/checkpoints/*.pt 2>/dev/null | head -1")
        if checkpoint_result["success"] and checkpoint_result["stdout"].strip():
            metrics["latest_checkpoint"] = checkpoint_result["stdout"].strip()

        return metrics

    async def upload_large_file(self, pod_id: str, local_path: str, remote_path: str, chunk_size: int = 100 * 1024 * 1024) -> bool:
        """
        Upload large file in chunks with resume support.

        Args:
            pod_id: Pod ID
            local_path: Local file path
            remote_path: Remote file path
            chunk_size: Size of chunks in bytes (default 100MB)

        Returns:
            Success status
        """
        connection = await self.connect_to_pod(pod_id)
        if not connection:
            return False

        try:
            file_size = os.path.getsize(local_path)
            logger.info(f"Uploading large file {local_path} ({file_size / 1024 / 1024:.1f}MB)")

            # Check if partial file exists
            check_result = connection.execute_command(f"ls -la {remote_path} 2>/dev/null || echo 'NOFILE'")

            start_offset = 0
            if "NOFILE" not in check_result.get("stdout", ""):
                # Get existing file size
                size_result = connection.execute_command(f"stat -c%s {remote_path} 2>/dev/null || echo 0")
                try:
                    start_offset = int(size_result.get("stdout", "0").strip())
                    if start_offset > 0:
                        logger.info(f"Resuming upload from offset {start_offset}")
                except Exception:
                    start_offset = 0

            # Upload in chunks
            with open(local_path, 'rb') as f:
                f.seek(start_offset)

                while True:
                    chunk_data = f.read(chunk_size)
                    if not chunk_data:
                        break

                    # Create temporary file for chunk
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp.write(chunk_data)
                        tmp_path = tmp.name

                    # Upload chunk
                    chunk_remote = f"{remote_path}.chunk"
                    if not connection.upload_file(tmp_path, chunk_remote):
                        os.unlink(tmp_path)
                        return False

                    # Append chunk to file
                    append_result = connection.execute_command(f"cat {chunk_remote} >> {remote_path} && rm {chunk_remote}")
                    os.unlink(tmp_path)

                    if not append_result.get("success"):
                        logger.error(f"Failed to append chunk: {append_result.get('stderr')}")
                        return False

                    current_offset = f.tell()
                    progress = current_offset / file_size * 100
                    logger.info(f"Upload progress: {progress:.1f}% ({current_offset / 1024 / 1024:.1f}MB / {file_size / 1024 / 1024:.1f}MB)")

            # Verify file size
            verify_result = connection.execute_command(f"stat -c%s {remote_path}")
            if verify_result.get("success"):
                remote_size = int(verify_result.get("stdout", "0").strip())
                if remote_size == file_size:
                    logger.info(f"Upload complete and verified: {remote_path}")
                    return True
                else:
                    logger.error(f"Size mismatch: local={file_size}, remote={remote_size}")
                    return False

        except Exception as e:
            logger.error(f"Large file upload failed: {e}")
            return False

    def _start_cleanup_task(self):
        """Start background task to clean up idle connections."""
        def cleanup_worker():
            while self._cleanup_task is not None:
                try:
                    with self.connection_lock:
                        for pod_id, pool in list(self.connections.items()):
                            # Remove disconnected connections
                            pool[:] = [c for c in pool if c.is_connected()]

                            # Remove connections idle for > 5 minutes
                            cutoff = datetime.now() - timedelta(minutes=5)
                            pool[:] = [c for c in pool if c.stats.last_activity and c.stats.last_activity > cutoff]

                            # Remove empty pools
                            if not pool:
                                del self.connections[pod_id]

                        self.pool_stats["active_connections"] = sum(len(pool) for pool in self.connections.values())

                except Exception as e:
                    logger.error(f"Cleanup task error: {e}")

                time.sleep(60)  # Run every minute

        self._cleanup_task = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_task.start()

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        with self.connection_lock:
            pod_stats = {}
            for pod_id, pool in self.connections.items():
                active = sum(1 for c in pool if c.is_connected())
                total_commands = sum(c.stats.total_commands for c in pool)
                failed_commands = sum(c.stats.failed_commands for c in pool)

                pod_stats[pod_id] = {
                    "total_connections": len(pool),
                    "active_connections": active,
                    "total_commands": total_commands,
                    "failed_commands": failed_commands,
                    "success_rate": (total_commands - failed_commands) / total_commands if total_commands > 0 else 0
                }

            return {
                "pool_stats": self.pool_stats,
                "pod_stats": pod_stats,
                "total_pods": len(self.connections)
            }


# Validation
if __name__ == "__main__":
    async def test_ssh_manager():
        # Test SSH key generation
        manager = SSHManager(api_key="dummy_key_for_test")

        assert manager.private_key_path.exists(), "Private key not created"
        assert manager.public_key_path.exists(), "Public key not created"

        print(f"SSH keys location: {manager.private_key_path}")
        print(f"Public key: {manager.public_key[:50]}...")

        # Test connection object
        conn = SSHConnection("test.host", 22, "user", str(manager.private_key_path), "test_pod")
        assert not conn.is_connected(), "Should not be connected initially"

        # Test connection stats
        assert conn.stats.total_commands == 0
        assert conn.stats.reconnect_count == 0

        # Test pool statistics
        pool_stats = manager.get_connection_stats()
        assert pool_stats["total_pods"] == 0
        assert pool_stats["pool_stats"]["total_connections"] == 0

        print("\n✅ SSH Manager validation passed")

    asyncio.run(test_ssh_manager())
