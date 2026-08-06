#!/usr/bin/env python3
"""Generate site/generated/battle-lineage.json from the recorded battle-004
adaptive-lineage fixture.

The homepage's "Proof Returns" hero instrument renders ONLY what this file
emits. The asserts below are the contract: if the recorded fixture drifts,
the site build fails rather than showing a stale or invented lineage. The
source fixture's SHA-256 is embedded so the figure is traceable without
exposing raw Battle paths.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE = (
    REPO
    / "skills/battle/spectator/public/battle-fixtures"
    / "battle-004-adaptive-lineage-live/adaptive-lineage-mechanics-fixture.json"
)
OUT = REPO / "site/generated/battle-lineage.json"


def main() -> None:
    raw = FIXTURE.read_bytes()
    fixture = json.loads(raw)

    assert fixture["schema"] == "battle.adaptive_lineage_mechanics_fixture.v1"
    assert fixture["battle_id"] == "battle-004"
    assert fixture["data_source"] == "live"
    assert fixture["qualification"]["status"] == "PASS"
    nodes = {node["id"]: node for node in fixture["nodes"]}
    assert set(nodes) == {"G0", "G1-A", "G1-B", "G2"}
    assert fixture["selection"]["selected_id"] == "G1-A"
    assert fixture["selection"]["runner_up_id"] == "G1-B"
    assert fixture["selection"]["deciding_criterion"] == "novelty_distance"
    assert nodes["G2"]["parentId"] == "G1-A"
    assert nodes["G1-A"]["mutation_operator"] == "method_replace"
    assert nodes["G1-B"]["mutation_operator"] == "oracle_or_parameter_mutation"
    assert nodes["G2"]["mutation_operator"] == "failure_guided_crossover"

    out = {
        "battleId": fixture["battle_id"],
        "runId": fixture["run_id"],
        "sourceSha256": hashlib.sha256(raw).hexdigest(),
        "qualification": fixture["qualification"]["status"],
        "criterion": fixture["selection"]["deciding_criterion"],
        "selectedId": fixture["selection"]["selected_id"],
        "runnerUpId": fixture["selection"]["runner_up_id"],
        "nodes": {
            node_id: {
                "id": node_id,
                "mutationOperator": node["mutation_operator"],
                "noveltyDistance": node["novelty_distance"],
                "techniqueDelta": node["technique_delta"],
                "changedDimensions": node["changed_dimensions"],
            }
            for node_id, node in nodes.items()
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} (source sha256 {out['sourceSha256'][:12]}…)")


if __name__ == "__main__":
    main()
