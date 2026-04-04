"""v3 Structured Edit Operations for code-runner.

Replaces free-form diff/complete-file output with typed JSON operations:
create_file, replace_file, edit_lines, insert_lines, delete_lines.

No diff parsing. No format guessing. Schema-validated JSON in, files out.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from loguru import logger

VALID_OPS = {"create_file", "replace_file", "edit_lines", "insert_lines", "delete_lines"}


def parse_edit_ops(response: str) -> dict | None:
    """Parse v3 structured edit ops from LLM response. Returns parsed JSON or None.

    Tries direct JSON parse, then extracts JSON from markdown fences.
    """
    text = response.strip()

    # Strip markdown JSON fences if present
    fence_match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        obj_match = re.search(r'(\{.*\})', text, re.DOTALL)
        if obj_match:
            try:
                data = json.loads(obj_match.group(1))
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not isinstance(data, dict) or "operations" not in data:
        return None

    ops = data.get("operations", [])
    if not isinstance(ops, list):
        return None

    for op in ops:
        if not isinstance(op, dict):
            return None
        if op.get("op") not in VALID_OPS:
            logger.warning("  v3: Unknown op type: {}", op.get("op"))
            return None
        if "file" not in op:
            return None

    return data


def apply_edit_ops(
    ops_data: dict, cwd: str,
    path_authorizer=None,
) -> list[str]:
    """Apply v3 structured edit operations to disk. Returns list of files changed.

    path_authorizer: callable(rel_path, cwd, allowlist) -> corrected_path | None
    If not provided, all paths under cwd are allowed.
    """
    ops = ops_data.get("operations", [])
    if not ops:
        return []

    cwd_path = Path(cwd).resolve()
    written: list[str] = []

    # Group operations by file
    file_ops: dict[str, list[dict]] = {}
    for op in ops:
        raw_path = op["file"]
        if path_authorizer:
            corrected = path_authorizer(raw_path)
            if not corrected:
                logger.warning("  v3: {} not authorized, rejecting batch", raw_path)
                return []
            if corrected != raw_path.lstrip("/"):
                logger.info("  v3: Correcting path {} → {}", raw_path, corrected)
            file_path = corrected
        else:
            file_path = raw_path.lstrip("/")
        op["_resolved_file"] = file_path
        file_ops.setdefault(file_path, []).append(op)

    for file_path, ops_for_file in file_ops.items():
        target = (cwd_path / file_path).resolve()

        if target.exists():
            existing = target.read_text(errors="replace")
            existing_lines = existing.splitlines(keepends=True)
        else:
            existing = ""
            existing_lines = []

        new_content = None

        for op in ops_for_file:
            op_type = op["op"]

            if op_type == "create_file":
                if target.exists():
                    logger.warning("  v3: create_file on existing {} — treating as replace", file_path)
                new_content = op.get("content", "")

            elif op_type == "replace_file":
                content = op.get("content", "")
                if len(existing_lines) > 500:
                    new_lines = len(content.splitlines())
                    if new_lines < len(existing_lines) * 0.5:
                        logger.warning(
                            "  v3: REJECTED truncated replace_file: {} has {} lines, "
                            "replacement has {} ({:.0f}%)",
                            file_path, len(existing_lines), new_lines,
                            new_lines / len(existing_lines) * 100)
                        return []
                new_content = content

            elif op_type == "edit_lines":
                start = op.get("start_line", 1) - 1
                end = op.get("end_line", start + 1)
                content = op.get("content", "")
                if not existing_lines:
                    logger.warning("  v3: edit_lines on non-existent {}", file_path)
                    return []
                if start < 0 or end > len(existing_lines):
                    logger.warning("  v3: edit_lines range {}-{} out of bounds ({} lines)",
                                   start + 1, end, len(existing_lines))
                    return []
                replacement = content.splitlines(keepends=True)
                if replacement and not replacement[-1].endswith("\n"):
                    replacement[-1] += "\n"
                existing_lines[start:end] = replacement
                new_content = "".join(existing_lines)

            elif op_type == "insert_lines":
                after = op.get("after_line", 0)
                content = op.get("content", "")
                insert = content.splitlines(keepends=True)
                if insert and not insert[-1].endswith("\n"):
                    insert[-1] += "\n"
                existing_lines[after:after] = insert
                new_content = "".join(existing_lines)

            elif op_type == "delete_lines":
                start = op.get("start_line", 1) - 1
                end = op.get("end_line", start + 1)
                if start < 0 or end > len(existing_lines):
                    logger.warning("  v3: delete_lines range out of bounds for {}", file_path)
                    return []
                del existing_lines[start:end]
                new_content = "".join(existing_lines)

        if new_content is None:
            continue

        # Pre-write lint gate for Python
        if file_path.endswith(".py"):
            try:
                compile(new_content, file_path, "exec")
            except SyntaxError as e:
                logger.warning("  v3: Pre-write lint REJECTED {}: {}", file_path, e)
                return []

        # Write atomically
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            os.write(fd, new_content.encode())
            os.close(fd)
            Path(tmp).rename(target)
            written.append(file_path)
            logger.info("  v3: Wrote {} ({} bytes, {} lines)",
                        file_path, len(new_content), len(new_content.splitlines()))
        except Exception as e:
            Path(tmp).unlink(missing_ok=True)
            logger.error("  v3: Write failed for {}: {}", file_path, e)
            return []

    return written
