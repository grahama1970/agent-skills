"""Battle Skill - Full-system QEMU VM twin.

One honest round primitive for host-policy battles: fresh qcow2 overlay from a
base image -> KVM boot -> SSH payload execution -> deterministic receipt ->
teardown. Docker twins cannot host systemd/AppArmor/cgroup-BPF policy because
containers share the host kernel; a full-system VM has its own kernel and can.

All target execution happens inside the VM. The host is control plane only.
Every round requires a security.target_authorization.v1 manifest binding the
base image identity before QEMU starts (battle invariant).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

REQUIRED_HOST_TOOLS = ("qemu-system-x86_64", "qemu-img", "xorriso", "ssh", "ssh-keygen")
CLOUD_USER = "ubuntu"
BOOT_POLL_SECONDS = 3


@dataclass
class VMRoundReceipt:
    """Typed seam contract for one vm-round. Fail-closed: validate() or raise."""

    schema_version: str = "battle.vm_round.v1"
    base_image: str = ""
    authorization_id: str = ""
    ssh_port: int = 0
    payload_sha256: str = ""
    booted: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    started_at: str = ""
    finished_at: str = ""
    seam_validation: dict = field(default_factory=dict)

    def validate(self) -> None:
        problems: list[str] = []
        if not self.base_image:
            problems.append("base_image required")
        if not self.authorization_id:
            problems.append("authorization_id required (unauthorized QEMU start)")
        if self.booted and self.exit_code is None:
            problems.append("booted round must record exit_code")
        if not self.booted and (self.stdout or self.stderr or self.exit_code is not None):
            problems.append("output recorded for a round that never booted")
        if problems:
            raise ValueError("VMRoundReceipt invalid: " + "; ".join(problems))


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def preflight_tools() -> None:
    missing = [tool for tool in REQUIRED_HOST_TOOLS if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(f"vm-round requires host tools not found: {', '.join(missing)}")


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_overlay(base_image: Path, round_dir: Path) -> Path:
    overlay = round_dir / "round-overlay.qcow2"
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", "-b", str(base_image), "-F", "qcow2", str(overlay)],
        check=True,
        capture_output=True,
    )
    return overlay


def make_seed_iso(round_dir: Path, ssh_public_key: str) -> Path:
    seed_dir = round_dir / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    user_data = (
        "#cloud-config\n"
        f"hostname: battle-vm\n"
        f"ssh_authorized_keys:\n  - {ssh_public_key}\n"
        "ssh_pwauth: false\n"
    )
    (seed_dir / "user-data").write_text(user_data)
    (seed_dir / "meta-data").write_text("instance-id: battle-vm-001\nlocal-hostname: battle-vm\n")
    iso = round_dir / "seed.iso"
    subprocess.run(
        ["xorriso", "-as", "mkisofs", "-output", str(iso), "-volid", "cidata", "-joliet", "-rock",
         str(seed_dir / "user-data"), str(seed_dir / "meta-data")],
        check=True,
        capture_output=True,
    )
    return iso


def _ssh_argv(port: int, key: Path, remote: str | None = None) -> list[str]:
    argv = ["ssh", "-i", str(key), "-p", str(port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=5", "-o", "IdentitiesOnly=yes",
            f"{CLOUD_USER}@127.0.0.1"]
    if remote:
        argv.append(remote)
    return argv


def boot_vm(overlay: Path, seed_iso: Path, port: int, round_dir: Path, boot_timeout: int, key: Path) -> int:
    pid_file = round_dir / "qemu.pid"
    serial_log = round_dir / "serial.log"
    cmd = [
        "qemu-system-x86_64",
        "-enable-kvm", "-cpu", "host", "-m", "2048", "-smp", "2",
        "-drive", f"file={overlay},if=virtio,format=qcow2",
        "-drive", f"file={seed_iso},if=virtio,media=cdrom,format=raw",
        "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:22",
        "-device", "virtio-net-pci,netdev=net0",
        "-display", "none", "-daemonize",
        "-pidfile", str(pid_file),
        "-serial", f"file:{serial_log}",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    deadline = time.monotonic() + boot_timeout
    while time.monotonic() < deadline:
        if subprocess.run(_ssh_argv(port, key), capture_output=True).returncode == 0:
            return int(pid_file.read_text().strip())
        time.sleep(BOOT_POLL_SECONDS)
    raise TimeoutError(f"VM did not accept SSH within {boot_timeout}s; see {serial_log}")


def run_payload(port: int, key: Path, payload: str) -> tuple[int, str, str]:
    proc = subprocess.run(_ssh_argv(port, key, "bash -s"), input=payload, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def teardown(pid: int, keep_round_dir: bool, round_dir: Path) -> None:
    import os
    import signal

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.5)
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if not keep_round_dir:
        shutil.rmtree(round_dir, ignore_errors=True)
        logger.info("vm round dir removed: {}", round_dir)


def vm_round(
    base_image: Path,
    payload: str,
    *,
    authorization: dict,
    out_dir: Path,
    ssh_port: int | None = None,
    boot_timeout: int = 300,
    keep_round_dir: bool = False,
) -> VMRoundReceipt:
    preflight_tools()
    if authorization.get("status") != "PASS":
        raise PermissionError("authorization manifest did not PASS; refusing to start QEMU")

    started = datetime.now(timezone.utc)
    round_dir = out_dir / f"vm-round-{started.strftime('%Y%m%dT%H%M%S')}-{int(started.timestamp())}"
    round_dir.mkdir(parents=True, exist_ok=True)

    port = ssh_port or _free_port()
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", str(round_dir / "id_ed25519")],
                   check=True, capture_output=True)
    public_key = (round_dir / "id_ed25519.pub").read_text().strip()

    receipt = VMRoundReceipt(
        base_image=str(base_image),
        authorization_id=authorization.get("authorization_id", ""),
        ssh_port=port,
        started_at=started.isoformat(),
    )
    pid: int | None = None
    try:
        overlay = prepare_overlay(base_image, round_dir)
        seed_iso = make_seed_iso(round_dir, public_key)
        payload_file = round_dir / "payload.sh"
        payload_file.write_text(payload)
        receipt.payload_sha256 = _sha256(payload_file)
        pid = boot_vm(overlay, seed_iso, port, round_dir, boot_timeout, round_dir / "id_ed25519")
        receipt.booted = True
        receipt.exit_code, receipt.stdout, receipt.stderr = run_payload(port, round_dir / "id_ed25519", payload)
    finally:
        if pid is not None:
            teardown(pid, keep_round_dir, round_dir)

    receipt.finished_at = datetime.now(timezone.utc).isoformat()
    receipt.validate()
    receipt.seam_validation = {"kind": "dataclass", "status": "PASS"}
    (out_dir / "vm-round-receipt.json").write_text(json.dumps(receipt.__dict__, indent=2) + "\n")
    return receipt
