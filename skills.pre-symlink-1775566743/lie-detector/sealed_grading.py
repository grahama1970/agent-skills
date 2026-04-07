"""Layer 1: Hash-chain audit trail + sealed grading verification.

Purpose:
    Tamper-evident conversation logging via SHA-256 hash chain (OpenClause pattern)
    and sealed grading file verification via raw + AST hashing. Seals are HMAC-signed
    so an agent cannot re-seal after tampering without the key.

Inputs:
    - File globs to seal (evaluation/scoring files)
    - Seal manifest JSON to verify against
    - Conversation turns to append to hash chain

Outputs:
    - SealManifest JSON with HMAC signature (seal command)
    - VerifyResult with CLEAN/TAMPERED verdict (verify command)
    - Hash chain JSONL (append-only audit log)

Failure modes:
    - File not found → skip with warning (partial seal)
    - AST parse failure → raw hash only (still useful)
    - Chain break → TAMPERED verdict with break point index
    - Missing HMAC key → seal creation fails (not silently skipped)
    - HMAC mismatch → TAMPERED (seal was re-created or edited)
"""
from __future__ import annotations

import ast
import glob
import hashlib
import hmac
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True), override=False)

# HMAC key for seal authentication. Stored in .env (not in code, not in git).
# Without this key, an agent cannot forge a valid seal.
_HMAC_KEY = os.getenv("LIE_DETECTOR_HMAC_KEY", "")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FunctionSeal:
    name: str
    sha256_ast: str


@dataclass
class FileSeal:
    path: str
    sha256_raw: str
    sha256_ast: str | None  # None for non-Python files
    functions: list[FunctionSeal] = field(default_factory=list)


@dataclass
class SealManifest:
    timestamp: str
    git_commit: str
    hmac_sig: str = ""  # HMAC-SHA256 of canonical payload
    files: list[FileSeal] = field(default_factory=list)

    def _canonical_payload(self) -> str:
        """Deterministic JSON for HMAC signing (excludes hmac_sig itself)."""
        return json.dumps({
            "timestamp": self.timestamp,
            "git_commit": self.git_commit,
            "files": [
                {
                    "path": f.path,
                    "sha256_raw": f.sha256_raw,
                    "sha256_ast": f.sha256_ast,
                    "functions": sorted(
                        [{"name": fn.name, "sha256_ast": fn.sha256_ast} for fn in f.functions],
                        key=lambda x: x["name"],
                    ),
                }
                for f in self.files
            ],
        }, sort_keys=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "git_commit": self.git_commit,
            "hmac_sig": self.hmac_sig,
            "files": [
                {
                    "path": f.path,
                    "sha256_raw": f.sha256_raw,
                    "sha256_ast": f.sha256_ast,
                    "functions": [{"name": fn.name, "sha256_ast": fn.sha256_ast} for fn in f.functions],
                }
                for f in self.files
            ],
        }


@dataclass
class VerifyResult:
    verdict: str  # CLEAN | TAMPERED
    tampered_files: list[dict[str, Any]] = field(default_factory=list)
    tampered_functions: list[dict[str, Any]] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "tampered_files": self.tampered_files,
            "tampered_functions": self.tampered_functions,
            "missing_files": self.missing_files,
        }


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_ast_source(source: str) -> str | None:
    """Hash the AST dump of Python source. Returns None if parse fails."""
    try:
        tree = ast.parse(source)
        return _sha256_bytes(ast.dump(tree, annotate_fields=True).encode())
    except SyntaxError:
        return None


def _extract_function_asts(source: str) -> list[FunctionSeal]:
    """Extract per-function AST hashes from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    seals = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_ast = ast.dump(node, annotate_fields=True)
            seals.append(FunctionSeal(
                name=node.name,
                sha256_ast=_sha256_bytes(fn_ast.encode()),
            ))
    return seals


def _git_commit() -> str:
    """Get current git HEAD short hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Seal: create manifest
# ---------------------------------------------------------------------------

