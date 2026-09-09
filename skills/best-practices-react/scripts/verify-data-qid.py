#!/usr/bin/env python3
"""Validate source-level React data-qid instrumentation.

Inputs are React/JSX source roots or files. Outputs are a human-readable report
or a JSON receipt. Exit 1 means the verifier found source-level violations it
can prove: missing QIDs on interactive JSX, malformed literal QIDs, volatile
repeated-entity QIDs, or duplicate literal QIDs.

This verifier is intentionally not a live-DOM oracle. Conditional reachability
and live uniqueness belong to skills/test-interactions/run.sh discover.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SOURCE_SUFFIXES = {".jsx", ".tsx"}
INTERACTIVE_TAGS = {"button", "input", "select", "textarea", "summary"}
EVENT_ATTRS = {
    "onClick",
    "onChange",
    "onDoubleClick",
    "onInput",
    "onKeyDown",
    "onKeyUp",
    "onMouseDown",
    "onPointerDown",
    "onSubmit",
}
INTERACTIVE_ROLES = {
    "button",
    "checkbox",
    "combobox",
    "link",
    "menuitem",
    "radio",
    "switch",
    "tab",
    "textbox",
}
SEGMENT_RE = re.compile(r"^[a-z][a-z0-9-]*$")
ATTR_RE = re.compile(r"\b([A-Za-z_:][-A-Za-z0-9_:]*)\s*=\s*(\"[^\"]*\"|'[^']*'|\{(?:[^{}]|\{[^{}]*\})*\})", re.S)
VOLATILE_EXPR_RE = re.compile(
    r"\b(index|idx|i|pos|position|renderIndex|arrayIndex|timestamp)\b"
    r"|Date\.now\s*\("
    r"|new\s+Date\s*\("
    r"|Math\.random\s*\("
    r"|crypto\.randomUUID\s*\("
    r"|\b(randomUUID|uuidv4|nanoid)\s*\(",
    re.I,
)
STABLE_EXPR_RE = re.compile(
    r"(\.|\[['\"]?|\b)(id|uuid|slug|key|qid|testId|testID|sku|code|handle)(\b|['\"]?\])"
)


@dataclass(frozen=True)
class OpeningTag:
    tag: str
    attrs: str
    line: int


@dataclass(frozen=True)
class QidOccurrence:
    value: str
    file: str
    line: int
    tag: str


@dataclass(frozen=True)
class Violation:
    code: str
    file: str
    line: int
    message: str
    tag: str = ""
    qid: str = ""


def source_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            files.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.suffix in SOURCE_SUFFIXES and child.is_file():
                    if any(part in {"node_modules", "dist", "build", ".next"} for part in child.parts):
                        continue
                    files.append(child)
    return sorted(set(files))


def iter_opening_tags(text: str) -> list[OpeningTag]:
    tags: list[OpeningTag] = []
    i = 0
    while i < len(text):
        if text[i] != "<" or i + 1 >= len(text) or not (text[i + 1].isalpha() or text[i + 1] == "_"):
            i += 1
            continue
        line = text.count("\n", 0, i) + 1
        j = i + 1
        while j < len(text) and (text[j].isalnum() or text[j] in {"_", "-", ".", ":"}):
            j += 1
        tag = text[i + 1 : j]
        quote = ""
        brace_depth = 0
        k = j
        while k < len(text):
            char = text[k]
            if quote:
                if char == "\\":
                    k += 2
                    continue
                if char == quote:
                    quote = ""
            elif char in {"'", '"', "`"}:
                quote = char
            elif char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == ">" and brace_depth == 0:
                tags.append(OpeningTag(tag=tag, attrs=text[j:k], line=line))
                i = k + 1
                break
            k += 1
        else:
            i += 1
            continue
    return tags


def attrs_map(attrs: str) -> dict[str, str]:
    return {match.group(1): match.group(2).strip() for match in ATTR_RE.finditer(attrs)}


def has_bare_attr(attrs: str, name: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\b(?:\s|=|$)", attrs) is not None


def literal_attr(attrs: dict[str, str], name: str) -> str:
    value = attrs.get(name, "")
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    return ""


def is_interactive(tag: OpeningTag) -> bool:
    lower = tag.tag.lower()
    attrs = attrs_map(tag.attrs)
    if lower in INTERACTIVE_TAGS:
        return literal_attr(attrs, "type").lower() != "hidden"
    if lower == "a" and (has_bare_attr(tag.attrs, "href") or any(has_bare_attr(tag.attrs, attr) for attr in EVENT_ATTRS)):
        return True
    role = literal_attr(attrs, "role").lower()
    if role in INTERACTIVE_ROLES:
        return True
    if any(has_bare_attr(tag.attrs, attr) for attr in EVENT_ATTRS):
        return True
    return bool(attrs.get("data-qs-action"))


def qid_attr_value(attrs: str) -> str:
    return attrs_map(attrs).get("data-qid", "")


def validate_literal_qid(value: str, file: str, line: int, tag: str) -> list[Violation]:
    violations: list[Violation] = []
    if not value.strip():
        return [Violation("empty_qid", file, line, "data-qid must not be empty", tag=tag)]
    if any(token in value for token in ("nth-child", "#", ".", "[", "]", "/", " ")):
        violations.append(Violation("malformed_qid", file, line, "data-qid is an identifier, not a CSS selector", tag=tag, qid=value))
    segments = value.split(":")
    if len(segments) < 3 or any(not SEGMENT_RE.match(segment) for segment in segments):
        violations.append(Violation("malformed_qid", file, line, "data-qid must use lowercase colon-separated segments: component:element:qualifier", tag=tag, qid=value))
    return violations


def split_template(template: str) -> tuple[list[str], list[str]]:
    static_parts: list[str] = []
    exprs: list[str] = []
    chunk: list[str] = []
    i = 0
    while i < len(template):
        if template.startswith("${", i):
            static_parts.append("".join(chunk))
            chunk = []
            i += 2
            depth = 1
            expr: list[str] = []
            quote = ""
            while i < len(template) and depth:
                char = template[i]
                if quote:
                    if char == "\\":
                        expr.append(char)
                        if i + 1 < len(template):
                            expr.append(template[i + 1])
                        i += 2
                        continue
                    if char == quote:
                        quote = ""
                elif char in {"'", '"', "`"}:
                    quote = char
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                expr.append(char)
                i += 1
            exprs.append("".join(expr).strip())
            continue
        chunk.append(template[i])
        i += 1
    static_parts.append("".join(chunk))
    return static_parts, exprs


def validate_dynamic_qid(raw: str, file: str, line: int, tag: str) -> list[Violation]:
    expression = raw[1:-1].strip()
    violations: list[Violation] = []
    static_prefix = ""
    expressions: list[str] = []
    if len(expression) >= 2 and expression[0] == "`" and expression[-1] == "`":
        static_parts, expressions = split_template(expression[1:-1])
        static_prefix = static_parts[0]
    else:
        literal_match = re.match(r"(['\"])(.*?)\1\s*\+\s*(.+)$", expression, re.S)
        if literal_match:
            static_prefix = literal_match.group(2)
            expressions = [literal_match.group(3).strip()]
        else:
            return [Violation("dynamic_qid_unverifiable", file, line, "dynamic data-qid must expose a literal semantic prefix and stable identity expression", tag=tag)]

    prefix = static_prefix[:-1] if static_prefix.endswith(":") else static_prefix
    prefix_segments = [segment for segment in prefix.split(":") if segment]
    if len(prefix_segments) < 3 or any(not SEGMENT_RE.match(segment) for segment in prefix_segments):
        violations.append(Violation("malformed_qid", file, line, "dynamic data-qid prefix must start with component:element:qualifier", tag=tag, qid=static_prefix))
    for expr in expressions:
        if VOLATILE_EXPR_RE.search(expr):
            violations.append(Violation("volatile_qid_identity", file, line, "repeated-entity QID uses array position, render order, timestamp, or random identity", tag=tag, qid=expr))
        elif not STABLE_EXPR_RE.search(expr):
            violations.append(Violation("dynamic_qid_unverifiable", file, line, "repeated-entity QID expression does not expose a stable domain/test identity", tag=tag, qid=expr))
    return violations


def validate_qid(raw: str, file: str, line: int, tag: str) -> tuple[str, list[Violation]]:
    if len(raw) >= 2 and raw[0] in {"'", '"'} and raw[-1] == raw[0]:
        value = raw[1:-1]
        return value, validate_literal_qid(value, file, line, tag)
    if len(raw) >= 2 and raw[0] == "{" and raw[-1] == "}":
        return raw, validate_dynamic_qid(raw, file, line, tag)
    return raw, [Violation("malformed_qid", file, line, "data-qid must be a string literal or a template with stable identity", tag=tag, qid=raw)]


def scan(paths: list[Path]) -> dict:
    files = source_files(paths)
    violations: list[Violation] = []
    occurrences: list[QidOccurrence] = []
    interactive_count = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path)
        for tag in iter_opening_tags(text):
            if not is_interactive(tag):
                continue
            interactive_count += 1
            raw_qid = qid_attr_value(tag.attrs)
            if not raw_qid:
                violations.append(Violation("missing_qid", rel, tag.line, "interactive JSX control is missing data-qid", tag=tag.tag))
                continue
            qid_value, qid_violations = validate_qid(raw_qid, rel, tag.line, tag.tag)
            violations.extend(qid_violations)
            if qid_value and not qid_value.startswith("{"):
                occurrences.append(QidOccurrence(value=qid_value, file=rel, line=tag.line, tag=tag.tag))

    by_value: dict[str, list[QidOccurrence]] = {}
    for item in occurrences:
        by_value.setdefault(item.value, []).append(item)
    for qid, rows in sorted(by_value.items()):
        if len(rows) <= 1:
            continue
        first = rows[0]
        lines = ", ".join(f"{Path(row.file).name}:{row.line}" for row in rows)
        violations.append(Violation("duplicate_literal_qid", first.file, first.line, f"literal data-qid appears more than once in source: {lines}", tag=first.tag, qid=qid))

    return {
        "schema": "best_practices_react.data_qid_report.v1",
        "status": "PASS_DATA_QID" if not violations else "FAIL_DATA_QID",
        "proof_boundary": {
            "source_static": True,
            "live_dom_uniqueness": False,
            "live_dom_reachability": False,
            "live_dom_owner": "skills/test-interactions/run.sh discover",
        },
        "files_scanned": len(files),
        "interactive_controls_scanned": interactive_count,
        "violations": [asdict(item) for item in violations],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="React source files or roots to scan")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    parser.add_argument("--output", type=Path, help="write the JSON report to this path")
    args = parser.parse_args()

    report = scan(args.paths)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['status']}  {report['files_scanned']} files  {report['interactive_controls_scanned']} interactive controls")
        for violation in report["violations"]:
            print(f"  FAIL {violation['code']} {violation['file']}:{violation['line']} {violation['message']}")
    return 0 if report["status"] == "PASS_DATA_QID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
