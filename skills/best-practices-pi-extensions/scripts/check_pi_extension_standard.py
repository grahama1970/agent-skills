#!/usr/bin/env python3
"""Validate the Pi extension best-practices skill contract.

This is intentionally documentation-aware: the skill is a standard, so the
runtime proof is that the standard names the concrete Pi APIs, Nico Bailon
extension patterns, Brave-search evidence, and executable eval posture that a
future agent must follow.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

FRONTMATTER_RE = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---(?:\n|$)", re.DOTALL)

REQUIRED_CANONICAL_TERMS = {
    "Pi docs": ["docs/extensions.md", "examples/extensions"],
    "Brave-search evidence": ["Brave", "pi.dev/docs/latest/extensions", "github.com/nicobailon"],
    "Nico package metadata": ["package.json", "pi.extensions", "pi.skills", "peerDependencies"],
    "Nico extension examples": ["pi-interactive-shell", "pi-intercom", "pi-mcp-adapter"],
    "tool schema pattern": ["defineTool", "Type.Object"],
    "lifecycle pattern": ["session_start", "session_shutdown", "dispose"],
    "UI mode pattern": ["ctx.hasUI", "ctx.ui.notify", "ctx.ui.custom", "ctx.ui.setWidget"],
    "message forcing pattern": ["triggerTurn", "deliverAs", "followUp", "pi.sendUserMessage"],
    "guard pattern": ["message_end", "tool_call", "tool_result", "input"],
    "output guard pattern": ["guardMcpOutput", "mcp-output-guard", "spill"],
    "proof boundary pattern": ["goal-drift", "immutable", "proof boundary"],
    "eval posture": ["agentic-evals", "fixtures/agentic_eval.json", "negative", "adversarial"],
}

NICO_ROOTS = [
    Path("/home/graham/.pi/agent/git/github.com/nicobailon/pi-interactive-shell"),
    Path("/home/graham/.pi/agent/git/github.com/nicobailon/pi-intercom"),
    Path("/home/graham/.pi/agent/git/github.com/nicobailon/pi-mcp-adapter"),
]

NICO_MARKERS = {
    "pi-interactive-shell/index.ts": ["ctx.ui.custom", "session_start", "session_shutdown", "triggerTurn"],
    "pi-intercom/index.ts": ["defineTool", "Type.Object", "ctx.ui.custom", "session_shutdown"],
    "pi-mcp-adapter/index.ts": ["registerTool", "Type.Object", "MCP_RUNTIME", "session_shutdown"],
    "pi-mcp-adapter/mcp-output-guard.ts": ["guardMcpOutput", "outputGuard", "spill"],
}


def load_frontmatter(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{skill_md} has no YAML frontmatter")
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(match.group("frontmatter")) or {}
    except Exception:
        parsed = {}
        current_key: str | None = None
        for raw in match.group("frontmatter").splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if line.startswith("  - ") and current_key:
                parsed.setdefault(current_key, []).append(line[4:].strip())
            elif ":" in line:
                key, value = line.split(":", 1)
                current_key = key.strip()
                parsed[current_key] = value.strip() or []
    if not isinstance(parsed, dict):
        raise ValueError(f"{skill_md} frontmatter is not a map")
    return parsed


def read_bundle(skill_dir: Path) -> str:
    parts = []
    for name in ("SKILL.md", "README.md", "PROJECT_KNOWLEDGE.md"):
        path = skill_dir / name
        if not path.exists():
            raise FileNotFoundError(f"missing {path}")
        parts.append(f"\n<!-- {name} -->\n" + path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def validate_canonical(skill_dir: Path, check_nico: bool) -> list[str]:
    failures: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    fm = load_frontmatter(skill_md)
    bundle = read_bundle(skill_dir)

    require(fm.get("name") == "best-practices-pi-extensions", failures, "frontmatter name must be best-practices-pi-extensions")
    composes = fm.get("composes") or []
    complies = fm.get("complies") or []
    provides = fm.get("provides") or []
    require("agentic-evals" in composes, failures, "canonical skill must compose agentic-evals")
    require("typescript-code" in complies, failures, "canonical skill must comply with typescript-code")
    require("best-practices-security" in complies, failures, "canonical skill must comply with best-practices-security")
    require("extension-validation" in provides, failures, "canonical skill must provide extension-validation")

    for label, terms in REQUIRED_CANONICAL_TERMS.items():
        missing = [term for term in terms if term not in bundle]
        if missing:
            failures.append(f"{label} missing required term(s): {', '.join(missing)}")

    fixture = skill_dir / "fixtures" / "agentic_eval.json"
    require(fixture.exists(), failures, "canonical skill must ship fixtures/agentic_eval.json")
    if fixture.exists():
        try:
            data = json.loads(fixture.read_text(encoding="utf-8"))
            require(data.get("version") == 2, failures, "agentic fixture version must be 2")
            require(data.get("skill") == "best-practices-pi-extensions", failures, "agentic fixture skill name mismatch")
            require(int(data.get("trials", 0)) >= 2, failures, "agentic fixture must run at least two trials")
            cases = data.get("cases") or []
            require(any(c.get("type") in {"negative", "adversarial"} for c in cases), failures, "agentic fixture must include a negative/adversarial case")
            require(any(c.get("real_world") for c in cases), failures, "agentic fixture must include a real_world case")
            require(bool(data.get("capability_claims")), failures, "agentic fixture must declare capability_claims")
            require(bool(data.get("seams")), failures, "agentic fixture must declare seams")
        except Exception as exc:  # pragma: no cover - exercised by CLI fixture
            failures.append(f"agentic fixture is not valid JSON/contract: {exc}")

    if check_nico:
        for root in NICO_ROOTS:
            require(root.exists(), failures, f"Nico reference root missing: {root}")
            package_json = root / "package.json"
            if package_json.exists():
                try:
                    pkg = json.loads(package_json.read_text(encoding="utf-8"))
                    pi_meta = pkg.get("pi") or {}
                    require(bool(pi_meta.get("extensions")), failures, f"{package_json} must declare pi.extensions")
                    require("test" in (pkg.get("scripts") or {}), failures, f"{package_json} must declare a test script")
                except Exception as exc:
                    failures.append(f"{package_json} is not readable JSON: {exc}")
        base = Path("/home/graham/.pi/agent/git/github.com/nicobailon")
        for relative, markers in NICO_MARKERS.items():
            path = base / relative
            require(path.exists(), failures, f"Nico marker file missing: {path}")
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                for marker in markers:
                    require(marker in text, failures, f"{path} missing marker {marker}")

    return failures


def validate_alias(alias_dir: Path) -> list[str]:
    failures: list[str] = []
    fm = load_frontmatter(alias_dir / "SKILL.md")
    bundle = read_bundle(alias_dir)
    require(fm.get("name") == "best-practices-pi-extension", failures, "alias name must be best-practices-pi-extension")
    composes = fm.get("composes") or []
    require("best-practices-pi-extensions" in composes, failures, "alias must compose canonical plural skill")
    require("agentic-evals" in composes, failures, "alias must compose agentic-evals")
    for term in ("best-practices-pi-extenstion", "canonical", "best-practices-pi-extensions", "typo"):
        require(term in bundle, failures, f"alias missing required term: {term}")
    fixture = alias_dir / "fixtures" / "agentic_eval.json"
    require(fixture.exists(), failures, "alias must ship fixtures/agentic_eval.json")
    if fixture.exists():
        try:
            data = json.loads(fixture.read_text(encoding="utf-8"))
            require(data.get("skill") == "best-practices-pi-extension", failures, "alias fixture skill name mismatch")
            require(int(data.get("trials", 0)) >= 2, failures, "alias fixture must run at least two trials")
            cases = data.get("cases") or []
            require(any(c.get("type") in {"negative", "adversarial"} for c in cases), failures, "alias fixture must include a negative/adversarial case")
            require(any(c.get("real_world") for c in cases), failures, "alias fixture must include a real_world case")
        except Exception as exc:
            failures.append(f"alias fixture is not valid JSON/contract: {exc}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--alias-dir", type=Path)
    parser.add_argument("--skip-nico", action="store_true", help="Skip installed Nico repo readback; used only for isolated negative controls.")
    args = parser.parse_args()

    failures = validate_canonical(args.skill_dir.resolve(), check_nico=not args.skip_nico)
    if args.alias_dir:
        failures.extend(validate_alias(args.alias_dir.resolve()))

    if failures:
        print("PI_EXTENSION_STANDARD_FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PI_EXTENSION_STANDARD_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
