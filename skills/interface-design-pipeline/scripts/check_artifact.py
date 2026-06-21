#!/usr/bin/env python3
"""Deterministic checks for interface-pipeline artifacts."""
from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class AuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attrs: list[tuple[str, dict[str, str]]] = []
        self.doctype = False

    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype html"):
            self.doctype = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = {key: value or "" for key, value in attrs}
        self.tags.append(tag.lower())
        self.attrs.append((tag.lower(), normalized))


def write_result(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "PASS" else 1


def check_mockup(args: argparse.Namespace) -> int:
    path = Path(args.path)
    findings: list[str] = []
    if not path.is_file():
        return write_result({"status": "BLOCKED", "findings": [f"missing mockup: {path}"]})
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    parser = AuditParser()
    try:
        parser.feed(text)
    except Exception as exc:  # noqa: BLE001
        findings.append(f"HTML parser failed: {exc}")

    required_tags = {"html", "head", "body", "style"}
    missing_tags = sorted(required_tags - set(parser.tags))
    if missing_tags:
        findings.append("missing required tags: " + ", ".join(missing_tags))
    if not parser.doctype:
        findings.append("missing <!doctype html>")
    if "name=\"viewport\"" not in lowered and "name='viewport'" not in lowered:
        findings.append("missing viewport meta tag")
    if ":focus" not in lowered and ":focus-visible" not in lowered:
        findings.append("missing visible keyboard focus CSS")
    if len(text) < 1800:
        findings.append("mockup is too small to demonstrate a real product surface")

    controls = [(tag, attrs) for tag, attrs in parser.attrs if tag in {"button", "input", "textarea", "select", "a"}]
    if not controls:
        findings.append("no interactive controls found")
    for tag, attrs in controls:
        if tag == "a" and not attrs.get("href"):
            findings.append("anchor without href")
        if tag in {"input", "textarea", "select"} and not any(
            attrs.get(key) for key in ("aria-label", "aria-labelledby", "title", "id")
        ):
            findings.append(f"{tag} lacks an accessible name hook")

    for required in args.required_text:
        if required.lower() not in lowered:
            findings.append(f"required state/text not represented: {required}")
    for forbidden in args.forbid:
        if re.search(rf"\b{re.escape(forbidden.lower())}\b", lowered):
            findings.append(f"forbidden UI term present: {forbidden}")

    remote_assets = re.findall(r"(?:src|href)=[\"']https?://", text, flags=re.IGNORECASE)
    if remote_assets and not args.allow_remote_assets:
        findings.append("remote script/style/image dependencies are not allowed in a self-contained mockup")

    return write_result(
        {
            "schema": "interface_design_pipeline.artifact_check.v1",
            "kind": "mockup",
            "path": str(path),
            "status": "PASS" if not findings else "NEEDS_CHANGES",
            "findings": findings,
            "metrics": {"characters": len(text), "controls": len(controls), "tags": len(parser.tags)},
        }
    )


def check_inventory(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        return write_result({"status": "BLOCKED", "findings": [f"missing inventory: {path}"]})
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return write_result({"status": "BLOCKED", "findings": [f"invalid inventory JSON: {exc}"]})
    findings: list[str] = []
    if not isinstance(value, dict):
        findings.append("inventory root must be an object")
        value = {}
    if value.get("status") != "PASS":
        findings.append("inventory status must be PASS")
    components = value.get("components")
    if not isinstance(components, list) or not components:
        findings.append("inventory must list at least one considered component")
    evidence = value.get("evidence_paths")
    if not isinstance(evidence, list) or not evidence:
        findings.append("inventory must include evidence_paths")
    return write_result(
        {
            "schema": "interface_design_pipeline.artifact_check.v1",
            "kind": "component_inventory",
            "path": str(path),
            "status": "PASS" if not findings else "NEEDS_CHANGES",
            "findings": findings,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate interface pipeline artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    mockup = subparsers.add_parser("mockup")
    mockup.add_argument("--path", required=True)
    mockup.add_argument("--required-text", action="append", default=[])
    mockup.add_argument("--forbid", action="append", default=[])
    mockup.add_argument("--allow-remote-assets", action="store_true")
    mockup.set_defaults(func=check_mockup)

    inventory = subparsers.add_parser("component-inventory")
    inventory.add_argument("--path", required=True)
    inventory.set_defaults(func=check_inventory)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
