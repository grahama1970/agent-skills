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


def test_reattach_journal_routes_to_watchdog_resume(monkeypatch, tmp_path):
    mod = load_recover_primary()
    journal = tmp_path / "operation.json"
    journal.write_text("{}", encoding="utf-8")
    called = {}

    def reattach(root, journal_path, *, apply):
        called.update(root=root, journal=journal_path, apply=apply)
        return {"ok": True, "status": "DRY_RUN"}

    monkeypatch.setattr(sys, "argv", ["recover_primary.py", "--root", str(tmp_path), "--reattach-journal", str(journal)])
    monkeypatch.setattr(mod.primary, "reattach_and_resume", reattach)

    assert mod.main() == 0
    assert called == {"root": tmp_path, "journal": journal, "apply": False}


def test_failed_reattachment_exits_nonzero(monkeypatch, tmp_path):
    mod = load_recover_primary()
    journal = tmp_path / "operation.json"
    monkeypatch.setattr(sys, "argv", ["recover_primary.py", "--root", str(tmp_path),
                                     "--reattach-journal", str(journal), "--apply"])
    monkeypatch.setattr(mod.primary, "reattach_and_resume", lambda *a, **kw: {
        "ok": False, "status": "NEEDS_ATTENTION", "summary": "nested Ask invocation failed"
    })
    assert mod.main() == 1
