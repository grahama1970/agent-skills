"""Build script for mypyc compilation of parser modules."""
import subprocess
import sys
import os


MODULES = [
    "src/python/parsers/stream.py",
    "src/python/parsers/network.py",
    "src/python/parsers/hybrid.py",
    "src/python/merger.py",
    "src/python/models.py",
]


def build():
    """Compile parser modules with mypyc.

    Returns a dict mapping module path to status string:
      "PASS"  – compiled successfully
      "SKIP"  – file not found
      "WARN: <reason>" – compilation failed (non-fatal)
    """
    skill_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    results = {}
    for mod in MODULES:
        full_path = os.path.join(skill_dir, mod)
        if not os.path.exists(full_path):
            print(f"SKIP: {mod} not found")
            results[mod] = "SKIP"
            continue
        try:
            result = subprocess.run(
                [sys.executable, "-m", "mypyc", full_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                print(f"PASS: {mod} compiled")
                results[mod] = "PASS"
            else:
                msg = result.stderr[:200].strip()
                print(f"WARN: {mod} failed: {msg}")
                results[mod] = f"WARN: {msg}"
        except Exception as e:
            print(f"WARN: {mod} error: {e}")
            results[mod] = f"WARN: {e}"
    return results


if __name__ == "__main__":
    build()
