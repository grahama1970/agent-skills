Download persona-dream-phase11-memory-identity-repair.patch

Incremental against:
  base commit 8be2a262f2ab5e1de4a39d96964dccadb9dd7b51
  plus applied patch 3d8c523a1ca80bf8fac70c4118847f22ea8082bb875d920cebeb692bc42d903e

Files changed:
  skills/persona-dream/scripts/phase11_canonical_common.py
  skills/persona-dream/tests/test_phase11_canonical_live_request.py

Byte count:
  13501

SHA-256:
  69501f375ce5ad5e301bdf3379a77d835bd5c74cd589cae3a5d4773554eb7e91

git apply --check:
  exit 0

git diff --check after application:
  exit 0

Targeted implementation harness:
  4 passed

Provider calls during proof:
  0

ArangoDB’s UPSERT ... UPDATE path partially updates an existing document, and UPDATE leaves unspecified attributes untouched. Separating exact requests by _key therefore fixes the collision without weakening the unexpected-field check or deleting history.
ArangoDB Docs
+1

Apply
Bash
set -euo pipefail

test "$(git rev-parse HEAD)" = \
  "8be2a262f2ab5e1de4a39d96964dccadb9dd7b51"

test "$(sha256sum /path/to/persona-dream-phase11-memory-identity-repair.patch | awk '{print $1}')" = \
  "69501f375ce5ad5e301bdf3379a77d835bd5c74cd589cae3a5d4773554eb7e91"

git apply --check \
  /path/to/persona-dream-phase11-memory-identity-repair.patch

git apply \
  /path/to/persona-dream-phase11-memory-identity-repair.patch

git diff --check
Focused deterministic test
Bash
python3 -m pytest -q \
  skills/persona-dream/tests/test_phase11_canonical_live_request.py

Expected count after application:

11 passed
Prove stable, noncolliding identities
Bash
PYTHONPATH=skills/persona-dream/scripts python3 - <<'PY'
from phase11_canonical_common import (
    legacy_phase11_memory_key,
    phase11_memory_key,
)

run_id = "pipeline-complete"
revision_id = "rev_idea_f3f9c48d5cc2"
failed = "sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71"
corrected = "sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16"

legacy_key = legacy_phase11_memory_key(run_id, revision_id)
failed_key = phase11_memory_key(run_id, revision_id, failed)
corrected_key = phase11_memory_key(run_id, revision_id, corrected)

assert legacy_key == (
    "pd_phase11_d1440cf980f38c916f0fa93bff648b17e036e58feb43a941"
)
assert failed_key == (
    "pd_phase11_ab56b1cf2875c1c9c35871073006bdc779397deae2777732"
)
assert corrected_key == (
    "pd_phase11_11c0a72cef02a4966cb3f21852341629a21dccbc6d2789ad"
)
assert len({legacy_key, failed_key, corrected_key}) == 3

print(f"legacy={legacy_key}")
print(f"failed_request={failed_key}")
print(f"corrected_request={corrected_key}")
print("PASS_PHASE11_REQUEST_SCOPED_MEMORY_KEYS")
PY
Preserve and recover the failed request history

This reads the already-collided legacy record, creates a separate request-scoped historical copy from the committed immutable failure receipt, and proves the legacy record was not changed or deleted.

Bash
set -euo pipefail

export MEMORY_URL="http://127.0.0.1:8601"
export COLLECTION="project_knowledge"
export RUN_ROOT="$PWD/skills/persona-dream/reports/pipeline-complete"
export REVISION_ID="rev_idea_f3f9c48d5cc2"
export FAILED_REQUEST_SHA="sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71"
export CORRECTED_REQUEST_SHA="sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16"

export LEGACY_KEY="$(
  PYTHONPATH=skills/persona-dream/scripts python3 - <<'PY'
from phase11_canonical_common import legacy_phase11_memory_key
print(legacy_phase11_memory_key(
    "pipeline-complete",
    "rev_idea_f3f9c48d5cc2",
))
PY
)"

export FAILED_SCOPED_KEY="$(
  PYTHONPATH=skills/persona-dream/scripts python3 - <<'PY'
from phase11_canonical_common import phase11_memory_key
print(phase11_memory_key(
    "pipeline-complete",
    "rev_idea_f3f9c48d5cc2",
    "sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71",
))
PY
)"

export FAILURE_RECEIPT="$RUN_ROOT/.persona-dream/revisions/$REVISION_ID/phase_11_submit_return/attempts/${FAILED_REQUEST_SHA#sha256:}/memory_failure_persistence_receipt.v1.json"

