from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
VENDOR_STATUS = SKILL_DIR / "scripts/vendor-status.sh"
VENDOR_SYNC = SKILL_DIR / "scripts/vendor-sync.sh"


def content_hash(root: Path, excludes: set[str]) -> tuple[str, int]:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in excludes
    )
    for path in files:
        data = path.read_bytes()
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(str(len(data)).encode())
        digest.update(b"\0")
        digest.update(data)
    return digest.hexdigest(), len(files)


def test_vendor_status_honors_declared_content_excludes(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "package.json").write_text('{"version":"1.0.0"}\n')
    (vendor / "included.txt").write_text("included\n")
    (vendor / "ignored.txt").write_text("ignored before hashing\n")
    excludes = {"VENDOR.lock.json", "ignored.txt"}
    sha256, count = content_hash(vendor, excludes)
    (vendor / "VENDOR.lock.json").write_text(json.dumps({
        "content_identity": {
            "excludes": sorted(excludes),
            "file_count": count,
            "sha256": sha256,
        }
    }))
    (vendor / "ignored.txt").write_text("changed but still excluded\n")
    env = os.environ.copy()
    env["SURF_CLI_PATH"] = str(vendor)

    proc = subprocess.run(
        [str(VENDOR_STATUS), "--json"], env=env, text=True, capture_output=True
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["content_identity_matches"] is True
    assert payload["content_identity"]["file_count"] == count


def test_vendor_sync_writes_current_content_identity_schema(tmp_path: Path) -> None:
    source = tmp_path / "source"
    vendor = tmp_path / "vendor"
    source.mkdir()
    (source / "package.json").write_text('{"version":"9.9.9"}\n')
    (source / "payload.txt").write_text("payload\n")
    env = os.environ.copy()
    env["SURF_CLI_PATH"] = str(vendor)

    proc = subprocess.run(
        [str(VENDOR_SYNC), "--from", str(source), "--json"],
        env=env,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr
    lock = json.loads((vendor / "VENDOR.lock.json").read_text())
    assert "recorded_at" in lock
    assert "synced_at" not in lock
    assert lock["package_version"] == "9.9.9"
    assert lock["clean_upstream_copy"] is False
    sha256, count = content_hash(vendor, {"VENDOR.lock.json"})
    assert lock["content_identity"]["sha256"] == sha256
    assert lock["content_identity"]["file_count"] == count
