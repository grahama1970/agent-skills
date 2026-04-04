#!/usr/bin/env python3
"""Patch Python entry-point files to add load_dotenv(find_dotenv(usecwd=True), override=False)."""

import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

TARGETS = [
    ("ask", "ask.py"),
    ("common", "memory_client.py"),
    ("common", "discord_notify.py"),
    ("interview", "interview.py"),
    ("monitor-personas", "monitor_core.py"),
    ("security-scan", "security_scan.py"),
    ("create-story", "story_models.py"),
    ("voice-lab", "voice_lab.py"),
    ("embedding", "embed.py"),
    ("consume-movie", "jellyfin_client.py"),
    ("ops-discord", "discord_ops.py"),
    ("surf", "cdp_client.py"),
    ("surf-qml", "surf_qml.py"),
    ("battle", "orchestrator.py"),
    ("create-code", "orchestrator.py"),
    ("create-icon", "creator.py"),
    ("create-ksml", "adapter.py"),
    ("create-walkthrough", "walkthrough.py"),
    ("debug-pdf", "dp_config.py"),
    ("batch-quality", "cli.py"),
    ("ingest-audiobook", "watchdog.py"),
    ("ingest-book", "readarr_ops.py"),
    ("ingest-movie", "config.py"),
    ("ops-sam-gov", "sam_gov_ops.py"),
    ("formalize-request", "formalize.py"),
]

DOTENV_IMPORT = "from dotenv import load_dotenv, find_dotenv"
DOTENV_CALL = "load_dotenv(find_dotenv(usecwd=True), override=False)"

patched = []
skipped_no_env = []
skipped_already = []
errors = []


def has_env_usage(content: str) -> bool:
    return bool(re.search(r"os\.environ|os\.getenv", content))


def has_load_dotenv(content: str) -> bool:
    return "load_dotenv" in content


def find_insertion_point(lines: list) -> int:
    """Find the line index after the last top-level import statement."""
    last_import_end = -1
    in_multiline = False
    in_docstring = False
    docstring_quote = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track docstrings
        if in_docstring:
            if docstring_quote in stripped:
                in_docstring = False
                last_import_end = max(last_import_end, i)
            continue

        # Detect start of module docstring (only before any imports)
        if last_import_end == -1 and not in_multiline:
            for q in ('"""', "'''"):
                if stripped.startswith(q):
                    if stripped.count(q) >= 2:
                        # single-line docstring
                        last_import_end = i
                        break
                    else:
                        in_docstring = True
                        docstring_quote = q
                        break
            if in_docstring:
                continue

        # Track multi-line imports
        if in_multiline:
            last_import_end = i
            if ")" in stripped:
                in_multiline = False
            continue

        # Detect import lines
        if stripped.startswith("import ") or stripped.startswith("from "):
            last_import_end = i
            if "(" in stripped and ")" not in stripped:
                in_multiline = True
            continue

        # Skip blank lines and comments within the import block area
        if stripped == "" or stripped.startswith("#"):
            continue

        # Non-import line: if we've seen imports, stop here
        if last_import_end >= 0:
            break

    return last_import_end + 1


def patch_file(filepath: Path) -> bool:
    content = filepath.read_text()

    if has_load_dotenv(content):
        skipped_already.append(str(filepath.relative_to(BASE)))
        return False

    if not has_env_usage(content):
        skipped_no_env.append(str(filepath.relative_to(BASE)))
        return False

    lines = content.split("\n")
    insert_at = find_insertion_point(lines)

    # Build insertion: blank line, import, call, blank line
    new_lines = []

    # Add blank separator before if previous line is not blank
    if insert_at > 0 and lines[insert_at - 1].strip() != "":
        new_lines.append("")

    new_lines.append(DOTENV_IMPORT)
    new_lines.append(DOTENV_CALL)

    # Add blank separator after if next line is not blank
    if insert_at < len(lines) and lines[insert_at].strip() != "":
        new_lines.append("")

    lines[insert_at:insert_at] = new_lines
    filepath.write_text("\n".join(lines))
    return True


def verify_syntax(filepath: Path) -> bool:
    result = subprocess.run(
        [sys.executable, "-c",
         f"import py_compile; py_compile.compile('{filepath}', doraise=True)"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"    SYNTAX ERROR: {result.stderr.strip()}")
    return result.returncode == 0


def main():
    print(f"Patching {len(TARGETS)} target files...\n")

    for skill, filename in TARGETS:
        filepath = BASE / skill / filename
        if not filepath.exists():
            errors.append(f"NOT FOUND: {filepath}")
            continue

        if patch_file(filepath):
            if verify_syntax(filepath):
                patched.append(f"{skill}/{filename}")
                print(f"  PATCHED: {skill}/{filename}")
            else:
                errors.append(f"SYNTAX ERROR: {skill}/{filename}")
                print(f"  ERROR:   {skill}/{filename} -- syntax error!")

    print(f"\n{'='*60}")
    print(f"PATCHED:           {len(patched)}")
    print(f"SKIPPED (already): {len(skipped_already)}")
    print(f"SKIPPED (no env):  {len(skipped_no_env)}")
    print(f"ERRORS:            {len(errors)}")
    print(f"{'='*60}")

    if skipped_already:
        print("\nAlready had load_dotenv:")
        for s in skipped_already:
            print(f"  {s}")

    if skipped_no_env:
        print("\nNo os.environ/os.getenv usage:")
        for s in skipped_no_env:
            print(f"  {s}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e}")

    if patched:
        print("\nPatched files:")
        for p in patched:
            print(f"  {p}")


if __name__ == "__main__":
    main()
