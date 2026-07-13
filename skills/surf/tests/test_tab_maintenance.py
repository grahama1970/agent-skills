import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tab-maintenance.sh"


def write_fake_surf(path: Path, log: Path, tabs: str, recovery: dict | None = None):
    rec = json.dumps(recovery or {"guards": {"chatgptGeneration": {"value": False}, "nonEmptyEditableDraft": {"value": False}, "activeDownload": {"value": False}}})
    path.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> {log}
case "$1" in
  tab.list) cat <<'EOF'
{tabs}EOF
    ;;
  tab.recovery-state) cat <<'EOF'
{rec}
EOF
    ;;
  tab.reload) echo '{{"success":true}}' ;;
  *) echo unknown >&2; exit 9 ;;
esac
""")
    path.chmod(0o755)


def run(tmp_path, *args):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    return subprocess.run([str(SCRIPT), *args], text=True, capture_output=True, env=env)


def test_default_dry_run_rebind_would_not_mutate(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    binding = {"name": "p", "backend": "webgpt", "tab_id": "1", "conversation_url": "https://chatgpt.com/c/abc"}
    (root / "p.json").write_text(json.dumps(binding))
    log = tmp_path / "surf.log"
    surf = tmp_path / "surf"
    write_fake_surf(surf, log, "2\tChatGPT\thttps://chatgpt.com/c/abc\n")
    receipts = tmp_path / "receipts"

    proc = run(tmp_path, "--root", str(root), "--surf-run", str(surf), "--receipt-dir", str(receipts), "--project", "p")

    assert proc.returncode == 0, proc.stderr
    assert json.loads((root / "p.json").read_text()) == binding
    receipt = json.loads((receipts / "p.json").read_text())
    assert receipt["status"] == "scanned"
    assert receipt["dry_run_would"] == "rebind"
    assert log.read_text().splitlines() == ["tab.list"]


def test_repair_rebinds_unique_stale_url_once_without_reload(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    (root / "p.json").write_text(json.dumps({"name": "p", "backend": "webgpt", "tab_id": "1", "conversation_url": "https://chatgpt.com/c/abc"}))
    log = tmp_path / "surf.log"
    surf = tmp_path / "surf"
    write_fake_surf(surf, log, "2\tChatGPT\thttps://chatgpt.com/c/abc\n")

    proc = run(tmp_path, "--repair", "--root", str(root), "--surf-run", str(surf), "--receipt-dir", str(tmp_path / "r"), "--project", "p", "--trigger", "discarded")

    assert proc.returncode == 0, proc.stderr
    assert json.loads((root / "p.json").read_text())["tab_id"] == "2"
    receipt = json.loads((tmp_path / "r" / "p.json").read_text())
    assert receipt["status"] == "rebound"
    assert "tab.reload" not in log.read_text()


def test_idle_trigger_never_reloads(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    (root / "p.json").write_text(json.dumps({"name": "p", "backend": "webgpt", "tab_id": "1", "conversation_url": "https://chatgpt.com/c/abc"}))
    log = tmp_path / "surf.log"
    surf = tmp_path / "surf"
    write_fake_surf(surf, log, "1\tChatGPT\thttps://chatgpt.com/c/abc\n")

    proc = run(tmp_path, "--repair", "--root", str(root), "--surf-run", str(surf), "--receipt-dir", str(tmp_path / "r"), "--project", "p", "--trigger", "idle")

    assert proc.returncode == 0, proc.stderr
    assert json.loads((tmp_path / "r" / "p.json").read_text())["status"] == "scanned"
    assert log.read_text().splitlines() == ["tab.list"]


def test_reload_requires_trigger_and_safe_guards(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    (root / "p.json").write_text(json.dumps({"name": "p", "backend": "webgpt", "tab_id": "1", "conversation_url": "https://chatgpt.com/c/abc"}))
    log = tmp_path / "surf.log"
    surf = tmp_path / "surf"
    write_fake_surf(surf, log, "1\tChatGPT\thttps://chatgpt.com/c/abc\n")

    proc = run(tmp_path, "--repair", "--root", str(root), "--surf-run", str(surf), "--receipt-dir", str(tmp_path / "r"), "--project", "p", "--trigger", "discarded")

    assert proc.returncode == 0, proc.stderr
    assert json.loads((tmp_path / "r" / "p.json").read_text())["status"] == "reloaded"
    assert log.read_text().splitlines() == ["tab.list", "tab.recovery-state --tab-id 1 --json", "tab.reload --tab-id 1"]
