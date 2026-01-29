"""
Battle Skill - QEMU Support
QEMU emulation support for firmware/microprocessor battles.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from rich.console import Console

from config import SKILL_DIR, SAFE_FILENAME_PATTERN

console = Console()


def detect_qemu_machine(source_path: Path) -> str | None:
    """Detect appropriate QEMU machine type from firmware file."""
    if not source_path.exists():
        return None

    try:
        with open(source_path, 'rb') as f:
            header = f.read(64)

        if header[:4] == b'\x7fELF':
            ei_class = header[4]
            e_machine = int.from_bytes(header[18:20], 'little')

            machine_map = {
                0x03: "i386",
                0x3E: "x86_64",
                0x28: "arm",
                0xB7: "aarch64",
                0xF3: "riscv64" if ei_class == 2 else "riscv32",
                0x08: "mips",
            }
            return machine_map.get(e_machine)

        if header.startswith(b':'):
            return "arm"

        if source_path.suffix.lower() in {'.bin', '.fw', '.rom'}:
            return "arm"

    except Exception:
        pass

    return None


def build_qemu_command(
    machine: str,
    firmware_name: str,
    gdb_port: str,
    qmp_port: str,
    disk_path: str,
    enable_peripheral_stubs: bool = True,
    enable_mmio_log: bool = False,
    mmio_log_path: str = "/battle/firmware/mmio.log"
) -> list[str]:
    """
    Build QEMU command as argument list for running inside container.

    Returns a list of arguments (not a string) to avoid shell injection.
    """
    machine_configs = {
        'arm': (['-M', 'virt', '-cpu', 'cortex-a15'], '-kernel'),
        'aarch64': (['-M', 'virt', '-cpu', 'cortex-a53'], '-kernel'),
        'riscv64': (['-M', 'virt', '-cpu', 'rv64'], '-kernel'),
        'x86_64': (['-M', 'q35', '-cpu', 'qemu64'], '-bios'),
        'i386': (['-M', 'q35', '-cpu', 'qemu32'], '-bios'),
        'mips': (['-M', 'malta', '-cpu', '24Kc'], '-kernel'),
    }

    machine_opts, fw_opt = machine_configs.get(machine, (['-M', 'virt'], '-kernel'))
    qemu_binary = f"qemu-system-{machine}"

    cmd_parts: list[str] = [
        qemu_binary,
        *machine_opts,
        "-m", "64M",
        "-nographic",
        "-gdb", f"tcp::{gdb_port}",
        "-qmp", f"tcp::{qmp_port},server,nowait",
        "-drive", f"file={disk_path},format=qcow2,if=virtio",
        fw_opt, f"/battle/firmware/{firmware_name}",
    ]

    if enable_peripheral_stubs:
        stub_opts = get_peripheral_stub_options(machine)
        cmd_parts.extend(stub_opts)

    if enable_mmio_log:
        mmio_opts = get_mmio_log_options(mmio_log_path)
        cmd_parts.extend(mmio_opts)

    return cmd_parts


def get_peripheral_stub_options(machine: str) -> list[str]:
    """Get QEMU options for P2IM-style peripheral stubbing."""
    opts = []

    if machine in ['arm', 'aarch64', 'x86_64', 'i386', 'riscv64', 'mips']:
        opts.extend(["-serial", "mon:stdio"])

    return opts


def get_mmio_log_options(log_path: str) -> list[str]:
    """Get QEMU options for MMIO access logging."""
    opts = [
        "-D", log_path,
        "-d", "guest_errors,unimp",
    ]
    return opts


def start_qemu_instance(
    battle_id: str,
    team: str,
    worktree_base: Path,
    wait_boot: bool = True
) -> bool:
    """Start a QEMU instance for the specified team inside Docker container."""
    team_dir = worktree_base / team
    if not team_dir.exists():
        console.print(f"[red]Team directory not found: {team_dir}[/red]")
        return False

    container_name = f"battle_{battle_id}_{team}"

    qemu_config = team_dir / "qemu.conf"
    if not qemu_config.exists():
        console.print(f"[red]QEMU config not found for {team}[/red]")
        return False

    config = {}
    for line in qemu_config.read_text().strip().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            config[key] = val

    machine = config.get('machine', 'arm')
    firmware_name = config.get('firmware', 'firmware')
    gdb_port = config.get('gdb_port', '5000')
    qmp_port = config.get('qmp_port', '6000')

    result = subprocess.run(
        ["docker", "start", container_name],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        console.print(f"[red]Failed to start container: {result.stderr}[/red]")
        return False

    disk_path = f"/battle/firmware/{team}_disk.qcow2"
    subprocess.run(
        ["docker", "exec", container_name,
         "qemu-img", "create", "-f", "qcow2", disk_path, "64M"],
        capture_output=True
    )

    enable_stubs = True
    enable_mmio_log = False
    mmio_log_path = f"/battle/firmware/{team}_mmio.log"

    stub_file = team_dir / "peripheral_stubs.json"
    if stub_file.exists():
        try:
            stub_config = json.loads(stub_file.read_text())
            enable_stubs = stub_config.get("uart", True) or stub_config.get("timer", True)
            enable_mmio_log = stub_config.get("mmio_log", False)
            cfg_path = stub_config.get("mmio_log_path", mmio_log_path)
            if isinstance(cfg_path, str) and cfg_path.startswith("/battle/"):
                mmio_log_path = cfg_path
        except Exception:
            pass

    qemu_args = build_qemu_command(
        machine, firmware_name, gdb_port, qmp_port, disk_path,
        enable_peripheral_stubs=enable_stubs,
        enable_mmio_log=enable_mmio_log,
        mmio_log_path=mmio_log_path
    )

    result = subprocess.run(
        ["docker", "exec", "-d", container_name, *qemu_args],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        console.print(f"[red]Failed to start QEMU in container: {result.stderr}[/red]")
        return False

    console.print(f"  [green]{team.title()} QEMU started in container {container_name}[/green]")
    console.print(f"    GDB: localhost:{gdb_port}, QMP: localhost:{qmp_port}")

    if wait_boot:
        time.sleep(2)

    return True


def create_golden_snapshot(
    battle_id: str,
    team: str,
    worktree_base: Path,
    snapshot_name: str = "golden"
) -> bool:
    """Create a golden snapshot of the QEMU state after boot."""
    team_dir = worktree_base / team
    qemu_config = team_dir / "qemu.conf"

    if not qemu_config.exists():
        console.print(f"[red]QEMU config not found for {team}[/red]")
        return False

    config = {}
    for line in qemu_config.read_text().strip().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            config[key] = val

    qmp_port = config.get('qmp_port', '6000')
    container_name = f"battle_{battle_id}_{team}"

    console.print(f"[cyan]Creating golden snapshot '{snapshot_name}' for {team}...[/cyan]")

    try:
        qmp_script = f'''
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect(("localhost", {qmp_port}))

greeting = sock.recv(4096)
sock.send(b'{{"execute": "qmp_capabilities"}}\\n')
response = sock.recv(4096)

cmd = {{"execute": "human-monitor-command", "arguments": {{"command-line": "savevm {snapshot_name}"}}}}
sock.send((json.dumps(cmd) + "\\n").encode())
response = sock.recv(4096)

sock.close()
print("OK")
'''
        result = subprocess.run(
            ["docker", "exec", container_name, "python3", "-c", qmp_script],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0 or "error" in result.stdout.lower():
            console.print(f"[red]Snapshot failed: {result.stdout} {result.stderr}[/red]")
            return False

        snapshot_meta = team_dir / f".snapshot_{snapshot_name}"
        snapshot_meta.write_text(f"created={time.time()}\nname={snapshot_name}\n")

        console.print(f"  [green]Snapshot '{snapshot_name}' created for {team}[/green]")
        return True

    except subprocess.TimeoutExpired:
        console.print("[red]Snapshot creation timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Snapshot creation failed: {e}[/red]")
        return False


def restore_snapshot(
    battle_id: str,
    team: str,
    worktree_base: Path,
    snapshot_name: str = "golden"
) -> bool:
    """Restore QEMU to a previously saved snapshot."""
    team_dir = worktree_base / team
    qemu_config = team_dir / "qemu.conf"

    if not qemu_config.exists():
        return False

    config = {}
    for line in qemu_config.read_text().strip().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            config[key] = val

    qmp_port = config.get('qmp_port', '6000')
    container_name = f"battle_{battle_id}_{team}"

    try:
        start_time = time.time()

        qmp_script = f'''
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect(("localhost", {qmp_port}))

greeting = sock.recv(4096)
sock.send(b'{{"execute": "qmp_capabilities"}}\\n')
response = sock.recv(4096)

cmd = {{"execute": "human-monitor-command", "arguments": {{"command-line": "loadvm {snapshot_name}"}}}}
sock.send((json.dumps(cmd) + "\\n").encode())
response = sock.recv(4096)

sock.close()
print("OK")
'''
        result = subprocess.run(
            ["docker", "exec", container_name, "python3", "-c", qmp_script],
            capture_output=True, text=True, timeout=10
        )

        restore_time_ms = (time.time() - start_time) * 1000

        if result.returncode != 0 or "error" in result.stdout.lower():
            console.print(f"[red]Restore failed: {result.stdout}[/red]")
            return False

        console.print(f"  [green]Snapshot restored in {restore_time_ms:.1f}ms[/green]")
        return True

    except Exception as e:
        console.print(f"[red]Restore failed: {e}[/red]")
        return False
