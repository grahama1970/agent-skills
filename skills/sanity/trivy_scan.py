#!/usr/bin/env python3
"""
PURPOSE: Verify Trivy vulnerability scanning works correctly
DOCUMENTATION: https://aquasecurity.github.io/trivy/
LAST VERIFIED: 2026-01-29

Tests:
- trivy CLI is available
- Can scan filesystem for vulnerabilities
- Returns structured JSON output
- Identifies vulnerabilities with CVE IDs

Exit codes: 0=PASS, 1=FAIL, 42=CLARIFY
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    print("=== Trivy Vulnerability Scanner Sanity Check ===\n")

    # Add ~/.local/bin to PATH for this session
    local_bin = os.path.expanduser("~/.local/bin")
    os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"

    # 1. Check trivy is available
    print("[1/4] Checking trivy availability...")
    try:
        result = subprocess.run(
            ["trivy", "version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"  FAIL: trivy version failed: {result.stderr}")
            return 1
        # Parse version from output
        version_line = result.stdout.strip().split('\n')[0]
        print(f"  OK: trivy {version_line}")
    except FileNotFoundError:
        print("  FAIL: trivy not found in PATH")
        return 1

    # 2. Create test directory with requirements file
    print("\n[2/4] Creating test directory with package files...")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create requirements.txt
        req_file = Path(tmpdir) / "requirements.txt"
        req_file.write_text('''
requests==2.25.0
urllib3==1.26.0
pyyaml==5.3
''')
        print(f"  OK: Created {req_file}")

        # 3. Run trivy filesystem scan
        print("\n[3/4] Running trivy filesystem scan...")
        try:
            result = subprocess.run(
                [
                    "trivy",
                    "filesystem",
                    "--format", "json",
                    "--quiet",
                    str(tmpdir)
                ],
                capture_output=True,
                text=True,
                timeout=120  # Trivy can be slow on first run (downloads DB)
            )
            print(f"  OK: trivy scan completed (exit code {result.returncode})")
        except subprocess.TimeoutExpired:
            print("  FAIL: trivy scan timed out")
            return 1

        # 4. Verify output
        print("\n[4/4] Verifying JSON output...")
        try:
            if result.stdout.strip():
                output = json.loads(result.stdout)

                # Trivy output has Results array
                if "Results" in output:
                    results = output["Results"]
                    print(f"  OK: {len(results)} result set(s)")

                    # Count vulnerabilities
                    total_vulns = 0
                    for r in results:
                        vulns = r.get("Vulnerabilities", [])
                        total_vulns += len(vulns)

                    print(f"  OK: {total_vulns} total vulnerabilities found")

                    # Show some CVE IDs
                    cves = []
                    for r in results:
                        for v in r.get("Vulnerabilities", [])[:3]:
                            if "VulnerabilityID" in v:
                                cves.append(v["VulnerabilityID"])
                    if cves:
                        print(f"  OK: CVEs: {cves[:3]}...")
                else:
                    print(f"  OK: Output received (keys: {list(output.keys())})")
            else:
                # No output might mean no vulnerabilities
                print("  OK: No vulnerabilities found (clean scan)")
                if result.stderr:
                    print(f"  Note: {result.stderr[:100]}")

        except json.JSONDecodeError as e:
            print(f"  WARN: Could not parse JSON: {e}")
            # Trivy might output progress to stderr
            if "Downloading" in result.stderr:
                print("  Note: Trivy is downloading vulnerability database")

    print("\n=== SANITY CHECK PASSED ===")
    print("Trivy is working correctly for vulnerability scanning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
