#!/usr/bin/env python3
"""Runpod Flash probe for the persona-dream NAVA lane.

This is intentionally a probe, not the full NAVA render. It verifies that Flash
can provision a remote CUDA worker and report GPU capacity before we attempt a
heavy NAVA install/checkpoint run. The full NAVA render should use a persistent
Runpod Pod if local A5000 fp8 inference is not viable.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

# Flash resolves deployed endpoints by app/env/name. If FLASH_APP is unset it
# defaults to the current directory name, which is fragile for copied probes.
os.environ.setdefault("FLASH_APP", "persona-dream-nava-probe")
os.environ.setdefault("FLASH_ENV", "production")
os.environ.setdefault("FLASH_SENTINEL_TIMEOUT", "180")

from runpod_flash import Endpoint, GpuGroup


@Endpoint(
    name="persona-dream-nava-flash-probe",
    gpu=GpuGroup.ANY,
    workers=1,
    idle_timeout=300,
    execution_timeout_ms=180_000,
    dependencies=["torch"],
)
def nava_flash_cuda_probe() -> dict[str, object]:
    import torch

    return {
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "memory_total_bytes": torch.cuda.get_device_properties(0).total_memory
        if torch.cuda.is_available()
        else None,
    }


async def main() -> None:
    result = await nava_flash_cuda_probe()
    receipt = {
        "status": "SUCCESS",
        "flash_app": os.environ["FLASH_APP"],
        "flash_env": os.environ["FLASH_ENV"],
        "endpoint_name": "persona-dream-nava-flash-probe",
        **result,
        "successful_command_shape": (
            "source ~/.zshrc; python "
            "skills/persona-dream/research/bakeoff/scripts/runpod_flash_nava_probe.py"
        ),
        "diagnosis": (
            "Runpod Flash can provision a CUDA worker for this probe. Earlier failures were "
            "caused by invoking the deployed endpoint through the wrong app namespace and then "
            "by using raw /runsync instead of the Flash SDK/sentinel call shape."
        ),
        "remaining_nava_runtime_issue": (
            "This confirms remote CUDA only. Full NAVA still needs checkpoint staging/caching "
            "and likely a larger GPU or persistent Runpod Pod if a 24GB worker is insufficient."
        ),
    }
    out = Path("/tmp/persona-dream-elevenlabs-baseline/nava_lane/runpod_flash_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    print(f"[runpod-flash] wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
