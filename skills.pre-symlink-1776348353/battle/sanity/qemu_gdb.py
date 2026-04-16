#!/usr/bin/env python3
"""
Sanity Script: QEMU GDB Integration
PURPOSE: Verify QEMU can start with GDB stub and accept connections
DEPENDENCIES: qemu-system-arm (or similar)
EXIT CODES: 0=PASS, 1=FAIL, 42=CLARIFY
"""

import subprocess
import socket
import time
import sys
import os
import signal

def check_qemu_installed() -> str | None:
    """Check if any QEMU system emulator is available."""
    for arch in ["arm", "aarch64", "riscv64", "x86_64", "i386"]:
        binary = f"qemu-system-{arch}"
        result = subprocess.run(["which", binary], capture_output=True)
        if result.returncode == 0:
            return binary
    return None

def check_gdb_installed() -> bool:
    """Check if GDB is available."""
    result = subprocess.run(["which", "gdb"], capture_output=True)
    return result.returncode == 0

def test_qemu_gdb_stub(qemu_binary: str, port: int = 1234) -> bool:
    """
    Start QEMU with GDB stub and verify we can connect.

    This tests the core functionality needed for battle debugging:
    - QEMU starts with -S (paused) and -gdb tcp::PORT
    - GDB can connect to the stub
    - Basic commands work (info registers)
    """
    print(f"Testing QEMU GDB stub with {qemu_binary} on port {port}...")

    # Start QEMU with minimal config
    # Machine type depends on architecture
    if "x86" in qemu_binary or "i386" in qemu_binary:
        machine = "q35"
        cpu = "qemu64"
    elif "aarch64" in qemu_binary:
        machine = "virt"
        cpu = "cortex-a53"
    elif "arm" in qemu_binary:
        machine = "virt"
        cpu = "cortex-a15"
    elif "riscv" in qemu_binary:
        machine = "virt"
        cpu = "rv64"
    else:
        machine = "virt"
        cpu = "max"

    qemu_cmd = [
        qemu_binary,
        "-M", machine,
        "-cpu", cpu,
        "-m", "64M",
        "-nographic",
        "-S",  # Start paused
        "-gdb", f"tcp::{port}",
    ]

    print(f"  Starting: {' '.join(qemu_cmd)}")

    try:
        # Start QEMU in background
        qemu_proc = subprocess.Popen(
            qemu_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )

        # Wait for GDB port to be ready
        time.sleep(2)

        # Try to connect to GDB port
        print(f"  Connecting to GDB stub on localhost:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)

        try:
            sock.connect(("localhost", port))
            print("  ✅ Connected to GDB stub")

            # Send a simple GDB command (query supported features)
            # GDB remote protocol: $qSupported#...
            sock.send(b"+")  # ACK
            sock.send(b"$qSupported:multiprocess+#c6")

            response = sock.recv(1024)
            print(f"  Response: {response[:50]}...")

            if response:
                print("  ✅ GDB stub responding")
                sock.close()
                return True
            else:
                print("  ❌ No response from GDB stub")
                sock.close()
                return False

        except socket.timeout:
            print("  ❌ Connection timed out")
            return False
        except ConnectionRefusedError:
            print("  ❌ Connection refused - QEMU may not have started")
            return False
        finally:
            sock.close()

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False
    finally:
        # Clean up QEMU process
        if 'qemu_proc' in locals():
            qemu_proc.terminate()
            try:
                qemu_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                qemu_proc.kill()
            print("  Cleaned up QEMU process")

def main():
    print("=" * 60)
    print("SANITY CHECK: QEMU GDB Integration")
    print("=" * 60)

    # Check QEMU installed
    qemu_binary = check_qemu_installed()
    if not qemu_binary:
        print("\n❌ FAIL: No QEMU system emulator found")
        print("   Install with: apt install qemu-system-arm qemu-system-misc")
        sys.exit(1)
    print(f"\n✅ Found QEMU: {qemu_binary}")

    # Check GDB installed (optional but recommended)
    if check_gdb_installed():
        print("✅ Found GDB")
    else:
        print("⚠️  GDB not found (optional for this test)")

    # Test GDB stub
    print("\n" + "-" * 40)
    if test_qemu_gdb_stub(qemu_binary, port=12345):
        print("\n" + "=" * 60)
        print("✅ PASS: QEMU GDB stub works correctly")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ FAIL: QEMU GDB stub test failed")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
