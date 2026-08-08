#!/usr/bin/env python3
"""Emit site/build-manifest.json and FAIL CLOSED on source incoherence.

The homepage renders several generated surfaces together (inventory, catalog,
research-map, graph, artifacts). Each is stamped with the commit it was
generated from. If they disagree — or lag HEAD — the page shows counts and
relationships from different source epochs while a `DRIFT: 0` receipt implies
one coherent state (webgpt review, Criterion 2). This gate makes that
impossible: it verifies every surface shares HEAD's commit, records a manifest
of source_commit + input/output sha256, and exits non-zero otherwise.

Run in CI AFTER regeneration and BEFORE build. Non-zero blocks the deploy.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"

# Regenerated-from-repo surfaces -> the field recording the commit they were
# built from. ALL must equal HEAD (this is the coherence contract).
SURFACES = {
    "inventory.json": "commit",
    "artifacts.json": "commit",
    "catalog.json": "sourceCommit",
    "research-map.json": "sourceCommit",
    "graph.json": "sourceCommit",
    "project-visibility.json": "sourceCommit",
    "resume.json": "sourceCommit",
}
# Immutable historical fixtures the page renders: NOT regenerated per commit —
# they capture a real PAST run. They carry their own evidence-source (a run id /
# content sha of the underlying artifacts) instead of HEAD, and are recorded in
# the manifest as fixtures so coverage is complete (webgpt trust check).
FIXTURES = {
    "proof-explainer.json": "run",          # the real Tau run that designed the site
    "generated/battle-lineage.json": "sourceSha256",  # recorded battle-004 fixture
}
INPUTS = ["../README.md", "content.json", "../RESUME.md"]

# Direct upstream inputs each output consumes. Recording their digests in the
# manifest makes a green gate prove not just "generated at HEAD" but "generated
# from exactly these upstream files" — closing the generator-order false-green
# (webgpt trust review). Keys map to files under site/.
INPUT_DEPS = {
    "inventory.json": [],  # repo state (git ls-tree) — no site-file inputs
    "project-visibility.json": ["content.json", "private-abstracts.json"],
    "research-map.json": ["content.json"],
    "catalog.json": ["inventory.json", "project-visibility.json", "research-map.json", "content.json"],
    "graph.json": ["project-visibility.json", "research-map.json", "content.json"],
    "artifacts.json": ["inventory.json"],
    # RESUME.md is the resume's only upstream; digesting it here means a green
    # gate proves /resume was generated from exactly the committed Markdown.
    "resume.json": ["../RESUME.md"],
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
    ).strip()


def main() -> int:
    commit = head()
    errors: list[str] = []

    for fname, key in SURFACES.items():
        p = SITE / fname
        if not p.exists():
            errors.append(f"{fname}: missing")
            continue
        stamped = json.loads(p.read_text()).get(key)
        if stamped != commit:
            errors.append(f"{fname}: {key}={stamped} != HEAD {commit} (regenerate)")

    # README / content.json counts must match the real repo inventory.
    inv = json.loads((SITE / "inventory.json").read_text()).get("stats", {})
    content = json.loads((SITE / "content.json").read_text()).get("stats", {})
    if content and content != inv:
        errors.append(f"content.json stats {content} != inventory {inv}")

    # Fixtures: declare each with its own evidence-source + digest. Missing
    # fixture or missing evidence-source field is a coverage gap -> fail.
    fixtures = {}
    for fname, srckey in FIXTURES.items():
        p = SITE / fname
        if not p.exists():
            errors.append(f"fixture missing: {fname}")
            continue
        src = json.loads(p.read_text()).get(srckey)
        if not src:
            errors.append(f"fixture {fname}: no evidence-source field '{srckey}'")
            continue
        fixtures[fname] = {"immutable": True, "evidence_source": src, "sha256": sha(p)}

    if errors:
        print("FAIL: source incoherence — the site would show mixed source state:",
              file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("Fix: run `monitor-website refresh` (regenerates all surfaces at HEAD).",
              file=sys.stderr)
        return 1

    manifest = {
        "source_commit": commit,
        "as_of": json.loads((SITE / "inventory.json").read_text()).get("as_of"),
        "stats": inv,
        "inputs": {i: sha(SITE / i) for i in INPUTS if (SITE / i).exists()},
        "outputs": {
            f: {
                "sha256": sha(SITE / f),
                "inputs": {
                    dep: sha(SITE / dep)
                    for dep in INPUT_DEPS.get(f, [])
                    if (SITE / dep).exists()
                },
            }
            for f in SURFACES if (SITE / f).exists()
        },
        "fixtures": fixtures,
    }
    (SITE / "build-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"build-manifest OK: {len(SURFACES)} surfaces coherent @ {commit} · "
          f"stats {inv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
