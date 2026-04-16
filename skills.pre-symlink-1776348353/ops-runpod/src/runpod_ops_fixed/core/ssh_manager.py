"""
Module: ssh_manager.py
Description: SSH connection management for RunPod instances

External Dependencies:
- paramiko: https://docs.paramiko.org/
- runpod: https://docs.runpod.io/
- loguru: https://loguru.readthedocs.io/

Sample Input:
>>> manager = SSHManager()
>>> connection = manager.connect("pod_host_id", "pod_id")

Expected Output:
>>> connection.is_connected()
True
>>> result = connection.execute("ls -la")
>>> print(result["stdout"])
'total 24\ndrwxr-xr-x 1 root root 4096 ...'

Example Usage:
>>> from runpod_ops_fixed.ssh_manager import SSHManager
>>> ssh = SSHManager()
>>> conn = await ssh.connect_to_pod("abc123")
>>> result = await conn.execute_command("nvidia-smi")
"""

import os
import asyncio
import subprocess
import time
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
import tempfile
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict
import threading
import queue

import runpod
import paramiko
from loguru import logger
import socket


@dataclass
class ConnectionStats:
    """Track connection statistics."""
    total_commands: int = 0
    failed_commands: int = 0
    total_bytes_uploaded: int = 0
    total_bytes_downloaded: int = 0
    connection_time: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    reconnect_count: int = 0


class SSHConnection:
    """Manages SSH connection to a RunPod instance."""
    
    def __init__(self, hostname: str, port: int, username: str, private_key_path: str):
        """
        Initialize SSH connection parameters.
        
        Args:
            hostname: SSH hostname
            port: SSH port
            username: SSH username
            private_key_path: Path to private key file
        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.private_key_path = private_key_path
        self.client: Optional[paramiko.SSHClient] = None
        self._connected = False
        
    def connect(self) -> bool:
        """
        Establish SSH connection.
        
        Returns:
            Success status
        """
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Load private key
            private_key = paramiko.RSAKey.from_private_key_file(self.private_key_path)
            
            # Connect
            self.client.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                pkey=private_key,
                timeout=30,
                banner_timeout=30
            )
            
            self._connected = True
            logger.info(f"SSH connected to {self.hostname}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"SSH connection failed: {e}")
            self._connected = False
            return False
            
    def disconnect(self):
        """Close SSH connection."""
        if self.client:
            self.client.close()
            self._connected = False
            logger.info("SSH connection closed")
            
    def is_connected(self) -> bool:
        """Check if SSH connection is active."""
        return self._connected and self.client and self.client.get_transport() and self.client.get_transport().is_active()
        
    def execute_command(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute command over SSH.
        
        Args:
            command: Command to execute
            timeout: Command timeout in seconds
            
        Returns:
            Dict with stdout, stderr, and exit_code
        """
        if not self.is_connected():
            return {"error": "Not connected", "exit_code": -1}
            
        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            
            # Get output
            stdout_data = stdout.read().decode('utf-8')
            stderr_data = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            
            return {
                "stdout": stdout_data,
                "stderr": stderr_data,
                "exit_code": exit_code,
                "success": exit_code == 0
            }
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {
                "error": str(e),
                "exit_code": -1,
                "success": False
            }
            
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """
        Upload file via SFTP.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            
        Returns:
            Success status
        """
        if not self.is_connected():
            return False
            
        try:
            sftp = self.client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            logger.info(f"Uploaded {local_path} to {remote_path}")
            return True
            
        except Exception as e:
            logger.error(f"File upload failed: {e}")
            return False
            
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """
        Download file via SFTP.
        
        Args:
            remote_path: Remote file path
            local_path: Local destination path
            
        Returns:
            Success status
        """
        if not self.is_connected():
            return False
            
        try:
            sftp = self.client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
            logger.info(f"Downloaded {remote_path} to {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"File download failed: {e}")
            return False


class SSHManager:
    """Manages SSH connections to RunPod instances."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize SSH manager.
        
        Args:
            api_key: RunPod API key (or from RUNPOD_API_KEY env)
        """
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        if not self.api_key:
            raise ValueError("RunPod API key required")
            
        runpod.api_key = self.api_key
        self.connections: Dict[str, SSHConnection] = {}
        
        # Ensure SSH key exists
        self._ensure_ssh_key()
        
    def _ensure_ssh_key(self):
        """Ensure SSH key pair exists."""
        ssh_dir = Path.home() / ".ssh"
        ssh_dir.mkdir(exist_ok=True)
        
        self.private_key_path = ssh_dir / "runpod_rsa"
        self.public_key_path = ssh_dir / "runpod_rsa.pub"
        
        if not self.private_key_path.exists():
            logger.info("Generating SSH key pair")
            subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", str(self.private_key_path), "-N", ""], check=True)
            
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
            # Get pod info
            pod_info = runpod.get_pod(pod_id)
            
            if not pod_info:
                logger.error(f"Pod {pod_id} not found")
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
                
            # Create connection
            connection = SSHConnection(
                hostname=hostname,
                port=port,
                username=username,
                private_key_path=str(self.private_key_path)
            )
            
            # Connect
            if connection.connect():
                self.connections[pod_id] = connection
                return connection
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to connect to pod {pod_id}: {e}")
            return None
            
    def disconnect_from_pod(self, pod_id: str):
        """Disconnect from a pod."""
        if pod_id in self.connections:
            self.connections[pod_id].disconnect()
            del self.connections[pod_id]
            
    def disconnect_all(self):
        """Disconnect all SSH connections."""
        for pod_id in list(self.connections.keys()):
            self.disconnect_from_pod(pod_id)
            
    async def execute_on_pod(self, pod_id: str, command: str) -> Dict[str, Any]:
        """
        Execute command on a pod, connecting if needed.
        
        Args:
            pod_id: Pod ID
            command: Command to execute
            
        Returns:
            Command result
        """
        # Get or create connection
        if pod_id not in self.connections or not self.connections[pod_id].is_connected():
            connection = await self.connect_to_pod(pod_id)
            if not connection:
                return {"error": "Failed to connect", "exit_code": -1}
        else:
            connection = self.connections[pod_id]
            
        return connection.execute_command(command)
        
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
        conn = SSHConnection("test.host", 22, "user", str(manager.private_key_path))
        assert not conn.is_connected(), "Should not be connected initially"
        
        print("\n✅ SSH Manager validation passed")
        
    asyncio.run(test_ssh_manager())