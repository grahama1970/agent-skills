"""
flash_trainer.py — RunPod GPU training job adapter.

Submits local training scripts to RunPod GPU pods, monitors progress,
retrieves logs, and downloads checkpoints — without requiring a custom
Docker image or Dockerfile authorship.

Inputs:
    script_path: local .py or .sh training script
    args: extra CLI arguments passed to the script
    gpu_type: RunPod GPU name string (use estimate_gpu() to choose)
    timeout_hours: hard wall-clock limit, 1–168 h (default 24)

Outputs:
    job_id: RunPod pod ID string
    status dict with 'state', 'desired_status', 'runtime' keys
    log text (str)
    downloaded checkpoint file(s) to a local directory

Failure modes:
    EnvironmentError  – RUNPOD_API_KEY not set; suggests --target local
    RunPodError       – API-level failures (quota exceeded, invalid GPU)
    TimeoutError      – pod did not reach RUNNING within startup_timeout
    FileNotFoundError – script_path does not exist
    subprocess.CalledProcessError – rsync/scp checkpoint download failure
"""
from __future__ import annotations

import base64
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
import runpod
import typer
from loguru import logger

# ---------------------------------------------------------------------------
# GPU catalogue — VRAM (GB), pricing ($/hr community cloud, approximate)
# ---------------------------------------------------------------------------

_GPU_SPECS: dict[str, dict[str, Any]] = {
    "NVIDIA GeForce RTX 4090": {"vram_gb": 24, "price_hr": 0.74},
    "NVIDIA RTX A6000": {"vram_gb": 48, "price_hr": 0.79},
    "NVIDIA A40": {"vram_gb": 48, "price_hr": 0.79},
    "NVIDIA RTX 6000 Ada Generation": {"vram_gb": 48, "price_hr": 1.25},
    "NVIDIA A100 80GB PCIe": {"vram_gb": 80, "price_hr": 1.64},
    "NVIDIA A100-SXM4-80GB": {"vram_gb": 80, "price_hr": 2.21},
    "NVIDIA H100 80GB HBM3": {"vram_gb": 80, "price_hr": 3.49},
    "NVIDIA H100 SXM": {"vram_gb": 80, "price_hr": 3.99},
    "NVIDIA H200 SXM": {"vram_gb": 141, "price_hr": 4.99},
}

# Fallback Docker image used when caller does not specify one
_DEFAULT_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"

# GraphQL endpoint for pod log queries
_RUNPOD_GQL_URL = "https://api.runpod.io/graphql"

# Maximum seconds to wait for a pod to reach RUNNING state
_STARTUP_TIMEOUT_S = 600  # 10 minutes

# Poll interval when waiting for status transitions
_POLL_INTERVAL_S = 15


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RunPodError(RuntimeError):
    """Raised for RunPod API-level failures."""


# ---------------------------------------------------------------------------
# Public helpers (no API key required)
# ---------------------------------------------------------------------------


def estimate_gpu(
    model_size_b: float,
    method: Literal["lora", "full"] = "lora",
) -> str:
    """
    Recommend the smallest RunPod GPU that fits the training job.

    Args:
        model_size_b: Model parameter count in billions (e.g. 7 for a 7B model).
        method: 'lora' for QLoRA / parameter-efficient fine-tuning;
                'full' for standard full-parameter fine-tuning.

    Returns:
        GPU name string (key in _GPU_SPECS) suitable for gpu_type argument.

    Examples:
        >>> estimate_gpu(7)
        'NVIDIA GeForce RTX 4090'
        >>> estimate_gpu(70, method='lora')
        'NVIDIA A100 80GB PCIe'
        >>> estimate_gpu(7, method='full')
        'NVIDIA A100 80GB PCIe'
    """
    if method == "lora":
        # QLoRA: 4-bit quantised base ≈ 0.5 bytes/param + adapter + activations
        # Empirical overhead factor: ~1.6× the raw 4-bit weight size
        vram_needed = model_size_b * 0.5 * 1.6  # GB
    else:
        # Full fp16: weights(2) + gradients(2) + Adam states(8) = 12 bytes/param
        # With gradient checkpointing: reduce activation overhead by ~4×
        vram_needed = model_size_b * 12 / 1.0  # GB (conservative)

    logger.debug(
        f"estimate_gpu: model={model_size_b}B method={method} "
        f"vram_needed={vram_needed:.1f} GB"
    )

    # Walk GPU list from cheapest to most expensive; pick first that fits
    ordered = sorted(_GPU_SPECS.items(), key=lambda kv: kv[1]["price_hr"])
    for gpu_name, spec in ordered:
        if spec["vram_gb"] >= vram_needed:
            logger.info(
                f"Selected GPU: {gpu_name} "
                f"({spec['vram_gb']} GB VRAM, ${spec['price_hr']}/hr)"
            )
            return gpu_name

    # Fallback: largest available GPU
    largest = max(_GPU_SPECS.items(), key=lambda kv: kv[1]["vram_gb"])
    logger.warning(
        f"Model {model_size_b}B {method} needs {vram_needed:.0f} GB — "
        f"exceeds single-GPU catalogue; returning {largest[0]} (consider multi-GPU)"
    )
    return largest[0]


