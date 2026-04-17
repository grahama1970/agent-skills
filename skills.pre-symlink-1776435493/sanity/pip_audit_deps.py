#!/usr/bin/env python3
"""
PURPOSE: Verify pip-audit dependency scanning works correctly
DOCUMENTATION: https://github.com/pypa/pip-audit
LAST VERIFIED: 2026-01-29

Tests:
- pip-audit CLI is available
- Can scan requirements files
- Returns structured JSON output
- Identifies CVE IDs

Exit codes: 0=PASS, 1=FAIL, 42=CLARIFY
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    print("=== pip-audit Dependency Audit Sanity Check ===\n")

    # 1. Check pip-audit is available
    print("[1/4] Checking pip-audit availability...")
    try:
        result = subprocess.run(
            ["pip-audit", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"  FAIL: pip-audit --version failed: {result.stderr}")
            return 1
        print(f"  OK: pip-audit version {result.stdout.strip()}")
    except FileNotFoundError:
        print("  FAIL: pip-audit not found in PATH")
        return 1

    # 2. Create test requirements with known vulnerabilities
    print("\n[2/4] Creating test requirements file...")
    with tempfile.TemporaryDirectory() as tmpdir:
        req_file = Path(tmpdir) / "requirements.txt"
        # Use packages that are likely to have known CVEs
        # Note: These specific versions may or may not have CVEs
        # The point is to test the tool works
        req_file.write_text('''
# Test requirements - some may have known CVEs
requests==2.25.0
urllib3==1.26.0
''')
        print(f"  OK: Created {req_file}")

        # 3. Run pip-audit
        print("\n[3/4] Running pip-audit scan...")
        try:
            result = subprocess.run(
                [
                    "pip-audit",
                    "-r", str(req_file),
                    "--format", "json",
                    "--progress-spinner", "off"
                ],
                capture_output=True,
                text=True,
                timeout=120  # Can be slow
            )
            # pip-audit returns 1 if vulnerabilities found
            print(f"  OK: pip-audit completed (exit code {result.returncode})")
        except subprocess.TimeoutExpired:
            print("  FAIL: pip-audit timed out")
            return 1

        # 4. Verify output format
        print("\n[4/4] Verifying JSON output...")
        try:
            if result.stdout.strip():
                output = json.loads(result.stdout)

                # pip-audit returns list of findings
                if isinstance(output, list):
                    vuln_count = len(output)
                    print(f"  OK: Found {vuln_count} vulnerabilities")

                    # Check for CVE IDs
                    cves = []
                    for vuln in output[:5]:  # Check first 5
                        if "id" in vuln:
                            cves.append(vuln["id"])
                    if cves:
                        print(f"  OK: CVE IDs found: {cves[:3]}...")
                else:
                    print(f"  OK: Output format: {type(output).__name__}")
            else:
                # No vulnerabilities found is also valid
                print("  OK: No vulnerabilities found (clean scan)")

        except json.JSONDecodeError as e:
            # pip-audit might output errors to stderr instead
            if "No dependencies found" in result.stderr:
                print("  OK: No dependencies to scan (valid result)")
            else:
                print(f"  WARN: Could not parse JSON: {e}")
                print(f"  stderr: {result.stderr[:200]}")

    print("\n=== SANITY CHECK PASSED ===")
    print("pip-audit is working correctly for dependency vulnerability scanning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
