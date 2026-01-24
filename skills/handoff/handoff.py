#!/usr/bin/env python3
import os
import subprocess
import json
import sys
from pathlib import Path

def run_command(cmd, cwd=None):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, shell=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {str(e)}"

def get_git_info():
    info = {}
    info["branch"] = run_command("git rev-parse --abbrev-ref HEAD")
    info["last_5_commits"] = run_command("git log -n 5 --oneline")
    info["uncommitted_changes"] = run_command("git status --porcelain")
    return info

def detect_ecosystem():
    files = os.listdir(".")
    if "pyproject.toml" in files or "requirements.txt" in files or "setup.py" in files:
        return "Python"
    if "package.json" in files:
        return "Node.js"
    if "Cargo.toml" in files:
        return "Rust"
    return "Unknown"

def find_docs():
    docs = []
    for doc in ["README.md", "CONTEXT.md", "HANDOFF.md", "DEVELOPMENT.md", "01_TASKS.md"]:
        if os.path.exists(doc):
            docs.append(doc)
    return docs

def find_todos():
    return run_command("rg 'TODO|FIXME|HACK' --vimgrep")

def main():
    report = {
        "ecosystem": detect_ecosystem(),
        "git": get_git_info(),
        "docs": find_docs(),
        "todos": find_todos(),
        "structure": run_command("fd --max-depth 2")
    }
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
