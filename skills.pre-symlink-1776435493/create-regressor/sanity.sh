#!/usr/bin/env bash
# Sanity check for create-regressor
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

echo "=== create-regressor sanity check ==="

# 1. Import check
echo -n "[1/3] Import check... "
uv run python -c "
from lib.models import Regressor, auto_select, MODEL_REGISTRY
from lib.data import load_data, describe_data, split_data
from lib.storage import save_model, load_model, list_models
print(f'OK — {len(MODEL_REGISTRY)} model types: {list(MODEL_REGISTRY.keys())}')
"

# 2. Train + predict on synthetic data
echo -n "[2/3] Train + predict... "
uv run python -c "
import json, tempfile
from pathlib import Path
from lib.models import Regressor
from lib.data import load_data, split_data
from lib.storage import save_model, load_model

# Create synthetic JSONL
tmp = Path(tempfile.mktemp(suffix='.jsonl'))
rows = []
for i in range(50):
    rows.append(json.dumps({'x': i, 'y': i * 2.0 + 1, 'cat': 'a' if i % 2 == 0 else 'b'}))
tmp.write_text('\n'.join(rows))

# Load
fd, targets = load_data(tmp, 'y')
assert len(fd) == 50, f'Expected 50 rows, got {len(fd)}'

# Train
reg = Regressor(model_type='linear')
metrics = reg.train(fd, targets)
assert metrics['r2'] > 0.9, f'R2 too low: {metrics[\"r2\"]}'

# Predict
point, interval = reg.predict({'x': 25, 'cat': 'a'})
assert 40 < point < 60, f'Prediction out of range: {point}'

# Save + load roundtrip
import tempfile as tf
with tf.TemporaryDirectory() as td:
    save_model(reg, 'sanity_test', models_dir=Path(td))
    loaded = load_model('sanity_test', models_dir=Path(td))
    p2, _ = loaded.predict({'x': 25, 'cat': 'a'})
    assert abs(p2 - point) < 0.01, f'Roundtrip mismatch: {p2} vs {point}'

tmp.unlink()
print(f'OK — R2={metrics[\"r2\"]:.4f}, prediction={point:.2f}')
"

# 3. Auto-select
echo -n "[3/3] Auto-select... "
uv run python -c "
import json, tempfile
from pathlib import Path
from lib.models import auto_select

# Synthetic data
fd = [{'x': i, 'z': i**2} for i in range(100)]
targets = [2 * i + 3 for i in range(100)]

best, cv = auto_select(fd, targets, cv_folds=3)
assert best in cv, f'Best model {best} not in cv results'
print(f'OK — best={best}, candidates={list(cv.keys())}')
"

echo ""
echo "=== All sanity checks passed ==="
