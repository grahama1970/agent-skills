#!/bin/bash
set -e

PORT="${VECTOR_STORE_PORT:-8600}"
URL="http://127.0.0.1:${PORT}"

echo "Resetting..."
curl -X DELETE "${URL}/reset"

echo "Indexing (Batch)..."
# v1=[1,0], v2=[0,1], v3=[-1,0]
curl -X POST "${URL}/index" \
  -H "Content-Type: application/json" \
  -d '{
    "ids": ["v1", "v2", "v3"],
    "vectors": [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.1]]
  }'

echo "Searching (Batch)..."
# q1=[1,0] (should find v1), q2=[0,1] (should find v2)
curl -X POST "${URL}/search" \
  -H "Content-Type: application/json" \
  -d '{
    "queries": [[1.0, 0.0], [0.0, 1.0]],
    "k": 2
  }' > /tmp/batch_res.json

echo "Response:"
cat /tmp/batch_res.json

# Validation
if grep -q "v1" /tmp/batch_res.json && grep -q "v2" /tmp/batch_res.json; then
    echo "Batch search successful!"
else
    echo "Batch search failed."
    exit 1
fi
