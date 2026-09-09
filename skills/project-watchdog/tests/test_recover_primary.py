from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_recover_primary():
    path = Path(__file__).resolve().parents[1] / "scripts" / "watchdog" / "recover_primary.py"
    spec = importlib.util.spec_from_file_location("recover_primary", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_running_writer_is_not_a_failed_recovery_command(monkeypatch, tmp_path):
    mod = load_recover_primary()
    monkeypatch.setattr(sys, "argv", ["recover_primary.py", "--root", str(tmp_path), "--apply"])
    monkeypatch.setattr(mod.primary, "reconcile", lambda root: {
        "writer_active": True,
        "operations": [{"issue_number": 1631}],
        "invalid_operations": [],
    })

    assert mod.main() == 0


def test_unowned_pending_operation_still_exits_nonzero(monkeypatch, tmp_path):
    mod = load_recover_primary()
    monkeypatch.setattr(sys, "argv", ["recover_primary.py", "--root", str(tmp_path), "--apply"])
    monkeypatch.setattr(mod.primary, "reconcile", lambda root: {
        "writer_active": False,
        "operations": [{"issue_number": 1631}],
        "invalid_operations": [],
    })

    assert mod.main() == 1
