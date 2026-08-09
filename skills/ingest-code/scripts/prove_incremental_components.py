#!/usr/bin/env python3
"""Prove ingest-code file-component reuse with real filesystem artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import ingest_code  # noqa: E402
from code_graph_artifact import write_code_graph_bundle  # noqa: E402
from incremental_state import FileComponentState, build_transform_fingerprints, source_fingerprint  # noqa: E402


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _setup_repo(root: Path) -> Path:
    repo = root / "fixture-repo"
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "alpha.py").write_text(
        "def alpha(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (repo / "pkg" / "beta.py").write_text(
        "from pkg.alpha import alpha\n\n"
        "def beta(value: int) -> int:\n    return alpha(value) * 2\n",
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "agent@example.invalid")
    _git(repo, "config", "user.name", "Agent")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _run_component_pass(repo: Path, state_path: Path, fingerprints: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    files = ingest_code.collect_files(repo, ["*.py"])
    branch = ingest_code._current_branch(repo)
    state = FileComponentState(state_path, repo=repo.name, branch=branch, transform_fingerprints=fingerprints)
    plan = state.plan(files, repo)
    records = [
        ingest_code._record_from_component_payload(payload)
        for payload in state.reused_symbols(plan.reused)
    ]
    for rel_path in plan.to_parse:
        records.extend(ingest_code._scan_treesitter_symbol_records_for_file(repo / rel_path, repo, "code"))
    records.sort(key=lambda item: (item.normalized_path, item.qualified_name, item.start_line))
    edges = ingest_code.extract_edges(files, repo)
    bundle = write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch=branch,
        commit=ingest_code._current_commit(repo),
        scan_roots=[repo],
        files=files,
        symbols=records,
        edges=edges,
    )
    receipt = {
        "schema": "ingest-code.incremental_receipt.v1",
        "mocked": False,
        "live": True,
        "component_plan": plan.summary(),
        "symbols_total": len(records),
        "bundle_path": bundle["path"],
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    state.commit(
        current_sources=plan.current_sources,
        symbols_by_path=ingest_code._symbols_by_path(records),
        bundle_digest=_sha256_file(Path(bundle["checksums"])),
        accepted_complete_bundle=bool(bundle["complete"]),
        receipt=receipt,
    )
    receipt["state_path"] = str(state_path)
    receipt["bundle_checksums_sha256"] = _sha256_file(Path(bundle["checksums"]))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/ingest-code-incremental-components-proof"))
    args = parser.parse_args()

    out = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    repo = _setup_repo(out)
    state_path = repo / "artifacts" / "ingest-code" / "incremental-components.json"
    fingerprints = build_transform_fingerprints(SKILL_ROOT, scope="code", patterns=["*.py"], scan_roots=["."])

    initial = _run_component_pass(repo, state_path, fingerprints)
    noop = _run_component_pass(repo, state_path, fingerprints)

    (repo / "pkg" / "alpha.py").write_text(
        "def alpha(value: int) -> int:\n    adjusted = value + 2\n    return adjusted\n",
        encoding="utf-8",
    )
    edit = _run_component_pass(repo, state_path, fingerprints)

    (repo / "pkg" / "beta.py").unlink()
    delete = _run_component_pass(repo, state_path, fingerprints)

    bumped_fingerprints = dict(fingerprints)
    bumped_fingerprints["typed_edge_resolver"] = "sha256:forced-change"
    bumped = _run_component_pass(repo, state_path, bumped_fingerprints)

    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    first_path = sorted(state_payload["components"])[0]
    state_payload["components"][first_path]["component_hash"] = "sha256:bad"
    state_path.write_text(json.dumps(state_payload, sort_keys=True), encoding="utf-8")
    corrupt_state = FileComponentState(state_path, repo=repo.name, branch=ingest_code._current_branch(repo), transform_fingerprints=bumped_fingerprints)
    corrupt_plan = corrupt_state.plan(ingest_code.collect_files(repo, ["*.py"]), repo)

    summary = {
        "schema": "ingest-code.incremental_components_proof.v1",
        "mocked": False,
        "live": True,
        "repo": str(repo),
        "state_path": str(state_path),
        "source_fingerprint_kind": source_fingerprint(repo / "pkg" / "alpha.py", repo).split(":", 1)[0],
        "runs": {
            "initial": initial,
            "noop": noop,
            "edit": edit,
            "delete": delete,
            "fingerprint_bump": bumped,
            "corrupt_cache_probe": corrupt_plan.summary(),
        },
        "assertions": {
            "initial_parses_files": initial["component_plan"]["files_to_parse"] >= 2,
            "noop_reuses_all_current_files": noop["component_plan"]["files_to_parse"] == 0 and noop["component_plan"]["files_reused"] >= 2,
            "edit_reparses_one_file": edit["component_plan"]["files_to_parse"] == 1,
            "delete_omits_removed_file": delete["component_plan"]["files_deleted"] == 1,
            "fingerprint_bump_reparses_current_files": bumped["component_plan"]["files_to_parse"] >= 2,
            "corrupt_cache_recomputes_one_file": corrupt_plan.summary()["files_to_parse"] == 1,
        },
    }
    summary["status"] = "pass" if all(summary["assertions"].values()) else "fail"
    _write_json(out / "proof-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
