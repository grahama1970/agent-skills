from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _probe_path(repo_root: Path) -> Path:
    return repo_root / "skills" / "personaplex" / "scripts" / "personaplex_gpu_inference_probe.py"


def _run_probe(repo_root: Path, fake_server: Path, out_dir: Path, require_real: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(_probe_path(repo_root)),
        "--personaplex-root",
        str(fake_server.parent),
        "--venv-python",
        sys.executable,
        "--golden-state-server",
        str(fake_server),
        "--out-dir",
        str(out_dir),
    ]
    if require_real:
        cmd.append("--require-real")
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_p10c_probe_accepts_valid_cuda_generated_output(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fake_server = tmp_path / "personaplex_golden_state_server.py"
    fake_server.write_text(
        "import json\n"
        "print(json.dumps({\n"
        "  'ok': True,\n"
        "  'torch_cuda_available': True,\n"
        "  'device': 'cuda:0',\n"
        "  'gpu_name': 'NVIDIA RTX A5000',\n"
        "  'generated_text': 'Embry generated a bounded GPU proof token.'\n"
        "}))\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "receipt"
    proc = _run_probe(repo_root, fake_server, out_dir, require_real=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    receipt = json.loads((out_dir / "p10-gpu-personaplex-receipt.json").read_text(encoding="utf-8"))
    assert receipt["real_gpu_personaplex"] is True
    assert receipt["golden_state_subprocess_attempted"] is True
    assert receipt["valid_cuda_device"] is True
    assert receipt["valid_generated_output"] is True
    assert receipt["generated_output_path"] == "generated_text"
    assert "--probe-lmgen-step" in receipt["command"]
    assert "--json" in receipt["command"]


def test_p10c_probe_rejects_hash_only_output(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fake_server = tmp_path / "personaplex_golden_state_server.py"
    fake_server.write_text(
        "import json\n"
        "print(json.dumps({\n"
        "  'ok': True,\n"
        "  'torch_cuda_available': True,\n"
        "  'device': 'cuda:0',\n"
        "  'gpu_name': 'NVIDIA RTX A5000',\n"
        "  'step_output_sha256': '" + "a" * 64 + "'\n"
        "}))\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "hash_only"
    proc = _run_probe(repo_root, fake_server, out_dir, require_real=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    receipt = json.loads((out_dir / "p10-gpu-personaplex-receipt.json").read_text(encoding="utf-8"))
    assert receipt["real_gpu_personaplex"] is False
    assert receipt["valid_cuda_device"] is True
    assert receipt["valid_generated_output"] is False


def test_p10c_probe_falls_back_when_server_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    out_dir = tmp_path / "fallback"
    missing = tmp_path / "missing_golden_state_server.py"
    proc = _run_probe(repo_root, missing, out_dir, require_real=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    receipt = json.loads((out_dir / "p10-gpu-personaplex-receipt.json").read_text(encoding="utf-8"))
    assert receipt["real_gpu_personaplex"] is False
    assert receipt["fallback_used"] is True
    assert receipt["fallback_reason"] == "personaplex_golden_state_server_not_found"