test -f "$FAILURE_RECEIPT"

Snapshot the legacy record:

Bash
jq -nc \
  --arg collection "$COLLECTION" \
  --arg key "$LEGACY_KEY" \
  '{
    collection: $collection,
    limit: 2,
    offset: 0,
    sort_field: "_key",
    sort_order: "ASC",
    filters: {_key: $key}
  }' >/tmp/pd11-legacy-list-request.json

http_code="$(
  curl -sS \
    -o /tmp/pd11-legacy-before.json \
    -w '%{http_code}' \
    -X POST "$MEMORY_URL/list" \
    -H 'Content-Type: application/json' \
    --data-binary @/tmp/pd11-legacy-list-request.json
)"
test "$http_code" = "200"

jq -e \
  --arg key "$LEGACY_KEY" '
  .count == 1
  and .total == 1
  and (.documents | length) == 1
  and .documents[0]._key == $key
' /tmp/pd11-legacy-before.json

legacy_before_sha="$(
  jq -S -c '.documents[0]' /tmp/pd11-legacy-before.json |
    sha256sum |
    awk '{print $1}'
)"

Fail closed if the request-scoped failed-history key is unexpectedly occupied:

Bash
jq -nc \
  --arg collection "$COLLECTION" \
  --arg key "$FAILED_SCOPED_KEY" \
  '{
    collection: $collection,
    limit: 2,
    offset: 0,
    sort_field: "_key",
    sort_order: "ASC",
    filters: {_key: $key}
  }' >/tmp/pd11-failed-scoped-list-request.json

http_code="$(
  curl -sS \
    -o /tmp/pd11-failed-scoped-before.json \
    -w '%{http_code}' \
    -X POST "$MEMORY_URL/list" \
    -H 'Content-Type: application/json' \
    --data-binary @/tmp/pd11-failed-scoped-list-request.json
)"
test "$http_code" = "200"
jq -e '.count == 0 and .total == 0' \
  /tmp/pd11-failed-scoped-before.json

Build the historical document from the committed failure receipt:

Bash
PYTHONPATH=skills/persona-dream/scripts \
python3 - \
  "$FAILURE_RECEIPT" \
  "$RUN_ROOT" \
  "$REVISION_ID" \
  "$FAILED_REQUEST_SHA" \
  "$COLLECTION" \
  >/tmp/pd11-failed-history-upsert.json <<'PY'
import json
import sys
from pathlib import Path

from phase11_canonical_common import canonical_sha256, phase11_memory_key

receipt_path = Path(sys.argv[1])
run_root = Path(sys.argv[2])
revision_id = sys.argv[3]
request_sha256 = sys.argv[4]
collection = sys.argv[5]
run_id = run_root.name

receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
assert receipt["status"] == "PASS_PHASE11_FAILURE_MEMORY_PERSISTED"

document = dict(receipt["document"])
assert document["run_id"] == run_id
assert document["phase11_revision_id"] == revision_id
assert document["request_body_sha256"] == request_sha256
assert document["actual_provider_call_attempts"] == 1
assert document["automatic_resubmit_allowed"] is False
assert document["returned_video"] is False
assert document["watch_invoked"] is False

# Remove only Memory-owned response metadata. No domain field is ignored.
for field in (
    "_id",
    "_rev",
    "qdrant_collection",
    "qdrant_point_id",
    "embedding_model",
    "embedding_version",
    "text_hash",
    "semantic_sync_state",
):
    document.pop(field, None)

request_identity = request_sha256.removeprefix("sha256:")
document["_key"] = phase11_memory_key(
    run_id,
    revision_id,
    request_sha256,
)
document["scope"] = (
    f"persona-dream:{run_id}:{revision_id}:"
    f"phase11:request:{request_identity}"
)
document["source"] = (
    f"persona-dream://{run_id}/revisions/{revision_id}/"
    f"phase11/requests/{request_identity}"
)

request_tag = f"phase11-request:{request_identity}"
tags = [str(value) for value in document.get("tags", [])]
document["tags"] = list(dict.fromkeys([*tags, request_tag]))

document.pop("document_contract_sha256", None)
document["document_contract_sha256"] = canonical_sha256(document)

print(json.dumps(
    {
        "collection": collection,
        "documents": [document],
    },
    indent=2,
    sort_keys=True,
    ensure_ascii=False,
))
PY

Persist and exactly reread the failed request under its new immutable identity:

