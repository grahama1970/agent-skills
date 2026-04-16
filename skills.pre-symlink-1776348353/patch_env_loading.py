#!/usr/bin/env python3
"""
Patch all run.sh scripts to add .env loading.

Patterns handled:
1. Has SCRIPT_DIR and PROJECT_ROOT -> insert .env block after PROJECT_ROOT
2. Has SCRIPT_DIR but no PROJECT_ROOT -> insert PROJECT_ROOT calc + .env block after SCRIPT_DIR
3. Has neither -> insert SCRIPT_DIR + PROJECT_ROOT + .env block after set -e (or after shebang)
"""

import os
import re
import subprocess
import sys
from pathlib import Path

SKILLS_DIR = str(Path(__file__).resolve().parent)

ENV_BLOCK_LINES = [
    "",
    "# Load .env if present",
    'if [ -f "$PROJECT_ROOT/.env" ]; then',
    "    export $(grep -v '^#' \"$PROJECT_ROOT/.env\" | xargs)",
    "fi",
]

PROJECT_ROOT_CALC = 'PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"'

# Common SCRIPT_DIR patterns
SCRIPT_DIR_PATTERNS = [
    r'^SCRIPT_DIR=',
    r'^export SCRIPT_DIR=',
]

PROJECT_ROOT_PATTERNS = [
    r'^PROJECT_ROOT=',
    r'^export PROJECT_ROOT=',
]

SET_E_PATTERNS = [
    r'^set -e\b',
    r'^set -euo pipefail',
    r'^set -eu\b',
]


def find_line_index(lines, patterns):
    """Find the last line matching any of the patterns."""
    last_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        for pat in patterns:
            if re.match(pat, stripped):
                last_idx = i
    return last_idx


def has_pattern(lines, patterns):
    return find_line_index(lines, patterns) >= 0


def patch_file(filepath):
    """Patch a single run.sh file. Returns (success, message)."""
    with open(filepath, 'r') as f:
        content = f.read()

    # Skip if already has .env loading
    if '.env' in content:
        return True, "SKIPPED (already has .env)"

    lines = content.split('\n')

    has_script_dir = has_pattern(lines, SCRIPT_DIR_PATTERNS)
    has_project_root = has_pattern(lines, PROJECT_ROOT_PATTERNS)
    has_set_e = has_pattern(lines, SET_E_PATTERNS)

    if has_script_dir and has_project_root:
        # Case 1: Both exist, insert after PROJECT_ROOT line
        idx = find_line_index(lines, PROJECT_ROOT_PATTERNS)
        insert_lines = ENV_BLOCK_LINES[:]
    elif has_script_dir and not has_project_root:
        # Case 2: Has SCRIPT_DIR but no PROJECT_ROOT
        idx = find_line_index(lines, SCRIPT_DIR_PATTERNS)
        # Check if the next few lines also define related vars (SKILLS_DIR, etc.) and skip past them
        for j in range(idx + 1, min(idx + 5, len(lines))):
            stripped = lines[j].strip()
            if stripped.startswith('SKILLS_DIR=') or stripped.startswith('export SKILLS_DIR='):
                idx = j
            elif stripped == '' or stripped.startswith('#'):
                continue
            else:
                break
        insert_lines = ["", PROJECT_ROOT_CALC] + ENV_BLOCK_LINES[:]
    else:
        # Case 3: No SCRIPT_DIR - add everything
        if has_set_e:
            idx = find_line_index(lines, SET_E_PATTERNS)
        else:
            # After shebang line
            idx = 0
            # Skip past any comment block at the top
            for j in range(1, len(lines)):
                stripped = lines[j].strip()
                if stripped.startswith('#') or stripped == '':
                    idx = j
                else:
                    break

        script_dir_line = 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"'
        insert_lines = ["", script_dir_line, PROJECT_ROOT_CALC] + ENV_BLOCK_LINES[:]

    # Insert the block after the identified line
    new_lines = lines[:idx + 1] + insert_lines + lines[idx + 1:]

    # Clean up any triple+ blank lines
    cleaned = []
    blank_count = 0
    for line in new_lines:
        if line.strip() == '':
            blank_count += 1
            if blank_count <= 2:
                cleaned.append(line)
        else:
            blank_count = 0
            cleaned.append(line)

    new_content = '\n'.join(cleaned)

    # Write back
    with open(filepath, 'w') as f:
        f.write(new_content)

    # Verify with bash -n
    result = subprocess.run(['bash', '-n', filepath], capture_output=True, text=True,
    env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    if result.returncode != 0:
        # Restore original
        with open(filepath, 'w') as f:
            f.write(content)
        return False, f"FAILED bash -n: {result.stderr.strip()}"

    return True, "PATCHED"


def main():
    skills = sorted(os.listdir(SKILLS_DIR))
    patched = 0
    skipped = 0
    failed = 0
    no_runsh = 0
    failures = []

    for skill in skills:
        run_sh = os.path.join(SKILLS_DIR, skill, 'run.sh')
        if not os.path.isfile(run_sh):
            no_runsh += 1
            continue

        success, msg = patch_file(run_sh)
        skill_name = skill.ljust(30)
        if 'SKIPPED' in msg:
            skipped += 1
        elif 'PATCHED' in msg:
            patched += 1
            print(f"  OK  {skill_name} {msg}")
        else:
            failed += 1
            failures.append((skill, msg))
            print(f" FAIL {skill_name} {msg}")

    print(f"\n{'='*60}")
    print(f"Total skills:     {len(skills)}")
    print(f"  No run.sh:  {no_runsh}")
    print(f"  Patched:    {patched}")
    print(f"  Skipped:    {skipped} (already had .env)")
    print(f"  Failed:     {failed}")

    if failures:
        print(f"\nFailures:")
        for skill, msg in failures:
            print(f"  {skill}: {msg}")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
