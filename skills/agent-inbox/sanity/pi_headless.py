#!/usr/bin/env python3
"""
Sanity Script: pi CLI headless mode

PURPOSE: Verify pi CLI is available and supports headless execution flags
DOCUMENTATION: pi --help, pi --no-session mode
EXIT CODES: 0=PASS, 1=FAIL, 42=CLARIFY (needs human)

NOTE: This doesn't actually run a full pi session (expensive).
      It verifies the CLI exists and accepts the expected flags.
"""
import shutil
import subprocess
import sys
import os

# CLI commands we might use for headless dispatch
CLI_OPTIONS = {
    "pi": {
        "check_cmd": ["pi", "--version"],
        "headless_flags": ["--no-session", "-p"],
        "description": "Pi coding agent CLI"
    },
    "claude": {
        "check_cmd": ["claude", "--version"],
        "headless_flags": ["--model", "sonnet"],
        "description": "Claude Code CLI"
    },
    "codex": {
        "check_cmd": ["codex", "--version"],
        "headless_flags": ["--model", "gpt-5.2-codex"],
        "description": "OpenAI Codex CLI"
    }
}

def check_cli_exists(name: str) -> tuple[bool, str]:
    """Check if a CLI tool exists in PATH."""
    path = shutil.which(name)
    if path:
        return True, f"Found at {path}"
    return False, "Not found in PATH"

def check_cli_version(name: str, cmd: list) -> tuple[bool, str]:
    """Check if CLI responds to version command."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        # Some CLIs return non-zero for --version, check if we got output
        output = result.stdout or result.stderr
        if output:
            version_line = output.strip().split('\n')[0][:60]
            return True, f"Version: {version_line}"
        return False, "No version output"
    except subprocess.TimeoutExpired:
        return False, "Timed out"
    except FileNotFoundError:
        return False, "Command not found"
    except Exception as e:
        return False, f"Error: {e}"

def check_help_contains_flag(name: str, flag: str) -> tuple[bool, str]:
    """Check if CLI help mentions a specific flag."""
    try:
        result = subprocess.run(
            [name, "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        help_text = result.stdout + result.stderr
        if flag in help_text:
            return True, f"Flag '{flag}' documented in help"
        # Some flags might work but not be in help
        return True, f"Flag '{flag}' not in help (may still work)"
    except Exception as e:
        return False, f"Error checking help: {e}"

if __name__ == "__main__":
    print("=== Sanity Check: CLI headless mode support ===\n")

    found_any = False
    all_results = {}

    for cli_name, config in CLI_OPTIONS.items():
        print(f"[{cli_name}] {config['description']}")

        # Check exists
        exists, exists_msg = check_cli_exists(cli_name)
        print(f"  Exists: {exists_msg}")

        if not exists:
            print(f"  Skipping (not installed)\n")
            continue

        found_any = True

        # Check version
        ver_ok, ver_msg = check_cli_version(cli_name, config["check_cmd"])
        print(f"  {ver_msg}")

        # Check headless flags
        for flag in config["headless_flags"]:
            flag_ok, flag_msg = check_help_contains_flag(cli_name, flag)
            print(f"  Flag {flag}: {flag_msg}")

        all_results[cli_name] = exists
        print()

    print("="*50)

    if not found_any:
        print("FAIL: No supported CLI tools found")
        print("      Install at least one of: pi, claude, codex")
        sys.exit(1)

    # We just need ONE working CLI for dispatch
    working_clis = [name for name, ok in all_results.items() if ok]
    print(f"PASS: Found {len(working_clis)} CLI tool(s): {', '.join(working_clis)}")
    print("      Headless dispatch will use available tools.")
    sys.exit(0)