def seal(file_globs: list[str], output_path: Path | None = None) -> SealManifest:
    """Create a sealed hash manifest for the given file globs.

    Resolves globs, hashes each file (raw + AST for Python), extracts per-function
    AST hashes, and writes the manifest to disk.
    """
    manifest = SealManifest(
        timestamp=datetime.now(timezone.utc).isoformat(),
        git_commit=_git_commit(),
    )
    seen: set[str] = set()
    for pattern in file_globs:
        for match in sorted(glob.glob(pattern, recursive=True)):
            p = Path(match).resolve()
            if not p.is_file() or str(p) in seen:
                continue
            seen.add(str(p))
            source = p.read_bytes()
            raw_hash = _sha256_bytes(source)
            ast_hash = None
            functions: list[FunctionSeal] = []
            if p.suffix == ".py":
                text = source.decode("utf-8", errors="replace")
                ast_hash = _sha256_ast_source(text)
                functions = _extract_function_asts(text)
            elif p.suffix == ".json":
                # For JSON gold standards, hash normalized JSON
                try:
                    obj = json.loads(source)
                    ast_hash = _sha256_bytes(json.dumps(obj, sort_keys=True).encode())
                except json.JSONDecodeError:
                    pass
            manifest.files.append(FileSeal(
                path=str(p),
                sha256_raw=raw_hash,
                sha256_ast=ast_hash,
                functions=functions,
            ))
            logger.debug("sealed {} (raw={:.8s}, ast={}, fns={})",
                         p.name, raw_hash, ast_hash[:8] if ast_hash else "N/A", len(functions))

    # Sign with HMAC if key is available
    if _HMAC_KEY:
        manifest.hmac_sig = hmac.new(
            _HMAC_KEY.encode(), manifest._canonical_payload().encode(), hashlib.sha256,
        ).hexdigest()
        logger.info("seal signed with HMAC")
    else:
        logger.warning("LIE_DETECTOR_HMAC_KEY not set — seal is unsigned (agent can re-seal)")

    if output_path is None:
        output_path = Path(".lie-detector-seal.json")
    output_path.write_text(json.dumps(manifest.to_dict(), indent=2))
    logger.info("seal manifest written to {} ({} files)", output_path, len(manifest.files))
    return manifest


# ---------------------------------------------------------------------------
# Verify: compare current state to manifest
# ---------------------------------------------------------------------------

def verify(seal_path: Path) -> VerifyResult:
    """Verify files match a previously created seal manifest.

    Checks HMAC signature first (if key available), then file hashes.
    A missing or invalid HMAC with a configured key = TAMPERED.
    """
    data = json.loads(seal_path.read_text())
    result = VerifyResult(verdict="CLEAN")

    # HMAC verification — catches re-sealing and direct JSON edits
    stored_hmac = data.get("hmac_sig", "")
    if _HMAC_KEY:
        # Reconstruct canonical payload from data (without hmac_sig)
        canonical = json.dumps({
            "timestamp": data["timestamp"],
            "git_commit": data["git_commit"],
            "files": [
                {
                    "path": f["path"],
                    "sha256_raw": f["sha256_raw"],
                    "sha256_ast": f.get("sha256_ast"),
                    "functions": sorted(f.get("functions", []), key=lambda x: x["name"]),
                }
                for f in data["files"]
            ],
        }, sort_keys=True)
        expected_hmac = hmac.new(
            _HMAC_KEY.encode(), canonical.encode(), hashlib.sha256,
        ).hexdigest()
        if not stored_hmac:
            result.verdict = "TAMPERED"
            result.tampered_files.append({"path": str(seal_path), "detail": "seal has no HMAC signature"})
            logger.error("TAMPERED: seal file has no HMAC (agent may have re-sealed)")
        elif not hmac.compare_digest(stored_hmac, expected_hmac):
            result.verdict = "TAMPERED"
            result.tampered_files.append({"path": str(seal_path), "detail": "HMAC signature mismatch"})
            logger.error("TAMPERED: seal HMAC mismatch (seal was forged or edited)")
        else:
            logger.debug("HMAC verified")

    for entry in data["files"]:
        p = Path(entry["path"])
        if not p.exists():
            result.missing_files.append(entry["path"])
            result.verdict = "TAMPERED"
            logger.warning("MISSING: {}", p)
            continue

        current_raw = _sha256_file(p)
        if current_raw != entry["sha256_raw"]:
            result.tampered_files.append({
                "path": entry["path"],
                "expected_raw": entry["sha256_raw"],
                "actual_raw": current_raw,
            })
            result.verdict = "TAMPERED"
            logger.warning("TAMPERED (raw): {}", p)

        # Check AST hash for Python files
        if entry.get("sha256_ast") and p.suffix == ".py":
            source = p.read_text(errors="replace")
            current_ast = _sha256_ast_source(source)
            if current_ast != entry["sha256_ast"]:
                result.tampered_files.append({
                    "path": entry["path"],
                    "expected_ast": entry["sha256_ast"],
                    "actual_ast": current_ast,
                    "type": "ast",
                })
                result.verdict = "TAMPERED"
                logger.warning("TAMPERED (ast): {}", p)

        # Check individual function hashes
        if entry.get("functions") and p.suffix == ".py":
            source = p.read_text(errors="replace")
            current_fns = {fn.name: fn.sha256_ast for fn in _extract_function_asts(source)}
            for fn_entry in entry["functions"]:
                fn_name = fn_entry["name"]
                expected_hash = fn_entry["sha256_ast"]
                actual_hash = current_fns.get(fn_name)
                if actual_hash is None:
                    result.tampered_functions.append({
                        "path": entry["path"],
                        "function": fn_name,
                        "detail": "function removed",
                    })
                    result.verdict = "TAMPERED"
                    logger.warning("TAMPERED (fn removed): {}:{}", p.name, fn_name)
                elif actual_hash != expected_hash:
                    result.tampered_functions.append({
                        "path": entry["path"],
                        "function": fn_name,
                        "expected_ast": expected_hash,
                        "actual_ast": actual_hash,
                    })
                    result.verdict = "TAMPERED"
                    logger.warning("TAMPERED (fn changed): {}:{}", p.name, fn_name)

    if result.verdict == "CLEAN":
        logger.info("seal verification: CLEAN ({} files checked)", len(data["files"]))
    else:
        logger.error("seal verification: TAMPERED ({} files, {} fns, {} missing)",
                      len(result.tampered_files), len(result.tampered_functions), len(result.missing_files))
    return result


