#!/usr/bin/env python3
"""
Claim verifiers for /create-walkthrough.

Each verifier takes a Claim and checks it against the codebase/environment,
populating the verdict, detail, and actual_value fields.

All rg commands use --no-ignore --hidden to search .pi/skills/ (gitignored, hidden).
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from models import Claim, Verdict


# ============================================================================
# Verifier Functions
# ============================================================================


def verify_file_path(claim: Claim) -> Claim:
    """Verify that a claimed file path exists."""
    path = Path(claim.value)
    if path.exists():
        claim.verdict = Verdict.VERIFIED
        claim.detail = f"{claim.value} exists"
        if path.is_file():
            claim.detail += f" ({sum(1 for _ in open(path))} lines)"
    else:
        claim.verdict = Verdict.UNVERIFIED
        claim.detail = f"{claim.value} does not exist"
    return claim


def verify_line_count(claim: Claim) -> Claim:
    """Verify that a file has the claimed number of lines."""
    parts = claim.value.split(":")
    if len(parts) != 2:
        claim.verdict = Verdict.SKIPPED
        claim.detail = "Could not parse file:count"
        return claim

    filename, claimed_count = parts[0], int(parts[1])

    # Try to find the file — it might be a basename
    candidates = []
    if os.path.isabs(filename) and Path(filename).exists():
        candidates = [filename]
    else:
        for root_dir in [".", "/home"]:
            try:
                result = subprocess.run(
                    ["find", root_dir, "-name", os.path.basename(filename),
                     "-type", "f", "-maxdepth", "8"],
                    capture_output=True, text=True, timeout=5,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                candidates = [
                    p.strip() for p in result.stdout.strip().split("\n") if p.strip()
                ]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            if candidates:
                break

    if not candidates:
        claim.verdict = Verdict.SKIPPED
        claim.detail = f"File {filename} not found for line count check"
        return claim

    filepath = candidates[0]
    try:
        actual_count = sum(1 for _ in open(filepath))
        claim.actual_value = str(actual_count)
        if actual_count == claimed_count:
            claim.verdict = Verdict.VERIFIED
            claim.detail = f"{filename}: {actual_count} lines"
        else:
            claim.verdict = Verdict.MISMATCH
            claim.detail = (
                f"{filename}: walkthrough says {claimed_count} lines, "
                f"actual is {actual_count}"
            )
    except (OSError, PermissionError) as e:
        claim.verdict = Verdict.SKIPPED
        claim.detail = f"Cannot read {filepath}: {e}"

    return claim


def verify_function_line(claim: Claim) -> Claim:
    """Verify that a function exists near the claimed line number."""
    parts = claim.value.split(":")
    if len(parts) != 2:
        claim.verdict = Verdict.SKIPPED
        return claim

    func_name, claimed_line = parts[0], int(parts[1])

    try:
        result = subprocess.run(
            ["rg", "-n", "--no-ignore", "--hidden", f"def {func_name}\\(", "--type", "py", "-l"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        claim.verdict = Verdict.SKIPPED
        claim.detail = "rg not available"
        return claim

    if not files:
        claim.verdict = Verdict.UNVERIFIED
        claim.detail = f"Function {func_name}() not found in any .py file"
        return claim

    for filepath in files:
        try:
            result = subprocess.run(
                ["rg", "-n", "--no-ignore", "--hidden", f"def {func_name}\\(", filepath],
                capture_output=True, text=True, timeout=5,
                env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            for match_line in result.stdout.strip().split("\n"):
                if match_line:
                    actual_line = int(match_line.split(":")[0])
                    claim.actual_value = f"{filepath}:{actual_line}"
                    tolerance = max(20, claimed_line * 0.1)
                    if abs(actual_line - claimed_line) <= tolerance:
                        claim.verdict = Verdict.VERIFIED
                        claim.detail = (
                            f"{func_name}() found at {filepath}:{actual_line} "
                            f"(claimed line {claimed_line})"
                        )
                    else:
                        claim.verdict = Verdict.MISMATCH
                        claim.detail = (
                            f"{func_name}() at {filepath}:{actual_line}, "
                            f"walkthrough says line {claimed_line} "
                            f"(off by {abs(actual_line - claimed_line)})"
                        )
                    return claim
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    claim.verdict = Verdict.SKIPPED
    claim.detail = f"Could not verify line number for {func_name}()"
    return claim


def verify_env_default(claim: Claim) -> Claim:
    """Verify an environment variable's default value in code."""
    parts = claim.value.split("=", 1)
    if len(parts) != 2:
        claim.verdict = Verdict.SKIPPED
        return claim

    env_var, claimed_default = parts

    try:
        result = subprocess.run(
            ["rg", "-n", "--no-ignore", "--hidden", f'"{env_var}"', "--type", "py"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            for match_line in result.stdout.strip().split("\n"):
                if claimed_default in match_line:
                    claim.verdict = Verdict.VERIFIED
                    claim.detail = f'{env_var} default "{claimed_default}" found: {match_line.strip()[:100]}'
                    return claim

            first_match = result.stdout.strip().split("\n")[0]
            claim.verdict = Verdict.MISMATCH
            claim.actual_value = first_match.strip()[:100]
            claim.detail = (
                f'{env_var} found but default "{claimed_default}" not confirmed. '
                f"First match: {first_match.strip()[:100]}"
            )
        else:
            claim.verdict = Verdict.UNVERIFIED
            claim.detail = f"{env_var} not found in any .py file"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        claim.verdict = Verdict.SKIPPED
        claim.detail = "rg not available"

    return claim


def verify_package_missing(claim: Claim) -> Claim:
    """Verify that a package is NOT installed."""
    pkg = claim.value.replace("-", "_").replace(".", "_").lower()

    try:
        result = subprocess.run(
            ["rg", "-l", "--no-ignore", "--hidden", pkg, "--glob", "pyproject.toml"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            claim.verdict = Verdict.MISMATCH
            claim.detail = (
                f'"{claim.value}" claimed missing but found in: '
                f"{result.stdout.strip()}"
            )
            return claim
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {pkg}"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            claim.verdict = Verdict.MISMATCH
            claim.detail = f'"{claim.value}" claimed missing but importable in current env'
            return claim
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ["rg", "-l", "--no-ignore", "--hidden", pkg, "--glob", "*.toml", "--glob", "*.txt",
             "--glob", "*.cfg", "-g", "!.git"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            claim.verdict = Verdict.MISMATCH
            claim.detail = (
                f'"{claim.value}" claimed missing but referenced in: '
                f"{result.stdout.strip().split(chr(10))[0]}"
            )
            return claim
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    claim.verdict = Verdict.VERIFIED
    claim.detail = f'"{claim.value}" confirmed not found in project'
    return claim


def verify_package_present(claim: Claim) -> Claim:
    """Verify that a package IS installed/available."""
    pkg = claim.value

    try:
        result = subprocess.run(
            ["rg", "-l", "--no-ignore", "--hidden", pkg, "--glob", "pyproject.toml"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            claim.verdict = Verdict.VERIFIED
            claim.detail = f'"{pkg}" found in {result.stdout.strip()}'
            return claim
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    claim.verdict = Verdict.UNVERIFIED
    claim.detail = f'"{pkg}" not found in pyproject.toml'
    return claim


def verify_port(claim: Claim) -> Claim:
    """Verify a port number claim by searching code."""
    port = claim.value

    try:
        result = subprocess.run(
            ["rg", "-n", "--no-ignore", "--hidden", port, "--type", "py"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            claim.verdict = Verdict.VERIFIED
            first = result.stdout.strip().split("\n")[0]
            claim.detail = f"Port {port} found in code: {first.strip()[:100]}"
        else:
            claim.verdict = Verdict.UNVERIFIED
            claim.detail = f"Port {port} not found in any .py file"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        claim.verdict = Verdict.SKIPPED
        claim.detail = "rg not available"

    return claim


def verify_collection(claim: Claim) -> Claim:
    """Verify an ArangoDB collection is referenced in code."""
    name = claim.value
    try:
        result = subprocess.run(
            ["rg", "-n", "--no-ignore", "--hidden", f'"{name}"', "--type", "py"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            first = result.stdout.strip().split("\n")[0]
            claim.verdict = Verdict.VERIFIED
            claim.detail = f'Collection "{name}" referenced in code: {first.strip()[:100]}'
        else:
            claim.verdict = Verdict.UNVERIFIED
            claim.detail = f'Collection "{name}" not found in any .py file'
    except (subprocess.TimeoutExpired, FileNotFoundError):
        claim.verdict = Verdict.SKIPPED
        claim.detail = "rg not available"
    return claim


def verify_field_name(claim: Claim) -> Claim:
    """Verify a field/attribute name exists in code."""
    name = claim.value
    try:
        result = subprocess.run(
            ["rg", "-n", "--no-ignore", "--hidden", f'["\']?{name}["\']?\\s*[=:]', "--type", "py"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            first = result.stdout.strip().split("\n")[0]
            claim.verdict = Verdict.VERIFIED
            claim.detail = f'Field "{name}" found: {first.strip()[:100]}'
        else:
            claim.verdict = Verdict.UNVERIFIED
            claim.detail = f'Field "{name}" not found as assignment/key in any .py file'
    except (subprocess.TimeoutExpired, FileNotFoundError):
        claim.verdict = Verdict.SKIPPED
        claim.detail = "rg not available"
    return claim


def verify_class_def(claim: Claim) -> Claim:
    """Verify a class/TypedDict definition exists."""
    name = claim.value
    try:
        result = subprocess.run(
            ["rg", "-n", "--no-ignore", "--hidden", f"class {name}\\b", "--type", "py"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            first = result.stdout.strip().split("\n")[0]
            claim.verdict = Verdict.VERIFIED
            claim.detail = f"class {name} found: {first.strip()[:100]}"
        else:
            claim.verdict = Verdict.UNVERIFIED
            claim.detail = f"class {name} not found in any .py file"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        claim.verdict = Verdict.SKIPPED
        claim.detail = "rg not available"
    return claim


def verify_import_from(claim: Claim) -> Claim:
    """Verify a 'from X import Y' statement exists in code."""
    parts = claim.value.split(":", 1)
    if len(parts) != 2:
        claim.verdict = Verdict.SKIPPED
        return claim

    module, names_str = parts
    first_name = names_str.split(",")[0].strip()

    try:
        result = subprocess.run(
            ["rg", "-n", "--no-ignore", "--hidden", f"from {re.escape(module)} import.*{re.escape(first_name)}", "--type", "py"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            first = result.stdout.strip().split("\n")[0]
            claim.verdict = Verdict.VERIFIED
            claim.detail = f"Import found: {first.strip()[:100]}"
        else:
            claim.verdict = Verdict.UNVERIFIED
            claim.detail = f'"from {module} import {first_name}" not found in any .py file'
    except (subprocess.TimeoutExpired, FileNotFoundError):
        claim.verdict = Verdict.SKIPPED
        claim.detail = "rg not available"
    return claim


def verify_import_module(claim: Claim) -> Claim:
    """Verify an 'import X' statement exists in code."""
    module = claim.value
    try:
        result = subprocess.run(
            ["rg", "-n", "--no-ignore", "--hidden", f"import {re.escape(module)}\\b", "--type", "py"],
            capture_output=True, text=True, timeout=10, cwd=".",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout.strip():
            first = result.stdout.strip().split("\n")[0]
            claim.verdict = Verdict.VERIFIED
            claim.detail = f"Import found: {first.strip()[:100]}"
        else:
            claim.verdict = Verdict.UNVERIFIED
            claim.detail = f'"import {module}" not found in any .py file'
    except (subprocess.TimeoutExpired, FileNotFoundError):
        claim.verdict = Verdict.SKIPPED
        claim.detail = "rg not available"
    return claim


def verify_relative_path(claim: Claim) -> Claim:
    """Verify a relative file path exists in the project."""
    rel = claim.value
    for base in [Path("."), Path(".pi/skills"), Path("packages")]:
        candidate = base / rel
        if candidate.exists():
            claim.verdict = Verdict.VERIFIED
            claim.detail = f"{rel} found at {candidate}"
            return claim

    basename = Path(rel).name
    try:
        result = subprocess.run(
            ["find", ".", "-name", basename, "-type", "f", "-maxdepth", "8"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        candidates = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        if candidates:
            claim.verdict = Verdict.VERIFIED
            claim.detail = f"{rel} found as {candidates[0]}"
            return claim
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    claim.verdict = Verdict.UNVERIFIED
    claim.detail = f"{rel} not found in project"
    return claim


# ============================================================================
# Verifier Registry
# ============================================================================

VERIFIERS = {
    "file_path": verify_file_path,
    "line_count": verify_line_count,
    "function_line": verify_function_line,
    "env_default": verify_env_default,
    "package_missing": verify_package_missing,
    "package_present": verify_package_present,
    "port": verify_port,
    "collection": verify_collection,
    "field_name": verify_field_name,
    "class_def": verify_class_def,
    "import_from": verify_import_from,
    "import_module": verify_import_module,
    "relative_path": verify_relative_path,
}


def verify_claims(claims: list[Claim]) -> list[Claim]:
    """Run verification on all claims."""
    for claim in claims:
        verifier = VERIFIERS.get(claim.claim_type)
        if verifier:
            verifier(claim)
        else:
            claim.verdict = Verdict.SKIPPED
            claim.detail = f"No verifier for type: {claim.claim_type}"
    return claims
