#!/usr/bin/env python3
"""Verify the delivery-proof contract is intact and its cross-skill anchors hold.

This is the skill's executable gate. It proves three things:

1. The SKILL.md frontmatter is valid and complete (yaml-parsed, not regexed).
2. All seven rules and their load-bearing strings are present, so an edit
   cannot silently drop one.
3. The cross-skill facts the rules cite still exist where the rules say they
   do: the ask contract's read-whole-file instruction, and the surf ChatGPT
   client actually emitting the acceptance signature Rule 1 tells agents to
   trust (`stopVisible`). A guidance skill whose anchors drift becomes
   confidently wrong, which is worse than absent.

`--mutate-drop-rule N` runs the same checks against an in-memory copy with rule
N removed, and must FAIL — the adversarial eval case uses it to prove the gate
fails closed rather than pattern-matching on green output.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import typer
import yaml

app = typer.Typer(add_completion=False)

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_DIR.parent

REQUIRED_FRONTMATTER = ("name", "description", "triggers", "provides", "composes", "complies")
RULE_HEADINGS = [f"## Rule {n} " for n in range(1, 8)]
LOAD_BEARING = [
    "DESTINATION",
    "stopVisible=true composerChars=0",
    "read this whole file before acting",
    "NEEDS_ATTENTION",
    "pkill -f",
    "reuse-bound",
]
# (anchor file relative to skills root, pattern, why it must hold)
CROSS_SKILL_ANCHORS = [
    ("ask/SKILL.md", r"read this whole\s*file before acting",
     "Rule 2 quotes the ask contract's Stop First instruction"),
    ("surf/vendor/surf-cli/native/chatgpt-client.cjs", r"stopVisible",
     "Rule 1 tells agents to trust the acceptance signature surf logs; the emitter must exist"),
]


def check(text: str) -> list[str]:
    problems: list[str] = []
    if not text.startswith("---\n"):
        return ["SKILL.md does not start with YAML frontmatter"]
    front = yaml.safe_load(text.split("---\n", 2)[1])
    for key in REQUIRED_FRONTMATTER:
        if not front.get(key):
            problems.append(f"frontmatter missing {key}")
    if front.get("name") != SKILL_DIR.name:
        problems.append(f"frontmatter name {front.get('name')!r} != directory {SKILL_DIR.name!r}")
    if "agentic-evals" not in (front.get("composes") or []):
        problems.append("composes must include agentic-evals")
    body = text.split("---\n", 2)[2]
    for heading in RULE_HEADINGS:
        if heading not in body:
            problems.append(f"missing rule heading {heading.strip()!r}")
    for needle in LOAD_BEARING:
        if needle not in body:
            problems.append(f"missing load-bearing string {needle!r}")
    for rel, pattern, why in CROSS_SKILL_ANCHORS:
        anchor = SKILLS_ROOT / rel
        if not anchor.exists():
            problems.append(f"anchor file missing: {rel} ({why})")
        elif not re.search(pattern, anchor.read_text(errors="replace")):
            problems.append(f"anchor drifted: {rel} no longer matches {pattern!r} ({why})")
    return problems


@app.command()
def main(mutate_drop_rule: int = typer.Option(0, help="Self-test: drop rule N and expect failure.")) -> None:
    text = (SKILL_DIR / "SKILL.md").read_text()
    if mutate_drop_rule:
        start = text.find(f"## Rule {mutate_drop_rule} ")
        end = text.find(f"## Rule {mutate_drop_rule + 1} ")
        if start == -1:
            typer.echo(f"cannot mutate: rule {mutate_drop_rule} not found", err=True)
            raise typer.Exit(2)
        text = text[:start] + (text[end:] if end != -1 else "")
    problems = check(text)
    if problems:
        for p in problems:
            typer.echo(f"FAIL: {p}", err=True)
        raise typer.Exit(1)
    typer.echo("PASS: frontmatter, all seven rules, load-bearing strings, and cross-skill anchors intact")


if __name__ == "__main__":
    app()
