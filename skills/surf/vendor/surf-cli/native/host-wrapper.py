#!/usr/bin/env python3
import subprocess
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
host_path = os.path.join(script_dir, "host.cjs")

proc = subprocess.Popen(
    ["/opt/homebrew/bin/node", host_path],
    stdin=sys.stdin,
    stdout=sys.stdout,
    stderr=sys.stderr
)
proc.wait()