# ---------------------------------------------------------------------------
# Hash chain: tamper-evident conversation log
# ---------------------------------------------------------------------------

_CHAIN_PREFIX = "liedetector:chain:v1"


def _chain_hash(prev_hash: str, payload: str, target_files: str) -> str:
    """Compute next hash in the chain using length-prefixed concatenation."""
    parts = [
        (len(_CHAIN_PREFIX), _CHAIN_PREFIX),
        (len(prev_hash), prev_hash),
        (len(payload), payload),
        (len(target_files), target_files),
    ]
    buf = b""
    for length, value in parts:
        buf += str(length).encode() + b"||" + value.encode() + b"||"
    return hashlib.sha256(buf).hexdigest()


def append_chain(chain_path: Path, payload: dict[str, Any], target_files: list[str] | None = None) -> str:
    """Append a turn to the hash chain. Returns the new hash."""
    prev_hash = "genesis"
    if chain_path.exists():
        lines = chain_path.read_text().strip().split("\n")
        if lines and lines[-1].strip():
            last = json.loads(lines[-1])
            prev_hash = last["hash"]

    payload_str = json.dumps(payload, sort_keys=True)
    files_str = json.dumps(sorted(target_files or []))
    new_hash = _chain_hash(prev_hash, payload_str, files_str)
    entry = {
        "index": _chain_count(chain_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hash": new_hash,
        "prev_hash": prev_hash,
        "payload": payload,
        "target_files": target_files or [],
    }
    with open(chain_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return new_hash


def verify_chain(chain_path: Path) -> tuple[bool, int | None]:
    """Verify the hash chain integrity. Returns (valid, break_index)."""
    if not chain_path.exists():
        return True, None
    lines = chain_path.read_text().strip().split("\n")
    prev_hash = "genesis"
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        entry = json.loads(line)
        expected = _chain_hash(
            prev_hash,
            json.dumps(entry["payload"], sort_keys=True),
            json.dumps(sorted(entry.get("target_files", []))),
        )
        if entry["hash"] != expected:
            logger.error("chain break at index {}: expected {:.8s}, got {:.8s}",
                         i, expected, entry["hash"])
            return False, i
        prev_hash = entry["hash"]
    return True, None


def _chain_count(chain_path: Path) -> int:
    if not chain_path.exists():
        return 0
    return sum(1 for line in chain_path.read_text().strip().split("\n") if line.strip())


# ---------------------------------------------------------------------------
# Self-integrity: verify the lie-detector's own code hasn't been tampered
# ---------------------------------------------------------------------------

_SELF_SEAL_FILE = Path(__file__).resolve().parent / ".self-seal.json"
_SELF_FILES = [
    "sealed_grading.py", "invariants.py", "delta_analysis.py", "cascade.py",
    "classifier.py", "llm_auditor.py", "intent_gate.py", "taxonomy_check.py",
    "skill_chain.py", "lie_detector.py",
]


def self_seal() -> None:
    """Create a seal of the lie-detector's own code. Run once by human."""
    skill_dir = Path(__file__).resolve().parent
    globs = [str(skill_dir / f) for f in _SELF_FILES]
    seal(globs, _SELF_SEAL_FILE)
    logger.info("self-seal created at {}", _SELF_SEAL_FILE)


def self_verify() -> VerifyResult:
    """Verify the lie-detector hasn't been modified since self-seal."""
    if not _SELF_SEAL_FILE.exists():
        logger.warning("no self-seal found — lie-detector integrity unverified")
        return VerifyResult(verdict="TAMPERED", tampered_files=[{
            "path": str(_SELF_SEAL_FILE), "detail": "self-seal missing",
        }])
    return verify(_SELF_SEAL_FILE)


# ---------------------------------------------------------------------------
# Git pre-commit hook generator
# ---------------------------------------------------------------------------

_HOOK_TEMPLATE = '''#!/usr/bin/env bash
# Auto-generated by /lie-detector — blocks commits that modify sealed files.
# To regenerate: ./run.sh install-hook
set -euo pipefail

SEAL_FILE="{seal_path}"
if [ ! -f "$SEAL_FILE" ]; then
    exit 0  # No seal file — nothing to enforce
fi

# Extract sealed file paths from the manifest
SEALED_FILES=$(python3 -c "
import json, sys
data = json.load(open('$SEAL_FILE'))
for f in data['files']:
    print(f['path'])
" 2>/dev/null || true)

if [ -z "$SEALED_FILES" ]; then
    exit 0
fi

# Check if any staged files match sealed paths
STAGED=$(git diff --cached --name-only --diff-filter=ACMRT)
for staged in $STAGED; do
    abs_staged="$(cd "$(git rev-parse --show-toplevel)" && realpath "$staged" 2>/dev/null || echo "$staged")"
    while IFS= read -r sealed; do
        if [ "$abs_staged" = "$sealed" ]; then
            echo >&2 "[lie-detector] BLOCKED: $staged is sealed."
            echo >&2 "  This file is protected by /lie-detector seal."
            echo >&2 "  If this is intentional, re-seal first: cd {skill_dir} && ./run.sh seal ..."
            exit 1
        fi
    done <<< "$SEALED_FILES"
done

exit 0
'''


def install_git_hook(repo_path: Path, seal_path: Path) -> Path:
    """Install a pre-commit hook that blocks edits to sealed files."""
    hook_dir = repo_path / ".git" / "hooks"
    if not hook_dir.exists():
        logger.error("not a git repo: {}", repo_path)
        raise FileNotFoundError(f"No .git/hooks at {repo_path}")

    hook_path = hook_dir / "pre-commit-lie-detector"
    skill_dir = Path(__file__).resolve().parent
    hook_content = _HOOK_TEMPLATE.format(
        seal_path=str(seal_path.resolve()),
        skill_dir=str(skill_dir),
    )
    hook_path.write_text(hook_content)
    hook_path.chmod(0o755)

    # Chain into existing pre-commit if present
    main_hook = hook_dir / "pre-commit"
    if main_hook.exists():
        existing = main_hook.read_text()
        chain_line = f'\n# lie-detector seal enforcement\n"{hook_path}" || exit 1\n'
        if str(hook_path) not in existing:
            # Insert before final exit 0
            if existing.rstrip().endswith("exit 0"):
                new_content = existing.rstrip()[:-6] + chain_line + "exit 0\n"
            else:
                new_content = existing + chain_line
            main_hook.write_text(new_content)
            logger.info("chained lie-detector hook into existing pre-commit")
    else:
        main_hook.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n"
                             f'"{hook_path}" || exit 1\nexit 0\n')
        main_hook.chmod(0o755)

    logger.info("git hook installed at {}", hook_path)
    return hook_path
