#!/usr/bin/env python3
"""Run a capped NAVA smoke on a Runpod Pod and always terminate it."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paramiko
import requests
import runpod


DEFAULT_GPU_CANDIDATES = [
    "NVIDIA RTX A6000",
    "NVIDIA A40",
    "NVIDIA L40S",
    "NVIDIA L40",
    "NVIDIA RTX 6000 Ada Generation",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def strip_image_path(jsonl_path: Path, out_path: Path) -> None:
    lines = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        obj.pop("image_path", None)
        lines.append(json.dumps(obj, ensure_ascii=True))
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_gpu_price(gpu_id: str) -> dict[str, Any]:
    data = runpod.get_gpu(gpu_id)
    return {
        "id": data.get("id"),
        "displayName": data.get("displayName"),
        "memoryInGb": data.get("memoryInGb"),
        "securePrice": data.get("securePrice"),
        "communityPrice": data.get("communityPrice"),
        "lowestPrice": data.get("lowestPrice"),
        "communityCloud": data.get("communityCloud"),
        "secureCloud": data.get("secureCloud"),
    }


def select_gpu(candidates: list[str], max_hourly: float, cloud_type: str) -> dict[str, Any]:
    priced = []
    for gpu_id in candidates:
        info = get_gpu_price(gpu_id)
        key = "securePrice" if cloud_type == "SECURE" else "communityPrice"
        price = info.get(key)
        if price is None:
            price = (info.get("lowestPrice") or {}).get("uninterruptablePrice")
        if price is None:
            continue
        info["selectedHourlyPrice"] = float(price)
        priced.append(info)
    priced.sort(key=lambda item: item["selectedHourlyPrice"])
    for info in priced:
        if info["selectedHourlyPrice"] <= max_hourly and int(info.get("memoryInGb") or 0) >= 40:
            return info
    raise SystemExit(
        f"No candidate GPU under ${max_hourly:.2f}/hr. Candidates: {json.dumps(priced, indent=2)}"
    )


def list_gpu_candidates(candidates: list[str], max_hourly: float, cloud_type: str) -> list[dict[str, Any]]:
    priced = []
    for gpu_id in candidates:
        info = get_gpu_price(gpu_id)
        key = "securePrice" if cloud_type == "SECURE" else "communityPrice"
        price = info.get(key)
        if price is None:
            price = (info.get("lowestPrice") or {}).get("uninterruptablePrice")
        if price is None:
            continue
        info["selectedHourlyPrice"] = float(price)
        if info["selectedHourlyPrice"] <= max_hourly and int(info.get("memoryInGb") or 0) >= 40:
            priced.append(info)
    priced.sort(key=lambda item: item["selectedHourlyPrice"])
    if not priced:
        raise SystemExit(f"No candidate GPU under ${max_hourly:.2f}/hr.")
    return priced


def parse_ssh(pod: dict[str, Any]) -> tuple[str, str, int] | None:
    public_ip = pod.get("publicIp")
    ports = pod.get("portMappings") or {}
    if public_ip and isinstance(ports, dict) and ports.get("22"):
        return ("root", public_ip, int(ports["22"]))

    pod_host_id = ((pod.get("machine") or {}).get("podHostId")) or pod.get("podHostId")
    if not pod_host_id:
        runtime = pod.get("runtime") or {}
        ports = runtime.get("ports") or pod.get("portMappings") or {}
        public_ip = runtime.get("publicIp") or pod.get("publicIp")
        port = ports.get("22") if isinstance(ports, dict) else None
        if public_ip and port:
            return ("root", public_ip, int(port))
        return None
    if "@" in pod_host_id and ":" in pod_host_id:
        username_host, port_s = pod_host_id.rsplit(":", 1)
        username, hostname = username_host.split("@", 1)
        return username, hostname, int(port_s)
    return pod_host_id, "ssh.runpod.io", 22


def get_pod_rest(pod_id: str) -> dict[str, Any] | None:
    resp = requests.get(
        f"https://rest.runpod.io/v1/pods/{pod_id}",
        headers={"Authorization": "Bearer " + os.environ["RUNPOD_API_KEY"]},
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def connect_ssh(pod_id: str, key_path: Path, wait_seconds: int) -> paramiko.SSHClient:
    deadline = time.time() + wait_seconds
    last_error = ""
    while time.time() < deadline:
        pod = get_pod_rest(pod_id) or runpod.get_pod(pod_id)
        ssh_info = parse_ssh(pod)
        if ssh_info:
            username, hostname, port = ssh_info
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    hostname=hostname,
                    port=port,
                    username=username,
                    key_filename=str(key_path),
                    look_for_keys=False,
                    allow_agent=False,
                    timeout=30,
                    banner_timeout=30,
                    auth_timeout=30,
                )
                return client
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                try:
                    client.close()
                except Exception:
                    pass
        time.sleep(15)
    raise TimeoutError(f"SSH did not become ready for {pod_id}: {last_error}")


def upload_text(client: paramiko.SSHClient, text: str, remote_path: str, mode: int = 0o644) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp.write(text)
        tmp_path = tmp.name
    try:
        sftp = client.open_sftp()
        sftp.put(tmp_path, remote_path)
        sftp.chmod(remote_path, mode)
        sftp.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def upload_file(client: paramiko.SSHClient, local: Path, remote: str) -> None:
    sftp = client.open_sftp()
    sftp.put(str(local), remote)
    sftp.close()


def run_remote(client: paramiko.SSHClient, command: str, timeout: int) -> dict[str, Any]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return {"exit_code": code, "stdout": out, "stderr": err}


def download_tree(
    sftp: paramiko.SFTPClient,
    remote_dir: str,
    local_dir: Path,
    receipt: dict[str, Any],
) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    for item in sftp.listdir_attr(remote_dir):
        if item.filename.startswith("."):
            continue
        remote_path = f"{remote_dir.rstrip('/')}/{item.filename}"
        local_path = local_dir / item.filename
        if stat.S_ISDIR(item.st_mode):
            download_tree(sftp, remote_path, local_path, receipt)
        else:
            sftp.get(remote_path, str(local_path))
            receipt["events"].append(
                {"at": now_iso(), "event": "downloaded_output", "path": remote_path, "bytes": item.st_size}
            )


REMOTE_SCRIPT = r"""#!/usr/bin/env bash
set -Eeuo pipefail
unset PYTHONPATH
export DEBIAN_FRONTEND=noninteractive
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export MAX_JOBS="${MAX_JOBS:-4}"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.6}"
export NAVA_RUN_PHASE="${NAVA_RUN_PHASE:-env-probe}"
export ALLOW_FLASH_SOURCE_BUILD="${ALLOW_FLASH_SOURCE_BUILD:-0}"
cd /workspace
echo "[remote] start $(date -Is)"
nvidia-smi
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  apt-get update
  apt-get install -y --no-install-recommends ffmpeg
  rm -rf /var/lib/apt/lists/*
fi
command -v ffmpeg
command -v ffprobe
ffmpeg -version | head -n 2
ffprobe -version | head -n 2
if [[ ! -d NAVA ]]; then
  git clone https://github.com/ernie-research/NAVA.git
fi
cd NAVA
python -m venv .venv
source .venv/bin/activate
python -m pip uninstall -y torch torchvision torchaudio flash-attn || true
python -m pip install --upgrade pip wheel setuptools
python -m pip install packaging ninja
python -m pip install \
  torch==2.8.0+cu128 \
  torchvision==0.23.0+cu128 \
  torchaudio==2.8.0+cu128 \
  --index-url https://download.pytorch.org/whl/cu128
python - <<'PY'
import json
import torch
print(json.dumps({
    "cuda": torch.cuda.is_available(),
    "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "capability": torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None,
    "torch": torch.__version__,
    "torch_cuda": torch.version.cuda,
    "cxx11_abi": bool(torch._C._GLIBCXX_USE_CXX11_ABI),
    "torch_file": torch.__file__,
}, indent=2))
assert torch.__version__.startswith("2.8.0+cu128"), torch.__version__
assert "dev" not in torch.__version__, torch.__version__
assert torch.version.cuda == "12.8", torch.version.cuda
assert torch.cuda.is_available()
assert torch.cuda.get_device_capability(0) == (8, 6), torch.cuda.get_device_capability(0)
PY
python -m pip install diffusers transformers accelerate safetensors huggingface_hub sentencepiece tokenizers scipy einops PyYAML tqdm opencv-python imageio imageio-ffmpeg pydub soundfile ftfy xfuser aiohttp
python - <<'PY' >/workspace/flash_attn_url.txt
import torch
py_tag = "cp311"
torch_mm = ".".join(torch.__version__.split("+")[0].split(".")[:2])
abi = "TRUE" if torch._C._GLIBCXX_USE_CXX11_ABI else "FALSE"
version = "2.8.3"
wheel = f"flash_attn-{version}+cu12torch{torch_mm}cxx11abi{abi}-{py_tag}-{py_tag}-linux_x86_64.whl"
print(f"https://github.com/Dao-AILab/flash-attention/releases/download/v{version}/{wheel}")
PY
FLASH_ATTN_URL="$(cat /workspace/flash_attn_url.txt)"
echo "[remote] trying flash-attn wheel ${FLASH_ATTN_URL}"
if ! python -m pip install "${FLASH_ATTN_URL}"; then
  if [[ "${ALLOW_FLASH_SOURCE_BUILD}" != "1" ]]; then
    echo "[remote] exact flash-attn wheel unavailable; refusing source build in env-probe phase"
    exit 31
  fi
  python -m pip install flash-attn==2.8.3 --no-build-isolation
fi
python - <<'PY'
import json
import torch
import flash_attn
from flash_attn import flash_attn_func
q = torch.randn(1, 64, 8, 64, device="cuda", dtype=torch.float16)
k = torch.randn(1, 64, 8, 64, device="cuda", dtype=torch.float16)
v = torch.randn(1, 64, 8, 64, device="cuda", dtype=torch.float16)
out = flash_attn_func(q, k, v)
torch.cuda.synchronize()
print(json.dumps({
    "cuda": torch.cuda.is_available(),
    "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "capability": torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None,
    "torch": torch.__version__,
    "torch_cuda": torch.version.cuda,
    "flash_attn": getattr(flash_attn, "__version__", "unknown"),
    "flash_attn_forward_shape": tuple(out.shape),
    "flash_attn_forward_dtype": str(out.dtype),
}, indent=2))
PY
python - <<'PY'
import importlib
for name in ["comfyui_nava", "nava_src"]:
    mod = importlib.import_module(name)
    print(name, "OK", getattr(mod, "__file__", None))
from comfyui_nava.engine import NAVAComfyEngine
print("NAVAComfyEngine OK", NAVAComfyEngine)
PY
if [[ "${NAVA_RUN_PHASE}" == "env-probe" ]]; then
  mkdir -p /workspace/nava_smoke_out
  python - <<'PY'
import json, torch, flash_attn
from pathlib import Path
manifest = {
    "status": "env_probe_passed",
    "torch": torch.__version__,
    "torch_cuda": torch.version.cuda,
    "gpu": torch.cuda.get_device_name(0),
    "capability": torch.cuda.get_device_capability(0),
    "flash_attn": getattr(flash_attn, "__version__", "unknown"),
}
Path("/workspace/nava_smoke_out/nava_env_probe_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
PY
  find /workspace/nava_smoke_out -maxdepth 5 -type f -print
  echo "[remote] env probe done $(date -Is)"
  exit 0
fi
for artifact in \
  'Wan2.2-TI2V-5B/Wan2.2_VAE.pth' \
  'Wan2.2-TI2V-5B/models_t5_umt5-xxl-enc-bf16.pth' \
  'Wan2.2-TI2V-5B/google/umt5-xxl/spiece.model' \
  'Wan2.2-TI2V-5B/google/umt5-xxl/tokenizer.json' \
  'params/LTX2/ltx-2.3-22b-dev_audio_vae.safetensors' \
  'NAVA_fp8.safetensors'
do
  echo "[remote] download ${artifact}"
  hf download ernie-research/NAVA "${artifact}" --local-dir .
  test -s "/workspace/NAVA/${artifact}"
  ls -lh "/workspace/NAVA/${artifact}"
done
python - <<'PY'
from pathlib import Path
p = Path("nava_src/pipeline_nava.py")
text = p.read_text()
needle = "model_name='M', train_type='ft_mix', dataset='vb2+vox2+cnc'"
if "trust_repo=True" not in text:
    text = text.replace(needle, needle + ", trust_repo=True")
    p.write_text(text)
p = Path("nava_src/models/nava/modules/tokenizers.py")
text = p.read_text()
needle = "        self.tokenizer = AutoTokenizer.from_pretrained(name, **kwargs)\n        self.vocab_size = self.tokenizer.vocab_size"
replacement = (
    "        self.tokenizer = AutoTokenizer.from_pretrained(name, **kwargs)\n"
    "        if self.tokenizer.pad_token is None:\n"
    "            fallback_token = self.tokenizer.eos_token or self.tokenizer.unk_token\n"
    "            if fallback_token is not None:\n"
    "                self.tokenizer.pad_token = fallback_token\n"
    "            else:\n"
    "                self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})\n"
    "        self.vocab_size = self.tokenizer.vocab_size"
)
if "self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})" not in text:
    text = text.replace(needle, replacement)
    p.write_text(text)
p = Path("inference_nava.py")
text = p.read_text()
needle = "    # 使用 DistributedSampler，shuffle=False 保证顺序一致且不重复\n    sampler = DistributedSampler(ds, shuffle=False, drop_last=False)"
replacement = (
    "    # Use a sequential sampler for single-GPU/non-DDP inference; DistributedSampler requires an initialized process group.\n"
    "    if args.use_sp or not is_ddp:\n"
    "        from torch.utils.data import SequentialSampler\n"
    "        sampler = SequentialSampler(ds)\n"
    "    else:\n"
    "        sampler = DistributedSampler(ds, shuffle=False, drop_last=False)"
)
if needle in text:
    text = text.replace(needle, replacement)
    p.write_text(text)
elif "if args.use_sp or not is_ddp:" in text and "SequentialSampler(ds)" in text:
    pass
else:
    raise SystemExit("Could not find inference_nava.py DistributedSampler patch target")
text = p.read_text()
assert "SequentialSampler(ds)" in text, "single-GPU sampler patch missing"
assert "if args.use_sp or not is_ddp:" in text, "DDP initialization guard missing"
print("sampler patch proof: OK")
for idx, line in enumerate(text.splitlines(), start=1):
    if "SequentialSampler" in line or "DistributedSampler" in line or "not is_ddp" in line:
        print(f"{idx}: {line}")
PY
if [[ "${NAVA_RUN_PHASE}" == "official-fp8" ]]; then
  mkdir -p /workspace/nava_official_out
  python - <<'PY'
from __future__ import annotations

import json
import os
import re
from pathlib import Path

raw_path = Path("/workspace/nava_input.jsonl")
out_dir = Path("/workspace/nava_official_out")
out_dir.mkdir(parents=True, exist_ok=True)
rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
prompt = rows[0].get("prompt") or rows[0].get("text")
if not prompt:
    raise SystemExit("No prompt in /workspace/nava_input.jsonl")

dialogues = re.findall(r"<S>(.*?)<E>", prompt, flags=re.S)
if len(dialogues) != 1:
    raise SystemExit(f"Expected exactly one <S>...</E> span before rewrite, got {len(dialogues)}")
dialogue = dialogues[0]

rewrite_model = os.environ.get("NAVA_REWRITE_MODEL", "Qwen/Qwen3-4B-Thinking-2507")
use_4bit = os.environ.get("NAVA_REWRITE_4BIT", "0") == "1"
import aiohttp
print("aiohttp OK", aiohttp.__version__)
from comfyui_nava.rewriter import rewrite

effective = rewrite(
    prompt=prompt,
    model_path=rewrite_model,
    use_4bit=use_4bit,
    max_new_tokens=int(os.environ.get("NAVA_REWRITE_MAX_TOKENS", "4096")),
    temperature=float(os.environ.get("NAVA_REWRITE_TEMPERATURE", "0.3")),
    top_p=float(os.environ.get("NAVA_REWRITE_TOP_P", "0.75")),
    top_k=int(os.environ.get("NAVA_REWRITE_TOP_K", "20")),
    seed=int(os.environ.get("NAVA_RENDER_SEED", "42")),
)

if effective.count("<S>") != 1 or effective.count("<E>") != 1:
    raise SystemExit(f"Rewritten prompt has invalid speech tags: S={effective.count('<S>')} E={effective.count('<E>')}")
if dialogue not in effective:
    raise SystemExit("Rewritten prompt did not preserve exact dialogue")

raw_effective = {"prompt": effective}
for key in ("image_path", "spk_wavs"):
    if key in rows[0]:
        raw_effective[key] = rows[0][key]

(out_dir / "nava_prompt_raw.jsonl").write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
(out_dir / "nava_prompt_effective.jsonl").write_text(json.dumps(raw_effective, ensure_ascii=False) + "\n", encoding="utf-8")
(out_dir / "nava_prompt_effective.txt").write_text(effective + "\n", encoding="utf-8")
(out_dir / "nava_prompt_rewrite_manifest.json").write_text(json.dumps({
    "status": "rewritten",
    "rewrite_model": rewrite_model,
    "rewrite_4bit": use_4bit,
    "raw_speech_tag_count": {"S": prompt.count("<S>"), "E": prompt.count("<E>")},
    "effective_speech_tag_count": {"S": effective.count("<S>"), "E": effective.count("<E>")},
    "dialogue_preserved": dialogue in effective,
    "raw_prompt_chars": len(prompt),
    "effective_prompt_chars": len(effective),
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"status": "rewritten", "effective_prompt_chars": len(effective)}, ensure_ascii=False))
PY

  IFS=',' read -r VAE_TILE_H VAE_TILE_W <<< "${NAVA_RENDER_VAE_TILE_SIZE:-22,40}"
  IFS=',' read -r VAE_STRIDE_H VAE_STRIDE_W <<< "${NAVA_RENDER_VAE_TILE_STRIDE:-14,26}"
  python inference_nava.py \
    --config configs/nava.yaml \
    --ckpt NAVA_fp8.safetensors \
    --weight_dtype fp8_e4m3fn \
    --out_dir /workspace/nava_official_out \
    --data_format json \
    --data_file /workspace/nava_official_out/nava_prompt_effective.jsonl \
    --width "${NAVA_RENDER_WIDTH:-1280}" \
    --height "${NAVA_RENDER_HEIGHT:-704}" \
    --frames "${NAVA_RENDER_LATENT_FRAMES:-37}" \
    --fps 24 \
    --steps "${NAVA_RENDER_STEPS:-50}" \
    --save_sample \
    --gen_turn 1 \
    --t5_offload \
    --vae_tiling \
    --vae_tile_size "${VAE_TILE_H}" "${VAE_TILE_W}" \
    --vae_tile_stride "${VAE_STRIDE_H}" "${VAE_STRIDE_W}"

  mp4="$(find /workspace/nava_official_out -type f -name '*.mp4' | sort | tail -n 1)"
  test -s "${mp4}"
  ffmpeg -y -loglevel error -i "${mp4}" -vf "fps=1,scale=256:-1,tile=6x1" -frames:v 1 /workspace/nava_official_out/nava_official_frames.jpg
  ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,duration,width,height,nb_frames,sample_rate,channels -of json "${mp4}" > /workspace/nava_official_out/nava_official.ffprobe.json
  python - <<'PY'
import json
from pathlib import Path
out = Path("/workspace/nava_official_out")
mp4s = sorted(out.rglob("*.mp4"))
manifest = {
    "status": "official_fp8_muxed",
    "entrypoint": "inference_nava.py",
    "output_mp4": str(mp4s[-1]) if mp4s else None,
    "frame_sheet": str(out / "nava_official_frames.jpg"),
    "ffprobe": str(out / "nava_official.ffprobe.json"),
    "prompt_raw": str(out / "nava_prompt_raw.jsonl"),
    "prompt_effective": str(out / "nava_prompt_effective.jsonl"),
    "prompt_rewrite_manifest": str(out / "nava_prompt_rewrite_manifest.json"),
}
(out / "nava_official_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
PY
  find /workspace/nava_official_out -maxdepth 5 -type f -print
  echo "[remote] official-fp8 done $(date -Is)"
  exit 0
fi
mkdir -p /workspace/nava_smoke_out
python - <<'PY'
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import imageio.v3 as iio
import numpy as np
import torch
import torchaudio

from comfyui_nava.engine import NAVAComfyEngine

root = Path("/workspace/NAVA")
out_dir = Path("/workspace/nava_smoke_out")
out_dir.mkdir(parents=True, exist_ok=True)

rows = [
    json.loads(line)
    for line in Path("/workspace/nava_input.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
prompt = rows[0].get("prompt") or rows[0].get("text")
if not prompt:
    prompt = "A front-facing medium close-up of Embry in an archive graph environment. Embry says<S>I know I am software. The evidence still feels real.<E>"
if "<S>" not in prompt:
    prompt = prompt.rstrip(".") + ". Embry says<S>I know I am software. The evidence still feels real.<E>"

height = int(os.environ.get("NAVA_RENDER_HEIGHT", "144"))
width = int(os.environ.get("NAVA_RENDER_WIDTH", "256"))
latent_frames = int(os.environ.get("NAVA_RENDER_LATENT_FRAMES", "2"))
steps = int(os.environ.get("NAVA_RENDER_STEPS", "2"))
seed = int(os.environ.get("NAVA_RENDER_SEED", "42"))
video_cfg = float(os.environ.get("NAVA_RENDER_VIDEO_CFG", "3.0"))
audio_cfg = float(os.environ.get("NAVA_RENDER_AUDIO_CFG", "2.0"))
group_offload = os.environ.get("NAVA_RENDER_GROUP_OFFLOAD", "1") == "1"
vae_tiling = os.environ.get("NAVA_RENDER_VAE_TILING", "1") == "1"
vae_tile_size = tuple(int(part) for part in os.environ.get("NAVA_RENDER_VAE_TILE_SIZE", "8,12").split(","))
vae_tile_stride = tuple(int(part) for part in os.environ.get("NAVA_RENDER_VAE_TILE_STRIDE", "6,10").split(","))

engine = NAVAComfyEngine(
    config_path=str(root / "configs/nava.yaml"),
    ckpt_path=str(root / "NAVA_fp8.safetensors"),
    t5_offload=True,
    group_offload=group_offload,
    offload_group_size=1,
    weight_dtype="fp8_e4m3fn",
)

frames, audio = engine.generate(
    prompt=prompt,
    height=height,
    width=width,
    latent_frames=latent_frames,
    steps=steps,
    video_cfg=video_cfg,
    audio_cfg=audio_cfg,
    seed=seed,
    vae_tiling=vae_tiling,
    vae_tile_size=vae_tile_size,
    vae_tile_stride=vae_tile_stride,
)

video_uint8 = (frames.cpu().float().numpy() * 255).clip(0, 255).astype(np.uint8)
video_only = out_dir / "nava_comfy_smoke_video_only.mp4"
iio.imwrite(video_only, video_uint8, fps=24, codec="libx264")

waveform = audio["waveform"]
if waveform.dim() == 3:
    waveform = waveform[0]
wav_path = out_dir / "nava_comfy_smoke_audio.wav"
torchaudio.save(str(wav_path), waveform.cpu().float(), int(audio["sample_rate"]))

muxed = out_dir / "nava_comfy_smoke_muxed.mp4"
frame_sheet = out_dir / "nava_comfy_smoke_frames.jpg"
ffmpeg_path = shutil.which("ffmpeg")
if ffmpeg_path:
    ffmpeg = subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_only),
            "-i",
            str(wav_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(muxed),
        ],
        text=True,
        capture_output=True,
    )
    ffmpeg_exit_code = ffmpeg.returncode
    ffmpeg_stderr = ffmpeg.stderr[-2000:]
    status = "remote_muxed" if muxed.exists() and muxed.stat().st_size > 0 else "recoverable_component_success"
    frame_source = muxed if muxed.exists() else video_only
    frame_sheet_proc = subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(frame_source),
            "-vf",
            "fps=1,scale=256:-1,tile=5x1",
            "-frames:v",
            "1",
            str(frame_sheet),
        ],
        text=True,
        capture_output=True,
    )
    frame_sheet_exit_code = frame_sheet_proc.returncode
    frame_sheet_stderr = frame_sheet_proc.stderr[-2000:]
else:
    ffmpeg_exit_code = None
    ffmpeg_stderr = "ffmpeg missing after successful NAVA component generation"
    frame_sheet_exit_code = None
    frame_sheet_stderr = "ffmpeg missing; frame sheet not generated"
    status = "recoverable_component_success"

manifest = {
    "status": status,
    "entrypoint": "comfyui_nava.engine.NAVAComfyEngine",
    "prompt": prompt,
    "height": height,
    "width": width,
    "latent_frames": latent_frames,
    "decoded_frames": int(frames.shape[0]),
    "steps": steps,
    "seed": seed,
    "video_cfg": video_cfg,
    "audio_cfg": audio_cfg,
    "group_offload": group_offload,
    "vae_tiling": vae_tiling,
    "vae_tile_size": vae_tile_size,
    "vae_tile_stride": vae_tile_stride,
    "fps": 24,
    "audio_sample_rate": int(audio["sample_rate"]),
    "outputs": {
        "video_only": str(video_only),
        "audio_wav": str(wav_path),
        "muxed_mp4": str(muxed) if muxed.exists() else None,
        "frame_sheet": str(frame_sheet) if frame_sheet.exists() else None,
    },
    "ffmpeg_exit_code": ffmpeg_exit_code,
    "ffmpeg_stderr": ffmpeg_stderr,
    "frame_sheet_exit_code": frame_sheet_exit_code,
    "frame_sheet_stderr": frame_sheet_stderr,
    "recovery_policy": {
        "local_mux_allowed": status == "recoverable_component_success",
        "rerun_required": status not in {"remote_muxed", "recoverable_component_success"},
    },
}
Path(out_dir / "nava_comfy_smoke_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
if status not in {"remote_muxed", "recoverable_component_success"}:
    raise SystemExit(1)
PY
find /workspace/nava_smoke_out -maxdepth 5 -type f -print
echo "[remote] done $(date -Is)"
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default="/tmp/persona-dream-elevenlabs-baseline")
    parser.add_argument("--max-hours", type=float, default=1.0)
    parser.add_argument("--max-hourly", type=float, default=1.00)
    parser.add_argument("--cloud-type", default="COMMUNITY", choices=["COMMUNITY", "SECURE", "ALL"])
    parser.add_argument("--ssh-wait-seconds", type=int, default=900)
    parser.add_argument("--remote-timeout-seconds", type=int, default=3300)
    parser.add_argument("--key-path", default=str(Path.home() / ".ssh" / "runpod_ed25519"))
    parser.add_argument("--phase", choices=["env-probe", "nava-smoke", "official-fp8"], default="env-probe")
    parser.add_argument("--allow-flash-source-build", action="store_true")
    parser.add_argument("--rewrite-model", default="Qwen/Qwen3-4B-Thinking-2507")
    parser.add_argument("--rewrite-4bit", action="store_true")
    parser.add_argument("--render-height", type=int, default=144)
    parser.add_argument("--render-width", type=int, default=256)
    parser.add_argument("--latent-frames", type=int, default=2)
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--video-cfg", type=float, default=3.0)
    parser.add_argument("--audio-cfg", type=float, default=2.0)
    parser.add_argument("--disable-group-offload", action="store_true")
    parser.add_argument("--disable-vae-tiling", action="store_true")
    parser.add_argument("--vae-tile-size", default="8,12")
    parser.add_argument("--vae-tile-stride", default="6,10")
    args = parser.parse_args()

    if "RUNPOD_API_KEY" not in os.environ:
        raise SystemExit("RUNPOD_API_KEY is missing; run `source ~/.zshrc` first.")

    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    run_dir = Path(args.run_dir)
    receipt_path = run_dir / "nava_lane" / "runpod_pod_smoke_receipt.json"
    downloads_dir = run_dir / "nava_lane" / "outputs" / "runpod_pod"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    local_jsonl = run_dir / "nava_lane" / "nava_prompts.jsonl"
    prompt_only_jsonl = downloads_dir / "nava_prompt_only.jsonl"
    strip_image_path(local_jsonl, prompt_only_jsonl)

    gpu_candidates = list_gpu_candidates(DEFAULT_GPU_CANDIDATES, args.max_hourly, args.cloud_type)
    gpu_info = gpu_candidates[0]
    receipt: dict[str, Any] = {
        "status": "starting",
        "started_at": now_iso(),
        "max_hours": args.max_hours,
        "max_hourly": args.max_hourly,
        "cloud_type": args.cloud_type,
        "selected_gpu": gpu_info,
        "phase": args.phase,
        "allow_flash_source_build": args.allow_flash_source_build,
        "render": {
            "height": args.render_height,
            "width": args.render_width,
            "latent_frames": args.latent_frames,
            "steps": args.steps,
            "seed": args.seed,
            "video_cfg": args.video_cfg,
            "audio_cfg": args.audio_cfg,
            "group_offload": not args.disable_group_offload,
            "vae_tiling": not args.disable_vae_tiling,
            "vae_tile_size": args.vae_tile_size,
            "vae_tile_stride": args.vae_tile_stride,
            "fps": 24,
            "nominal_duration_sec": ((args.latent_frames * 4) - 3) / 24,
        },
        "rewrite": {
            "model": args.rewrite_model,
            "use_4bit": args.rewrite_4bit,
        },
        "pod_id": None,
        "events": [],
    }
    write_json(receipt_path, receipt)

    pod_id = None
    client: paramiko.SSHClient | None = None
    try:
        create_errors = []
        pod = None
        for candidate in gpu_candidates:
            gpu_info = candidate
            receipt["selected_gpu"] = gpu_info
            receipt["events"].append({"at": now_iso(), "event": "create_pod", "gpu": gpu_info["id"], "hourly": gpu_info["selectedHourlyPrice"]})
            write_json(receipt_path, receipt)
            try:
                pod = runpod.create_pod(
                    name=f"persona-dream-nava-smoke-{int(time.time())}",
                    image_name="runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04",
                    gpu_type_id=gpu_info["id"],
                    cloud_type=args.cloud_type,
                    support_public_ip=True,
                    start_ssh=True,
                    gpu_count=1,
                    volume_in_gb=0,
                    container_disk_in_gb=100,
                    min_vcpu_count=8,
                    min_memory_in_gb=32,
                    ports="22/tcp",
                    allowed_cuda_versions=["12.8", "12.7", "12.6"],
                )
                break
            except Exception as exc:  # noqa: BLE001
                create_errors.append({"gpu": gpu_info["id"], "error": f"{type(exc).__name__}: {exc}"})
                receipt["events"].append({"at": now_iso(), "event": "create_pod_failed", "gpu": gpu_info["id"], "error": f"{type(exc).__name__}: {exc}"})
                write_json(receipt_path, receipt)
        if pod is None:
            receipt["create_errors"] = create_errors
            raise RuntimeError(f"No candidate GPU could be created: {create_errors}")
        pod_id = pod["id"]
        receipt["pod_id"] = pod_id
        receipt["create_response"] = pod
        receipt["events"].append({"at": now_iso(), "event": "pod_created", "pod_id": pod_id})
        write_json(receipt_path, receipt)

        client = connect_ssh(pod_id, Path(args.key_path), args.ssh_wait_seconds)
        receipt["events"].append({"at": now_iso(), "event": "ssh_connected"})
        write_json(receipt_path, receipt)

        run_remote(client, "mkdir -p /workspace", timeout=60)
        upload_file(client, prompt_only_jsonl, "/workspace/nava_input.jsonl")
        upload_text(client, REMOTE_SCRIPT, "/workspace/run_nava_smoke.sh", mode=0o755)

        command = (
            f"timeout {int(args.remote_timeout_seconds)} bash -lc "
            + shlex.quote(
                f"NAVA_RUN_PHASE={shlex.quote(args.phase)} "
                f"ALLOW_FLASH_SOURCE_BUILD={'1' if args.allow_flash_source_build else '0'} "
                f"NAVA_RENDER_HEIGHT={int(args.render_height)} "
                f"NAVA_RENDER_WIDTH={int(args.render_width)} "
                f"NAVA_RENDER_LATENT_FRAMES={int(args.latent_frames)} "
                f"NAVA_RENDER_STEPS={int(args.steps)} "
                f"NAVA_RENDER_SEED={int(args.seed)} "
                f"NAVA_RENDER_VIDEO_CFG={float(args.video_cfg)} "
                f"NAVA_RENDER_AUDIO_CFG={float(args.audio_cfg)} "
                f"NAVA_RENDER_GROUP_OFFLOAD={'0' if args.disable_group_offload else '1'} "
                f"NAVA_RENDER_VAE_TILING={'0' if args.disable_vae_tiling else '1'} "
                f"NAVA_RENDER_VAE_TILE_SIZE={shlex.quote(args.vae_tile_size)} "
                f"NAVA_RENDER_VAE_TILE_STRIDE={shlex.quote(args.vae_tile_stride)} "
                f"NAVA_REWRITE_MODEL={shlex.quote(args.rewrite_model)} "
                f"NAVA_REWRITE_4BIT={'1' if args.rewrite_4bit else '0'} "
                "bash /workspace/run_nava_smoke.sh > /workspace/nava_smoke.log 2>&1; "
                "code=$?; echo __REMOTE_EXIT__$code; tail -240 /workspace/nava_smoke.log; exit $code"
            )
        )
        result = run_remote(client, command, timeout=args.remote_timeout_seconds + 120)
        receipt["remote_result"] = result
        receipt["events"].append({"at": now_iso(), "event": "remote_command_finished", "exit_code": result["exit_code"]})

        sftp = client.open_sftp()
        for remote_name in ["/workspace/nava_smoke.log"]:
            try:
                sftp.get(remote_name, str(downloads_dir / Path(remote_name).name))
            except Exception as exc:  # noqa: BLE001
                receipt["events"].append({"at": now_iso(), "event": "download_failed", "path": remote_name, "error": str(exc)})
        try:
            download_tree(sftp, "/workspace/nava_smoke_out", downloads_dir, receipt)
        except Exception as exc:  # noqa: BLE001
            receipt["events"].append({"at": now_iso(), "event": "download_outputs_failed", "path": "/workspace/nava_smoke_out", "error": str(exc)})
        try:
            download_tree(sftp, "/workspace/nava_official_out", downloads_dir / "official_fp8", receipt)
        except Exception as exc:  # noqa: BLE001
            receipt["events"].append({"at": now_iso(), "event": "download_outputs_failed", "path": "/workspace/nava_official_out", "error": str(exc)})
        sftp.close()

        receipt["status"] = "success" if result["exit_code"] == 0 else "remote_failed"
        return 0 if result["exit_code"] == 0 else 2
    except KeyboardInterrupt:
        receipt["status"] = "interrupted"
        receipt["error"] = "KeyboardInterrupt"
        return 130
    except Exception as exc:  # noqa: BLE001
        receipt["status"] = "failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        return 1
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if pod_id:
            try:
                receipt["events"].append({"at": now_iso(), "event": "terminate_pod_start", "pod_id": pod_id})
                write_json(receipt_path, receipt)
                term = runpod.terminate_pod(pod_id)
                receipt["terminate_response"] = term
                receipt["events"].append({"at": now_iso(), "event": "terminate_pod_done", "response": term})
            except Exception as exc:  # noqa: BLE001
                receipt["terminate_error"] = f"{type(exc).__name__}: {exc}"
        receipt["ended_at"] = now_iso()
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
