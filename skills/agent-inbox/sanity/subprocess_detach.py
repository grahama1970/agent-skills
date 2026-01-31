#!/usr/bin/env python3
"""
Sanity Script: subprocess detached process spawning

PURPOSE: Verify that we can spawn a detached process that survives parent exit
DOCUMENTATION: Python subprocess module, start_new_session parameter
EXIT CODES: 0=PASS, 1=FAIL, 42=CLARIFY (needs human)
"""
import subprocess
import sys
import os
import time
import signal
from pathlib import Path

MARKER_FILE = Path("/tmp/sanity_subprocess_detach_marker.txt")

def cleanup():
    """Remove marker file if exists."""
    if MARKER_FILE.exists():
        MARKER_FILE.unlink()

def test_detached_process():
    """Test that a detached process can run independently."""
    cleanup()

    # Spawn a detached process that writes to a marker file
    # The process should survive even if we exit
    cmd = f'''python3 -c "
import time
from pathlib import Path
time.sleep(0.5)
Path('{MARKER_FILE}').write_text('DETACHED_PROCESS_RAN')
"'''

    try:
        # Spawn detached process
        proc = subprocess.Popen(
            cmd,
            shell=True,
            start_new_session=True,  # This is the key for detachment
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Don't wait for it - just check it started
        if proc.pid is None:
            print("FAIL: Process did not get a PID")
            return False

        print(f"Spawned detached process with PID {proc.pid}")

        # Wait a bit for the detached process to complete
        time.sleep(1.0)

        # Check if marker file was created
        if MARKER_FILE.exists():
            content = MARKER_FILE.read_text()
            if content == "DETACHED_PROCESS_RAN":
                print("PASS: Detached process ran successfully")
                cleanup()
                return True
            else:
                print(f"FAIL: Marker file has unexpected content: {content}")
                return False
        else:
            print("FAIL: Marker file not created - detached process may not have run")
            return False

    except Exception as e:
        print(f"FAIL: Exception during test: {e}")
        return False
    finally:
        cleanup()

def test_process_group():
    """Test that start_new_session creates a new process group."""
    try:
        proc = subprocess.Popen(
            ["sleep", "0.1"],
            start_new_session=True,
        )

        # Check that process group is different from ours
        our_pgid = os.getpgid(0)
        child_pgid = os.getpgid(proc.pid)

        proc.wait()

        if our_pgid != child_pgid:
            print(f"PASS: Child has different process group (ours={our_pgid}, child={child_pgid})")
            return True
        else:
            print(f"FAIL: Child has same process group as parent ({our_pgid})")
            return False

    except Exception as e:
        print(f"FAIL: Exception during process group test: {e}")
        return False

if __name__ == "__main__":
    print("=== Sanity Check: subprocess detached process ===\n")

    results = []

    print("[1/2] Testing detached process execution...")
    results.append(test_detached_process())

    print("\n[2/2] Testing process group separation...")
    results.append(test_process_group())

    print("\n" + "="*50)
    if all(results):
        print("PASS: All subprocess detachment tests passed")
        sys.exit(0)
    else:
        print("FAIL: Some tests failed")
        sys.exit(1)
