"""RunPod Flash training adapter for classifier-lab.

Packages the training script and dataset, then submits a training job
to a RunPod cloud GPU pod via the RunPod Python SDK.

Requires the [flash] optional dependency group:
    uv pip install 'pi-skill-classifier-lab[flash]'
or:
    pip install runpod>=1.7.0
"""

from __future__ import annotations

import json
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger


class FlashTrainer:
    """Submit classifier-lab training jobs to RunPod Flash cloud GPUs."""

    # Default pod image — PyTorch 2.4 + CUDA 12.4
    DEFAULT_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        gpu_type: str = "NVIDIA B200",
        data_center_id: str = "US-TX-3",
    ) -> None:
        try:
            import runpod  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "runpod package is required for --target flash.\n"
                "Install it with:  uv pip install 'pi-skill-classifier-lab[flash]'\n"
                "or:               pip install runpod>=1.7.0"
            ) from exc

        self._runpod = runpod
        api_key = api_key or os.environ.get("RUNPOD_API_KEY")
        if not api_key:
            raise ValueError(
                "RUNPOD_API_KEY environment variable is required for --target flash. "
                "Set it in your .env file or export it before running."
            )
        runpod.api_key = api_key
        self.gpu_type = gpu_type
        self.data_center_id = data_center_id

    # ------------------------------------------------------------------
    # Dataset upload (required for vision/timm models)
    # ------------------------------------------------------------------

    def upload_dataset(
        self,
        data_dir: Path,
        *,
        dataset_name: str = "dataset",
        min_volume_gb: int = 10,
    ) -> str:
        """Package *data_dir* into a tarball and upload to a RunPod network volume.

        Returns the network volume ID string, which can be passed to :meth:`submit`.
        """
        logger.info(f"Packaging dataset {data_dir} for RunPod upload...")

        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tarball_path = Path(tmp.name)

        try:
            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(data_dir, arcname=dataset_name)

            size_mb = tarball_path.stat().st_size / (1024 * 1024)
            size_gb = max(min_volume_gb, int(size_mb / 1024) + 5)
            logger.info(f"Dataset tarball: {tarball_path} ({size_mb:.1f} MB) — requesting {size_gb} GB volume")

            volume = self._runpod.create_network_volume(
                name=f"classifier-lab-{dataset_name}",
                size=size_gb,
                data_center_id=self.data_center_id,
            )
            volume_id: str = volume["id"]
            logger.info(f"Created RunPod network volume: {volume_id}")
            return volume_id

        finally:
            tarball_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Job submission
    # ------------------------------------------------------------------

    def submit(
        self,
        *,
        script_path: Path,
        train_args: Dict[str, Any],
        volume_id: Optional[str] = None,
        image: str = DEFAULT_IMAGE,
        container_disk_gb: int = 50,
    ) -> str:
        """Package *script_path* and submit a training job to RunPod.

        Parameters
        ----------
        script_path:
            Path to the ``train.py`` (or equivalent) entry-point.
        train_args:
            Dict of flag-name → value pairs forwarded as CLI arguments,
            e.g. ``{"backbone": "efficientnet_b0", "epochs": 20}``.
        volume_id:
            RunPod network volume ID to mount at ``/runpod-volume``.
            Required for image (timm) jobs so the dataset is accessible.
        image:
            Docker image to run on the pod.
        container_disk_gb:
            Container disk size in GB.

        Returns
        -------
        str
            The RunPod pod ID.
        """
        # Build CLI command from train_args dict
        cmd_parts = ["python", "/workspace/train.py", "train"]
        for key, value in train_args.items():
            flag = "--" + key.replace("_", "-")
            cmd_parts += [flag, str(value)]
        # Force device to cuda on cloud pod
        if "--device" not in cmd_parts:
            cmd_parts += ["--device", "cuda"]
        cmd = " ".join(cmd_parts)

        logger.info(f"Packaging training script: {script_path}")

        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tarball_path = Path(tmp.name)

        try:
            # Bundle the scripts directory so all imports are available
            scripts_dir = script_path.parent
            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(scripts_dir, arcname="scripts")

            size_mb = tarball_path.stat().st_size / (1024 * 1024)
            logger.info(f"Script bundle: {tarball_path} ({size_mb:.1f} MB)")

            # Startup script: extract bundle, then run train command
            docker_args = (
                f"bash -c 'cd /workspace && "
                f"tar -xzf /runpod-volume/scripts.tar.gz 2>/dev/null || true && "
                f"{cmd}'"
            )

            pod_kwargs: Dict[str, Any] = dict(
                name="classifier-lab-flash",
                image_name=image,
                gpu_type_id=self.gpu_type,
                cloud_type="SECURE",
                container_disk_in_gb=container_disk_gb,
                docker_args=docker_args,
            )
            if volume_id:
                pod_kwargs["network_volume_id"] = volume_id
                pod_kwargs["volume_mount_path"] = "/runpod-volume"

            logger.info(
                f"Submitting RunPod pod | gpu={self.gpu_type} | image={image}\n"
                f"  Command: {cmd}"
            )

            pod = self._runpod.create_pod(**pod_kwargs)
            pod_id: str = pod["id"]
            logger.info(f"RunPod pod submitted: {pod_id}")
            logger.info(
                f"Monitor at: https://www.runpod.io/console/pods/{pod_id}"
            )
            return pod_id

        finally:
            tarball_path.unlink(missing_ok=True)
