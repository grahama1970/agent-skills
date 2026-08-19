#!/usr/bin/env python3
"""G2i public benchmark pack integrity + promotion-gate proof (#1455).

Verifies, by readback:

- the pinned source copy matches the digest recorded in source-manifest.json;
- the pinned commit's README is byte-identical upstream when the network
  allows (skipped honestly offline, never faked);
- the pack's role rubric validates under live_evidence.role_rubric.v1 and its
  digest is deterministic;
- every benchmark requirement term traces to the pinned spec text (owned
  fixtures cannot invent stated requirements);
- claim hygiene: forbidden comparison formulations are rejected, the allowed
  formulation passes;
- the release marker is fail-closed: with zero blocking-case receipts the gate
  refuses LIVE_EVIDENCE_G2I_PUBLIC_BENCHMARK_READY.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    pack = root / "benchmarks" / "g2i-public-python-v1"
    sys.path.insert(0, str(pack / "oracles"))

    manifest = json.loads((pack / "source-manifest.json").read_text())
    benchmark = json.loads((pack / "benchmark.json").read_text())
    spec_path = pack / manifest["files"][0]["local_copy"]
    spec_bytes = spec_path.read_bytes()

    check(
        "pinned source copy matches manifest digest",
        hashlib.sha256(spec_bytes).hexdigest() == manifest["files"][0]["sha256"],
        manifest["files"][0]["sha256"][:16],
    )
    check(
        "manifest records commit, retrieval date, and license limitation",
        manifest["commit"] == "25ceb5ad7005782e3015a9da750143ac99a87fde"
        and bool(manifest.get("retrieval_date"))
        and "clean-room" in (manifest.get("license") or {}).get("limitation", ""),
    )

    # Upstream identity: live readback when the network allows; honest skip
    # otherwise (an offline run must not fake a network verification).
    url = (
        "https://raw.githubusercontent.com/g2i/python-api-challenge/"
        f"{manifest['commit']}/README.md"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            upstream = response.read()
        check("pinned commit README byte-identical upstream (live)", upstream == spec_bytes)
    except Exception as exc:
        print(f"pinned commit README byte-identical upstream (live): SKIP (offline: {type(exc).__name__})")

    # Rubric validates under the real contract and digests deterministically.
    from live_evidence.rubric import RoleRubric

    rubric_payload = json.loads((pack / "role-rubric.json").read_text())
    rubric = RoleRubric(**{k: v for k, v in rubric_payload.items() if k != "schema"})
    check(
        "pack rubric validates under live_evidence.role_rubric.v1 with deterministic digest",
        len(rubric.criteria) == 6
        and rubric.rubric_digest() == RoleRubric(
            **{k: v for k, v in rubric_payload.items() if k != "schema"}
        ).rubric_digest(),
        rubric.rubric_digest()[:16],
    )

    # No invented stated requirement: each requirement's anchor terms appear in
    # the pinned spec text itself.
    spec_text = " ".join(spec_bytes.decode("utf-8").lower().split())
    anchors = {
        "req-local-api": ["django rest framework"],
        "req-data-migration": ["departures.json", "data migration"],
        "req-pagination": ["next", "page"],
        "req-filter-date": ["june 1st, 2018", "start_date"],
        "req-filter-category": ["adventurous"],
        "req-csv-output": ["csv", "title-case"],
        "req-docs": ["readme"],
        "req-structure-testability": ["testable"],
    }
    missing: list[str] = []
    for requirement in benchmark["task_requirements"]:
        for term in anchors[requirement["id"]]:
            if term not in spec_text:
                missing.append(f"{requirement['id']}:{term}")
    check("every benchmark requirement traces to the pinned spec text", not missing,
          f"missing={missing}" if missing else f"requirements={len(benchmark['task_requirements'])}")

    # Claim hygiene.
    from claim_hygiene import ALLOWED_SHAPE, violations  # type: ignore

    bad_report = (
        "In this benchmark Live Evidence beats G2i and is better than G2i's "
        "production platform because we copied G2i's flow."
    )
    check("forbidden comparison formulations rejected",
          len(violations(bad_report)) >= 3, f"hits={violations(bad_report)}")
    check("allowed measured-metrics formulation passes", violations(ALLOWED_SHAPE) == [])

    # Promotion gate is fail-closed: no blocking-case receipts -> no marker.
    receipts_dir = pack / "receipts"
    blocking = benchmark["blocking_cases"]
    have = {
        case: sorted(receipts_dir.glob(f"{case}-trial-*.json")) if receipts_dir.exists() else []
        for case in blocking
    }
    ready = all(len(trials) >= 2 for trials in have.values())
    marker = benchmark["release_marker"] if ready else None
    check(
        "release marker refused while blocking cases lack two clean trials each",
        marker is None,
        f"cases_with_receipts={sum(1 for t in have.values() if t)}/{len(blocking)}",
    )

    print()
    if FAILURES:
        print(f"g2i benchmark pack: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("g2i benchmark pack: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