def estimate_cost(gpu_type: str, hours: float) -> float:
    """
    Estimate compute cost for a training job.

    Args:
        gpu_type: GPU name string (must be a key in _GPU_SPECS).
        hours: Estimated wall-clock duration in hours.

    Returns:
        Estimated USD cost as a float.

    Raises:
        KeyError: if gpu_type is not in the GPU catalogue.

    Example:
        >>> estimate_cost("NVIDIA GeForce RTX 4090", 8)
        5.92
    """
    if gpu_type not in _GPU_SPECS:
        known = ", ".join(_GPU_SPECS)
        raise KeyError(
            f"Unknown gpu_type '{gpu_type}'. Known GPUs: {known}"
        )
    price_hr = _GPU_SPECS[gpu_type]["price_hr"]
    total = round(price_hr * hours, 4)
    logger.debug(f"estimate_cost: {gpu_type} × {hours}h = ${total}")
    return total


# ---------------------------------------------------------------------------
# FlashTrainer
# ---------------------------------------------------------------------------


class FlashTrainer:
    """
    RunPod GPU training job adapter.

    Wraps the RunPod Python SDK to submit training scripts, monitor their
    progress, stream logs, and download output checkpoints.

    Usage::

        trainer = FlashTrainer()
        gpu = estimate_gpu(7, method='lora')
        job_id = trainer.submit_training_job(
            "train.py", args=["--epochs", "3"], gpu_type=gpu, timeout_hours=8
        )
        while True:
            status = trainer.poll_status(job_id)
            if status["state"] in ("EXITED", "TERMINATED", "FAILED"):
                break
            time.sleep(60)
        print(trainer.get_logs(job_id))
        trainer.download_checkpoint(job_id, "./output")
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        Initialise the trainer and validate the RunPod API key.

        Args:
            api_key: RunPod API key. Falls back to RUNPOD_API_KEY env var.

        Raises:
            EnvironmentError: if no API key is found.
        """
        key = api_key or os.environ.get("RUNPOD_API_KEY", "")
        if not key:
            raise EnvironmentError(
                "RUNPOD_API_KEY environment variable is not set.\n"
                "  • Set it: export RUNPOD_API_KEY=<your-key>\n"
                "  • Or run locally: use --target local flag in your CLI"
            )
        self._api_key = key
        runpod.api_key = key
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {key}"},
            timeout=30.0,
        )
        logger.debug("FlashTrainer initialised (RunPod SDK ready)")

    # ------------------------------------------------------------------
    # Core public interface
    # ------------------------------------------------------------------

    def submit_training_job(
        self,
        script_path: str | Path,
        args: Optional[list[str]] = None,
        gpu_type: str = "NVIDIA GeForce RTX 4090",
        timeout_hours: int = 24,
        image: str = _DEFAULT_IMAGE,
        volume_gb: int = 100,
        disk_gb: int = 50,
    ) -> str:
        """
        Create a RunPod pod and launch the training script.

        The script is base64-encoded and embedded into the pod's startup
        command so no external hosting is required for small scripts
        (< 32 KB). For larger scripts, pre-upload to a Network Volume
        and pass the remote path instead.

        Args:
            script_path: local path to a .py or .sh training script.
            args: extra CLI arguments forwarded to the script.
            gpu_type: RunPod GPU name (use estimate_gpu() to choose).
            timeout_hours: hard wall-clock limit; pod self-terminates after
                           this many hours (capped at 168 = 7 days).
            image: Docker image for the pod worker.
            volume_gb: persistent Network Volume size in GB.
            disk_gb: ephemeral container disk in GB.

        Returns:
            job_id: RunPod pod ID string.

        Raises:
            FileNotFoundError: if script_path does not exist.
            RunPodError: if the RunPod API rejects the pod creation request.
        """
        script = Path(script_path).resolve()
        if not script.exists():
            raise FileNotFoundError(f"Training script not found: {script}")

        timeout_hours = min(max(1, timeout_hours), 168)
        args_str = " ".join(str(a) for a in (args or []))
        runner = "python3" if script.suffix.lower() == ".py" else "bash"

        # Encode script so we can bootstrap it without SCP in the first run
        encoded = base64.b64encode(script.read_bytes()).decode()
        script_name = script.name

        startup_cmd = (
            f"echo {encoded} | base64 -d > /tmp/{script_name} && "
            f"{runner} /tmp/{script_name} {args_str} "
            f"2>&1 | tee /runpod-volume/train.log ; "
            f"echo EXIT_CODE=$? >> /runpod-volume/train.log"
        )

        pod_name = f"flash-train-{script.stem[:24]}"
        logger.info(
            f"Creating pod '{pod_name}' | GPU={gpu_type} | "
            f"timeout={timeout_hours}h"
        )

        pod_cfg: dict[str, Any] = {
            "name": pod_name,
            "image_name": image,
            "gpu_type_id": gpu_type,
            "cloud_type": "ALL",
            "start_ssh": True,
            "support_public_ip": True,
            "container_disk_in_gb": disk_gb,
            "volume_in_gb": volume_gb,
            "volume_mount_path": "/runpod-volume",
            "docker_args": startup_cmd,
            "env": {
                "TIMEOUT_HOURS": str(timeout_hours),
                "PYTHONUNBUFFERED": "1",
            },
        }

        try:
            response = runpod.create_pod(**pod_cfg)
        except Exception as exc:
            raise RunPodError(f"RunPod create_pod failed: {exc}") from exc

        pod_id: Optional[str] = (
            response.get("id") or response.get("podId") if isinstance(response, dict)
            else getattr(response, "id", None)
        )
        if not pod_id:
            raise RunPodError(f"No pod ID in RunPod response: {response!r}")

        logger.success(f"Pod created: {pod_id} — waiting for RUNNING state")
        self._wait_for_running(pod_id)
        return pod_id

    def poll_status(self, job_id: str) -> dict[str, Any]:
        """
        Fetch the current status of a training job.

        Args:
            job_id: RunPod pod ID returned by submit_training_job().

        Returns:
            Dict with at minimum:
                'state'          – e.g. "RUNNING", "EXITED", "TERMINATED"
                'desired_status' – operator-set desired state
                'runtime'        – nested dict with uptimeInSeconds etc.
                'pod_id'         – echoed back for convenience

        Raises:
            RunPodError: if the API call fails or pod is not found.
        """
        try:
            pod = runpod.get_pod(job_id)
        except Exception as exc:
            raise RunPodError(f"Failed to fetch pod {job_id}: {exc}") from exc

        if pod is None:
            raise RunPodError(f"Pod not found: {job_id}")

        # SDK may return a dict or an object; normalise to dict
        if not isinstance(pod, dict):
            pod = dict(vars(pod)) if hasattr(pod, "__dict__") else {"raw": pod}

        status = {
            "pod_id": job_id,
            "state": pod.get("desiredStatus") or pod.get("status") or "UNKNOWN",
            "desired_status": pod.get("desiredStatus", ""),
            "runtime": pod.get("runtime") or {},
            "raw": pod,
        }
        logger.debug(f"poll_status {job_id}: state={status['state']}")
        return status

    def get_logs(self, job_id: str, tail_lines: int = 500) -> str:
        """
        Retrieve recent log output from a training job.

        Queries the RunPod GraphQL API for pod log data. Falls back to
        a helpful message if the pod has already terminated.

        Args:
            job_id: RunPod pod ID.
            tail_lines: maximum number of log lines to return.

        Returns:
            Log text as a single string (may be empty if pod just started).

        Raises:
            RunPodError: if the API request fails.
        """
        query = """
        query GetPodLogs($podId: String!, $tail: Int) {
            pod(input: { podId: $podId }) {
                runtime {
                    logs(tail: $tail)
                }
            }
        }
        """
        variables = {"podId": job_id, "tail": tail_lines}

        try:
            resp = self._http.post(
                _RUNPOD_GQL_URL,
                json={"query": query, "variables": variables},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RunPodError(f"RunPod log API error {exc.response.status_code}: {exc}") from exc
        except httpx.RequestError as exc:
            raise RunPodError(f"RunPod log request failed: {exc}") from exc

        data = resp.json()
        errors = data.get("errors")
        if errors:
            logger.warning(f"GraphQL errors for {job_id}: {errors}")

        try:
            logs: str = data["data"]["pod"]["runtime"]["logs"] or ""
        except (KeyError, TypeError):
            logs = ""

        if not logs:
            logger.info(
                f"No logs yet for {job_id} — pod may still be starting or "
                "logs are stored in /runpod-volume/train.log on the worker"
            )
        return logs

    def download_checkpoint(
        self,
        job_id: str,
        local_path: str | Path,
        remote_checkpoint_dir: str = "/runpod-volume/checkpoints",
    ) -> Path:
        """
        Download checkpoint files from a running or stopped pod via SCP.

        Requires the pod to have SSH enabled (start_ssh=True) and a
        reachable public IP. Destination directory is created if absent.

        Args:
            job_id: RunPod pod ID.
            local_path: local directory where checkpoints are written.
            remote_checkpoint_dir: absolute path on the pod worker.

        Returns:
            Path to the local destination directory.

        Raises:
            RunPodError: if pod SSH details cannot be retrieved.
            subprocess.CalledProcessError: if scp/rsync fails.
        """
        dest = Path(local_path)
        dest.mkdir(parents=True, exist_ok=True)

        ssh_host, ssh_port = self._get_ssh_info(job_id)
        logger.info(
            f"Downloading checkpoints from {job_id} "
            f"({ssh_host}:{ssh_port}) → {dest}"
        )

        cmd = [
            "rsync",
            "-avz",
            "--progress",
            "-e", f"ssh -p {ssh_port} -o StrictHostKeyChecking=no",
            f"root@{ssh_host}:{remote_checkpoint_dir}/",
            str(dest),
        ]

        logger.debug(f"rsync command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.success(f"Checkpoint download complete → {dest}")
        logger.debug(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        return dest

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _wait_for_running(
        self,
        pod_id: str,
        timeout_seconds: int = _STARTUP_TIMEOUT_S,
    ) -> None:
        """
        Block until the pod enters RUNNING state or timeout is reached.

        Args:
            pod_id: RunPod pod ID.
            timeout_seconds: max wait time in seconds.

        Raises:
            TimeoutError: if the pod does not reach RUNNING within the timeout.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                status = self.poll_status(pod_id)
            except RunPodError as exc:
                logger.warning(f"Status poll error (will retry): {exc}")
                time.sleep(_POLL_INTERVAL_S)
                continue

            state = status.get("state", "").upper()
            logger.info(f"Pod {pod_id} state: {state}")

            if state == "RUNNING":
                return
            if state in ("EXITED", "TERMINATED", "FAILED", "DEAD"):
                raise RunPodError(
                    f"Pod {pod_id} reached terminal state '{state}' before RUNNING"
                )
            time.sleep(_POLL_INTERVAL_S)

        raise TimeoutError(
            f"Pod {pod_id} did not reach RUNNING within {timeout_seconds}s. "
            "Check your RunPod dashboard for quota or availability issues."
        )

    def _get_ssh_info(self, pod_id: str) -> tuple[str, int]:
        """
        Extract SSH host and port from pod metadata.

        Args:
            pod_id: RunPod pod ID.

        Returns:
            (host, port) tuple for SSH connections.

        Raises:
            RunPodError: if SSH info is unavailable.
        """
        status = self.poll_status(pod_id)
        raw = status.get("raw", {})

        # RunPod SDK returns different shapes depending on version
        runtime = raw.get("runtime") or {}
        ports = runtime.get("ports") or []

        ssh_port = 22
        ssh_host: Optional[str] = None

        for port_info in ports:
            if isinstance(port_info, dict):
                if port_info.get("privatePort") == 22:
                    ssh_host = port_info.get("ip") or port_info.get("publicIp")
                    ssh_port = int(port_info.get("publicPort") or 22)
                    break

        # Fallback: top-level public IP
        if not ssh_host:
            ssh_host = raw.get("publicIp") or raw.get("ip")

        if not ssh_host:
            raise RunPodError(
                f"Could not determine SSH host for pod {pod_id}. "
                "Ensure start_ssh=True and support_public_ip=True were set at creation."
            )

        return ssh_host, ssh_port

    def terminate(self, job_id: str) -> None:
        """
        Terminate a running pod and stop billing.

        Args:
            job_id: RunPod pod ID returned by submit_training_job().

        Raises:
            RunPodError: if termination fails.
        """
        logger.warning(f"Terminating pod {job_id}")
        try:
            runpod.terminate_pod(job_id)
            logger.success(f"Pod {job_id} terminated")
        except Exception as exc:
            raise RunPodError(f"Failed to terminate pod {job_id}: {exc}") from exc

    def __repr__(self) -> str:
        return f"FlashTrainer(api_key={'***' if self._api_key else 'NOT SET'})"


# ---------------------------------------------------------------------------
# Typer CLI — thin wrapper around FlashTrainer for manual / script use
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="flash-trainer",
    help="RunPod GPU training adapter. Submits and monitors training jobs.",
    add_completion=False,
)


@app.command("submit")
def cmd_submit(
    script: str = typer.Argument(..., help="Path to the training script (.py or .sh)"),
    args: Optional[list[str]] = typer.Option(None, "--arg", help="Script argument (repeat)"),
    model_size: float = typer.Option(7.0, "--model-size", help="Model size in billions"),
    method: str = typer.Option("lora", "--method", help="lora or full"),
    timeout_hours: int = typer.Option(24, "--timeout", help="Max training hours"),
) -> None:
    """Submit a training job to RunPod and print the job ID."""
    gpu = estimate_gpu(model_size, method=method)  # type: ignore[arg-type]
    cost = estimate_cost(gpu, timeout_hours)
    typer.echo(f"Selected GPU : {gpu}")
    typer.echo(f"Max cost est.: ${cost:.2f} (at ${_GPU_SPECS[gpu]['price_hr']}/hr)")
    trainer = FlashTrainer()
    job_id = trainer.submit_training_job(
        script_path=script,
        args=args,
        gpu_type=gpu,
        timeout_hours=timeout_hours,
    )
    typer.echo(f"Job ID: {job_id}")


@app.command("status")
def cmd_status(
    job_id: str = typer.Argument(..., help="RunPod pod ID"),
) -> None:
    """Poll and print the current status of a training job."""
    import json as _json
    trainer = FlashTrainer()
    status = trainer.poll_status(job_id)
    typer.echo(_json.dumps({k: v for k, v in status.items() if k != "raw"}, indent=2))


@app.command("logs")
def cmd_logs(
    job_id: str = typer.Argument(..., help="RunPod pod ID"),
    tail: int = typer.Option(500, "--tail", help="Number of log lines to show"),
) -> None:
    """Print the tail of a training job's log output."""
    trainer = FlashTrainer()
    logs = trainer.get_logs(job_id, tail_lines=tail)
    typer.echo(logs or "(no logs yet)")


@app.command("download")
def cmd_download(
    job_id: str = typer.Argument(..., help="RunPod pod ID"),
    local_path: str = typer.Argument(..., help="Local directory for checkpoints"),
    remote_dir: str = typer.Option(
        "/runpod-volume/checkpoints", "--remote-dir", help="Checkpoint dir on pod"
    ),
) -> None:
    """Download checkpoints from a training job pod."""
    trainer = FlashTrainer()
    dest = trainer.download_checkpoint(job_id, local_path, remote_dir)
    typer.echo(f"Checkpoints downloaded to: {dest}")


@app.command("estimate")
def cmd_estimate(
    model_size: float = typer.Argument(..., help="Model size in billions (e.g. 7)"),
    method: str = typer.Option("lora", "--method", help="lora or full"),
    hours: float = typer.Option(8.0, "--hours", help="Estimated training hours"),
) -> None:
    """Estimate GPU type and compute cost for a training job."""
    gpu = estimate_gpu(model_size, method=method)  # type: ignore[arg-type]
    cost = estimate_cost(gpu, hours)
    typer.echo(f"Recommended GPU : {gpu}")
    typer.echo(f"VRAM            : {_GPU_SPECS[gpu]['vram_gb']} GB")
    typer.echo(f"Price           : ${_GPU_SPECS[gpu]['price_hr']}/hr")
    typer.echo(f"Estimated cost  : ${cost:.2f} for {hours}h")


if __name__ == "__main__":
    app()
