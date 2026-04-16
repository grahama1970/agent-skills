"""
Module: ssh_connection.py
Description: SSH connection and statistics classes for RunPod instance management.

Extracted from ssh_manager_enhanced.py to keep modules under 800 lines.
Contains the ConnectionStats dataclass and SSHConnection class which handle
individual SSH connections with retry logic, keepalive, file transfer, and
directory sync.

External Dependencies:
- paramiko: https://docs.paramiko.org/
- loguru: https://loguru.readthedocs.io/

Sample Input:
>>> conn = SSHConnection("ssh.runpod.io", 22, "user", "/path/to/key", "pod_abc")
>>> conn.connect()

Expected Output:
>>> True

Example Usage:
>>> from runpod_ops_fixed.core.ssh_connection import SSHConnection, ConnectionStats
>>> conn = SSHConnection("host", 22, "root", "~/.ssh/id_ed25519", "pod123")
>>> if conn.connect():
...     result = conn.execute_command("nvidia-smi")
"""

import os
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
import threading
import socket
import fnmatch

import paramiko
from loguru import logger


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
    """Manages SSH connection to a RunPod instance with retry and pooling."""

    def __init__(self, hostname: str, port: int, username: str, private_key_path: str, pod_id: str):
        """
        Initialize SSH connection parameters.

        Args:
            hostname: SSH hostname
            port: SSH port
            username: SSH username
            private_key_path: Path to private key file
            pod_id: RunPod pod ID
        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.private_key_path = private_key_path
        self.pod_id = pod_id
        self.client: Optional[paramiko.SSHClient] = None
        self._connected = False
        self._lock = threading.Lock()
        self.stats = ConnectionStats()
        self._last_keepalive = time.time()

    def connect(self, retry_count: int = 3, retry_delay: int = 5) -> bool:
        """
        Establish SSH connection with retry logic.

        Args:
            retry_count: Number of connection attempts
            retry_delay: Delay between retries in seconds

        Returns:
            Success status
        """
        with self._lock:
            for attempt in range(retry_count):
                try:
                    if attempt > 0:
                        logger.info(f"Retry attempt {attempt + 1}/{retry_count} for {self.hostname}")
                        time.sleep(retry_delay)

                    self.client = paramiko.SSHClient()
                    self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                    # Load private key (support ed25519 or RSA)
                    private_key = self._load_private_key(self.private_key_path)

                    # Connect with optimized settings
                    self.client.connect(
                        hostname=self.hostname,
                        port=self.port,
                        username=self.username,
                        pkey=private_key,
                        timeout=30,
                        banner_timeout=30,
                        auth_timeout=30,
                        # Performance optimizations
                        compress=True,
                        allow_agent=False,
                        look_for_keys=False
                    )

                    # Set keepalive
                    transport = self.client.get_transport()
                    transport.set_keepalive(30)

                    self._connected = True
                    self.stats.connection_time = datetime.now()
                    self.stats.last_activity = datetime.now()

                    logger.info(f"SSH connected to {self.hostname}:{self.port} (pod: {self.pod_id})")
                    return True

                except paramiko.AuthenticationException as e:
                    logger.error(f"SSH authentication failed: {e}")
                    break  # Don't retry auth failures
                except paramiko.SSHException as e:
                    logger.error(f"SSH error on attempt {attempt + 1}: {e}")
                except Exception as e:
                    logger.error(f"Connection error on attempt {attempt + 1}: {e}")

            self._connected = False
            return False

    @staticmethod
    def _load_private_key(path: str) -> paramiko.PKey:
        """
        Load a private key, trying ed25519 first then RSA for compatibility.
        """
        try:
            return paramiko.Ed25519Key.from_private_key_file(path)
        except Exception:
            return paramiko.RSAKey.from_private_key_file(path)

    def disconnect(self):
        """Close SSH connection."""
        with self._lock:
            if self.client:
                self.client.close()
                self._connected = False
                logger.info("SSH connection closed")

    def is_connected(self) -> bool:
        """Check if SSH connection is active and send keepalive if needed."""
        if not self._connected or not self.client:
            return False

        try:
            transport = self.client.get_transport()
            if not transport or not transport.is_active():
                return False

            # Send keepalive if needed
            current_time = time.time()
            if current_time - self._last_keepalive > 60:
                transport.send_ignore()
                self._last_keepalive = current_time

            return True
        except Exception:
            return False

    def reconnect_if_needed(self) -> bool:
        """Reconnect if connection is lost."""
        if not self.is_connected():
            logger.info(f"Reconnecting to {self.pod_id}...")
            self.stats.reconnect_count += 1
            return self.connect(retry_count=2)
        return True

    def execute_command(self, command: str, timeout: int = 30, retry_on_fail: bool = True) -> Dict[str, Any]:
        """
        Execute command over SSH with auto-reconnect.

        Args:
            command: Command to execute
            timeout: Command timeout in seconds
            retry_on_fail: Whether to retry on connection failure

        Returns:
            Dict with stdout, stderr, and exit_code
        """
        with self._lock:
            # Auto-reconnect if needed
            if retry_on_fail and not self.reconnect_if_needed():
                self.stats.failed_commands += 1
                return {"error": "Connection lost and reconnect failed", "exit_code": -1, "success": False}

            try:
                self.stats.total_commands += 1
                self.stats.last_activity = datetime.now()

                # Create channel for better control
                channel = self.client.get_transport().open_session()
                channel.settimeout(timeout)
                channel.exec_command(command)

                # Read output with timeout
                stdout_data = b""
                stderr_data = b""

                # Read in chunks to handle large outputs
                while not channel.exit_status_ready():
                    if channel.recv_ready():
                        stdout_data += channel.recv(4096)
                    if channel.recv_stderr_ready():
                        stderr_data += channel.recv_stderr(4096)
                    time.sleep(0.01)

                # Get remaining data
                while channel.recv_ready():
                    stdout_data += channel.recv(4096)
                while channel.recv_stderr_ready():
                    stderr_data += channel.recv_stderr(4096)

                exit_code = channel.recv_exit_status()
                channel.close()

                return {
                    "stdout": stdout_data.decode('utf-8', errors='replace'),
                    "stderr": stderr_data.decode('utf-8', errors='replace'),
                    "exit_code": exit_code,
                    "success": exit_code == 0
                }

            except socket.timeout:
                self.stats.failed_commands += 1
                return {
                    "error": f"Command timed out after {timeout}s",
                    "exit_code": -1,
                    "success": False
                }
            except Exception as e:
                self.stats.failed_commands += 1
                logger.error(f"Command execution failed: {e}")

                # Try to reconnect and retry once
                if retry_on_fail and "SSH session not active" in str(e):
                    logger.info("Attempting reconnect and retry...")
                    if self.connect():
                        return self.execute_command(command, timeout, retry_on_fail=False)

                return {
                    "error": str(e),
                    "exit_code": -1,
                    "success": False
                }

    def upload_file(self, local_path: str, remote_path: str, callback=None) -> bool:
        """
        Upload file via SFTP with progress callback.

        Args:
            local_path: Local file path
            remote_path: Remote destination path
            callback: Progress callback function(bytes_transferred, total_bytes)

        Returns:
            Success status
        """
        with self._lock:
            if not self.reconnect_if_needed():
                return False

            try:
                sftp = self.client.open_sftp()

                # Get file size for progress
                file_size = os.path.getsize(local_path)

                # Upload with progress callback
                def progress_callback(transferred, total):
                    if callback:
                        callback(transferred, total)

                sftp.put(local_path, remote_path, callback=progress_callback)
                sftp.close()

                self.stats.total_bytes_uploaded += file_size
                self.stats.last_activity = datetime.now()

                logger.info(f"Uploaded {local_path} to {remote_path} ({file_size} bytes)")
                return True

            except Exception as e:
                logger.error(f"File upload failed: {e}")
                return False

    def download_file(self, remote_path: str, local_path: str, callback=None) -> bool:
        """
        Download file via SFTP with progress callback.

        Args:
            remote_path: Remote file path
            local_path: Local destination path
            callback: Progress callback function(bytes_transferred, total_bytes)

        Returns:
            Success status
        """
        with self._lock:
            if not self.reconnect_if_needed():
                return False

            try:
                sftp = self.client.open_sftp()

                # Get remote file size
                file_stats = sftp.stat(remote_path)
                file_size = file_stats.st_size

                # Download with progress callback
                def progress_callback(transferred, total):
                    if callback:
                        callback(transferred, total)

                sftp.get(remote_path, local_path, callback=progress_callback)
                sftp.close()

                self.stats.total_bytes_downloaded += file_size
                self.stats.last_activity = datetime.now()

                logger.info(f"Downloaded {remote_path} to {local_path} ({file_size} bytes)")
                return True

            except Exception as e:
                logger.error(f"File download failed: {e}")
                return False

    def sync_directory(self, local_dir: str, remote_dir: str, exclude_patterns: List[str] = None) -> bool:
        """
        Sync entire directory to remote.

        Args:
            local_dir: Local directory path
            remote_dir: Remote directory path
            exclude_patterns: List of patterns to exclude

        Returns:
            Success status
        """
        with self._lock:
            if not self.reconnect_if_needed():
                return False

            try:
                # Create remote directory
                self.execute_command(f"mkdir -p {remote_dir}")

                # Walk local directory
                for root, dirs, files in os.walk(local_dir):
                    # Calculate relative path
                    rel_path = os.path.relpath(root, local_dir)
                    remote_root = os.path.join(remote_dir, rel_path).replace("\\", "/")

                    # Create remote directories
                    if rel_path != ".":
                        self.execute_command(f"mkdir -p {remote_root}")

                    # Upload files
                    for file in files:
                        # Check exclusions
                        if exclude_patterns:
                            skip = False
                            for pattern in exclude_patterns:
                                if fnmatch.fnmatch(file, pattern):
                                    skip = True
                                    break
                            if skip:
                                continue

                        local_file = os.path.join(root, file)
                        remote_file = os.path.join(remote_root, file).replace("\\", "/")

                        if not self.upload_file(local_file, remote_file):
                            logger.warning(f"Failed to upload {local_file}")

                return True

            except Exception as e:
                logger.error(f"Directory sync failed: {e}")
                return False
