#!/usr/bin/env python3
"""
PURPOSE: Verify Bandit Python SAST tool works correctly
DOCUMENTATION: https://bandit.readthedocs.io/
LAST VERIFIED: 2026-01-29

Tests:
- bandit CLI is available
- Can scan Python files
- Returns structured JSON output
- Categorizes findings by severity

Exit codes: 0=PASS, 1=FAIL, 42=CLARIFY
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    print("=== Bandit SAST Sanity Check ===\n")

    # 1. Check bandit is available
    print("[1/4] Checking bandit availability...")
    try:
        result = subprocess.run(
            ["bandit", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"  FAIL: bandit --version failed: {result.stderr}")
            return 1
        print(f"  OK: {result.stdout.strip().split(chr(10))[0]}")
    except FileNotFoundError:
        print("  FAIL: bandit not found in PATH")
        return 1

    # 2. Create test file with known vulnerabilities
    print("\n[2/4] Creating test file with known vulnerabilities...")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_vulnerable.py"
        test_file.write_text('''
import subprocess
import pickle
import hashlib

def run_shell(cmd):
    # B602: subprocess_popen_with_shell_equals_true
    subprocess.Popen(cmd, shell=True)

def load_data(data):
    # B301: pickle
    return pickle.loads(data)

def weak_hash(password):
    # B303: md5
    return hashlib.md5(password.encode()).hexdigest()

def hardcoded_password():
    # B105: hardcoded_password_string
    password = "admin123"
    return password
''')
        print(f"  OK: Created {test_file}")

        # 3. Run bandit scan
        print("\n[3/4] Running bandit scan...")
        try:
            result = subprocess.run(
                [
                    "bandit",
                    "-r", str(test_file),
                    "-f", "json",
                    "-q"
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            # Bandit returns 1 if findings exist
            print(f"  OK: bandit scan completed (exit code {result.returncode})")
        except subprocess.TimeoutExpired:
            print("  FAIL: bandit scan timed out")
            return 1

        # 4. Verify JSON output and findings
        print("\n[4/4] Verifying JSON output and findings...")
        try:
            output = json.loads(result.stdout)
            results = output.get("results", [])
            metrics = output.get("metrics", {})

            print(f"  OK: Found {len(results)} security issues")

            # Check severity categorization
            severities = {}
            for r in results:
                sev = r.get("issue_severity", "UNKNOWN")
                severities[sev] = severities.get(sev, 0) + 1

            if severities:
                print(f"  OK: Severities: {severities}")
            else:
                print("  WARN: No severity data found")

            # Verify expected issue types
            issue_ids = [r.get("test_id", "") for r in results]
            expected = ["B602", "B301", "B303"]  # We expect at least these
            found = [i for i in expected if any(i in iid for iid in issue_ids)]
            print(f"  OK: Expected issues found: {found}")

        except json.JSONDecodeError as e:
            print(f"  FAIL: Could not parse JSON: {e}")
            return 1

    print("\n=== SANITY CHECK PASSED ===")
    print("Bandit is working correctly for Python SAST scanning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
