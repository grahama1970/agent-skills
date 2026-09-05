#!/usr/bin/env python3
"""#1577 named proof: a repair worktree is created WITH an ops-worktrees lease.

Live seam: real git repo + origin, real prepare_repair_worktree, real
worktree_lease.register write, read back from the lease registry file.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
base = Path(tempfile.mkdtemp(prefix="pw-lease-proof-"))
registry_file = base / "leases.jsonl"
os.environ["WORKTREE_LEASE_REGISTRY"] = str(registry_file)
from watchdog import registry as wreg  # noqa: E402

def sh(*a, cwd=None):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)

origin = base / "origin.git"; sh("git", "init", "-q", "--bare", str(origin))
repo = base / "repo"; sh("git", "init", "-q", str(repo))
(repo / "f.txt").write_text("x\n")
sh("git", "add", ".", cwd=repo)
sh("git", "-c", "user.email=p@p", "-c", "user.name=p", "commit", "-qm", "init", cwd=repo)
sh("git", "remote", "add", "origin", str(origin), cwd=repo)
sh("git", "push", "-q", "origin", "HEAD:main", cwd=repo)

wt = base / "wt-42"
result = wreg.prepare_repair_worktree(repo, wt, 42)
assert result.get("ok") is True, result

# READBACK: the lease registry entry for this worktree, from disk.
entries = [json.loads(l) for l in registry_file.read_text().splitlines() if l.strip()]
match = [e for e in entries if e.get("path") == str(wt.resolve())]
assert match, f"no lease registry entry for {wt}: {entries}"
print(json.dumps({"worktree_created": wt.exists(), "lease_entry": match[0],
                  "registry_file": str(registry_file), "ok": True}, indent=1))