Bash
http_code="$(
  curl -sS \
    -o /tmp/pd11-failed-history-upsert-response.json \
    -w '%{http_code}' \
    -X POST "$MEMORY_URL/upsert" \
    -H 'Content-Type: application/json' \
    --data-binary @/tmp/pd11-failed-history-upsert.json
)"
test "$http_code" = "200"

jq -e '
  ((.inserted // 0) + (.updated // 0)) == 1
  and ((.errors // []) | length) == 0
' /tmp/pd11-failed-history-upsert-response.json

http_code="$(
  curl -sS \
    -o /tmp/pd11-failed-scoped-after.json \
    -w '%{http_code}' \
    -X POST "$MEMORY_URL/list" \
    -H 'Content-Type: application/json' \
    --data-binary @/tmp/pd11-failed-scoped-list-request.json
)"
test "$http_code" = "200"

jq -e \
  --arg key "$FAILED_SCOPED_KEY" \
  --arg request "$FAILED_REQUEST_SHA" '
  .count == 1
  and .total == 1
  and .documents[0]._key == $key
  and .documents[0].request_body_sha256 == $request
  and .documents[0].actual_provider_call_attempts == 1
  and .documents[0].submit_intent_count == 1
  and .documents[0].lifecycle_state == "FAILED_CANARY"
  and .documents[0].automatic_resubmit_allowed == false
  and .documents[0].returned_video == false
  and .documents[0].watch_invoked == false
  and .documents[0].semantic_sync_state == "synced"
  and (.documents[0].qdrant_point_id | length) > 0
' /tmp/pd11-failed-scoped-after.json

Prove the legacy record remains byte-equivalent at the JSON level:

Bash
http_code="$(
  curl -sS \
    -o /tmp/pd11-legacy-after.json \
    -w '%{http_code}' \
    -X POST "$MEMORY_URL/list" \
    -H 'Content-Type: application/json' \
    --data-binary @/tmp/pd11-legacy-list-request.json
)"
test "$http_code" = "200"

legacy_after_sha="$(
  jq -S -c '.documents[0]' /tmp/pd11-legacy-after.json |
    sha256sum |
    awk '{print $1}'
)"

test "$legacy_after_sha" = "$legacy_before_sha"
printf 'PASS_LEGACY_RECORD_UNCHANGED=%s\n' "$LEGACY_KEY"
printf 'PASS_FAILED_REQUEST_HISTORY=%s\n' "$FAILED_SCOPED_KEY"
Rerun live corrected-request validation
Bash
set -o pipefail

skills/persona-dream/run.sh \
  validate-phase11-canonical-live-request \
  --run-root "$PWD/skills/persona-dream/reports/pipeline-complete" \
  --revision-id rev_idea_f3f9c48d5cc2 \
  --persist-memory \
  --memory-url http://127.0.0.1:8601 \
  --collection project_knowledge \
  --json |
  tee /tmp/persona-dream-phase11-memory-identity-validation.json
Bash
export CORRECTED_SCOPED_KEY="$(
  PYTHONPATH=skills/persona-dream/scripts python3 - <<'PY'
from phase11_canonical_common import phase11_memory_key
print(phase11_memory_key(
    "pipeline-complete",
    "rev_idea_f3f9c48d5cc2",
    "sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16",
))
PY
)"

jq -e \
  --arg request "$CORRECTED_REQUEST_SHA" \
  --arg key "$CORRECTED_SCOPED_KEY" \
  --arg legacy "$LEGACY_KEY" '
  .validator_status
      == "PASS_PHASE11_CANONICAL_BOUNDARY_VALIDATED"
  and .gate_status == "BLOCKED_AWAITING_HUMAN_APPROVAL"
  and .request_body_sha256 == $request
  and .technical_blockers == []
  and (
    .missing_approval_types | sort
  ) == (
    [
      "publication_authorization",
      "visual_media_acceptance",
      "exact_request_acceptance",
      "cost_acceptance",
      "paid_call_authorization"
    ] | sort
  )
  and .memory.persisted == true
  and .memory.request_body_sha256 == $request
  and .memory.phase11_key == $key
  and .memory.legacy_phase11_key == $legacy
  and .memory.exact_reread_count == 1
  and .memory.semantic_sync_state == "synced"
  and .memory.recall.matching_identity_count >= 1
  and .memory.recall.dense_matching_count >= 1
  and .memory.recall.max_dense > 0
  and .actual_provider_call_attempts == 0
  and .provider_live == false
  and .paid_call_authorized == false
  and .submitted == false
  and .provider_ready == false
  and .live_submit_ready == false
' /tmp/persona-dream-phase11-memory-identity-validation.json
