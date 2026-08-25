#!/usr/bin/env python3
"""Discover and materialize reusable Tau DAG primitives."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]
REGISTRY_PATH = SKILL_DIR / "registry.json"
PHART_RUN = REPO_ROOT / "skills" / "phart-dag-chart" / "run.sh"


class UsageError(Exception):
    pass


def load_registry() -> dict[str, Any]:
    with REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        registry = json.load(fh)
    if registry.get("schema") != "dag_template_registry.v1":
        raise UsageError("registry schema must be dag_template_registry.v1")
    return registry


def templates() -> list[dict[str, Any]]:
    return list(load_registry().get("templates") or [])


def template_by_id(template_id: str) -> dict[str, Any]:
    for template in templates():
        if template.get("id") == template_id:
            return template
    raise UsageError(f"unknown template id: {template_id}")


def load_template_doc(entry: dict[str, Any]) -> dict[str, Any]:
    path = SKILL_DIR / str(entry["path"])
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def slot_map(entry: dict[str, Any]) -> dict[str, str]:
    return {str(slot["name"]): str(slot["json_pointer"]) for slot in entry.get("customization_slots") or []}


def pointer_set(doc: dict[str, Any], pointer: str, value: Any) -> None:
    if not pointer.startswith("/"):
        raise UsageError(f"invalid json pointer: {pointer}")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.strip("/").split("/")]
    target: Any = doc
    for part in parts[:-1]:
        if not isinstance(target, dict) or part not in target:
            raise UsageError(f"json pointer does not exist: {pointer}")
        target = target[part]
    if not isinstance(target, dict):
        raise UsageError(f"json pointer parent is not an object: {pointer}")
    target[parts[-1]] = value


def parse_set_values(values: list[str], entry: dict[str, Any]) -> dict[str, str]:
    allowed = slot_map(entry)
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise UsageError(f"--set values must be key=value, got: {item}")
        key, value = item.split("=", 1)
        if key not in allowed:
            valid = ", ".join(sorted(allowed))
            raise UsageError(f"unknown slot '{key}' for {entry['id']}; valid slots: {valid}")
        parsed[key] = value
    return parsed


def score_template(entry: dict[str, Any], query: str) -> int:
    terms = [term.lower() for term in query.split() if term.strip()]
    haystack = " ".join(
        [
            str(entry.get("id", "")),
            str(entry.get("title", "")),
            str(entry.get("summary", "")),
            " ".join(entry.get("tags") or []),
            " ".join(entry.get("use_when") or []),
        ]
    ).lower()
    return sum(1 for term in terms if term in haystack)


def public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "version": entry.get("version"),
        "title": entry.get("title"),
        "schema": entry.get("schema"),
        "owner_skill": entry.get("owner_skill"),
        "path": entry.get("path"),
        "summary": entry.get("summary"),
        "tags": entry.get("tags") or [],
        "slots": [slot.get("name") for slot in entry.get("customization_slots") or []],
    }


def emit_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def cmd_list(args: argparse.Namespace) -> int:
    entries = [public_entry(entry) for entry in templates()]
    if args.json:
        emit_json({"schema": "dag_template_list.v1", "templates": entries})
    else:
        for entry in entries:
            print(f"{entry['id']} v{entry['version']} [{', '.join(entry['tags'])}]")
            print(f"  {entry['summary']}")
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    matches = []
    for entry in templates():
        score = score_template(entry, args.query)
        if score > 0:
            row = public_entry(entry)
            row["score"] = score
            matches.append(row)
    matches.sort(key=lambda item: (-int(item["score"]), str(item["id"])))
    if args.json:
        emit_json({"schema": "dag_template_search.v1", "query": args.query, "matches": matches})
    else:
        for entry in matches:
            print(f"{entry['id']} score={entry['score']} slots={', '.join(entry['slots'])}")
            print(f"  {entry['summary']}")
    return 0 if matches else 1


def cmd_show(args: argparse.Namespace) -> int:
    entry = template_by_id(args.template_id)
    if args.json:
        emit_json(entry)
    else:
        print(f"{entry['id']} v{entry['version']}: {entry['title']}")
        print(entry["summary"])
        print("slots:")
        for slot in entry.get("customization_slots") or []:
            required = "required" if slot.get("required") else "optional"
            print(f"  {slot['name']} ({required}) -> {slot['json_pointer']}")
    return 0


def validate_file(path: Path) -> None:
    result = subprocess.run([str(PHART_RUN), "validate", str(path), "--json"], cwd=SKILL_DIR, text=True, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        sys.stderr.write(result.stdout)
        raise UsageError(f"materialized DAG failed PHART validation: {path}")


def cmd_materialize(args: argparse.Namespace) -> int:
    entry = template_by_id(args.template_id)
    doc = deepcopy(load_template_doc(entry))
    sets = parse_set_values(args.set_values or [], entry)
    slots = slot_map(entry)
    for key, value in sets.items():
        pointer_set(doc, slots[key], value)
    doc.setdefault("_template", {})
    doc["_template"].update(
        {
            "source_id": entry["id"],
            "source_version": entry["version"],
            "customized": True,
            "customized_slots": sorted(sets),
        }
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    if not args.no_validate:
        validate_file(output)
    print(str(output))
    return 0


def cmd_chart(args: argparse.Namespace) -> int:
    result = subprocess.run([str(PHART_RUN), "chart", str(args.dag_file)], cwd=SKILL_DIR, text=True)
    return int(result.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dag-templates", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List registered DAG primitives.")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_find = sub.add_parser("find", help="Search DAG primitives by intent.")
    p_find.add_argument("query")
    p_find.add_argument("--json", action="store_true")
    p_find.set_defaults(func=cmd_find)

    p_show = sub.add_parser("show", help="Inspect one DAG primitive registry entry.")
    p_show.add_argument("template_id")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_materialize = sub.add_parser("materialize", help="Write a customized DAG from a primitive.")
    p_materialize.add_argument("template_id")
    p_materialize.add_argument("--set", dest="set_values", action="append", default=[], help="Slot assignment as key=value.")
    p_materialize.add_argument("--output", required=True, help="Output DAG JSON path.")
    p_materialize.add_argument("--no-validate", action="store_true", help="Skip PHART validation.")
    p_materialize.set_defaults(func=cmd_materialize)

    p_chart = sub.add_parser("chart", help="Render a materialized DAG through phart-dag-chart.")
    p_chart.add_argument("dag_file")
    p_chart.set_defaults(func=cmd_chart)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
