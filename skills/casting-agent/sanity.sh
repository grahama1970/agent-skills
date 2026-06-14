#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/run.sh" sanity
ARTIFACT_ROOT="${CASTING_AGENT_SANITY_ROOT:-/mnt/storage12tb/skills/casting-agent/outputs/sanity-e2e/latest}"
rm -rf "$ARTIFACT_ROOT"
mkdir -p "$ARTIFACT_ROOT"
"$SCRIPT_DIR/run.sh" sanity-e2e --artifact-root "$ARTIFACT_ROOT"

GOOD_JOB="$ARTIFACT_ROOT/positive"
BROKEN_JOB="$ARTIFACT_ROOT/broken-missing-terminal-state"
rm -rf "$BROKEN_JOB"
mkdir -p "$BROKEN_JOB"
cp "$GOOD_JOB/casting_contract.json" "$BROKEN_JOB/casting_contract.json"
cp "$GOOD_JOB/chosen_reference_inputs.json" "$BROKEN_JOB/chosen_reference_inputs.json"
cp "$GOOD_JOB/contact_sheet_work_order.json" "$BROKEN_JOB/contact_sheet_work_order.json"

if "$SCRIPT_DIR/run.sh" verify --job-dir "$BROKEN_JOB" >/tmp/casting-agent-verify-broken.json 2>&1; then
  echo "broken casting fixture unexpectedly passed verify" >&2
  exit 1
fi

export GOOD_JOB
python3 - <<'PY'
import json
import os
from pathlib import Path

job = Path(os.environ["GOOD_JOB"])
contract = json.loads((job / "casting_contract.json").read_text())
receipt_dir = job / "contact_sheet_receipts"
receipt_dir.mkdir(exist_ok=True)
entities = []
for entity in contract["entities"]:
    entity_id = entity["entity_id"]
    receipt_path = receipt_dir / f"{entity_id}.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "casting_agent.sanity_contact_sheet_receipt.v1",
                "entity_id": entity_id,
                "status": "accepted",
            },
            indent=2,
        )
        + "\n"
    )
    entities.append(
        {
            "entity_id": entity_id,
            "status": "accepted",
            "contact_sheet_receipt_path": str(receipt_path.relative_to(job)),
        }
    )
(job / "accepted_casting_receipt.json").write_text(
    json.dumps(
        {
            "schema": "casting_agent.accepted_casting_receipt.v1",
            "status": "accepted",
            "entities": entities,
        },
        indent=2,
    )
    + "\n"
)
PY

"$SCRIPT_DIR/run.sh" verify --job-dir "$GOOD_JOB" >/tmp/casting-agent-verify-good.json
"$SCRIPT_DIR/run.sh" file-maintainer-ticket --job-dir "$BROKEN_JOB" >/tmp/casting-agent-maintainer-ticket.json
test -f "$GOOD_JOB/verify-receipt.json"
test -f "$BROKEN_JOB/verify-receipt.json"
test -f "$BROKEN_JOB/maintainer-ticket.json"
