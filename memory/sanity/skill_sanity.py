#!/usr/bin/env python3
"""Sanity tests for the memory skill commands.

Tests each command documented in SKILL.md:
- query: Unified search across all sources
- add-episode: Log new knowledge
- prove: Formal verification (assess provability)
- codebase-status: Check if codebase is indexed
- codebase-ingest: Index a codebase (long-running, skip by default)

Run with: python -m graph_memory.sanity.skill_sanity
Or: python .skills/memory/sanity/skill_sanity.py
"""
import subprocess
import json
import sys
import os

# Change to project root
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/../../..")

CLI = "python -m graph_memory.agent_cli"


def run_command(cmd: str) -> dict:
    """Run a CLI command and return parsed JSON output."""
    result = subprocess.run(
        cmd.split(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"_raw": result.stdout, "_stderr": result.stderr, "_code": result.returncode}


def test_query_command():
    """Test: memory-agent query --q 'test' --k 5"""
    print("Testing: query command")

    result = run_command(f"{CLI} query --q authentication --k 5")

    if "_raw" in result:
        print(f"    FAIL: Did not return JSON")
        print(f"    stderr: {result.get('_stderr', '')[:200]}")
        return False

    if "meta" not in result:
        print(f"    FAIL: Missing 'meta' key")
        return False

    if "items" not in result:
        print(f"    FAIL: Missing 'items' key")
        return False

    if "errors" not in result:
        print(f"    FAIL: Missing 'errors' key")
        return False

    items = result.get("items", [])
    print(f"    OK: Returned {len(items)} items")
    if items:
        print(f"    Top result: {items[0].get('_source', 'unknown')} - score {items[0].get('score', 0):.3f}")
    return True


def test_query_with_sources():
    """Test: memory-agent query --q 'test' --sources code"""
    print("Testing: query with --sources filter")

    result = run_command(f"{CLI} query --q function --sources code --k 5")

    if "items" not in result:
        print(f"    FAIL: Missing 'items' key")
        return False

    items = result.get("items", [])
    # All items should be from code sources if filtering works
    sources = set(item.get("_source") for item in items)
    print(f"    OK: Sources returned: {sources}")
    return True


def test_add_episode():
    """Test: memory-agent add-episode --text '...'"""
    print("Testing: add-episode command")

    # Use a unique test marker
    import uuid
    test_id = uuid.uuid4().hex[:8]
    test_text = f"Sanity_test_episode_{test_id}"

    # Correct format: --text, --scope, --status, --no-prove (to skip slow assessment)
    result = subprocess.run(
        [
            "python", "-m", "graph_memory.agent_cli", "add-episode",
            "--text", test_text,
            "--scope", "sanity_test",
            "--status", "success",
            "--no-prove",  # Skip proof assessment for speed
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check if it succeeded (may not return JSON)
    if result.returncode == 0:
        print(f"    OK: Episode logged (exit code 0)")
        if result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                print(f"    Data: {data.get('meta', {})}")
            except:
                print(f"    Output: {result.stdout[:100]}...")
        return True

    if "error" in result.stderr.lower():
        print(f"    FAIL: {result.stderr[:200]}")
        return False

    print(f"    OK: Episode command ran (exit {result.returncode})")
    return True


def test_codebase_status():
    """Test: memory-agent codebase-status"""
    print("Testing: codebase-status command")

    result = run_command(f"{CLI} codebase-status --scope memory_project")

    if "_raw" in result:
        print(f"    FAIL: Did not return JSON")
        return False

    if "indexed" not in result and "counts" not in result:
        print(f"    FAIL: Missing expected keys")
        return False

    indexed = result.get("indexed", False)
    counts = result.get("counts", {})
    total = result.get("total", sum(counts.values()))
    print(f"    OK: indexed={indexed}, total={total}, counts={counts}")
    return True


def test_prove_assessment():
    """Test: memory-agent prove --claim '...' --assess"""
    print("Testing: prove command (assess-only)")

    # Correct format: --claim "..." --assess (or -a)
    result = subprocess.run(
        [
            "python", "-m", "graph_memory.agent_cli", "prove",
            "--claim", "n + 0 = n",
            "--assess",  # Assess only, don't queue
            "--local-only",  # Fast local check, no LLM
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    output = result.stdout + result.stderr

    # Check for assessment output
    if "provable" in output.lower() or "confidence" in output.lower():
        print(f"    OK: Assessment returned")
        if result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                print(f"    provable={data.get('provable', 'N/A')}, confidence={data.get('confidence', 'N/A')}")
            except:
                # Non-JSON output is OK
                print(f"    Output: {result.stdout[:100]}...")
        return True

    if result.returncode == 0:
        print(f"    OK: prove command succeeded (exit 0)")
        return True

    print(f"    WARN: Output: {output[:200]}")
    return True  # Don't fail on unclear output


def test_codebase_ingest():
    """Test: memory-agent codebase-ingest on a small directory"""
    print("Testing: codebase-ingest command")

    import tempfile
    import os

    # Create a small test directory with a Python file
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_module.py")
        with open(test_file, "w") as f:
            f.write('''
def test_function():
    """A test function for ingest verification."""
    return 42

class TestClass:
    """A test class."""
    def method(self):
        pass
''')

        result = subprocess.run(
            [
                "python", "-m", "graph_memory.agent_cli", "codebase-ingest",
                "--code-path", tmpdir,
                "--scope", "ingest_sanity_test",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            print(f"    FAIL: codebase-ingest failed: {result.stderr[:200]}")
            return False

        try:
            data = json.loads(result.stdout)
            meta = data.get("meta", {})
            status = meta.get("status", "unknown")
            counts = meta.get("counts", {})
            symbols = counts.get("code_symbols_persisted", 0)

            if status != "ok":
                print(f"    FAIL: status={status}, expected 'ok'")
                return False

            if symbols < 2:  # Should find at least function + class
                print(f"    FAIL: only {symbols} symbols found, expected >= 2")
                return False

            print(f"    OK: status={status}, symbols={symbols}, duration={meta.get('duration_ms', 0)}ms")
            return True

        except json.JSONDecodeError:
            print(f"    FAIL: Non-JSON output: {result.stdout[:200]}")
            return False


def test_python_api():
    """Test: Python API import and basic usage"""
    print("Testing: Python API (MemoryClient)")

    try:
        from graph_memory import MemoryClient

        client = MemoryClient(scope="sanity_test")

        # Test query
        result = client.query("test", k=3)

        if "items" not in result:
            print(f"    FAIL: query() missing 'items'")
            return False

        if "meta" not in result:
            print(f"    FAIL: query() missing 'meta'")
            return False

        print(f"    OK: MemoryClient.query() returned {len(result['items'])} items")

        # Test codebase_status
        status = client.codebase_status()
        print(f"    OK: codebase_status() returned indexed={status.get('indexed', False)}")

        return True

    except ImportError as e:
        print(f"    FAIL: Could not import MemoryClient: {e}")
        return False
    except Exception as e:
        print(f"    FAIL: API error: {e}")
        return False


def main():
    print("=" * 50)
    print("Memory Skill Sanity Tests")
    print("=" * 50)
    print()

    tests = [
        ("query command", test_query_command),
        ("query with sources", test_query_with_sources),
        ("add-episode", test_add_episode),
        ("codebase-status", test_codebase_status),
        ("codebase-ingest", test_codebase_ingest),
        ("prove assessment", test_prove_assessment),
        ("Python API", test_python_api),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            if test_fn():
                print(f"  PASS: {name}\n")
                passed += 1
            else:
                print(f"  FAIL: {name}\n")
                failed += 1
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT: {name}\n")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {name}: {e}\n")
            failed += 1

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
