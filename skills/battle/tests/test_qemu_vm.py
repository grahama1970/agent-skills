"""Non-boot unit tests for the qemu-vm round primitive (fail-closed seams)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from battle_skill.qemu_vm import VMRoundReceipt, make_seed_iso, preflight_tools, prepare_overlay


def test_receipt_requires_authorization():
    receipt = VMRoundReceipt(base_image="x.qcow2")
    with pytest.raises(ValueError, match="authorization_id"):
        receipt.validate()


def test_receipt_rejects_output_without_boot():
    receipt = VMRoundReceipt(base_image="x.qcow2", authorization_id="a1", stdout="leaked-output")
    with pytest.raises(ValueError, match="never booted"):
        receipt.validate()


def test_receipt_valid_round():
    receipt = VMRoundReceipt(base_image="x.qcow2", authorization_id="a1", booted=True, exit_code=0)
    receipt.validate()  # must not raise


def test_overlay_and_seed(tmp_path: Path):
    preflight_tools()  # host has qemu-img/xorriso; skip test if not
    base = tmp_path / "base.qcow2"
    import subprocess
    subprocess.run(["qemu-img", "create", "-f", "qcow2", str(base), "1M"], check=True, capture_output=True)
    overlay = prepare_overlay(base, tmp_path)
    assert overlay.exists()
    iso = make_seed_iso(tmp_path, "ssh-ed25519 AAAA test@battle")
    assert iso.exists() and iso.stat().st_size > 0


def test_preflight_fail_closed(monkeypatch):
    import battle_skill.qemu_vm as qv
    monkeypatch.setattr(qv.shutil, "which", lambda t: None)
    with pytest.raises(RuntimeError, match="qemu-system-x86_64"):
        preflight_tools()
